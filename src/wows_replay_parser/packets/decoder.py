"""
Decodes the binary packet stream from a decompressed replay.

Packet header format (verified against landaire/wows-toolkit):
- uint32 LE: payload_size (bytes after header)
- uint32 LE: packet_type
- float32 LE: clock (game time in seconds)
Total header: 12 bytes, then payload_size bytes of payload.

Entity type resolution:
- BASE_PLAYER_CREATE / ENTITY_CREATE packets register entity_id → type
- Method and property packets carry entity_id + uint32 method/property index
  plus uint32 payload_length before the serialized data.
"""

from __future__ import annotations

import logging
import struct
from io import BytesIO
from typing import TYPE_CHECKING

from wows_replay_parser.gamedata.entity_registry import EntityRegistry
from wows_replay_parser.gamedata.schema_builder import SchemaBuilder
from wows_replay_parser.packets.types import Packet, PacketType

if TYPE_CHECKING:
    from wows_replay_parser.state.tracker import GameStateTracker

log = logging.getLogger(__name__)


class PacketDecoder:
    """
    Decodes the binary packet stream from a replay.

    Usage:
        decoder = PacketDecoder(schema_builder, entity_registry)
        packets = list(decoder.decode_stream(replay.packet_data))
    """

    _HANDLERS: dict[PacketType, str] = {
        PacketType.BASE_PLAYER_CREATE: "_handle_base_player_create",
        PacketType.BASE_PLAYER_CREATE_STUB: "_handle_base_player_create_stub",
        PacketType.CELL_PLAYER_CREATE: "_handle_cell_player_create",
        PacketType.ENTITY_CREATE: "_handle_entity_create",
        PacketType.ENTITY_ENTER: "_handle_entity_enter",
        PacketType.ENTITY_METHOD: "_handle_method_call",
        PacketType.ENTITY_PROPERTY: "_handle_property_update",
        PacketType.POSITION: "_handle_position",
        PacketType.NON_VOLATILE_POSITION: "_handle_non_volatile_position",
    }

    def __init__(
        self,
        schema: SchemaBuilder,
        entities: EntityRegistry,
        tracker: GameStateTracker | None = None,
    ) -> None:
        self._schema = schema
        self._entities = entities
        self._tracker = tracker
        # Runtime entity_id → entity_type_name mapping
        self._entity_types: dict[int, str] = {}

    def decode_stream(self, data: bytes) -> list[Packet]:
        """Decode all packets from the binary stream."""
        stream = BytesIO(data)
        packets: list[Packet] = []

        while stream.tell() < len(data):
            try:
                packet = self._read_packet(stream)
                if packet is not None:
                    packets.append(packet)
            except (struct.error, ValueError):
                break

        return packets

    def _read_packet(self, stream: BytesIO) -> Packet | None:
        """
        Read a single packet from the stream.

        Header layout (12 bytes):
        - uint32 LE: payload_size
        - uint32 LE: packet_type
        - float32 LE: clock
        """
        header_data = stream.read(12)
        if len(header_data) < 12:
            return None

        packet_size, packet_type, clock = struct.unpack("<IIf", header_data)

        payload = stream.read(packet_size)
        if len(payload) < packet_size:
            return None

        try:
            ptype = PacketType(packet_type)
        except ValueError:
            ptype = PacketType.UNKNOWN

        packet = Packet(
            type=ptype,
            timestamp=clock,
            raw_payload=payload,
            size=packet_size,
        )

        self._dispatch(packet)
        if self._tracker is not None:
            self._tracker.process_packet(packet)
        return packet

    def _dispatch(self, packet: Packet) -> None:
        """Dispatch packet to type-specific handler."""
        method_name = self._HANDLERS.get(packet.type)
        if method_name is not None:
            try:
                getattr(self, method_name)(packet)
            except Exception:
                log.debug("Failed to decode packet type=%s", packet.type, exc_info=True)

    # ── Entity creation / tracking ──────────────────────────────────

    def _register_entity(self, entity_id: int, entity_type_idx: int) -> str | None:
        """Map a 1-based entity type index to a name and register it."""
        entity = self._entities.get_by_type_id(entity_type_idx)
        if entity is None:
            return None
        self._entity_types[entity_id] = entity.name
        return entity.name

    def _handle_base_player_create(self, packet: Packet) -> None:
        """
        BasePlayerCreate (0x00).

        Payload: entity_id(u32) + entity_type(u16) + base properties...
        """
        if len(packet.raw_payload) < 6:
            return
        entity_id, entity_type_idx = struct.unpack("<IH", packet.raw_payload[:6])
        packet.entity_id = entity_id
        entity_name = self._register_entity(entity_id, entity_type_idx)
        if entity_name:
            packet.entity_type = entity_name

    def _handle_base_player_create_stub(self, packet: Packet) -> None:
        """
        BasePlayerCreateStub (0x26) — same header, no inline properties.
        """
        if len(packet.raw_payload) < 6:
            return
        entity_id, entity_type_idx = struct.unpack("<IH", packet.raw_payload[:6])
        packet.entity_id = entity_id
        entity_name = self._register_entity(entity_id, entity_type_idx)
        if entity_name:
            packet.entity_type = entity_name

    def _handle_cell_player_create(self, packet: Packet) -> None:
        """
        CellPlayerCreate (0x01).

        Payload: entity_id(u32) + space_id(u32) + vehicle_id(u32) +
                 position(3xf32) + rotation(3xf32) + props_length(u32) + props...
        Entity must already exist from a prior BasePlayerCreate.
        """
        if len(packet.raw_payload) < 4:
            return
        entity_id = struct.unpack("<I", packet.raw_payload[:4])[0]
        packet.entity_id = entity_id
        entity_type = self._entity_types.get(entity_id)
        if entity_type:
            packet.entity_type = entity_type

    def _handle_entity_create(self, packet: Packet) -> None:
        """
        EntityCreate (0x05).

        Payload: entity_id(u32) + entity_type(u16) + vehicle_id(u32) +
                 space_id(u32) + position(3xf32) + rotation(3xf32) +
                 state_length(u32) + state_data...
        """
        if len(packet.raw_payload) < 6:
            return
        entity_id, entity_type_idx = struct.unpack("<IH", packet.raw_payload[:6])
        packet.entity_id = entity_id
        entity_name = self._register_entity(entity_id, entity_type_idx)
        if entity_name:
            packet.entity_type = entity_name

        # Extract position if enough data (offset 14 = 4+2+4+4)
        if len(packet.raw_payload) >= 26:
            x, y, z = struct.unpack("<fff", packet.raw_payload[14:26])
            packet.position = (x, y, z)

    def _handle_entity_enter(self, packet: Packet) -> None:
        """
        EntityEnter (0x03) — 12-byte payload: entity_id(u32) + space_id(u32) + vehicle_id(u32).
        The entity type should already be known from a create packet.
        """
        if len(packet.raw_payload) < 4:
            return
        entity_id = struct.unpack("<I", packet.raw_payload[:4])[0]
        packet.entity_id = entity_id
        entity_type = self._entity_types.get(entity_id)
        if entity_type:
            packet.entity_type = entity_type

    # ── Method / property decoding ──────────────────────────────────

    def _handle_method_call(self, packet: Packet) -> None:
        """
        EntityMethod (0x08).

        Payload: entity_id(u32) + method_id(u32) + payload_length(u32) + args...
        """
        if len(packet.raw_payload) < 12:
            return

        entity_id, method_id, payload_length = struct.unpack(
            "<III", packet.raw_payload[:12]
        )
        packet.entity_id = entity_id

        entity_type = self._entity_types.get(entity_id)
        if entity_type is None:
            return
        packet.entity_type = entity_type

        method = self._entities.get_client_method(entity_type, method_id)
        if method is None:
            return
        packet.method_name = method.name

        # Decode args
        schema = self._schema.build_method_schema(entity_type, method_id)
        if schema is not None:
            arg_data = packet.raw_payload[12 : 12 + payload_length]
            try:
                parsed = schema.parse(arg_data)
                packet.method_args = {
                    k: v for k, v in parsed.items() if not k.startswith("_")
                }
            except Exception:
                log.debug(
                    "Failed to parse method args: %s.%s",
                    entity_type,
                    method.name,
                    exc_info=True,
                )

    def _handle_property_update(self, packet: Packet) -> None:
        """
        EntityProperty (0x07).

        Payload: entity_id(u32) + property_id(u32) + payload_length(u32) + value...
        """
        if len(packet.raw_payload) < 12:
            return

        entity_id, prop_id, payload_length = struct.unpack(
            "<III", packet.raw_payload[:12]
        )
        packet.entity_id = entity_id

        entity_type = self._entity_types.get(entity_id)
        if entity_type is None:
            return
        packet.entity_type = entity_type

        prop = self._entities.get_client_property(entity_type, prop_id)
        if prop is None:
            return
        packet.property_name = prop.name

        schema = self._schema.build_property_schema(entity_type, prop_id)
        if schema is not None:
            try:
                packet.property_value = schema.parse(
                    packet.raw_payload[12 : 12 + payload_length]
                )
            except Exception:
                log.debug(
                    "Failed to parse property: %s.%s",
                    entity_type,
                    prop.name,
                    exc_info=True,
                )

    def _handle_non_volatile_position(self, packet: Packet) -> None:
        """
        NonVolatilePosition (0x2A) — smoke screens, weather zones.

        Same layout as Position but WITHOUT direction and is_on_ground:
        entity_id(u32) + space_id(u32) + position(3xf32) + rotation(3xf32)
        """
        if len(packet.raw_payload) < 20:
            return
        entity_id, _space_id = struct.unpack("<II", packet.raw_payload[:8])
        x, y, z = struct.unpack("<fff", packet.raw_payload[8:20])
        packet.entity_id = entity_id
        packet.position = (x, y, z)
        entity_type = self._entity_types.get(entity_id)
        if entity_type:
            packet.entity_type = entity_type
        if len(packet.raw_payload) >= 32:
            rx, ry, rz = struct.unpack_from("<fff", packet.raw_payload, 20)
            packet.rotation = (rx, ry, rz)

    def _handle_position(self, packet: Packet) -> None:
        """
        Position (0x0A) — 45 bytes.

        entity_id(u32) + space_id(u32) + position(3xf32) +
        direction(3xf32) + rotation(3xf32) + is_on_ground(u8)
        """
        if len(packet.raw_payload) >= 20:
            entity_id, _space_id = struct.unpack("<II", packet.raw_payload[:8])
            x, y, z = struct.unpack("<fff", packet.raw_payload[8:20])
            packet.entity_id = entity_id
            packet.position = (x, y, z)
            entity_type = self._entity_types.get(entity_id)
            if entity_type:
                packet.entity_type = entity_type
        if len(packet.raw_payload) >= 32:
            dx, dy, dz = struct.unpack_from("<fff", packet.raw_payload, 20)
            packet.direction = (dx, dy, dz)
        if len(packet.raw_payload) >= 44:
            rx, ry, rz = struct.unpack_from("<fff", packet.raw_payload, 32)
            packet.rotation = (rx, ry, rz)
        if len(packet.raw_payload) >= 45:
            packet.is_on_ground = struct.unpack_from("<B", packet.raw_payload, 44)[0] != 0
