"""
BigWorld network packet decoding.

The decompressed replay data is a stream of packets, each with:
- 4 bytes: packet size (uint32le)
- 4 bytes: packet type (uint32le)
- 4 bytes: entity ID (int32le) — which entity this packet belongs to
- 4 bytes: timestamp (float32le) — game clock
- N bytes: payload (type-specific)

Packet types (from Monstrofil/replays_unpack + lkolbly/wows-replays):
- 0x00: Entity enter
- 0x01: Entity leave
- 0x05: Entity method call (ClientMethods from .def)
- 0x07: Entity property update (Properties from .def)
- 0x08: Position update (entity moved)
- 0x0A: Nested property update
- 0x16: Version packet
- 0x22: Camera position
- 0x27: Player orientation

NOTE: Exact packet type values need verification against
landaire/wows-toolkit source. The BigWorld protocol is not
publicly documented and varies between engine versions.
"""

from wows_replay_parser.packets.decoder import PacketDecoder
from wows_replay_parser.packets.types import Packet, PacketType

__all__ = ["PacketDecoder", "Packet", "PacketType"]
