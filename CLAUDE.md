# wows-replay-parser

## Source of Truth Rules

**The `.def` files and `alias.xml` are the single source of truth** for all entity
definitions, property names, field names, method signatures, type structures, and
entity type mappings. This applies to every entity in `entities.xml`.

When implementing or debugging any feature:
1. Read the actual `.def` file and `alias.xml` FIRST — do not rely on field names,
   type structures, or entity descriptions written elsewhere in this document
2. If this document contradicts a `.def` file or `alias.xml`, the document is WRONG —
   fix the document, do not work around the discrepancy
3. If a field name, type, or structure is not in the `.def`/alias files, it does not
   exist — do not invent properties based on assumptions
4. The renderer must never work around parser bugs — if data is wrong, fix the parser

File locations:
- Entity definitions: `wows-gamedata/data/scripts_entity/entity_defs/*.def`
- Interface definitions: `wows-gamedata/data/scripts_entity/entity_defs/interfaces/*.def`
- Type aliases: `wows-gamedata/data/scripts_entity/entity_defs/alias.xml`
- Entity type ID mapping: `wows-gamedata/data/scripts_entity/entities.xml`

## Debugging Principle: Never conclude data doesn't exist

When investigating a feature and our parser doesn't produce expected data:

1. **NEVER conclude "the replay doesn't contain this data" or "the server doesn't send this."**
   Our parser has known gaps (missing entity types, unparsed inline state, incomplete
   NestedProperty routing). Absence of data in our output means our parser probably
   isn't reading it — not that it isn't there.

2. **Always verify against wows-toolkit first.** The Rust reference implementation at
   `/home/claude/wows-toolkit` is a working parser. Search its codebase to see if it
   handles the feature. If wows-toolkit reads the data, it's in the replay and our
   parser has a bug.

   ```bash
   grep -rn "KEYWORD" /home/claude/wows-toolkit/crates/wows-replays/src/
   grep -rn "KEYWORD" /home/claude/wows-toolkit/crates/minimap-renderer/src/
   ```

3. **Check the .def files and alias.xml** before concluding a property or method
   doesn't exist. These are the source of truth (see Source of Truth Rules above).

4. **When logging shows zero events, suspect the logging** — not the data source.
   Add logging at progressively lower levels until you find where the data drops:
   - Raw packet level (do packets with relevant entity_ids exist?)
   - Entity routing level (does the entity exist in our registry?)
   - Property/method resolution level (does the index resolve to the right name?)
   - Tracker level (does the decoded data reach the state tracker?)

5. **Never run validation tests with workarounds enabled.** If testing whether the
   deterministic algorithm works, disable the auto-detector. If testing whether a
   parser fix works, disable renderer fallbacks. Label every test with which
   workarounds are active.

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

### PlayerOrientation Packet (0x2C) — 32 bytes
```
pid(u32) + parent_id(u32) + position(3xf32) + rotation(3xf32)
```
BigWorld does NOT send Position (0x0A) packets for the self player's own entity. Instead, PlayerOrientation carries the self ship's position. Only `parent_id==0` entries are the actual ship position (parent_id!=0 is camera on attached object). Appears twice per tick.

### NonVolatilePosition Packet (0x2A)
Same as Position but without direction/is_on_ground. Used for smoke screens, weather zones.
```
entity_id(u32) + space_id(u32) + position(3xf32) + rotation(3xf32)
```

### ENTITY_CREATE Inline State Data Format
After the fixed header (`eid(4) + type_idx(2) + vehicle_id(4) + space_id(4) + pos(12) + rot(12) + state_len(4)` = 42 bytes), the inline state data encodes properties as:
```
num_props(u8) + [prop_id(u8) + typed_value] × num_props
```
Properties are in sort_size order (smallest first). For Vehicle entities, this is how `teamId` (index 5, INT8, 1 byte) and `owner` (index 36, ENTITY_ID/INT32, 4 bytes) are decoded. Variable-length properties (sort_size=65535) have a u32 length prefix before the data.

**Important:** This is NOT a flag table — it's prop_id followed by the actual typed value bytes. Getting this wrong produces garbage values.

### Key Alias Structs (from real alias.xml)
- **SHOT**: pos(V3), pitch(F), speed(F), tarPos(V3), shotID(U16), gunBarrelID(U16), serverTimeLeft(F), shooterHeight(F), hitDistance(F)
- **SHOTS_PACK**: paramsID(U32), ownerID(I32), salvoID(I32), shots(ARRAY<SHOT>)
- **SHOTKILL**: pos(V3), shotID(U16), terminalBallisticsInfo(FIXED_DICT)
- **TORPEDO**: pos(V3), dir(V3), shotID(U16), armed(BOOL), maneuverDump(AllowNone), acousticDump(AllowNone)
- **TORPEDOES_PACK**: paramsID(U32), ownerID(I32), salvoID(I32), skinID(U32), torpedoes(ARRAY<TORPEDO>)
- **BATTLE_LOGIC_STATE**: attentionMarkers, clientAnimations, controlPoints(ARRAY<ENTITY_ID>), diplomacy, uiInfo, physics, respawns
- **INTERACTIVE_ZONE_STATE**: controlPoint(CONTROL_POINT_STATE), captureLogic(CAPTURE_LOGIC_STATE, AllowNone)
- **CAPTURE_LOGIC_STATE**: progress(F), invaderTeam(TEAM_ID), bothInside(BOOL), hasInvaders(BOOL), isEnabled(BOOL), isVisible(BOOL), captureTime(F), captureSpeed(F)
- **CONTROL_POINT_STATE**: buoyVisualId(GAMEPARAMS_ID), nextControlPoint(ENTITY_ID), type(U8), timerName(STRING), index(I8)
- **TEAMS_DEF**: default(U8), teams(ARRAY<TEAM_STATE>)

### Vehicle ALL_CLIENTS Properties (sort_size order, 54 total)
```
1-byte:  [0]hasAirTargetsInRange [1]isAntiAirMode [2]buoyancyCurrentState [3]buoyancyRudderIndex
         [4]isOnForsage [5]teamId [6]uiEnabled [7]isAlive [8]speedSignDir [9]enginePower
         [10]engineDir [11]ignoreMapBorders [12]isBot [13]isFogHornOn [14]blockedControls
         [15]isInvisible [16]hasActiveMainSquadron [17]isInRageMode [18]oilLeakState
2-byte:  [19]burningFlags [20]targetLocalPos [21]torpedoLocalPos [22]laserTargetLocalPos
         [23]waveLocalPos [24]weaponLockFlags [25]serverSpeedRaw [26]respawnTime
4-byte:  [27]airDefenseDispRadius [28]health [29]regenerationHealth [30]regeneratedHealth
         [31]maxHealth [32]buoyancyCurrentWaterline [33]regenCrewHpLimit [34]buoyancy
         [35]visibilityFlags [36]owner [37]selectedWeapon [38]maxServerSpeedRaw
         [39]draught [40]ruddersAngle [41]deepRuddersAngle
8-byte:  [42]visibilityTime
variable:[43-53] airDefenseTargetIds, antiAirAuras, effects, sounds, shipConfig,
         crewModifiersCompactParams, debugText, miscsPresetsStatus, triggeredSkillsData,
         deathSettings, state
```

### Avatar ALL_CLIENTS Properties (sort_size order, 21 total)
```
1-byte:  [0]useATBAandAirDefense [1]teamId [2]hasFullPing [3]isFlyMode [4]intuitionActive
         [5]allyTargetsCapture [6]isAlive [7]isInMinefield
2-byte:  [8]willBeDeadAtTime [9]playerModeState
4-byte:  [10]ownShipId [11]selectedWeapon [12]selectedTorpedoGroup
8-byte:  [13]attrs
12-byte: [14]vehiclePosition [15]visibilityDistances
92-byte: [16]weatherParams [17]squadronWeatherParams
variable:[18]privateBattleLogicState [19]privateVehicleState [20]spottedEntities
```

### Roster: Vehicle-to-Player Matching (FIXED)
**Status: ID-based matching via `onArenaStateReceived` — working correctly.**

#### onArenaStateReceived Wire Format

The `onArenaStateReceived` method (Avatar.def) arrives as an ENTITY_METHOD (0x08) packet:
```
Packet header (12 bytes):
  payload_size(u32 LE) + packet_type(u32 LE, 0x08) + clock(f32 LE)

Method payload:
  entity_id(u32) + method_id(u32) + payload_length(u32)  ← 12-byte method header
  arenaUniqueId(INT64, 8 bytes)                          ← fixed arg
  teamBuildTypeId(INT8, 1 byte)                          ← fixed arg
  preBattlesInfo(BLOB)                                    ← pickle: dict with preBattle info
  playersStates(BLOB)                                     ← pickle: list of 24 player tuples
  botsStates(BLOB)                                        ← pickle: list of bot tuples (often empty)
  observersState(BLOB)                                    ← pickle: empty list
  buildingsInfo(BLOB)                                     ← pickle: empty list
```

#### BLOB Encoding (BigWorld VariableLengthHeaderSize)

Each BLOB arg uses BigWorld's variable-length prefix encoding. The method's `variable_length_header_size` (vlh) determines the base prefix size:

**vlh=1 (default, used by onArenaStateReceived):**
```
if first_byte < 0xFF:  length = first_byte                          (1 byte prefix)
if first_byte == 0xFF: length = next_u16                            (3 bytes prefix)
if first_byte == 0xFF and next_u16 == 0xFFFF: length = next_u32    (7 bytes prefix)
```

**vlh=2:** Same pattern but starts with u16 and escalates to u32.
**vlh=4:** Always u32 (no escalation).

This differs from the standard `construct` schema which assumes all BLOBs have a u32 length prefix. The schema builder's `cs.Prefixed(cs.Int32ul, cs.GreedyBytes)` for BLOB types is therefore **wrong** for methods with vlh < 4. This is why the construct-based schema fails to parse `onArenaStateReceived` args (the construct parser silently fails, leaving `method_args = None`).

In practice, the roster code bypasses the length prefix encoding entirely by scanning the raw payload for pickle protocol 2 headers (`\x80\x02`) and deserializing sequentially. Each pickle is self-delimiting (ends at the STOP opcode `\x2E`), so boundaries are unambiguous.

#### Pickle Deserialization (Python 2 → Python 3)

The pickle data is created by the WoWs game server running **Python 2.7**, using **pickle protocol 2**.

Python 2 pickle specifics:
- `str` objects are serialized as raw bytes (no encoding metadata)
- Python 3's `pickle.loads()` must be told how to decode these bytes → use `encoding='latin-1'`
- `latin-1` is safe because it maps 0x00-0xFF 1:1 to Unicode — it never raises, even for Cyrillic/CJK player names stored as UTF-8 byte sequences inside Python 2 `str` objects
- The pickle references game-specific classes (e.g. `CamouflageInfo`) that don't exist in our code → use a custom `Unpickler.find_class()` that creates dummy `dict` subclasses

This `latin-1` + safe unpickler approach applies to **any BLOB containing Python 2 pickle data** in the replay (e.g. `onGameRoomStateChanged`, `receivePlayerData`), not to the binary packet stream itself. The replay's packet headers, entity properties, and construct-based schemas use standard LE binary encoding, not pickle.

#### Pickle Content: Player Data Structure

Each player in the `playersStates` pickle is a list of `(int_key, value)` tuples — NOT a dict:
```python
[
  (0, 502524043),        # accountDBID
  (1, True),             # antiAbuseEnabled
  (2, 1041006),          # avatarId
  (3, CamouflageInfo{}), # camouflageInfo (game class → dummy dict)
  (4, 11776947),         # clanColor
  (5, 12345),            # clanID
  (6, 'TTT'),            # clanTag
  ...
  (11, 502524043),       # id ← matches JSON header vehicles[].id
  ...
  (25, 'Dutch_Elephant'),# name
  ...
  (33, 1041009),         # shipId ← Vehicle entity_id in game world
  ...
  (36, 1),               # teamId
  ...
]
```

Full key maps for players (38 keys) and bots (28 keys, different indices) are in `roster.py`.

#### Matching Chain

1. Find the arena state packet by content probing (scan early ENTITY_METHOD packets for valid pickle player lists)
2. Deserialize `playersStates` pickle with `encoding='latin-1'` + safe unpickler
3. Convert each player's `(int_key, value)` tuples to dicts using the key map
4. Match to JSON header: `arena_player["id"] == meta_vehicle["id"]` (AccountId)
5. Use `arena_player["shipId"]` as the Vehicle entity_id for all subsequent lookups

#### Method Ordering (Verified 100% Correct)

Method indices are assigned by `std::stable_sort` on `streamSize` (BigWorld v14.4.1
convention). Our `compute_method_sort_size()` + Python stable sort produces the exact
same ordering as the engine. **Verified 10/10 against real replay data** (both unique
sort_size methods and tie groups).

Key sort rules:
- Fixed-size methods first (ascending by arg byte sum)
- Variable-size methods second (ascending by VLH: 1, then 2, then 4)
- Ties broken by declaration order (depth-first interface merge = stable sort)

Critical detail: types with `<implementedBy>` tag → `streamSize() = -1` (variable),
regardless of field contents. Our `compute_type_sort_size()` handles this via
`TypeAlias.has_implemented_by`. 16 types in alias.xml have this tag.

The **auto-detector** (`method_id_detector.py`) is still enabled by default but is now
redundant for Avatar and Vehicle. It may still help with Account entity tie groups
(lobby/pre-battle methods) where the declaration order has not been verified.

#### Base Player Entity Type

`BASE_PLAYER_CREATE` (0x00) is a WoWS-custom packet. The `type_idx` field does NOT
map to `entities.xml`. The decoder resolves the type dynamically by finding the entity
type with the most ClientMethods (= Avatar, 178 methods). This entity receives all
player-side method calls including combat events, vision updates, and chat.

### Method Index Sizing
BigWorld uses variable-size method indices depending on total method count:
- ≤ 256 methods: uint8
- \> 256 methods: uint16
Check entity's total ClientMethods count (including inherited from interfaces).

### Interface Merging
.def files use `<Implements>` to include interface definitions. Methods/properties from interfaces are prepended. Sorting happens AFTER merging.

### VariableLengthHeaderSize
Some methods have `<VariableLengthHeaderSize>` (1=uint8, 2=uint16, 4=uint32) affecting payload size encoding. Notable: `receiveDamagesOnShip` (2), `onGameRoomStateChanged` (2), `receiveHitLocationsInitialState` (2).

### Entity Type ID Mapping (from entities.xml)
```
0=Avatar  1=Vehicle  2=Account  3=SmokeScreen  4=OfflineEntity
5=VehicleAppearance  6=Login  7=BattleEntity  8=Building  9=MasterChanger
10=BattleLogic  11=ReplayLeech  12=ReplayConnectionHandler
13=InteractiveZone  14=InteractiveObject
```
Note: type_id auto-detector infers this from packet analysis, not from entities.xml directly.

### Feature Data Path Status (audited 2026-03-28)

**Decode rate: 100%** (37,307/37,309 method calls in test replay). All 178 Avatar
and 83 Vehicle ClientMethods decode successfully. Method index assignment verified
correct against real replay data.

| Feature | Status | Entity → Property/Method |
|---------|--------|--------------------------|
| Ship positions | WORKING | Vehicle → Position (0x0A), Avatar → PlayerOrientation (0x2C) |
| Ship health | WORKING | Vehicle → health/maxHealth properties |
| Ship deaths | WORKING | Avatar → receiveVehicleDeath, Vehicle → kill |
| Player roster | WORKING | Avatar → onArenaStateReceived (pickle) |
| Team scores | WORKING | BattleLogic → teams property (TEAMS_DEF) |
| Chat messages | WORKING | Avatar → onChatMessage (35/37 = 94.6%, 2 encoding edge cases) |
| Consumables | WORKING | Vehicle → onConsumableUsed, setConsumables, onConsumableInterrupted |
| Ribbons | WORKING | Derived from hit events (no network method) |
| Minimap vision | WORKING | Avatar → updateMinimapVisionInfo (both args) |
| Artillery/shells | WORKING | Avatar → receiveArtilleryShots, receiveShotKills, receiveShellInfo |
| Torpedoes | WORKING | Avatar → receiveTorpedoes, receiveTorpedoArmed/Sync/Direction |
| Depth charges | WORKING | Avatar → receiveDepthChargesPacks |
| Plane projectiles | WORKING | Avatar → receivePlaneProjectilePack |
| Explosions | WORKING | Avatar → receiveExplosions |
| Damage stats | WORKING | Avatar → receiveDamageStat (pickle), receiveShellInfo |
| Damage on ship | WORKING | Vehicle → receiveDamagesOnShip (ARRAY<DAMAGES>) |
| Gun state | WORKING | Vehicle → syncGun (yaw, pitch, reload, ammo) |
| Torpedo tubes | WORKING | Vehicle → syncTorpedoTube, syncTorpedoState |
| Weapon switching | WORKING | Vehicle → setAmmoForWeapon, shootOnClient, shootATBAGuns |
| Squadrons | WORKING | Avatar → 16 receive_* methods (add/remove/update/health/death/state) |
| Air support | WORKING | Avatar → activateAirSupport, deactivateAirSupport |
| Game room state | WORKING | Avatar → onGameRoomStateChanged (pickle, 88 updates/game) |
| Arena state | WORKING | Avatar → onArenaStateReceived (pickle, full player roster) |
| Battle end | WORKING | Avatar → onBattleEnd |
| Cooldowns | WORKING | Avatar → updateCoolDown |
| Ship physics | WORKING | Vehicle → syncShipPhysics (pickle blob) |
| Hit locations | WORKING | Vehicle → receiveHitLocationStateChange, receiveHitLocationsInitialState |
| Achievements | WORKING | Avatar → onAchievementEarned |
| Capture zones | PARTIAL | InteractiveZone → componentsState (field names fixed, inline state not parsed) |
| Smoke screens | NOT IMPL | SmokeScreen entity — positions tracked, no state model |
| Buildings | NOT IMPL | Building entity — no state model |

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
