"""
Reads .wowsreplay files: JSON header blocks + encrypted/compressed packet stream.

Decryption:
- Blowfish ECB with known key
- Non-standard CBC: each decrypted block XORed with the previous
  *decrypted output* (not ciphertext). IV is 8 zero bytes.
- Then zlib decompress
"""

from __future__ import annotations

import json
import struct
import zlib
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any

# Verified magic number from real replay files
REPLAY_MAGIC = 0x11_34_32_12

# Blowfish decryption key (known WoWs client constant)
BLOWFISH_KEY = bytes([
    0x29, 0xB7, 0xC9, 0x09, 0x38, 0x3F, 0x84, 0x88,
    0xFA, 0x98, 0xEC, 0x4E, 0x13, 0x19, 0x79, 0xFB,
])


@dataclass
class ReplayFile:
    """Parsed .wowsreplay file."""

    # JSON blocks (typically 1-2)
    meta: dict[str, Any] = field(default_factory=dict)  # Block 0: match info
    result: dict[str, Any] | None = None  # Block 1: battle result (if complete)
    extra_blocks: list[dict[str, Any]] = field(default_factory=list)

    # Raw compressed data (before decompression)
    compressed_data: bytes = b""

    # Decompressed packet stream
    packet_data: bytes = b""

    @property
    def is_complete(self) -> bool:
        """A replay is complete if it has 2+ JSON blocks."""
        return self.result is not None

    @property
    def game_version(self) -> str:
        return str(self.meta.get("clientVersionFromExe", "unknown"))

    @property
    def map_name(self) -> str:
        return str(self.meta.get("mapName", "unknown"))

    @property
    def player_name(self) -> str:
        return str(self.meta.get("playerName", "unknown"))

    @property
    def players(self) -> list[dict[str, Any]]:
        result: Any = self.meta.get("vehicles", [])
        return result  # type: ignore[no-any-return]


class ReplayReader:
    """
    Reads and decompresses .wowsreplay files.

    Usage:
        reader = ReplayReader()
        replay = reader.read(Path("my_replay.wowsreplay"))
        # replay.meta — match metadata
        # replay.packet_data — decompressed binary packet stream
    """

    def read(self, path: Path) -> ReplayFile:
        """Read a replay file from disk."""
        with open(path, "rb") as f:
            data = f.read()
        return self.parse(data)

    def parse(self, data: bytes) -> ReplayFile:
        """Parse raw replay bytes."""
        stream = BytesIO(data)
        replay = ReplayFile()

        # Read magic
        magic = struct.unpack("<I", stream.read(4))[0]
        if magic != REPLAY_MAGIC:
            raise ValueError(
                f"Invalid replay magic: 0x{magic:08X} (expected 0x{REPLAY_MAGIC:08X})"
            )

        # Read block count
        block_count = struct.unpack("<I", stream.read(4))[0]

        # Read JSON blocks
        blocks: list[dict[str, Any]] = []
        for _ in range(block_count):
            block_size = struct.unpack("<I", stream.read(4))[0]
            block_data = stream.read(block_size)
            try:
                blocks.append(json.loads(block_data))
            except json.JSONDecodeError:
                blocks.append({"_raw": block_data.hex()})

        if blocks:
            replay.meta = blocks[0]
        if len(blocks) > 1:
            replay.result = blocks[1]
        if len(blocks) > 2:
            replay.extra_blocks = blocks[2:]

        # Remaining data: 8-byte size header + encrypted compressed packet stream
        remaining = stream.read()
        if len(remaining) >= 8:
            _uncompressed_size, _compressed_size = struct.unpack("<II", remaining[:8])
            replay.compressed_data = remaining[8:]

            # Decrypt then decompress
            decrypted = self._decrypt(replay.compressed_data)
            replay.packet_data = self._decompress(decrypted)

        return replay

    def _decrypt(self, data: bytes) -> bytes:
        """
        Decrypt the packet stream using Blowfish ECB with XOR chaining.

        Non-standard CBC variant: each decrypted block is XORed with the
        *previous decrypted output* (not the previous ciphertext).
        IV is 8 zero bytes.
        """
        try:
            from Crypto.Cipher import Blowfish
        except ImportError:
            try:
                from Cryptodome.Cipher import Blowfish  # type: ignore[no-redef]
            except ImportError:
                return data

        # Pad to 8-byte boundary
        pad_len = (8 - len(data) % 8) % 8
        if pad_len:
            data = data + b"\x00" * pad_len

        cipher = Blowfish.new(BLOWFISH_KEY, Blowfish.MODE_ECB)

        # Bulk-decrypt the entire payload in one C call, then XOR-chain
        # using struct for speed. ~9x faster than per-block cipher.decrypt.
        all_decrypted = cipher.decrypt(data)
        n = len(all_decrypted) // 8
        unpacked = struct.unpack(f"<{n}Q", all_decrypted)
        result = bytearray(len(all_decrypted))
        prev = 0  # IV as u64
        for i in range(n):
            xored = unpacked[i] ^ prev
            struct.pack_into("<Q", result, i * 8, xored)
            prev = xored

        return bytes(result)

    def _decompress(self, data: bytes) -> bytes:
        """
        Decompress the replay packet stream.

        WoWs replays use zlib deflate after Blowfish decryption.
        """
        try:
            return zlib.decompress(data)
        except zlib.error:
            # Try raw deflate (no header)
            try:
                return zlib.decompress(data, -zlib.MAX_WBITS)
            except zlib.error:
                import logging
                logging.getLogger(__name__).warning(
                    "Failed to decompress packet data (%d bytes) — returning raw",
                    len(data),
                )
                return data
