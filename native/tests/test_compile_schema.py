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
