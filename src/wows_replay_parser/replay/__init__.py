"""
Replay file framing — reads the .wowsreplay container format.

Format (from evido/wotreplay-parser + Monstrofil/replays_unpack):
  - 4 bytes: magic number (must be verified)
  - 4 bytes: block count (uint32le) — number of JSON blocks
  - For each block:
    - 4 bytes: block size (uint32le)
    - N bytes: JSON data
  - Remaining bytes: compressed replay data (zlib deflate, no header)

Block 0: Match metadata (map, players, game mode, etc.)
Block 1: (if present) Battle result summary
The compressed data contains the binary network packet stream.
"""

from wows_replay_parser.replay.reader import ReplayReader

__all__ = ["ReplayReader"]
