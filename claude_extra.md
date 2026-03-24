# Parser Adaptation Instructions for WG Bounty Renderer

## Context

We're building a minimap replay renderer for a Wargaming bounty (deadline: April 20, 2026). The replay parser is ~85% complete. This document describes what needs to change or be added so the parser's EventStream output directly feeds the renderer without translation layers.

The renderer needs to produce mp4 videos showing ship movements, shells, torpedoes, capture points, health bars, team scores, and ship names — embedded in a Discord bot.

## Data Sources Available

Clone the gamedata repo — it has everything, automatically extracted and versioned:
```bash
git clone git@github.com:toalba/wows-gamedata.git
```

The repo is maintained by an automated pipeline (GitHub Actions on a self-hosted runner with the WoWs game client). It checks for Steam updates every 6 hours, and when a new patch lands, it re-extracts everything, diffs against the previous version, and creates a tagged release. No manual intervention needed.

### Repo Structure

```
data/
├── content/
│   └── GameParams.data              # Blowfish-encrypted pickle — ALL ships, projectiles,
│                                     # consumables, skills, upgrades. Decode with:
│                                     # wowsunpack game-params --ugly --id "" output.json
├── gui/
│   ├── battle_hud/                  # HUD assets (health bars, score bar, etc.)
│   ├── consumables/                 # Consumable icons
│   ├── fla/minimap/                 # Flash minimap assets
│   ├── fonts/                       # Game fonts
│   ├── ship_bars/                   # Ship HP bar textures
│   └── ...
├── spaces/
│   ├── <map_name>/minimap*          # Minimap PNG images per map
│   └── <map_name>/space.settings    # Map metadata (may contain world bounds)
├── scripts_entity/
│   └── entity_defs/                 # .def XML files + alias.xml (network protocol)
│       ├── Avatar.def, Vehicle.def, BattleLogic.def, ...
│       ├── alias.xml                # Type aliases (FIXED_DICT, ARRAY, etc.)
│       └── interfaces/              # Interface .def files
├── scripts_decrypted/
│   ├── extracted_constants.json     # ~39,000 constants from ~5000 encrypted .pyc files
│   ├── diff.json                    # Changes vs previous version (enum shifts flagged)
│   └── extracted_constants.prev.json
└── scripts_decrypted_decompiled/    # 58 fully decompiled Python source files
    ├── wows_replays/                # REPLAY_EVENT enums, ShotEvents, HealthEvents, etc.
    └── ...
```

### What's Where

| Data you need | Where it is | Format |
|---|---|---|
| Entity definitions (parser schemas) | `data/scripts_entity/entity_defs/` | XML (.def files) |
| Type aliases | `data/scripts_entity/entity_defs/alias.xml` | XML |
| Minimap images | `data/spaces/<map_name>/minimap*` | PNG |
| Ship names, stats, ammo ballistics | `data/content/GameParams.data` | Blowfish-encrypted pickle → JSON via `wowsunpack` |
| HUD assets (health bars, icons) | `data/gui/battle_hud/`, `data/gui/ship_bars/` | PNG/DDS |
| Consumable icons | `data/gui/consumables/` | PNG |
| Game fonts | `data/gui/fonts/` | TTF/OTF |
| Weapon type enums, ship constants | `data/scripts_decrypted/extracted_constants.json` | JSON |
| Death reasons, ribbon IDs | `data/scripts_decrypted/extracted_constants.json` | JSON |
| REPLAY_EVENT enum hierarchy | `data/scripts_decrypted_decompiled/wows_replays/EventTypes*` | Python source |
| Shot/damage event structures | `data/scripts_decrypted_decompiled/wows_replays/ReplayContent/ReplayEvents/` | Python source |
| Enum shift detection between patches | `data/scripts_decrypted/diff.json` | JSON |

### Key Constants File: extracted_constants.json

This is the output of the script decryptor — 39,000+ constants extracted from 5141 encrypted `.pyc` files by cracking the 4-stage Wargaming/Lesta encryption. Structure:

```json
{
  "shared_constants.ships": {
    "source": "scripts/shared_constants/ships.pyc",
    "constants": {
      "SHIP_WEAPON_TYPES.ARTILLERY": 0,
      "SHIP_WEAPON_TYPES.ATBA": 1,
      "SHIP_WEAPON_TYPES.TORPEDO": 2,
      "BRANCH.US_CV": 1,
      "BRANCH.GER_BB": 2,
      ...
    }
  },
  "shared_constants.weapons": { ... },
  ...
}
```

### GameParams.data

The parser itself doesn't need GameParams (it works from .def files). But the RENDERER needs it for:
- Ship name resolution (GameParams ship ID → human-readable name)
- Ship class/tier/nation (for icons, team display)
- Ammo type names (for shot visualization — AP blue, HE orange, SAP pink)

If `wowsunpack` is not available on the build machine, check if the gamedata repo includes a pre-converted JSON. Otherwise, the renderer can ship a lightweight lookup table extracted from GameParams (ship_id → name/class/tier).

## Event System Overhaul

### Current State
The EventStream emits generic events: `DamageEvent`, `DeathEvent`, `ShotEvent`, `ChatEvent`, `PositionEvent`, `ConsumableEvent`. These were designed before we understood the actual replay event structure.

### What we now know
The decompiled client scripts reveal the real event hierarchy. The REPLAY_EVENT enum uses `parentID << 8 | childID`:

```python
REPLAY_EVENT = {
    'BATTLE': (1, {'WEATHER': 1, 'BL_STATE_CHANGE': 2, 'START': 3}),
    'ENTITY_PROPERTY_CHANGED': 2,
    'VEHICLE': (3, {'DESC_POS': 1, 'KILL': 2, 'VISION': 3, 'HL_STATE_CHANGE': 4}),
    'SHOT': (4, {
        'GUN_EFFECT': 1, 'DESTROY': 2, 'CREATE_PLANE_PROJECTILE': 3,
        'CREATE_TORP': 4, 'CREATE_BULLET': 5, 'UPDATE_PROJ_VISIB': 6,
    }),
    'HEALTH': (5, {'DAMAGE': 4, 'REGENERATION': 5}),
    'SMOKE': (6, {'CREATE': 1, 'DESTROY': 2, 'ADD_POINT': 3, 'REMOVE_POINT': 4}),
    'PLANES': 7,
    'OTHER': (8, {'CONSUMABLE': 1, 'AIR_AURA': 2}),
    'BUILDING': (9, {
        'CREATE': 1, 'DESTROY': 2, 'KILL': 3, 'SUPPRESS': 4,
        'RESTORE_FROM_SUPPRESSION': 5, 'RESTORE_SOME_HEALTH': 6,
        'CHANGE_TEAM': 7, 'APPLY_DAMAGE': 8, 'UPDATE_WEAPON_TARGET_POSITION': 9,
    }),
    'STATS': (10, {
        'DAMAGE_AGRO': 1, 'SQUADRON_DAMAGE': 2, 'CONTROL_POINTS_DROP': 3,
        'SCOUTING_DAMAGE': 4, 'CP_PLAYER_CHANGE': 5,
        'SHUTDOWN_PLANES': 6, 'DECK_PLANES_CHANGE': 7,
    }),
}
```

### Required Changes

The event models don't need to mirror this enum 1:1, but they need to carry the right data for the renderer. Here's what the renderer actually needs:

## Renderer-Critical Events

### 1. Position Updates (VEHICLE.DESC_POS)
**Priority: P0 — without this nothing renders**

The decompiled VehicleEvents show the actual structure:
```python
# VehiclePosition (VEHICLE.DESC_POS = 769)
pos             # Vector3 — world position
dir             # Vector3 — heading direction
speed           # float — current speed
targetLocalPos  # int — main battery aim direction (packed)
torpedoLocalPos # int — torpedo aim direction (packed)
burningFlags    # int — which fire zones are burning
fov             # int — field of view / packed aim direction
isOnForsage     # bool — engine boost active
enginePower     # int — engine power level
```

The current `PositionEvent` only has x/y/z. It needs:
- `yaw` (derive from `dir` vector)
- `speed`
- `is_alive` (derive from entity property tracking)

Source: These come from `POSITION` packet types (0x08) and from entity property updates on Vehicle entities.

### 2. Ship Metadata (from JSON header + entity properties)
**Priority: P0 — needed for team display, ship names, health bars**

The replay JSON header (`meta` block) contains the player/vehicle list. Each vehicle entry has:
- `shipId` — GameParams ID for the ship
- `name` — player name
- `relation` — 0=self, 1=ally, 2=enemy
- `id` — avatar/player ID

The renderer needs a `ShipInfo` structure per ship that combines:
- Player name (from JSON header)
- Ship name (need GameParams lookup or the header may contain it)
- Ship class (DD/CA/BB/CV/SS)
- Team ID
- Max HP (from Vehicle entity `maxHealth` property, via HitLocationManagerOwner interface)
- Current HP (from Vehicle entity `health` property)

**Action:** Ensure the parser exposes a method to get the full player/vehicle roster from the JSON header, and that entity property updates for `health`, `maxHealth`, `isAlive` on Vehicle entities are tracked and queryable.

### 3. Shell Tracking (SHOT.CREATE_BULLET + SHOT.DESTROY)
**Priority: P1 — WG requirement: "show shells"**

From the decompiled ShotEvents:
```python
# CreateBullet (SHOT.CREATE_BULLET = 1029)
paramsID        # int — GameParams ID (ammo type)
pos             # Vector3 — spawn position
pitch           # float
speed           # float — muzzle velocity
tarPos          # Vector3 — target impact position
ownerID         # int — vehicleID of firing ship
salvoID         # int
shotID          # int — unique ID
gunBarrelID     # int
serverTimeLeft  # float
shooterHeight   # float
hitDistance      # float

# KillShot (SHOT.DESTROY = 1026)
ownerID         # int
pos             # Vector3 — impact position
shotID          # int
hitTypePacked   # bytearray
hitType         # int
```

These come from Avatar ClientMethods: `receiveArtilleryShots` (creates a SHOTS_PACK containing SHOT structs) and `receiveShotKills` (creates a SHOTKILLS_PACK). The .def definitions in Avatar.def define these methods and their arg types.

**Action:** The `ShotEvent` model needs a `shot_id` field to correlate creation with destruction. Emit `ShotCreatedEvent` and `ShotDestroyedEvent` separately. The renderer interpolates shell positions between creation pos and target pos over `serverTimeLeft`.

### 4. Torpedo Tracking (SHOT.CREATE_TORP)
**Priority: P1 — WG requirement: "show torpedoes"**

```python
# CreateTorpedo (SHOT.CREATE_TORP = 1028)
paramsID    # int
pos         # Vector3 — spawn position
dir         # Vector3 — direction * speed
ownerID     # int
salvoID     # int
shotID      # int
skinID      # int
```

Torpedoes come from Avatar's `receiveTorpedoes` method (TORPEDOES_PACK containing TORPEDO structs). The TORPEDO struct in alias.xml also has `armed`, `maneuverDump`, `acousticDump` for homing torps.

**Action:** Emit `TorpedoCreatedEvent` with position, direction, speed (derive from `dir` vector length), and owner. The renderer draws these as moving dots until they hit something (SHOT.DESTROY) or leave the map.

### 5. Capture Points (from BattleLogic entity properties)
**Priority: P1 — WG requirement: "capture points, status, progress"**

Capture point data comes from multiple sources:
- `BattleLogic` entity has a `state` property of type `BATTLE_LOGIC_STATE` which contains `controlPoints` (array of entity IDs for InteractiveZone entities)
- `InteractiveZone` entities have properties: `radius`, `teamId`, `componentsState` (contains `captureLogic` with `progress`, `invaderTeam`, `hasInvaders`, `isEnabled`)
- Score comes from `BattleLogic.teams` property (TEAMS_DEF type)

**Action:** Track entity property updates on InteractiveZone entities. Emit `CapturePointUpdateEvent` with position, radius, controlling team, capture progress. Track BattleLogic.teams for score updates.

### 6. Health Updates (HEALTH.DAMAGE + entity properties)
**Priority: P1 — WG requirement: "health bars"**

```python
# HealthDamage (HEALTH.DAMAGE = 1284)
vehicleID   # int — damaged ship
shooterId   # int — attacker
damage      # int — damage amount
weaponType  # int — weapon type enum
isAlly      # bool
salvoID     # int
```

Additionally, the `health` property on Vehicle entities (from HitLocationManagerOwner interface) is updated via entity property packets.

**Action:** Track both the discrete damage events AND the entity property updates for `health`. The renderer needs current HP per ship per frame. Entity property tracking is the reliable source; damage events give context (who did the damage).

### 7. Death Events (VEHICLE.KILL)
**Priority: P1 — ships need to show as dead**

From VehicleEvents:
```python
# VehicleKill (VEHICLE.KILL = 770)
killedID    # int
fraggerID   # int
deathReason # int — maps to DEATH_REASONS enum (36 values, see game-logic docs)
```

Also, the `isAlive` property on Vehicle entities flips to False.

**Action:** Emit `DeathEvent` with victim, killer, and death reason. The renderer shows dead ships differently (X marker, faded).

### 8. Team Scores
**Priority: P1 — WG requirement: "total team points"**

Comes from `BattleLogic` entity's `teams` property (TEAMS_DEF). This is a FIXED_DICT with `default` (TEAM_INFO = UINT8) and `teams` (ARRAY of TEAM_STATE, each with `teamId` and `state`).

The actual score values come from entity property updates on the BattleLogic entity, specifically the `state` property which contains the full `BATTLE_LOGIC_STATE` including mission scores.

**Action:** Track BattleLogic entity property updates. Emit `ScoreUpdateEvent` with team scores.

## Nice-to-Have Events (for bonus features)

### 9. Ribbons
From our research: ribbon IDs are known (57 entries, IDs 446-502 from padtrack/wows-constants). Since ~14.8, ribbons are derived client-side from hit events, not sent as packets. Implementing ribbon derivation requires reimplementing client game logic.

For the bounty submission: if we can show ribbons, it's a bonus. Skip for now, focus on P0/P1.

### 10. Repair Party Recoverable HP
Requires tracking the `regenerationHealth` property on Vehicle entities (from HitLocationManagerOwner interface). This is the amount of HP the Repair Party can restore.

**Action:** Track entity property `regenerationHealth` alongside `health`. The renderer can show a lighter-colored section on the health bar.

## Map Data

Minimap images and map metadata are in the gamedata repo:

```
data/spaces/<map_name>/minimap*        # PNG minimap image
data/spaces/<map_name>/space.settings  # Map metadata XML
```

The replay JSON header contains `mapName` (e.g., `"spaces/42_Neighbors"`) which maps directly to the directory name.

**Map size (world coordinate bounds):** Check `space.settings` for each map — it may contain the bounding box. If not, common world sizes are: 24000 (24km), 30000 (30km), 36000 (36km), 42000 (42km), 48000 (48km). The repo has ~84 map directories under `data/spaces/`. A lookup table of map_name → world_size may be needed as a fallback.

**Minimap image usage:** The minimap PNG is the background layer for the renderer. Load it, resize to render resolution, and draw ship positions / torpedoes / capture points on top. The coordinate mapping is: world coords (origin at center, ±half_map_size) → pixel coords (origin at top-left, 0..render_size).

## Entity Property Tracking

This is the single most important architectural requirement. The current parser decodes entity method calls well, but the renderer heavily depends on **entity property state over time**.

Properties to track per entity type:

**Vehicle (Ship):**
- `health` (FLOAT32) — current HP
- `maxHealth` (FLOAT32) — max HP
- `regenerationHealth` (FLOAT32) — repair party recoverable
- `isAlive` (BOOL)
- `isOnForsage` (BOOL) — engine boost
- `teamId` (TEAM_ID = INT8)
- `visibilityFlags` (UINT32) — is ship spotted
- `burningFlags` (UINT16) — which fire zones active
- `shipConfig` (SHIP_CONFIG) — ship build (USER_TYPE, opaque)
- `crewModifiersCompactParams` (CREW_MODIFIERS_COMPACT_PARAMS) — captain skills

**BattleLogic:**
- `state` (BATTLE_LOGIC_STATE) — full battle state including cap points, weather, missions
- `teams` (TEAMS_DEF) — team scores
- `timeLeft` (UINT16) — battle timer
- `battleStage` (UINT8)
- `battleResult` (BATTLE_RESULT) — winner team + finish reason

**InteractiveZone (Capture Point):**
- `radius` (FLOAT32)
- `teamId` (TEAM_ID)
- `componentsState` (INTERACTIVE_ZONE_STATE) — contains captureLogic with progress
- `visualState` (INTERACTIVE_ZONE_ENTITY_STATE)

**Action:** The parser needs a `GameStateTracker` or similar that maintains the current value of tracked properties per entity. On every entity property update packet, update the tracker. The EventStream should be able to query "what is Vehicle 511260's health at timestamp 120.5?"

## Output API

The renderer expects to call something like:

```python
from wows_replay_parser import parse_replay

replay = parse_replay(
    replay_path="battle.wowsreplay",
    gamedata_path="./wows-gamedata/data/scripts_entity/entity_defs"
)

# Metadata
replay.meta              # JSON header dict
replay.players           # List of player info (name, ship, team, relation)
replay.map_name          # "spaces/42_Neighbors"
replay.game_version      # "15.2.0"
replay.duration          # float, seconds

# Events (time-ordered)
replay.events            # List[GameEvent], all events sorted by timestamp

# State queries
replay.state_at(120.5)   # GameState snapshot at timestamp
replay.ship_state(entity_id, 120.5)  # ShipState at timestamp
replay.battle_state(120.5)           # BattleState (scores, timer, caps)

# Filtered events
replay.events_of_type(ShotCreatedEvent)
replay.events_in_range(60.0, 120.0)
```

The `state_at()` pattern is critical — the renderer iterates frame by frame and needs to know the complete game state at each timestamp without re-processing all events.

## Hard Constraints

1. **The parser is a general-purpose replay parsing library, not a renderer-specific tool.** Every packet must be decoded and every entity method call / property update must be captured and accessible. The renderer is ONE consumer — future consumers include replay analyzers, stat tools, damage breakdowns, and data exports. Do not skip, filter, or ignore packets/events just because the renderer doesn't need them today.

2. **No data loss in the pipeline.** Raw packet data must remain accessible even after decoding. If a method call can't be fully decoded (unknown entity type, schema mismatch), store it as a raw event with the undecoded payload — don't silently drop it.

3. **The EventStream is additive.** New event types can be added without changing existing ones. If a future consumer needs `SmokeCreatedEvent` or `PlaneSpawnedEvent`, adding those must not require refactoring the existing event system.

4. **Entity state history must be complete.** The property tracker stores every property change with its timestamp, not just the latest value. A consumer must be able to reconstruct the full history of any property on any entity. `state_at(t)` is a convenience view over this history, not the primary storage.

5. **The parser must not depend on the renderer or any specific consumer.** No imports from renderer code, no renderer-specific data structures in the parser. The parser is a standalone package.

## Implementation Priority

1. **Entity property tracking** — without this, no health bars, no cap points, no scores
2. **Position events with full data** (yaw, speed, alive status)
3. **Top-level `parse_replay()` API** with state queries
4. **Shell and torpedo events** with shot_id correlation
5. **BattleLogic state tracking** (scores, timer, caps)
6. **Player roster enrichment** (ship names, classes from JSON header)

## Automated Pipeline (Maintenance Advantage)

The wows-gamedata repo has a fully automated CI/CD pipeline that is critical for the bounty's 1-year maintenance requirement:

1. **`check-update.yml`** — runs every 6 hours, compares installed vs remote Steam build IDs
2. **`update-gamedata.yml`** — triggered on update detection or manually:
   - Updates game client via steamcmd
   - Extracts all assets via wowsunpack (entity defs, minimaps, GUI, GameParams)
   - Decrypts scripts.zip → extracted_constants.json (~39k constants)
   - Diffs against previous version, flags enum shifts
   - Commits, tags, creates GitHub release
3. **`verify_extraction.py`** — validates extraction integrity:
   - Checks file counts and sizes against thresholds
   - Detects regressions (constant count drops)
   - Detects enum shifts (multiple values in same class changed — hallmark of inserted/removed enum member)
4. **`diff_versions.py`** — structured diff between versions with enum shift classification

When a new WoWs patch drops:
- The check-update workflow detects it within 6 hours
- The update workflow runs automatically
- Entity defs, constants, and assets are updated
- The parser reads from the gamedata repo — no code changes needed
- If an enum shifts, the diff + verification flags it as a warning

This means the renderer stays working across patches without manual intervention, unless WG changes the serialization protocol itself (rare, ~1x/year).

## Testing

Get a real `.wowsreplay` file and validate:
- Ships appear at correct positions on the map
- Ships move in reasonable directions
- Deaths happen at the right time
- Health values decrease when damage events fire
- Capture points appear at correct positions

The minimap renderer IS the visual test harness — if ships move correctly on the minimap, the parser is correct. Build both in parallel.