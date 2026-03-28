# WoWS Replay Parser — Architecture & Internals

This document explains how the parser works end-to-end: from a binary `.wowsreplay` file to fully typed game events and state snapshots. It covers the BigWorld engine conventions we reverse-engineered, the method resolution algorithm, entity lifecycle, and every layer in between.

## Table of Contents

1. [Overview & Data Flow](#1-overview--data-flow)
2. [Replay File Format](#2-replay-file-format)
3. [Gamedata Loading Pipeline](#3-gamedata-loading-pipeline)
4. [Method Index Resolution — The Core Problem](#4-method-index-resolution--the-core-problem)
5. [Packet Decoding](#5-packet-decoding)
6. [Entity Lifecycle & Type Resolution](#6-entity-lifecycle--type-resolution)
7. [State Tracking](#7-state-tracking)
8. [Event Stream Generation](#8-event-stream-generation)
9. [Player Roster Enrichment](#9-player-roster-enrichment)
10. [Known Limitations & Open Issues](#10-known-limitations--open-issues)

---

## 1. Overview & Data Flow

```
┌─────────────────────┐
│  .wowsreplay file   │
│  (binary container)  │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐   JSON headers (match meta, player list)
│    ReplayReader      │──────────────────────────────────────────┐
│  decrypt + decompress│                                          │
└─────────┬───────────┘                                          │
          │ raw packet stream (bytes)                             │
          ▼                                                       │
┌─────────────────────┐   alias.xml    entity_defs/*.def          │
│  Gamedata Loading    │◄──────────────────────────────           │
│  AliasRegistry       │   entities.xml                           │
│  DefLoader           │                                          │
│  EntityRegistry      │                                          │
│  SchemaBuilder       │                                          │
└─────────┬───────────┘                                          │
          │ indexed methods, properties, binary schemas            │
          ▼                                                       │
┌─────────────────────┐                                          │
│  Type ID Detection   │  entities.xml → type_idx → entity_name   │
│  Method ID Detection │  auto-detect tie groups from payloads    │
└─────────┬───────────┘                                          │
          │                                                       │
          ▼                                                       │
┌─────────────────────┐                                          │
│   PacketDecoder      │  163k+ packets per replay                │
│   12-byte headers    │  entity lifecycle, methods, properties   │
│   handler dispatch   │  positions, camera, metadata             │
└────┬────────────┬───┘                                          │
     │            │                                               │
     ▼            ▼                                               │
┌──────────┐ ┌──────────┐                                        │
│GameState │ │EventStream│                                        │
│ Tracker  │ │  process  │                                        │
└────┬─────┘ └────┬─────┘                                        │
     │            │                                               │
     ▼            ▼                                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                        ParsedReplay                              │
│  .events       — typed game events (Death, Shot, Damage, ...)   │
│  .packets      — all decoded packets                             │
│  .players      — roster with entity_id ↔ player matching         │
│  .state_at(t)  — full game state snapshot at any timestamp       │
│  .ship_state() — single ship state query                         │
└──────────────────────────────────────────────────────────────────┘
```

**Key design principle:** No hardcoded schemas. Everything is loaded dynamically from the `wows-gamedata` repository (entity definitions, type aliases, entity type mappings). When a new game patch ships, a `git pull` on wows-gamedata is all that's needed — no parser code changes.

### Entry Point

```python
from wows_replay_parser import parse_replay

replay = parse_replay(
    "battle.wowsreplay",
    "wows-gamedata/data/scripts_entity/entity_defs",
)

# Typed events
for event in replay.events_of_type(ShotCreatedEvent):
    print(event.owner_id, event.speed, event.target_position)

# State snapshots
state = replay.state_at(120.5)
for eid, ship in state.ships.items():
    print(eid, ship.health, ship.is_alive)
```

---

## 2. Replay File Format

**File:** `src/wows_replay_parser/replay/reader.py`

A `.wowsreplay` file has this structure:

```
┌──────────────────────────────────────────┐
│ Magic: 0x12324211 (4 bytes, LE)          │
│ Block count: u32 LE (1 or 2)            │
├──────────────────────────────────────────┤
│ JSON block 1: match metadata             │
│   size(u32) + UTF-8 JSON                 │
├──────────────────────────────────────────┤
│ JSON block 2: battle results (optional)  │
│   size(u32) + UTF-8 JSON                 │
├──────────────────────────────────────────┤
│ Encrypted packet stream                  │
│   Blowfish ECB with XOR chaining         │
│   then zlib decompress                   │
└──────────────────────────────────────────┘
```

### Encryption

The packet stream is encrypted with a non-standard Blowfish variant:

- **Algorithm:** Blowfish ECB (8-byte blocks)
- **Key:** `0x29B7C909383F8488FA98EC4E131979FB` (hardcoded, same for all replays)
- **Chaining:** XOR with *previous decrypted output* (not ciphertext — differs from standard CBC)
- **IV:** 8 zero bytes

After decryption, the result is zlib-decompressed into a raw packet stream.

### JSON Header

The first JSON block contains match metadata:

```json
{
  "gameVersion": "15,2,0,12116141",
  "mapName": "spaces/56_AngelWings",
  "vehicles": [
    {"shipId": 4282300368, "name": "Dutch_Elephant", "id": 502524043, ...},
    ...
  ]
}
```

The `vehicles[].id` field is the AccountId, used later to match players to ship entities.

---

## 3. Gamedata Loading Pipeline

The parser needs to understand entity definitions before it can decode packets. This knowledge comes from four files in the `wows-gamedata` repository.

### 3.1 Type Aliases (`alias.xml`)

**File:** `src/wows_replay_parser/gamedata/alias_registry.py`

`alias.xml` defines shorthand type names used throughout `.def` files. Five patterns:

```xml
<!-- Simple alias -->
<ENTITY_ID> INT32 </ENTITY_ID>

<!-- FIXED_DICT — structured type with named fields -->
<SHOT> FIXED_DICT
  <Properties>
    <pos> <Type> VECTOR3 </Type> </pos>
    <speed> <Type> FLOAT </Type> </speed>
    <shotID> <Type> UINT16 </Type> </shotID>
  </Properties>
</SHOT>

<!-- FIXED_DICT with AllowNone — nullable, becomes variable-length -->
<OPTIONAL_DATA> FIXED_DICT
  <Properties>...</Properties>
  <AllowNone> true </AllowNone>
</OPTIONAL_DATA>

<!-- FIXED_DICT with implementedBy — custom Python serializer -->
<MISSILE> FIXED_DICT
  <Properties>...</Properties>
  <implementedBy>MissileDef.converter</implementedBy>
</MISSILE>

<!-- ARRAY — variable-length list -->
<SHOTS_ARRAY> ARRAY <of> SHOT </of> </SHOTS_ARRAY>

<!-- TUPLE — fixed-length array -->
<VISION_PAIR> TUPLE <of> INT32 </of> <size> 2 </size> </VISION_PAIR>

<!-- USER_TYPE — custom type with underlying storage -->
<ZIPPED_BLOB> USER_TYPE
  <Type> BLOB </Type>
  <implementedBy>ZippedBlobConverter.converter</implementedBy>
</ZIPPED_BLOB>
```

The `AliasRegistry` resolves these recursively. `ENTITY_ID` → `INT32`, `SHOT.pos` → `VECTOR3`, etc.

**Critical detail:** The `<implementedBy>` tag means the BigWorld engine uses a custom Python class to serialize/deserialize the data. The engine's `streamSize()` returns `-1` (variable) for these types, regardless of whether the fields themselves are fixed-size. Our code tracks this via `TypeAlias.has_implemented_by` and returns `INFINITY` in sort_size computation. Missing this caused a method index offset bug (see Section 4).

### 3.2 Entity Definitions (`.def` files)

**File:** `src/wows_replay_parser/gamedata/def_loader.py`

Each entity type has a `.def` file (Avatar.def, Vehicle.def, etc.) defining:

- **Properties:** typed fields with visibility flags (`ALL_CLIENTS`, `OWN_CLIENT`, etc.)
- **ClientMethods:** methods the server can call on the client (these appear in replays)
- **CellMethods / BaseMethods:** server-side only, not in replays

#### Interface Merging

Entity definitions use `<Implements>` to include shared interfaces:

```xml
<!-- Avatar.def -->
<root>
  <Implements>
    <AvatarCMDs/>          <!-- interface 1 -->
    <SquadronController/>  <!-- interface 2 -->
    <DebugDrawable/>       <!-- interface 3 -->
    ...
  </Implements>
  <ClientMethods>
    <onArenaStateReceived>  <!-- Avatar's own methods -->
      <Arg> INT64 </Arg>
      <Arg> INT8 </Arg>
      <Arg> BLOB </Arg>
      ...
    </onArenaStateReceived>
  </ClientMethods>
</root>
```

The merge algorithm is **depth-first, XML document order**:

```
Avatar.def
  ├─ AvatarCMDs (interface)
  │   ├─ CommonCMDs (sub-interface of AvatarCMDs)
  │   │   └─ receive_CommonCMD         → index 0
  │   ├─ receiveSignedCommand          → index 1
  │   └─ receivePublicIntStat          → index 2
  ├─ SquadronController
  │   ├─ receive_addSquadron           → index 3
  │   └─ receive_addMinimapSquadron    → index 4
  ├─ DebugDrawable
  │   └─ drawDebugLine                 → index 5
  ...
  └─ Avatar's own methods
      ├─ onArenaStateReceived          → index 103
      └─ onChatMessage                 → index 107
```

**Deduplication:** First definition wins. If interface A and B both define `methodX`, the first one encountered (depth-first) keeps its position. Subsequent duplicates are skipped.

**Diamond inheritance protection:** A `_visited` set prevents re-parsing the same interface. If interfaces A and B both implement interface C, C's methods are added when first encountered (via A), and skipped when encountered again (via B).

This declaration order becomes the **tiebreaker** in method sorting (see Section 4).

### 3.3 Entity Registry & Sort Size Computation

**File:** `src/wows_replay_parser/gamedata/entity_registry.py`

After loading `.def` files, the `EntityRegistry` computes a `sort_size` for each method and property, then sorts them. This sorted order determines the binary index used in network packets.

#### Sort Size Rules

| Type | sort_size |
|------|-----------|
| `INT8`, `UINT8`, `BOOL` | 1 |
| `INT16`, `UINT16` | 2 |
| `INT32`, `UINT32`, `FLOAT` | 4 |
| `INT64`, `UINT64`, `FLOAT64` | 8 |
| `VECTOR2` | 8 |
| `VECTOR3` | 12 |
| `STRING`, `BLOB`, `PYTHON` | INFINITY (0xFFFF) |
| `FIXED_DICT` (no AllowNone) | sum of field sizes |
| `FIXED_DICT` with `AllowNone` | INFINITY |
| `FIXED_DICT` with `implementedBy` | INFINITY |
| Any type with `implementedBy` | INFINITY |
| `ARRAY` (no fixed size) | INFINITY |
| `ARRAY` with `<size>N</size>` | N × element_size |

For a method:

```
method_sort_size = sum(arg_sort_sizes) + variable_length_header_size
```

If any arg is INFINITY, the whole method is INFINITY + VLH.

#### Why This Matters

The sort_size determines where each method sits in the binary index table. If we compute the wrong sort_size, we assign the wrong method to an index, and every packet using that index decodes with the wrong schema.

---

## 4. Method Index Resolution — The Core Problem

This is the hardest part of the parser to get right. Here's the full story.

### 4.1 The Engine's Sort Algorithm

BigWorld Engine (v14.4.1) sorts exposed client methods using `std::stable_sort` with this comparator:

```cpp
bool operator()(methodIndex1, methodIndex2) {
    int16 size1 = methods_[methodIndex1].streamSize(true);
    int16 size2 = methods_[methodIndex2].streamSize(true);

    // Both variable-length: sort by VLH size ascending
    if (size1 < 0 && size2 < 0) return -size1 < -size2;

    // Both fixed-length: sort by byte count ascending
    if (size1 >= 0 && size2 >= 0) return size1 < size2;

    // Fixed always before variable
    return size1 > size2;
}
```

Where `streamSize(true)` returns:
- **Positive integer:** fixed-size method (sum of arg bytes)
- **Negative integer:** variable-size method (`-vlh_size`, e.g. VLH=1 → -1)

Because `std::stable_sort` preserves insertion order for equal elements, **methods with the same streamSize keep their declaration order** (i.e., the depth-first interface merge order from Section 3.2).

### 4.2 Our Implementation

We map this to Python's `list.sort()` (also stable) with a sort key:

```python
def sort_key(method):
    if method.sort_size >= INFINITY:
        vlh = method.sort_size - (INFINITY - 1)
        return (1, vlh)       # variable: group 1, ascending VLH
    else:
        return (0, method.sort_size)  # fixed: group 0, ascending size
```

This produces the same ordering as the C++ comparator:
1. Fixed-size methods first, ascending by byte count
2. Variable-size methods second, ascending by VLH (1, then 2, then 4)
3. Ties broken by declaration order (stable sort preserves it)

### 4.3 Tier 1 vs Tier 2 Resolution

**Tier 1 (deterministic, from .def files):**
The sort described above produces correct indices for ~95% of methods. The remaining ~5% are in "tie groups" — methods with identical sort_size where the declaration-order tiebreaker is ambiguous.

**Tier 2 (auto-detector, from replay data):**
The `method_id_detector.py` module resolves tie groups by observing actual packet payloads:

1. **Fixed-size matching:** If a method index always has the same payload length, and only one candidate method has that exact arg byte sum → match.
2. **Trial parsing:** Parse the payload with each candidate method's schema. If only one succeeds (consumes all bytes without error) → match.
3. **Semantic validation:** When multiple candidates parse successfully, apply domain rules:
   - Artillery shots: speed 50–2500 m/s, positions within map bounds
   - Torpedoes: direction vector roughly normalized (length 0.3–2.0)
   - Chat messages: at least one non-empty string arg
   - Vehicle death: entity IDs within 0–10M, reason code 0–200
4. **Elimination:** If N-1 of N methods in a group are resolved, the last one is assigned.
5. **Fallback:** Unresolved methods keep their sort-order position.

### 4.4 The `implementedBy` Bug (Fixed)

We discovered that 16 type aliases with `<implementedBy>` tags were being computed as fixed-size, when the engine treats them as variable-size. This shifted method indices:

- **Avatar:** 1 method (`receivePingerLaunchPosition`, uses `FLAT_VECTOR` + `NULLABLE_VECTOR3`) was misclassified → all VLH=1 methods shifted by -1
- **Vehicle:** 2 methods (`receiveGunSyncRotations` uses `GUN_DIRECTIONS`, `updateInvisibleWavedPoint` uses `NULLABLE_VECTOR3`) → all methods shifted by -2

The fix: check `alias.has_implemented_by` in `compute_type_sort_size()` and return INFINITY.

### 4.5 Verification

`scripts/verify_method_sort.py` validates the sort against real replay data using semantic validators as ground truth. After the implementedBy fix: **10/10 verified methods correct (100%)** across unique sort_size methods and tie groups alike.

---

## 5. Packet Decoding

**File:** `src/wows_replay_parser/packets/decoder.py`

### 5.1 Packet Header

Every packet in the decompressed stream has a 12-byte header:

```
┌───────────────┬───────────────┬───────────────┐
│ payload_size  │  packet_type  │    clock      │
│   uint32 LE   │   uint32 LE   │  float32 LE   │
│   (4 bytes)   │   (4 bytes)   │  (4 bytes)    │
└───────────────┴───────────────┴───────────────┘
```

`clock` is the game time in seconds since match start.

### 5.2 Packet Types

| Type | Code | Description | Frequency |
|------|------|-------------|-----------|
| `BASE_PLAYER_CREATE` | 0x00 | Creates the player's Avatar entity | 1/replay |
| `CELL_PLAYER_CREATE` | 0x01 | Attaches cell data to base player | 1/replay |
| `ENTITY_CONTROL` | 0x02 | Grants/revokes control of an entity | 1/replay |
| `ENTITY_ENTER` | 0x03 | Entity enters Area of Interest | low |
| `ENTITY_LEAVE` | 0x04 | Entity leaves AoI | ~100 |
| `ENTITY_CREATE` | 0x05 | Creates any entity (ships, zones, ...) | ~111 |
| `ENTITY_PROPERTY` | 0x07 | Property value update | ~41k |
| `ENTITY_METHOD` | 0x08 | Remote method call | ~37k |
| `POSITION` | 0x0A | Entity position update (other ships) | ~24k |
| `SERVER_TICK` | 0x0E | Time sync tick | ~7.8k |
| `SERVER_TIMESTAMP` | 0x0F | Absolute server time | 1/replay |
| `VERSION` | 0x16 | Game version string | 1/replay |
| `GUN_MARKER` | 0x18 | Aim point indicator | ~10k |
| `PLAYER_NET_STATS` | 0x1D | Network statistics | ~10k |
| `OWN_SHIP` | 0x20 | Which Vehicle the player controls | 1/replay |
| `BATTLE_RESULTS` | 0x22 | Post-battle JSON blob | 1/replay |
| `NESTED_PROPERTY` | 0x23 | Partial property update | ~3.7k |
| `CAMERA` | 0x25 | Camera position/rotation/FOV | ~10k |
| `BASE_PLAYER_CREATE_STUB` | 0x26 | Lightweight base player create | 1/replay |
| `CAMERA_MODE` | 0x27 | Camera mode switch | ~18 |
| `MAP` | 0x28 | Map identifier + space info | 1/replay |
| `NON_VOLATILE_POSITION` | 0x2A | Static entity position (smoke, zones) | ~588 |
| `PLAYER_ORIENTATION` | 0x2C | Self-ship position (not via 0x0A) | ~15k |
| `CRUISE_STATE` | 0x32 | Speed/rudder settings | ~442 |
| `SHOT_TRACKING` | 0x33 | Weapon tracking state | ~9 |

### 5.3 ENTITY_METHOD Packet Format

This is the most important packet type — it carries game events.

```
┌────────────┬────────────┬──────────────┬──────────────────┐
│ entity_id  │ method_id  │ payload_len  │ serialized_args  │
│  uint32 LE │  uint32 LE │  uint32 LE   │  payload_len B   │
└────────────┴────────────┴──────────────┴──────────────────┘
```

The `method_id` is looked up via the entity's sorted method table (see Section 4). The `serialized_args` are parsed with the method's dynamically-built `construct` schema.

### 5.4 Binary Serialization Details

The `SchemaBuilder` generates `construct` parsers for each method. Key encoding rules:

**Primitives:** Standard little-endian (`INT32` → `cs.Int32sl`, `FLOAT` → `cs.Float32l`, etc.)

**VECTOR3:** `Struct("x"/Float32l, "y"/Float32l, "z"/Float32l)` (12 bytes)

**ARRAY count prefix:** Always `uint8` at ALL nesting levels. No VLH escalation for array counts.

**STRING/BLOB length prefix (inside method calls):**
Uses VLH-aware escalating encoding:
```
if first_byte < 0xFF:
    length = first_byte                                    (1 byte prefix)
elif first_byte == 0xFF:
    length = next_u16_LE                                   (3 bytes prefix)
    skip 1 padding byte
elif first_byte == 0xFF and next_u16 == 0xFFFF:
    length = next_u32_LE                                   (7 bytes prefix)
```

**FIXED_DICT:** Struct of fields in declaration order. If `AllowNone`, prepend `u8` flag (0=None, nonzero=data follows).

**Property updates** use a different encoding: always `u32` length prefix for BLOBs (no VLH escalation). This distinction is critical — method args and property values use different blob prefix encodings.

---

## 6. Entity Lifecycle & Type Resolution

### 6.1 Entity Creation

Entities are created by three packet types:

**`BASE_PLAYER_CREATE` (0x00)** — The player's own controller entity.
- WoWS-specific: the `type_idx` in this packet does **not** map to `entities.xml`
- We resolve the type dynamically: find the entity type with the most ClientMethods (= Avatar in WoWS, 178 methods)
- Only 1 per replay

**`BASE_PLAYER_CREATE_STUB` (0x26)** — Same entity, lightweight create without properties. Arrives before BASE_PLAYER_CREATE.

**`ENTITY_CREATE` (0x05)** — All other entities (ships, capture zones, smoke, etc.)
- Format: `entity_id(u32) + type_idx(u16) + vehicle_id(u32) + space_id(u32) + position(3×f32) + rotation(3×f32) + state_length(u32) + state_data`
- `type_idx` correctly maps to `entities.xml`
- Inline state: `num_props(u8) + [prop_id(u8) + typed_value] × num_props`

### 6.2 Entity Type Remapping

BigWorld sends ENTITY_CREATE with the **base entity type**, not the cell type. In WoWS:

| Packet says | Actually is | How we detect |
|-------------|-------------|---------------|
| Account (idx=2) | Vehicle | num_props > Account's property count → trial-parse with Vehicle schema |
| OfflineEntity (idx=4) | Vehicle or Building | same detection |
| InteractiveObject (idx=14) | InteractiveZone | same detection |

This happens because other players' ships are created with the Account base type but carry Vehicle cell properties.

### 6.3 Entity Type Map (`entities.xml`)

```
Index  Entity              Role
─────  ──────────────────  ──────────────────────
  0    Avatar              Player controller (178 ClientMethods)
  1    Vehicle             Ship (83 methods, 54 client properties)
  2    Account             Player account (remapped → Vehicle)
  3    SmokeScreen         Smoke entity
  4    OfflineEntity       Disconnected player (remapped → Vehicle)
  5    VehicleAppearance   Unused in replays
  6    Login               Login entity
  7    BattleEntity        Base battle entity
  8    Building            Destructible structure
  9    MasterChanger       Channel controller
 10    BattleLogic         Score tracking (2 methods, 11 properties)
 11    ReplayLeech         Replay observer
 12    ReplayConnectionHandler
 13    InteractiveZone     Capture point
 14    InteractiveObject   Remapped → InteractiveZone
```

### 6.4 Position Tracking

The self-player's position is **not** sent via `POSITION` (0x0A). Instead:

- **Other ships:** `POSITION` (0x0A) — 45 bytes: `entity_id, space_id, position(V3), direction(V3), rotation(V3), is_on_ground(u8)`
- **Self ship:** `PLAYER_ORIENTATION` (0x2C) — 32 bytes: `pid, parent_id, position(V3), rotation(V3)`. Only entries with `parent_id==0` are the actual ship position.
- **Static entities (smoke, zones):** `NON_VOLATILE_POSITION` (0x2A) — same as POSITION but without direction/is_on_ground.

---

## 7. State Tracking

**File:** `src/wows_replay_parser/state/tracker.py`

The `GameStateTracker` accumulates entity state over time from decoded packets.

### Data Structures

- `_current[entity_id][property_name]` → current value
- `_history` → list of `PropertyChange(entity_id, prop, old, new, timestamp)`
- `_positions[entity_id]` → list of `(timestamp, (x, y, z), yaw)`
- `_minimap_positions` → vision data from `updateMinimapVisionInfo`
- `_death_positions`, `_consumable_activations` → event-specific tracking

### Queries

**`state_at(t) → GameState`**
Returns a full snapshot: all ships' health/team/alive status, battle state (stage, time, scores), all property values as of time `t`. Uses cached snapshots every 5 seconds + incremental replay forward.

**`iter_states(timestamps) → Iterator[GameState]`**
Optimized for sequential rendering. O(delta) per frame instead of O(history) per frame. Steps forward through property changes rather than replaying from scratch.

**`ship_state(entity_id, t) → ShipState`**
Single ship query: health, max_health, team_id, is_alive, visibility_flags, burning_flags.

---

## 8. Event Stream Generation

**Files:** `src/wows_replay_parser/events/models.py`, `stream.py`

The `EventStream` maps decoded packets to typed game events:

### Method → Event Mapping

| Method | Event Type | Key Fields |
|--------|-----------|------------|
| `Avatar.receiveVehicleDeath` | `DeathEvent` | victim_id, killer_id, death_reason |
| `Avatar.receiveArtilleryShots` | `ShotCreatedEvent[]` | per-shell: position, speed, target, shotID |
| `Avatar.receiveTorpedoes` | `TorpedoCreatedEvent[]` | per-torpedo: position, direction, armed |
| `Avatar.receiveShotKills` | `ShotDestroyedEvent[]` | impact position, armor_penetration, hit_type |
| `Avatar.receiveShellInfo` | `DamageEvent` | target_id, damage, ammo_id |
| `Avatar.onChatMessage` | `ChatEvent` | sender_id, channel, message |
| `Avatar.updateMinimapVisionInfo` | `MinimapVisionEvent[]` | per-ship: vehicleID, x/y, heading, visible |
| `Avatar.onAchievementEarned` | `AchievementEvent` | player_id, achievement_id |
| `Vehicle.kill` | `DeathEvent` | victim_id, killer_id, death_reason |
| `Vehicle.onConsumableUsed` | `ConsumableEvent` | consumable_id, work_time_left |
| Position packets (0x0A, 0x2C) | `PositionEvent` | x, y, z, yaw, speed |
| Property updates (0x07) | `PropertyUpdateEvent` | entity_id, property_name, value |
| Unmatched packets | `RawEvent` | raw packet data |

### Minimap Vision Unpacking

`updateMinimapVisionInfo` sends two arrays of `{vehicleID: u32, packedData: u32}`. The `packedData` is a bitfield encoding position and heading:

```python
raw_x = (packed >> 0) & 0x3FF     # 10 bits, 0-1023
raw_y = (packed >> 10) & 0x3FF    # 10 bits, 0-1023
heading = (packed >> 20) & 0x1FF  # 9 bits, degrees
flags = (packed >> 29) & 0x7      # 3 bits
```

World coordinates are computed from map bounds.

---

## 9. Player Roster Enrichment

**File:** `src/wows_replay_parser/roster.py`

Matches player metadata (from JSON header) to in-game entity IDs.

### Data Sources

1. **JSON header** `meta["vehicles"]` — AccountId, player name, ship type, clan
2. **`onArenaStateReceived`** method — pickle blob with full player state

### Arena State Format

The `onArenaStateReceived` method (called once at battle start) carries:

```
arenaUniqueId(INT64) + teamBuildTypeId(INT8)
+ preBattlesInfo(BLOB)   ← pickle
+ playersStates(BLOB)    ← pickle: list of (int_key, value) tuples per player
+ botsStates(BLOB)       ← pickle
+ observersState(BLOB)   ← pickle
+ buildingsInfo(BLOB)    ← pickle
```

The BLOBs use VLH-1 encoding (see Section 5.4). The pickles are Python 2.7 protocol 2, deserialized with `encoding='latin-1'` and a safe unpickler.

Each player in `playersStates` is a list of `(int_key, value)` tuples:

```python
[
  (0, 502524043),        # accountDBID
  (6, 'TTT'),            # clanTag
  (11, 502524043),       # id (= AccountId, matches JSON header)
  (25, 'Dutch_Elephant'),# name
  (33, 1041009),         # shipId (= Vehicle entity_id in game world)
  (36, 1),               # teamId
  ...
]
```

### Matching Chain

1. Scan early ENTITY_METHOD packets for valid pickle data (content probing)
2. Deserialize `playersStates` pickle
3. Match to JSON header: `arena_player["id"] == meta_vehicle["id"]`
4. Use `arena_player["shipId"]` as the Vehicle entity_id

---

## 10. Current Status & Known Limitations

### Decode Rate: 100%

As of 2026-03-28, the parser achieves **100% decode rate** on all Avatar (178) and Vehicle (83) ClientMethods. Method index assignment is verified correct against real replay data (10/10 methods, including tie groups). Test replay: 37,307/37,309 method calls decoded successfully (2 failures are chat message encoding edge cases).

The sort_size computation is now fully correct:
- `std::stable_sort` by `streamSize` (BigWorld v14.4.1 convention)
- Declaration order (depth-first interface merge) as tiebreaker
- `implementedBy` types correctly treated as variable-length
- Base player entity correctly identified as Avatar (not Vehicle)

The auto-detector (`method_id_detector.py`) is still enabled but **redundant** for Avatar and Vehicle. It may help with Account entity tie groups (lobby methods, not critical for gameplay).

### Fully Working (77 methods cataloged)
- Ship positions — Position (0x0A) + PlayerOrientation (0x2C)
- All combat events — artillery, torpedoes, depth charges, plane projectiles, explosions, kills, damage
- All vision/detection — minimap vision, spotting, disappearing
- All squadrons — 16 receive_* methods (add, remove, update, health, death, state changes)
- All consumables — activation, interruption, cooldowns, air support
- All weapon state — gun sync (yaw/pitch/reload), torpedo tubes, ammo switching, firing events
- Game state — arena state, game room updates, battle end, player data, achievements
- Player roster — pickle deserialization, entity ID matching
- Chat messages (94.6%, 2 encoding edge cases out of 37)
- Damage stats, shell info, hit locations
- Ship physics, ship cracks, rage mode

### Partially Working
- **Capture zones:** InteractiveZone property updates flow through, but NESTED_PROPERTY (0x23) deep navigation for CAPTURE_LOGIC_STATE is incomplete
- **Account entity methods:** Tie groups unresolved (lobby/pre-battle, not gameplay-critical)

### Not Implemented (state model only — packets still decode)
- Building entity state tracking
- Smoke screen state model (positions tracked, no lifetime/radius)
- NESTED_PROPERTY (0x23) deep navigation for complex nested types

### Architecture Constraints
- **General-purpose parser:** Decodes ALL packets, not just renderer-needed ones
- **No data loss:** Raw payloads always accessible; unknown packets become `RawEvent`
- **Additive events:** New event types don't break existing ones
- **No renderer dependencies:** Parser is standalone; renderer is one consumer

---

## Appendix: File Map

```
src/wows_replay_parser/
├── api.py                    Top-level parse_replay() + ParsedReplay
├── gamedata/
│   ├── alias_registry.py     alias.xml → TypeAlias resolution
│   ├── def_loader.py         .def XML → EntityDef (interface merging)
│   ├── entity_registry.py    sort_size computation, method/property indexing
│   ├── schema_builder.py     Dynamic construct schema generation
│   └── blob_decoders.py      BLOB decoders (zipped, msgpack, pickle)
├── packets/
│   ├── types.py              PacketType enum + Packet dataclass
│   ├── decoder.py            Packet stream decoding + entity tracking
│   ├── type_id_detector.py   Auto-detect type_id → entity_name
│   └── method_id_detector.py Tie-group resolution from payload data
├── replay/
│   └── reader.py             .wowsreplay container: JSON + decrypt + decompress
├── state/
│   ├── tracker.py            GameStateTracker — property history + snapshots
│   └── models.py             ShipState, BattleState, GameState, PropertyChange
├── events/
│   ├── models.py             All event types (GameEvent subclasses)
│   └── stream.py             Packet → Event transformation
├── roster.py                 Player roster enrichment (pickle + matching)
├── ribbons.py                Ribbon derivation from hit events
├── merge.py                  Dual perspective replay merging
└── cli.py                    Click CLI (info, parse, events, state)

wows-gamedata/data/
├── scripts_entity/
│   ├── entity_defs/          *.def files (15 entity types)
│   │   ├── interfaces/       Shared interface .def files (22)
│   │   └── alias.xml         Type alias definitions
│   └── entities.xml          Entity type ID mapping (0=Avatar, 1=Vehicle, ...)
├── spaces/<map>/minimap.png  Minimap images
├── gui/                      Extracted PNGs (HUD, icons, consumables)
├── split/<Type>/<Name>.json  Per-entity GameParams (ships, projectiles, etc.)
└── scripts_decrypted/        Decompiled client scripts + constants
```
