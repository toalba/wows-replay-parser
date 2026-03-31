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

import functools
import logging
import struct
from io import BytesIO
from typing import TYPE_CHECKING, Any

from wows_replay_parser.gamedata.alias_registry import AliasRegistry
from wows_replay_parser.gamedata.entity_registry import EntityRegistry
from wows_replay_parser.gamedata.schema_builder import SchemaBuilder
from wows_replay_parser.packets.nested_property import (
    BitReader,
    _bits_for_count,
    _resolve_type_structure,
)
from wows_replay_parser.packets.types import Packet, PacketType

if TYPE_CHECKING:
    from wows_replay_parser.state.tracker import GameStateTracker

log = logging.getLogger(__name__)


def _dict_to_list(d: dict) -> list:
    """Convert a dict with numeric string keys to a list."""
    if not d:
        return []
    max_idx = max((int(k) for k in d if k.isdigit()), default=-1)
    result = [None] * (max_idx + 1)
    for k, v in d.items():
        if k.isdigit():
            result[int(k)] = v
    return result


def _replace_child(root: dict, path: list[str], new_value: Any) -> None:
    """Replace the value at path[-1] within root with new_value."""
    target = root
    for key in path[:-1]:
        if isinstance(target, dict):
            target = target.get(key, {})
        elif isinstance(target, list):
            try:
                target = target[int(key)]
            except (ValueError, IndexError):
                return
    last = path[-1] if path else None
    if last is not None:
        if isinstance(target, dict):
            target[last] = new_value
        elif isinstance(target, list):
            try:
                target[int(last)] = new_value
            except (ValueError, IndexError):
                pass


class PacketDecoder:
    """
    Decodes the binary packet stream from a replay.

    Usage:
        decoder = PacketDecoder(schema_builder, entity_registry)
        packets = list(decoder.decode_stream(replay.packet_data))
    """

    _HANDLERS: dict[PacketType, str] = {
        # Entity lifecycle
        PacketType.BASE_PLAYER_CREATE: "_handle_base_player_create",
        PacketType.BASE_PLAYER_CREATE_STUB: "_handle_base_player_create_stub",
        PacketType.CELL_PLAYER_CREATE: "_handle_cell_player_create",
        PacketType.ENTITY_CREATE: "_handle_entity_create",
        PacketType.ENTITY_ENTER: "_handle_entity_enter",
        PacketType.ENTITY_LEAVE: "_handle_entity_leave",
        PacketType.ENTITY_CONTROL: "_handle_entity_control",
        # Data
        PacketType.ENTITY_METHOD: "_handle_method_call",
        PacketType.ENTITY_PROPERTY: "_handle_property_update",
        PacketType.NESTED_PROPERTY: "_handle_nested_property",
        # Position
        PacketType.POSITION: "_handle_position",
        PacketType.NON_VOLATILE_POSITION: "_handle_non_volatile_position",
        PacketType.PLAYER_ORIENTATION: "_handle_player_orientation",
        # Critical metadata
        PacketType.OWN_SHIP: "_handle_own_ship",
        PacketType.VERSION: "_handle_version",
        PacketType.MAP: "_handle_map",
        PacketType.BATTLE_RESULTS: "_handle_battle_results",
        # Useful per-tick data
        PacketType.CAMERA: "_handle_camera",
        PacketType.GUN_MARKER: "_handle_gun_marker",
        PacketType.SERVER_TIMESTAMP: "_handle_server_timestamp",
        PacketType.SERVER_TICK: "_handle_server_tick",
        # Low priority metadata
        PacketType.INIT_FLAG: "_handle_init_flag",
        PacketType.INIT_MARKER: "_handle_init_marker",
        PacketType.PLAYER_NET_STATS: "_handle_player_net_stats",
        PacketType.CAMERA_MODE: "_handle_camera_mode",
        PacketType.CAMERA_FREE_LOOK: "_handle_camera_free_look",
        PacketType.SET_WEAPON_LOCK: "_handle_set_weapon_lock",
        PacketType.CRUISE_STATE: "_handle_cruise_state",
        PacketType.SUB_CONTROLLER: "_handle_sub_controller",
        PacketType.SHOT_TRACKING: "_handle_shot_tracking",
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

    # Entity types commonly sent as base type in ENTITY_CREATE but whose
    # inline state uses the cell type's property schema.
    _CELL_TYPE_CANDIDATES: dict[str, list[str]] = {
        "Account": ["Vehicle"],
        "OfflineEntity": ["Vehicle", "Building"],
    }

    def _register_entity(self, entity_id: int, entity_type_idx: int) -> str | None:
        """Map a 1-based entity type index to a name and register it."""
        entity = self._entities.get_by_type_id(entity_type_idx)
        if entity is None:
            return None
        self._entity_types[entity_id] = entity.name
        return entity.name

    def _remap_entity_type(
        self,
        entity_id: int,
        declared_name: str,
        num_props: int,
        state_data: bytes,
    ) -> str | None:
        """Try to remap an entity to its real cell type.

        BigWorld sends ENTITY_CREATE with the base entity type (e.g.
        Account) but the inline state uses the cell type's property
        schema (e.g. Vehicle with 54 properties). We detect this when
        num_props exceeds the declared type's property count, then try
        candidate cell types to find one that parses successfully.
        """
        candidates = self._CELL_TYPE_CANDIDATES.get(declared_name, [])
        for candidate in candidates:
            candidate_entity = self._entities.get(candidate)
            if candidate_entity is None:
                continue
            if num_props <= len(candidate_entity.client_properties):
                # Try parsing inline state with this candidate
                props = self._try_parse_inline_state(
                    candidate, state_data, num_props,
                )
                if props is not None and len(props) == num_props:
                    self._entity_types[entity_id] = candidate
                    log.debug(
                        "Remapped entity %d: %s → %s (%d inline props)",
                        entity_id, declared_name, candidate, num_props,
                    )
                    return candidate
        return None

    def _handle_base_player_create(self, packet: Packet) -> None:
        """
        BasePlayerCreate (0x00).

        Payload: entity_id(u32) + entity_type(u16) + base properties...

        WoWS-specific: the type_idx in this packet does NOT index into
        entities.xml's ClientServerEntities list. This packet creates
        the player's controller entity, which needs the entity type with
        the largest ClientMethods table (Avatar in current WoWS).
        We resolve the type dynamically rather than trusting type_idx.
        """
        if len(packet.raw_payload) < 6:
            return
        entity_id = struct.unpack("<I", packet.raw_payload[:4])[0]
        packet.entity_id = entity_id

        # Find the entity type with the most client methods — that's
        # the base player type (it receives all player-side method calls).
        base_player_type = self._find_base_player_type()
        if base_player_type:
            self._entity_types[entity_id] = base_player_type
            packet.entity_type = base_player_type
            log.debug(
                "Base player entity %d → %s (%d client methods)",
                entity_id, base_player_type,
                len(self._entities.get(base_player_type).client_methods_by_index),
            )

    def _find_base_player_type(self) -> str | None:
        """Find the entity type with the most ClientMethods.

        In BigWorld, the base player entity is the player controller
        that receives all client-side method calls. It always has
        the largest method table (Avatar in WoWS).
        """
        best_name: str | None = None
        best_count = 0
        for name in self._entities.entity_names:
            entity = self._entities.get(name)
            if entity is None:
                continue
            count = len(entity.client_methods_by_index)
            if count > best_count:
                best_count = count
                best_name = name
        return best_name

    def _handle_base_player_create_stub(self, packet: Packet) -> None:
        """
        BasePlayerCreateStub (0x26) — same as BASE_PLAYER_CREATE but
        without inline properties. Creates the same base player entity.
        """
        if len(packet.raw_payload) < 6:
            return
        entity_id = struct.unpack("<I", packet.raw_payload[:4])[0]
        packet.entity_id = entity_id

        # Same logic as _handle_base_player_create: resolve type by
        # largest method table, not by packet type_idx.
        base_player_type = self._find_base_player_type()
        if base_player_type:
            self._entity_types[entity_id] = base_player_type
            packet.entity_type = base_player_type

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

        The state_data contains initial property values:
            num_props(u8) + [prop_id(u8) + typed_value] × num_props
        """
        if len(packet.raw_payload) < 6:
            return
        entity_id, entity_type_idx = struct.unpack("<IH", packet.raw_payload[:6])
        packet.entity_id = entity_id
        entity_name = self._register_entity(entity_id, entity_type_idx)
        if entity_name:
            packet.entity_type = entity_name

        # BigWorld sends ENTITY_CREATE for other players' ships with the
        # base entity type (Account, idx=2) rather than the cell type
        # (Vehicle, idx=1). Detect this by checking if the inline state
        # has more properties than the declared type supports, and remap.
        if entity_name and len(packet.raw_payload) >= 43:
            state_length = struct.unpack("<I", packet.raw_payload[38:42])[0]
            if state_length >= 1:
                num_props = packet.raw_payload[42]
                declared_entity = self._entities.get(entity_name)
                if declared_entity is not None:
                    max_props = len(declared_entity.client_properties)
                    if num_props > max_props:
                        # Inline state exceeds declared type — try to find
                        # the real cell entity type by testing candidates.
                        remapped = self._remap_entity_type(
                            entity_id, entity_name, num_props,
                            packet.raw_payload[42:42 + state_length],
                        )
                        if remapped:
                            entity_name = remapped
                            packet.entity_type = remapped

        # Extract position (offset 14 = 4+2+4+4)
        if len(packet.raw_payload) >= 26:
            x, y, z = struct.unpack("<fff", packet.raw_payload[14:26])
            packet.position = (x, y, z)

        # Extract rotation (offset 26)
        if len(packet.raw_payload) >= 38:
            rx, ry, rz = struct.unpack("<fff", packet.raw_payload[26:38])
            packet.rotation = (rx, ry, rz)

        # Parse inline state data (offset 38 = state_length, 42 = state_data)
        if entity_name and len(packet.raw_payload) >= 42:
            state_length = struct.unpack("<I", packet.raw_payload[38:42])[0]
            state_data = packet.raw_payload[42:42 + state_length]
            if state_data:
                self._parse_inline_state(packet, entity_name, state_data)

    def _parse_inline_state(
        self, packet: Packet, entity_name: str, state_data: bytes,
    ) -> None:
        """Parse EntityCreate inline state: initial property values."""
        if len(state_data) < 1:
            return

        num_props = state_data[0]
        if num_props == 0:
            return

        # Try parsing with the detected entity type first.
        # If that fails (e.g., InteractiveObject with InteractiveZone data),
        # try alternative entity types with the same or more properties.
        candidates = [entity_name]
        if entity_name == "InteractiveObject":
            candidates.append("InteractiveZone")

        for candidate in candidates:
            props = self._try_parse_inline_state(candidate, state_data, num_props)
            if props is not None and len(props) == num_props:
                if candidate != entity_name:
                    # Remap the entity type to the one that parsed successfully
                    packet.entity_type = candidate
                    self._entity_types[packet.entity_id] = candidate
                    log.debug(
                        "Remapped entity %d: %s → %s (%d inline props)",
                        packet.entity_id, entity_name, candidate, len(props),
                    )
                packet.initial_properties = props
                return

    def _try_parse_inline_state(
        self, entity_name: str, state_data: bytes, expected_count: int = 0,
    ) -> dict[str, Any] | None:
        """Try parsing inline state with a specific entity type's schema."""
        import io

        stream = io.BytesIO(state_data)
        num_props = struct.unpack("B", stream.read(1))[0]

        props: dict[str, Any] = {}
        for _ in range(num_props):
            if stream.tell() >= len(state_data):
                break

            prop_id_byte = stream.read(1)
            if len(prop_id_byte) < 1:
                break
            prop_id = prop_id_byte[0]

            prop_def = self._entities.get_client_property(entity_name, prop_id)
            if prop_def is None:
                return None  # Schema doesn't fit — prop_id out of range

            schema = self._schema.build_inline_property_schema(entity_name, prop_id)
            if schema is None:
                return None

            try:
                value = schema.parse_stream(stream)
                props[prop_def.name] = value
            except Exception:
                return None  # Parse failed — wrong schema

        return props if props else None

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

    def _handle_nested_property(self, packet: Packet) -> None:
        """
        NestedProperty (0x23) — update to a nested field within a property.

        Payload: entity_id(u32) + is_slice(u8) + payload_size(u32) + bit_payload
        Uses bit-packed path navigation to update FIXED_DICT fields or ARRAY elements.
        """
        if len(packet.raw_payload) < 9:
            return

        entity_id, is_slice_byte, _payload_size = struct.unpack(
            "<IBi", packet.raw_payload[:9],
        )
        packet.entity_id = entity_id

        entity_type = self._entity_types.get(entity_id)
        if entity_type is None:
            return
        packet.entity_type = entity_type

        bit_payload = packet.raw_payload[9:]
        if not bit_payload:
            return

        # Read the property index from the bit stream

        entity = self._entities.get(entity_type)
        if entity is None:
            return

        num_props = len(entity.client_properties)
        if num_props == 0:
            return

        reader = BitReader(bit_payload)

        # First bit: continuation flag
        #   1 = descend into nested structure (FIXED_DICT/ARRAY)
        #   0 = leaf update — replace the entire property value
        cont = reader.read_bits(1)

        # Property index: ceil(log2(num_props)) bits
        prop_bits = _bits_for_count(num_props)
        prop_idx = reader.read_bits(prop_bits)

        prop_def = self._entities.get_client_property(entity_type, prop_idx)
        if prop_def is None:
            return

        if cont == 0:
            # Leaf update: the remaining bytes contain the new value
            # for the entire property (simple type like float, int, etc.)
            remaining = reader.remaining_bytes()
            if not remaining:
                return
            schema = self._schema.build_property_schema(entity_type, prop_idx)
            if schema is None:
                return
            try:
                value = schema.parse(remaining)
                packet.property_name = prop_def.name
                packet.property_value = value
                # Apply to tracker's _current
                if self._tracker is not None:
                    entity_props = self._tracker._current.setdefault(entity_id, {})
                    entity_props[prop_def.name] = value
            except Exception:
                log.debug(
                    "Failed to parse leaf nested update: %s.%s",
                    entity_type, prop_def.name, exc_info=True,
                )
            return

        # cont == 1: descend into nested structure
        is_slice = is_slice_byte & 1 == 1
        _spec_info = None  # (array_path, candidate_len) from speculation
        result = self._parse_nested_update(
            entity_type, prop_idx, prop_def.name,
            bit_payload, entity_id, is_slice,
        )
        if result is None:
            # Speculative: array length may be wrong — try incrementing
            spec_result = self._speculative_nested_decode(
                entity_type, prop_idx, prop_def.name,
                bit_payload, entity_id, is_slice,
            )
            if spec_result is not None:
                result, _spec_info = spec_result
        if result is not None:
            path, field_name, value = result
            packet.property_name = prop_def.name

            # Apply the update to the current value in tracker
            if self._tracker is not None:
                entity_props = self._tracker._current.setdefault(entity_id, {})
                current = entity_props.get(prop_def.name)

                # If property doesn't exist yet (e.g. OWN_CLIENT properties
                # like privateVehicleState that are never set via entity-create),
                # build the intermediate path as nested dicts so the update
                # has somewhere to land.
                if current is None:
                    current = {}
                    entity_props[prop_def.name] = current

                # Navigate the path, tracking parent for array conversion
                target = current
                parent = None
                parent_key = None
                for key in path:
                    next_target = None
                    if isinstance(target, dict) and key in target:
                        next_target = target[key]
                    elif isinstance(target, dict):
                        next_target = {}
                        target[key] = next_target
                    elif isinstance(target, list):
                        try:
                            next_target = target[int(key)]
                        except (ValueError, IndexError):
                            break
                    if next_target is None:
                        break
                    parent = target
                    parent_key = key
                    target = next_target
                else:
                    if field_name.startswith("__slice__"):
                        # Array slice: insert value at idx1..idx2
                        parts = field_name.split("__")
                        try:
                            idx1, idx2 = int(parts[2]), int(parts[3])
                        except (IndexError, ValueError):
                            idx1 = idx2 = 0

                        # Ensure target is a list (may be a dict from
                        # intermediate path creation)
                        if isinstance(target, dict):
                            target = _dict_to_list(target)
                            if parent is not None and parent_key is not None:
                                if isinstance(parent, dict):
                                    parent[parent_key] = target
                                elif isinstance(parent, list):
                                    try:
                                        parent[int(parent_key)] = target
                                    except (ValueError, IndexError):
                                        pass

                        if isinstance(target, list):
                            target[idx1:idx2] = [value]
                            packet.property_value = current
                    elif isinstance(target, list):
                        try:
                            target[int(field_name)] = value
                            packet.property_value = current
                        except (ValueError, IndexError):
                            pass
                    elif isinstance(target, dict):
                        target[field_name] = value
                        packet.property_value = current

                # After apply: if this was a speculative decode, grow the
                # tracked array to the inferred min length. We do this AFTER
                # apply so the intermediate dicts + array exist in _current.
                if _spec_info is not None:
                    arr_path, _candidate_len = _spec_info
                    # Infer min array length from the decoded indices
                    # and grow the tracked array so subsequent packets
                    # use the correct arr_len in the normal path.
                    min_len = self._infer_min_array_len(result)
                    if min_len > 0:
                        self._grow_tracked_array(
                            entity_id, prop_def.name, arr_path, min_len,
                        )

    @staticmethod
    def _infer_min_array_len(
        result: tuple[list[str], str, Any],
    ) -> int:
        """Infer minimum array length from a decoded nested update result.

        For SetRange: __slice__idx1__idx2 → array had at least max(idx1,idx2) elements
        For SetElement: field_name is str(index) → array had at least index+1 elements
        For descent: path contains str(elem_idx) → array had at least elem_idx+1 elements
        """
        path, field_name, _ = result

        # Check field_name for slice marker
        if field_name.startswith("__slice__"):
            parts = field_name.split("__")
            try:
                idx1, idx2 = int(parts[2]), int(parts[3])
                # After slice[idx1:idx2] = [value], new len = old_len - (idx2-idx1) + 1
                # But the server's arr_len at encode time was >= max(idx1, idx2)
                # For an append: idx1 == idx2 == old_arr_len, so min = idx1 + 1
                return max(idx1, idx2) + 1
            except (IndexError, ValueError):
                pass

        # Check field_name for numeric element index
        if field_name.isdigit():
            return int(field_name) + 1

        # Check path for numeric segments (descent into array element)
        for segment in reversed(path):
            if segment.isdigit():
                return int(segment) + 1

        return 0

    def _parse_nested_update(
        self,
        entity_type: str,
        prop_idx: int,
        prop_name: str,
        bit_payload: bytes,
        entity_id: int,
        is_slice: bool,
        arr_len_overrides: dict[tuple[str, ...], int] | None = None,
    ) -> tuple[list[str], str, Any] | None:
        """Parse a nested property update from the bit payload."""

        entity = self._entities.get(entity_type)
        if entity is None:
            return None

        prop_def = self._entities.get_client_property(entity_type, prop_idx)
        if prop_def is None:
            return None

        # Resolve the property's type structure
        aliases = self._schema._aliases
        type_info = _resolve_type_structure(prop_def.type_name, aliases)
        if type_info is None:
            return None

        reader = BitReader(bit_payload)
        path: list[str] = []

        # First bit = cont (already checked as 1)
        reader.read_bits(1)
        # Property index (already extracted but need to advance the reader)
        num_props = len(entity.client_properties)
        reader.read_bits(_bits_for_count(num_props))

        # Now navigate the nested structure
        return self._navigate_nested(
            reader, is_slice, type_info, entity_id, prop_name, path, aliases,
            arr_len_overrides=arr_len_overrides,
        )

    def _navigate_nested(
        self,
        reader,
        is_slice: bool,
        type_info: dict[str, Any],
        entity_id: int,
        prop_name: str,
        path: list[str],
        aliases: AliasRegistry,
        arr_len_overrides: dict[tuple[str, ...], int] | None = None,
    ) -> tuple[list[str], str, Any] | None:
        """Recursively navigate nested structure and return (path, field, value)."""

        cont = reader.read_bits(1)
        kind = type_info.get("kind")

        if cont == 0:
            # Apply update at this level
            if kind == "dict":
                fields = type_info["fields"]
                bits = _bits_for_count(len(fields))
                field_idx = reader.read_bits(bits)
                if field_idx >= len(fields):
                    return None
                field_name, field_type = fields[field_idx]
                remaining = reader.remaining_bytes()
                if not remaining:
                    return None
                schema = self._schema._resolve_type(field_type, in_method=True)
                if schema is None:
                    return None
                try:
                    value = schema.parse(remaining)
                    return (path, field_name, value)
                except Exception:
                    return None

            elif kind == "array":
                # Array update — resolve array length
                path_key = tuple(path)
                if arr_len_overrides and path_key in arr_len_overrides:
                    arr_len = arr_len_overrides[path_key]
                else:
                    arr_len = self._get_tracked_arr_len(entity_id, prop_name, path_key)

                if is_slice:
                    # SetRange: idx1..idx2 replaced with new values
                    count = arr_len + 1
                    bits = _bits_for_count(count)
                    idx1 = reader.read_bits(bits)
                    idx2 = reader.read_bits(bits)
                    remaining = reader.remaining_bytes()
                    if not remaining:
                        return None
                    elem_type = type_info.get("element_type", "BLOB")
                    schema = self._schema._resolve_type(elem_type, in_method=True)
                    if schema is None:
                        return None
                    try:
                        value = schema.parse(remaining)
                        # Return special marker for slice operations
                        return (path, f"__slice__{idx1}__{idx2}", value)
                    except Exception:
                        return None
                else:
                    # SetElement: update single element at index
                    bits = _bits_for_count(max(arr_len, 1))
                    idx1 = reader.read_bits(bits)
                    remaining = reader.remaining_bytes()
                    if not remaining:
                        return None
                    elem_type = type_info.get("element_type", "BLOB")
                    schema = self._schema._resolve_type(elem_type, in_method=True)
                    if schema is None:
                        return None
                    try:
                        value = schema.parse(remaining)
                        return (path, str(idx1), value)
                    except Exception:
                        return None

            return None

        # cont == 1: descend deeper
        if kind == "dict":
            fields = type_info["fields"]
            bits = _bits_for_count(len(fields))
            field_idx = reader.read_bits(bits)
            if field_idx >= len(fields):
                return None
            field_name, field_type = fields[field_idx]
            child_type = _resolve_type_structure(field_type, aliases)
            if child_type is None:
                child_type = {"kind": "leaf", "type_name": field_type}
            return self._navigate_nested(
                reader, is_slice, child_type, entity_id, prop_name,
                path + [field_name], aliases,
                arr_len_overrides=arr_len_overrides,
            )

        elif kind == "array":
            path_key = tuple(path)
            if arr_len_overrides and path_key in arr_len_overrides:
                arr_len = arr_len_overrides[path_key]
            else:
                arr_len = self._get_tracked_arr_len(entity_id, prop_name, path_key)
            bits = _bits_for_count(max(arr_len, 1))
            elem_idx = reader.read_bits(bits)
            elem_type = type_info.get("element_type", "BLOB")
            child_type = _resolve_type_structure(elem_type, aliases)
            if child_type is None:
                child_type = {"kind": "leaf", "type_name": elem_type}
            return self._navigate_nested(
                reader, is_slice, child_type, entity_id, prop_name,
                path + [str(elem_idx)], aliases,
                arr_len_overrides=arr_len_overrides,
            )

        return None

    def _collect_array_paths(
        self,
        type_info: dict[str, Any],
        prefix: tuple[str, ...],
        aliases: AliasRegistry,
        result: list[tuple[str, ...]],
    ) -> None:
        """Recursively collect paths to ARRAY types within a type structure."""

        kind = type_info.get("kind")
        if kind == "array":
            result.append(prefix)
        elif kind == "dict":
            for field_name, field_type in type_info["fields"]:
                child = _resolve_type_structure(field_type, aliases)
                if child:
                    self._collect_array_paths(child, prefix + (field_name,), aliases, result)

    @functools.lru_cache(maxsize=256)
    def _find_array_paths(
        self, entity_type: str, prop_idx: int,
    ) -> list[tuple[str, ...]]:
        """Return all path tuples that lead to ARRAY types in this property."""

        prop_def = self._entities.get_client_property(entity_type, prop_idx)
        if prop_def is None:
            return []
        aliases = self._schema._aliases
        type_info = _resolve_type_structure(prop_def.type_name, aliases)
        if type_info is None:
            return []
        paths: list[tuple[str, ...]] = []
        self._collect_array_paths(type_info, (), aliases, paths)
        return paths

    def _get_tracked_arr_len(
        self, entity_id: int, prop_name: str, array_path: tuple[str, ...],
    ) -> int:
        """Get the current tracked array length for a nested array path."""
        if not self._tracker:
            return 0
        current = self._tracker._current.get(entity_id, {}).get(prop_name)
        for key in array_path:
            if isinstance(current, dict):
                current = current.get(key)
            else:
                return 0
        if isinstance(current, (list, tuple)):
            return len(current)
        return 0

    def _speculative_nested_decode(
        self,
        entity_type: str,
        prop_idx: int,
        prop_name: str,
        bit_payload: bytes,
        entity_id: int,
        is_slice: bool,
    ) -> tuple[tuple[list[str], str, Any], tuple[tuple[str, ...], int]] | None:
        """Try decoding with progressively larger array lengths.

        Returns (result, (array_path, candidate_len)) on success, None on failure.
        The caller is responsible for growing the tracked array AFTER applying
        the result to _current (so the intermediate structure exists).
        """
        from wows_replay_parser.packets.nested_property import _bits_for_count

        array_paths = self._find_array_paths(entity_type, prop_idx)
        if not array_paths:
            return None

        # _bits_for_count is a step function. Try ONE representative per
        # bracket, starting from the next bracket above base_len.
        # Stop at 512 — arrays larger than that are extremely rare and
        # high-bracket false positives are dangerous (they corrupt state).
        bracket_representatives = [2, 3, 5, 9, 17, 33, 65, 129, 257, 513]

        for array_path in array_paths:
            base_len = self._get_tracked_arr_len(entity_id, prop_name, array_path)
            base_bits = _bits_for_count(max(base_len + 1 if is_slice else base_len, 1))

            for candidate_len in bracket_representatives:
                if candidate_len <= base_len:
                    continue
                candidate_bits = _bits_for_count(
                    max(candidate_len + 1 if is_slice else candidate_len, 1),
                )
                if candidate_bits == base_bits:
                    continue  # same bit count, won't help

                overrides = {array_path: candidate_len}
                result = self._parse_nested_update(
                    entity_type, prop_idx, prop_name,
                    bit_payload, entity_id, is_slice,
                    arr_len_overrides=overrides,
                )
                if result is not None:
                    return (result, (array_path, candidate_len))

        return None

    def _grow_tracked_array(
        self,
        entity_id: int,
        prop_name: str,
        array_path: tuple[str, ...],
        target_len: int,
    ) -> None:
        """Grow an existing tracked array to target_len by appending None.

        Only operates on arrays that already exist in _current.
        Does NOT create intermediate dict structure — that would corrupt
        state for subsequent normal-path decodes.
        """
        if not self._tracker:
            return
        current = self._tracker._current.get(entity_id, {}).get(prop_name)
        if current is None:
            return
        # Navigate the path — bail if any step is missing
        target = current
        for key in array_path:
            if isinstance(target, dict) and key in target:
                target = target[key]
            else:
                return  # path doesn't exist yet, don't create it
        if isinstance(target, list):
            while len(target) < target_len:
                target.append(None)

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

    def _handle_player_orientation(self, packet: Packet) -> None:
        """
        PlayerOrientation (0x2C) — self player's ship position.

        The BigWorld engine doesn't send Position packets for the player's
        own entity. Instead, PlayerOrientation carries the self ship's
        world position and rotation each tick.

        Payload (32 bytes):
            pid(u32) + parent_id(u32) + position(3xf32) + rotation(3xf32)

        Appears twice per tick: once with parent_id=0 (ship position),
        once with parent_id!=0 (camera on attached object).
        Only parent_id=0 entries represent the actual ship position.
        """
        if len(packet.raw_payload) < 32:
            return
        pid, parent_id = struct.unpack("<II", packet.raw_payload[:8])
        if parent_id != 0:
            return  # Camera orientation, not ship position
        x, y, z = struct.unpack("<fff", packet.raw_payload[8:20])
        rx, ry, rz = struct.unpack("<fff", packet.raw_payload[20:32])
        packet.entity_id = pid
        packet.position = (x, y, z)
        packet.rotation = (rx, ry, rz)
        entity_type = self._entity_types.get(pid)
        if entity_type:
            packet.entity_type = entity_type

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

    # ── Critical missing handlers ────────────────────────────────────

    def _handle_entity_leave(self, packet: Packet) -> None:
        """
        EntityLeave (0x04) — entity leaves Area of Interest.

        Payload: entity_id(u32)
        """
        if len(packet.raw_payload) < 4:
            return
        entity_id = struct.unpack("<I", packet.raw_payload[:4])[0]
        packet.entity_id = entity_id
        entity_type = self._entity_types.get(entity_id)
        if entity_type:
            packet.entity_type = entity_type

    def _handle_entity_control(self, packet: Packet) -> None:
        """
        EntityControl (0x02) — transfers entity ownership to client.

        Payload: entity_id(u32) + is_controlled(u8)
        """
        if len(packet.raw_payload) < 5:
            return
        entity_id, is_controlled = struct.unpack("<IB", packet.raw_payload[:5])
        packet.entity_id = entity_id
        packet.is_controlled = is_controlled != 0
        entity_type = self._entity_types.get(entity_id)
        if entity_type:
            packet.entity_type = entity_type

    def _handle_own_ship(self, packet: Packet) -> None:
        """
        OwnShip (0x20) — links Avatar to its owned Vehicle entity.

        Payload: entity_id(u32) — the Vehicle entity_id that the Avatar owns.
        """
        if len(packet.raw_payload) < 4:
            return
        vehicle_id = struct.unpack("<I", packet.raw_payload[:4])[0]
        packet.owned_vehicle_id = vehicle_id
        packet.entity_id = vehicle_id
        entity_type = self._entity_types.get(vehicle_id)
        if entity_type:
            packet.entity_type = entity_type

    def _handle_version(self, packet: Packet) -> None:
        """
        Version (0x16) — game version string.

        Payload: length(u32) + version_string(bytes)
        """
        if len(packet.raw_payload) < 4:
            return
        str_len = struct.unpack("<I", packet.raw_payload[:4])[0]
        if len(packet.raw_payload) >= 4 + str_len:
            packet.version_string = packet.raw_payload[4:4 + str_len].decode("utf-8", errors="replace")

    def _handle_map(self, packet: Packet) -> None:
        """
        Map (0x28, >=12.6) — map/arena info.

        Layout (verified against wows-toolkit parse_map_packet):
            space_id(u32) + arena_id(i64) + unknown1(u32) + unknown2(u32) +
            blob(128 bytes) + map_name_len(u32) + map_name(str) +
            matrix(4x4 f32, 64 bytes) + unknown(u8)
        """
        if len(packet.raw_payload) < 20:
            return
        space_id = struct.unpack_from("<I", packet.raw_payload, 0)[0]
        arena_id = struct.unpack_from("<q", packet.raw_payload, 4)[0]
        packet.space_id = space_id
        packet.arena_id = arena_id
        # unknown1, unknown2 at offset 12, 16
        # 128-byte opaque blob at offset 20
        # map name string at offset 148
        if len(packet.raw_payload) >= 152:
            str_len = struct.unpack_from("<I", packet.raw_payload, 148)[0]
            if len(packet.raw_payload) >= 152 + str_len:
                packet.map_name = packet.raw_payload[152:152 + str_len].decode(
                    "utf-8", errors="replace",
                )
        packet.map_data = packet.raw_payload[20:148]  # the 128-byte blob

    def _handle_battle_results(self, packet: Packet) -> None:
        """
        BattleResults (0x22, >=12.6) — post-battle statistics blob.

        Payload: length(u32) + JSON/pickle data.
        The first 4 bytes appear to be a length prefix, followed by
        a JSON blob with battle results.
        """
        packet.battle_results_data = packet.raw_payload

    # ── Useful per-tick handlers ─────────────────────────────────────

    def _handle_camera(self, packet: Packet) -> None:
        """
        Camera (0x25) — camera position/rotation, 60 bytes per tick.

        Payload layout (from hex analysis):
        - rotation quaternion: 4xf32 (16 bytes) at offset 0
        - unknown: 8 bytes at offset 16
        - pitch/yaw: 2xf32 at offset 24
        - fov related: f32 at offset 28
        - padding: 4 bytes at offset 32
        - position: 3xf32 at offset 36
        - more data: remaining bytes

        Based on hex dumps: positions visible at offset 36-48,
        fov-like value (1.0) at offset 56.
        """
        if len(packet.raw_payload) < 60:
            return
        # Quaternion at offset 0-16
        qx, qy, qz, qw = struct.unpack_from("<ffff", packet.raw_payload, 0)
        packet.camera_rotation = (qx, qy, qz, qw)
        # Position at offset 36
        cx, cy, cz = struct.unpack_from("<fff", packet.raw_payload, 36)
        packet.camera_position = (cx, cy, cz)
        # FOV at offset 56
        fov = struct.unpack_from("<f", packet.raw_payload, 56)[0]
        packet.camera_fov = fov

    def _handle_gun_marker(self, packet: Packet) -> None:
        """
        GunMarker (0x18) — aiming state, 52 bytes per tick.

        Written alongside Camera every tick. Contains gun direction data.
        """
        if len(packet.raw_payload) < 52:
            return
        packet.gun_marker_data = packet.raw_payload

    def _handle_server_timestamp(self, packet: Packet) -> None:
        """
        ServerTimestamp (0x0F) — f64 server time.

        Payload: server_time(f64)
        """
        if len(packet.raw_payload) < 8:
            return
        packet.server_time = struct.unpack("<d", packet.raw_payload[:8])[0]

    def _handle_server_tick(self, packet: Packet) -> None:
        """
        ServerTick (0x0E) — tick rate constant (always 1/7 ≈ 0.1428).

        Payload: tick_rate(f64)
        """
        if len(packet.raw_payload) < 8:
            return
        packet.server_time = struct.unpack("<d", packet.raw_payload[:8])[0]

    # ── Low priority metadata handlers ───────────────────────────────

    def _handle_init_flag(self, packet: Packet) -> None:
        """InitFlag (0x10) — u8 flag at clock=0."""
        pass  # 1 byte, logged but not actionable

    def _handle_init_marker(self, packet: Packet) -> None:
        """InitMarker (0x13) — empty packet, zero bytes."""
        pass  # No payload

    def _handle_player_net_stats(self, packet: Packet) -> None:
        """PlayerNetStats (0x1D) — network quality metrics (u32 packed)."""
        pass  # 4 bytes packed network stats, not needed for gameplay

    def _handle_camera_mode(self, packet: Packet) -> None:
        """
        CameraMode (0x27) — camera mode change.

        Payload: mode(u32)
        """
        if len(packet.raw_payload) < 4:
            return
        packet.camera_mode = struct.unpack("<I", packet.raw_payload[:4])[0]

    def _handle_camera_free_look(self, packet: Packet) -> None:
        """
        CameraFreelook (0x2F) — freelook camera state.

        Payload: state(u8)
        """
        pass  # 1 byte state flag

    def _handle_set_weapon_lock(self, packet: Packet) -> None:
        """
        SetWeaponLock (0x30) — weapon lock state change.

        Payload: flags(u32) + weapon_type(u32) + target_entity_id(u32)
        """
        if len(packet.raw_payload) < 12:
            return
        flags, weapon_type, target_id = struct.unpack("<III", packet.raw_payload[:12])
        packet.weapon_lock_flags = flags
        packet.weapon_lock_target = target_id
        packet.entity_id = target_id

    def _handle_cruise_state(self, packet: Packet) -> None:
        """
        CruiseState (0x32) — cruise control state.

        Payload: state(u32) + value(u32)
        """
        if len(packet.raw_payload) < 8:
            return
        state, value = struct.unpack("<II", packet.raw_payload[:8])
        packet.cruise_state = state
        packet.cruise_value = value

    def _handle_sub_controller(self, packet: Packet) -> None:
        """SubController (0x31) — submarine controller mode."""
        pass  # Submarine-specific, no data needed yet

    def _handle_shot_tracking(self, packet: Packet) -> None:
        """
        ShotTracking (0x33) — shot tracking (2026+).

        Payload: entity_id(u32) + weapon_id(u32) + value(u32)
        """
        if len(packet.raw_payload) < 12:
            return
        entity_id, weapon_id, value = struct.unpack("<III", packet.raw_payload[:12])
        packet.entity_id = entity_id
        packet.shot_tracking_entity = entity_id
        packet.shot_tracking_weapon = weapon_id
        packet.shot_tracking_value = value
        entity_type = self._entity_types.get(entity_id)
        if entity_type:
            packet.entity_type = entity_type
