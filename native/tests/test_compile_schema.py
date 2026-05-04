import pytest


def test_compile_schema_int32(native):
    handle = native.compile_schema({"kind": "int32"})
    assert handle is not None
    assert repr(handle).startswith("<wows_native.Schema")


def test_compile_schema_unknown_kind_raises(native):
    with pytest.raises(ValueError, match="unknown kind"):
        native.compile_schema({"kind": "bogus"})


def test_compile_schema_missing_kind_raises(native):
    with pytest.raises(ValueError, match="missing kind"):
        native.compile_schema({})


@pytest.mark.parametrize("kind", [
    "int8", "int16", "int32", "int64",
    "uint8", "uint16", "uint32", "uint64",
    "float32", "float64",
    "bool", "mailbox",
    "vector2", "vector3",
])
def test_compile_schema_fixed_primitives(native, kind):
    handle = native.compile_schema({"kind": kind})
    assert handle is not None
    assert repr(handle).startswith("<wows_native.Schema")


def test_compile_schema_float_legacy_alias(native):
    """`float` is a legacy alias for `float32` (BigWorld FLOAT)."""
    handle = native.compile_schema({"kind": "float"})
    assert handle is not None


@pytest.mark.parametrize("kind", ["blob", "python", "string", "unicode_string"])
@pytest.mark.parametrize("mode", ["method", "u32"])
def test_compile_schema_variable_primitive(native, kind, mode):
    handle = native.compile_schema({"kind": kind, "mode": mode})
    assert handle is not None


@pytest.mark.parametrize("kind", ["blob", "python", "string", "unicode_string"])
def test_compile_schema_variable_missing_mode_raises(native, kind):
    with pytest.raises(ValueError, match="missing mode"):
        native.compile_schema({"kind": kind})


def test_compile_schema_variable_unknown_mode_raises(native):
    with pytest.raises(ValueError, match="unknown mode"):
        native.compile_schema({"kind": "blob", "mode": "weird"})
