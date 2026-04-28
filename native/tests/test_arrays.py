"""TDD tests for bulk ARRAY decoders.

BigWorld ARRAY wire format (verified in CLAUDE.md):
    u8 count  +  count × element

Element type is fixed at decode time. Each ``decode_array_<primitive>``
reads the count byte, then ``count`` little-endian elements of the named
primitive type, and returns ``(list, new_offset)``.

Ground truth: ``struct.unpack`` on the same byte slice.
"""

from __future__ import annotations

import struct

import pytest


# --- Helpers ------------------------------------------------------------


def _pack_array(fmt: str, values: list) -> bytes:
    return bytes([len(values)]) + b"".join(struct.pack(fmt, v) for v in values)


# --- Integer arrays -----------------------------------------------------


@pytest.mark.parametrize(
    "fn_name, fmt, sample",
    [
        ("decode_array_int8", "<b", [0, -1, 127, -128, 5]),
        ("decode_array_uint8", "<B", [0, 255, 1, 128, 42]),
        ("decode_array_int16", "<h", [0, -1, 32767, -32768, 1234]),
        ("decode_array_uint16", "<H", [0, 65535, 256, 0xBEEF]),
        ("decode_array_int32", "<i", [0, -1, 2_147_483_647, -2_147_483_648]),
        ("decode_array_uint32", "<I", [0, 4_294_967_295, 0xCAFEBABE]),
        ("decode_array_int64", "<q", [0, -1, 9_223_372_036_854_775_807]),
        ("decode_array_uint64", "<Q", [0, 18_446_744_073_709_551_615]),
    ],
)
class TestIntArrays:
    def test_empty(self, native, fn_name, fmt, sample):
        fn = getattr(native, fn_name)
        value, new_offset = fn(b"\x00", 0)
        assert value == []
        assert new_offset == 1

    def test_single(self, native, fn_name, fmt, sample):
        fn = getattr(native, fn_name)
        data = _pack_array(fmt, [sample[0]])
        value, new_offset = fn(data, 0)
        assert value == [sample[0]]
        assert new_offset == len(data)

    def test_full(self, native, fn_name, fmt, sample):
        fn = getattr(native, fn_name)
        data = _pack_array(fmt, sample)
        value, new_offset = fn(data, 0)
        assert value == sample
        assert new_offset == len(data)

    def test_offset_into_buffer(self, native, fn_name, fmt, sample):
        fn = getattr(native, fn_name)
        prefix = b"\xaa\xbb\xcc"
        data = prefix + _pack_array(fmt, sample)
        value, new_offset = fn(data, len(prefix))
        assert value == sample
        assert new_offset == len(data)

    def test_underrun_count(self, native, fn_name, fmt, sample):
        # count=10 but only 1 byte payload
        fn = getattr(native, fn_name)
        with pytest.raises(ValueError):
            fn(b"\x0a\x00", 0)


# --- Float arrays -------------------------------------------------------


class TestFloatArrays:
    def test_empty_float32(self, native):
        value, new_offset = native.decode_array_float32(b"\x00", 0)
        assert value == []
        assert new_offset == 1

    def test_basic_float32(self, native):
        data = bytes([3]) + struct.pack("<fff", 1.5, -2.5, 3.14)
        value, new_offset = native.decode_array_float32(data, 0)
        assert value == pytest.approx([1.5, -2.5, 3.14])
        assert new_offset == len(data)

    def test_basic_float64(self, native):
        data = bytes([2]) + struct.pack("<dd", 1.5, -2.5)
        value, new_offset = native.decode_array_float64(data, 0)
        assert value == [1.5, -2.5]
        assert new_offset == len(data)


# --- Bool array ---------------------------------------------------------


class TestBoolArray:
    def test_empty(self, native):
        assert native.decode_array_bool(b"\x00", 0) == ([], 1)

    def test_basic(self, native):
        data = b"\x05\x00\x01\x00\x42\xff"
        value, new_offset = native.decode_array_bool(data, 0)
        assert value == [False, True, False, True, True]
        assert new_offset == 6

    def test_returns_python_bools(self, native):
        value, _ = native.decode_array_bool(b"\x02\x00\x01", 0)
        assert all(isinstance(b, bool) for b in value)


# --- Vector arrays ------------------------------------------------------


class TestVectorArrays:
    def test_vector2(self, native):
        data = bytes([2]) + struct.pack("<ffff", 1.0, 2.0, 3.0, 4.0)
        value, new_offset = native.decode_array_vector2(data, 0)
        assert value == [(1.0, 2.0), (3.0, 4.0)]
        assert new_offset == len(data)

    def test_vector3(self, native):
        data = bytes([1]) + struct.pack("<fff", 1.0, 2.0, 3.0)
        value, new_offset = native.decode_array_vector3(data, 0)
        assert value == [(1.0, 2.0, 3.0)]
        assert new_offset == len(data)

    def test_empty_vector3(self, native):
        assert native.decode_array_vector3(b"\x00", 0) == ([], 1)


# --- Large array (200 elements, plausible BigWorld scale) --------------


class TestLargeArray:
    def test_uint16_200_elements(self, native):
        values = list(range(200))
        data = _pack_array("<H", values)
        out, new_offset = native.decode_array_uint16(data, 0)
        assert out == values
        assert new_offset == len(data)
