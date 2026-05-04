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


# ---------------------------------------------------------------------------
# Task 13 — FIXED_DICT, ARRAY alias, AllowNone, TUPLE
# ---------------------------------------------------------------------------

def test_descriptor_fixed_dict():
    alias = TypeAlias(
        name="POS_PAIR", base_type="FIXED_DICT",
        fields=[("x", "FLOAT32"), ("y", "FLOAT32")],
    )
    aliases = _make_registry(alias)
    b = NativeDescriptorBuilder(aliases, EntityRegistry())
    assert b.descriptor_for_type("POS_PAIR") == {
        "kind": "fixed_dict",
        "fields": [
            {"name": "x", "schema": {"kind": "float32"}},
            {"name": "y", "schema": {"kind": "float32"}},
        ],
    }


def test_descriptor_fixed_dict_allow_none():
    alias = TypeAlias(
        name="NULL_POS", base_type="FIXED_DICT",
        fields=[("x", "FLOAT32")], allow_none=True,
    )
    aliases = _make_registry(alias)
    b = NativeDescriptorBuilder(aliases, EntityRegistry())
    assert b.descriptor_for_type("NULL_POS") == {
        "kind": "allow_none",
        "inner": {
            "kind": "fixed_dict",
            "fields": [{"name": "x", "schema": {"kind": "float32"}}],
        },
    }


def test_descriptor_array_alias():
    alias = TypeAlias(name="POS_LIST", base_type="ARRAY", element_type="UINT32")
    aliases = _make_registry(alias)
    b = NativeDescriptorBuilder(aliases, EntityRegistry())
    assert b.descriptor_for_type("POS_LIST") == {
        "kind": "array",
        "count_prefix": "uint8",
        "element": {"kind": "uint32"},
    }


def test_descriptor_tuple_alias():
    alias = TypeAlias(
        name="ID_NAME_PAIR", base_type="TUPLE",
        tuple_types=["INT32", "STRING"],
    )
    aliases = _make_registry(alias)
    b = NativeDescriptorBuilder(aliases, EntityRegistry())
    assert b.descriptor_for_type("ID_NAME_PAIR", in_method=True) == {
        "kind": "tuple",
        "elements": [
            {"kind": "int32"},
            {"kind": "string", "mode": "method"},
        ],
    }


def test_descriptor_nested_fixed_dict():
    """FIXED_DICT containing another FIXED_DICT — exercises recursion."""
    inner = TypeAlias(
        name="POSITION", base_type="FIXED_DICT",
        fields=[("x", "FLOAT32"), ("y", "FLOAT32")],
    )
    outer = TypeAlias(
        name="ENTITY", base_type="FIXED_DICT",
        fields=[("id", "UINT32"), ("pos", "POSITION")],
    )
    aliases = _make_registry(inner, outer)
    b = NativeDescriptorBuilder(aliases, EntityRegistry())
    desc = b.descriptor_for_type("ENTITY")
    assert desc == {
        "kind": "fixed_dict",
        "fields": [
            {"name": "id", "schema": {"kind": "uint32"}},
            {"name": "pos", "schema": {
                "kind": "fixed_dict",
                "fields": [
                    {"name": "x", "schema": {"kind": "float32"}},
                    {"name": "y", "schema": {"kind": "float32"}},
                ],
            }},
        ],
    }


# ---------------------------------------------------------------------------
# Task 14 — post_process (marker conversion + Container wrap)
# ---------------------------------------------------------------------------

import construct as cs

from wows_replay_parser.gamedata import native_descriptor as nd
from wows_replay_parser.gamedata.native_descriptor import (
    post_process,
    set_alias_registry,
)


def test_post_process_primitives():
    assert post_process(42) == 42
    assert post_process(3.14) == 3.14
    assert post_process(b"x") == b"x"
    assert post_process("hello") == "hello"
    assert post_process(None) is None


def test_post_process_dict_wraps_container():
    out = post_process({"a": 1, "b": 2})
    assert isinstance(out, cs.Container)
    assert out.a == 1
    assert out.b == 2


def test_post_process_recursive():
    out = post_process({"outer": {"inner": 7}, "list": [{"k": 9}]})
    assert isinstance(out, cs.Container)
    assert isinstance(out.outer, cs.Container)
    assert out.outer.inner == 7
    assert isinstance(out.list[0], cs.Container)
    assert out.list[0].k == 9


def test_post_process_user_type_marker(monkeypatch):
    captured = {}
    fake_alias = TypeAlias.__new__(TypeAlias)
    fake_alias.name = "ZIPPED_BLOB"
    fake_alias.base_type = "BLOB"
    fake_alias.implemented_by = "X.converter"

    def fake_decode_blob(alias, raw):
        captured["alias"] = alias.name
        return {"decoded": raw}

    monkeypatch.setattr(nd, "_lookup_alias", lambda name: fake_alias if name == "ZIPPED_BLOB" else None)
    monkeypatch.setattr(nd, "decode_blob", fake_decode_blob)

    raw = {"__alias__": "ZIPPED_BLOB", "__bytes__": b"hello"}
    out = post_process(raw)
    assert captured["alias"] == "ZIPPED_BLOB"
    assert isinstance(out, cs.Container)
    assert out.decoded == b"hello"


def test_post_process_unknown_alias_returns_raw_bytes(monkeypatch):
    monkeypatch.setattr(nd, "_lookup_alias", lambda name: None)
    raw = {"__alias__": "UNKNOWN", "__bytes__": b"raw"}
    assert post_process(raw) == b"raw"


def test_post_process_auto_pickle_marker_pickle_byte(monkeypatch):
    captured = {}
    def fake_decode_pickle(b):
        captured["pickled"] = b
        return {"unpickled": True}
    monkeypatch.setattr(nd, "decode_pickle", fake_decode_pickle)

    raw = {"__autopickle__": True, "__bytes__": b"\x80\x02something"}
    out = post_process(raw)
    assert captured["pickled"] == b"\x80\x02something"
    assert isinstance(out, cs.Container)
    assert out.unpickled is True


def test_post_process_auto_pickle_marker_zlib_byte(monkeypatch):
    captured = {}
    def fake_decode_zipped(b):
        captured["zipped"] = b
        return {"unzipped": True}
    monkeypatch.setattr(nd, "decode_zipped", fake_decode_zipped)

    raw = {"__autopickle__": True, "__bytes__": b"\x78\x9csomething"}
    out = post_process(raw)
    assert captured["zipped"] == b"\x78\x9csomething"


def test_post_process_auto_pickle_marker_unknown_byte():
    raw = {"__autopickle__": True, "__bytes__": b"\x99plain"}
    out = post_process(raw)
    assert out == b"\x99plain"


def test_set_alias_registry_lookup():
    """The registry installed via set_alias_registry is used by _lookup_alias."""
    fake_alias = TypeAlias.__new__(TypeAlias)
    fake_alias.name = "X"

    class FakeReg:
        def resolve(self, name):
            return fake_alias if name == "X" else None

    set_alias_registry(FakeReg())
    try:
        assert nd._lookup_alias("X") is fake_alias
        assert nd._lookup_alias("Y") is None
    finally:
        set_alias_registry(None)
