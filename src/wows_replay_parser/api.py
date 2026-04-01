"""Top-level replay parsing API."""

from __future__ import annotations

import hashlib
import logging
import pickle
from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar

from wows_replay_parser.events.models import GameEvent
from wows_replay_parser.events.stream import EventStream
from wows_replay_parser.gamedata.alias_registry import AliasRegistry
from wows_replay_parser.gamedata.def_loader import DefLoader
from wows_replay_parser.gamedata.entity_registry import EntityRegistry
from wows_replay_parser.gamedata.schema_builder import SchemaBuilder
from wows_replay_parser.packets.decoder import PacketDecoder
from wows_replay_parser.packets.type_id_detector import detect_type_id_mapping
from wows_replay_parser.replay.reader import ReplayReader
from wows_replay_parser.roster import PlayerInfo, build_roster
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
        avatar_eid = None
        for eid, etype in self._tracker._entity_types.items():
            if etype == "Avatar":
                avatar_eid = eid
                break
        if avatar_eid is None:
            return []

        return extract_recording_player_ribbons(
            self._tracker._history, avatar_eid,
        )

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
    players = build_roster(
        replay.meta, tracker, packets=packets, registry=registry,
        gamedata_path=gamedata_path,
    )
    for player in players:
        if player.entity_id:
            tracker.inject_property(
                player.entity_id, "teamId", player.team_id,
            )

    # Compute duration from max packet timestamp
    duration = max((p.timestamp for p in packets), default=0.0)

    return ParsedReplay(
        meta=replay.meta,
        players=players,
        map_name=replay.map_name,
        game_version=replay.game_version,
        duration=duration,
        events=events,
        packets=packets,
        _tracker=tracker,
    )
