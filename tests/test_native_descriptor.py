"""Tests for NativeDescriptorBuilder — converts BigWorld type aliases into
the dict-descriptor format consumed by wows_native.compile_schema."""

from __future__ import annotations

import pytest

from wows_replay_parser.gamedata.alias_registry import AliasRegistry
from wows_replay_parser.gamedata.entity_registry import EntityRegistry
from wows_replay_parser.gamedata.native_descriptor import NativeDescriptorBuilder


@pytest.fixture
def empty_registry():
    return AliasRegistry(), EntityRegistry()


def test_descriptor_for_int32(empty_registry):
    aliases, registry = empty_registry
    b = NativeDescriptorBuilder(aliases, registry)
    assert b.descriptor_for_type("INT32") == {"kind": "int32"}


@pytest.mark.parametrize("type_name, kind", [
    ("INT8", "int8"), ("INT16", "int16"), ("INT64", "int64"),
    ("UINT8", "uint8"), ("UINT16", "uint16"), ("UINT32", "uint32"), ("UINT64", "uint64"),
    ("FLOAT", "float32"), ("FLOAT32", "float32"), ("FLOAT64", "float64"),
    ("BOOL", "bool"), ("MAILBOX", "mailbox"),
    ("VECTOR2", "vector2"), ("VECTOR3", "vector3"),
])
def test_descriptor_for_fixed_primitive(empty_registry, type_name, kind):
    aliases, registry = empty_registry
    b = NativeDescriptorBuilder(aliases, registry)
    assert b.descriptor_for_type(type_name) == {"kind": kind}


@pytest.mark.parametrize("type_name, kind", [
    ("STRING", "string"), ("UNICODE_STRING", "unicode_string"),
    ("BLOB", "blob"), ("PYTHON", "python"),
])
@pytest.mark.parametrize("in_method, mode", [(True, "method"), (False, "u32")])
def test_descriptor_for_variable_primitive(empty_registry, type_name, kind, in_method, mode):
    aliases, registry = empty_registry
    b = NativeDescriptorBuilder(aliases, registry)
    assert b.descriptor_for_type(type_name, in_method=in_method) == {"kind": kind, "mode": mode}
