from typing import List, TypeVar, Any, Optional, Union, Dict
import dataclasses
import inspect

from yaml import MarkedYAMLError

import typing_inspect
import enum

from yaml.composer import Composer
from yaml.constructor import Constructor
from yaml.nodes import ScalarNode
from yaml.resolver import BaseResolver
from yaml.loader import SafeLoader

from bentoudev.dataclass.base import DataclassLoadError, UnhandledType, EErrorFormat, Source, SourceTracker, get_inline_load_type, get_type_name, is_inline_loaded, is_source_tracked, is_clazz_dict, is_clazz_list, track_source


class DataclassVisitorContext:
    ext_types : List[TypeVar]
    type_cache = {}
    clazz_stack = []
    yaml_content : str
    yaml_lines : List[str]
    filename : str
    error_format : EErrorFormat
    always_track_source : bool
    code_snippet_lines : int

    def get_yaml_line(self, line: int):
        return self.yaml_lines[ min(line, len(self.yaml_lines) - 1) ]

    def get_location_source(self, field_name:str = "") -> Optional[Source]:
        stack_len = len(self.clazz_stack)

        if stack_len > 0:
            top_object = self.clazz_stack[stack_len - 1]

            if isinstance(top_object, YamlSourceTracker):
                if field_name == "":
                    return top_object.get_source()
                return top_object.get_field_source(field_name)

            elif isinstance(top_object, Source):
                return top_object

        return Source(0, 0, SourceTracker.build_code_snippet(self.get_yaml_line, 0, self.code_snippet_lines), self.filename)

    # def get_location_msg(self, field_name:str = ""):
    #     stack_len = len(self.clazz_stack)

    #     if stack_len > 0:
    #         top_object = self.clazz_stack[stack_len - 1]

    #         if isinstance(top_object, YamlSourceTracker):
    #             if field_name == "":
    #                 return top_object.format_source()
    #             return top_object.format_field_source(field_name)

    #         elif isinstance(top_object, Source):
    #             return top_object.format()

    #     return ''


class YamlSourceLocation:
    line: int
    column: int

    def __init__(self, line:int, column:int):
        self.line = line
        self.column = column


class YamlFieldLocation:
    name: str


class FieldLocationScope:
    def __init__(self, field_name:str, loc:Source, context: DataclassVisitorContext):
        self.field_name = field_name
        self.source_loc = loc
        self.context = context

    def __enter__(self):
        if self.source_loc is not None:
            self.context.clazz_stack.append(self.source_loc)

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.source_loc is not None:
            self.context.clazz_stack.remove(self.source_loc)


def load_bool(value, context: DataclassVisitorContext):
    value_t = type(value)
    if value_t is bool:
        return value

    if value_t is int:
        if value in [0, 1]:
            return bool(value)

    if value_t is str:
        lowercase_value = value.lower()
        true_values = ['true', 'on', 'yes', 'ok', 'enable']
        false_values = ['false', 'off', 'no', 'nook', 'disable']

        if lowercase_value in true_values:
            return True
        elif lowercase_value in false_values:
            return False

        loc_src = context.get_location_source()
        raise DataclassLoadError.from_source(f"Got '{value}' when expecting a bool", loc_src, context.error_format)

    loc_src = context.get_location_source()
    raise DataclassLoadError.from_source(f"Got '{value_t}' when expecting a bool", loc_src, context.error_format)


def load_int(value, context: DataclassVisitorContext):
    value_t = type(value)
    if value_t != int:
        loc_src = context.get_location_source()
        raise DataclassLoadError.from_source(f"Got '{value_t}' when expecting an int", loc_src, context.error_format)

    return int(value)


def load_float(value, context: DataclassVisitorContext):
    supported_types = [int, float]
    value_t = type(value)

    if value_t not in supported_types:
        loc_src = context.get_location_source()
        raise DataclassLoadError.from_source(f"Got '{value_t}' when expecting a float", loc_src, context.error_format)

    return float(value)


def load_str(value, context: DataclassVisitorContext):
    supported_types = [str, bool, int, float]
    value_t = type(value)

    if value_t not in supported_types:
        loc_src = context.get_location_source()
        raise DataclassLoadError(f"Got '{value_t}' when expecting a string", loc_src, context.error_format)

    return f'{value}'


def default_type_loaders():
    return {
        bool : load_bool,
        int  : load_int,
        float: load_float,
        str  : load_str
    }


def is_field_hidden(field_name:str):
    return field_name.startswith('__')


def get_dict_items(data):
    def is_normal_field(tuple):
        name, _ = tuple
        if type(name) is str and is_field_hidden(name):
            return False
        return True

    return list(filter(is_normal_field, data.items()))


def is_obj_dict(obj):
    return is_clazz_dict(obj)


def is_obj_list(obj):
    return is_clazz_list(obj)


def is_obj_tracked(obj):
    if is_obj_dict(type(obj)):
        return '__yaml_location__' in obj and '__yaml_field_location__' in obj
    return (hasattr(obj, '__yaml_location__') and hasattr(obj, '__yaml_field_location__'))



class YamlSourceTracker(SourceTracker):

    @staticmethod
    def yaml_to_src(yaml_loc: YamlSourceLocation, context: DataclassVisitorContext) -> Source:
        start_line: int = yaml_loc.line
        buff = context.get_yaml_line(start_line - 1)
        column: int = len(buff) - len(buff.lstrip(' \t'))

        snippet: List[str] = SourceTracker.build_code_snippet(context.get_yaml_line, start_line, context.code_snippet_lines)

        return Source(
            line_number=start_line,
            column_number=column,
            buffer='\n'.join(snippet),
            file_name=context.filename
        )

    @staticmethod
    def from_yaml_obj(root: Any, context: DataclassVisitorContext, fields: list):
        root_loc : YamlSourceLocation = root['__yaml_location__']
        field_loc = root['__yaml_field_location__']
        return YamlSourceTracker(YamlSourceTracker.yaml_to_src(root_loc, context), field_loc, fields, context)

    @staticmethod
    def from_inline(root_loc: Source, context: DataclassVisitorContext):
        return YamlSourceTracker(root_loc, None, [], context)

    def __init__(self, root_loc: Source, field_loc: dict, fields: list, context: DataclassVisitorContext):
        super().__init__(root_loc)
        for name, _ in fields:
            loc : YamlSourceLocation = field_loc[name]
            super().track_field(name, self.yaml_to_src(loc, context))

    def __eq__(self, other):
        if isinstance(other, YamlSourceTracker):
            return self.__root_src__ == other.__root_src__
        return False

    def __ne__(self, other):
        return not(self == other)


def YamlToScalar(clazz: type, yaml_obj: Any, context: DataclassVisitorContext):
    if inspect.isclass(clazz) and issubclass(clazz, enum.Enum):
        value_t = type(yaml_obj)
        if value_t is not str:
            loc_src = context.get_location_source()
            raise DataclassLoadError(f"Got '{value_t.__name__}' when expecting enum '{clazz.__name__}'", loc_src, context.error_format)

        allowed_values = list(map(lambda i: i[0], clazz.__members__.items()))
        if yaml_obj not in allowed_values:
            loc_src = context.get_location_source()
            allowed_values_str = ', '.join(allowed_values)
            raise DataclassLoadError(f"Got '{yaml_obj}' when expecting enum '{clazz.__name__}' with one of values: {allowed_values_str}", loc_src, context.error_format)

        return clazz[yaml_obj]

    elif clazz in context.type_cache:
        return context.type_cache[clazz](yaml_obj, context)

    raise UnhandledType(f"Unhandled type '{clazz}', unable to load value '{yaml_obj}'")


def YamlToObject(clazz: type, yaml_obj: Any, context: DataclassVisitorContext, field_name:str='', field_loc:Source=None):
    with FieldLocationScope(field_name, field_loc, context):
        with FieldLocationScope(field_name, YamlSourceTracker.from_yaml_obj(yaml_obj, context, []) if is_obj_tracked(yaml_obj) else None, context):
            if typing_inspect.is_forward_ref(clazz):
                for t in context.ext_types:
                    if get_type_name(t) == clazz.__forward_arg__:
                        return YamlToObject(t, yaml_obj, context)

            if dataclasses.is_dataclass(clazz):
                return DictToDataclass(clazz, yaml_obj, context)

            elif is_obj_list(clazz):
                subtype = clazz.__args__[0]

                # Loading multi element list
                if is_obj_list(type(yaml_obj)):
                    num_items = len(yaml_obj)
                    if num_items == 0:
                        return []

                    result = []
                    for x in range(num_items):
                        result.append(YamlToObject(subtype, yaml_obj[x], context))
                    return result
                # Loading inline, single element
                else:
                    return [ YamlToObject(subtype, yaml_obj, context) ]

            elif typing_inspect.is_optional_type(clazz):
                subtype = clazz.__args__[0]
                return YamlToObject(subtype, yaml_obj, context)

            elif typing_inspect.get_origin(clazz) is Union:
                preffered_type = type(yaml_obj)
                union_types = typing_inspect.get_args(clazz)

                # Check the type of the value, it may fit just fine
                if preffered_type in union_types:
                    try:
                        result = YamlToObject(preffered_type, yaml_obj, context)
                    except UnhandledType as err:
                        pass
                    else:
                        return result

                else:
                    failed_attempts = []
                    for possible_dict_t in union_types:
                        try:
                            result = YamlToObject(possible_dict_t, yaml_obj, context)
                        except Exception as err:
                            failed_attempts.append(str(err))
                        else:
                            return result

                    attempt_msg = '\n'.join(failed_attempts)
                    allowed_types = ', '.join([t.__name__ for t in union_types] )
                    loc_src = context.get_location_source()
                    raise DataclassLoadError(f"Got '{type(yaml_obj)}' when expecting 'Union [{allowed_types}]'. Failed to substitute all Union types:\n{attempt_msg}", loc_src, context.error_format)

                allowed_types = ', '.join([t.__name__ for t in union_types] )
                loc_src = context.get_location_source()
                raise DataclassLoadError(f"Got '{type(yaml_obj)}' when expecting 'Union [{allowed_types}]'", loc_src, context.error_format)

            elif is_obj_dict(clazz):
                key_type, value_type = typing_inspect.get_args(clazz)

                if not is_obj_dict(type(yaml_obj)):
                    loc_src = context.get_location_source()
                    raise DataclassLoadError(f"Got '{type(yaml_obj)}', when expecting 'Dict [{key_type.__name__},{value_type.__name__}]'", loc_src, context.error_format)

                entries = get_dict_items(yaml_obj)

                result = { YamlToScalar(key_type, entry[0], context) : YamlToObject(value_type, entry[1], context) for entry in entries }
                return result

            return YamlToScalar(clazz, yaml_obj, context)


class LineLoader(SafeLoader):
    def __init__(self, stream):
        super(LineLoader, self).__init__(stream)

    def compose_node(self, parent, index):
        line = self.line
        column =  self.column
        node = Composer.compose_node(self, parent, index)
        node.__line__ = line + 1
        node.__column__ = column + 1
        return node

    def construct_mapping(self, node, deep=False):
        node_pair_lst = node.value
        locations = {}

        for key_node, _ in node_pair_lst:
            locations[key_node.value] = YamlSourceLocation(key_node.__line__, key_node.__column__)

        location_node_name = ScalarNode(tag=BaseResolver.DEFAULT_SCALAR_TAG, value='__yaml_field_location__')
        location_node_value = ScalarNode(tag=BaseResolver.DEFAULT_SCALAR_TAG, value=locations)

        node_pair_lst.append((location_node_name, location_node_value))
        node.value = node_pair_lst

        mapping = Constructor.construct_mapping(self, node, deep=deep)
        mapping['__yaml_location__'] = YamlSourceLocation(node.__line__, node.__column__)

        return mapping


def validate_dataclass_fields(clazz:type, yaml_obj:dict, fields:List[dataclasses.Field], context: DataclassVisitorContext):
    missing_fields = []
    unknown_fields = []
    entry_names = [ f[0] for f in get_dict_items(yaml_obj) ]
    field_names = [ f.name for f in fields ]

    for field in fields:
        if not typing_inspect.is_optional_type(field.type):
            if field.name not in entry_names:
                missing_fields.append(field.name)

    for entry in entry_names:
        if entry not in field_names:
            unknown_fields.append(entry)

    has_unknown_fields : bool = len(unknown_fields) > 0
    has_missing_fields : bool = len(missing_fields) > 0

    if has_unknown_fields or has_missing_fields:
        # Compund error, a lot can happen here
        root_src = context.get_location_source()

        lines = []
        if has_unknown_fields:
            for entry in unknown_fields:
                loc_src = context.get_location_source(entry)
                lines.append(
                    loc_src.format(DataclassLoadError.LABEL, f"Unknown field '{entry}' for class '{clazz.__name__}'", context.error_format)
                )

        if has_missing_fields:
            lines.append(
                root_src.format(DataclassLoadError.LABEL, f"Missing required field(s) of class '{clazz.__name__}': { ','.join(missing_fields) }", context.error_format)
            )

        msg = '\n'.join(lines)

        raise DataclassLoadError(msg, root_src, context.error_format)


def DictToDataclass(clazz: type, yaml_obj: Any, context: DataclassVisitorContext):
    if not dataclasses.is_dataclass(clazz):
        raise ValueError(f'Class \'{clazz}\' passed to YAMLToDataclass must be a dataclass!')

    if is_obj_dict(type(yaml_obj)):

        if context.always_track_source:
            clazz = track_source(clazz)

        st = None
        if is_source_tracked(clazz):
            st = YamlSourceTracker.from_yaml_obj(yaml_obj, context, get_dict_items(yaml_obj))
            context.clazz_stack.append(st)

        def get_field_src(name:str):
            if st is not None:
                return st.get_field_source(name)
            return None

        clazz_fields = list(dataclasses.fields(clazz))
        validate_dataclass_fields(clazz, yaml_obj, clazz_fields, context)

        fieldtypes = { f.name : f.type for f in clazz_fields }
        result = clazz(
            **{ name : YamlToObject(fieldtypes[name], val, context, name, get_field_src(name)) for name, val in get_dict_items(yaml_obj) }
        )

        if st is not None:
            result.set_source_tracker(st)
            context.clazz_stack.remove(st)

        return result

    else:
        if is_inline_loaded(clazz):
            loader = get_inline_load_type(clazz)
            loaded_val = YamlToScalar(loader.inline_type, yaml_obj, context)
            result = loader.loader(loaded_val)
        else:
            result = yaml_obj

        if is_source_tracked(clazz) and hasattr(result, 'set_source_tracker'):
            stack_len = len(context.clazz_stack)
            if stack_len > 0:
                st = context.clazz_stack[stack_len - 1]
                result.set_source_tracker(YamlSourceTracker.from_inline(st, context))
            else:
                raise ValueError(f"Unable to set source tracker for {clazz}")

        return result


def load_yaml_dataclass(clazz:type, label:str, yaml_content:str, *, type_cache:dict=default_type_loaders(), ext_types:list=[],
        error_format:EErrorFormat=EErrorFormat.Pretty, always_track_source:bool=False, error_code_snippet_lines:int=4):
    try:
        context = DataclassVisitorContext()
        context.ext_types = ext_types
        context.type_cache = type_cache
        context.yaml_content = yaml_content
        context.yaml_lines = yaml_content.splitlines()
        context.filename = label
        context.error_format = error_format
        context.always_track_source = always_track_source
        context.code_snippet_lines = error_code_snippet_lines

        loader = LineLoader(yaml_content)
        loaded_yaml = loader.get_single_data()

        parsed_yaml = DictToDataclass(clazz, loaded_yaml, context)
        return parsed_yaml

    except MarkedYAMLError as err:
        # Re-raise as our custom exception, for consistency
        # TODO: should we track context_mark here also? We already merge multiple errors for dataclass field validation
        raise DataclassLoadError.from_source(err.problem, Source(
            err.problem_mark.line, err.problem_mark.column, err.problem_mark.get_snippet(), err.problem_mark.name
        ), error_format)
