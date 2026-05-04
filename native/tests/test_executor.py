import struct

import pytest


def test_decode_int32(native):
    handle = native.compile_schema({"kind": "int32"})
    data = struct.pack("<i", -42)
    value, new_offset = native.decode(handle, data, 0)
    assert value == -42
    assert new_offset == 4


@pytest.mark.parametrize("kind, fmt, sample", [
    ("int8",    "<b", -128),
    ("int16",   "<h", -32768),
    ("int32",   "<i", -2147483648),
    ("int64",   "<q", -9223372036854775808),
    ("uint8",   "<B", 255),
    ("uint16",  "<H", 65535),
    ("uint32",  "<I", 4294967295),
    ("uint64",  "<Q", 18446744073709551615),
    ("float32", "<f", 3.14),
    ("float64", "<d", 3.141592653589793),
])
def test_decode_fixed_primitive(native, kind, fmt, sample):
    handle = native.compile_schema({"kind": kind})
    data = struct.pack(fmt, sample)
    value, off = native.decode(handle, data, 0)
    if isinstance(sample, float):
        assert value == pytest.approx(sample)
    else:
        assert value == sample
    assert off == struct.calcsize(fmt)


def test_decode_bool(native):
    h = native.compile_schema({"kind": "bool"})
    assert native.decode(h, b"\x00", 0) == (False, 1)
    assert native.decode(h, b"\x42", 0) == (True, 1)


def test_decode_mailbox(native):
    h = native.compile_schema({"kind": "mailbox"})
    blob = bytes(range(16))
    value, off = native.decode(h, blob, 0)
    assert value == blob
    assert off == 16


def test_decode_vector2(native):
    h = native.compile_schema({"kind": "vector2"})
    data = struct.pack("<ff", 1.5, -2.5)
    assert native.decode(h, data, 0) == ((1.5, -2.5), 8)


def test_decode_vector3(native):
    h = native.compile_schema({"kind": "vector3"})
    data = struct.pack("<fff", 1.0, 2.0, 3.0)
    assert native.decode(h, data, 0) == ((1.0, 2.0, 3.0), 12)


def test_decode_buffer_underrun_raises(native):
    handle = native.compile_schema({"kind": "int32"})
    with pytest.raises(ValueError, match="buffer underrun"):
        native.decode(handle, b"\x00\x00", 0)
