"""Player roster enrichment from replay JSON header."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from wows_replay_parser.gamedata.entity_registry import EntityRegistry
    from wows_replay_parser.packets.types import Packet
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
    packets: list[Packet] | None = None,
    registry: EntityRegistry | None = None,
) -> list[PlayerInfo]:
    """Build player roster from JSON header + entity tracking.

    Matches vehicles from the replay header to entity IDs by:
    1. Decoding teamId and owner from ENTITY_CREATE inline state data
    2. Identifying self Vehicle via owner == self Avatar entity_id
    3. Splitting entities by teamId into ally/enemy teams
    4. Matching JSON header vehicles to entities by team, then by order
    """
    from wows_replay_parser.packets.types import PacketType

    vehicles = meta.get("vehicles", [])
    vehicle_entity_ids = tracker.get_vehicle_entity_ids()

    if not vehicle_entity_ids or not vehicles:
        return _build_fallback(vehicles)

    # Step 1: Find self Avatar entity_id from BASE_PLAYER_CREATE
    self_avatar_eid = None
    if packets:
        for p in packets:
            if p.type == PacketType.BASE_PLAYER_CREATE:
                self_avatar_eid = p.entity_id
                break

    # Step 2: Decode teamId and owner from Vehicle ENTITY_CREATE state data
    vehicle_team: dict[int, int] = {}  # entity_id → teamId
    vehicle_owner: dict[int, int] = {}  # entity_id → owner Avatar eid
    if packets and registry:
        vehicle_team, vehicle_owner = _decode_vehicle_state(
            packets, registry,
        )

    # Step 3: Identify self Vehicle (owner == self Avatar)
    self_vehicle_eid = None
    if self_avatar_eid is not None:
        for eid, owner in vehicle_owner.items():
            if owner == self_avatar_eid:
                self_vehicle_eid = eid
                break

    # Step 4: Split into ally/enemy by teamId
    if self_vehicle_eid is not None and vehicle_team:
        self_team = vehicle_team.get(self_vehicle_eid)
        ally_eids: set[int] = set()
        enemy_eids: set[int] = set()
        for eid in vehicle_entity_ids:
            tid = vehicle_team.get(eid)
            if tid is None:
                enemy_eids.add(eid)
            elif tid == self_team:
                ally_eids.add(eid)
            else:
                enemy_eids.add(eid)
    else:
        # No state data — all unknown
        ally_eids = set()
        enemy_eids = set(vehicle_entity_ids)

    return _match_by_team(vehicles, self_vehicle_eid, ally_eids, enemy_eids)


def _decode_vehicle_state(
    packets: list[Packet],
    registry: EntityRegistry,
) -> tuple[dict[int, int], dict[int, int]]:
    """Decode teamId and owner from Vehicle ENTITY_CREATE inline state data.

    The state data format (from BigWorld engine) is:
      num_props(u8) + [prop_id(u8) + typed_value] × num_props

    Properties are in sort_size order. We need:
      - teamId (TEAM_ID = INT8, 1 byte)
      - owner (ENTITY_ID = INT32, 4 bytes)

    Returns:
        (vehicle_team, vehicle_owner) dicts mapping entity_id to values.
    """
    from wows_replay_parser.packets.types import PacketType

    vehicle_entity = registry.get("Vehicle")
    if vehicle_entity is None:
        return {}, {}

    # Build property info lookup: index → (name, byte_size)
    # For variable-length props (sort_size=65535), size is None
    prop_info: dict[int, tuple[str, int | None]] = {}
    for i, prop in enumerate(vehicle_entity.client_properties):
        s = prop.sort_size
        prop_info[i] = (prop.name, None if s >= 0xFFFF else s)

    vehicle_team: dict[int, int] = {}
    vehicle_owner: dict[int, int] = {}
    seen: set[int] = set()

    for p in packets:
        if p.type != PacketType.ENTITY_CREATE:
            continue
        if getattr(p, "entity_type", "") != "Vehicle":
            continue
        eid = p.entity_id
        if eid in seen:
            continue
        seen.add(eid)

        # State data starts after: eid(4) + type_idx(2) + vehicle_id(4) +
        #   space_id(4) + pos(12) + rot(12) + state_len(4) = offset 42
        if len(p.raw_payload) < 42:
            continue
        state_len = struct.unpack_from("<I", p.raw_payload, 38)[0]
        state_data = p.raw_payload[42:42 + state_len]
        if not state_data:
            continue

        num_props = state_data[0]
        offset = 1

        for _ in range(num_props):
            if offset >= len(state_data):
                break
            prop_id = state_data[offset]
            offset += 1

            if prop_id not in prop_info:
                break  # Unknown property — can't continue

            name, byte_size = prop_info[prop_id]

            if byte_size is None:
                # Variable-length: u32 length prefix + data
                if offset + 4 > len(state_data):
                    break
                vlen = struct.unpack_from("<I", state_data, offset)[0]
                offset += 4 + vlen
            else:
                # Fixed-size: extract value if it's one we care about
                if name == "teamId" and offset + 1 <= len(state_data):
                    vehicle_team[eid] = struct.unpack_from(
                        "<b", state_data, offset,
                    )[0]
                elif name == "owner" and offset + 4 <= len(state_data):
                    vehicle_owner[eid] = struct.unpack_from(
                        "<i", state_data, offset,
                    )[0]
                offset += byte_size

    return vehicle_team, vehicle_owner


def _match_by_team(
    vehicles: list[dict[str, Any]],
    self_vehicle_eid: int | None,
    ally_eids: set[int],
    enemy_eids: set[int],
) -> list[PlayerInfo]:
    """Match JSON header vehicles to entity IDs by team membership.

    Self player → self_vehicle_eid
    Allies → ally_eids (matched by order)
    Enemies → enemy_eids (matched by order)
    """
    # Separate JSON vehicles by relation
    self_vehicles: list[dict[str, Any]] = []
    ally_vehicles: list[dict[str, Any]] = []
    enemy_vehicles: list[dict[str, Any]] = []

    for v in vehicles:
        if not isinstance(v, dict):
            continue
        rel = v.get("relation", 0)
        if rel == 0:
            self_vehicles.append(v)
        elif rel == 1:
            ally_vehicles.append(v)
        else:
            enemy_vehicles.append(v)

    # Determine team_id mapping from self vehicle's team
    # Self vehicle's raw teamId becomes "team 0" in display
    self_raw_team = None
    if self_vehicle_eid is not None:
        # The self vehicle is in ally_eids
        pass  # team_id for display: self/ally=0, enemy=1

    # Sort entity ID sets for deterministic order-based matching
    ally_eid_list = sorted(
        ally_eids - ({self_vehicle_eid} if self_vehicle_eid else set()),
    )
    enemy_eid_list = sorted(enemy_eids)

    players: list[PlayerInfo] = []

    # Self player
    for v in self_vehicles:
        players.append(PlayerInfo(
            account_id=v.get("id", 0),
            name=v.get("name", ""),
            ship_id=v.get("shipId", 0),
            team_id=0,
            relation=0,
            entity_id=self_vehicle_eid or 0,
        ))

    # Allies
    for i, v in enumerate(ally_vehicles):
        eid = ally_eid_list[i] if i < len(ally_eid_list) else 0
        players.append(PlayerInfo(
            account_id=v.get("id", 0),
            name=v.get("name", ""),
            ship_id=v.get("shipId", 0),
            team_id=0,
            relation=1,
            entity_id=eid,
        ))

    # Enemies
    for i, v in enumerate(enemy_vehicles):
        eid = enemy_eid_list[i] if i < len(enemy_eid_list) else 0
        players.append(PlayerInfo(
            account_id=v.get("id", 0),
            name=v.get("name", ""),
            ship_id=v.get("shipId", 0),
            team_id=1,
            relation=2,
            entity_id=eid,
        ))

    return players


def _build_fallback(vehicles: list[dict[str, Any]]) -> list[PlayerInfo]:
    """Fallback: build roster without entity matching."""
    players: list[PlayerInfo] = []
    for v in vehicles:
        if not isinstance(v, dict):
            continue
        relation = v.get("relation", 0)
        team_id = 0 if relation in (0, 1) else 1
        players.append(PlayerInfo(
            account_id=v.get("id", 0),
            name=v.get("name", ""),
            ship_id=v.get("shipId", 0),
            team_id=team_id,
            relation=relation,
        ))
    return players
