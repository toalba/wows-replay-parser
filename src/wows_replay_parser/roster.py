"""Player roster enrichment from replay JSON header."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from wows_replay_parser.state.tracker import GameStateTracker


@dataclass
class PlayerInfo:
    """Player/vehicle info from the replay header."""

    account_id: int = 0
    name: str = ""
    ship_id: int = 0
    team_id: int = 0
    relation: int = 0  # 0=self, 1=ally, 2=enemy
    entity_id: int = 0


def build_roster(
    meta: dict[str, Any],
    tracker: GameStateTracker,
) -> list[PlayerInfo]:
    """Build player roster from JSON header + entity tracking.

    Matches vehicles from the replay header to entity IDs
    discovered during packet decoding.
    """
    players: list[PlayerInfo] = []
    vehicles = meta.get("vehicles", [])

    # Get all Vehicle entity IDs from tracker
    vehicle_entity_ids = tracker.get_vehicle_entity_ids()

    # Build a map of team_id → list of entity_ids
    team_entities: dict[int, list[int]] = {}
    for eid in vehicle_entity_ids:
        props = tracker.get_entity_props(eid)
        tid = int(props.get("teamId", 0))
        team_entities.setdefault(tid, []).append(eid)

    # Track which entity_ids have been assigned
    assigned: set[int] = set()

    for vehicle in vehicles:
        if not isinstance(vehicle, dict):
            continue

        player = PlayerInfo(
            account_id=vehicle.get("id", 0),
            name=vehicle.get("name", ""),
            ship_id=vehicle.get("shipId", 0),
            team_id=vehicle.get("teamId", 0),
            relation=vehicle.get("relation", 0),
        )

        # Try to match entity_id by team
        team_ents = team_entities.get(player.team_id, [])
        for eid in team_ents:
            if eid not in assigned:
                player.entity_id = eid
                assigned.add(eid)
                break

        players.append(player)

    return players
