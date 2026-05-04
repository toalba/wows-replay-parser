"""Tests for NativeDescriptorBuilder — converts BigWorld type aliases into
the dict-descriptor format consumed by wows_native.compile_schema."""

from __future__ import annotations

import pytest

from wows_replay_parser.gamedata.alias_registry import AliasRegistry, TypeAlias
from wows_replay_parser.gamedata.entity_registry import EntityRegistry
from wows_replay_parser.gamedata.native_descriptor import NativeDescriptorBuilder


def _make_registry(*aliases: TypeAlias) -> AliasRegistry:
    """Construct an AliasRegistry pre-loaded with the given TypeAlias objects."""
    reg = AliasRegistry()
    for alias in aliases:
        reg._aliases[alias.name] = alias
    return reg


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


# ---------------------------------------------------------------------------
# Task 12 — Inline ARRAY + simple aliases + USER_TYPE
# ---------------------------------------------------------------------------

def test_descriptor_inline_array_uint16(empty_registry):
    aliases, registry = empty_registry
    b = NativeDescriptorBuilder(aliases, registry)
    desc = b.descriptor_for_type("ARRAY<of>UINT16</of>", in_method=True)
    assert desc == {
        "kind": "array",
        "count_prefix": "uint8",
        "element": {"kind": "uint16"},
    }


def test_descriptor_alias_to_primitive():
    """Single-level alias resolution: ENTITY_ID → INT32."""
    alias = TypeAlias(name="ENTITY_ID", base_type="INT32")
    aliases = _make_registry(alias)
    b = NativeDescriptorBuilder(aliases, EntityRegistry())
    assert b.descriptor_for_type("ENTITY_ID") == {"kind": "int32"}


def test_descriptor_alias_implementedby_blob():
    """USER_TYPE with implementedBy → marker."""
    alias = TypeAlias(
        name="ZIPPED_BLOB",
        base_type="BLOB",
        has_implemented_by=True,
        implemented_by="ZippedBlobConverter.converter",
    )
    aliases = _make_registry(alias)
    b = NativeDescriptorBuilder(aliases, EntityRegistry())
    assert b.descriptor_for_type("ZIPPED_BLOB", in_method=True) == {
        "kind": "user_type", "alias": "ZIPPED_BLOB", "blob_mode": "method",
    }
    assert b.descriptor_for_type("ZIPPED_BLOB", in_method=False) == {
        "kind": "user_type", "alias": "ZIPPED_BLOB", "blob_mode": "u32",
    }
