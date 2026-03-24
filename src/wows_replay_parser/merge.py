"""Dual perspective replay merging.

Merges two replays from the same match (one from each team) into
a unified view where all ships from both teams are visible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from wows_replay_parser.state.models import GameState

if TYPE_CHECKING:
    from wows_replay_parser.api import ParsedReplay
    from wows_replay_parser.events.models import GameEvent
    from wows_replay_parser.state.models import ShipState


@dataclass
class MergedReplay:
    """Two replays from the same match merged for dual perspective."""

    replay_a: ParsedReplay
    replay_b: ParsedReplay
    arena_unique_id: int
    entity_mapping: dict[int, int] = field(default_factory=dict)
    merged_events: list[GameEvent] = field(default_factory=list)

    def state_at(self, t: float) -> GameState:
        """Get combined game state from both perspectives.

        For ships visible in both replays, prefers the "owner"
        perspective (the replay where the ship's team is playing).
        """
        state_a = self.replay_a.state_at(t)
        state_b = self.replay_b.state_at(t)

        # Start with all ships from replay A
        combined_ships: dict[int, ShipState] = dict(state_a.ships)

        # Add ships from replay B that aren't already present
        for eid_b, ship_b in state_b.ships.items():
            eid_a = self.entity_mapping.get(eid_b)
            if eid_a is not None and eid_a in combined_ships:
                # Ship exists in both — keep the one with more data
                ship_a = combined_ships[eid_a]
                if ship_b.max_health > 0 and ship_a.max_health == 0:
                    combined_ships[eid_a] = ship_b
            elif eid_a is None:
                # Ship only in replay B — add it
                combined_ships[eid_b] = ship_b

        # Use replay A's battle state (arbitrary choice)
        return GameState(
            timestamp=t,
            ships=combined_ships,
            battle=state_a.battle,
        )


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
        if player.entity_id:
            a_lookup[(player.name, player.ship_id)] = player.entity_id

    # Match replay B players to replay A
    for player in replay_b.players:
        if player.entity_id:
            key = (player.name, player.ship_id)
            eid_a = a_lookup.get(key)
            if eid_a is not None:
                mapping[player.entity_id] = eid_a

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
        ValueError: If replays are not from the same match.
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

    return MergedReplay(
        replay_a=replay_a,
        replay_b=replay_b,
        arena_unique_id=int(arena_a),
        entity_mapping=entity_map,
        merged_events=merged,
    )
