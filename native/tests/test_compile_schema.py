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


def test_compile_schema_fixed_dict_recursive(native):
    """fixed_dict with primitive fields compiles cleanly."""
    handle = native.compile_schema({
        "kind": "fixed_dict",
        "fields": [
            {"name": "a", "schema": {"kind": "int32"}},
            {"name": "b", "schema": {"kind": "string", "mode": "method"}},
        ],
    })
    assert handle is not None


def test_compile_schema_fixed_dict_missing_fields_raises(native):
    with pytest.raises(ValueError, match="missing fields"):
        native.compile_schema({"kind": "fixed_dict"})


def test_compile_schema_allow_none(native):
    handle = native.compile_schema({"kind": "allow_none", "inner": {"kind": "int32"}})
    assert handle is not None


def test_compile_schema_allow_none_missing_inner_raises(native):
    with pytest.raises(ValueError, match="missing inner"):
        native.compile_schema({"kind": "allow_none"})


def test_compile_schema_array(native):
    handle = native.compile_schema({
        "kind": "array",
        "count_prefix": "uint8",
        "element": {"kind": "int32"},
    })
    assert handle is not None


def test_compile_schema_array_missing_count_prefix_raises(native):
    with pytest.raises(ValueError, match="count_prefix"):
        native.compile_schema({
            "kind": "array",
            "element": {"kind": "int32"},
        })


def test_compile_schema_array_unsupported_count_prefix_raises(native):
    with pytest.raises(ValueError, match="uint8"):
        native.compile_schema({
            "kind": "array",
            "count_prefix": "uint16",
            "element": {"kind": "int32"},
        })


def test_compile_schema_array_missing_element_raises(native):
    with pytest.raises(ValueError, match="missing element"):
        native.compile_schema({
            "kind": "array",
            "count_prefix": "uint8",
        })


def test_compile_schema_user_type(native):
    handle = native.compile_schema({"kind": "user_type", "alias": "ZIPPED_BLOB", "blob_mode": "method"})
    assert handle is not None


def test_compile_schema_user_type_missing_alias_raises(native):
    with pytest.raises(ValueError, match="missing alias"):
        native.compile_schema({"kind": "user_type", "blob_mode": "method"})


def test_compile_schema_user_type_missing_blob_mode_raises(native):
    with pytest.raises(ValueError, match="missing blob_mode"):
        native.compile_schema({"kind": "user_type", "alias": "X"})


def test_compile_schema_auto_pickle_blob(native):
    handle = native.compile_schema({"kind": "auto_pickle_blob", "blob_mode": "u32"})
    assert handle is not None


def test_compile_schema_auto_pickle_missing_blob_mode_raises(native):
    with pytest.raises(ValueError, match="missing blob_mode"):
        native.compile_schema({"kind": "auto_pickle_blob"})
