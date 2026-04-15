# wows-replay-parser — Internal Notes

Architectural reference for maintainers. User-facing docs live in `README.md`;
end-user issues in `KNOWN_ISSUES.md`; release notes in `CHANGELOG.md`.

---

## Project Overview

Python library that parses World of Warships `.wowsreplay` files by deriving all
binary schemas at runtime from the [wows-gamedata](https://github.com/toalba/wows-gamedata)
entity definitions. No hardcoded schemas — new patches only require a `git pull`
on the gamedata repo.

Design goal: a **general-purpose** replay parser. Every packet is decoded, every
entity method call and property update is captured and queryable. The minimap
renderer is one consumer; stat tools, data exports, and damage breakdowns are
equally supported. Do not shortcut decoding based on any single consumer.

---

## Source of Truth Rules

**The `.def` files and `alias.xml` are the single source of truth** for all entity
definitions, property names, field names, method signatures, type structures, and
entity type mappings. This applies to every entity in `entities.xml`.

When implementing or debugging any feature:

1. Read the actual `.def` file and `alias.xml` FIRST — do not rely on field names,
   type structures, or entity descriptions written elsewhere in this document.
2. If this document contradicts a `.def` file or `alias.xml`, the document is WRONG —
   fix the document, do not work around the discrepancy.
3. If a field name, type, or structure is not in the `.def`/alias files, it does not
   exist — do not invent properties based on assumptions.
4. The renderer must never work around parser bugs — if data is wrong, fix the parser.

File locations:

- Entity definitions: `wows-gamedata/data/scripts_entity/entity_defs/*.def`
- Interface definitions: `wows-gamedata/data/scripts_entity/entity_defs/interfaces/*.def`
- Type aliases: `wows-gamedata/data/scripts_entity/entity_defs/alias.xml`
- Entity type ID mapping: `wows-gamedata/data/scripts_entity/entities.xml`

---

## Debugging Principle: Never conclude data doesn't exist

When investigating a feature and our parser doesn't produce the expected data:

1. **Never conclude "the replay doesn't contain this data" or "the server doesn't
   send this."** Our parser has known gaps (missing entity types, unparsed inline
   state, incomplete nested-property routing). Absence of data in our output usually
   means our parser isn't reading it — not that it isn't there.

2. **Check the `.def` files and `alias.xml`** before concluding a property or method
   doesn't exist. These are the source of truth.

3. **When logging shows zero events, suspect the logging** — not the data source.
   Add logging at progressively lower levels until you find where the data drops:
   - Raw packet level (do packets with relevant `entity_id`s exist?)
   - Entity routing level (does the entity exist in our registry?)
   - Property/method resolution level (does the index resolve to the right name?)
   - Tracker level (does the decoded data reach the state tracker?)

4. **Never run validation tests with workarounds enabled.** If testing whether the
   deterministic algorithm works, disable the auto-detector. If testing whether a
   parser fix works, disable renderer fallbacks. Label every test with which
   workarounds are active.

---

## Architecture

```
src/wows_replay_parser/
├── gamedata/            # alias_registry, def_loader, entity_registry,
│                        # schema_builder, blob_decoders
├── replay/              # reader.py — JSON headers + Blowfish ECB + zlib
├── packets/             # types, decoder, type_id_detector,
│                        # method_id_detector, nested_property,
│                        # implemented_by_parsers
├── state/               # models (ShipState/BattleState/GameState/etc.) +
│                        # tracker (GameStateTracker, state_at / iter_states)
├── events/              # models (100+ event types) + stream (factories)
├── api.py               # parse_replay() → ParsedReplay
├── roster.py            # JSON header + onArenaStateReceived pickle
├── ribbons.py           # server-authoritative + derived ribbon extraction
├── ship_config.py       # SHIP_CONFIG binary decoder
├── gamedata_sync.py     # auto-sync gamedata repo to replay version
├── merge.py             # dual perspective replay merging
└── cli.py               # Click CLI (info, parse, events, state, export)
```

### Data Flow

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

### Key Data Sources

- **Entity defs**: `wows-gamedata/data/scripts_entity/entity_defs/` — 14 entity types, 22 interfaces
- **alias.xml**: Type aliases — Simple, FIXED_DICT, ARRAY, TUPLE, USER_TYPE patterns
- **Decompiled client scripts**: `wows-gamedata/data/scripts_decrypted_decompiled/wows_replays/` — ground truth for event structures
- **Extracted constants**: `wows-gamedata/data/scripts_decrypted/extracted_constants.json` — ~39k constants (ribbon IDs, weapon types, death reasons, etc.)

---

## Critical Implementation Notes

### Packet Header Format (verified)

12 bytes: `payload_size(u32 LE) + packet_type(u32 LE) + clock(f32 LE)`.
Every packet carries a timestamp in its header — mis-parsing the header causes all
timestamps to drift.

### Packet Type Mapping (verified)

Full enum in `packets/types.py`. Common mis-mappings to avoid:

- `0x22` is **BattleResults**, not NestedPropertyUpdate (that's `0x23`).
- `0x07 = EntityProperty`, `0x08 = EntityMethod` — some older references swap these.
- `CellPlayerCreate (0x01)` MUST arrive after `BasePlayerCreate (0x00)`; the
  decoder expects base-player state to exist first.
- `0x27 = CameraMode`, not Map (Map is `0x28`).
- `0x2A = NonVolatilePosition` (SmokeScreen / weather) — not Position (0x0A).
- `0x33 = ShotTracking` (added ~Feb 2026).

### Position Packet (0x0A) — 45 bytes

```
entity_id(u32) + space_id(u32) + position(3xf32) + direction(3xf32)
  + rotation(3xf32) + is_on_ground(u8)
```

### PlayerOrientation Packet (0x2C) — 32 bytes

```
pid(u32) + parent_id(u32) + position(3xf32) + rotation(3xf32)
```

BigWorld does NOT send Position (0x0A) packets for the self player's own entity.
Instead, PlayerOrientation carries the self ship's position. Only `parent_id==0`
entries are the actual ship position (`parent_id!=0` is the camera attached to an
object). Appears twice per tick.

### NonVolatilePosition Packet (0x2A)

Same as Position but without direction/is_on_ground. Used for smoke screens and
weather zones:

```
entity_id(u32) + space_id(u32) + position(3xf32) + rotation(3xf32)
```

Without this packet, smoke positions never reach the minimap.

### Dual Position Sources

Ships have **two parallel position sources** and the parser must expose both:

1. **Position packets (0x0A)** — world coordinates in space units, with direction/rotation.
2. **`updateMinimapVisionInfo` (EntityMethod)** — normalized 11-bit coordinates
   with visibility status.

Position packets provide precise world coords; MinimapVisionInfo is authoritative
for minimap display and carries the spotted/unspotted state.

### updateMinimapVisionInfo Bitfield

32-bit `packedData`:

```
Bit  0-10:  x (11 bits)
Bit 11-21:  y (11 bits)
Bit 22-29:  heading (8 bits)
Bit 30:     unknown
Bit 31:     is_disappearing
```

Conversions:

```python
heading_degrees = raw_heading / 256.0 * 360.0 - 180.0
stored_x = raw_x / 512.0 - 1.5
stored_y = raw_y / 512.0 - 1.5
world_x  = (stored_x + 1.5) * 512.0 / 2047.0 * 5000.0 - 2500.0
world_z  = (stored_y + 1.5) * 512.0 / 2047.0 * 5000.0 - 2500.0
```

**Sentinel check:** `raw_x == 0 && raw_y == 0` is a sentinel (no valid position) —
NOT position (-2500, -2500). Without this check, ships drop to the corner.
`is_disappearing=true` with a valid position means the ship just became unspotted;
the position is valid at the moment of disappearance.

### ENTITY_CREATE Inline State Data

After the fixed header (`eid(4) + type_idx(2) + vehicle_id(4) + space_id(4) +
pos(12) + rot(12) + state_len(4)` = 42 bytes), inline state encodes properties as:

```
num_props(u8) + [prop_id(u8) + typed_value] × num_props
```

Properties are in sort_size order (smallest first). For Vehicle entities, that's
how `teamId` (index 5, INT8, 1 byte) and `owner` (index 36, ENTITY_ID/INT32,
4 bytes) are decoded. Variable-length properties (sort_size=65535) have a u32
length prefix before the data.

**Important:** This is NOT a flag table — it's prop_id followed by the actual
typed value bytes. Getting this wrong produces garbage values.

### Method Index Sizing

BigWorld uses variable-size method indices depending on total method count:

- ≤ 256 methods: uint8
- \> 256 methods: uint16

Check the entity's total ClientMethods count (including those inherited from
interfaces).

### Interface Merging

`.def` files use `<Implements>` to include interface definitions. Methods/properties
from interfaces are prepended. Sorting happens AFTER merging.

### VariableLengthHeaderSize (vlh)

Some methods have `<VariableLengthHeaderSize>` (1=uint8, 2=uint16, 4=uint32)
affecting payload size encoding. Notable: `receiveDamagesOnShip` (2),
`onGameRoomStateChanged` (2), `receiveHitLocationsInitialState` (2),
`onArenaStateReceived` (1).

### Method Ordering (verified)

Method indices are assigned by `std::stable_sort` on `streamSize` (BigWorld v14.4.1
convention). Our `compute_method_sort_size()` + Python stable sort produces the
exact same ordering as the engine. Verified 10/10 against real replay data.

Key sort rules:

- Fixed-size methods first (ascending by arg byte sum).
- Variable-size methods second (ascending by vlh: 1, then 2, then 4).
- Ties broken by declaration order (depth-first interface merge = stable sort).

Critical detail: types with an `<implementedBy>` tag → `streamSize() = -1`
(variable) regardless of field contents. `compute_type_sort_size()` handles this
via `TypeAlias.has_implemented_by`. 16 types in `alias.xml` carry this tag.

The **auto-detector** (`method_id_detector.py`) is still enabled by default but
is now redundant for Avatar and Vehicle. It may still help with Account entity
tie groups (lobby/pre-battle methods) where the declaration order has not been
verified.

### Base Player Entity Type

`BASE_PLAYER_CREATE` (0x00) is a WoWS-custom packet. The `type_idx` field does NOT
map to `entities.xml`. The decoder resolves the type dynamically by finding the
entity type with the most ClientMethods (= Avatar, 178 methods). This entity
receives all player-side method calls including combat events, vision updates,
and chat.

### Entity Type ID Mapping (from entities.xml)

```
0=Avatar  1=Vehicle  2=Account  3=SmokeScreen  4=OfflineEntity
5=VehicleAppearance  6=Login  7=BattleEntity  8=Building  9=MasterChanger
10=BattleLogic  11=ReplayLeech  12=ReplayConnectionHandler
13=InteractiveZone  14=InteractiveObject
```

Note: the type_id auto-detector infers this from packet analysis, not from
`entities.xml` directly.

### BattleStage Enum is Inverted

```
BattleStage::Battle  (raw 1) = PRE-BATTLE COUNTDOWN
BattleStage::Waiting (raw 0) = BATTLE ACTIVE
```

Counter-intuitive: "Battle" = countdown, "Waiting" = match in progress.

### Dead Ship Position Cache

On kill events the current ship position must be cached (last Position packet +
last minimap-vision position as fallback) — otherwise dead ships simply vanish
from the minimap.

### Game Constants Must Match Replay Version

`CONSUMABLE_IDS`, `BATTLE_STAGES`, ribbon IDs, weapon type enums, and death
reasons all shift between patches. Our `extracted_constants.json` in the gamedata
repo is regenerated on every patch by the automated pipeline. `gamedata_sync.py`
checks out the correct tag for the replay's game version (with closest-tag
fallback by build-ID delta).

---

## Key Alias Structs (from real alias.xml)

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

### Projectile gotchas

- **Shells:** `receiveArtilleryShots` supplies `pos`, `tarPos`, `speed`, `pitch`,
  `shotID`, `serverTimeLeft`, `hitDistance`, `shooterHeight`, `gunBarrelID`.
  Flight time = `dist(origin, target) / speed`. Without speed/time data, animated
  tracers are impossible.
- **Torpedoes:** no `tarPos`. `pos` (origin) + `dir` (direction vector whose
  magnitude = speed in m/s). Current position = `origin + dir * elapsed`.
  S-turn torps (`maneuverDump != None`) require arc integration during the turn
  and then a straight line from the end of the arc. Drawing all torps as
  straight lines breaks alternative/homing torps.
- **`receiveShotKills` contains ALL hits**, not just kills (misnamed). Fields
  include `ownerID`, `hitType` (Penetration / OverPen / Bounce / Shatter / etc.
  from ShipsConstants), `shotID`, `pos`, and optional `terminalBallisticsInfo`.
  This is the basis for ribbon derivation.

### Vehicle / Avatar ALL_CLIENTS Properties (sort_size order)

Full canonical lists with indices, names, and byte widths live in the source of
truth (`Vehicle.def` / `Avatar.def` + interface merge). Quick reminders:

- **Vehicle** has 54 properties: `teamId` (index 5, INT8), `health` (28, F32),
  `maxHealth` (31, F32), `visibilityFlags` (35, U32), `owner` (36, ENTITY_ID),
  variable-length at indices 43–53 (`shipConfig`, `crewModifiersCompactParams`,
  `triggeredSkillsData`, `state`, etc.).
- **Avatar** has 21 properties: `teamId` (1), `isAlive` (6), `ownShipId` (10),
  `attrs` (13, INT64), `vehiclePosition` (14, V3), `visibilityDistances` (15),
  `weatherParams` (16, 92 bytes), variable-length tail:
  `privateBattleLogicState` (18), `privateVehicleState` (19, holds ribbons),
  `spottedEntities` (20).

---

## Roster: `onArenaStateReceived`

### Wire format

Arrives as an ENTITY_METHOD (0x08) packet:

```
Packet header (12 bytes):
  payload_size(u32 LE) + packet_type(u32 LE, 0x08) + clock(f32 LE)

Method payload:
  entity_id(u32) + method_id(u32) + payload_length(u32)  ← 12-byte method header
  arenaUniqueId(INT64, 8 bytes)                          ← fixed arg
  teamBuildTypeId(INT8, 1 byte)                          ← fixed arg
  preBattlesInfo(BLOB)                                    ← pickle
  playersStates(BLOB)                                     ← pickle: list of 24 player tuples
  botsStates(BLOB)                                        ← pickle: list of bot tuples
  observersState(BLOB)                                    ← pickle
  buildingsInfo(BLOB)                                     ← pickle
```

### BLOB encoding (BigWorld VariableLengthHeaderSize)

BLOB length prefix depends on the method's `variable_length_header_size` (vlh):

- **vlh=1** (default, used by `onArenaStateReceived`): `first < 0xFF` → 1-byte
  length. `first == 0xFF` → next u16 (3-byte prefix). `first == 0xFF && next_u16
  == 0xFFFF` → next u32 (7-byte prefix).
- **vlh=2:** same escalation starting from u16 → u32.
- **vlh=4:** always u32.

This differs from the standard `construct` schema, which assumes all BLOBs carry
a u32 length prefix. `cs.Prefixed(cs.Int32ul, cs.GreedyBytes)` is therefore wrong
for methods with vlh < 4 — the parser silently fails and leaves `method_args =
None`. The roster code bypasses length-prefix encoding by scanning the raw
payload for pickle protocol 2 headers (`\x80\x02`) and deserializing sequentially
(each pickle is self-delimiting via STOP opcode `\x2E`).

### Pickle deserialization (Python 2 → Python 3)

Pickles come from the WoWs server running **Python 2.7**, using **pickle protocol 2**.

- Python 2 `str` objects are serialized as raw bytes with no encoding metadata.
- Python 3 `pickle.loads()` must be told to decode these bytes → use `encoding='latin-1'`.
- `latin-1` is safe because it maps 0x00–0xFF 1:1 to Unicode — it never raises,
  even for Cyrillic/CJK player names stored as UTF-8 byte sequences inside
  Python 2 `str`.
- The pickles reference game-specific classes (e.g. `CamouflageInfo`) that don't
  exist in our code → use a custom `Unpickler.find_class()` that creates dummy
  `dict` subclasses.

This `latin-1` + safe-unpickler approach applies to **any BLOB containing Python 2
pickle data** in the replay (e.g. `onGameRoomStateChanged`, `receivePlayerData`),
not to the binary packet stream itself. The replay's packet headers, entity
properties, and construct-based schemas use standard LE binary encoding, not
pickle.

### Player data structure

Each player in `playersStates` is a list of `(int_key, value)` tuples — NOT a dict.
Key highlights: `0=accountDBID`, `2=avatarId`, `3=camouflageInfo` (game class →
dummy dict), `4=clanColor`, `5=clanID`, `6=clanTag`, `11=id` (matches JSON header
`vehicles[].id`), `25=name`, `33=shipId` (Vehicle entity_id in game world),
`36=teamId`. Full key maps for players (38 keys) and bots (28 keys, different
indices) live in `roster.py`.

### Matching chain

1. Find the arena-state packet by content probing (scan early ENTITY_METHOD packets
   for a valid pickle player list).
2. Deserialize `playersStates` with `encoding='latin-1'` and the safe unpickler.
3. Convert each player's `(int_key, value)` tuples to dicts using the key map.
4. Match to JSON header: `arena_player["id"] == meta_vehicle["id"]` (AccountId).
5. Use `arena_player["shipId"]` as the Vehicle entity_id for all subsequent
   lookups.

---

## Feature Data Path Status

Decode rate: **100%** method-name resolution, 99.99% method-arg parsing, 100%
property-name resolution, 98.6% property-value parsing. Method index assignment
verified deterministically correct against real replay data.

All of the following are fully WORKING end-to-end (packet → tracker/event →
public API). See `events/models.py` and `state/models.py` for the exposed fields.

- Ship positions (Vehicle Position 0x0A, Avatar PlayerOrientation 0x2C)
- Ship health, maxHealth, regenerationHealth, isAlive (Vehicle properties)
- Ship deaths (Avatar `receiveVehicleDeath`, Vehicle `kill`)
- Player roster incl. clan_tag/clan_color/crew_id/prebattle/realm/etc.
  (Avatar `onArenaStateReceived` pickle) + observers, buildings_info, prebattles_info
- Ship loadouts — SHIP_CONFIG decoder (modules, upgrades, signals, camo)
- Team scores (BattleLogic.teams TEAMS_DEF) + battle_type, duration, map_border
- Chat messages (Avatar `onChatMessage`, ~94.6% — 2 encoding edge cases)
- Consumables (Vehicle `onConsumableUsed` / `setConsumables` / `onConsumableInterrupted`)
- Ribbons (server-authoritative `privateVehicleState.ribbons` + derived from hit events)
- Minimap vision (Avatar `updateMinimapVisionInfo`, both args)
- Artillery shells (Avatar `receiveArtilleryShots` / `receiveShotKills` / `receiveShellInfo`)
- Torpedoes (Avatar `receiveTorpedoes` / `receiveTorpedoArmed` / `receiveTorpedoSync` / direction)
- Depth charges, plane projectiles, explosions (Avatar receive_*)
- Damage stats (Avatar `receiveDamageStat` pickle) + damages on ship (Vehicle `receiveDamagesOnShip`)
- Gun state, turret yaw, torpedo tubes, ammo switching, shootOnClient / shootATBAGuns
- Squadrons (16 Avatar `receive_*` methods) + air support with params_id preserved
- Game room / arena state / battle end / battle results (0x22) / cooldowns
- Ship physics (Vehicle `syncShipPhysics` pickle) + hit locations + achievements
- Capture zones, smoke screens, buildings, weather zones (InteractiveZone type==5)
- Triggered skills (`Vehicle.triggeredSkillsData` → `SkillActivationEvent`)
- Camera timeline (0x25), net stats (0x1D), entity leave (0x04)
- Ping-noise filter: `onCheckGamePing` / `onCheckCellPing` dropped before event creation

---

## State Tracker Notes

- **Weather zones:** InteractiveZone entities with `type==5` are identified on
  ENTITY_CREATE and tracked as `WeatherZoneState` in `GameState.weather_zones`.
  Position from NonVolatilePosition (0x2A), radius from entity props, params_id
  matched from `BattleLogic.state.weather.localWeather` by name.
  `_build_capture_points` excludes weather zones.
- **Turret yaw:** `syncGun` calls with `weapon_type==0` (ARTILLERY) accumulate
  per-turret yaw in `ShipState.turret_yaws: dict[int, float]` (gun_id → radians).
  Renderer uses the lowest gun_id (forward turret) for the direction line.
- **Camera / net-stats timelines:** `tracker._camera_positions` and
  `_net_stats` are stored as append-only timelines; `camera_at(t)` / `net_stats_at(t)`
  are O(log n) bisects. See `KNOWN_ISSUES.md` A-1 for the temp-list rebuild
  inefficiency when called per-frame.

---

## Hard Constraints

1. **General-purpose parser** — decode ALL packets, not just renderer-needed ones.
2. **No data loss** — raw payload accessible; unknown packets → `RawEvent`, never
   silently dropped.
3. **Additive events** — new event types don't break existing ones.
4. **Complete entity state history** — every property change carries a timestamp;
   snapshots are a view over the history, not the primary storage.
5. **No renderer dependencies** — parser is standalone, no imports from renderer
   or any specific consumer.

---

## Map Coordinate System

- Map bounds from `wows-gamedata/data/spaces/<map_name>/space.settings` — XML
  with `<bounds minX maxX minY maxY />`.
- Minimap PNG at `data/spaces/<map_name>/minimap.png`.
- World coords (origin at center, ±half_map_size) → pixel coords (origin top-left).

---

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

---

## Gamedata Repo

The `wows-gamedata/` subdir is a clone of
[github.com/toalba/wows-gamedata](https://github.com/toalba/wows-gamedata). An
automated pipeline checks Steam every 6 hours and auto-extracts on new patches.
Key paths:

- Entity defs: `data/scripts_entity/entity_defs/`
- Minimaps: `data/spaces/<map_name>/minimap.png`
- Constants: `data/scripts_decrypted/extracted_constants.json`
- Decompiled events: `data/scripts_decrypted_decompiled/wows_replays/`
- GameParams: `data/content/GameParams.data` (Blowfish-encrypted pickle, needs `wowsunpack`)

`gamedata_sync.sync_gamedata()` checks out the correct git tag for a replay's
game version, falling back to the closest tag by smallest absolute build-ID delta
when an exact match is missing. It refuses checkout if tracked files have
uncommitted changes.

---

## Known Remaining Gaps

See `KNOWN_ISSUES.md` for the canonical list. Parser-side summary:

- **Nested property routing:** ~34% of nested-property packets don't resolve.
  Bulk are `Vehicle.state.atba.atbaTargets` SetElement ops where the server's
  array shrank but our tracker holds the old length (48 packets left unresolved —
  speculative downward decode silently corrupts data, and the payload is
  cosmetic: secondary-battery target IDs). Other unresolved Vehicle nested
  updates (~1,232/replay) need per-leaf decoders for additional `state` /
  `effects` sub-paths. SmokeScreen nested routing (~22/replay) not implemented.
  `Vehicle.state` leaf FIXED_DICTs (`battery`, `buffs`, `vehicleVisualState`,
  `decals`, `atba`) resolve by name but leaves aren't fully decoded.
- **Speed units (M-1):** `ShipState.speed` / `max_speed` are the game's internal
  fixed-point integer, not knots.
- **`SubSurfacingEvent.time` (M-2):** typed `int` but `syncSurfacingTime` may send
  a float — verify against `Vehicle.def`.
- **Per-frame timeline queries (A-1):** `camera_at` / `net_stats_at` /
  `position_at` rebuild a temp timestamp list on every call. Fine for ad-hoc
  queries, ~5s overhead on 30fps full-replay renders.
- **OWN_CLIENT triple rebuild (A-2):** `own_player_vehicle_state` /
  `spotted_entities_at` / `visibility_distances_at` each call `_rebuild_state_at`
  independently — a combined `avatar_data_at(t)` would let callers extract all
  Avatar private state in one rebuild.

---

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
wowsreplay export replay.wowsreplay --gamedata ./wows-gamedata/data/scripts_entity/entity_defs -o replay.json

# Top-level API
from wows_replay_parser import parse_replay
replay = parse_replay("battle.wowsreplay", "./wows-gamedata/data/scripts_entity/entity_defs")
replay.state_at(120.5)             # GameState snapshot
replay.ship_state(entity_id, t)    # ShipState
replay.events_of_type(ShotCreatedEvent)
replay.recording_player_ribbons()  # Server-authoritative ribbons
```
