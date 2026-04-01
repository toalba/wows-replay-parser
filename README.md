# wows-replay-parser

A Python library for parsing World of Warships `.wowsreplay` files with dynamic schema loading. No hardcoded schemas — the binary format is derived at runtime from entity definition files, so new game patches require only a `git pull` on the gamedata repository.

**GitHub:** https://github.com/toalba/wows-replay-parser

---

## Features

- Decodes all BigWorld network packets from any `.wowsreplay` file
- Dynamic schema generation from `.def` XML entity definitions — no manual updates on patches
- Full entity state history with timestamp-indexed `state_at()` queries
- Typed event stream: 20 event types covering positions, shots, torpedoes, damage, deaths, cap points, scores, vision, squadrons, ribbons, and more
- Blowfish ECB decryption + zlib decompression of the packet stream
- Auto-detection of type-ID to entity-name mapping from live packet data
- Player roster enrichment with ship loadouts, clan info, and crew IDs
- Server-authoritative ribbon extraction for the recording player
- Structured JSON export with state snapshots
- No data loss: unrecognized packets produce `RawEvent` rather than being silently dropped
- CLI with five commands: `info`, `parse`, `events`, `state`, `export`

---

## Quick Start

### Install

```bash
# Core library
pip install wows-replay-parser

# With CLI support
pip install "wows-replay-parser[cli]"
```

### Get gamedata

```bash
git clone https://github.com/toalba/wows-gamedata.git
```

### Parse a replay

```python
from wows_replay_parser import parse_replay
from wows_replay_parser.events.models import ShotCreatedEvent, DeathEvent

replay = parse_replay(
    replay_path="battle.wowsreplay",
    gamedata_path="./wows-gamedata/data/scripts_entity/entity_defs",
)

print(replay.map_name)       # "spaces/42_Neighbors"
print(replay.game_version)   # "15.2.0"
print(replay.duration)       # 1243.6  (seconds)

for player in replay.players:
    print(player.name, player.ship_id, player.team_id)

shots = replay.events_of_type(ShotCreatedEvent)
deaths = replay.events_of_type(DeathEvent)

state = replay.state_at(120.5)
for entity_id, ship in state.ships.items():
    print(entity_id, ship.health, ship.position)
```

---

## CLI Usage

All CLI commands require `"wows-replay-parser[cli]"` to be installed.

```bash
# Show metadata: map, version, player list, duration
wowsreplay info battle.wowsreplay

# Decode and print all packets as JSON
wowsreplay parse battle.wowsreplay \
    --gamedata ./wows-gamedata/data/scripts_entity/entity_defs

# Print typed event stream as JSON
wowsreplay events battle.wowsreplay \
    --gamedata ./wows-gamedata/data/scripts_entity/entity_defs

# Print entity state at a specific timestamp
wowsreplay state battle.wowsreplay \
    --gamedata ./wows-gamedata/data/scripts_entity/entity_defs \
    --time 120.5

# Export complete replay as structured JSON (with state snapshots)
wowsreplay export battle.wowsreplay \
    --gamedata ./wows-gamedata/data/scripts_entity/entity_defs \
    -o replay.json
```

---

## API Reference

### `parse_replay(replay_path, gamedata_path) -> ParsedReplay`

Top-level entry point. Loads gamedata, decrypts and decodes the replay, builds the event stream and state tracker, and returns a `ParsedReplay`.

### `ParsedReplay` fields

| Field | Type | Description |
|---|---|---|
| `meta` | `dict[str, Any]` | Raw JSON header from the replay file |
| `players` | `list[PlayerInfo]` | Player roster (name, ship, team, loadout, clan) |
| `map_name` | `str` | Map identifier, e.g. `"spaces/42_Neighbors"` |
| `game_version` | `str` | Game client version string |
| `duration` | `float` | Replay length in seconds |
| `events` | `list[GameEvent]` | All game events, sorted by timestamp |
| `packets` | `list[Packet]` | All decoded packets (raw access) |

### `ParsedReplay` methods

```python
# Full game state snapshot at timestamp t
replay.state_at(t: float) -> GameState

# State for one ship at timestamp t
replay.ship_state(entity_id: int, t: float) -> ShipState

# Battle-level state (scores, timer, cap points) at timestamp t
replay.battle_state(t: float) -> BattleState

# Optimized sequential iteration for rendering (O(delta) per frame)
replay.iter_states(timestamps: list[float]) -> Iterator[GameState]

# Server-authoritative ribbons for the recording player
replay.recording_player_ribbons() -> list[RibbonEvent]

# Filter events by type
replay.events_of_type(ShotCreatedEvent) -> list[ShotCreatedEvent]

# Events in a time window (inclusive)
replay.events_in_range(start: float, end: float) -> list[GameEvent]
```

### `PlayerInfo` fields

| Field | Type | Description |
|---|---|---|
| `account_id` | `int` | WG account ID |
| `name` | `str` | Player name |
| `ship_id` | `int` | GameParams ship ID |
| `team_id` | `int` | Team index |
| `relation` | `int` | 0=self, 1=ally, 2=enemy |
| `entity_id` | `int` | In-battle entity ID |
| `clan_tag` | `str` | Clan abbreviation |
| `clan_color` | `int` | Clan tag display color as packed RGB (0 = no custom color) |
| `max_health` | `int` | Ship max health |
| `is_bot` | `bool` | Whether player is a bot |
| `ship_config` | `ShipConfig \| None` | Parsed ship loadout (modules, upgrades, signals, camo) |
| `crew_id` | `int` | GameParams ID of the captain |

---

## Event Types

All events inherit from `GameEvent(timestamp, entity_id, raw_data)`.

| Event class | Key fields | Source |
|---|---|---|
| `PositionEvent` | `x y z yaw speed is_alive` | Position packet (0x0A) |
| `DamageEvent` | `target_id damage damage_type ammo_id attacker_id` | `receiveDamagesOnShip` |
| `DamageReceivedStatEvent` | `target_id attacker_id damage weapon_type` | `receiveDamageStat` |
| `DeathEvent` | `victim_id killer_id death_reason` | `kill` / `receiveVehicleDeath` |
| `ShotEvent` | `owner_id params_id salvo_id shot_count` | `receiveArtilleryShots` |
| `ShotCreatedEvent` | `shot_id owner_id spawn_x/y/z target_x/y/z speed server_time_left` | Per-shell from salvo |
| `ShotDestroyedEvent` | `shot_id owner_id hit_type impact_x/y/z` | `receiveShotKills` |
| `TorpedoCreatedEvent` | `shot_id owner_id x y z direction_x/y/z armed` | `receiveTorpedoes` |
| `CapturePointUpdateEvent` | `zone_entity_id team_id radius capture_points capture_speed` | InteractiveZone property |
| `ScoreUpdateEvent` | `battle_stage time_left teams` | BattleLogic property |
| `ChatEvent` | `sender_id channel message` | `onChatMessage` |
| `ConsumableEvent` | `vehicle_id consumable_id consumable_type is_used work_time_left` | `onConsumableUsed` |
| `AchievementEvent` | `player_id achievement_id` | `onAchievementEarned` |
| `MinimapVisionEvent` | `entity_id x z heading is_visible` | `updateMinimapVisionInfo` |
| `ScoutingDamageEvent` | `victim_id spotter_id amount weapon_type` | Avatar stats methods |
| `CapContestEvent` | `cap_index vehicle_id is_entering` | Avatar stats methods |
| `SquadronEvent` | `squadron_id action owner_id plane_type` | Avatar receive_* squadron methods |
| `AirSupportEvent` | `vehicle_id params_id position` | `activateAirSupport` |
| `RibbonEvent` | `ribbon_id ribbon_name count derived` | `privateVehicleState.ribbons` / derived |
| `PropertyUpdateEvent` | `entity_type property_name value` | Any entity property change |
| `RawEvent` | `packet_type method_name property_name` | Unmatched packets |

`ShotCreatedEvent` and `ShotDestroyedEvent` share a `shot_id` for correlation.

---

## State Tracking

The `GameStateTracker` records every entity property change with its timestamp. State queries reconstruct a snapshot by replaying the change history up to time `t`.

```python
# Full snapshot: all ships + battle state at t=120s
state = replay.state_at(120.0)
state.timestamp            # 120.0
state.ships                # dict[entity_id, ShipState]
state.battle.time_left     # seconds remaining
state.battle.team_scores   # {0: 450, 1: 320}
state.battle.capture_points  # list[CapturePointState]

# Single ship
ship = replay.ship_state(entity_id=511260, t=120.0)
ship.health                # current HP
ship.max_health            # maximum HP
ship.regeneration_health   # HP recoverable by Repair Party
ship.is_alive              # bool
ship.position              # (x, y, z) world coordinates
ship.yaw                   # heading in radians
ship.speed                 # current speed
ship.team_id
ship.burning_flags         # bitmask of active fire zones
ship.visibility_flags      # spotted status bitmask

# Battle state only
battle = replay.battle_state(120.0)
battle.time_left
battle.team_scores         # {team_id: score}
battle.battle_stage
battle.battle_result_winner
```

Position interpolation is not built into `ship_state()` — the returned position is the last known value at or before `t`. If you need smooth interpolation, query positions from `PositionEvent` objects directly.

---

## Architecture

```
wows-gamedata/
  entity_defs/*.def + alias.xml
        |
        v
  AliasRegistry        (resolves Simple/FIXED_DICT/ARRAY/TUPLE/USER_TYPE aliases)
        |
  DefLoader            (parses .def XML, merges interfaces)
        |
  EntityRegistry       (indexes entities, methods, properties; sort_size)
        |
  SchemaBuilder        (builds construct binary parsers on demand)
        |
.wowsreplay file
        |
        v
  ReplayReader         (extracts JSON headers, Blowfish ECB decrypt, zlib decompress)
        |
  PacketDecoder        (12-byte header: payload_size u32 + packet_type u32 + clock f32)
        |       \
        |     GameStateTracker  (property history per entity, state_at() queries)
        |
  EventStream          (method + property factories → typed GameEvent objects)
        |
  ParsedReplay         (meta, players, events, packets, state queries)
```

Packet header format (verified): `payload_size(u32 LE) + packet_type(u32 LE) + clock(f32 LE)` — 12 bytes.

---

## Gamedata

The parser reads entity definitions from [wows-gamedata](https://github.com/toalba/wows-gamedata), a companion repository with all game data automatically extracted and versioned.

```bash
git clone https://github.com/toalba/wows-gamedata.git
```

Key paths used by the parser:

| Path | Contents |
|---|---|
| `data/scripts_entity/entity_defs/` | `.def` XML files (14 entities, 22 interfaces) + `alias.xml` |
| `data/scripts_decrypted/extracted_constants.json` | ~39,000 constants (ribbon IDs, weapon types, death reasons) |
| `data/spaces/<map_name>/minimap.png` | Minimap image per map |
| `data/spaces/<map_name>/space.settings` | Map world bounds (minX/maxX/minY/maxY) |
| `data/content/GameParams.data` | Ship stats and names (Blowfish-encrypted pickle) |

### Automated patch pipeline

The gamedata repository is maintained by a GitHub Actions pipeline running on a self-hosted runner with the game client installed:

1. Every 6 hours, the pipeline compares the installed Steam build ID against the remote.
2. On a new patch, it re-extracts all assets via `wowsunpack`, decrypts scripts, diffs against the previous version, and creates a tagged release.
3. Enum shifts (inserted or removed enum members) are detected and flagged in `diff.json`.

Because the parser derives all schemas from the `.def` files at runtime, no code changes are needed when WoWs updates — a `git pull` on the gamedata repo is sufficient.

---

## Development

```bash
# Clone and install in dev mode (uv recommended)
git clone https://github.com/toalba/wows-replay-parser.git
cd wows-replay-parser
uv pip install -e ".[dev,cli]"

# Run tests
pytest

# Lint
ruff check src/

# Type check
mypy src/
```

**Requirements:** Python >= 3.11

**Dependencies:** `construct`, `lxml`, `pycryptodome`

**Dev dependencies:** `pytest`, `ruff`, `mypy`

---

## License

MIT
