"""Dual perspective replay merging.

Merges two replays from the same match (one from each team) into
a unified view where all ships from both teams are visible.

``MergedReplay`` is a first-class :class:`ReplaySource` implementation:
the renderer can consume it identically to a single
:class:`~wows_replay_parser.api.ParsedReplay`.

Id-offset scheme
----------------
``replay_a`` entity ids pass through unchanged. For ``replay_b`` entity
ids the policy depends on whether the id already appears in ``replay_a``:

* **Mapped via** :attr:`entity_mapping` (known players present in both
  replays) — remapped to the ``replay_a`` id. A single ship has exactly
  one id in the merged view.
* **Shared raw id also present in** ``replay_a`` — kept as the same id.
  For server-authoritative entity types (smoke screens, weather zones,
  buildings, aircraft, buff zones) both client replays observe the same
  server-assigned eid, so an overlap means the SAME entity. Merging by
  equal id deduplicates; the richer snapshot wins via
  :func:`_prefer_richer`.
* **Otherwise (truly disjoint)** — the id is virtualized by adding
  :data:`B_ID_OFFSET` (``2**30``) to keep it in a disjoint integer range
  as a safety net against accidental collisions.

This applies uniformly to :meth:`MergedReplay.state_at` /
:meth:`iter_states` and to all cached auxiliary maps
(``first_seen``, ``smoke_screen_lifetimes``, ``zone_lifetimes``,
``aim_yaw_timeline``, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property
from typing import TYPE_CHECKING, TypeVar
import logging
import warnings

from wows_replay_parser.interfaces import ReplaySource
from wows_replay_parser.state.models import (
    BattleState,
    CapturePointState,
    GameState,
)

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from wows_replay_parser.api import ParsedReplay
    from wows_replay_parser.events.models import GameEvent
    from wows_replay_parser.roster import PlayerInfo
    from wows_replay_parser.state.models import (
        AircraftState,
        BuffZoneState,
        BuildingState,
        ShipState,
        SmokeScreenState,
        WeatherZoneState,
    )


_log = logging.getLogger(__name__)

_T = TypeVar("_T")

#: Fixed sentinel offset applied to unmapped replay_b entity ids to keep
#: them in a disjoint range from replay_a ids. ``2**30`` leaves plenty of
#: headroom below ``2**31`` (signed int32 max) and well above any real
#: BigWorld entity id we've observed.
B_ID_OFFSET: int = 1 << 30


def _ship_richness(ship: ShipState) -> tuple[int, float]:
    """Return a (flags, health) sort key — higher = richer data.

    ``max_health > 0`` is the single strongest "I actually know this
    ship" signal; beyond that we prefer the snapshot that sees more
    secondary info (turret yaws, battery dict, visible position).
    """
    flags = 0
    if ship.max_health > 0:
        flags |= 1 << 4
    if ship.position != (0.0, 0.0, 0.0):
        flags |= 1 << 3
    if ship.turret_yaws:
        flags |= 1 << 2
    if ship.battery is not None:
        flags |= 1 << 1
    if ship.is_detected:
        flags |= 1
    return (flags, ship.health)


def _prefer_richer(a: _T | None, b: _T | None, *, score) -> _T | None:
    """Pick the entity with higher ``score``; ``None`` loses."""
    if a is None:
        return b
    if b is None:
        return a
    return b if score(b) > score(a) else a


def _smoke_richness(s: SmokeScreenState) -> tuple[int, int]:
    pts = len(s.points) if s.points else 0
    has_radius = 1 if s.radius > 0 else 0
    return (has_radius, pts)


def _building_richness(b: BuildingState) -> tuple[int, int, int]:
    return (
        1 if b.position != (0.0, 0.0, 0.0) else 0,
        b.params_id,
        b.team_id,
    )


def _weather_richness(w: WeatherZoneState) -> tuple[int, float, int]:
    return (
        1 if w.position != (0.0, 0.0, 0.0) else 0,
        w.radius,
        w.params_id,
    )


def _buff_richness(z: BuffZoneState) -> tuple[int, float, int]:
    return (
        1 if z.position != (0.0, 0.0, 0.0) else 0,
        z.radius,
        z.params_id,
    )


def _aircraft_richness(a: AircraftState) -> tuple[int, int, int]:
    return (
        1 if (a.x != 0.0 or a.z != 0.0) else 0,
        a.num_planes,
        a.params_id,
    )


def _cap_richness(c: CapturePointState) -> tuple[int, float, float]:
    """Prefer enabled caps; tiebreak on later progress / capture_time."""
    return (
        1 if c.is_enabled else 0,
        c.progress,
        c.capture_time,
    )


def _merge_sorted_unique(
    a: list[tuple[float, float]],
    b: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """Merge two ``(t, v)`` timelines keeping duplicates from both."""
    if not a:
        return list(b)
    if not b:
        return list(a)
    out: list[tuple[float, float]] = []
    i = j = 0
    while i < len(a) and j < len(b):
        if a[i][0] <= b[j][0]:
            out.append(a[i])
            i += 1
        else:
            out.append(b[j])
            j += 1
    out.extend(a[i:])
    out.extend(b[j:])
    return out


@dataclass
class MergedReplay:
    """Two replays from the same match merged for dual perspective.

    Implements :class:`~wows_replay_parser.interfaces.ReplaySource` so
    the renderer (or any consumer) can treat it identically to a plain
    :class:`~wows_replay_parser.api.ParsedReplay`.

    Merge strategy per :class:`GameState` field:

    * ``ships`` — union by player-entity mapping. For shared ships,
      prefer the replay whose ``owner_team`` matches the ship's team
      (the "owner" perspective; server data is authoritative when the
      ship is on your side). Tiebreak on :func:`_ship_richness`.
    * ``smoke_screens`` / ``weather_zones`` / ``buildings`` /
      ``aircraft`` / ``buff_zones`` — union by entity id. These are
      **server-authoritative**: if the same raw eid appears in both
      replays it is the SAME entity (both clients received it from the
      server). Shared eids are deduped via :func:`_prefer_richer`;
      truly disjoint ``replay_b`` eids are offset by
      :data:`B_ID_OFFSET` as a collision safety net.
    * ``battle.capture_points`` — union by ``point_index``, preferring
      ``is_enabled=True`` then later ``progress`` (see
      :func:`_cap_richness`).
    * ``battle`` scalar fields (scores, timer, winner, drop_state, map
      border, scoring config…) — ``replay_a`` is authoritative.
    """

    replay_a: ParsedReplay
    replay_b: ParsedReplay
    arena_unique_id: int
    entity_mapping: dict[int, int] = field(default_factory=dict)
    merged_events: list[GameEvent] = field(default_factory=list)
    b_id_offset: int = B_ID_OFFSET

    # ------------------------------------------------------------------
    # Id remapping helpers
    # ------------------------------------------------------------------
    def _remap_b_eid_server(self, eid_b: int) -> int:
        """Remap a ``replay_b`` eid for a **server-authoritative** entity.

        Server-authoritative entity ids (smoke screens, weather zones,
        buildings, aircraft, buff zones) are assigned by the server and
        are identical across both client replays: if the same raw id
        appears on both sides it is literally the same entity. Disjoint
        ids are distinct entities — there is no collision to guard
        against, so the offset does not apply here.

        * Mapped via :attr:`entity_mapping` → use ``replay_a`` id.
        * Otherwise → pass the raw id through unchanged.
        """
        mapped = self.entity_mapping.get(eid_b)
        if mapped is not None:
            return mapped
        return eid_b

    def _remap_b_eid(self, eid_b: int, a_keys: set[int] | None = None) -> int:
        """Return the merged-view eid for a ``replay_b`` entity id.

        * Mapped via :attr:`entity_mapping` → use ``replay_a`` id.
        * Same raw id also present in ``a_keys`` → treat as shared and
          keep the raw id (no offset). This covers auxiliary data
          (first_seen, smoke_screen_lifetimes, aim_yaw_timeline, …)
          where the two parsers may have independently assigned the
          same id to what is semantically the same entity (e.g. world
          entities with stable BigWorld ids).
        * Otherwise → add :attr:`b_id_offset` to keep it in a disjoint
          range and prevent accidental collision.
        """
        mapped = self.entity_mapping.get(eid_b)
        if mapped is not None:
            return mapped
        if a_keys is not None and eid_b in a_keys:
            return eid_b
        return eid_b + self.b_id_offset

    @staticmethod
    def _compute_owner_team(replay: ParsedReplay) -> int | None:
        """Team id of the recording player for ``replay``, or ``None``."""
        for p in replay.players:
            if getattr(p, "relation", None) == 0:
                return p.team_id
        return None

    @cached_property
    def _owner_team_a(self) -> int | None:
        return self._compute_owner_team(self.replay_a)

    @cached_property
    def _owner_team_b(self) -> int | None:
        return self._compute_owner_team(self.replay_b)

    # ------------------------------------------------------------------
    # ReplaySource: core metadata
    # ------------------------------------------------------------------
    @cached_property
    def map_name(self) -> str:
        return self.replay_a.map_name

    @cached_property
    def duration(self) -> float:
        return max(self.replay_a.duration, self.replay_b.duration)

    @cached_property
    def game_version(self) -> str:
        if self.replay_a.game_version != self.replay_b.game_version:
            warnings.warn(
                "Merging replays with different game_version: "
                f"{self.replay_a.game_version} vs {self.replay_b.game_version}",
                stacklevel=2,
            )
        return self.replay_a.game_version

    @cached_property
    def meta(self) -> dict:
        """replay_a's meta is authoritative (documented choice)."""
        return self.replay_a.meta

    @cached_property
    def players(self) -> list[PlayerInfo]:
        """Deduped union via :attr:`entity_mapping`.

        A player present in both replays appears once, preferring
        ``replay_a``'s :class:`PlayerInfo`.
        """
        seen_obj: set[int] = set()  # id(object) identity dedup
        seen_keys: set[tuple] = set()
        out: list[PlayerInfo] = []

        def _key(p: object) -> tuple:
            name = getattr(p, "name", None)
            ship_id = getattr(p, "ship_id", None)
            if name is not None and ship_id is not None:
                return ("player", name, ship_id)
            return ("id", id(p))

        for p in self.replay_a.players:
            k = _key(p)
            if k in seen_keys or id(p) in seen_obj:
                continue
            seen_keys.add(k)
            seen_obj.add(id(p))
            out.append(p)
        for p in self.replay_b.players:
            k = _key(p)
            if k in seen_keys or id(p) in seen_obj:
                continue
            seen_keys.add(k)
            seen_obj.add(id(p))
            out.append(p)
        return out

    @property
    def events(self) -> list[GameEvent]:
        return self.merged_events

    # ------------------------------------------------------------------
    # ReplaySource: event / state queries
    # ------------------------------------------------------------------
    def events_of_type(self, event_type: type[_T]) -> list[_T]:
        return [e for e in self.merged_events if isinstance(e, event_type)]

    def _merge_gamestate(
        self, state_a: GameState, state_b: GameState, t: float,
    ) -> GameState:
        """Core per-frame merger used by :meth:`state_at` and
        :meth:`iter_states`."""
        owner_a = self._owner_team_a
        owner_b = self._owner_team_b

        # ----- ships --------------------------------------------------
        # Ships merge only via entity_mapping (known players); raw-id
        # collisions on unmapped ships are offset like other entities.
        combined_ships: dict[int, ShipState] = dict(state_a.ships)
        for eid_b, ship_b in state_b.ships.items():
            merged_eid = self._remap_b_eid(eid_b)
            existing = combined_ships.get(merged_eid)
            if existing is None:
                combined_ships[merged_eid] = ship_b
                continue
            # Owner-perspective rule
            b_is_owner = owner_b is not None and ship_b.team_id == owner_b
            a_is_owner = owner_a is not None and existing.team_id == owner_a
            if b_is_owner and not a_is_owner:
                combined_ships[merged_eid] = ship_b
            elif a_is_owner and not b_is_owner:
                pass  # keep existing
            else:
                # Tiebreak on data richness
                if _ship_richness(ship_b) > _ship_richness(existing):
                    combined_ships[merged_eid] = ship_b

        # ----- smoke_screens -----------------------------------------
        # Server-authoritative: shared raw eids across replays ARE the
        # same entity (both clients see the same server-assigned id).
        # Use _remap_b_eid_server which preserves raw ids (no offset).
        combined_smoke: dict[int, SmokeScreenState] = dict(state_a.smoke_screens)
        for eid_b, s_b in state_b.smoke_screens.items():
            merged_eid = self._remap_b_eid_server(eid_b)
            ex = combined_smoke.get(merged_eid)
            chosen = _prefer_richer(ex, s_b, score=_smoke_richness)
            if chosen is not None:
                combined_smoke[merged_eid] = chosen

        # ----- weather_zones -----------------------------------------
        combined_weather: dict[int, WeatherZoneState] = dict(state_a.weather_zones)
        for eid_b, w_b in state_b.weather_zones.items():
            merged_eid = self._remap_b_eid_server(eid_b)
            ex = combined_weather.get(merged_eid)
            chosen = _prefer_richer(ex, w_b, score=_weather_richness)
            if chosen is not None:
                combined_weather[merged_eid] = chosen

        # ----- buildings ---------------------------------------------
        combined_bldgs: dict[int, BuildingState] = dict(state_a.buildings)
        for eid_b, b_b in state_b.buildings.items():
            merged_eid = self._remap_b_eid_server(eid_b)
            ex = combined_bldgs.get(merged_eid)
            chosen = _prefer_richer(ex, b_b, score=_building_richness)
            if chosen is not None:
                combined_bldgs[merged_eid] = chosen

        # ----- aircraft ----------------------------------------------
        combined_ac: dict[int, AircraftState] = dict(state_a.aircraft)
        for eid_b, a_b in state_b.aircraft.items():
            merged_eid = self._remap_b_eid_server(eid_b)
            ex = combined_ac.get(merged_eid)
            chosen = _prefer_richer(ex, a_b, score=_aircraft_richness)
            if chosen is not None:
                combined_ac[merged_eid] = chosen

        # ----- buff_zones --------------------------------------------
        combined_buff: dict[int, BuffZoneState] = dict(state_a.buff_zones)
        for eid_b, z_b in state_b.buff_zones.items():
            merged_eid = self._remap_b_eid_server(eid_b)
            ex = combined_buff.get(merged_eid)
            chosen = _prefer_richer(ex, z_b, score=_buff_richness)
            if chosen is not None:
                combined_buff[merged_eid] = chosen

        # ----- battle (scalars from replay_a, caps merged) -----------
        battle_a = state_a.battle
        battle_b = state_b.battle

        caps_by_index: dict[int, CapturePointState] = {}
        for c in battle_a.capture_points:
            caps_by_index[c.point_index] = c
        for c in battle_b.capture_points:
            idx = c.point_index
            ex = caps_by_index.get(idx)
            if ex is None:
                caps_by_index[idx] = c
            elif _cap_richness(c) > _cap_richness(ex):
                caps_by_index[idx] = c
        merged_caps = [
            caps_by_index[k] for k in sorted(caps_by_index.keys())
        ]

        merged_battle = BattleState(
            battle_stage=battle_a.battle_stage,
            time_left=battle_a.time_left,
            team_scores=dict(battle_a.team_scores),
            capture_points=merged_caps,
            battle_result_winner=battle_a.battle_result_winner,
            battle_result_reason=battle_a.battle_result_reason,
            team_win_score=battle_a.team_win_score,
            team_start_scores=dict(battle_a.team_start_scores),
            kill_scoring=list(battle_a.kill_scoring),
            hold_scoring=list(battle_a.hold_scoring),
            battle_type=battle_a.battle_type,
            duration=battle_a.duration,
            map_border=battle_a.map_border,
            drop_state=battle_a.drop_state,
        )

        return GameState(
            timestamp=t,
            ships=combined_ships,
            battle=merged_battle,
            aircraft=combined_ac,
            smoke_screens=combined_smoke,
            buildings=combined_bldgs,
            weather_zones=combined_weather,
            buff_zones=combined_buff,
        )

    def state_at(self, t: float) -> GameState:
        """Get combined game state from both perspectives."""
        state_a = self.replay_a.state_at(t)
        state_b = self.replay_b.state_at(t)
        return self._merge_gamestate(state_a, state_b, t)

    def iter_states(
        self, timestamps: Sequence[float],
    ) -> Iterator[GameState]:
        """Yield merged :class:`GameState` for each timestamp.

        Advances both underlying trackers in lockstep. The tracker's
        own ``iter_states`` yields a result for every input timestamp
        (past-end-of-replay returns the last known state), so this
        works even when the two replays have different durations.
        """
        ts = list(timestamps)
        if not ts:
            return
        it_a = self.replay_a.iter_states(ts)
        it_b = self.replay_b.iter_states(ts)
        for t, state_a, state_b in zip(ts, it_a, it_b):
            yield self._merge_gamestate(state_a, state_b, t)

    # ------------------------------------------------------------------
    # ReplaySource: precomputed helpers
    # ------------------------------------------------------------------
    @cached_property
    def battle_start_time(self) -> float | None:
        a = self.replay_a.battle_start_time
        b = self.replay_b.battle_start_time
        if a is None:
            return b
        if b is None:
            return a
        return min(a, b)

    @cached_property
    def first_seen(self) -> dict[int, float]:
        """Per-entity earliest first-seen across both perspectives.

        Unmatched ``replay_b`` entities are id-offset.
        """
        out: dict[int, float] = dict(self.replay_a.first_seen)
        a_keys = set(self.replay_a.first_seen.keys())
        for eid_b, t_b in self.replay_b.first_seen.items():
            merged_eid = self._remap_b_eid(eid_b, a_keys)
            ex = out.get(merged_eid)
            if ex is None or t_b < ex:
                out[merged_eid] = t_b
        return out

    @cached_property
    def aim_yaw_timeline(self) -> dict[int, list[tuple[float, float]]]:
        """Per-entity union of aim-yaw timelines (merged + sorted)."""
        out: dict[int, list[tuple[float, float]]] = {
            eid: list(tl) for eid, tl in self.replay_a.aim_yaw_timeline.items()
        }
        a_keys = set(self.replay_a.aim_yaw_timeline.keys())
        for eid_b, tl_b in self.replay_b.aim_yaw_timeline.items():
            merged_eid = self._remap_b_eid(eid_b, a_keys)
            if merged_eid in out:
                out[merged_eid] = _merge_sorted_unique(out[merged_eid], list(tl_b))
            else:
                out[merged_eid] = list(tl_b)
        return out

    @cached_property
    def camera_yaw_timeline(self) -> None:
        """Dual render has no self camera — always ``None``."""
        return None

    @cached_property
    def smoke_screen_lifetimes(self) -> dict[int, tuple[float, float]]:
        out: dict[int, tuple[float, float]] = dict(
            self.replay_a.smoke_screen_lifetimes,
        )
        # Smoke is server-authoritative: shared raw eids are the same entity.
        for eid_b, (spawn_b, leave_b) in self.replay_b.smoke_screen_lifetimes.items():
            merged_eid = self._remap_b_eid_server(eid_b)
            ex = out.get(merged_eid)
            if ex is None:
                out[merged_eid] = (spawn_b, leave_b)
            else:
                out[merged_eid] = (min(ex[0], spawn_b), max(ex[1], leave_b))
        return out

    @cached_property
    def zone_positions(self) -> dict[int, list[tuple[float, float, float]]]:
        out: dict[int, list[tuple[float, float, float]]] = {
            eid: list(v) for eid, v in self.replay_a.zone_positions.items()
        }
        # Zones are server-authoritative: shared raw eids are the same entity.
        for eid_b, samples in self.replay_b.zone_positions.items():
            merged_eid = self._remap_b_eid_server(eid_b)
            if merged_eid in out:
                # Merge sorted-by-t (samples are (t, x, z))
                merged = sorted(out[merged_eid] + list(samples), key=lambda s: s[0])
                out[merged_eid] = merged
            else:
                out[merged_eid] = list(samples)
        return out

    @cached_property
    def zone_lifetimes(self) -> dict[int, tuple[float, float]]:
        out: dict[int, tuple[float, float]] = dict(self.replay_a.zone_lifetimes)
        # Zones are server-authoritative: shared raw eids are the same entity.
        for eid_b, (spawn_b, leave_b) in self.replay_b.zone_lifetimes.items():
            merged_eid = self._remap_b_eid_server(eid_b)
            ex = out.get(merged_eid)
            if ex is None:
                out[merged_eid] = (spawn_b, leave_b)
            else:
                out[merged_eid] = (min(ex[0], spawn_b), max(ex[1], leave_b))
        return out

    @cached_property
    def consumable_activations(
        self,
    ) -> dict[int, list[tuple[float, int, float]]]:
        out: dict[int, list[tuple[float, int, float]]] = {
            eid: list(v) for eid, v in self.replay_a.consumable_activations.items()
        }
        a_keys = set(self.replay_a.consumable_activations.keys())
        for eid_b, acts in self.replay_b.consumable_activations.items():
            merged_eid = self._remap_b_eid(eid_b, a_keys)
            if merged_eid in out:
                merged = sorted(out[merged_eid] + list(acts), key=lambda a: a[0])
                out[merged_eid] = merged
            else:
                out[merged_eid] = list(acts)
        return out

    @cached_property
    def crew_modifiers(self) -> dict[int, object]:
        out: dict[int, object] = dict(self.replay_a.crew_modifiers)
        a_keys = set(self.replay_a.crew_modifiers.keys())
        for eid_b, val in self.replay_b.crew_modifiers.items():
            merged_eid = self._remap_b_eid(eid_b, a_keys)
            if merged_eid not in out:  # replay_a preference
                out[merged_eid] = val
        return out


def match_entities(
    replay_a: ParsedReplay,
    replay_b: ParsedReplay,
) -> dict[int, int]:
    """Map entity IDs between two replays of the same match.

    Uses player name + ship ID from JSON headers to correlate
    entities across replays.

    Returns:
        Mapping of replay_b entity_id -> replay_a entity_id.
    """
    mapping: dict[int, int] = {}

    # Build lookup: (name, ship_id) -> entity_id for replay A
    a_lookup: dict[tuple[str, int], int] = {}
    for player in replay_a.players:
        eid = getattr(player, "entity_id", 0)
        if eid:
            a_lookup[(player.name, player.ship_id)] = eid

    # Match replay B players to replay A
    for player in replay_b.players:
        eid = getattr(player, "entity_id", 0)
        if eid:
            key = (player.name, player.ship_id)
            eid_a = a_lookup.get(key)
            if eid_a is not None:
                mapping[eid] = eid_a

    return mapping


def merge_replays(
    replay_a: ParsedReplay,
    replay_b: ParsedReplay,
) -> MergedReplay:
    """Merge two replays from the same match.

    Both replays must be from the same match (same arenaUniqueId).

    Args:
        replay_a: First replay (typically your team's perspective).
        replay_b: Second replay (opponent team's perspective).

    Returns:
        MergedReplay with combined events and state queries.

    Raises:
        ValueError: If replays are not from the same match, or if their
            ``map_name`` disagrees (indicates mismatched matches).
    """
    # Validate same match
    arena_a = replay_a.meta.get("arenaUniqueId")
    arena_b = replay_b.meta.get("arenaUniqueId")

    if arena_a is None or arena_b is None:
        msg = "Both replays must have arenaUniqueId in metadata"
        raise ValueError(msg)

    if arena_a != arena_b:
        msg = f"Replays are from different matches: {arena_a} != {arena_b}"
        raise ValueError(msg)

    if replay_a.map_name != replay_b.map_name:
        msg = (
            f"Replays disagree on map_name: "
            f"{replay_a.map_name!r} vs {replay_b.map_name!r}"
        )
        raise ValueError(msg)

    # Match entities between replays
    entity_map = match_entities(replay_a, replay_b)

    # Merge event streams by timestamp
    merged: list[GameEvent] = []
    i, j = 0, 0
    events_a = replay_a.events
    events_b = replay_b.events

    while i < len(events_a) and j < len(events_b):
        if events_a[i].timestamp <= events_b[j].timestamp:
            merged.append(events_a[i])
            i += 1
        else:
            merged.append(events_b[j])
            j += 1

    # Append remaining
    merged.extend(events_a[i:])
    merged.extend(events_b[j:])

    result = MergedReplay(
        replay_a=replay_a,
        replay_b=replay_b,
        arena_unique_id=int(arena_a),
        entity_mapping=entity_map,
        merged_events=merged,
    )

    # Structural runtime check — ReplaySource is @runtime_checkable so
    # this verifies the merged object exposes every required attribute.
    assert isinstance(result, ReplaySource), (  # noqa: S101
        "MergedReplay does not satisfy ReplaySource protocol"
    )
    return result
