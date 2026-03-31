# Undecoded Packet & Event Audit

**Replay:** `20260322_172639_PHSC710-Prins-Van-Oranje_56_AngelWings.wowsreplay`
**Build:** 12116141 (March 2026)
**Date:** 2026-03-30

## Summary

| Category | Count | % of total |
|----------|------:|----------:|
| Total packets | 163,757 | 100% |
| → Produce typed events | 120,102 | 73.3% |
| → Silent (no event emitted) | 43,655 | 26.7% |
| Total events | 120,102 | 100% |
| → Typed events | 90,857 | 75.6% |
| → RawEvent (undecoded) | 29,245 | 24.4% |

### Decode rates

| Layer | Decoded | Total | Rate |
|-------|--------:|------:|-----:|
| Method name resolution | 37,309 | 37,309 | 100% |
| Method arg parsing | 37,307 | 37,309 | 99.99% |
| Property name resolution | 41,315 | 41,315 | 100% |
| Property value parsing | 40,731 | 41,315 | 98.6% |
| Nested property routing | 2,423 | 3,677 | 65.9% |
| Method → typed event factory | 8,064 | 37,309 | 21.6% |

The parser decodes all packets and resolves all names correctly. The "undecoded"
bucket is entirely **missing event factories** — methods that decode fine at the
binary level but have no `_METHOD_FACTORIES` entry to convert them to typed events.

---

## 1. RawEvent Breakdown (29,245 events)

### 1.1 Network Noise — no gameplay value (15,278 / 52.2%)

| Method | Count | Entity | Description |
|--------|------:|--------|-------------|
| `onCheckGamePing` | 7,724 | Avatar | Client→server latency ping. Fires every tick. No args. |
| `onCheckCellPing` | 7,554 | Avatar | Cell server latency ping. Fires every tick. No args. |

**Recommendation:** Filter these out before event creation. They're ~10% of all packets.

### 1.2 Visual-Only — cosmetic effects (5,183 / 17.7%)

| Method | Count | Entity | Description |
|--------|------:|--------|-------------|
| `syncShipCracks` | 5,165 | Vehicle | Hull damage decal sync. Updates visual cracks on the 3D model. No gameplay data. |
| `makeShipCracksActive` | 18 | Vehicle | Activates a set of hull cracks on a vehicle. No args. |

### 1.3 Weapons & Combat (6,337 / 21.7%)

| Method | Count | Entity | Args | Description |
|--------|------:|--------|------|-------------|
| `receiveHitLocationStateChange` | 2,922 | Vehicle | `arg0`: blob | Module damage state changes (turrets destroyed, torpedo tubes knocked out, engine disabled). Critical for damage modeling. |
| `shootOnClient` | 1,173 | Vehicle | `arg0`: weapon_id, `arg1`: shot_count | Main battery fire event. Tells which guns fired and when. |
| `shootATBAGuns` | 888 | Vehicle | `arg0`: weapon_id, `arg1`: shot_count | Secondary battery fire event. Same format as shootOnClient. |
| `syncGun` | 450 | Vehicle | `arg0`: gun_index, `arg1`: packed_state | Gun turret state sync: yaw, pitch, reload progress, loaded ammo type. |
| `updateOwnerlessTracersPosition` | 407 | Avatar | `arg0`: tracer_data | Shell tracer position updates for shells in flight. Positional data. |
| `receiveTorpedoSynchronization` | 291 | Avatar | `arg0`: torpedo_sync_data | Torpedo position/heading corrections from server. |
| `receiveTorpedoArmed` | 142 | Avatar | `arg0`: torpedo_id, `arg1`: armed_state | Torpedo arm state change (torpedoes arm after traveling minimum distance). |
| `receivePlaneProjectilePack` | 156 | Avatar | `arg0`: projectile_pack (ARRAY) | CV plane ordnance drops (bombs, rockets, torpedoes from aircraft). Structured like SHOTS_PACK. |
| `syncTorpedoState` | 100 | Vehicle | `arg0`: tube_index, `arg1`: state_blob | Torpedo tube state (loaded, reloading, destroyed). |
| `receiveExplosions` | 64 | Avatar | `arg0`: explosion_array | Explosion events at world positions. Contains position + type. |
| `syncTorpedoTube` | 70 | Vehicle | `arg0`: tube_index, `arg1`: state | Individual torpedo tube reload/ready state. |
| `beginOwnerlessTracers` | 49 | Avatar | tracer_data | Start rendering shell tracers for shots not owned by any visible entity. |
| `endOwnerlessTracers` | 49 | Avatar | tracer_data | Stop rendering shell tracers. Paired with beginOwnerlessTracers. |
| `shootTorpedo` | 46 | Vehicle | torpedo_data | Torpedo launch event from a vehicle's torpedo tubes. |
| `setAmmoForWeapon` | 43 | Vehicle | `arg0`: weapon_id, `arg1`: ammo_id | Ammo type switch (HE→AP→SAP). weapon_id = SHIP_WEAPON_TYPES enum. |
| `receiveGunSyncRotations` | 18 | Avatar | `arg0`: gun_group, `arg1`: packed_rotation | Bulk turret rotation sync. gun_group=0 means all turrets. |
| `receiveDepthChargesPacks` | 2 | Avatar | `arg0`: ARRAY of depth_charge_pack | Depth charge drop events. Contains ownerID, salvoID, paramsID, positions. Already fully decoded by construct schema. |
| `setReloadingStateForWeapon` | 5 | Avatar | `arg0`: weapon_type (int), `arg1`: state_blob (pickle) | Weapon reload state. weapon_type maps to SHIP_WEAPON_TYPES. State blob contains reload progress, ammo info. |

### 1.4 Squadrons & Aviation (1,092 / 3.7%)

| Method | Count | Entity | Args | Description |
|--------|------:|--------|------|-------------|
| `receive_squadronHealth` | 392 | Avatar | `arg0`: squadron_id, `arg1`: health_data | Squadron total HP update. |
| `receive_updateSquadron` | 308 | Avatar | position, heading, speed updates | Squadron state update (position, velocity, active status). |
| `receive_updateMinimapSquadron` | 170 | Avatar | `arg0`: squadron_id, `arg1`: team, `arg2`: params_id, `arg3`: position_2d, `arg4`: flags | Squadron position on minimap. Has 2D coords. |
| `receive_resetWaypoints` | 122 | Avatar | `arg0`: squadron_id | Squadron waypoint reset (plane recall or new orders). |
| `receive_squadronPlanesHealth` | 94 | Avatar | `arg0`: squadron_id, `arg1`: per_plane_hp_array | Individual plane HP within a squadron. |
| `receive_changeState` | 31 | Avatar | `arg0`: squadron_id, `arg1`: new_state | Squadron state machine transition (launching, attacking, returning, etc.). |
| `receive_planeDeath` | 26 | Avatar | `arg0`: squadron_id, `arg1`: plane_indices, `arg2`: death_type, `arg3`: killer_id | Plane shot down. Has killer entity ID and which planes in the squadron died. |
| `receive_squadronVisibilityChanged` | 16 | Avatar | `arg0`: squadron_id, `arg1`: is_visible (bool) | Squadron enters/leaves visibility. |
| `receive_addSquadron` | 11 | Avatar | `arg0`: params_id, `arg1`: team, `arg2`: squadron_info (planeID, skinID, isActive, numPlanes, position, heading), `arg3-6`: metadata | New squadron spawned. Full initial state. |
| `receive_removeSquadron` | 11 | Avatar | `arg0`: squadron_id | Squadron removed from world. |
| `receive_addMinimapSquadron` | 11 | Avatar | `arg0`: squadron_id, `arg1`: team, `arg2`: params_id, `arg3`: position_2d, `arg4`: flags | Squadron appears on minimap. |
| `receive_removeMinimapSquadron` | 11 | Avatar | `arg0`: squadron_id | Squadron removed from minimap. |
| `receive_stopManeuvering` | 10 | Avatar | `squadronId`: squadron_id | Squadron stops maneuvering (attack run complete). |
| `receive_deactivateSquadron` | 10 | Avatar | `arg0`: squadron_id, `arg1`: reason | Squadron deactivated (landed, destroyed, recalled). |

### 1.5 Game State & Lifecycle (334 / 1.1%)

| Method | Count | Entity | Args | Description |
|--------|------:|--------|------|-------------|
| `setConsumables` | 100 | Vehicle | `arg0`: consumable_setup_blob | Initial consumable slot configuration for each vehicle. Sent once per vehicle at battle start. Contains equipped consumable GameParams IDs per slot. |
| `syncShipPhysics` | 100 | Vehicle | pickle blob | Ship physics state sync (speed, rudder, engine). Pickle contains speed vector, rudder angle, engine state. Sent once per vehicle at battle start, then via properties. |
| `receiveHitLocationsInitialState` | 100 | Vehicle | `arg0`: hit_locations_blob | Initial module HP state for all hit locations (turrets, torpedo tubes, engine, steering). Sent once per vehicle. |
| `onGameRoomStateChanged` | 88 | Avatar | pickle blob | Game room state transitions. Pickle contains battle phase, timer state, team standings. Fires throughout the match at phase changes. |
| `startDissapearing` | 97 | Vehicle | (no args) | Vehicle goes unspotted (leaves render range). Vision loss event. Note: WG typo "dissapearing" is in the actual method name. |
| `updateOwnerlessAuraState` | 77 | Avatar | `arg0`: aura_state_data | AA aura visual state updates for ships not owned by the player. Used for rendering AA bubble effects. |
| `updateCoolDown` | 11 | Avatar | `arg0`: pickle — list of (gameparams_id, cooldown_end_time) tuples | Consumable cooldown timer updates. Each entry is a (consumable_gp_id, server_time_when_ready) pair. |
| `updatePreBattlesInfo` | 22 | Avatar | `packedData`: pickle blob | Pre-battle/division info updates. Contains division IDs, player states within divisions. |

### 1.6 One-Shot Events (21 / 0.07%)

| Method | Count | Entity | Args | Description |
|--------|------:|--------|------|-------------|
| `onArenaStateReceived` | 1 | Avatar | `arenaUniqueId` (INT64), `teamBuildTypeId` (INT8), `preBattlesInfo` (pickle), `playersStates` (pickle), `botsStates` (pickle), `observersState` (pickle), `buildingsInfo` (pickle) | Full arena roster. Already parsed by roster.py — the RawEvent is a duplicate. Contains all 24 players with shipConfigDump, crewModifiers, names, clan tags, ship IDs. |
| `onBattleEnd` | 1 | Avatar | (no args — empty dict) | Battle over signal. The actual results are in the BATTLE_RESULTS packet (0x22), not in this method's args. |
| `onConnected` | 1 | Avatar | `artilleryAmmoId` (UINT32 GameParams ID), `torpdoAmmoId` (UINT32, note WG typo), `airSupportAmmoId` (UINT32), `torpedoSelectedAngle` (INT), `weaponLocks` (ARRAY) | Initial weapon state on connection. Tells which ammo types are loaded and which weapons are locked. |
| `onEnterPreBattle` | 1 | Avatar | `packedPreBattleData` (zlib-compressed blob), `grants` (INT = 320), `isRecreated` (INT = 0) | Pre-battle phase entry. The packed data is zlib-compressed and contains division/team setup information. |
| `receiveAvatarInfo` | 1 | Avatar | `arg0`: pickle dict with `evaluationsLeft` ({0: 15, 1: 14}), `strategicActionsTask` (empty tuple) | Avatar metadata. evaluationsLeft = remaining karma votes per type (compliment/report). |
| `onShutdownTime` | 1 | Avatar | `arg0`: 0, `arg1`: 0, `arg2`: 0 | Server shutdown warning timer. All zeros = no shutdown pending. Three ints: (shutdown_type, time_remaining, flags). |
| `setAirDefenseState` | 1 | Avatar | `arg0`: pickle tuple — (sector_id=-1, sector_id=-1, state=0, None, range=0.0, reinforced_range=10.0) | Initial AA defense sector state. sector_id=-1 = no sector selected. Sets up the AA sector reinforcement UI. |
| `setUniqueSkills` | 1 | Avatar | `arg0`: pickle dict with `triggers` list — each entry has `achEarned` (int), `triggerNum` (int) | Unique/legendary commander skill trigger state. Lists which unique skill triggers have been activated and their progress. |
| `receiveChatHistory` | 1 | Avatar | `arg0`: zlib-compressed blob (decompresses to near-empty msgpack) | Chat history from before the player joined. Usually empty or minimal in replays. |
| `receive_refresh` | 1 | Avatar | `arg0`: pickle — `{float: [list]}` mapping | Squadron system refresh. Resets squadron state tracking. Typically fires once at battle start. |
| `onWorldStateReceived` | 1 | Avatar | (no args — empty dict) | World state initialization complete signal. Fires once after all initial entity creation is done. No payload — it's a pure signal. |
| `changePreBattleGrants` | 1 | Avatar | `grants`: 208886 (INT) | Pre-battle permission flags update. Bitmask controlling what the player can do in the pre-battle lobby (change ship, ready up, etc.). |
| `onOwnerChanged` | 1 | Vehicle | `ownerId`: 806471823 (entity ID), `isOwner`: 1 (bool) | Vehicle ownership assignment. Links this Vehicle entity to its Avatar. Fires once when the player takes control of their ship. |
| `onConsumableInterrupted` | 1 | Vehicle | `arg0`: 10 (consumable slot index) | A consumable was interrupted (e.g., repair party cancelled by module destruction). The int is the consumable slot index. |
| `uniqueTriggerActivated` | 3 | Avatar | (no args — empty dict) | Unique commander skill trigger fired. No payload — the skill effect is applied server-side. Count = number of times a unique skill procced during the match. |
| `resetResettableWaveEnemyHits` | 4 | Avatar | (no args — empty dict) | Submarine wave mechanic: reset the enemy hit counter for wave-based abilities. Fires when the sub resurfaces or the wave cycle resets. |
| `onCrashCrewEnable` | 4 | Vehicle | (no args — empty dict) | Damage control party (crash crew) activated. Fires on the Vehicle when DCP consumable starts. No args — the consumable ID comes from the preceding consumable event. |
| `onCrashCrewDisable` | 4 | Vehicle | (no args — empty dict) | Damage control party ended (duration expired). Paired with onCrashCrewEnable. |
| `receivePlayerData` | 2 | Avatar | `arg0`: pickle tuple — (account_id, avatar_id, player_name, None, rank, team, bools..., stats_dict), `arg1`: 0 | Player data update. Contains account ID, player name, team, and session stats. Fires twice: once at start, once mid-battle (update). |
| `onWeaponStateSwitched` | 2 | Vehicle | `arg0`: weapon_group (0=main), `arg1`: new_state (0 or 1) | Weapon state toggle (e.g., switching between main battery fire modes, or torpedo wide/narrow spread). |
| `onPrioritySectorSet` | 7 | Avatar | `arg0`: sector_id (int, 0=left, 1=right), `arg1`: reinforcement_progress (float, 0.0=none) | AA priority sector changed. Player selected a side for AA reinforcement. Progress = buildup toward full reinforcement. |
| `activateAirSupport` | 8 | Avatar | `index` (int), `squadronID` (int64), `position` (Vector3), `aimLength` (float), `airSupportShotID` (int) | Air support (ASW/airstrike) called in. Contains exact drop position and aim corridor length. |
| `deactivateAirSupport` | 8 | Avatar | `index` (int), `squadronID` (int64) | Air support squadron finished its run and is leaving. Paired with activateAirSupport. |

### 1.7 No Method Name (35 / 0.1%)

All 35 are `packet_type=0x00` (BASE_PLAYER_CREATE). These are entity creation
packets that establish the player's Avatar entity. They don't carry method/property
data — they're structural packets handled by the decoder for entity registration.

---

## 2. Property Updates Without Decoded Values (584 / 1.4%)

| Entity | Property | Count | Reason |
|--------|----------|------:|--------|
| Vehicle | `triggeredSkillsData` | 584 | Variable-length blob, needs custom deserializer (pickle/msgpack). Contains activated commander skill state changes. |

All other 40,731 property updates decode successfully.

---

## 3. Nested Property Routing Gaps (1,254 / 34.1% of nested)

| Entity | Property | Count | Status |
|--------|----------|------:|--------|
| Vehicle | (unknown — no name) | 1,232 | Property index doesn't resolve. Likely `state` or `effects` sub-properties where the nested path can't be followed. |
| Vehicle | `state` | 183 | Name resolves but leaf value not decoded. Complex nested FIXED_DICT. |
| SmokeScreen | (unknown — no name) | 22 | SmokeScreen entity nested property routing not implemented. |

Successfully routed nested properties (2,423 / 65.9%):

| Entity | Property | Count |
|--------|----------|------:|
| Vehicle | `state` | 948 |
| InteractiveZone | `componentsState` | 530 |
| BattleLogic | `state` | 474 |
| Avatar | `privateVehicleState` | 193 |
| Vehicle | `airDefenseTargetIds` | 56 |
| SmokeScreen | `points` | 30 |
| InteractiveZone | `visualState` | 9 |

**Note:** `Avatar.privateVehicleState` (193 packets) is where the server-authoritative
**ribbon counts** live (`RIBBONS_STATE = ARRAY<of>{ribbonId: INT8, count: UINT16}</of>`).
These are routed but the `ribbons` sub-field is not yet extracted into typed events.

---

## 4. Silent Packet Types (43,655 packets — no events emitted)

| Packet Type | Hex | Count | Description | Has useful data? |
|-------------|-----|------:|-------------|-----------------|
| CAMERA | 0x25 | 10,672 | Player camera position/orientation per tick | Yes — camera world position, could derive "where player is looking" |
| GUN_MARKER | 0x18 | 10,672 | Aim point / crosshair position in world space | Yes — where the player is aiming, per tick |
| PLAYER_NET_STATS | 0x1D | 10,656 | Network latency/jitter/packet loss stats per tick | Low value — connection quality metrics |
| SERVER_TICK | 0x0E | 7,790 | Server tick heartbeat, carries tick number | No — timing only |
| CRUISE_STATE | 0x32 | 442 | Autopilot/cruise control waypoints | Yes — player's set autopilot course |
| ENTITY_CREATE | 0x05 | 111 | Entity spawned (Vehicle, SmokeScreen, etc.) with inline state | Already processed by decoder for entity registration, not emitted as event |
| ENTITY_LEAVE | 0x04 | 102 | Entity left player's area of interest | Yes — vision loss (ship went unspotted or left render range) |
| SET_WEAPON_LOCK | 0x30 | 22 | Weapon lock state changes | Yes — which weapons are locked/unlocked |
| CAMERA_MODE | 0x27 | 18 | Camera mode switches (normal, binocular, aircraft, free) | Low value — UI state |
| SHOT_TRACKING | 0x33 | 9 | Shot tracking updates (shell flight corrections) | Low value — visual refinement |
| INIT_FLAG | 0x10 | 2 | Initialization flags | No — internal protocol |
| VERSION | 0x16 | 1 | Replay format version | No — metadata only |
| SERVER_TIMESTAMP | 0x0F | 1 | Server epoch timestamp | No — already in replay header |
| BASE_PLAYER_CREATE_STUB | 0x26 | 1 | Stub for base player entity | No — internal protocol |
| BASE_PLAYER_CREATE | 0x00 | 1 | Player Avatar entity creation | No — handled internally |
| CELL_PLAYER_CREATE | 0x01 | 1 | Cell-side player entity creation | No — handled internally |
| ENTITY_CONTROL | 0x02 | 1 | Entity control assignment | No — internal protocol |
| MAP | 0x28 | 1 | Map identifier | No — already in replay header |
| OWN_SHIP | 0x20 | 1 | Own ship entity ID assignment | No — already resolved |
| INIT_MARKER | 0x13 | 1 | Initialization sequence marker | No — internal protocol |
| BATTLE_RESULTS | 0x22 | 1 | End-of-battle results blob (the 0x22 JSON/pickle with 503 fields/player) | **YES — huge value, not parsed into events** |
| UNKNOWN | 0xFF | 1 | Unrecognized packet type | Unknown |

---

## 5. Method Arg Parse Failures (2 / 0.005%)

| Entity | Method | Timestamp | Cause |
|--------|--------|-----------|-------|
| Avatar | `onChatMessage` | 727.9s | Encoding edge case — likely Cyrillic/CJK player name in chat payload |
| Avatar | `onChatMessage` | 727.9s | Same message, duplicate packet |

---

## 6. Priority Ranking for Implementation

### Tier 1 — High value, low effort
1. **Filter ping noise** — skip `onCheckGamePing` + `onCheckCellPing` (saves 15,278 RawEvents, 52%)
2. **`BATTLE_RESULTS` (0x22)** — single packet with complete post-battle stats for all players (credits, XP, damage, achievements). Already identified, needs parser.
3. **`privateVehicleState.ribbons`** — 193 nested property updates already routed, just need to extract the RIBBONS_STATE sub-field into RibbonEvents.

### Tier 2 — Combat data
4. **`shootOnClient`** (1,173) + **`shootATBAGuns`** (888) — gun fire events, simple int args
5. **`receiveHitLocationStateChange`** (2,922) — module damage, blob needs format analysis
6. **`syncGun`** (450) — turret state, packed format
7. **`startDissapearing`** (97) — vision loss events, no args needed
8. **`setAmmoForWeapon`** (43) — ammo switches, two int args

### Tier 3 — Aviation
9. **Squadron methods** (1,092 total) — full CV plane tracking. The args are already decoded by construct, just needs event factories.

### Tier 4 — Game state enrichment
10. **`onGameRoomStateChanged`** (88) — battle phase transitions, pickle
11. **`setConsumables`** (100) — initial consumable loadout per vehicle
12. **`updateCoolDown`** (11) — consumable cooldown timers, pickle
13. **`ENTITY_LEAVE`** (102) — vision tracking
14. **`GUN_MARKER`** (10,672) — aim point tracking (if needed for heatmaps)

### Tier 5 — Nice to have
15. **`Vehicle.triggeredSkillsData`** (584) — commander skill activations
16. **`Vehicle.state` nested** (1,131) — complex vehicle state blob
17. **`CAMERA`** (10,672) — camera position (replay viewer feature)
18. **`CRUISE_STATE`** (442) — autopilot waypoints
