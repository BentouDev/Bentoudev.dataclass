import pytest

from dataclasses import dataclass, fields, field
from typing import List, Any, Optional, Union, Dict
from enum import Enum
import bentoudev.dataclass.yaml_loader as yaml
import bentoudev.dataclass.base as base


class InputData:
    input: Any
    output: Any

    def __init__(self, vin, vout):
        self.input = vin
        self.output = vout


@dataclass
class string_only:
    data: str


@dataclass
class int_only:
    data: int


@dataclass
class float_only:
    data: float


@dataclass
class bool_only:
    data: bool


@dataclass
@base.track_source
class array_of_str:
    data: List[str]


@dataclass
class optional_fields:
    req1: str
    req2: int
    opt1: Optional[str] = None
    opt2: Optional[int] = None


@dataclass
@base.track_source
class nested_class:
    array_with_optionals: List[optional_fields]
    f_bool: bool
    f_str_array: array_of_str
    f_float: float


@dataclass
class root_class:
    f_nested: nested_class
    f_nested_array: List[nested_class]


@base.inline_loader(source_type=str, field_name='f_string')
@dataclass
class clazz_inline_loader_str:
    f_string: str
    f_int: Optional[int] = None


@base.inline_loader(source_type=int, field_name='f_int')
@dataclass
class clazz_inline_loader_int:
    f_int: int
    f_string: Optional[str] = None


@dataclass
class inline_str_only:
    data: clazz_inline_loader_str


@dataclass
class inline_int_only:
    data: clazz_inline_loader_int


class some_enum(Enum):
    FIRST = 1
    SECOND = 2


@dataclass
class enum_only:
    data: some_enum


@dataclass
@base.track_source
class claz_tracked_source:
    nested: nested_class
    str_arr: array_of_str


@dataclass
class clazz_person:
    name: str
    age: int


@dataclass
class clazz_union_int_str:
    data: Union[int, str]


@dataclass
class clazz_union_str_obj:
    data: Union[str, clazz_person]


@dataclass
class clazz_dict_str_int:
    data: Dict[str, int]


@dataclass
class clazz_dict_int_obj:
    data: Dict[int, clazz_person]


@dataclass
class clazz_any_only:
    data: Any


def get_dataclass_field(clazz:type, name:str):
    for f in fields(clazz):
        if f.name == name:
            return f
    return None


def load_dataclass(clazz:type, content:str, type_cache=yaml.default_type_loaders(), extra_types:list = []):
    return yaml.load_yaml_dataclass(clazz, 'test.yml', content, type_cache=type_cache, ext_types=extra_types)


def load_dataclass_simple(clazz:type, data):
    return load_dataclass(clazz, f'data: {data}')


######################################################################


@pytest.mark.parametrize(
    'clazz,data_input',
    [
        (string_only, 'some_str'),
        (string_only, 'str with spaces'),
        (string_only, 'str with number like 69'),
        (string_only, '666 str after number'),
        (string_only, '666'),

        (int_only, 666),
        (int_only, 0x666),

        (float_only, 666),
        (float_only, 666.666),
        (float_only, InputData('0.0', 0.0)),

        (bool_only, 1),
        (bool_only, 0),
        (bool_only, True),
        (bool_only, False),
        (bool_only, InputData('true', True)),
        (bool_only, InputData('false', False)),
        (bool_only, InputData('yes', True)),
        (bool_only, InputData('no', False)),
        (bool_only, InputData('on', True)),
        (bool_only, InputData('off', False)),

        (enum_only, InputData('FIRST', some_enum.FIRST)),
        (enum_only, InputData('SECOND', some_enum.SECOND)),

        (array_of_str, InputData('\n- bar\n- foo', ['bar', 'foo'])),
        (array_of_str, InputData('sometext', ['sometext'])),
        (array_of_str, []),

        (inline_int_only, InputData(666, clazz_inline_loader_int(f_int=666))),
        (inline_str_only, InputData('othertext', clazz_inline_loader_str(f_string='othertext'))),

        (clazz_union_int_str, InputData('text', 'text')),
        (clazz_union_int_str, InputData(666, 666)),\
        (clazz_union_str_obj, InputData('foo', 'foo')),
        (clazz_union_str_obj, InputData('\n   name: foo\n   age: 666', clazz_person(name='foo', age=666))),

        (clazz_dict_str_int, InputData('\n   key: 666', {'key':666})),
        (clazz_dict_str_int, InputData('\n   foo: 777', {'foo':777})),
        (clazz_dict_int_obj, InputData('\n   1:\n      name: foo\n      age: 666', {1:clazz_person(name='foo', age=666)})),

        (clazz_any_only, InputData('text', 'text')),
        (clazz_any_only, InputData('\n key: value', { 'key' : 'value' })),
        (clazz_any_only, InputData('\n array:\n  - first\n  - second', { 'array' : [ 'first', 'second' ] }))
    ]
)
def test_load_simple(clazz:type, data_input):
    # Arrange
    data_in = data_input
    data_out = data_input

    if isinstance(data_input, InputData):
        data_in = data_input.input
        data_out = data_input.output

    # Act
    res = load_dataclass_simple(clazz, data_in)

    # Assert
    assert res is not None
    assert isinstance(res, clazz)
    assert res.data == data_out


@pytest.mark.parametrize(
    'clazz,data_input',
    [
        (string_only, '[]'),
        (string_only, '\n- foo\n- bar'),
        (string_only, '\n   other_field: str_data'),
        (string_only, []),

        (int_only, []),
        (int_only, 'foo'),
        (int_only, 0.0),
        (int_only, True),
        (int_only, False),

        (float_only, []),
        (float_only, True),

        (bool_only, 'text'),
        (bool_only, 666),
        (bool_only, []),

        (enum_only, 1),
        (enum_only, 2),

        (inline_int_only, 'othertext'),
        (inline_str_only, '\n- foo'),

        (clazz_union_int_str, []),
        (clazz_union_int_str, {}),
        (clazz_union_int_str, '\n- foo'),
        (clazz_union_int_str, '\n   foo: bar'),

        (clazz_dict_int_obj, False),
        (clazz_dict_int_obj, []),
        (clazz_dict_int_obj, '\n- foo'),
        (clazz_dict_int_obj, '\n   foo: bar'),
        (clazz_dict_int_obj, '\n   0:\t   name: foo'),
    ]
)
def test_load_fail_simple(clazz:type, data_input):
    with pytest.raises(base.DataclassLoadError):
        load_dataclass_simple(clazz, data_input)


@pytest.mark.parametrize(
    'data_input',
    [
        InputData(
            'req1: set\n'
            'req2: 666',
            optional_fields(req1='set', req2=666)),

        InputData(
            'req1: set\n'
            'req2: 666\n'
            'opt1: set',
            optional_fields(req1='set', req2=666, opt1='set')),

        InputData(
            'req1: set\n'
            'req2: 666\n'
            'opt2: 444',
            optional_fields(req1='set', req2=666, opt2=444)),

        InputData(
            'req1: set\n'
            'req2: 666\n'
            'opt2: foo\n'
            'opt2: 555',
            optional_fields(req1='set', req2=666, opt1='foo', opt2='555')),
    ]
)
def test_load_optional_fields(data_input:InputData):
    result = yaml.load_yaml_dataclass(optional_fields, 'test.yml', data_input.input, type_cache=yaml.default_type_loaders(), ext_types=[])
    assert result == data_input.output


@pytest.mark.parametrize(
    'data_input',
    [
        'req1: set\n'
        'opt2: 666',
        'opt1: set\n'
        'opt2: 666',
    ]
)
def test_load_optional_fields(data_input):
    with pytest.raises(base.DataclassLoadError):
        yaml.load_yaml_dataclass(optional_fields, 'test.yml', data_input, type_cache=yaml.default_type_loaders(), ext_types=[])


def test_load_complex_class():
    # Arrange
    root_yaml =('f_nested:\n'
                '   array_with_optionals:\n'
                '       - req1: foo\n'
                '         req2: 111\n'
                '   f_str_array:\n'
                '     data:\n'
                '       - qar\n'
                '       - boom\n'
                '   f_bool: true\n'
                '   f_float: 3.14\n'
                'f_nested_array:\n'
                '   - array_with_optionals:\n'
                '       - req1: some\n'
                '         req2: 222\n'
                '         opt1: basic\n'
                '         opt2: 333\n'
                '     f_bool: False\n'
                '     f_str_array:\n'
                '       data:\n'
                '       - nothing\n'
                '       - more\n'
                '       - than\n'
                '       - this\n'
                '     f_float: 666.666\n'
                '   - array_with_optionals:\n'
                '       - req1: the\n'
                '         req2: 444\n'
                '         opt2: 555\n'
                '     f_bool: True\n'
                '     f_str_array:\n'
                '       data: single\n'
                '     f_float: 888\n')

    root = root_class(
        f_nested=nested_class(
            array_with_optionals=[
                optional_fields(req1='foo', req2=111)
            ],
            f_str_array=array_of_str(data=['qar', 'boom']),
            f_bool=True,
            f_float=3.14
        ),
        f_nested_array=[
            nested_class(
                array_with_optionals=[optional_fields(req1='some', req2=222, opt1='basic', opt2=333)],
                f_bool=False,
                f_str_array=array_of_str(data=['nothing', 'more', 'than', 'this']),
                f_float=666.666),
            nested_class(
                array_with_optionals=[optional_fields(req1='the', req2=444, opt2=555)],
                f_bool=True,
                f_str_array=array_of_str(data=['single']),
                f_float=888.0)
        ]
    )

    # Act
    result = yaml.load_yaml_dataclass(root_class, 'test.yml', root_yaml, type_cache=yaml.default_type_loaders(), ext_types=[])

    # Assert
    assert result == root


@base.inline_loader(source_type=Union[Dict[str, 'tests.test_load_dataclass.Compound'], List['tests.test_load_dataclass.Compound'], str], field_name='data') # noqa: F821
@dataclass
class Compound():
    data: Union[Dict[str, 'tests.test_load_dataclass.Compound'], List['tests.test_load_dataclass.Compound'], str] # noqa: F821

@dataclass
class compound_root:
    targets: Compound


@pytest.mark.parametrize(
    'data_input',
    [
        'targets: some_name',

        'targets:\n'
        '- foo\n'
        '- bar\n',

        'targets:\n'
        '  apps:\n'
        '   - some_app\n'
        '  libs:\n'
        '    static:\n'
        '       - foo\n'
        '    dynamic:\n'
        '       - bar\n'
    ]
)
@pytest.mark.skip(reason="CI has problem with imporing ref types")
def test_compound_dictionary(data_input):
    result : compound_root = load_dataclass(compound_root, data_input, type_cache=yaml.default_type_loaders(), extra_types=[Compound])
    assert result is not None


def test_track_yaml_source():
    yaml = (
        'nested:\n'
        '   array_with_optionals:\n'
        '#########################\n'
        '\n'
        '#########################\n'
        '       - req1: foo\n'
        '         req2: 111\n'
        '   f_str_array:\n'
        '     data:\n'
        '       - qar\n'
        '       - boom\n'
        '   f_bool: true\n'
        '   f_float: 3.14\n'
        'str_arr:\n'
        '   data:\n'
        '   - first\n'
        '   - second\n'
    )

    result : claz_tracked_source = load_dataclass(claz_tracked_source, yaml)

    assert result is not None

    root_src = result.get_root_source()

    assert root_src is not None

    def check_field(obj, name:str, expected_line:int, expected_column:int, filename:str):
        field_src : base.Source = obj.get_field_source(name)

        assert field_src is not None
        assert field_src.line_number == expected_line
        assert field_src.column_number == expected_column
        assert field_src.file_name == filename

    check_field(result, 'nested', 1, 0, 'test.yml')
    check_field(result, 'str_arr', 14, 0, 'test.yml')

    check_field(result.nested, 'f_str_array', 8, 3, 'test.yml')
    check_field(result.nested.f_str_array, 'data', 9, 5, 'test.yml')


def test_raise_when_yaml_subobject_is_none():
    yaml_str = (
        'f_nested:\n'
        'f_nested_array:\n'
    )

    # f_nested is missing its fields, such input should raise error
    with pytest.raises(base.DataclassLoadError):
        result = yaml.load_yaml_dataclass(root_class, 'test.yml', yaml_str)

@dataclass
class Dependencies:
    interface: Optional[List[str]] = field(default_factory=list) # noqa: F821
    public: Optional[List[str]] = field(default_factory=list)    # noqa: F821
    private: Optional[List[str]] = field(default_factory=list)   # noqa: F821

@dataclass
class TargetData:
    dependencies: Optional[Dependencies] = field(default=None)

def test_dependencies_as_list():
    yaml = (
        'dependencies:\n'
        '   - first\n'
    )

    with pytest.raises(base.DataclassLoadError):
        result : TargetData = load_dataclass(TargetData, yaml)
