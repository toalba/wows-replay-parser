"""Top-level replay parsing API."""

from __future__ import annotations

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

if TYPE_CHECKING:
    from collections.abc import Iterator

    from wows_replay_parser.packets.types import Packet
    from wows_replay_parser.state.models import BattleState, GameState, ShipState

_T = TypeVar("_T", bound=GameEvent)


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
) -> ParsedReplay:
    """Parse a .wowsreplay file with full state tracking.

    Args:
        replay_path: Path to the .wowsreplay file.
        gamedata_path: Path to wows-gamedata entity_defs dir.
        auto_update_gamedata: If True, automatically fetch
            matching gamedata version when replay version
            doesn't match. Requires git. Defaults to False.

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

    # Load gamedata
    aliases = AliasRegistry.from_file(gamedata_path / "alias.xml")
    loader = DefLoader(gamedata_path)
    entity_defs = loader.load_all()

    registry = EntityRegistry(aliases)
    for entity_def in entity_defs.values():
        registry.register(entity_def)

    # Read replay file
    reader = ReplayReader()
    replay = reader.read(replay_path)

    # Auto-detect type_id → entity mapping
    type_mapping = detect_type_id_mapping(replay.packet_data, registry)
    for tidx, name in type_mapping.items():
        registry.register_type_id(tidx, name)

    # Decode packets with state tracking
    tracker = GameStateTracker()
    schema = SchemaBuilder(aliases, registry)
    decoder = PacketDecoder(schema, registry, tracker=tracker)
    packets = decoder.decode_stream(replay.packet_data)

    # Generate events
    stream = EventStream(tracker=tracker)
    events = stream.process(packets)

    # Build player roster and inject team_id into tracker
    # (teamId is set during entity creation, not as a property
    # update, so the tracker never sees it from packets)
    players = build_roster(replay.meta, tracker)
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
