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


def test_decode_blob_method_mode(native):
    h = native.compile_schema({"kind": "blob", "mode": "method"})
    data = b"\x05hello"
    assert native.decode(h, data, 0) == (b"hello", 6)


def test_decode_blob_u32_mode(native):
    h = native.compile_schema({"kind": "blob", "mode": "u32"})
    data = (5).to_bytes(4, "little") + b"hello"
    assert native.decode(h, data, 0) == (b"hello", 9)


def test_decode_blob_method_escalated(native):
    """0xFF sentinel triggers u16 length + 1 padding byte (4-byte total prefix)."""
    h = native.compile_schema({"kind": "blob", "mode": "method"})
    payload = b"x" * 300
    data = b"\xff" + (300).to_bytes(2, "little") + b"\xaa" + payload
    value, off = native.decode(h, data, 0)
    assert value == payload
    assert off == 4 + 300


def test_decode_string_utf8(native):
    h = native.compile_schema({"kind": "string", "mode": "method"})
    payload = "héllo".encode("utf-8")
    data = bytes([len(payload)]) + payload
    assert native.decode(h, data, 0) == ("héllo", 1 + len(payload))


def test_decode_string_latin1_fallback(native):
    """Invalid UTF-8 falls back to latin-1 (1:1 byte→codepoint)."""
    h = native.compile_schema({"kind": "string", "mode": "method"})
    data = b"\x02\xc3\x28"  # invalid UTF-8 sequence
    value, off = native.decode(h, data, 0)
    assert value == "Ã("
    assert off == 3


def test_decode_string_strips_nulls(native):
    h = native.compile_schema({"kind": "string", "mode": "method"})
    payload = b"ab\x00cd"
    data = bytes([len(payload)]) + payload
    value, _ = native.decode(h, data, 0)
    assert value == "abcd"


def test_decode_unicode_string_u32_mode(native):
    h = native.compile_schema({"kind": "unicode_string", "mode": "u32"})
    payload = "test".encode("utf-8")
    data = (len(payload)).to_bytes(4, "little") + payload
    assert native.decode(h, data, 0) == ("test", 8)


def test_decode_python_method_mode(native):
    h = native.compile_schema({"kind": "python", "mode": "method"})
    data = b"\x04\x80\x02ab"
    assert native.decode(h, data, 0) == (b"\x80\x02ab", 5)


def test_decode_fixed_dict_primitives(native):
    descriptor = {
        "kind": "fixed_dict",
        "fields": [
            {"name": "x",  "schema": {"kind": "float32"}},
            {"name": "y",  "schema": {"kind": "float32"}},
            {"name": "id", "schema": {"kind": "uint16"}},
        ],
    }
    handle = native.compile_schema(descriptor)
    data = struct.pack("<ffH", 1.5, -2.5, 42)
    value, off = native.decode(handle, data, 0)
    assert value == {"x": 1.5, "y": -2.5, "id": 42}
    assert off == 10


def test_decode_fixed_dict_empty(native):
    handle = native.compile_schema({"kind": "fixed_dict", "fields": []})
    value, off = native.decode(handle, b"", 0)
    assert value == {}
    assert off == 0


def test_decode_fixed_dict_offset(native):
    """Decoding at a non-zero offset must consume only the right slice."""
    descriptor = {
        "kind": "fixed_dict",
        "fields": [{"name": "v", "schema": {"kind": "uint32"}}],
    }
    handle = native.compile_schema(descriptor)
    prefix = b"\xaa\xbb\xcc"
    data = prefix + (42).to_bytes(4, "little") + b"\xff"
    value, off = native.decode(handle, data, 3)
    assert value == {"v": 42}
    assert off == 7


def test_decode_allow_none_present(native):
    h = native.compile_schema({
        "kind": "allow_none",
        "inner": {"kind": "uint32"},
    })
    data = b"\x01" + (42).to_bytes(4, "little")
    assert native.decode(h, data, 0) == (42, 5)


def test_decode_allow_none_absent(native):
    h = native.compile_schema({
        "kind": "allow_none",
        "inner": {"kind": "uint32"},
    })
    assert native.decode(h, b"\x00", 0) == (None, 1)


def test_decode_allow_none_wraps_fixed_dict(native):
    h = native.compile_schema({
        "kind": "allow_none",
        "inner": {
            "kind": "fixed_dict",
            "fields": [{"name": "v", "schema": {"kind": "uint32"}}],
        },
    })
    import struct
    data = b"\x01" + struct.pack("<I", 7)
    assert native.decode(h, data, 0) == ({"v": 7}, 5)


def test_decode_array_uint16(native):
    h = native.compile_schema({
        "kind": "array",
        "count_prefix": "uint8",
        "element": {"kind": "uint16"},
    })
    data = bytes([3]) + struct.pack("<HHH", 1, 2, 3)
    assert native.decode(h, data, 0) == ([1, 2, 3], 7)


def test_decode_array_of_fixed_dict(native):
    h = native.compile_schema({
        "kind": "array",
        "count_prefix": "uint8",
        "element": {
            "kind": "fixed_dict",
            "fields": [
                {"name": "x", "schema": {"kind": "float32"}},
                {"name": "id", "schema": {"kind": "uint16"}},
            ],
        },
    })
    rec = lambda x, i: struct.pack("<fH", x, i)
    data = bytes([2]) + rec(1.5, 10) + rec(-2.5, 20)
    value, off = native.decode(h, data, 0)
    assert value == [{"x": 1.5, "id": 10}, {"x": -2.5, "id": 20}]
    assert off == 1 + 2 * 6


def test_decode_array_empty(native):
    h = native.compile_schema({
        "kind": "array",
        "count_prefix": "uint8",
        "element": {"kind": "int32"},
    })
    assert native.decode(h, b"\x00", 0) == ([], 1)


def test_decode_array_of_allow_none(native):
    """Composability: array of AllowNone-wrapped values."""
    h = native.compile_schema({
        "kind": "array",
        "count_prefix": "uint8",
        "element": {
            "kind": "allow_none",
            "inner": {"kind": "uint32"},
        },
    })
    data = bytes([3]) + b"\x01" + (10).to_bytes(4, "little") + b"\x00" + b"\x01" + (30).to_bytes(4, "little")
    value, off = native.decode(h, data, 0)
    assert value == [10, None, 30]
    assert off == len(data)
