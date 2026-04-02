"""Player roster enrichment from replay JSON header + onArenaStateReceived."""

from __future__ import annotations

import io
import json
import logging
import pickle
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from wows_replay_parser.ship_config import ShipConfig, parse_ship_config

if TYPE_CHECKING:
    from wows_replay_parser.gamedata.entity_registry import EntityRegistry
    from wows_replay_parser.packets.types import Packet
    from wows_replay_parser.state.tracker import GameStateTracker

log = logging.getLogger(__name__)


# ── Key maps for onArenaStateReceived pickle data ──────────────────
# Each player in the pickle is a list of (int_key, value) tuples.
# The int keys map to field names in alphabetically sorted order
# (the game uses Python sets internally, which sort on serialization).
#
# Primary source: data/arena_key_maps.json (extracted from game bytecode
# by the wows-gamedata pipeline). Fallback: hardcoded maps below.

def _load_key_maps(
    gamedata_path: Path | None,
) -> tuple[dict[int, str], dict[int, str]]:
    """Load arena key maps from gamedata JSON, falling back to hardcoded maps.

    The JSON contains unordered field lists (extracted from Python sets).
    The game serializes in alphabetical order, so we sort before indexing.
    """
    if gamedata_path is not None:
        # gamedata_path is entity_defs/, JSON is at ../../arena_key_maps.json
        json_path = (gamedata_path / ".." / ".." / "arena_key_maps.json").resolve()
        if json_path.exists():
            try:
                with open(json_path) as f:
                    data = json.load(f)
                player_keys = sorted(data["player_keys"])
                bot_keys = sorted(data["bot_keys"])
                player_map = {i: k for i, k in enumerate(player_keys)}
                bot_map = {i: k for i, k in enumerate(bot_keys)}
                log.info(
                    "Loaded arena key maps from %s (%d player, %d bot keys)",
                    json_path, len(player_map), len(bot_map),
                )
                return player_map, bot_map
            except Exception:
                log.warning(
                    "Failed to load arena_key_maps.json, using hardcoded maps",
                    exc_info=True,
                )

    return _FALLBACK_PLAYER_KEY_MAP, _FALLBACK_BOT_KEY_MAP


# Fallback maps — used when arena_key_maps.json is not available.
# Alphabetically sorted, matching the game's serialization order.
_FALLBACK_PLAYER_KEY_MAP: dict[int, str] = {
    0: "accountDBID", 1: "antiAbuseEnabled", 2: "avatarId",
    3: "camouflageInfo", 4: "clanColor", 5: "clanID", 6: "clanTag",
    7: "crewParams", 8: "dogTag", 9: "fragsCount",
    10: "friendlyFireEnabled", 11: "id", 12: "invitationsEnabled",
    13: "isAbuser", 14: "isAlive", 15: "isBot", 16: "isClientLoaded",
    17: "isConnected", 18: "isHidden", 19: "isLeaver",
    20: "isPreBattleOwner", 21: "isTShooter", 22: "keyTargetMarkers",
    23: "killedBuildingsCount", 24: "maxHealth", 25: "name",
    26: "playerMode", 27: "preBattleIdOnStart", 28: "preBattleSign",
    29: "prebattleId", 30: "realm", 31: "shipComponents",
    32: "shipConfigDump", 33: "shipId", 34: "shipParamsId", 35: "skinId",
    36: "teamId", 37: "ttkStatus",
}

_FALLBACK_BOT_KEY_MAP: dict[int, str] = {
    0: "accountDBID", 1: "antiAbuseEnabled", 2: "camouflageInfo",
    3: "clanColor", 4: "clanID", 5: "clanTag", 6: "crewParams",
    7: "dogTag", 8: "fragsCount", 9: "friendlyFireEnabled", 10: "id",
    11: "isAbuser", 12: "isAlive", 13: "isBot", 14: "isHidden",
    15: "isTShooter", 16: "keyTargetMarkers", 17: "killedBuildingsCount",
    18: "maxHealth", 19: "name", 20: "realm", 21: "shipComponents",
    22: "shipConfigDump", 23: "shipId", 24: "shipParamsId", 25: "skinId",
    26: "teamId", 27: "ttkStatus",
}


@dataclass
class PlayerInfo:
    """Player/vehicle info from the replay header."""

    account_id: int = 0
    name: str = ""
    ship_id: int = 0
    team_id: int = 0
    relation: int = 0  # 0=self, 1=ally, 2=enemy
    entity_id: int = 0
    clan_tag: str = ""
    clan_color: int = 0  # Clan tag display color as packed RGB integer (0 = no custom color)
    max_health: int = 0
    is_bot: bool = False
    ship_config: ShipConfig | None = None  # Parsed loadout from shipConfigDump
    crew_id: int = 0  # GameParams ID of the captain (from crewParams[0])
    prebattle_id: int = 0
    is_prebattle_owner: bool = False
    clan_id: int = 0
    avatar_id: int = 0
    realm: str = ""
    skin_id: int = 0
    ship_params_id: int = 0
    is_leaver: bool = False
    is_connected: bool = False
    is_hidden: bool = False
    dog_tag: Any = None
    player_mode: dict = field(default_factory=dict)
    ship_components: dict = field(default_factory=dict)


def build_roster(
    meta: dict[str, Any],
    tracker: GameStateTracker,
    packets: list[Packet] | None = None,
    registry: EntityRegistry | None = None,
    gamedata_path: Path | None = None,
) -> tuple[list[PlayerInfo], list[bytes] | None]:
    """Build player roster from JSON header + onArenaStateReceived.

    Primary approach: decode onArenaStateReceived pickle blobs to get
    the authoritative entity_id <-> account_id mapping.
    Fallback: order-based matching within teams (broken for non-self players).

    Returns (roster, arena_blobs) — arena_blobs can be passed to
    extract_arena_extras() to avoid re-scanning packets.
    """
    vehicles = meta.get("vehicles", [])
    if not vehicles:
        return [], None

    # Load key maps from gamedata (or fallback to hardcoded)
    player_key_map, bot_key_map = _load_key_maps(gamedata_path)

    # Try arena state matching first
    if packets:
        arena_roster, blobs = _match_via_arena_state(
            vehicles, packets, player_key_map, bot_key_map,
        )
        if arena_roster:
            return arena_roster, blobs

    # Fallback to old order-based matching
    log.warning("onArenaStateReceived not found, falling back to order-based matching")
    return _match_by_order_fallback(meta, tracker, packets, registry), None


class _SafeUnpickler(pickle.Unpickler):
    """Unpickler that handles missing game modules (CamouflageInfo, etc.)."""

    def find_class(self, module: str, name: str) -> type:
        try:
            return super().find_class(module, name)
        except (ModuleNotFoundError, AttributeError):
            # Create a dummy dict subclass for unknown game classes
            cls = type(name, (dict,), {"__module__": module})
            return cls


def _safe_pickle_loads(data: bytes) -> Any:
    """Pickle loads with latin-1 encoding (handles Python 2 pickles)."""
    return _SafeUnpickler(io.BytesIO(data), encoding="latin-1").load()


def _decode_arena_players(
    blob: bytes,
    key_map: dict[int, str],
) -> list[dict[str, Any]]:
    """Decode a pickled player/bot states blob into a list of dicts.

    Each player in the pickle is a list of (int_key, value) tuples.
    We convert using the appropriate key map.
    """
    try:
        data = _safe_pickle_loads(blob)  # noqa: S301
    except Exception:
        log.debug("Failed to unpickle arena state blob", exc_info=True)
        return []

    if not isinstance(data, list):
        return []

    players: list[dict[str, Any]] = []
    for entry in data:
        if not isinstance(entry, (list, tuple)):
            continue
        player: dict[str, Any] = {}
        for item in entry:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            idx = item[0]
            val = item[1]
            name = key_map.get(idx)
            if name is not None:
                player[name] = val
        if player:
            players.append(player)
    return players


def _extract_arena_blobs(
    packet: Packet,
) -> list[bytes] | None:
    """Extract all pickle blobs from onArenaStateReceived.

    The payload format after the 12-byte method header (eid+mid+len):
      arenaUniqueId(INT64, 8) + teamBuildTypeId(INT8, 1) +
      preBattlesInfo(pickle) + playersStates(pickle) + botsStates(pickle) +
      observersState(pickle) + buildingsInfo(pickle)

    BLOBs use variable-length prefix encoding (vlh=1):
      u8 < 0xFF: that's the length
      u8 == 0xFF: read u16, if 0xFFFF: read u32

    Since pickle boundaries can be tricky, we locate each pickle by
    scanning for protocol 2 headers (\\x80\\x02) and deserializing.
    Returns up to 5 pickle blobs (indices 0–4). Index 1 is playersStates,
    index 2 is botsStates. Returns None if fewer than 2 pickles are found.
    """
    raw = packet.raw_payload
    if len(raw) < 100:
        return None

    # Args start after 12-byte method header + 9-byte fixed args
    args_data = raw[12:]

    # Find all pickle protocol 2 boundaries
    pickles: list[bytes] = []
    pos = 0
    while len(pickles) < 5:
        idx = args_data.find(b"\x80\x02", pos)
        if idx == -1:
            break
        stream = io.BytesIO(args_data[idx:])
        try:
            _SafeUnpickler(stream, encoding="latin-1").load()
            consumed = stream.tell()
            pickles.append(args_data[idx : idx + consumed])
            pos = idx + consumed
        except Exception:
            pos = idx + 1

    # pickles[0] = preBattlesInfo, [1] = playersStates, [2] = botsStates
    # pickles[3] = observersState, [4] = buildingsInfo
    if len(pickles) < 2:
        return None

    return pickles


def _find_arena_state_packet(
    packets: list[Packet],
) -> Packet | None:
    """Find the onArenaStateReceived packet.

    First tries by method name. If that fails or yields a tiny payload
    (method sort order mismatch), scans all early Avatar method packets
    for one whose raw payload parses as valid arena state data.
    """
    from wows_replay_parser.packets.types import PacketType

    # Try by method name first
    for p in packets:
        if getattr(p, "method_name", None) == "onArenaStateReceived":
            # Verify it's actually arena data (payload > 1000 bytes)
            if len(p.raw_payload) > 1000:
                return p
            break  # Found but too small — sort order is wrong

    # Fallback: scan early Avatar method packets by content
    # onArenaStateReceived arrives very early (t < 5s) and has a large payload
    for p in packets:
        if p.timestamp > 10.0:
            break
        if p.type != PacketType.ENTITY_METHOD:
            continue
        if len(p.raw_payload) < 1000:
            continue
        # Try to parse as arena state: header(12) + arenaUniqueId(8) + teamBuildTypeId(1)
        # + preBattlesInfo(BLOB) + playersStates(BLOB)
        blobs = _extract_arena_blobs(p)
        if blobs is None:
            continue
        players_blob = blobs[1] if len(blobs) > 1 else b""
        if not players_blob:
            continue
        # Verify it's valid pickle containing a list of player tuples
        try:
            data = _safe_pickle_loads(players_blob)
            if (
                isinstance(data, list)
                and len(data) >= 2
                and isinstance(data[0], (list, tuple))
            ):
                log.info(
                    "Found arena state packet by content probe: t=%.2f, method=%s, %d bytes",
                    p.timestamp,
                    getattr(p, "method_name", "?"),
                    len(p.raw_payload),
                )
                return p
        except Exception:
            continue

    return None


def _match_via_arena_state(
    vehicles: list[dict[str, Any]],
    packets: list[Packet],
    player_key_map: dict[int, str],
    bot_key_map: dict[int, str],
) -> tuple[list[PlayerInfo] | None, list[bytes] | None]:
    """Match players using onArenaStateReceived pickle data.

    Returns (roster, blobs) — roster is None if the packet wasn't found
    or decoding failed.  blobs is the raw extracted pickle list (reusable
    by extract_arena_extras to avoid a second scan).
    """
    arena_packet = _find_arena_state_packet(packets)
    if arena_packet is None:
        return None, None

    blobs = _extract_arena_blobs(arena_packet)
    if blobs is None:
        return None, None

    players_blob = blobs[1]
    bots_blob = blobs[2] if len(blobs) > 2 else b""

    arena_players = _decode_arena_players(players_blob, player_key_map)
    arena_bots: list[dict[str, Any]] = []
    if bots_blob:
        arena_bots = _decode_arena_players(bots_blob, bot_key_map)

    if not arena_players and not arena_bots:
        log.warning("onArenaStateReceived found but decoded 0 players")
        return None, blobs

    log.info(
        "Decoded onArenaStateReceived: %d players, %d bots",
        len(arena_players),
        len(arena_bots),
    )

    # Build account_id → vehicle metadata lookup from JSON header
    # The JSON header "id" field is the account-level identifier
    meta_by_account: dict[int, dict[str, Any]] = {}
    for v in vehicles:
        if isinstance(v, dict):
            aid = v.get("id", 0)
            if aid:
                meta_by_account[aid] = v

    # Match arena players to metadata and build roster
    roster: list[PlayerInfo] = []
    all_arena = arena_players + arena_bots

    for ap in all_arena:
        # "id" in the pickle = account-level identifier matching JSON header "id"
        meta_ship_id = ap.get("id", 0)
        # "shipId" in the pickle = Vehicle entity ID in the game world
        entity_id = ap.get("shipId", 0)
        team_id = ap.get("teamId", 0)
        is_bot = bool(ap.get("isBot", False))

        # Match to JSON header metadata
        meta_vehicle = meta_by_account.get(meta_ship_id)

        if meta_vehicle is not None:
            relation = meta_vehicle.get("relation", 2)
            name = meta_vehicle.get("name", ap.get("name", ""))
            ship_id = meta_vehicle.get("shipId", 0)
            account_id = meta_vehicle.get("id", 0)
        else:
            # Bot or unmatched player — use arena state data directly
            relation = 2  # assume enemy for unmatched
            name = ap.get("name", "")
            ship_id = ap.get("shipParamsId", 0)
            account_id = ap.get("accountDBID", 0)

        # Parse ship loadout from shipConfigDump
        config_dump = ap.get("shipConfigDump")
        ship_config = parse_ship_config(config_dump) if config_dump else None

        # Extract crew ID from crewParams
        crew_params = ap.get("crewParams")
        crew_id = crew_params[0] if isinstance(crew_params, (list, tuple)) and crew_params else 0

        roster.append(PlayerInfo(
            account_id=account_id,
            name=name,
            ship_id=ship_id,
            team_id=team_id,
            relation=relation,
            entity_id=entity_id,
            clan_tag=ap.get("clanTag", ""),
            clan_color=int(ap.get("clanColor", 0)),
            max_health=int(ap.get("maxHealth", 0)),
            is_bot=is_bot,
            ship_config=ship_config,
            crew_id=int(crew_id) if crew_id else 0,
            prebattle_id=int(ap.get("prebattleId", 0)),
            is_prebattle_owner=bool(ap.get("isPreBattleOwner", False)),
            clan_id=int(ap.get("clanID", 0)),
            avatar_id=int(ap.get("avatarId", 0)),
            realm=ap.get("realm", ""),
            skin_id=int(ap.get("skinId", 0)),
            ship_params_id=int(ap.get("shipParamsId", 0)),
            is_leaver=bool(ap.get("isLeaver", False)),
            is_connected=bool(ap.get("isConnected", False)),
            is_hidden=bool(ap.get("isHidden", False)),
            dog_tag=ap.get("dogTag"),
            player_mode=ap.get("playerMode") or {},
            ship_components=ap.get("shipComponents") or {},
        ))

    return roster, blobs


def extract_arena_extras(
    packets: list[Packet],
    gamedata_path: Path | None = None,
    arena_blobs: list[bytes] | None = None,
) -> dict[str, Any]:
    """Extract prebattles_info, observers, and buildings_info from onArenaStateReceived.

    If arena_blobs is provided (from build_roster), reuses them to avoid
    re-scanning packets.  Otherwise finds and extracts blobs from scratch.

    Returns a dict with keys 'prebattles_info' (dict), 'observers' (list),
    'buildings_info' (list). All default to empty if the blob is missing or
    cannot be decoded.
    """
    result: dict[str, Any] = {
        "prebattles_info": {},
        "observers": [],
        "buildings_info": [],
    }

    blobs = arena_blobs
    if blobs is None:
        arena_packet = _find_arena_state_packet(packets)
        if arena_packet is None:
            return result
        blobs = _extract_arena_blobs(arena_packet)
    if blobs is None:
        return result

    # Use version-aware key map (falls back to hardcoded if gamedata unavailable)
    player_key_map, _ = _load_key_maps(gamedata_path)

    if len(blobs) > 0:
        try:
            prebattles = _safe_pickle_loads(blobs[0])
            if isinstance(prebattles, dict):
                result["prebattles_info"] = prebattles
        except Exception:
            log.debug("Failed to decode prebattles_info blob", exc_info=True)

    if len(blobs) > 3:
        try:
            observers_raw = _safe_pickle_loads(blobs[3])
            if isinstance(observers_raw, list) and observers_raw:
                first = observers_raw[0]
                first_item_is_tuple = (
                    isinstance(first, (list, tuple))
                    and first
                    and isinstance(first[0], (list, tuple))
                )
                if first_item_is_tuple:
                    # Same (int_key, value) tuple structure as playersStates
                    observers = []
                    for entry in observers_raw:
                        if not isinstance(entry, (list, tuple)):
                            continue
                        player: dict[str, Any] = {}
                        for item in entry:
                            if not isinstance(item, (list, tuple)) or len(item) < 2:
                                continue
                            name = player_key_map.get(item[0])
                            if name is not None:
                                player[name] = item[1]
                        if player:
                            observers.append(player)
                    result["observers"] = observers
                else:
                    result["observers"] = observers_raw
            elif isinstance(observers_raw, list):
                result["observers"] = observers_raw
        except Exception:
            log.debug("Failed to decode observersState blob", exc_info=True)

    if len(blobs) > 4:
        try:
            buildings = _safe_pickle_loads(blobs[4])
            if isinstance(buildings, list):
                result["buildings_info"] = buildings
        except Exception:
            log.debug("Failed to decode buildingsInfo blob", exc_info=True)

    return result


# ── Fallback: order-based matching (old broken approach) ───────────

def _match_by_order_fallback(
    meta: dict[str, Any],
    tracker: GameStateTracker,
    packets: list[Packet] | None = None,
    registry: EntityRegistry | None = None,
) -> list[PlayerInfo]:
    """Fallback roster building using order-based matching within teams."""
    from wows_replay_parser.packets.types import PacketType

    vehicles = meta.get("vehicles", [])
    vehicle_entity_ids = tracker.get_vehicle_entity_ids()

    if not vehicle_entity_ids or not vehicles:
        return _build_fallback(vehicles)

    self_avatar_eid = None
    if packets:
        for p in packets:
            if p.type == PacketType.BASE_PLAYER_CREATE:
                self_avatar_eid = p.entity_id
                break

    vehicle_team: dict[int, int] = {}
    vehicle_owner: dict[int, int] = {}
    if packets and registry:
        vehicle_team, vehicle_owner = _decode_vehicle_state(packets, registry)

    self_vehicle_eid = None
    if self_avatar_eid is not None:
        for eid, owner in vehicle_owner.items():
            if owner == self_avatar_eid:
                self_vehicle_eid = eid
                break

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
        ally_eids = set()
        enemy_eids = set(vehicle_entity_ids)

    return _match_by_team(vehicles, self_vehicle_eid, ally_eids, enemy_eids)


def _decode_vehicle_state(
    packets: list[Packet],
    registry: EntityRegistry,
) -> tuple[dict[int, int], dict[int, int]]:
    """Decode teamId and owner from Vehicle ENTITY_CREATE inline state data."""
    from wows_replay_parser.packets.types import PacketType

    vehicle_entity = registry.get("Vehicle")
    if vehicle_entity is None:
        return {}, {}

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
                break

            name, byte_size = prop_info[prop_id]

            if byte_size is None:
                if offset + 4 > len(state_data):
                    break
                vlen = struct.unpack_from("<I", state_data, offset)[0]
                offset += 4 + vlen
            else:
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
    """Match JSON header vehicles to entity IDs by team (order-based fallback)."""
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

    ally_eid_list = sorted(
        ally_eids - ({self_vehicle_eid} if self_vehicle_eid else set()),
    )
    enemy_eid_list = sorted(enemy_eids)

    players: list[PlayerInfo] = []

    for v in self_vehicles:
        players.append(PlayerInfo(
            account_id=v.get("id", 0),
            name=v.get("name", ""),
            ship_id=v.get("shipId", 0),
            team_id=0,
            relation=0,
            entity_id=self_vehicle_eid or 0,
        ))

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
