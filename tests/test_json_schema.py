import pytest
import json
from typing import List, Union
from enum import Enum
from dataclasses import dataclass
from bentoudev.dataclass.json_schema import (
    BuilderContext, Handler, InlineListHandler, UnionHandler, ListHandler, NoNullHandler, EnumHandler,
    build_json_schema
)

def _process_handlers(typez:type, handlers:List[Handler], ext_types:List[type]=[]):
    ctx = BuilderContext()
    ctx.handlers = handlers
    ctx.ext_types = ext_types
    return ctx.handle_type(typez)

def test_handle_inline_str():
    typez = Union[str, List[str], None]
    result = _process_handlers(typez, [
        NoNullHandler(),
        InlineListHandler(),
        UnionHandler(),
        ListHandler()
    ])

    assert result == {"anyOf": [{"type": "string"}, {"items": {"type": "string"}, "type": "array"}]}

class EMyEnum(Enum):
    NONE = 1
    FIRST = 1
    SECOND = 2

def test_handle_inline_enum():
    typez = Union[EMyEnum, List[EMyEnum], None]
    result = _process_handlers(typez, [
        NoNullHandler(),
        InlineListHandler(),
        UnionHandler(),
        ListHandler(),
        EnumHandler(),
    ])

    assert result == {"anyOf": [{"enum": ["NONE", "FIRST", "SECOND"]}, {"items": {"enum": ["NONE", "FIRST", "SECOND"]}, "type": "array"}]}


@dataclass
class SimpleDataclass:
    number: int
    name: str

def test_handle_simple_dataclass():
    result = _process_handlers(SimpleDataclass, [])
    assert result == {"$ref": "#/$defs/SimpleDataclass"}

@dataclass
class SelfRefDataclass:
    number: int
    collect: List['tests.test_json_schema.SelfRefDataclass'] # noqa: F821

def test_handle_self_ref_dataclass():
    result = build_json_schema(SelfRefDataclass, ext_types=[SelfRefDataclass])
    assert result == {"$ref": "#/$defs/SelfRefDataclass", "$defs": {"SelfRefDataclass": {"type": "object", "properties": {"number": {"type": "integer"}, "collect": {"items": {"$ref": "#/$defs/SelfRefDataclass"}, "type": "array"}}, "additionalProperties": False, "title": "SelfRefDataclass", "required": ["number", "collect"]}}, "$schema": "https://json-schema.org/draft/2020-12/schema", "title": "SelfRefDataclass"}

@dataclass
class EntryClass:
    name: str
    number: int

@dataclass
class ConfigClass:
    entry: EntryClass
    surname: str
    kinds: List[EMyEnum]

@dataclass
class OwnerClass:
    config: ConfigClass
    entries: List[EntryClass]

def test_complex_class():
    result = build_json_schema(OwnerClass)
    assert result == {"$ref": "#/$defs/OwnerClass", "$defs": {"OwnerClass": {"type": "object", "properties": {"config": {"$ref": "#/$defs/ConfigClass"}, "entries": {"items": {"$ref": "#/$defs/EntryClass"}, "type": "array"}}, "additionalProperties": False, "title": "OwnerClass", "required": ["config", "entries"]}, "ConfigClass": {"type": "object", "properties": {"entry": {"$ref": "#/$defs/EntryClass"}, "surname": {"type": "string"}, "kinds": {"anyOf": [{"enum": ["NONE", "FIRST", "SECOND"]}, {"items": {"enum": ["NONE", "FIRST", "SECOND"]}, "type": "array"}]}}, "additionalProperties": False, "title": "ConfigClass", "required": ["entry", "surname", "kinds"]}, "EntryClass": {"type": "object", "properties": {"name": {"type": "string"}, "number": {"type": "integer"}}, "additionalProperties": False, "title": "EntryClass", "required": ["name", "number"]}}, "$schema": "https://json-schema.org/draft/2020-12/schema", "title": "OwnerClass"}
