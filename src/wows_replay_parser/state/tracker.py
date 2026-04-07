from __future__ import annotations

import dataclasses
import math
from bisect import bisect_left, bisect_right
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator

from wows_replay_parser.packets.types import Packet, PacketType

from .models import (
    AircraftState,
    BattleState,
    BuildingState,
    CapturePointState,
    GameState,
    HoldScoring,
    KillScoring,
    PropertyChange,
    ShipState,
    SmokeScreenState,
)

_SENTINEL = object()


def _container_get(obj: Any, key: str, default: Any = None) -> Any:
    """Get a value from a construct Container or plain dict.

    Handles both attribute access (Container) and dict access.
    Correctly preserves falsy values (0, False, empty string).
    """
    val = getattr(obj, key, _SENTINEL)
    if val is not _SENTINEL:
        return val
    if isinstance(obj, dict) and key in obj:
        return obj[key]
    return default


# Properties that map to ShipState fields
_SHIP_PROPERTY_MAP: dict[str, str] = {
    "health": "health",
    "maxHealth": "max_health",
    "regenerationHealth": "regeneration_health",
    "regeneratedHealth": "regenerated_health",
    "isAlive": "is_alive",
    "teamId": "team_id",
    "visibilityFlags": "visibility_flags",
    "burningFlags": "burning_flags",
}

_SNAPSHOT_INTERVAL = 5.0  # seconds between cached snapshots


class GameStateTracker:
    """Tracks entity property state over time from decoded packets."""

    def __init__(self) -> None:
        self._current: dict[int, dict[str, Any]] = {}
        self._entity_types: dict[int, str] = {}
        self._history: list[PropertyChange] = []
        self._history_timestamps: list[float] = []  # parallel index for bisect
        self._positions: dict[int, list[tuple[float, tuple[float, float, float], float]]] = {}
        self._snapshots: list[tuple[float, dict[int, dict[str, Any]]]] = []
        self._last_snapshot_time: float = -_SNAPSHOT_INTERVAL
        # Dirty tracking for copy-on-write snapshots: entity_ids modified
        # since the last snapshot. Only these need copying on next snapshot.
        self._dirty_entities: set[int] = set()
        # Previous snapshot data — clean entities reuse their dict from here
        self._prev_snapshot: dict[int, dict[str, Any]] = {}
        # Minimap vision info (Trap 5/6): entity_id → list of
        # (timestamp, world_x, world_z, heading_rad, is_visible, is_disappearing)
        self._minimap_positions: dict[int, list[tuple[float, float, float, float, bool, bool]]] = {}
        # Death position cache (Trap 13): entity_id → (position, yaw)
        self._death_positions: dict[int, tuple[tuple[float, float, float], float]] = {}
        # OwnShip: the Vehicle entity_id owned by the replay's player
        self._own_vehicle_id: int | None = None
        # Entities that have left Area of Interest (timestamp tracked)
        self._entity_leave_times: dict[int, float] = {}
        # Consumable activations per entity:
        # entity_id → list of (timestamp, consumable_type_id, duration)
        self._consumable_activations: dict[int, list[tuple[float, int, float]]] = {}
        # Consumable ID → slot index mapping per entity (from setConsumables pickle)
        self._consumable_id_to_slot: dict[int, dict[int, int]] = {}
        # Aircraft/squadron log: (timestamp, plane_id, state) — None state = removed
        self._aircraft_log: list[tuple[float, int, AircraftState | None]] = []
        # Camera state per tick
        self._camera_positions: list[tuple[float, tuple[float, float, float]]] = []
        # Server timestamp (absolute time from ServerTimestamp packet)
        self._server_time: float | None = None
        # Version string from Version packet
        self._version_string: str | None = None
        # Map info from Map packet
        self._map_space_id: int | None = None
        self._map_arena_id: int | None = None
        self._map_name: str | None = None
        # PlayerNetStats (0x1D) timeline: list of (timestamp, raw_u32)
        self._net_stats: list[tuple[float, int]] = []

    def process_packet(self, packet: Packet) -> list[PropertyChange]:
        """Process a decoded packet, updating internal state.
        Returns list of PropertyChange objects for any state changes."""
        changes: list[PropertyChange] = []

        ptype = packet.type

        # Periodic snapshots — take BEFORE processing the packet so
        # the snapshot reflects the state just before this timestamp.
        # This ensures bisect_right(history_timestamps, snapshot_time)
        # correctly excludes all entries at or after this timestamp.
        #
        # Copy-on-write: only shallow-copy entities that changed since
        # the last snapshot. Clean entities reuse their previous dict.
        if packet.timestamp - self._last_snapshot_time >= _SNAPSHOT_INTERVAL:
            snapshot: dict[int, dict[str, Any]] = {}
            for eid, props in self._current.items():
                if eid in self._dirty_entities:
                    # Entity was modified — deep-copy mutable property values.
                    # NESTED_PROPERTY (0x23) mutates dicts/lists in-place on
                    # _current, so a shallow copy would share references and
                    # corrupt earlier snapshots when later packets arrive.
                    snapshot[eid] = self._snapshot_props(props)
                elif eid in self._prev_snapshot:
                    # Safe to reuse: entity not dirty means no writes to
                    # _current[eid] since last snapshot. NESTED_PROPERTY
                    # handler must mark entities dirty on any mutation —
                    # if that invariant breaks, the reused snapshot will
                    # silently diverge from _current.
                    snapshot[eid] = self._prev_snapshot[eid]
                else:
                    # New entity, first snapshot — deep-copy mutable values
                    snapshot[eid] = self._snapshot_props(props)
            self._snapshots.append((packet.timestamp, snapshot))
            self._prev_snapshot = snapshot
            self._dirty_entities.clear()
            self._last_snapshot_time = packet.timestamp

        # Entity creation — register type
        creation_types = (
            PacketType.BASE_PLAYER_CREATE,
            PacketType.ENTITY_CREATE,
            PacketType.BASE_PLAYER_CREATE_STUB,
        )
        if ptype in creation_types:
            if packet.entity_type is not None:
                self._entity_types[packet.entity_id] = packet.entity_type
                self._current.setdefault(packet.entity_id, {})
                self._dirty_entities.add(packet.entity_id)

            # Seed initial position from ENTITY_CREATE so vehicles are
            # visible from spawn (especially the self player and allies
            # that may not receive POSITION packets immediately).
            if (
                ptype == PacketType.ENTITY_CREATE
                and packet.position is not None
                and packet.entity_id not in self._positions
            ):
                entry = (packet.timestamp, packet.position, 0.0)
                self._positions.setdefault(packet.entity_id, []).insert(0, entry)

            # Store initial properties from ENTITY_CREATE inline state.
            # Snapshot values for history so nested property mutations
            # don't corrupt the historical record.
            if (
                ptype == PacketType.ENTITY_CREATE
                and packet.initial_properties
            ):
                entity_props = self._current.setdefault(packet.entity_id, {})
                entity_type = packet.entity_type or ""
                for prop_name, prop_value in packet.initial_properties.items():
                    entity_props[prop_name] = prop_value
                    change = PropertyChange(
                        timestamp=packet.timestamp,
                        entity_id=packet.entity_id,
                        entity_type=entity_type,
                        property_name=prop_name,
                        old_value=None,
                        new_value=self._snapshot_value(prop_value),
                    )
                    self._history.append(change)
                    self._history_timestamps.append(change.timestamp)
                    changes.append(change)

        # Property update
        elif ptype == PacketType.ENTITY_PROPERTY:
            if packet.property_name:
                self._dirty_entities.add(packet.entity_id)
                entity_props = self._current.setdefault(packet.entity_id, {})
                old_value = entity_props.get(packet.property_name)
                entity_props[packet.property_name] = packet.property_value
                entity_type = packet.entity_type or self._entity_types.get(packet.entity_id, "")
                change = PropertyChange(
                    timestamp=packet.timestamp,
                    entity_id=packet.entity_id,
                    entity_type=entity_type,
                    property_name=packet.property_name,
                    old_value=old_value,
                    new_value=self._snapshot_value(packet.property_value),
                )
                self._history.append(change)
                self._history_timestamps.append(change.timestamp)
                changes.append(change)

        # NestedProperty update (0x23) — sub-field change within a property.
        # The decoder applies the update to _current directly; we record
        # a snapshot of the property in history so iter_states sees
        # the value at each point in time (not the final mutated ref).
        # We use _snapshot_value() to avoid deepcopy on BytesIO objects
        # inside construct Containers.
        elif ptype == PacketType.NESTED_PROPERTY:
            if packet.property_name and packet.property_value is not None:
                self._dirty_entities.add(packet.entity_id)
                entity_type = packet.entity_type or self._entity_types.get(packet.entity_id, "")
                change = PropertyChange(
                    timestamp=packet.timestamp,
                    entity_id=packet.entity_id,
                    entity_type=entity_type,
                    property_name=packet.property_name,
                    old_value=None,
                    new_value=self._snapshot_value(packet.property_value),
                )
                self._history.append(change)
                self._history_timestamps.append(change.timestamp)
                changes.append(change)

        # EntityLeave (0x04) — entity leaves AoI
        elif ptype == PacketType.ENTITY_LEAVE:
            if packet.entity_id:
                self._entity_leave_times[packet.entity_id] = packet.timestamp

        # OwnShip (0x20) — links Avatar to its Vehicle
        elif ptype == PacketType.OWN_SHIP:
            if packet.owned_vehicle_id is not None:
                self._own_vehicle_id = packet.owned_vehicle_id

        # Version (0x16)
        elif ptype == PacketType.VERSION:
            if packet.version_string:
                self._version_string = packet.version_string

        # Map (0x28)
        elif ptype == PacketType.MAP:
            if packet.space_id is not None:
                self._map_space_id = packet.space_id
                self._map_arena_id = packet.arena_id
            if packet.map_name is not None:
                self._map_name = packet.map_name

        # ServerTimestamp (0x0F)
        elif ptype == PacketType.SERVER_TIMESTAMP:
            if packet.server_time is not None:
                self._server_time = packet.server_time

        # Camera (0x25) — store camera position for potential replay rendering
        elif ptype == PacketType.CAMERA:
            if packet.camera_position is not None:
                self._camera_positions.append(
                    (packet.timestamp, packet.camera_position),
                )

        # PlayerNetStats (0x1D) — store raw network quality metric for timeline queries
        elif ptype == PacketType.PLAYER_NET_STATS:
            raw = getattr(packet, "net_stats_raw", None)
            if raw is not None:
                self._net_stats.append((packet.timestamp, raw))

        # Position update (0x0A), NonVolatilePosition (0x2A — Trap 10),
        # and PlayerOrientation (0x2C — self player's ship position)
        elif ptype in (PacketType.POSITION, PacketType.NON_VOLATILE_POSITION,
                       PacketType.PLAYER_ORIENTATION):
            if packet.position and packet.entity_id:
                yaw = 0.0
                # All position packet types store ship heading in
                # rotation[0] (yaw, pitch, roll). The 'direction' field
                # in Position (0x0A) is NOT a velocity vector for other
                # players — it contains garbage (denormalized floats).
                rotation = getattr(packet, "rotation", None)
                if rotation is not None:
                    yaw = rotation[0]
                entry = (packet.timestamp, packet.position, yaw)
                self._positions.setdefault(packet.entity_id, []).append(entry)

        # Method call — watch for deaths, minimap vision, consumables
        elif ptype == PacketType.ENTITY_METHOD:
            # Consumable slot mapping from setConsumables (pickle with consumablesDict)
            if packet.method_name == "setConsumables" and packet.method_args:
                self._track_consumable_slots(packet)

            # Consumable activation tracking via onConsumableUsed.
            # Args: consumableUsageParams(BLOB) + workTimeLeft(FLOAT32)
            # The BLOB contains: usage_type(u8) + consumable_id(u8)
            if packet.method_name == "onConsumableUsed" and packet.method_args:
                self._track_consumable_used(packet)

            # Minimap vision info (Trap 5/6)
            if packet.method_name == "updateMinimapVisionInfo" and packet.method_args:
                self._process_minimap_vision(packet)

            elif packet.method_name == "receiveVehicleDeath" and packet.method_args:
                # Args: (victim_id, killer_id, reason)
                victim_id = self._get_arg(packet.method_args, 0)
                if victim_id is not None:
                    # Trap 13: cache death position before marking dead
                    self._cache_death_position(victim_id, packet.timestamp)
                    self._dirty_entities.add(victim_id)
                    victim_props = self._current.setdefault(victim_id, {})
                    old = victim_props.get("isAlive", True)
                    victim_props["isAlive"] = False
                    entity_type = self._entity_types.get(victim_id, "")
                    change = PropertyChange(
                        timestamp=packet.timestamp,
                        entity_id=victim_id,
                        entity_type=entity_type,
                        property_name="isAlive",
                        old_value=old,
                        new_value=False,
                    )
                    self._history.append(change)
                    self._history_timestamps.append(change.timestamp)
                    changes.append(change)

            elif packet.method_name == "kill" and packet.entity_id:
                # Trap 13: cache death position before marking dead
                self._cache_death_position(packet.entity_id, packet.timestamp)
                self._dirty_entities.add(packet.entity_id)
                entity_props = self._current.setdefault(packet.entity_id, {})
                old = entity_props.get("isAlive", True)
                entity_props["isAlive"] = False
                entity_type = packet.entity_type or self._entity_types.get(packet.entity_id, "")
                change = PropertyChange(
                    timestamp=packet.timestamp,
                    entity_id=packet.entity_id,
                    entity_type=entity_type,
                    property_name="isAlive",
                    old_value=old,
                    new_value=False,
                )
                self._history.append(change)
                self._history_timestamps.append(change.timestamp)
                changes.append(change)

            # Squadron tracking
            elif packet.method_name == "receive_addMinimapSquadron" and packet.method_args:
                args = packet.method_args
                plane_id = int(self._get_arg(args, 0) or 0)
                pos = self._get_arg(args, 3) or {}
                self._aircraft_log.append((packet.timestamp, plane_id, AircraftState(
                    plane_id=plane_id,
                    squadron_type="controllable",
                    team_id=int(self._get_arg(args, 1) or 0),
                    params_id=int(self._get_arg(args, 2) or 0),
                    x=float(pos.get("x", 0)) if isinstance(pos, dict) else 0.0,
                    z=float(pos.get("y", 0)) if isinstance(pos, dict) else 0.0,
                )))

            elif packet.method_name == "receive_updateMinimapSquadron" and packet.method_args:
                args = packet.method_args
                plane_id = int(self._get_arg(args, 0) or 0)
                pos = self._get_arg(args, 1) or {}
                current = self._aircraft_latest(plane_id)
                if current is not None:
                    updated = dataclasses.replace(
                        current,
                        x=float(pos.get("x", 0)) if isinstance(pos, dict) else current.x,
                        z=float(pos.get("y", 0)) if isinstance(pos, dict) else current.z,
                    )
                    self._aircraft_log.append((packet.timestamp, plane_id, updated))

            elif packet.method_name in (
                "receive_removeMinimapSquadron", "receive_removeSquadron",
            ) and packet.method_args:
                plane_id = int(self._get_arg(packet.method_args, 0) or 0)
                self._aircraft_log.append((packet.timestamp, plane_id, None))

            elif packet.method_name == "receive_deactivateSquadron" and packet.method_args:
                plane_id = int(self._get_arg(packet.method_args, 0) or 0)
                current = self._aircraft_latest(plane_id)
                if current is not None:
                    self._aircraft_log.append((packet.timestamp, plane_id,
                        dataclasses.replace(current, is_active=False)))

            elif packet.method_name == "activateAirSupport" and packet.method_args:
                args = packet.method_args
                plane_id = int(args.get("squadronID", 0))
                pos = args.get("position") or {}
                # Avatar doesn't have teamId as a tracked property (BASE_PLAYER_CREATE
                # has no inline state). Derive from the Avatar's Vehicle via _own_vehicle_id.
                team_id = 0
                if self._own_vehicle_id is not None:
                    vehicle_props = self._current.get(self._own_vehicle_id, {})
                    team_id = int(vehicle_props.get("teamId", 0))
                # Preserve params_id from receive_addMinimapSquadron if it
                # already arrived (both fire at the same timestamp).
                existing = self._aircraft_latest(plane_id)
                params_id = existing.params_id if existing and existing.params_id else 0
                self._aircraft_log.append((packet.timestamp, plane_id, AircraftState(
                    plane_id=plane_id,
                    squadron_type="airstrike",
                    team_id=team_id or (existing.team_id if existing else 0),
                    params_id=params_id,
                    x=float(pos.get("x", 0)) if isinstance(pos, dict) else 0.0,
                    z=float(pos.get("z", 0)) if isinstance(pos, dict) else 0.0,
                )))

            elif packet.method_name == "deactivateAirSupport" and packet.method_args:
                plane_id = int(packet.method_args.get("squadronID", 0))
                self._aircraft_log.append((packet.timestamp, plane_id, None))

        return changes

    def state_at(self, t: float) -> GameState:
        """Reconstruct full game state at timestamp t."""
        state = self._rebuild_state_at(t)

        ships: dict[int, ShipState] = {}
        battle = BattleState()

        for entity_id, props in state.items():
            entity_type = self._entity_types.get(entity_id, "")

            if entity_type == "Vehicle":
                # Include ships with world position OR minimap position
                has_world_pos = self.position_at(entity_id, t) is not None
                has_mm_pos = self.minimap_at(entity_id, t) is not None
                if not has_world_pos and not has_mm_pos:
                    continue
                ship = self._build_ship_state(entity_id, props, t)
                ships[entity_id] = ship

            elif entity_type in ("BattleLogic", "BattleEntity"):
                battle = self._build_battle_state(props, state)

        # Build capture points even if BattleLogic entity is missing
        if not battle.capture_points:
            cap_points = self._build_capture_points(state)
            if cap_points:
                battle.capture_points = cap_points

        return GameState(
            timestamp=t, ships=ships, battle=battle,
            aircraft=self._build_aircraft_at(t),
            smoke_screens=self._build_smoke_screens(state, t),
            buildings=self._build_buildings(state, t),
        )

    def iter_states(
        self, timestamps: list[float],
    ) -> Iterator[GameState]:
        """Yield GameState for each timestamp, advancing forward.

        Optimized for sequential access (e.g., frame-by-frame
        rendering). Maintains running property state AND position
        pointers — no bisect, no copying, O(delta) per frame.

        Args:
            timestamps: Monotonically increasing list of query times.

        Yields:
            GameState snapshot at each requested timestamp.
        """
        if not timestamps:
            return

        # Initialize running state from the snapshot at or before the
        # first requested timestamp.  This ensures entity-create inline
        # state (which lives only in snapshots, not in _history) is
        # included — matching what _rebuild_state_at() does.
        t0 = timestamps[0]
        running: dict[int, dict[str, Any]] = {}
        snapshot_time = -1.0

        if self._snapshots:
            snapshot_times = [s[0] for s in self._snapshots]
            idx = bisect_right(snapshot_times, t0)
            if idx > 0:
                snapshot_time, snapshot_data = self._snapshots[idx - 1]
                running = {
                    eid: dict(props)
                    for eid, props in snapshot_data.items()
                }

        # Start history cursor at the snapshot time (bisect_left).
        # The snapshot is taken BEFORE the packet at snapshot_time is
        # processed, so history entries at snapshot_time need to be applied.
        history_idx = bisect_left(self._history_timestamps, snapshot_time)

        # Per-entity position cursors: entity_id → index into
        # self._positions[entity_id]
        pos_cursors: dict[int, int] = {}
        # Cached last-known position + yaw per entity
        pos_cache: dict[int, tuple[tuple[float, float, float], float]] = {}
        # Cached last position timestamp per entity (for stale detection)
        pos_time_cache: dict[int, float] = {}

        # Minimap vision cursors (Trap 5/6)
        mm_cursors: dict[int, int] = {}
        mm_cache: dict[int, tuple[float, float, float, bool]] = {}
        mm_time_cache: dict[int, float] = {}

        # Aircraft cursor
        aircraft_cursor = 0
        running_aircraft: dict[int, AircraftState] = {}

        for t in timestamps:
            # Apply property changes up to time t
            while (
                history_idx < len(self._history)
                and self._history[history_idx].timestamp <= t
            ):
                change = self._history[history_idx]
                entity_props = running.setdefault(
                    change.entity_id, {},
                )
                entity_props[change.property_name] = (
                    change.new_value
                )
                history_idx += 1

            # Advance position cursors for all tracked entities
            for eid, positions in self._positions.items():
                cursor = pos_cursors.get(eid, 0)
                while (
                    cursor < len(positions)
                    and positions[cursor][0] <= t
                ):
                    cursor += 1
                pos_cursors[eid] = cursor
                if cursor > 0:
                    entry = positions[cursor - 1]
                    pos_cache[eid] = (entry[1], entry[2])
                    pos_time_cache[eid] = entry[0]

            # Advance minimap vision cursors
            for eid, mm_entries in self._minimap_positions.items():
                cursor = mm_cursors.get(eid, 0)
                while (
                    cursor < len(mm_entries)
                    and mm_entries[cursor][0] <= t
                ):
                    cursor += 1
                mm_cursors[eid] = cursor
                if cursor > 0:
                    e = mm_entries[cursor - 1]
                    is_detected = e[4] and not e[5]
                    mm_cache[eid] = (e[1], e[2], e[3], is_detected)
                    mm_time_cache[eid] = e[0]

            # Build GameState using cached positions
            ships: dict[int, ShipState] = {}
            battle = BattleState()
            for entity_id, props in running.items():
                etype = self._entity_types.get(entity_id, "")
                if etype == "Vehicle":
                    is_alive = bool(props.get("isAlive", True))
                    mm = mm_cache.get(entity_id)

                    # Trap 13: use death position for dead ships
                    if not is_alive and entity_id in self._death_positions:
                        death_pos, death_yaw = self._death_positions[entity_id]
                        pos = death_pos
                        yaw = death_yaw
                    else:
                        cached = pos_cache.get(entity_id)
                        mm = mm_cache.get(entity_id)

                        if cached is not None:
                            pos = cached[0]
                            yaw = cached[1]

                            # Use minimap position if world pos is stale.
                            if mm is not None:
                                last_pos_t = pos_time_cache.get(entity_id, 0.0)
                                if t - last_pos_t > 5.0:
                                    last_mm_t = mm_time_cache.get(entity_id, 0.0)
                                    if last_mm_t > last_pos_t + 2.0:
                                        mm_x, mm_z, mm_h, _ = mm
                                        if mm_x != 0.0 or mm_z != 0.0:
                                            pos = (mm_x, 0.0, mm_z)
                                            yaw = mm_h

                        elif mm is not None:
                            mm_x, mm_z, mm_h, _ = mm
                            if mm_x != 0.0 or mm_z != 0.0:
                                pos = (mm_x, 0.0, mm_z)
                                yaw = mm_h
                            else:
                                continue
                        else:
                            continue  # not yet spotted

                    # Minimap vision (Trap 5/6) — mm already fetched above
                    if mm is None:
                        mm = mm_cache.get(entity_id)
                    mm_x = mm[0] if mm else 0.0
                    mm_z = mm[1] if mm else 0.0
                    mm_h = mm[2] if mm else 0.0
                    mm_det = mm[3] if mm else False

                    death_pos_val = self._death_positions.get(entity_id)
                    death_position = death_pos_val[0] if death_pos_val else None

                    ships[entity_id] = ShipState(
                        entity_id=entity_id,
                        health=float(props.get("health", 0)),
                        max_health=float(props.get("maxHealth", 0)),
                        regeneration_health=float(
                            props.get("regenerationHealth", 0),
                        ),
                        regenerated_health=float(
                            props.get("regeneratedHealth", 0),
                        ),
                        is_alive=is_alive,
                        team_id=int(props.get("teamId", 0)),
                        visibility_flags=int(
                            props.get("visibilityFlags", 0),
                        ),
                        burning_flags=int(
                            props.get("burningFlags", 0),
                        ),
                        position=pos,
                        yaw=yaw,
                        speed=float(
                            props.get("serverSpeedRaw", 0),
                        ),
                        minimap_x=mm_x,
                        minimap_z=mm_z,
                        minimap_heading=mm_h,
                        is_detected=mm_det,
                        death_position=death_position,
                        is_on_forsage=bool(props.get("isOnForsage", False)),
                        engine_power=int(props.get("enginePower", 0)),
                        engine_dir=int(props.get("engineDir", 0)),
                        speed_sign_dir=int(props.get("speedSignDir", 0)),
                        max_speed=float(props.get("maxServerSpeedRaw", 0)),
                        rudder_angle=float(props.get("ruddersAngle", 0)),
                        deep_rudder_angle=float(props.get("deepRuddersAngle", 0)),
                        selected_weapon=int(props.get("selectedWeapon", 0)),
                        is_invisible=bool(props.get("isInvisible", False)),
                        has_active_squadron=bool(props.get("hasActiveMainSquadron", False)),
                        is_in_rage_mode=bool(props.get("isInRageMode", False)),
                        respawn_time=float(props.get("respawnTime", 0)),
                        blocked_controls=int(props.get("blockedControls", 0)),
                        oil_leak_state=int(props.get("oilLeakState", 0)),
                        owner=int(props.get("owner", 0)),
                        regen_crew_hp_limit=float(props.get("regenCrewHpLimit", 0)),
                        buoyancy=float(props.get("buoyancy", 0)),
                        air_defense_disp_radius=float(props.get("airDefenseDispRadius", 0)),
                        weapon_lock_flags=int(props.get("weaponLockFlags", 0)),
                        target_local_pos=int(props.get("targetLocalPos", 0)),
                        torpedo_local_pos=int(props.get("torpedoLocalPos", 0)),
                    )
                elif etype in ("BattleLogic", "BattleEntity"):
                    battle = self._build_battle_state(
                        props, running,
                    )

            # Build capture points even if BattleLogic is missing
            if not battle.capture_points:
                cap_points = self._build_capture_points(running)
                if cap_points:
                    battle.capture_points = cap_points

            # Advance aircraft cursor
            while (
                aircraft_cursor < len(self._aircraft_log)
                and self._aircraft_log[aircraft_cursor][0] <= t
            ):
                _, plane_id, ac_state = self._aircraft_log[aircraft_cursor]
                if ac_state is None:
                    running_aircraft.pop(plane_id, None)
                else:
                    running_aircraft[plane_id] = ac_state
                aircraft_cursor += 1

            yield GameState(
                timestamp=t, ships=ships, battle=battle,
                aircraft=dict(running_aircraft),
                smoke_screens=self._build_smoke_screens(running, t),
                buildings=self._build_buildings(running, t),
            )

    def ship_state(self, entity_id: int, t: float) -> ShipState:
        """Get a specific ship's state at time t."""
        state = self._rebuild_state_at(t)
        props = state.get(entity_id, {})
        return self._build_ship_state(entity_id, props, t)

    def battle_state(self, t: float) -> BattleState:
        """Get battle-level state at time t."""
        state = self._rebuild_state_at(t)
        for entity_id, props in state.items():
            if self._entity_types.get(entity_id) in ("BattleLogic", "BattleEntity"):
                return self._build_battle_state(props, state)
        return BattleState()

    def camera_at(self, t: float) -> tuple[float, float, float] | None:
        """Get camera position at time t (bisect lookup).

        Returns the most recent camera position recorded at or before t,
        or None if no camera data is available.
        """
        if not self._camera_positions:
            return None
        timestamps = [entry[0] for entry in self._camera_positions]
        idx = bisect_right(timestamps, t)
        if idx == 0:
            return None
        return self._camera_positions[idx - 1][1]

    def net_stats_at(self, t: float) -> int | None:
        """Get raw network quality stat (u32) at time t (bisect lookup).

        Returns the most recent PLAYER_NET_STATS value recorded at or
        before t, or None if no data is available.  The packed u32 bitfield
        format is not fully documented; use raw value for custom analysis.
        """
        if not self._net_stats:
            return None
        timestamps = [entry[0] for entry in self._net_stats]
        idx = bisect_right(timestamps, t)
        if idx == 0:
            return None
        return self._net_stats[idx - 1][1]

    def position_at(self, entity_id: int, t: float) -> tuple[float, float, float] | None:
        """Interpolate position for entity at time t."""
        positions = self._positions.get(entity_id)
        if not positions:
            return None

        timestamps = [p[0] for p in positions]
        idx = bisect_right(timestamps, t)

        if idx == 0:
            return None  # No position recorded yet at time t
        if idx >= len(positions):
            return positions[-1][1]

        # Linear interpolation between two nearest points
        t0, pos0, _ = positions[idx - 1]
        t1, pos1, _ = positions[idx]
        dt = t1 - t0
        if dt <= 0:
            return pos0

        frac = (t - t0) / dt
        return (
            pos0[0] + (pos1[0] - pos0[0]) * frac,
            pos0[1] + (pos1[1] - pos0[1]) * frac,
            pos0[2] + (pos1[2] - pos0[2]) * frac,
        )

    def property_history(self, entity_id: int, prop_name: str) -> list[PropertyChange]:
        """Get all changes for a specific property on an entity."""
        return [
            c for c in self._history
            if c.entity_id == entity_id and c.property_name == prop_name
        ]

    def inject_property(
        self,
        entity_id: int,
        prop_name: str,
        value: Any,
    ) -> None:
        """Inject a property value from an external source.

        Used for properties that are set during entity creation
        (initial state data) rather than via ENTITY_PROPERTY packets,
        e.g., teamId.

        Updates _current, all snapshots, and prepends to history
        so both state_at() and iter_states() can see the value.
        """
        props = self._current.setdefault(entity_id, {})
        if prop_name not in props:
            props[prop_name] = value

        # Also inject into all existing snapshots
        for _ts, snap_data in self._snapshots:
            snap_props = snap_data.setdefault(entity_id, {})
            if prop_name not in snap_props:
                snap_props[prop_name] = value

        # And prepend to history so iter_states picks it up
        entity_type = self._entity_types.get(entity_id, "")
        change = PropertyChange(
            timestamp=-0.5,
            entity_id=entity_id,
            entity_type=entity_type,
            property_name=prop_name,
            old_value=None,
            new_value=value,
        )
        self._history.insert(0, change)
        self._history_timestamps.insert(0, -0.5)

    def get_entity_type(self, entity_id: int) -> str | None:
        """Look up entity type name by entity_id."""
        return self._entity_types.get(entity_id)

    def get_vehicle_entity_ids(self) -> list[int]:
        """Return all entity_ids that are Vehicle entities."""
        return [
            eid for eid, etype in self._entity_types.items()
            if etype == "Vehicle"
        ]

    def get_entity_props(self, entity_id: int) -> dict[str, Any]:
        """Get current property values for an entity."""
        return self._current.get(entity_id, {})

    @property
    def own_vehicle_id(self) -> int | None:
        """The Vehicle entity_id owned by the replay's player (from OwnShip packet)."""
        return self._own_vehicle_id

    @property
    def version_string(self) -> str | None:
        """Game version string from the Version packet."""
        return self._version_string

    @property
    def map_arena_id(self) -> int | None:
        """Arena ID from the Map packet."""
        return self._map_arena_id

    @property
    def server_time(self) -> float | None:
        """Absolute server time from the ServerTimestamp packet."""
        return self._server_time

    def active_consumables_at(
        self, entity_id: int, t: float,
    ) -> list[tuple[int, float, float]]:
        """Get active consumables for an entity at time t.

        Returns list of (slot_index, activated_at, duration)
        for consumables that are currently active (activated_at ≤ t < activated_at + duration).

        The slot_index maps to the ship's consumable slot ordering from
        GameParams (0=first slot, 1=second, etc.).
        """
        entries = self._consumable_activations.get(entity_id)
        if not entries:
            return []

        # Map cons_id → slot_index using the setConsumables pickle mapping
        id_to_slot = self._consumable_id_to_slot.get(entity_id, {})

        active = []
        for activated_at, cons_id, duration in entries:
            if activated_at <= t < activated_at + duration:
                slot_idx = id_to_slot.get(cons_id, cons_id)
                active.append((slot_idx, activated_at, duration))
        return active

    def is_entity_in_aoi(self, entity_id: int, t: float) -> bool:
        """Check if entity is in Area of Interest at time t.

        Returns True if the entity has not left AoI, or if it was
        re-created after leaving.
        """
        leave_time = self._entity_leave_times.get(entity_id)
        if leave_time is None:
            return True  # Never left
        return leave_time > t  # Was still in AoI at time t

    def minimap_at(
        self, entity_id: int, t: float,
    ) -> tuple[float, float, float, bool] | None:
        """Get minimap vision data at time t.

        Returns (world_x, world_z, heading_rad, is_detected) or None
        if no minimap data exists for this entity.
        """
        entries = self._minimap_positions.get(entity_id)
        if not entries:
            return None

        timestamps = [e[0] for e in entries]
        idx = bisect_right(timestamps, t)
        if idx == 0:
            return None

        entry = entries[idx - 1]
        _ts, wx, wz, heading, is_visible, is_disappearing = entry
        is_detected = is_visible and not is_disappearing
        return (wx, wz, heading, is_detected)

    def get_death_position(
        self, entity_id: int,
    ) -> tuple[tuple[float, float, float], float] | None:
        """Get cached death position and yaw for an entity.

        Returns (position, yaw) or None if not dead / no position cached.
        """
        return self._death_positions.get(entity_id)

    # --- Avatar / OWN_CLIENT helpers ---

    def _find_avatar_eid(self) -> int | None:
        """Return the entity ID of the Avatar (recording player), or None."""
        for eid, etype in self._entity_types.items():
            if etype == "Avatar":
                return eid
        return None

    def _avatar_props_at(self, t: float) -> dict[str, Any] | None:
        """Return the Avatar entity's property dict at time t, or None."""
        avatar_eid = self._find_avatar_eid()
        if avatar_eid is None:
            return None
        state = self._rebuild_state_at(t)
        return state.get(avatar_eid)

    def own_player_vehicle_state(self, t: float) -> dict | None:
        """Get the recording player's privateVehicleState at time t.

        Returns the full decoded dict (ribbons, damage tallies, etc.)
        or None if the Avatar entity hasn't been created yet or the
        property has not been received.

        This is an OWN_CLIENT property — only the recording player's
        Avatar entity carries it.
        """
        props = self._avatar_props_at(t)
        if props is None:
            return None
        pvs = props.get("privateVehicleState")
        if pvs is None:
            return None
        # Return a plain dict copy so callers can't mutate internal state.
        if isinstance(pvs, dict):
            return dict(pvs)
        # construct Container (dict subclass) — convert to plain dict,
        # stripping private keys like '_io'.
        return {k: v for k, v in pvs.items() if not k.startswith("_")}

    def spotted_entities_at(self, t: float) -> list | None:
        """Get the recording player's spottedEntities at time t.

        Returns the decoded list of spotted entity records, or None if
        the property is absent or not yet received.

        This is an OWN_CLIENT property on the Avatar entity.
        """
        props = self._avatar_props_at(t)
        if props is None:
            return None
        value = props.get("spottedEntities")
        if value is None:
            return None
        if isinstance(value, list):
            return list(value)
        return value

    def visibility_distances_at(self, t: float) -> dict | None:
        """Get the recording player's visibilityDistances at time t.

        Returns the decoded dict of visibility distance fields, or None
        if the property is absent or not yet received.

        Note: visibilityDistances has ALL_CLIENTS flag in Avatar.def, so
        it is visible for all spectators, not only the recording player.
        """
        props = self._avatar_props_at(t)
        if props is None:
            return None
        value = props.get("visibilityDistances")
        if value is None:
            return None
        if isinstance(value, dict):
            return dict(value)
        # construct Container — strip private keys
        if hasattr(value, "items"):
            return {k: v for k, v in value.items() if not k.startswith("_")}
        return value

    # --- Private helpers ---

    def _track_consumable_slots(self, packet: Packet) -> None:
        """Build cons_id → display_index mapping from setConsumables pickle.

        The pickle contains {'consumablesDict': [(cons_id, (...))]}.
        The list position in consumablesDict = display index for rendering.
        cons_id = game internal consumable type ID used in onConsumableUsed.

        Note: the pickle ordering does NOT match GameParams AbilitySlot ordering.
        We use the pickle ordering as the authoritative display order.
        """
        args = packet.method_args
        if not args:
            return
        data = args.get("arg0")
        if isinstance(data, bytes):
            # Legacy path: raw bytes (pre-auto-pickle)
            import pickle as _pickle
            try:
                data = _pickle.loads(data, encoding="latin-1")
            except Exception:
                return
        if not isinstance(data, dict):
            return
        cons_list = data.get("consumablesDict")
        if not isinstance(cons_list, list):
            return

        mapping: dict[int, int] = {}
        for display_idx, entry in enumerate(cons_list):
            if isinstance(entry, (list, tuple)) and len(entry) >= 1:
                cons_id = entry[0]
                if isinstance(cons_id, int):
                    mapping[cons_id] = display_idx

        if mapping:
            self._consumable_id_to_slot[packet.entity_id] = mapping

    def _track_consumable_used(self, packet: Packet) -> None:
        """Track consumable activation from onConsumableUsed.

        Args in method_args:
            consumableUsageParams: BLOB — usage_type(u8) + consumable_id(u8)
            workTimeLeft: FLOAT32 — duration in seconds
        """
        args = packet.method_args
        if not args:
            return

        # Get the consumable param (may be decoded dict or raw bytes)
        params = args.get("consumableUsageParams") or args.get("arg0", b"")
        duration = args.get("workTimeLeft") or args.get("arg1", 0.0)

        if isinstance(params, dict) and "consumable_id" in params:
            consumable_id = params["consumable_id"]
        elif isinstance(params, bytes) and len(params) >= 2:
            consumable_id = params[1]  # Legacy: second byte = consumable slot/type
        else:
            return

        if isinstance(duration, (int, float)) and 0.0 <= duration <= 300.0:
            self._consumable_activations.setdefault(
                packet.entity_id, [],
            ).append((packet.timestamp, consumable_id, float(duration)))

    def _process_minimap_vision(self, packet: Packet) -> None:
        """Process updateMinimapVisionInfo method call (Trap 5/6).

        Decodes packed bitfield per vehicle and stores minimap position data.
        """
        args = packet.method_args or {}
        # updateMinimapVisionInfo has two MINIMAPINFO args (ally + enemy vision)
        all_entries: list = []
        for arg_key in ("arg0", "arg1"):
            entries = args.get(arg_key, [])
            if isinstance(entries, dict):
                entries = [entries]
            if isinstance(entries, list):
                all_entries.extend(entries)
        if not all_entries:
            return

        for entry in all_entries:
            if not isinstance(entry, dict):
                continue
            vehicle_id = entry.get("vehicleID", 0)
            packed = int(entry.get("packedData", 0))

            raw_x = packed & 0x7FF
            raw_y = (packed >> 11) & 0x7FF
            raw_heading = (packed >> 22) & 0xFF
            is_disappearing = bool(packed & (1 << 31))

            # Sentinel check
            is_visible = not (raw_x == 0 and raw_y == 0)

            # Heading: 8-bit → radians
            heading_deg = raw_heading / 256.0 * 360.0 - 180.0
            heading_rad = math.radians(heading_deg)

            # Position: raw → world (Trap 6 formula)
            world_x = raw_x / 2047.0 * 5000.0 - 2500.0 if is_visible else 0.0
            world_z = raw_y / 2047.0 * 5000.0 - 2500.0 if is_visible else 0.0

            mm_entry = (
                packet.timestamp, world_x, world_z,
                heading_rad, is_visible, is_disappearing,
            )
            self._minimap_positions.setdefault(vehicle_id, []).append(mm_entry)

    def _cache_death_position(self, entity_id: int, timestamp: float) -> None:
        """Cache the last known position and yaw at time of death (Trap 13)."""
        if entity_id in self._death_positions:
            return  # Already cached (e.g., both receiveVehicleDeath and kill)

        pos = self.position_at(entity_id, timestamp)
        if pos is None:
            return

        # Get yaw
        yaw = 0.0
        positions = self._positions.get(entity_id)
        if positions:
            timestamps = [p[0] for p in positions]
            idx = bisect_right(timestamps, timestamp)
            if idx > 0:
                yaw = positions[idx - 1][2]

        self._death_positions[entity_id] = (pos, yaw)

    def _rebuild_state_at(self, t: float) -> dict[int, dict[str, Any]]:
        """Rebuild entity property state at time t from snapshots + history.

        Uses bisect on the timestamp index to slice only the relevant
        portion of history, avoiding a full linear scan.
        """
        # Find nearest snapshot at or before t
        snapshot_state: dict[int, dict[str, Any]] = {}
        snapshot_time = -1.0

        if self._snapshots:
            snapshot_times = [s[0] for s in self._snapshots]
            idx = bisect_right(snapshot_times, t)
            if idx > 0:
                snapshot_time, snapshot_data = self._snapshots[idx - 1]
                # Shallow copy: copy outer dicts, not property values
                snapshot_state = {
                    eid: dict(props)
                    for eid, props in snapshot_data.items()
                }

        # Use bisect to find the slice of history between snapshot and t.
        # The snapshot is taken BEFORE processing the packet at snapshot_time,
        # so all history entries at snapshot_time are NOT in the snapshot.
        # bisect_left includes them.
        lo = bisect_left(self._history_timestamps, snapshot_time)
        hi = bisect_right(self._history_timestamps, t)

        for change in self._history[lo:hi]:
            entity_props = snapshot_state.setdefault(
                change.entity_id, {},
            )
            entity_props[change.property_name] = change.new_value

        return snapshot_state

    def _build_ship_state(
        self, entity_id: int, props: dict[str, Any], t: float
    ) -> ShipState:
        """Build a ShipState from raw property dict."""
        is_alive = bool(props.get("isAlive", True))

        # Minimap vision data (Trap 5/6)
        minimap_x, minimap_z, minimap_heading, is_detected = 0.0, 0.0, 0.0, False
        mm = self.minimap_at(entity_id, t)
        if mm is not None:
            minimap_x, minimap_z, minimap_heading, is_detected = mm

        # Trap 13: use death position for dead ships
        if not is_alive and entity_id in self._death_positions:
            death_pos, death_yaw = self._death_positions[entity_id]
            pos = death_pos
            yaw = death_yaw
        else:
            world_pos = self.position_at(entity_id, t)
            if world_pos is not None:
                pos = world_pos
                yaw = 0.0
                positions = self._positions.get(entity_id)
                if positions:
                    timestamps = [p[0] for p in positions]
                    idx = bisect_right(timestamps, t)
                    if idx > 0:
                        yaw = positions[idx - 1][2]

                # Check if world position is stale — use minimap if newer
                if positions and mm is not None:
                    last_pos_t = positions[min(idx, len(positions)) - 1][0] if idx > 0 else 0.0
                    mm_entries = self._minimap_positions.get(entity_id, [])
                    mm_ts = [e[0] for e in mm_entries]
                    mm_idx = bisect_right(mm_ts, t)
                    last_mm_t = mm_entries[mm_idx - 1][0] if mm_idx > 0 else 0.0
                    if last_mm_t > last_pos_t + 2.0 and (minimap_x != 0.0 or minimap_z != 0.0):
                        pos = (minimap_x, 0.0, minimap_z)
                        yaw = minimap_heading
            elif mm is not None and (minimap_x != 0.0 or minimap_z != 0.0):
                # No world position — use minimap position
                pos = (minimap_x, 0.0, minimap_z)
                yaw = minimap_heading
            else:
                pos = (0.0, 0.0, 0.0)
                yaw = 0.0

        # Death position for the state model
        death_pos_val = self._death_positions.get(entity_id)
        death_position = death_pos_val[0] if death_pos_val else None

        return ShipState(
            entity_id=entity_id,
            health=float(props.get("health", 0)),
            max_health=float(props.get("maxHealth", 0)),
            regeneration_health=float(props.get("regenerationHealth", 0)),
            regenerated_health=float(props.get("regeneratedHealth", 0)),
            is_alive=is_alive,
            team_id=int(props.get("teamId", 0)),
            visibility_flags=int(props.get("visibilityFlags", 0)),
            burning_flags=int(props.get("burningFlags", 0)),
            position=pos,
            yaw=yaw,
            speed=float(props.get("serverSpeedRaw", 0)),
            minimap_x=minimap_x,
            minimap_z=minimap_z,
            minimap_heading=minimap_heading,
            is_detected=is_detected,
            death_position=death_position,
            is_on_forsage=bool(props.get("isOnForsage", False)),
            engine_power=int(props.get("enginePower", 0)),
            engine_dir=int(props.get("engineDir", 0)),
            speed_sign_dir=int(props.get("speedSignDir", 0)),
            max_speed=float(props.get("maxServerSpeedRaw", 0)),
            rudder_angle=float(props.get("ruddersAngle", 0)),
            deep_rudder_angle=float(props.get("deepRuddersAngle", 0)),
            selected_weapon=int(props.get("selectedWeapon", 0)),
            is_invisible=bool(props.get("isInvisible", False)),
            has_active_squadron=bool(props.get("hasActiveMainSquadron", False)),
            is_in_rage_mode=bool(props.get("isInRageMode", False)),
            respawn_time=float(props.get("respawnTime", 0)),
            blocked_controls=int(props.get("blockedControls", 0)),
            oil_leak_state=int(props.get("oilLeakState", 0)),
            owner=int(props.get("owner", 0)),
            regen_crew_hp_limit=float(props.get("regenCrewHpLimit", 0)),
            buoyancy=float(props.get("buoyancy", 0)),
            air_defense_disp_radius=float(props.get("airDefenseDispRadius", 0)),
            weapon_lock_flags=int(props.get("weaponLockFlags", 0)),
            target_local_pos=int(props.get("targetLocalPos", 0)),
            torpedo_local_pos=int(props.get("torpedoLocalPos", 0)),
        )

    @staticmethod
    def _snapshot_props(props: dict[str, Any]) -> dict[str, Any]:
        """Deep-copy mutable property values for snapshot isolation.

        Applies _snapshot_value to dicts/lists (which may be mutated
        in-place by NESTED_PROPERTY) while leaving primitives as-is.
        """
        return {
            k: GameStateTracker._snapshot_value(v)
            if isinstance(v, (dict, list)) else v
            for k, v in props.items()
        }

    @staticmethod
    def _snapshot_value(value: Any) -> Any:
        """Create a plain-dict snapshot of a value for history recording.

        construct Containers are dict subclasses with a _io (BytesIO)
        attribute that cannot be deepcopied. We recursively convert to
        plain dicts, skipping private keys like '_io'.
        """
        if isinstance(value, dict):
            return {
                k: GameStateTracker._snapshot_value(v)
                for k, v in value.items()
                if not k.startswith("_")
            }
        if isinstance(value, list):
            return [GameStateTracker._snapshot_value(v) for v in value]
        return value

    def _build_capture_points(
        self, all_state: dict[int, dict[str, Any]],
    ) -> list[CapturePointState]:
        """Build capture point states from InteractiveZone entities."""
        cap_points: list[CapturePointState] = []
        for entity_id, props in all_state.items():
            if self._entity_types.get(entity_id) != "InteractiveZone":
                continue
            cs_raw = props.get("componentsState", {})
            cap_logic = _container_get(cs_raw, "captureLogic") or {}
            ctrl_point = _container_get(cs_raw, "controlPoint") or {}

            cap_points.append(CapturePointState(
                entity_id=entity_id,
                radius=float(props.get("radius", 0)),
                team_id=int(props.get("teamId", 0)),
                progress=float(_container_get(cap_logic, "progress", 0)),
                capture_speed=float(_container_get(cap_logic, "captureSpeed", 0)),
                invader_team=int(_container_get(cap_logic, "invaderTeam", 0)),
                has_invaders=bool(_container_get(cap_logic, "hasInvaders", False)),
                both_inside=bool(_container_get(cap_logic, "bothInside", False)),
                is_enabled=bool(_container_get(cap_logic, "isEnabled", False)),
                point_type=int(_container_get(ctrl_point, "type", 0)),
                point_index=int(_container_get(ctrl_point, "index", -1)),
            ))
        return cap_points

    def _build_smoke_screens(
        self, all_state: dict[int, dict[str, Any]], t: float,
    ) -> dict[int, SmokeScreenState]:
        """Build smoke screen states from SmokeScreen entities."""
        result: dict[int, SmokeScreenState] = {}
        for entity_id, props in all_state.items():
            if self._entity_types.get(entity_id) != "SmokeScreen":
                continue
            pos_data = self.position_at(entity_id, t)
            position = pos_data if pos_data else (0.0, 0.0, 0.0)

            raw_points = props.get("points", [])
            points: list[tuple[float, float, float]] = []
            if isinstance(raw_points, list):
                for p in raw_points:
                    if isinstance(p, (list, tuple)) and len(p) >= 3:
                        points.append((float(p[0]), float(p[1]), float(p[2])))
                    else:
                        x = float(_container_get(p, "x", 0))
                        y = float(_container_get(p, "y", 0))
                        z = float(_container_get(p, "z", 0))
                        points.append((x, y, z))

            result[entity_id] = SmokeScreenState(
                entity_id=entity_id,
                radius=float(props.get("radius", 0)),
                height=float(props.get("height", 0)),
                bc_radius=float(props.get("bcRadius", 0)),
                active_point_index=int(props.get("activePointIndex", -1)),
                points=points,
                position=position,
            )
        return result

    def _build_buildings(
        self, all_state: dict[int, dict[str, Any]], t: float,
    ) -> dict[int, BuildingState]:
        """Build building states from Building entities."""
        result: dict[int, BuildingState] = {}
        for entity_id, props in all_state.items():
            if self._entity_types.get(entity_id) != "Building":
                continue
            pos_data = self.position_at(entity_id, t)
            position = pos_data if pos_data else (0.0, 0.0, 0.0)

            result[entity_id] = BuildingState(
                entity_id=entity_id,
                params_id=int(props.get("paramsId", 0)),
                team_id=int(props.get("teamId", 0)),
                is_alive=bool(props.get("isAlive", True)),
                is_suppressed=bool(props.get("isSuppressed", False)),
                position=position,
            )
        return result

    def _build_battle_state(
        self, bl_props: dict[str, Any], all_state: dict[int, dict[str, Any]]
    ) -> BattleState:
        """Build BattleState from BattleLogic properties."""
        # Build capture point states from InteractiveZone entities
        cap_points = self._build_capture_points(all_state)

        battle_result = bl_props.get("battleResult")
        winner = -1
        reason = 0
        if isinstance(battle_result, dict):
            winner = battle_result.get("winnerTeamId", -1)
            reason = battle_result.get("finishReason", 0)

        # Extract scoring config + live scores from BattleLogic.state.missions.
        # The live team scores are in state.missions.teamsScore[N].score,
        # updated via nested property packets throughout the match.
        # NB: bl_props["teams"][N].state is the INITIAL default (always 2),
        # NOT the live score — don't use it.
        team_scores: dict[int, int] = {}
        team_win_score = 1000
        team_start_scores: dict[int, int] = {}
        kill_scoring: list[KillScoring] = []
        hold_scoring: list[HoldScoring] = []

        bl_state = bl_props.get("state")
        if bl_state is not None:
            missions = _container_get(bl_state, "missions")
            if missions is not None:
                team_win_score = int(_container_get(missions, "teamWinScore", 1000))

                # teamsScore: live score per team (updated in-place by nested property)
                for entry in _container_get(missions, "teamsScore", []):
                    tid = _container_get(entry, "teamId")
                    score = _container_get(entry, "score")
                    if tid is not None and score is not None:
                        team_scores[int(tid)] = int(score)
                        team_start_scores[int(tid)] = int(score)

                # kill scoring config
                for entry in _container_get(missions, "kill", []):
                    kill_scoring.append(KillScoring(
                        ship_type=str(_container_get(entry, "shipType", "")),
                        reward=int(_container_get(entry, "reward", 0)),
                        penalty=int(_container_get(entry, "penalty", 0)),
                    ))

                # hold scoring config
                for entry in _container_get(missions, "hold", []):
                    hold_scoring.append(HoldScoring(
                        reward=int(_container_get(entry, "reward", 0)),
                        period=int(_container_get(entry, "period", 5)),
                        cp_indices=list(_container_get(entry, "cpIndices", [])),
                    ))

        return BattleState(
            battle_stage=int(bl_props.get("battleStage", 0)),
            time_left=int(bl_props.get("timeLeft", 0)),
            team_scores=team_scores,
            capture_points=cap_points,
            battle_result_winner=winner,
            battle_result_reason=reason,
            team_win_score=team_win_score,
            team_start_scores=team_start_scores,
            kill_scoring=kill_scoring,
            hold_scoring=hold_scoring,
            battle_type=int(bl_props.get("battleType", 0)),
            duration=int(bl_props.get("duration", 0)),
            map_border=bl_props.get("mapBorder"),
        )

    @staticmethod
    def _get_arg(args: dict[str, Any] | None, index: int) -> Any:
        """Get argument by index from method_args dict.

        The schema builder names positional args as "arg0", "arg1", etc.
        Named args keep their original names from the .def file.
        """
        if args is None:
            return None
        # Try "argN" convention first (schema builder output)
        arg_key = f"arg{index}"
        if arg_key in args:
            return args[arg_key]
        # Try raw numeric string key
        key = str(index)
        if key in args:
            return args[key]
        # Fall back to positional by dict order
        keys = list(args.keys())
        if index < len(keys):
            return args[keys[index]]
        return None

    def _aircraft_latest(self, plane_id: int) -> AircraftState | None:
        """Return the latest known state for a plane_id, or None if removed."""
        for _, pid, state in reversed(self._aircraft_log):
            if pid == plane_id:
                return state  # None means removed
        return None

    def _build_aircraft_at(self, t: float) -> dict[int, AircraftState]:
        """Rebuild aircraft dict up to timestamp t."""
        result: dict[int, AircraftState] = {}
        for ts, plane_id, state in self._aircraft_log:
            if ts > t:
                break
            if state is None:
                result.pop(plane_id, None)
            else:
                result[plane_id] = state
        return result
