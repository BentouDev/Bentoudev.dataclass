# Bentoudev.dataclass

[![CI (on push)](https://github.com/BentouDev/Bentoudev.dataclass/actions/workflows/python-ci.yml/badge.svg)](https://github.com/BentouDev/Bentoudev.dataclass/actions/workflows/python-ci.yml) [![PyPI version](https://badge.fury.io/py/bentoudev.dataclass.svg)](https://badge.fury.io/py/bentoudev.dataclass)

Yaml to dataclass loader. Validates objects based on type information.

Supports folowing types:
- classes marked as dataclass (from ``dataclasses``)
- int, str, float, list
- Enum (from ``enum``)
- Optional, List, Dict, Union (from ``typing``)
- forward references to not yet known types (see example), including self-referencing

## Install
```sh
pip install bentoudev.dataclass
```

## Documentation
Work in progress, for now, check out examples below or browse the source code.

## Example

```python
@dataclass
class Person:
    name: str
    age: int
    money: float

yaml_content = (
    'name: John\n'
    'age: 30\n'
    'money: 400.50'
)

obj = load_yaml_dataclass(Person, 'Person', yaml_content)

assert obj.name == 'John'
```

### Inline loaders
If you need to load complex class from a single value (like string), you can use ``@inline_loader`` attribute

```python
import bentoudev.dataclass.yaml_loader
import bentoudev.dataclass.base

@dataclass
@inline_loader(source_type=str, field_name='name')
class ObjFromStr:
    name: str
    foo: int
    bar: float

@dataclass
class Container:
    value: ObjFromStr

obj = load_yaml_dataclass(Container, 'pretty file name', 'value: ThisIsMyName')

assert obj.value.name == 'ThisIsMyName'
```
### Forward references to external types
Sometimes you might want to load dataclass that forward references foreign types, from other modules, in form of a string. In order to support such types, loader must be supplied with list of them.
```python

@dataclass
class MyDataclass:
    foo: Optional['my_namespace.project.model.my_ext_dataclass']

local_types = base.get_types_from_modules([__name__, 'my_namespace.project.model.my_ext_dataclass'])

my_obj: MyDataclass = yaml_loader.load_yaml_dataclass(MyDataclass, 'pretty file name', yaml_content, ext_types=local_types)
```

### Self referencing types
Additionaly to external types, self referencing is also supported

```python
from dataclasses import dataclass
import bentoudev.dataclass.yaml_loader as yaml_loader

@dataclass
class MyDataclass:
    my_string: str
    self_nested: Optional['MyDataclass']
    list_of_sth: List[str]
    user_data: Dict[str, str]

yaml_content = (
    'my_string: foo\n'
    'self_nested:\n'
    '  my_string: bar\n'
    '  list_of_sth: inline_value\n'
    'list_of_sth:\n'
    '- first\n'
    '- second\n'
    'user_data:\n'
    '  anything: goes'
)

my_obj: MyDataclass = yaml_loader.load_yaml_dataclass(MyDataclass, 'pretty file name', yaml_content)
```
### Remember lines
Additional information about source from which obj/field was loaded can be enabled by using ``@track_source`` attribute, or setting ``always_track_source`` parameter to True (disabled by default, but recomended). Such information is then used to print prettier errors in ``DataclassLoadError``.

```python
class EKind(Enum):
    FIRST = 1
    SECOND = 2

@dataclass
class SomeClass:
    kind: EKind

try:
    obj =  yaml_loader.load_yaml_dataclass(SomeClass, '[SomeClass] my_file.yml', 'kind: THIRD', always_track_source=True)
except DataclassLoadError as err:
    print(err)
```
Outputs:
```
error: Got 'THIRD' when expecting enum 'EKind' with one of values: FIRST, SECOND
in "[SomeClass] my_file.yml", line 1, column 1:
kind: THIRD
^ (line: 1)
```

If you desire to retrieve this information and print error yourself, access it's ``source`` field in error, or use injected methods ``get_root_source`` or ``get_field_source``.
```python
try:
    obj =  yaml_loader.load_yaml_dataclass(SomeClass, 'broken_file.yml', broken_yaml_content, always_track_source=True)
    field_src = obj.get_field_source('my_field_name')
    print(f"Value location line '{field_src.line_number}', column '{field_src.column_number}'")
except DataclassLoadError as err:
    print(f"Error location line '{err.source.line_number}', column '{err.source.column_number}'")
```

Additionaly, you can control how many lines are loaded for code snippet and in which format line numbers are presented via ``error_code_snippet_lines`` and ``error_format`` (Pretty or MSVC compatible).
