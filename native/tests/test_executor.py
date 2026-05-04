import struct


def test_decode_int32(native):
    handle = native.compile_schema({"kind": "int32"})
    data = struct.pack("<i", -42)
    value, new_offset = native.decode(handle, data, 0)
    assert value == -42
    assert new_offset == 4
