"""Unit tests for chat message decoding edge cases.

The STRING decode path used to be strict UTF-8 (`cs.GreedyString("utf-8")`),
which raised UnicodeDecodeError on ~2/37 chat messages in the corpus
(mojibake / non-UTF8 bytes originating from the Python 2 game server).
A fatal parse error there wipes the whole method's args. The fix decodes
tolerantly (UTF-8 → latin-1 fallback) and strips NULs.
"""

from __future__ import annotations

import construct as cs

from wows_replay_parser.events.models import ChatEvent
from wows_replay_parser.events.stream import _chat, _coerce_chat_str
from wows_replay_parser.gamedata.schema_builder import (
    _MethodBlobPrefixed,
    _RobustString,
    _decode_string_bytes,
)
from wows_replay_parser.packets.types import Packet, PacketType


def _pkt(method_args: dict) -> Packet:
    p = Packet(type=PacketType.ENTITY_METHOD)
    p.entity_id = 1
    p.timestamp = 10.0
    p.method_name = "onChatMessage"
    p.method_args = method_args
    return p


class TestDecodeStringBytes:
    def test_plain_ascii(self) -> None:
        assert _decode_string_bytes(b"hello") == "hello"

    def test_utf8_cyrillic(self) -> None:
        text = "Привет"
        assert _decode_string_bytes(text.encode("utf-8")) == text

    def test_utf8_cjk(self) -> None:
        text = "こんにちは"
        assert _decode_string_bytes(text.encode("utf-8")) == text

    def test_utf8_emoji(self) -> None:
        text = "gg 🔥"
        assert _decode_string_bytes(text.encode("utf-8")) == text

    def test_latin1_fallback_for_invalid_utf8(self) -> None:
        # 0xFF is not valid UTF-8 start byte → must fall back to latin-1.
        raw = b"name\xff\xe9"
        out = _decode_string_bytes(raw)
        assert isinstance(out, str)
        assert out.startswith("name")
        # No exception; all bytes map 1:1 under latin-1.
        assert len(out) == 6

    def test_strips_null_bytes(self) -> None:
        assert _decode_string_bytes(b"he\x00llo") == "hello"

    def test_empty_bytes(self) -> None:
        assert _decode_string_bytes(b"") == ""


class TestRobustStringConstruct:
    def test_parses_valid_utf8(self) -> None:
        schema = _RobustString(_MethodBlobPrefixed(cs.GreedyBytes))
        # u8 length=5 + bytes "hello"
        data = bytes([5]) + b"hello"
        assert schema.parse(data) == "hello"

    def test_parses_invalid_utf8_without_raising(self) -> None:
        schema = _RobustString(_MethodBlobPrefixed(cs.GreedyBytes))
        # u8 length=4 + invalid UTF-8 bytes
        data = bytes([4]) + b"\xff\xfe\xfd\xfc"
        out = schema.parse(data)
        assert isinstance(out, str)
        assert len(out) == 4

    def test_parses_empty_string(self) -> None:
        schema = _RobustString(_MethodBlobPrefixed(cs.GreedyBytes))
        data = bytes([0])
        assert schema.parse(data) == ""


class TestChatFactory:
    def test_basic_message(self) -> None:
        evt = _chat(_pkt({
            "arg0": 12345, "arg1": "battle_team", "arg2": "gg",
        }))
        assert isinstance(evt, ChatEvent)
        assert evt.sender_id == 12345
        assert evt.channel == "battle_team"
        assert evt.message == "gg"

    def test_cyrillic_message(self) -> None:
        evt = _chat(_pkt({
            "arg0": 1, "arg1": "battle_common", "arg2": "Привет!",
        }))
        assert evt.message == "Привет!"

    def test_cjk_message(self) -> None:
        evt = _chat(_pkt({
            "arg0": 1, "arg1": "battle_common", "arg2": "よろしく",
        }))
        assert evt.message == "よろしく"

    def test_empty_message(self) -> None:
        evt = _chat(_pkt({
            "arg0": 1, "arg1": "", "arg2": "",
        }))
        assert evt.channel == ""
        assert evt.message == ""

    def test_none_args_coerced(self) -> None:
        # None in any string slot should coerce to "", not crash.
        evt = _chat(_pkt({
            "arg0": None, "arg1": None, "arg2": None,
        }))
        assert evt.sender_id == 0
        assert evt.channel == ""
        assert evt.message == ""

    def test_raw_bytes_fallback(self) -> None:
        # Should not happen post-fix (schema decodes), but belt-and-braces.
        evt = _chat(_pkt({
            "arg0": 1, "arg1": b"battle_common", "arg2": b"\xff\xfe hi",
        }))
        assert evt.channel == "battle_common"
        assert evt.message.endswith(" hi")

    def test_null_bytes_stripped(self) -> None:
        evt = _chat(_pkt({
            "arg0": 1, "arg1": "c", "arg2": "he\x00llo",
        }))
        assert evt.message == "hello"

    def test_missing_args_dont_crash(self) -> None:
        evt = _chat(_pkt({}))
        assert evt.sender_id == 0
        assert evt.channel == ""
        assert evt.message == ""


class TestCoerceChatStr:
    def test_none(self) -> None:
        assert _coerce_chat_str(None) == ""

    def test_utf8_bytes(self) -> None:
        assert _coerce_chat_str("ß".encode("utf-8")) == "ß"

    def test_latin1_fallback_bytes(self) -> None:
        out = _coerce_chat_str(b"\xff\xfe")
        assert isinstance(out, str) and len(out) == 2

    def test_int_coerced(self) -> None:
        assert _coerce_chat_str(42) == "42"
