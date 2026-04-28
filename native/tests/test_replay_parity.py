"""Differential parity test: Rust primitives vs struct.unpack on real replay bytes.

Walks a real .wowsreplay file as raw bytes (no parsing — we only need a real-
world byte distribution including NaNs, dense floats, weird sign patterns).
For every primitive we sample many offsets across the file and assert that
``wows_native.decode_<prim>`` produces the exact same value as ``struct.unpack``.

This is the strongest non-integrated parity check we can run without wiring
the Rust module into the live parser.
"""

from __future__ import annotations

import math
import struct
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Replay discovery
# ---------------------------------------------------------------------------

_THIS = Path(__file__).resolve()
_PROJECT = _THIS.parent.parent.parent  # wows-replay-parser/
_PARSER_FIXTURES = _PROJECT / "tests" / "fixtures" / "replays"
_RENDERER_DIR = _PROJECT.parent / "wows-renderer"


def _find_replay() -> Path | None:
    for parent in (_PARSER_FIXTURES, _RENDERER_DIR):
        if parent.is_dir():
            hits = sorted(parent.glob("*.wowsreplay"))
            if hits:
                return hits[0]
    return None


@pytest.fixture(scope="module")
def replay_bytes() -> bytes:
    path = _find_replay()
    if path is None:
        pytest.skip(
            "No .wowsreplay available. Drop one into "
            "tests/fixtures/replays/ or ../wows-renderer/ "
            "to run replay-parity checks.",
        )
    data = path.read_bytes()
    if len(data) < 4096:
        pytest.skip(f"Replay {path.name} is too small ({len(data)} bytes)")
    return data


# ---------------------------------------------------------------------------
# Sampling helpers
# ---------------------------------------------------------------------------


def _offsets(buf_len: int, size: int, step: int = 17) -> range:
    """Walk the buffer at a stride that's coprime with all primitive sizes
    (17 is prime; primitives are 1/2/4/8/12/16). Guarantees we hit every
    alignment class without being O(N) on a 50 MB file.
    """
    return range(0, buf_len - size + 1, step)


# ---------------------------------------------------------------------------
# Per-primitive parity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fn_name, struct_fmt, size",
    [
        ("decode_int8", "<b", 1),
        ("decode_uint8", "<B", 1),
        ("decode_int16", "<h", 2),
        ("decode_uint16", "<H", 2),
        ("decode_int32", "<i", 4),
        ("decode_uint32", "<I", 4),
        ("decode_int64", "<q", 8),
        ("decode_uint64", "<Q", 8),
    ],
)
def test_int_primitives_match_struct_on_real_replay(
    native, replay_bytes, fn_name, struct_fmt, size
):
    fn = getattr(native, fn_name)
    mismatches: list[tuple[int, int, int]] = []
    for off in _offsets(len(replay_bytes), size):
        (expected,) = struct.unpack_from(struct_fmt, replay_bytes, off)
        value, new_offset = fn(replay_bytes, off)
        if value != expected or new_offset != off + size:
            mismatches.append((off, value, expected))
            if len(mismatches) > 5:
                break
    assert not mismatches, f"{fn_name}: {mismatches[:5]}"


@pytest.mark.parametrize(
    "fn_name, struct_fmt, size",
    [
        ("decode_float32", "<f", 4),
        ("decode_float64", "<d", 8),
    ],
)
def test_float_primitives_match_struct_on_real_replay(
    native, replay_bytes, fn_name, struct_fmt, size
):
    fn = getattr(native, fn_name)
    mismatches: list[tuple[int, float, float]] = []
    for off in _offsets(len(replay_bytes), size):
        (expected,) = struct.unpack_from(struct_fmt, replay_bytes, off)
        value, new_offset = fn(replay_bytes, off)
        if new_offset != off + size:
            mismatches.append((off, value, expected))
        elif math.isnan(expected):
            if not math.isnan(value):
                mismatches.append((off, value, expected))
        elif value != expected:
            mismatches.append((off, value, expected))
        if len(mismatches) > 5:
            break
    assert not mismatches, f"{fn_name}: {mismatches[:5]}"


def test_bool_matches_byte_truthiness(native, replay_bytes):
    for off in _offsets(len(replay_bytes), 1):
        expected = replay_bytes[off] != 0
        value, new_offset = native.decode_bool(replay_bytes, off)
        assert value is expected
        assert new_offset == off + 1


def test_mailbox_returns_exact_16_byte_slice(native, replay_bytes):
    for off in _offsets(len(replay_bytes), 16):
        expected = replay_bytes[off : off + 16]
        value, new_offset = native.decode_mailbox(replay_bytes, off)
        assert value == expected
        assert new_offset == off + 16


def test_vector2_matches_two_float32(native, replay_bytes):
    mismatches = []
    for off in _offsets(len(replay_bytes), 8):
        expected = struct.unpack_from("<ff", replay_bytes, off)
        value, new_offset = native.decode_vector2(replay_bytes, off)
        if new_offset != off + 8:
            mismatches.append((off, value, expected))
            continue
        for got, want in zip(value, expected, strict=True):
            if math.isnan(want):
                if not math.isnan(got):
                    mismatches.append((off, value, expected))
            elif got != want:
                mismatches.append((off, value, expected))
        if len(mismatches) > 5:
            break
    assert not mismatches, mismatches[:5]


def test_vector3_matches_three_float32(native, replay_bytes):
    mismatches = []
    for off in _offsets(len(replay_bytes), 12):
        expected = struct.unpack_from("<fff", replay_bytes, off)
        value, new_offset = native.decode_vector3(replay_bytes, off)
        if new_offset != off + 12:
            mismatches.append((off, value, expected))
            continue
        for got, want in zip(value, expected, strict=True):
            if math.isnan(want):
                if not math.isnan(got):
                    mismatches.append((off, value, expected))
            elif got != want:
                mismatches.append((off, value, expected))
        if len(mismatches) > 5:
            break
    assert not mismatches, mismatches[:5]
