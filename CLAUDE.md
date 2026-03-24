# wows-replay-parser

## Project Overview

World of Warships `.wowsreplay` file parser with dynamic schema loading from [wows-gamedata](https://github.com/toalba/wows-gamedata). No hardcoded schemas — new patches only require a `git pull` on the gamedata repo.

**Goal:** General-purpose replay parsing library feeding a minimap replay renderer (WG bounty, deadline April 20, 2026). The parser decodes ALL packets and tracks entity state over time — the renderer is ONE consumer, but the parser must serve future consumers (stat tools, damage breakdowns, data exports) equally.

## Architecture

```
src/wows_replay_parser/
├── gamedata/          # Entity definition loading + schema building
│   ├── alias_registry.py   # Parses alias.xml → type alias lookup (all 5 patterns)
│   ├── def_loader.py       # Parses .def XML files → EntityDef structs (with interface merging)
│   ├── entity_registry.py  # Central indexed registry, sort_size computation
│   ├── schema_builder.py   # Builds `construct` binary schemas dynamically
│   └── blob_decoders.py    # BLOB decoders (zipped, msgpack, pickle)
├── replay/            # .wowsreplay container format
│   └── reader.py           # JSON headers + Blowfish ECB decrypt + zlib decompress
├── packets/           # BigWorld network packet decoding
│   ├── types.py            # PacketType enum (24 types) + Packet dataclass
│   ├── decoder.py          # Reads packet stream, 7 handlers, entity tracking
│   └── type_id_detector.py # Auto-detects type_id → entity_name mapping
├── state/             # Entity state tracking over time (NEW)
│   ├── models.py           # ShipState, BattleState, CapturePointState, GameState, PropertyChange
│   └── tracker.py          # GameStateTracker — property history + state_at() queries
├── events/            # Typed game event stream
│   ├── models.py           # All event types (Position, Damage, Death, Shot, Torpedo, Cap, Score, etc.)
│   └── stream.py           # Packet → Event transformation with method+property factories
├── api.py             # Top-level parse_replay() + ParsedReplay with state queries
├── roster.py          # Player roster enrichment (JSON header + entity matching)
├── ribbons.py         # Ribbon derivation from hit events (P2)
├── merge.py           # Dual perspective replay merging (P2)
└── cli.py             # Click CLI (info, parse, events, state commands)
```

## Data Flow

1. **wows-gamedata repo** (entity_defs/*.def + alias.xml)
2. → `AliasRegistry.from_file()` resolves type aliases
3. → `DefLoader.load_all()` parses .def XML into `EntityDef` structs (with interface merging)
4. → `EntityRegistry` indexes entities, methods, properties (sorted by sort_size)
5. → `SchemaBuilder` creates `construct` binary parsers on-the-fly
6. **Replay file** (.wowsreplay)
7. → `ReplayReader.read()` extracts JSON headers + Blowfish decrypts + zlib decompresses
8. → `type_id_detector.detect_type_id_mapping()` auto-maps type indices to entity names
9. → `PacketDecoder.decode_stream()` uses schemas to decode packets, feeds `GameStateTracker`
10. → `EventStream.process()` maps packets to typed game events (method + property events)
11. → `parse_replay()` returns `ParsedReplay` with events, packets, and state query API

## Key References

- **Entity defs**: `wows-gamedata/data/scripts_entity/entity_defs/` — 14 entity types, 22 interfaces
- **alias.xml**: Type aliases — Simple, FIXED_DICT, ARRAY, TUPLE, USER_TYPE patterns
- **Decompiled client scripts**: `wows-gamedata/data/scripts_decrypted_decompiled/wows_replays/` — ground truth for event structures
- **Extracted constants**: `wows-gamedata/data/scripts_decrypted/extracted_constants.json` — ~39k constants (ribbon IDs, weapon types, death reasons, etc.)
- **landaire/wows-toolkit**: Actively maintained Rust implementation — **primary reference for packet format**
- **Monstrofil/replays_unpack**: Python reference (unmaintained)

## Critical Implementation Notes

### Packet Header Format (Verified)
12 bytes: `payload_size(u32 LE) + packet_type(u32 LE) + clock(f32 LE)`

### Position Packet (0x0A) — 45 bytes
```
entity_id(u32) + space_id(u32) + position(3xf32) + direction(3xf32) + rotation(3xf32) + is_on_ground(u8)
```

### Key Alias Structs (from real alias.xml)
- **SHOT**: pos(V3), pitch(F), speed(F), tarPos(V3), shotID(U16), gunBarrelID(U16), serverTimeLeft(F), shooterHeight(F), hitDistance(F)
- **SHOTS_PACK**: paramsID(U32), ownerID(I32), salvoID(I32), shots(ARRAY<SHOT>)
- **SHOTKILL**: pos(V3), shotID(U16), terminalBallisticsInfo(FIXED_DICT)
- **TORPEDO**: pos(V3), dir(V3), shotID(U16), armed(BOOL), maneuverDump(AllowNone), acousticDump(AllowNone)
- **TORPEDOES_PACK**: paramsID(U32), ownerID(I32), salvoID(I32), skinID(U32), torpedoes(ARRAY<TORPEDO>)
- **BATTLE_LOGIC_STATE**: attentionMarkers, clientAnimations, controlPoints(ARRAY<ENTITY_ID>), diplomacy, uiInfo, physics, respawns
- **INTERACTIVE_ZONE_STATE**: controlPoint(CONTROL_POINT_STATE), captureLogic(CAPTURE_LOGIC_STATE, AllowNone)
- **CAPTURE_LOGIC_STATE**: capturePoints(I16), ownerId(U32), teamId(I8), captureSpeed(F)
- **TEAMS_DEF**: default(U8), teams(ARRAY<TEAM_STATE>)

### Vehicle Properties (from Vehicle.def + HitLocationManagerOwner interface)
- health(F32), maxHealth(F32), regenerationHealth(F32), regeneratedHealth(F32)
- isAlive(BOOL), teamId(INT8), visibilityFlags(UINT32), burningFlags(UINT16)
- serverSpeedRaw(UINT16), isOnForsage(BOOL), enginePower(UINT8)

### Method Index Sizing
BigWorld uses variable-size method indices depending on total method count:
- ≤ 256 methods: uint8
- \> 256 methods: uint16
Check entity's total ClientMethods count (including inherited from interfaces).

### Interface Merging
.def files use `<Implements>` to include interface definitions. Methods/properties from interfaces are prepended. Sorting happens AFTER merging.

### VariableLengthHeaderSize
Some methods have `<VariableLengthHeaderSize>` (1=uint8, 2=uint16, 4=uint32) affecting payload size encoding. Notable: `receiveDamagesOnShip` (2), `onGameRoomStateChanged` (2), `receiveHitLocationsInitialState` (2).

### Map Coordinate System
- Map bounds from `wows-gamedata/data/spaces/<map_name>/space.settings` — XML with `<bounds minX maxX minY maxY />`
- Minimap PNG at `data/spaces/<map_name>/minimap.png`
- World coords (origin at center, ±half_map_size) → pixel coords (origin at top-left)

## Hard Constraints

1. **General-purpose parser** — decode ALL packets, not just renderer-needed ones
2. **No data loss** — raw payload accessible; unknown packets → RawEvent, never silently dropped
3. **Additive events** — new event types don't break existing ones
4. **Complete entity state history** — every property change with timestamp, not just latest value
5. **No renderer dependencies** — parser is standalone

## Commands

```bash
# Install in dev mode
uv pip install -e ".[dev,cli]"

# Run tests
pytest

# Lint
ruff check src/

# Type check
mypy src/

# CLI
wowsreplay info replay.wowsreplay
wowsreplay parse replay.wowsreplay --gamedata ./wows-gamedata/data/scripts_entity/entity_defs
wowsreplay events replay.wowsreplay --gamedata ./wows-gamedata/data/scripts_entity/entity_defs

# Top-level API
from wows_replay_parser import parse_replay
replay = parse_replay("battle.wowsreplay", "./wows-gamedata/data/scripts_entity/entity_defs")
replay.state_at(120.5)           # GameState snapshot
replay.ship_state(entity_id, t)  # ShipState
replay.events_of_type(ShotCreatedEvent)
```

## Gamedata Repo

The `wows-gamedata/` subdir is a clone of github.com/toalba/wows-gamedata. Automated pipeline checks Steam every 6h, auto-extracts on new patches. Key paths:
- Entity defs: `data/scripts_entity/entity_defs/`
- Minimaps: `data/spaces/<map_name>/minimap.png`
- Constants: `data/scripts_decrypted/extracted_constants.json`
- Decompiled events: `data/scripts_decrypted_decompiled/wows_replays/`
- GameParams: `data/content/GameParams.data` (Blowfish-encrypted pickle, needs `wowsunpack`)

## Ribbon Constants (from extracted_constants.json)

```
0=MAIN_CALIBER  1=TORPEDO  2=BOMB  3=PLANE  4=CRIT  5=FRAG
6=BURN  7=FLOOD  8=CITADEL  9=BASE_DEFENSE  10=BASE_CAPTURE
13=SECONDARY_CALIBER  14=OVER_PEN  15=PENETRATION  16=NO_PEN(shatter)
```

## Weapon Types (SHIP_WEAPON_TYPES)

```
0=ARTILLERY  1=ATBA  2=TORPEDO  3=AIRPLANES  4=AIRDEFENCE
5=DEPTH_CHARGES  6=PINGER  12=AIR_SUPPORT  14=MISSILES  100=SQUADRON
```
