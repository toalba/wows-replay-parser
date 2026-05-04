def test_compile_schema_int32(native):
    handle = native.compile_schema({"kind": "int32"})
    assert handle is not None
    assert repr(handle).startswith("<wows_native.Schema")
