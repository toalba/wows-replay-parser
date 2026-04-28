"""TDD tests for the 4 variable-length BigWorld primitives.

Length encoding modes (verified in CLAUDE.md and schema_builder.py):

    "method" — used inside method calls (ENTITY_METHOD payloads):
              u8 length. If first byte == 0xFF, next u16 LE is the
              length followed by 1 padding byte (4-byte total prefix).

    "u32"    — used in property updates and inline state:
              u32 LE length (4-byte prefix).

Decoders return ``(value, new_offset)`` where ``new_offset`` points past
the entire encoded record (prefix + padding + payload).

STRING/UNICODE_STRING decode payload bytes via tolerant UTF-8: try strict
UTF-8 first, fall back to latin-1, strip embedded NULs (mirrors
``_decode_string_bytes`` in schema_builder.py).
"""

from __future__ import annotations

import pytest


# --- BLOB: method mode --------------------------------------------------


class TestDecodeBlobMethod:
    def test_short_payload(self, native):
        # 1-byte prefix = 5, then 5 payload bytes
        data = b"\x05hello"
        value, new_offset = native.decode_blob(data, 0, "method")
        assert value == b"hello"
        assert new_offset == 6

    def test_empty_payload(self, native):
        data = b"\x00"
        value, new_offset = native.decode_blob(data, 0, "method")
        assert value == b""
        assert new_offset == 1

    def test_at_threshold_254_bytes(self, native):
        # 0xFE is still inline; 0xFF triggers escalation
        payload = b"x" * 254
        data = b"\xfe" + payload
        value, new_offset = native.decode_blob(data, 0, "method")
        assert value == payload
        assert new_offset == 255

    def test_escalated_3_byte_length(self, native):
        # Sentinel 0xFF + u16 LE length(=300) + 1 padding byte + 300 payload
        payload = b"y" * 300
        data = b"\xff" + (300).to_bytes(2, "little") + b"\xaa" + payload
        value, new_offset = native.decode_blob(data, 0, "method")
        assert value == payload
        assert new_offset == 4 + 300

    def test_escalated_zero_length(self, native):
        # Pathological but legal: escalation header for length 0
        data = b"\xff\x00\x00\xaa"
        value, new_offset = native.decode_blob(data, 0, "method")
        assert value == b""
        assert new_offset == 4

    def test_offset_into_buffer(self, native):
        prefix = b"\xde\xad\xbe\xef"
        record = b"\x03abc"
        buf = prefix + record + b"\xff"
        value, new_offset = native.decode_blob(buf, 4, "method")
        assert value == b"abc"
        assert new_offset == 8

    def test_underrun_inline(self, native):
        # Says length=10 but only 5 payload bytes available
        with pytest.raises(ValueError):
            native.decode_blob(b"\x0ashort", 0, "method")

    def test_underrun_escalated_length_header(self, native):
        # Sentinel byte but no u16 length follows
        with pytest.raises(ValueError):
            native.decode_blob(b"\xff", 0, "method")


# --- BLOB: u32 mode -----------------------------------------------------


class TestDecodeBlobU32:
    def test_short_payload(self, native):
        data = (5).to_bytes(4, "little") + b"hello"
        value, new_offset = native.decode_blob(data, 0, "u32")
        assert value == b"hello"
        assert new_offset == 9

    def test_empty_payload(self, native):
        data = b"\x00\x00\x00\x00"
        value, new_offset = native.decode_blob(data, 0, "u32")
        assert value == b""
        assert new_offset == 4

    def test_large_payload(self, native):
        payload = b"z" * 100_000
        data = (100_000).to_bytes(4, "little") + payload
        value, new_offset = native.decode_blob(data, 0, "u32")
        assert value == payload
        assert new_offset == 4 + 100_000

    def test_offset_into_buffer(self, native):
        prefix = b"\xde\xad"
        record = (3).to_bytes(4, "little") + b"abc"
        buf = prefix + record
        value, new_offset = native.decode_blob(buf, 2, "u32")
        assert value == b"abc"
        assert new_offset == 9

    def test_underrun_payload(self, native):
        with pytest.raises(ValueError):
            native.decode_blob(b"\x0a\x00\x00\x00ab", 0, "u32")

    def test_underrun_length_header(self, native):
        with pytest.raises(ValueError):
            native.decode_blob(b"\x00\x00\x00", 0, "u32")


# --- PYTHON (raw bytes, identical to BLOB on the wire) ------------------


class TestDecodePython:
    def test_method_mode(self, native):
        data = b"\x04\x80\x02ab"
        value, new_offset = native.decode_python(data, 0, "method")
        assert value == b"\x80\x02ab"
        assert new_offset == 5

    def test_u32_mode(self, native):
        data = (4).to_bytes(4, "little") + b"\x80\x02ab"
        value, new_offset = native.decode_python(data, 0, "u32")
        assert value == b"\x80\x02ab"
        assert new_offset == 8

    def test_returns_bytes_not_str(self, native):
        value, _ = native.decode_python(b"\x03abc", 0, "method")
        assert isinstance(value, bytes)


# --- STRING (tolerant UTF-8 + NUL strip) --------------------------------


class TestDecodeString:
    def test_ascii(self, native):
        data = b"\x05hello"
        value, new_offset = native.decode_string(data, 0, "method")
        assert value == "hello"
        assert isinstance(value, str)
        assert new_offset == 6

    def test_empty(self, native):
        value, new_offset = native.decode_string(b"\x00", 0, "method")
        assert value == ""
        assert new_offset == 1

    def test_utf8_multibyte(self, native):
        # "héllo" = 6 UTF-8 bytes
        encoded = "héllo".encode("utf-8")
        data = bytes([len(encoded)]) + encoded
        value, _ = native.decode_string(data, 0, "method")
        assert value == "héllo"

    def test_strips_embedded_nulls(self, native):
        # "ab\x00cd" → "abcd"
        payload = b"ab\x00cd"
        data = bytes([len(payload)]) + payload
        value, _ = native.decode_string(data, 0, "method")
        assert value == "abcd"

    def test_latin1_fallback_for_invalid_utf8(self, native):
        # 0xC3 0x28 is invalid UTF-8 (continuation byte missing)
        # latin-1 maps it 1:1 to "Ã("
        payload = b"\xc3\x28"
        data = bytes([len(payload)]) + payload
        value, _ = native.decode_string(data, 0, "method")
        assert value == "Ã("

    def test_u32_mode(self, native):
        encoded = "world".encode("utf-8")
        data = (len(encoded)).to_bytes(4, "little") + encoded
        value, new_offset = native.decode_string(data, 0, "u32")
        assert value == "world"
        assert new_offset == 9

    def test_offset(self, native):
        prefix = b"\xaa\xbb"
        record = b"\x03foo"
        value, new_offset = native.decode_string(prefix + record, 2, "method")
        assert value == "foo"
        assert new_offset == 6

    def test_escalated_method_mode(self, native):
        payload = b"a" * 500
        data = b"\xff" + (500).to_bytes(2, "little") + b"\xaa" + payload
        value, new_offset = native.decode_string(data, 0, "method")
        assert value == "a" * 500
        assert new_offset == 4 + 500


# --- UNICODE_STRING (same wire format as STRING in BigWorld) -----------


class TestDecodeUnicodeString:
    def test_ascii(self, native):
        value, new_offset = native.decode_unicode_string(b"\x05hello", 0, "method")
        assert value == "hello"
        assert new_offset == 6

    def test_utf8(self, native):
        encoded = "ünïcödé".encode("utf-8")
        data = bytes([len(encoded)]) + encoded
        value, _ = native.decode_unicode_string(data, 0, "method")
        assert value == "ünïcödé"

    def test_u32_mode(self, native):
        encoded = "test".encode("utf-8")
        data = (len(encoded)).to_bytes(4, "little") + encoded
        value, new_offset = native.decode_unicode_string(data, 0, "u32")
        assert value == "test"
        assert new_offset == 8


# --- Mode validation ----------------------------------------------------


class TestModeValidation:
    def test_invalid_mode_raises(self, native):
        with pytest.raises(ValueError):
            native.decode_blob(b"\x00", 0, "bogus")
