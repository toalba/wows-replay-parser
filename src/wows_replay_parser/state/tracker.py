from __future__ import annotations

import copy
import math
from bisect import bisect_right
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator

from wows_replay_parser.packets.types import Packet, PacketType

from .models import (
    BattleState,
    CapturePointState,
    GameState,
    PropertyChange,
    ShipState,
)

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

    def process_packet(self, packet: Packet) -> list[PropertyChange]:
        """Process a decoded packet, updating internal state.
        Returns list of PropertyChange objects for any state changes."""
        changes: list[PropertyChange] = []

        ptype = packet.type

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

        # Property update
        elif ptype == PacketType.ENTITY_PROPERTY:
            if packet.property_name:
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
                    new_value=packet.property_value,
                )
                self._history.append(change)
                self._history_timestamps.append(change.timestamp)
                changes.append(change)

        # Position update
        elif ptype == PacketType.POSITION:
            if packet.position and packet.entity_id:
                yaw = 0.0
                # direction field is being added by Agent 1C — safe fallback
                direction: tuple[float, float, float] | None = getattr(packet, "direction", None)
                if direction is not None:
                    dx, _dy, dz = direction
                    yaw = math.atan2(dx, dz)
                entry = (packet.timestamp, packet.position, yaw)
                self._positions.setdefault(packet.entity_id, []).append(entry)

        # Method call — watch for deaths
        elif ptype == PacketType.ENTITY_METHOD:
            if packet.method_name == "receiveVehicleDeath" and packet.method_args:
                # Args: (victim_id, killer_id, reason)
                victim_id = self._get_arg(packet.method_args, 0)
                if victim_id is not None:
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

        # Periodic snapshots
        if packet.timestamp - self._last_snapshot_time >= _SNAPSHOT_INTERVAL:
            self._snapshots.append((packet.timestamp, copy.deepcopy(self._current)))
            self._last_snapshot_time = packet.timestamp

        return changes

    def state_at(self, t: float) -> GameState:
        """Reconstruct full game state at timestamp t."""
        state = self._rebuild_state_at(t)

        ships: dict[int, ShipState] = {}
        battle = BattleState()

        for entity_id, props in state.items():
            entity_type = self._entity_types.get(entity_id, "")

            if entity_type == "Vehicle":
                # Only include ships that have received position data
                if self.position_at(entity_id, t) is None:
                    continue
                ship = self._build_ship_state(entity_id, props, t)
                ships[entity_id] = ship

            elif entity_type == "BattleLogic":
                battle = self._build_battle_state(props, state)

        return GameState(timestamp=t, ships=ships, battle=battle)

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
        running: dict[int, dict[str, Any]] = {}
        history_idx = 0

        # Per-entity position cursors: entity_id → index into
        # self._positions[entity_id]
        pos_cursors: dict[int, int] = {}
        # Cached last-known position + yaw per entity
        pos_cache: dict[int, tuple[tuple[float, float, float], float]] = {}

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

            # Build GameState using cached positions
            ships: dict[int, ShipState] = {}
            battle = BattleState()
            for entity_id, props in running.items():
                etype = self._entity_types.get(entity_id, "")
                if etype == "Vehicle":
                    cached = pos_cache.get(entity_id)
                    if cached is None:
                        continue  # not yet spotted
                    pos = cached[0]
                    yaw = cached[1]
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
                        is_alive=bool(props.get("isAlive", True)),
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
                    )
                elif etype == "BattleLogic":
                    battle = self._build_battle_state(
                        props, running,
                    )
            yield GameState(
                timestamp=t, ships=ships, battle=battle,
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
            if self._entity_types.get(entity_id) == "BattleLogic":
                return self._build_battle_state(props, state)
        return BattleState()

    def position_at(self, entity_id: int, t: float) -> tuple[float, float, float] | None:
        """Interpolate position for entity at time t."""
        positions = self._positions.get(entity_id)
        if not positions:
            return None

        timestamps = [p[0] for p in positions]
        idx = bisect_right(timestamps, t)

        if idx == 0:
            return positions[0][1]
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

    # --- Private helpers ---

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

        # Use bisect to find the slice of history between snapshot and t
        lo = bisect_right(self._history_timestamps, snapshot_time)
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
        pos = self.position_at(entity_id, t) or (0.0, 0.0, 0.0)

        # Get yaw from position history
        yaw = 0.0
        positions = self._positions.get(entity_id)
        if positions:
            timestamps = [p[0] for p in positions]
            idx = bisect_right(timestamps, t)
            if idx > 0:
                yaw = positions[idx - 1][2]

        return ShipState(
            entity_id=entity_id,
            health=float(props.get("health", 0)),
            max_health=float(props.get("maxHealth", 0)),
            regeneration_health=float(props.get("regenerationHealth", 0)),
            regenerated_health=float(props.get("regeneratedHealth", 0)),
            is_alive=bool(props.get("isAlive", True)),
            team_id=int(props.get("teamId", 0)),
            visibility_flags=int(props.get("visibilityFlags", 0)),
            burning_flags=int(props.get("burningFlags", 0)),
            position=pos,
            yaw=yaw,
            speed=float(props.get("serverSpeedRaw", 0)),
        )

    def _build_battle_state(
        self, bl_props: dict[str, Any], all_state: dict[int, dict[str, Any]]
    ) -> BattleState:
        """Build BattleState from BattleLogic properties."""
        teams_raw = bl_props.get("teams")
        team_scores: dict[int, int] = {}
        if isinstance(teams_raw, dict):
            for team_entry in teams_raw.get("teams", []):
                if isinstance(team_entry, dict):
                    tid = team_entry.get("teamId", 0)
                    team_scores[tid] = team_entry.get("state", 0)

        # Build capture point states from InteractiveZone entities
        cap_points: list[CapturePointState] = []
        for entity_id, props in all_state.items():
            if self._entity_types.get(entity_id) == "InteractiveZone":
                cs_raw = props.get("componentsState", {})
                cap_logic: dict[str, Any] = {}
                ctrl_point: dict[str, Any] = {}
                if isinstance(cs_raw, dict):
                    cap_logic = cs_raw.get("captureLogic") or {}
                    ctrl_point = cs_raw.get("controlPoint") or {}

                cap_points.append(CapturePointState(
                    entity_id=entity_id,
                    radius=float(props.get("radius", 0)),
                    team_id=int(props.get("teamId", 0)),
                    capture_points=(
                        int(cap_logic.get("capturePoints", 0))
                        if isinstance(cap_logic, dict) else 0
                    ),
                    capture_speed=(
                        float(cap_logic.get("captureSpeed", 0))
                        if isinstance(cap_logic, dict) else 0
                    ),
                    owner_id=(
                        int(cap_logic.get("ownerId", 0))
                        if isinstance(cap_logic, dict) else 0
                    ),
                    control_team_id=(
                        int(ctrl_point.get("teamId", 0))
                        if isinstance(ctrl_point, dict) else 0
                    ),
                ))

        battle_result = bl_props.get("battleResult")
        winner = -1
        reason = 0
        if isinstance(battle_result, dict):
            winner = battle_result.get("winnerTeamId", -1)
            reason = battle_result.get("finishReason", 0)

        return BattleState(
            battle_stage=int(bl_props.get("battleStage", 0)),
            time_left=int(bl_props.get("timeLeft", 0)),
            team_scores=team_scores,
            capture_points=cap_points,
            battle_result_winner=winner,
            battle_result_reason=reason,
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
