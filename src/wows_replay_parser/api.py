"""Top-level replay parsing API."""

from __future__ import annotations

import hashlib
import logging
import math
import pickle
from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar

from wows_replay_parser.events.models import BattleResultsEvent, GameEvent, MinimapVisionEvent
from wows_replay_parser.events.stream import EventStream
from wows_replay_parser.gamedata.alias_registry import AliasRegistry
from wows_replay_parser.gamedata.def_loader import DefLoader
from wows_replay_parser.gamedata.entity_registry import EntityRegistry
from wows_replay_parser.gamedata.schema_builder import SchemaBuilder
from wows_replay_parser.packets.decoder import PacketDecoder
from wows_replay_parser.packets.type_id_detector import detect_type_id_mapping
from wows_replay_parser.packets.types import PacketType
from wows_replay_parser.replay.reader import ReplayReader
from wows_replay_parser.roster import (
    PlayerInfo,
    build_roster,
    extract_arena_extras,
    extract_arena_unique_id,
)
from wows_replay_parser.state.tracker import GameStateTracker

_log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from wows_replay_parser.packets.types import Packet
    from wows_replay_parser.state.models import BattleState, GameState, ShipState

_T = TypeVar("_T", bound=GameEvent)


def _gamedata_version_hash(gamedata_path: Path) -> str:
    """Compute a fast hash of the gamedata directory for cache invalidation.

    Uses mtime of alias.xml + entities.xml + all .def files. Fast because
    it only stats files, doesn't read them.
    """
    h = hashlib.md5(usedforsecurity=False)
    # alias.xml mtime
    alias_xml = gamedata_path / "alias.xml"
    if alias_xml.exists():
        h.update(str(alias_xml.stat().st_mtime_ns).encode())
    # entities.xml mtime
    for candidate in (gamedata_path / "entities.xml", gamedata_path.parent / "entities.xml"):
        if candidate.exists():
            h.update(str(candidate.stat().st_mtime_ns).encode())
            break
    # All .def files
    for def_file in sorted(gamedata_path.glob("*.def")):
        h.update(def_file.name.encode())
        h.update(str(def_file.stat().st_mtime_ns).encode())
    for def_file in sorted((gamedata_path / "interfaces").glob("*.def")):
        h.update(def_file.name.encode())
        h.update(str(def_file.stat().st_mtime_ns).encode())
    return h.hexdigest()[:16]


def _load_gamedata_cached(
    gamedata_path: Path,
) -> tuple[AliasRegistry, EntityRegistry]:
    """Load gamedata with disk caching.

    First run: normal XML parsing (~1.2s). Subsequent runs for the same
    gamedata version: pickle load (~0.05s).
    """
    cache_dir = gamedata_path / ".cache"
    version_hash = _gamedata_version_hash(gamedata_path)
    cache_file = cache_dir / f"gamedata_{version_hash}.pkl"

    if cache_file.exists():
        try:
            with open(cache_file, "rb") as f:
                aliases, registry = pickle.load(f)
            _log.debug("Loaded gamedata from cache: %s", cache_file)
            return aliases, registry
        except Exception:
            _log.debug("Cache load failed, rebuilding", exc_info=True)

    # Normal load
    aliases = AliasRegistry.from_file(gamedata_path / "alias.xml")
    loader = DefLoader(gamedata_path)
    entity_defs = loader.load_all()

    registry = EntityRegistry(aliases)
    for entity_def in entity_defs.values():
        registry.register(entity_def)

    # Write cache
    try:
        cache_dir.mkdir(exist_ok=True)
        with open(cache_file, "wb") as f:
            pickle.dump((aliases, registry), f, protocol=pickle.HIGHEST_PROTOCOL)
        _log.debug("Wrote gamedata cache: %s", cache_file)
    except Exception:
        _log.debug("Failed to write gamedata cache", exc_info=True)

    return aliases, registry


@dataclass
class ParsedReplay:
    """Fully parsed replay with events, packets, and state queries."""

    meta: dict[str, Any]
    players: list[PlayerInfo]
    map_name: str
    game_version: str
    duration: float
    events: list[GameEvent]
    packets: list[Packet]
    _tracker: GameStateTracker = field(repr=False, compare=False)
    prebattles_info: dict = field(default_factory=dict)
    observers: list = field(default_factory=list)
    buildings_info: list = field(default_factory=list)
    battle_results: dict | None = None

    @property
    def tracker(self) -> GameStateTracker:
        """Public access to the game state tracker."""
        return self._tracker

    def camera_at(self, t: float) -> tuple[float, float, float] | None:
        """Get camera position at time t (bisect lookup)."""
        return self._tracker.camera_at(t)

    def net_stats_at(self, t: float) -> int | None:
        """Get raw network quality stat (u32) at time t (bisect lookup)."""
        return self._tracker.net_stats_at(t)

    def state_at(self, t: float) -> GameState:
        """Get full game state snapshot at timestamp t."""
        return self._tracker.state_at(t)

    def ship_state(self, entity_id: int, t: float) -> ShipState:
        """Get a specific ship's state at timestamp t."""
        return self._tracker.ship_state(entity_id, t)

    def battle_state(self, t: float) -> BattleState:
        """Get battle-level state at timestamp t."""
        return self._tracker.battle_state(t)

    def iter_states(
        self,
        timestamps: list[float],
    ) -> Iterator[GameState]:
        """Yield GameState for each timestamp, advancing forward.

        Optimized for sequential rendering. O(delta) per frame
        instead of O(history) per frame.

        Args:
            timestamps: Monotonically increasing query times.
        """
        return self._tracker.iter_states(timestamps)

    def recording_player_ribbons(self) -> list[GameEvent]:
        """Get server-authoritative ribbons for the recording player.

        Extracts from privateVehicleState.ribbons (OWN_CLIENT property).
        Each RibbonEvent has the exact timestamp and ribbon_id.
        derived=False indicates these are server-authoritative, not guesses.

        For other players' ribbons, use derive_ribbons() with self.events.
        """
        from wows_replay_parser.ribbons import extract_recording_player_ribbons

        # Find Avatar entity ID
        avatar_eid = self.tracker.get_avatar_entity_id()
        if avatar_eid is None:
            return []

        return extract_recording_player_ribbons(
            self._tracker._history, avatar_eid,
        )

    def own_player_vehicle_state(self, t: float) -> dict | None:
        """Get the recording player's privateVehicleState at time t.

        Returns the full decoded dict (ribbons, damage tallies, etc.)
        or None if not yet available.  OWN_CLIENT only.
        """
        return self._tracker.own_player_vehicle_state(t)

    def spotted_entities_at(self, t: float) -> list | None:
        """Get the recording player's spotted entities at time t.

        Returns the decoded spottedEntities list, or None if not yet
        received.  OWN_CLIENT only.
        """
        return self._tracker.spotted_entities_at(t)

    def visibility_distances_at(self, t: float) -> dict | None:
        """Get the recording player's visibility distances at time t.

        Returns the decoded visibilityDistances dict, or None if not
        yet received.  ALL_CLIENTS property on the Avatar entity.
        """
        return self._tracker.visibility_distances_at(t)

    def events_of_type(self, cls: type[_T]) -> list[_T]:
        """Filter events by type."""
        return [e for e in self.events if isinstance(e, cls)]

    def events_in_range(
        self,
        start: float,
        end: float,
    ) -> list[GameEvent]:
        """Get events in a time range (inclusive)."""
        timestamps = [e.timestamp for e in self.events]
        lo = bisect_left(timestamps, start)
        hi = bisect_right(timestamps, end)
        return self.events[lo:hi]

    # ------------------------------------------------------------------
    # Precomputed renderer helpers (all lazy via @cached_property).
    # These mirror logic previously duplicated in wows-renderer layers.
    # Kept on ParsedReplay (not only MergedReplay) so the single-render
    # path gets the same speedup and renderers can accept a generic
    # ReplaySource. See src/wows_replay_parser/interfaces.py.
    # ------------------------------------------------------------------

    @cached_property
    def battle_start_time(self) -> float | None:
        """Timestamp where ``battleStage`` transitioned to 0, or ``None``."""
        return self._tracker.battle_start_time

    @cached_property
    def first_seen(self) -> dict[int, float]:
        """entity_id → earliest real-visibility timestamp.

        Mirrors renderer/layers/base.py ``_build_first_seen`` logic:
        - For every entity with a position history, seed with the first
          position timestamp (skipping pre-battle fakes at t < 1.0 when
          any later frame exists).
        - For entities that also have MinimapVisionEvents, take the
          minimum of first-spotted vs. first real position (enemies are
          routinely spotted before their position packets arrive).
        """
        tracker = self._tracker
        positions = tracker.positions_dict
        minimap = tracker.minimap_positions_dict

        # Bucket MinimapVisionEvents by vehicle_entity_id for O(1) lookup.
        vision_first: dict[int, float] = {}
        for ev in self.events:
            if isinstance(ev, MinimapVisionEvent):
                eid = ev.vehicle_entity_id
                if eid not in vision_first:
                    vision_first[eid] = ev.timestamp

        result: dict[int, float] = {}
        for entity_id, pos_list in positions.items():
            if not pos_list:
                continue
            # First "real" position (skip t<1.0 pre-battle seeds if
            # there's a later one).
            first_pos_t = float("inf")
            for pos in pos_list:
                if pos[0] >= 1.0:
                    first_pos_t = pos[0]
                    break
            if first_pos_t == float("inf"):
                first_pos_t = pos_list[0][0]

            first_vision_t = float("inf")
            mm_entries = minimap.get(entity_id, [])
            for entry in mm_entries:
                # (t, wx, wz, heading, is_visible, is_disappearing)
                if entry[4] and not entry[5]:
                    first_vision_t = entry[0]
                    break
            if first_vision_t == float("inf"):
                first_vision_t = vision_first.get(entity_id, float("inf"))

            result[entity_id] = min(first_pos_t, first_vision_t)
        return result

    @cached_property
    def aim_yaw_timeline(self) -> dict[int, list[tuple[float, float]]]:
        """Vehicle entity_id → sorted ``[(t, yaw_rad)]`` from ``targetLocalPos``.

        Mirrors renderer/layers/ships.py ``_build_target_yaw_timeline``:
        the property value is a packed int where the low byte encodes
        the aim yaw as ``(lo / 256) * 2π - π``.
        """
        two_pi = 2.0 * math.pi
        result: dict[int, list[tuple[float, float]]] = {}
        for change in self._tracker.property_changes_by_name("targetLocalPos"):
            val = change.new_value
            if val is None or val == 65535:
                continue
            try:
                lo = int(val) & 0xFF
            except (TypeError, ValueError):
                continue
            yaw = (lo / 256.0) * two_pi - math.pi
            result.setdefault(change.entity_id, []).append(
                (change.timestamp, yaw),
            )
        # property_changes_by_name already returns history order
        # (ascending timestamp); keep explicit sort for safety.
        for timeline in result.values():
            timeline.sort(key=lambda tv: tv[0])
        return result

    @cached_property
    def camera_yaw_timeline(self) -> list[tuple[float, float]] | None:
        """Sorted ``[(t, yaw_rad)]`` from CAMERA packet quaternions, or ``None``.

        Mirrors renderer/layers/ships.py ``_build_camera_yaw_timeline``.
        Returns ``None`` when no CAMERA packets are present (common for
        non-recording-player perspectives in ``MergedReplay``).
        """
        out: list[tuple[float, float]] = []
        for packet in self.packets:
            if packet.type != PacketType.CAMERA:
                continue
            rot = getattr(packet, "camera_rotation", None)
            if rot is None:
                continue
            qx, qy, qz, qw = rot
            siny_cosp = 2.0 * (qw * qy + qx * qz)
            cosy_cosp = 1.0 - 2.0 * (qy * qy + qx * qx)
            yaw = math.atan2(siny_cosp, cosy_cosp)
            out.append((packet.timestamp, yaw))
        if not out:
            return None
        out.sort(key=lambda tv: tv[0])
        return out

    @cached_property
    def smoke_screen_lifetimes(self) -> dict[int, tuple[float, float]]:
        """SmokeScreen entity_id → ``(spawn_t, leave_t)``.

        ``leave_t`` falls back to :attr:`duration` if the entity was
        still present when the replay ended (no EntityLeave packet).
        """
        tracker = self._tracker
        out: dict[int, tuple[float, float]] = {}
        for eid in tracker.get_entities_by_type("SmokeScreen"):
            spawn_t = tracker.first_position_timestamp(eid)
            if spawn_t is None:
                spawn_t = 0.0
            leave_t = tracker.get_entity_leave_time(eid)
            if leave_t is None:
                leave_t = self.duration
            out[eid] = (spawn_t, leave_t)
        return out

    @cached_property
    def zone_positions(
        self,
    ) -> dict[int, list[tuple[float, float, float]]]:
        """InteractiveZone entity_id -> ``[(t, x, z)]`` position samples.

        Covers capture points, buff drop zones, weather zones, wards, and
        any other ``InteractiveZone`` entity. Samples come from the
        tracker's position history (populated from Position 0x0A and
        NonVolatilePosition 0x2A packets). If the zone is static after
        creation, the list will contain a single sample seeded from
        :meth:`GameStateTracker.first_position_timestamp`.
        """
        tracker = self._tracker
        positions = tracker.positions_dict
        out: dict[int, list[tuple[float, float, float]]] = {}
        for eid in tracker.get_entities_by_type("InteractiveZone"):
            samples: list[tuple[float, float, float]] = []
            pos_list = positions.get(eid, [])
            for entry in pos_list:
                # entry = (timestamp, (x, y, z), yaw)
                t, pos, _ = entry
                samples.append((t, pos[0], pos[2]))
            if not samples:
                # No Position/NonVolatilePosition samples — fall back to
                # whatever position_at can resolve at the zone's earliest
                # known time (typically the ENTITY_CREATE inline position).
                seed_t = tracker.first_position_timestamp(eid)
                if seed_t is None:
                    seed_t = tracker.battle_start_time or 0.0
                pos = tracker.position_at(eid, seed_t)
                if pos is not None and (pos[0] != 0.0 or pos[2] != 0.0):
                    samples.append((seed_t, pos[0], pos[2]))
            # If still empty, skip the entity — never emit a misleading
            # (0, 0) sample that the renderer would treat as a real pos.
            if samples:
                out[eid] = samples
        return out

    @cached_property
    def zone_lifetimes(self) -> dict[int, tuple[float, float]]:
        """InteractiveZone entity_id -> ``(spawn_t, leave_t)``.

        Mirrors :attr:`smoke_screen_lifetimes` for ``InteractiveZone``
        entities. ``leave_t`` falls back to :attr:`duration` if the
        entity was still present when the replay ended.
        """
        tracker = self._tracker
        out: dict[int, tuple[float, float]] = {}
        for eid in tracker.get_entities_by_type("InteractiveZone"):
            spawn_t = tracker.first_position_timestamp(eid)
            if spawn_t is None:
                spawn_t = 0.0
            leave_t = tracker.get_entity_leave_time(eid)
            if leave_t is None:
                leave_t = self.duration
            out[eid] = (spawn_t, leave_t)
        return out

    @cached_property
    def consumable_activations(
        self,
    ) -> dict[int, list[tuple[float, int, float]]]:
        """Vehicle entity_id -> ``[(activated_at, consumable_id, duration)]``.

        Preserves the shape returned by
        :meth:`GameStateTracker.get_consumable_activations`.
        """
        tracker = self._tracker
        out: dict[int, list[tuple[float, int, float]]] = {}
        for eid in tracker.get_vehicle_entity_ids():
            acts = tracker.get_consumable_activations(eid)
            if acts:
                out[eid] = acts
        return out

    @cached_property
    def crew_modifiers(self) -> dict[int, object]:
        """Vehicle entity_id → raw ``crewModifiersCompactParams`` value.

        Same value team_roster.py / build_export.py read via
        ``tracker.get_entity_props(eid).get("crewModifiersCompactParams")``.
        Entities without the property are skipped entirely.
        """
        tracker = self._tracker
        out: dict[int, object] = {}
        for eid in tracker.get_vehicle_entity_ids():
            props = tracker.get_entity_props(eid)
            val = props.get("crewModifiersCompactParams")
            if val is not None:
                out[eid] = val
        return out


def parse_replay(
    replay_path: str | Path,
    gamedata_path: str | Path,
    *,
    auto_update_gamedata: bool = False,
    auto_detect_methods: bool = False,
) -> ParsedReplay:
    """Parse a .wowsreplay file with full state tracking.

    Method ID resolution uses two tiers:
      Tier 1 (.def files available): Deterministic mapping from sort_size +
          stable sort preserving depth-first interface merge order. Correct
          for most methods but has known tiebreak issues in the INFINITY
          group (sort_size=65536) where ~15 methods are misplaced.
      Tier 2 (auto-detector): Refines the ordering by observing actual
          packet payloads. Required for correct projectile/combat method
          decoding. Enabled by default.

    Args:
        replay_path: Path to the .wowsreplay file.
        gamedata_path: Path to wows-gamedata entity_defs dir.
        auto_update_gamedata: If True, automatically fetch
            matching gamedata version when replay version
            doesn't match. Requires git. Defaults to False.
        auto_detect_methods: If True, run the auto-detector to resolve
            method ID ties from packet data. Should be True for correct
            projectile parsing. Defaults to True.

    Returns:
        ParsedReplay with events, packets, and state queries.
    """
    replay_path = Path(replay_path)
    gamedata_path = Path(gamedata_path)

    # Auto-sync gamedata if requested
    if auto_update_gamedata:
        import logging
        import warnings

        from wows_replay_parser.gamedata_sync import sync_gamedata

        pre_replay = ReplayReader().read(replay_path)
        # gamedata_path is entity_defs/, repo root is 3 levels up:
        # <root>/data/scripts_entity/entity_defs
        gamedata_root = gamedata_path.parent.parent.parent
        ok = sync_gamedata(gamedata_root, pre_replay.game_version)
        if not ok:
            logging.getLogger(__name__).warning(
                "Gamedata sync failed; proceeding with current version",
            )
            warnings.warn(
                "Gamedata sync failed; version may not match replay",
                stacklevel=2,
            )

    # Load gamedata (with disk cache for repeat runs)
    aliases, registry = _load_gamedata_cached(gamedata_path)

    # Read replay file
    reader = ReplayReader()
    replay = reader.read(replay_path)

    # Type ID mapping: use entities.xml as authoritative source,
    # fall back to auto-detection if entities.xml is unavailable.
    entities_xml = gamedata_path / "entities.xml"
    if not entities_xml.exists():
        # entities.xml may be one level up from entity_defs/
        entities_xml = gamedata_path.parent / "entities.xml"
    if entities_xml.exists():
        from lxml import etree as _et

        _tree = _et.parse(str(entities_xml))
        _root = _tree.getroot()
        _cs = _root.find("ClientServerEntities")
        if _cs is not None:
            for idx, child in enumerate(
                c for c in _cs if isinstance(c.tag, str)
            ):
                # Wire type_idx is 1-based (BigWorld convention),
                # entities.xml enumeration is 0-based.
                registry.register_type_id(idx + 1, child.tag)
    else:
        # Fallback: auto-detect type_id mapping from packet data
        type_mapping = detect_type_id_mapping(replay.packet_data, registry)
        for tidx, name in type_mapping.items():
            registry.register_type_id(tidx, name)

    # Method ordering is now deterministic via stable_sort + declaration order
    # + implementedBy fix. The auto-detector is redundant for Avatar/Vehicle.
    # Kept as opt-in fallback for edge cases (e.g., Account lobby methods).
    schema = SchemaBuilder(aliases, registry)
    if auto_detect_methods:
        from wows_replay_parser.packets.method_id_detector import (
            detect_method_id_mapping,
        )

        method_overrides = detect_method_id_mapping(
            replay.packet_data, registry, schema, aliases,
        )
        for entity_name, mapping in method_overrides.items():
            registry.override_method_mapping(entity_name, mapping)

    # Decode packets with state tracking
    tracker = GameStateTracker()
    decoder = PacketDecoder(schema, registry, tracker=tracker)
    packets = decoder.decode_stream(replay.packet_data)

    # Generate events
    stream = EventStream(tracker=tracker, gamedata_path=gamedata_path)
    events = stream.process(packets)

    # Build player roster and inject team_id into tracker
    # teamId is decoded from ENTITY_CREATE inline state data
    players, arena_blobs = build_roster(
        replay.meta, tracker, packets=packets, registry=registry,
        gamedata_path=gamedata_path,
    )
    for player in players:
        if player.entity_id:
            tracker.inject_property(
                player.entity_id, "teamId", player.team_id,
            )

    # Extract additional arena state blobs (reuse blobs from build_roster)
    arena_extras = extract_arena_extras(
        packets, gamedata_path=gamedata_path, arena_blobs=arena_blobs,
    )

    # Surface arenaUniqueId in meta for match-identity consumers (e.g. merge_replays).
    # The JSON header doesn't carry it; it arrives in the onArenaStateReceived packet.
    arena_uid = extract_arena_unique_id(packets)
    if arena_uid is not None:
        replay.meta["arenaUniqueId"] = arena_uid

    # Compute duration from max packet timestamp
    duration = max((p.timestamp for p in packets), default=0.0)

    # Extract battle results from events (single 0x22 packet per replay)
    battle_results: dict | None = None
    for evt in events:
        if isinstance(evt, BattleResultsEvent):
            battle_results = evt.results
            break

    return ParsedReplay(
        meta=replay.meta,
        players=players,
        map_name=replay.map_name,
        game_version=replay.game_version,
        duration=duration,
        events=events,
        packets=packets,
        _tracker=tracker,
        prebattles_info=arena_extras["prebattles_info"],
        observers=arena_extras["observers"],
        buildings_info=arena_extras["buildings_info"],
        battle_results=battle_results,
    )
