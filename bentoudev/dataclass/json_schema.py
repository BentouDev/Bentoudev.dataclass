import dataclasses
from bentoudev.dataclass.base import get_type_name, is_clazz_list, is_enum
import typing_inspect
from typing import List, Dict, Tuple, TypeVar, Union, Any
from abc import ABC, abstractmethod


class DataclassJsonSchema(dict):
    pass


def handle_string():
    return {
        "type" : "string"
    }

def handle_float():
    return {
        "type" : "number"
    }

def handle_int():
    return {
        "type" : "integer"
    }

def handle_bool():
    return {
        "type" : "boolean"
    }


SIMPLE_HANDLERS = {
    str : handle_string,
    float : handle_float,
    int : handle_int,
    bool : handle_bool
}


class Handler(ABC):
    @abstractmethod
    def condition(self, clazz:type) -> bool:
        pass

    @abstractmethod
    def handle(self, ctx:'BuilderContext', clazz:type) -> dict:
        pass

    def can_recurse(self) -> bool:
        return True


@dataclasses.dataclass
class CheckDefault:
    # Python doesnt allow comparing to dataclasses.MISSING
    field:str

    @staticmethod
    def check(field:dataclasses.Field):
        fs = list(dataclasses.fields(CheckDefault))
        obj = { f.name : f for f in fs }
        return field.default != obj['field'].default


def field_has_valid_default(field:dataclasses.Field):
    if field.default is None:
        return False
    if field.default == '':
        return False
    return CheckDefault.check(field)


# intermediate data
class BuilderContext:
    dataclazzes : Dict[type, DataclassJsonSchema]
    handlers: List[Handler]
    ext_types: List[TypeVar]

    _handler_stack: List[Handler]

    def __init__(self) -> None:
        self.dataclazzes = dict()
        self.handlers = []
        self._handler_stack = []
        self.ext_types = []

    def _ensure_no_recurse(self, handler:Handler):
        if not handler.can_recurse() and handler in self._handler_stack:
            return False
        return True

    def find_dataclass_schema(self, clazz:type):
        return self.dataclazzes.get(clazz, None)

    def create_dataclass_schema(self, clazz:type):
        assert clazz not in self.dataclazzes
        schema = DataclassJsonSchema()
        schema['type'] = 'object'
        schema['properties'] = {}
        schema['additionalProperties'] = False
        schema['title'] = clazz.__name__
        self.dataclazzes[clazz] = schema
        return schema

    def handle_dataclass(self, clazz:type):
        # Prevent recursion, allow class to reference itself
        schema = self.find_dataclass_schema(clazz)
        ref = { '$ref' : f'#/$defs/{clazz.__name__}' }
        if schema is not None:
            return ref

        schema = self.create_dataclass_schema(clazz)
        props = schema['properties']
        required = []

        if not dataclasses.is_dataclass(clazz):
            raise ValueError(f'Class \'{clazz}\' passed to YAMLToDataclass must be a dataclass!')

        clazz_fields = list(dataclasses.fields(clazz))
        for field in clazz_fields:
            if not typing_inspect.is_optional_type(field.type):
                required.append(field.name)

            field_schema = self.handle_type(field.type)

            if field_has_valid_default(field):
                field_schema['default'] = field.default

            props[field.name] = field_schema

        if len(required) != 0:
            schema['required'] = required

        return ref

    def handle_type(self, clazz:type) -> dict:
        for h in self.handlers:
            if h.condition(clazz) and self._ensure_no_recurse(h):
                self._handler_stack.append(h)
                result = h.handle(self, clazz)
                self._handler_stack.pop()
                return result

        if typing_inspect.is_forward_ref(clazz):
            for t in self.ext_types:
                if get_type_name(t) == clazz.__forward_arg__:
                    return self.handle_type(t)

        if dataclasses.is_dataclass(clazz):
            return self.handle_dataclass(clazz)

        simple_h = SIMPLE_HANDLERS.get(clazz, None)
        if simple_h is not None:
            return simple_h()

        raise ValueError(f"Unable to handle type {clazz}!")

    def anyOf(self, typez:List[type]) -> dict:
        return {
            "anyOf" : [
                self.handle_type(tt) for tt in typez
            ]
        }

    def array(self, typez:type) -> dict:
        return {
            "items" : self.handle_type(typez),
            "type" : "array"
        }


class ListHandler(Handler):
    def condition(self, clazz: type) -> bool:
        return is_clazz_list(clazz)

    def handle(self, ctx: BuilderContext, clazz: type) -> Dict:
        subtype = clazz.__args__[0]
        return ctx.array(subtype)


class AnyHandler(Handler):
    def condition(self, clazz: type) -> bool:
        return clazz is Any

    def handle(self, ctx: BuilderContext, clazz: type) -> Dict:
        return {}


class UnionHandler(Handler):
    def condition(self, clazz: type) -> bool:
        return typing_inspect.is_union_type(clazz)

    def handle(self, ctx: BuilderContext, clazz: type) -> Dict:
        return ctx.anyOf(typing_inspect.get_args(clazz, evaluate=True))


# Allows enums to be set by their values names.
class EnumHandler(Handler):
    def condition(self, clazz: type) -> bool:
        return is_enum(clazz)

    def handle(self, ctx: BuilderContext, clazz: type) -> Dict:
        return {
            "enum": [ name for name, _ in clazz.__members__.items() ]
        }


# Ommits nulls from schema, so that optional fields are either not present at all or have value.
class NoNullHandler(Handler):
    def condition(self, clazz: type) -> bool:
        return typing_inspect.is_optional_type(clazz)

    def _build_union(self, *args):
        return Union[ args ]

    def handle(self, ctx: BuilderContext, clazz: type) -> Dict:
        subtypes: List[type] = [ i for i in typing_inspect.get_args(clazz, evaluate=True) ]
        for idx, t in enumerate(subtypes):
            if t is type(None):
                del subtypes[idx]
        if len(subtypes) == 1:
            return ctx.handle_type(subtypes[0])
        else:
            return ctx.handle_type(self._build_union(*subtypes))


# Allows arrays to be set with single inlined values as well.
class InlineListHandler(Handler):
    def can_recurse(self) -> bool:
        return False

    # Returns (T, List[T])
    def _deconstruct_two(self, typez:List[type]) -> Tuple[type, type]:
        if is_clazz_list(typez[0]):
            return (typez[1], typez[0])
        else:
            return (typez[0], typez[1])

    # Returns (T, List[T])
    def _deconstruct_three(self, typez:List[type]) -> Tuple[type, type]:
        cop = list(typez)
        cop.remove(type(None))
        return self._deconstruct_two(cop)

    def condition(self, clazz: type) -> bool:
        if typing_inspect.is_union_type(clazz):
            subtypes = typing_inspect.get_args(clazz, evaluate=True)
            # Union[T, List[T]]
            if len(subtypes) == 2:
                typ, typ_lst = self._deconstruct_two(subtypes)
                if is_clazz_list(typ_lst) and typ_lst.__args__[0] == typ:
                    return True

            # Union[T, List[T], None]
            # if len(subtypes) == 3 and type(None) in subtypes:
            #     typ, typ_lst = self._deconstruct_three(subtypes)
            #     if is_clazz_list(typ_lst) and typ_lst.__args__[0] == typ:
            #         return True

        if is_clazz_list(clazz):
            subtype = clazz.__args__[0]
            if is_enum(subtype) or subtype in [ str, float, int, bool ]:
                return True
        return False

    def _any_of_inline(self, ctx: BuilderContext, clazz:type) -> dict:
        return {
            "anyOf" : [
                ctx.handle_type(clazz),
                ctx.array(clazz)
            ]
        }

    def handle(self, ctx: BuilderContext, clazz: type) -> Dict:
        if typing_inspect.is_union_type(clazz):
            subtypes = typing_inspect.get_args(clazz, evaluate=True)
            if len(subtypes) == 2:
                typ, _ = self._deconstruct_two(subtypes)
                return self._any_of_inline(ctx, typ)

            # if len(subtypes) == 3:
            #     typ, _ = self._deconstruct_three(subtypes)
            #     return self._any_of_inline(ctx, typ)

        if is_clazz_list(clazz):
            return self._any_of_inline(ctx, clazz.__args__[0])

        raise ValueError(f"Unexpected type '{clazz.__name__}' in InlineListHandler!")


# Order of handlers matters! Handlers are evaluated in order, first satisfied condition wins
def build_json_schema(clazz:type, *, ext_types:list=[], ext_handlers:List[Handler]=[]):
    handler_registry = [
        NoNullHandler(),
        InlineListHandler(),
        UnionHandler(),
        ListHandler(),
        EnumHandler(),
        AnyHandler(),
    ]

    ctx = BuilderContext()
    ctx.handlers = ext_handlers + handler_registry
    ctx.ext_types = ext_types
    main_schema = ctx.handle_type(clazz)

    # Fill references
    defs = {}
    for c, schema in ctx.dataclazzes.items():
        defs[c.__name__] = schema
    main_schema['$defs'] = defs

    # Default schema fields
    main_schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    main_schema["title"] = clazz.__name__

    return main_schema
