"""TDD tests for the 14 BigWorld fixed-width primitives.

Ground truth: `struct.unpack` from the standard library.

API shape (one function per primitive):
    decode_<NAME>(data: bytes, offset: int) -> tuple[value, new_offset]

Returning the new offset (offset + size) keeps callers cursor-style and
mirrors how the higher-level packet readers will consume it.
"""

from __future__ import annotations

import math
import struct

import pytest


# --- INT8 ---------------------------------------------------------------


class TestDecodeInt8:
    def test_zero(self, native):
        assert native.decode_int8(b"\x00", 0) == (0, 1)

    def test_positive_max(self, native):
        assert native.decode_int8(b"\x7f", 0) == (127, 1)

    def test_negative_min(self, native):
        assert native.decode_int8(b"\x80", 0) == (-128, 1)

    def test_negative_one(self, native):
        assert native.decode_int8(b"\xff", 0) == (-1, 1)

    def test_offset_into_buffer(self, native):
        buf = b"\xaa\xbb\x05\xcc"
        assert native.decode_int8(buf, 2) == (5, 3)

    @pytest.mark.parametrize("byte", range(256))
    def test_matches_struct_unpack(self, native, byte):
        data = bytes([byte])
        (expected,) = struct.unpack("<b", data)
        value, new_offset = native.decode_int8(data, 0)
        assert value == expected
        assert new_offset == 1


# --- UINT8 --------------------------------------------------------------


class TestDecodeUint8:
    def test_zero(self, native):
        assert native.decode_uint8(b"\x00", 0) == (0, 1)

    def test_max(self, native):
        assert native.decode_uint8(b"\xff", 0) == (255, 1)

    def test_offset_into_buffer(self, native):
        assert native.decode_uint8(b"\x00\x2a", 1) == (42, 2)

    @pytest.mark.parametrize("byte", range(256))
    def test_matches_struct_unpack(self, native, byte):
        data = bytes([byte])
        (expected,) = struct.unpack("<B", data)
        value, new_offset = native.decode_uint8(data, 0)
        assert value == expected
        assert new_offset == 1


# --- INT16 / UINT16 -----------------------------------------------------


class TestDecodeInt16:
    def test_zero(self, native):
        assert native.decode_int16(b"\x00\x00", 0) == (0, 2)

    def test_positive_max(self, native):
        assert native.decode_int16(b"\xff\x7f", 0) == (32767, 2)

    def test_negative_min(self, native):
        assert native.decode_int16(b"\x00\x80", 0) == (-32768, 2)

    def test_negative_one(self, native):
        assert native.decode_int16(b"\xff\xff", 0) == (-1, 2)

    def test_little_endian(self, native):
        # 0x0102 LE = 0x02 0x01
        assert native.decode_int16(b"\x02\x01", 0) == (0x0102, 2)

    def test_offset(self, native):
        assert native.decode_int16(b"\xaa\xbb\x05\x00", 2) == (5, 4)

    @pytest.mark.parametrize(
        "data",
        [b"\x00\x00", b"\x01\x00", b"\xff\xff", b"\x00\x80", b"\xff\x7f", b"\x34\x12"],
    )
    def test_matches_struct_unpack(self, native, data):
        (expected,) = struct.unpack("<h", data)
        assert native.decode_int16(data, 0) == (expected, 2)


class TestDecodeUint16:
    def test_zero(self, native):
        assert native.decode_uint16(b"\x00\x00", 0) == (0, 2)

    def test_max(self, native):
        assert native.decode_uint16(b"\xff\xff", 0) == (65535, 2)

    def test_little_endian(self, native):
        assert native.decode_uint16(b"\x02\x01", 0) == (0x0102, 2)

    def test_offset(self, native):
        assert native.decode_uint16(b"\xaa\xbb\x05\x00", 2) == (5, 4)

    @pytest.mark.parametrize(
        "data",
        [b"\x00\x00", b"\x01\x00", b"\xff\xff", b"\x00\x80", b"\xff\x7f", b"\x34\x12"],
    )
    def test_matches_struct_unpack(self, native, data):
        (expected,) = struct.unpack("<H", data)
        assert native.decode_uint16(data, 0) == (expected, 2)


# --- INT32 / UINT32 -----------------------------------------------------


class TestDecodeInt32:
    def test_zero(self, native):
        assert native.decode_int32(b"\x00\x00\x00\x00", 0) == (0, 4)

    def test_positive_max(self, native):
        assert native.decode_int32(b"\xff\xff\xff\x7f", 0) == (2_147_483_647, 4)

    def test_negative_min(self, native):
        assert native.decode_int32(b"\x00\x00\x00\x80", 0) == (-2_147_483_648, 4)

    def test_negative_one(self, native):
        assert native.decode_int32(b"\xff\xff\xff\xff", 0) == (-1, 4)

    def test_little_endian(self, native):
        assert native.decode_int32(b"\x04\x03\x02\x01", 0) == (0x01020304, 4)

    def test_offset(self, native):
        buf = b"\xaa\xbb" + b"\x2a\x00\x00\x00"
        assert native.decode_int32(buf, 2) == (42, 6)

    @pytest.mark.parametrize(
        "data",
        [
            b"\x00\x00\x00\x00",
            b"\xff\xff\xff\xff",
            b"\x00\x00\x00\x80",
            b"\xff\xff\xff\x7f",
            b"\x78\x56\x34\x12",
        ],
    )
    def test_matches_struct_unpack(self, native, data):
        (expected,) = struct.unpack("<i", data)
        assert native.decode_int32(data, 0) == (expected, 4)


class TestDecodeUint32:
    def test_zero(self, native):
        assert native.decode_uint32(b"\x00\x00\x00\x00", 0) == (0, 4)

    def test_max(self, native):
        assert native.decode_uint32(b"\xff\xff\xff\xff", 0) == (4_294_967_295, 4)

    def test_little_endian(self, native):
        assert native.decode_uint32(b"\x04\x03\x02\x01", 0) == (0x01020304, 4)

    @pytest.mark.parametrize(
        "data",
        [
            b"\x00\x00\x00\x00",
            b"\xff\xff\xff\xff",
            b"\x00\x00\x00\x80",
            b"\xff\xff\xff\x7f",
            b"\x78\x56\x34\x12",
        ],
    )
    def test_matches_struct_unpack(self, native, data):
        (expected,) = struct.unpack("<I", data)
        assert native.decode_uint32(data, 0) == (expected, 4)


# --- INT64 / UINT64 -----------------------------------------------------


class TestDecodeInt64:
    def test_zero(self, native):
        assert native.decode_int64(b"\x00" * 8, 0) == (0, 8)

    def test_positive_max(self, native):
        assert native.decode_int64(b"\xff\xff\xff\xff\xff\xff\xff\x7f", 0) == (
            9_223_372_036_854_775_807,
            8,
        )

    def test_negative_min(self, native):
        assert native.decode_int64(b"\x00\x00\x00\x00\x00\x00\x00\x80", 0) == (
            -9_223_372_036_854_775_808,
            8,
        )

    def test_negative_one(self, native):
        assert native.decode_int64(b"\xff" * 8, 0) == (-1, 8)

    def test_little_endian(self, native):
        assert native.decode_int64(b"\x08\x07\x06\x05\x04\x03\x02\x01", 0) == (
            0x0102030405060708,
            8,
        )

    @pytest.mark.parametrize(
        "data",
        [
            b"\x00" * 8,
            b"\xff" * 8,
            b"\x00\x00\x00\x00\x00\x00\x00\x80",
            b"\xff\xff\xff\xff\xff\xff\xff\x7f",
            b"\xef\xcd\xab\x90\x78\x56\x34\x12",
        ],
    )
    def test_matches_struct_unpack(self, native, data):
        (expected,) = struct.unpack("<q", data)
        assert native.decode_int64(data, 0) == (expected, 8)


class TestDecodeUint64:
    def test_zero(self, native):
        assert native.decode_uint64(b"\x00" * 8, 0) == (0, 8)

    def test_max(self, native):
        assert native.decode_uint64(b"\xff" * 8, 0) == (18_446_744_073_709_551_615, 8)

    def test_little_endian(self, native):
        assert native.decode_uint64(b"\x08\x07\x06\x05\x04\x03\x02\x01", 0) == (
            0x0102030405060708,
            8,
        )

    @pytest.mark.parametrize(
        "data",
        [
            b"\x00" * 8,
            b"\xff" * 8,
            b"\x00\x00\x00\x00\x00\x00\x00\x80",
            b"\xff\xff\xff\xff\xff\xff\xff\x7f",
            b"\xef\xcd\xab\x90\x78\x56\x34\x12",
        ],
    )
    def test_matches_struct_unpack(self, native, data):
        (expected,) = struct.unpack("<Q", data)
        assert native.decode_uint64(data, 0) == (expected, 8)


# --- FLOAT32 / FLOAT64 --------------------------------------------------


class TestDecodeFloat32:
    def test_zero(self, native):
        value, new_offset = native.decode_float32(b"\x00\x00\x00\x00", 0)
        assert value == 0.0
        assert new_offset == 4

    def test_one(self, native):
        # 1.0f32 = 0x3f800000 LE
        value, _ = native.decode_float32(b"\x00\x00\x80\x3f", 0)
        assert value == 1.0

    def test_negative(self, native):
        # -2.5f32 = 0xc0200000 LE
        value, _ = native.decode_float32(b"\x00\x00\x20\xc0", 0)
        assert value == -2.5

    def test_nan(self, native):
        value, _ = native.decode_float32(b"\x00\x00\xc0\x7f", 0)
        assert math.isnan(value)

    def test_offset(self, native):
        buf = b"\xaa\xbb" + struct.pack("<f", 3.14)
        value, new_offset = native.decode_float32(buf, 2)
        assert value == pytest.approx(3.14, rel=1e-6)
        assert new_offset == 6

    @pytest.mark.parametrize(
        "value",
        [0.0, 1.0, -1.0, 3.14, -2.71828, 1e30, 1e-30, float("inf"), float("-inf")],
    )
    def test_matches_struct_unpack(self, native, value):
        data = struct.pack("<f", value)
        (expected,) = struct.unpack("<f", data)
        decoded, new_offset = native.decode_float32(data, 0)
        assert decoded == expected
        assert new_offset == 4


class TestDecodeFloat64:
    def test_zero(self, native):
        value, new_offset = native.decode_float64(b"\x00" * 8, 0)
        assert value == 0.0
        assert new_offset == 8

    def test_one(self, native):
        value, _ = native.decode_float64(struct.pack("<d", 1.0), 0)
        assert value == 1.0

    def test_negative(self, native):
        value, _ = native.decode_float64(struct.pack("<d", -2.5), 0)
        assert value == -2.5

    def test_nan(self, native):
        value, _ = native.decode_float64(struct.pack("<d", float("nan")), 0)
        assert math.isnan(value)

    @pytest.mark.parametrize(
        "value",
        [0.0, 1.0, -1.0, 3.141592653589793, -2.718281828459045, 1e300, 1e-300, float("inf"), float("-inf")],
    )
    def test_matches_struct_unpack(self, native, value):
        data = struct.pack("<d", value)
        (expected,) = struct.unpack("<d", data)
        decoded, new_offset = native.decode_float64(data, 0)
        assert decoded == expected
        assert new_offset == 8


# --- BOOL ---------------------------------------------------------------


class TestDecodeBool:
    def test_zero_is_false(self, native):
        assert native.decode_bool(b"\x00", 0) == (False, 1)

    def test_one_is_true(self, native):
        assert native.decode_bool(b"\x01", 0) == (True, 1)

    def test_returns_python_bool_type(self, native):
        value, _ = native.decode_bool(b"\x01", 0)
        assert isinstance(value, bool)
        assert value is True

    def test_returns_python_bool_type_false(self, native):
        value, _ = native.decode_bool(b"\x00", 0)
        assert isinstance(value, bool)
        assert value is False

    @pytest.mark.parametrize("byte", range(256))
    def test_any_nonzero_is_true(self, native, byte):
        value, new_offset = native.decode_bool(bytes([byte]), 0)
        assert value is (byte != 0)
        assert new_offset == 1

    def test_offset(self, native):
        assert native.decode_bool(b"\xaa\x00\x05", 2) == (True, 3)


# --- MAILBOX ------------------------------------------------------------


class TestDecodeMailbox:
    def test_zero_blob(self, native):
        data = b"\x00" * 16
        value, new_offset = native.decode_mailbox(data, 0)
        assert value == data
        assert new_offset == 16
        assert isinstance(value, bytes)

    def test_arbitrary_blob(self, native):
        data = bytes(range(16))
        value, new_offset = native.decode_mailbox(data, 0)
        assert value == data
        assert new_offset == 16

    def test_offset(self, native):
        prefix = b"\xaa\xbb"
        blob = bytes(range(100, 116))
        buf = prefix + blob + b"\xcc"
        value, new_offset = native.decode_mailbox(buf, 2)
        assert value == blob
        assert new_offset == 18

    def test_underrun_raises(self, native):
        with pytest.raises(ValueError):
            native.decode_mailbox(b"\x00" * 15, 0)


# --- VECTOR2 / VECTOR3 --------------------------------------------------


class TestDecodeVector2:
    def test_zeros(self, native):
        data = struct.pack("<ff", 0.0, 0.0)
        value, new_offset = native.decode_vector2(data, 0)
        assert value == (0.0, 0.0)
        assert new_offset == 8

    def test_basic(self, native):
        data = struct.pack("<ff", 1.5, -2.5)
        value, _ = native.decode_vector2(data, 0)
        assert value == (1.5, -2.5)

    def test_returns_tuple(self, native):
        data = struct.pack("<ff", 1.0, 2.0)
        value, _ = native.decode_vector2(data, 0)
        assert isinstance(value, tuple)
        assert len(value) == 2

    def test_offset(self, native):
        buf = b"\xaa\xbb" + struct.pack("<ff", 3.14, 2.71)
        value, new_offset = native.decode_vector2(buf, 2)
        assert value[0] == pytest.approx(3.14, rel=1e-6)
        assert value[1] == pytest.approx(2.71, rel=1e-6)
        assert new_offset == 10

    @pytest.mark.parametrize(
        "x, y",
        [(0.0, 0.0), (1.0, -1.0), (3.14, 2.71), (1e30, -1e-30), (float("inf"), float("-inf"))],
    )
    def test_matches_struct_unpack(self, native, x, y):
        data = struct.pack("<ff", x, y)
        expected = struct.unpack("<ff", data)
        value, new_offset = native.decode_vector2(data, 0)
        assert value == expected
        assert new_offset == 8


class TestDecodeVector3:
    def test_zeros(self, native):
        data = struct.pack("<fff", 0.0, 0.0, 0.0)
        value, new_offset = native.decode_vector3(data, 0)
        assert value == (0.0, 0.0, 0.0)
        assert new_offset == 12

    def test_basic(self, native):
        data = struct.pack("<fff", 1.5, -2.5, 3.5)
        value, _ = native.decode_vector3(data, 0)
        assert value == (1.5, -2.5, 3.5)

    def test_returns_tuple(self, native):
        data = struct.pack("<fff", 1.0, 2.0, 3.0)
        value, _ = native.decode_vector3(data, 0)
        assert isinstance(value, tuple)
        assert len(value) == 3

    def test_offset(self, native):
        buf = b"\xaa\xbb" + struct.pack("<fff", 1.0, 2.0, 3.0)
        value, new_offset = native.decode_vector3(buf, 2)
        assert value == (1.0, 2.0, 3.0)
        assert new_offset == 14

    @pytest.mark.parametrize(
        "x, y, z",
        [
            (0.0, 0.0, 0.0),
            (1.0, -1.0, 0.5),
            (3.14, 2.71, 1.41),
            (1e30, -1e-30, 0.0),
            (float("inf"), float("-inf"), float("nan")),
        ],
    )
    def test_matches_struct_unpack(self, native, x, y, z):
        data = struct.pack("<fff", x, y, z)
        expected = struct.unpack("<fff", data)
        value, new_offset = native.decode_vector3(data, 0)
        # Element-wise compare so NaN is handled
        for got, want in zip(value, expected, strict=True):
            if math.isnan(want):
                assert math.isnan(got)
            else:
                assert got == want
        assert new_offset == 12
