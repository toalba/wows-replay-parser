# Task: Expose All Decoded But Hidden Data

The parser decodes significantly more data than it exposes through its public API (`ParsedReplay`, `GameState`, `ShipState`, `BattleState`, `PlayerInfo`, events). This task is to systematically expose everything that's already decoded or decodable.

**Guiding principle:** The parser is a general-purpose library. Every piece of data in the replay should be accessible to consumers. The minimap renderer is one consumer, but stat tools, data exports, and analysis tools are equally valid. Expose everything — let consumers decide what they need.

**Reference:** `UNDECODED_AUDIT.md` has packet counts and method signatures from a real replay. `CLAUDE.md` has entity property layouts, alias structs, and the full architecture. The `.def` files and `alias.xml` are the source of truth for all types and signatures.

---

## Cluster 1: PlayerInfo — Roster Fields

**File:** `roster.py` (lines 94-110, 384-397)

The `onArenaStateReceived` pickle is fully decoded into `ap` dicts with all 38 player fields, but only 12 are mapped to `PlayerInfo`. Add the missing useful fields:

### Fields to add to `PlayerInfo`:

| Field | Source key | Type | Notes |
|---|---|---|---|
| `prebattle_id` | `prebattleId` | `int` | Division ID — players in the same division share this value. 0 = no division. |
| `is_prebattle_owner` | `isPreBattleOwner` | `bool` | Division leader flag |
| `clan_id` | `clanID` | `int` | Numeric clan ID |
| `avatar_id` | `avatarId` | `int` | Avatar entity ID in the game world |
| `realm` | `realm` | `str` | Server region ("EU", "NA", "ASIA", "RU") |
| `skin_id` | `skinId` | `int` | Ship skin/camo visual ID |
| `ship_params_id` | `shipParamsId` | `int` | Ship GameParams ID (different from ship_id which is Vehicle entity ID in some code paths) |
| `is_leaver` | `isLeaver` | `bool` | Player disconnected/left |
| `is_connected` | `isConnected` | `bool` | Player is connected at time of arena state |
| `is_hidden` | `isHidden` | `bool` | Player is hidden (private profile) |
| `dog_tag` | `dogTag` | `Any` | Dog tag cosmetic data (complex structure, expose as-is) |
| `player_mode` | `playerMode` | `dict` | Player mode state |
| `ship_components` | `shipComponents` | `dict` | Ship module loadout components |

### Also add to `_match_via_arena_state` (line 384-397):

Map each new field from the `ap` dict to the `PlayerInfo` constructor, following the same pattern as existing fields (e.g. `clan_tag=ap.get("clanTag", "")`).

### Ignored pickle blobs to decode:

The `_extract_arena_blobs` function (line 198) extracts 5 pickles but only uses indices 1 (`playersStates`) and 2 (`botsStates`). Decode and expose the remaining three:

| Pickle index | Name | Content | Where to expose |
|---|---|---|---|
| `[0]` | `preBattlesInfo` | `dict[int, list]` — team_id → list of division slots, each slot has `{info: {}, id: <prebattle_id>}` or None | Add to `ParsedReplay` as `prebattles_info: dict` |
| `[3]` | `observersState` | List of observer/spectator entries (same tuple format as players, uses player key map) | Add to `ParsedReplay` as `observers: list[PlayerInfo]` or separate `ObserverInfo` |
| `[4]` | `buildingsInfo` | List of building entries | Add to `ParsedReplay` as `buildings_info: list[dict]` |

---

## Cluster 2: ShipState — Vehicle Properties

**File:** `state/models.py` (ShipState, lines 20-42), `state/tracker.py` (iter_states Vehicle building, ~line 536-617)

The tracker's `_current` dict stores all Vehicle properties from ENTITY_CREATE inline state + ENTITY_PROPERTY updates, but `ShipState` only exposes 15 of ~54 properties. Add:

### Fields to add to `ShipState`:

| Field | Source property | Type | Notes |
|---|---|---|---|
| `is_on_forsage` | `isOnForsage` | `bool` | Engine boost active |
| `engine_power` | `enginePower` | `int` | Engine power level (0-100) |
| `engine_dir` | `engineDir` | `int` | Engine direction |
| `speed_sign_dir` | `speedSignDir` | `int` | Speed direction (-1/0/+1) |
| `max_speed` | `maxServerSpeedRaw` | `float` | Maximum speed |
| `rudder_angle` | `ruddersAngle` | `float` | Rudder deflection angle |
| `deep_rudder_angle` | `deepRuddersAngle` | `float` | Submarine deep rudder angle |
| `selected_weapon` | `selectedWeapon` | `int` | Currently selected weapon class |
| `is_invisible` | `isInvisible` | `bool` | Stealth/cloak state |
| `has_active_squadron` | `hasActiveMainSquadron` | `bool` | CV squadron active |
| `is_in_rage_mode` | `isInRageMode` | `bool` | Rage mode flag |
| `respawn_time` | `respawnTime` | `float` | Respawn countdown |
| `blocked_controls` | `blockedControls` | `int` | Controls locked flags |
| `oil_leak_state` | `oilLeakState` | `int` | Oil leak damage level |
| `owner` | `owner` | `int` | Owner avatar entity ID |
| `regen_crew_hp_limit` | `regenCrewHpLimit` | `float` | Crew regen capacity |
| `buoyancy` | `buoyancy` | `float` | Sinking state |
| `air_defense_disp_radius` | `airDefenseDispRadius` | `float` | AA dispersion radius |
| `weapon_lock_flags` | `weaponLockFlags` | `int` | Weapon target lock state |
| `target_local_pos` | `targetLocalPos` | `int` | Main battery aim direction (packed) |
| `torpedo_local_pos` | `torpedoLocalPos` | `int` | Torpedo aim direction (packed) |

### Wire these in `iter_states()` and `state_at()`:

Follow the same pattern as existing fields — read from `props.get("propertyName", default)` and assign to the new ShipState fields in both code paths.

---

## Cluster 3: BattleState — BattleLogic Properties

**File:** `state/models.py` (BattleState, lines 85-98), `state/tracker.py` (`_build_battle_state`)

### Fields to add to `BattleState`:

| Field | Source property | Type | Notes |
|---|---|---|---|
| `battle_type` | `battleType` | `int` | Match type ID (Random, Ranked, Clan, etc.) |
| `duration` | `duration` | `int` | Total battle time in seconds |
| `map_border` | `mapBorder` | `dict \| None` | MAP_BORDER — paramsId + position |

---

## Cluster 4: Entity Methods → Events

**File:** `events/models.py`, `events/stream.py`

These entity methods have their args fully decoded by the construct schema system but no event factory exists in `_METHOD_FACTORIES` to convert them to typed events. For each, create an event model and a factory.

### 4a: Combat Methods (Vehicle)

| Method | Count/replay | Args | Suggested event |
|---|---|---|---|
| `shootOnClient` | ~1173 | `weapon_type`, `gun_bits` | `GunFireEvent` — which guns fired |
| `shootATBAGuns` | ~888 | `weapon_type`, `gun_bits` | `SecondaryFireEvent` or reuse `GunFireEvent` with a flag |
| `syncGun` | ~450 | `weapon_type`, `gun_id`, `yaw`, `pitch`, `alive`, `reload_perc`, `loaded_ammo` | `GunStateEvent` — turret angles, reload progress. **Renderer opinion:** tracking gun yaw per entity over time (like a property) would be more useful than discrete events, since the renderer queries state at a timestamp. Consider adding gun state to `ShipState` or a separate queryable timeline. |
| `syncTorpedoTube` | ~70 | `gun_id`, `yaw`, `pitch`, `alive`, `reload_perc`, `state` | `TorpedoTubeStateEvent` — same consideration as syncGun |
| `syncTorpedoState` | ~100 | `state` (UINT8) | `TorpedoSpreadEvent` — torpedo spread pattern |
| `setAmmoForWeapon` | ~43 | `weapon_type`, `ammo_params_id`, `is_reload` | `AmmoSwitchEvent` — ammo type change (AP/HE/SAP) |
| `onWeaponStateSwitched` | ~2 | `weapon_type`, `new_state` | `WeaponStateSwitchEvent` |
| `shootTorpedo` | ~46 | `id`, `position`, `id2`, `id3`, `bool` | `TorpedoLaunchEvent` — individual torp salvo |
| `shootDepthCharge` | ~2 | `id`, `count` | `DepthChargeLaunchEvent` |
| `receiveGunSyncRotations` | ~18 | `weapon_type`, `GUN_DIRECTIONS` (8×2-bit packed) | `GunRotationSyncEvent` — per-turret barrel yaw |
| `receiveHitLocationStateChange` | ~2922 | blob | `ModuleDamageEvent` — module (turret/engine/rudder) state change. Needs format analysis of the blob. |
| `setReloadingStateForWeapon` | ~5 | `weapon_type`, `state_blob` (pickle) | `WeaponReloadStateEvent` |
| `syncShipCracks` | ~5165 | blob, blob | `ShipCracksEvent` — visual hull damage (low priority, mostly cosmetic) |
| `syncShipPhysics` | ~100 | `INT8`, blob (pickle) | `ShipPhysicsEvent` — physics state |
| `startDissapearing` | ~97 | (no args) | `ShipDisappearEvent` — vision loss. Note: WG typo in method name is intentional. |
| `onRespawned` | rare | `reset_consumables_count`, `initial_speed`, `yaw` | `RespawnEvent` |
| `onCrashCrewEnable` | ~4 | (no args) | `DamageControlStartEvent` |
| `onCrashCrewDisable` | ~4 | (no args) | `DamageControlEndEvent` |
| `syncRageMode` | rare | `hit_counter`, `state`, `state_time_passed` | `RageModeEvent` |
| `receiveMirrorDamage` | rare | `damage` (FLOAT) | `MirrorDamageEvent` |

### 4b: Consumable Methods (Vehicle)

| Method | Args | Suggested event |
|---|---|---|
| `onConsumableSelected` | `consumable_type`, `is_selected` | `ConsumableSelectedEvent` |
| `onConsumableEnabled` | `consumable_id`, `enabled` | `ConsumableEnabledEvent` |
| `onConsumablePaused` | `consumable_type` | `ConsumablePausedEvent` |

Note: `onConsumableInterrupted` already exists in the tracker but isn't emitted as an event.

### 4c: Avatar Combat Methods

| Method | Count/replay | Args | Suggested event |
|---|---|---|---|
| `receiveExplosions` | ~64 | `ARRAY<EXPLOSION>` — each has position, type, radius | `ExplosionEvent` per explosion. **Renderer opinion:** these would be great for visual FX on the minimap (flash at impact point). |
| `receiveMissile` | rare | `MISSILE` — launch position, trajectory | `MissileLaunchEvent` |
| `updateMissileWaypoints` | rare | `shot_id`, `fly_time`, `AERIAL_PATH` | `MissileWaypointEvent` |
| `receiveMissileDamage` | rare | `shot_id`, `damager_id`, `damage` | `MissileDamageEvent` |
| `receiveMissileKill` | rare | `shot_id`, `hit_pos`, `hit_type` | `MissileImpactEvent` |
| `receivePlaneProjectilePack` | ~156 | `ARRAY<PLANE_PROJECTILE_PACK>` | `PlaneProjectileEvent` — CV aircraft strafing |
| `receivePlaneSkipBombPacks` | rare | `ARRAY<PLANE_SKIP_BOMB_PACK>` | `SkipBombEvent` |
| `receivePlaneRocketPacks` | rare | `ARRAY<PLANE_ROCKET_PACK>` | `RocketEvent` |
| `receiveDepthChargesPacks` | ~2 | `ARRAY<DEPTH_CHARGES_PACK>` | `DepthChargeEvent` — already decoded by construct |
| `receiveLaserBeams` | rare | `ARRAY<LASER_BEAM>` | `LaserBeamEvent` |
| `updateOwnerlessTracersPosition` | ~407 | tracer position data | `TracerPositionEvent` — shell tracer updates |
| `beginOwnerlessTracers` | ~49 | tracer data | `TracerStartEvent` |
| `endOwnerlessTracers` | ~49 | tracer data | `TracerEndEvent` |
| `receiveTorpedoSynchronization` | ~291 | torpedo sync data | `TorpedoSyncEvent` — server torpedo position correction |
| `receiveTorpedoArmed` | ~142 | `torpedo_id`, `armed_state` | `TorpedoArmedEvent` |

### 4d: Submarine/Sonar Methods (Avatar)

| Method | Args | Suggested event |
|---|---|---|
| `receivePingerShot` | `weapon_type`, `gun_id`, `yaw` | `SonarPingEvent` |
| `resetPinger` | `weapon_type` | `SonarResetEvent` |
| `onPingerWaveEnemyHit` | various | `SonarHitEvent` |
| `receiveWaveFromEnemy` | `shooter_id`, `local_point`, `side`, `lifetime`, `width`, `count`, `yaw`, `weapon_type`, `is_resettable` | `SonarWaveReceivedEvent` |
| `updateWaveEnemyHit` | `target_id`, `lifetime`, `width`, `count`, `weapon_type` | `SonarHitUpdateEvent` |
| `updateInvisibleWavedPoint` | `target_id`, `position`, `weapon_type` | `SonarDetectionEvent` |
| `addSubmarineHydrophoneTargets` | `targets_info`, `zone_life_time` | `HydrophoneTargetEvent` |
| `syncSurfacingTime` | `INT32` | `SubSurfacingEvent` |

### 4e: AA/Priority Sector (Avatar)

| Method | Args | Suggested event |
|---|---|---|
| `onPrioritySectorSet` | `sector_id`, `reinforcement_progress` | `AASectorEvent` |
| `onNextPrioritySectorSet` | `sector_id` | `AASectorQueueEvent` |
| `updateOwnerlessAuraState` | `aura_state_data` | `AAAuraStateEvent` |
| `setAirDefenseState` | pickle blob | `AirDefenseStateEvent` |

### 4f: Squadron Methods (Avatar)

These are already partially tracked for the aircraft state model, but they should ALSO emit events. ~1092 packets/replay.

| Method | Suggested event |
|---|---|
| `receive_addSquadron` | `SquadronSpawnEvent` |
| `receive_removeSquadron` | `SquadronRemoveEvent` |
| `receive_updateSquadron` | `SquadronUpdateEvent` |
| `receive_changeState` | `SquadronStateChangeEvent` |
| `receive_squadronHealth` | `SquadronHealthEvent` |
| `receive_squadronPlanesHealth` | `SquadronPlaneHealthEvent` |
| `receive_planeDeath` | `PlaneDeathEvent` |
| `receive_squadronVisibilityChanged` | `SquadronVisibilityEvent` |
| `receive_deactivateSquadron` | `SquadronDeactivateEvent` |
| `receive_stopManeuvering` | `SquadronStopManeuverEvent` |
| `receive_addMinimapSquadron` | `MinimapSquadronAddEvent` |
| `receive_removeMinimapSquadron` | `MinimapSquadronRemoveEvent` |
| `receive_updateMinimapSquadron` | `MinimapSquadronUpdateEvent` |
| `receive_resetWaypoints` | `SquadronWaypointResetEvent` |
| `receive_refresh` | `SquadronRefreshEvent` |

### 4g: Game State Methods (Avatar)

| Method | Count/replay | Args | Suggested event |
|---|---|---|---|
| `onGameRoomStateChanged` | ~88 | pickle blob — battle phase, timer, team standings | `GameRoomStateEvent` — decode pickle, expose as dict or structured fields |
| `updateCoolDown` | ~11 | pickle — list of `(gameparams_id, cooldown_end_time)` | `CooldownUpdateEvent` |
| `updatePreBattlesInfo` | ~22 | pickle — division info updates | `PreBattleUpdateEvent` |
| `onConnected` | 1 | `artillery_ammo_id`, `torpedo_ammo_id`, `air_support_ammo_id`, `torpedo_angle`, `weapon_locks` | `ConnectedEvent` — initial weapon state |
| `onEnterPreBattle` | 1 | zlib blob, `grants`, `is_recreated` | `PreBattleEnterEvent` |
| `receiveAvatarInfo` | 1 | pickle — evaluations left, strategic actions | `AvatarInfoEvent` |
| `receivePlayerData` | ~2 | pickle — account, name, team, stats | `PlayerDataEvent` |
| `onNewPlayerSpawned` | rare | spawn notification | `PlayerSpawnedEvent` |
| `onBattleEnd` | 1 | (no args) | `BattleEndEvent` (may already exist — verify) |
| `onShutdownTime` | 1 | `type`, `time_remaining`, `flags` | `ShutdownTimeEvent` |
| `setUniqueSkills` | 1 | pickle — trigger state | `UniqueSkillsEvent` |
| `receiveChatHistory` | 1 | zlib blob → msgpack | `ChatHistoryEvent` |
| `onWorldStateReceived` | 1 | (no args) | `WorldStateReceivedEvent` |
| `changePreBattleGrants` | 1 | `grants` bitmask | `PreBattleGrantsEvent` |
| `onAchievementEarned` | varies | achievement data | `AchievementEvent` (may already exist — verify) |
| `uniqueTriggerActivated` | ~3 | (no args) | `UniqueTriggerEvent` |
| `resetResettableWaveEnemyHits` | ~4 | (no args) | `WaveResetEvent` |

### 4h: Vehicle One-Shot Methods

| Method | Args | Suggested event |
|---|---|---|
| `onOwnerChanged` | `owner_id`, `is_owner` | `OwnerChangedEvent` |
| `setConsumables` | pickle blob — consumable slot configuration | `ConsumablesSetEvent` — initial consumable loadout per vehicle. Already tracked internally for slot mapping; also emit as event. |
| `receiveHitLocationsInitialState` | blob — module HP state | `HitLocationsInitEvent` — initial module HP for all hit locations |
| `teleport` | `VECTOR3`, `yaw`, `BOOL` | `TeleportEvent` |

---

## Cluster 5: Packet Types → Events or State

**File:** `packets/decoder.py`, `state/tracker.py`

These packet types are decoded at the binary level but their data is either discarded or stored internally without being exposed.

### 5a: BATTLE_RESULTS (0x22) — HIGH PRIORITY

Single packet at end of match containing the complete post-battle stats blob for all players. This is extremely valuable data (credits, XP, damage, detailed stats per player).

The raw payload is available on the packet object but is not parsed. Decode the blob (JSON or pickle format — investigate which) and expose it as:
- A `BattleResultsEvent` in the event stream
- A `battle_results` field on `ParsedReplay`

### 5b: Tracked But Not Exposed

| Packet | Hex | Count/replay | Current state | Action |
|---|---|---|---|---|
| CAMERA | 0x25 | ~10,672 | Position stored in `tracker._camera_positions` | Expose via `ParsedReplay.camera_positions` or a public method `tracker.camera_at(t)` |
| GUN_MARKER | 0x18 | ~10,672 | Raw payload stored, not decoded | Decode 52-byte structure (aim point in world space), expose as queryable timeline |
| ENTITY_LEAVE | 0x04 | ~102 | Leave time stored in `tracker._entity_leave_times` | Emit `EntityLeaveEvent` with entity_id and timestamp |

### 5c: Decoded But Discarded

| Packet | Hex | Count/replay | Action |
|---|---|---|---|
| CRUISE_STATE | 0x32 | ~442 | Store in tracker, expose as `CruiseStateEvent` or on `ShipState` |
| SET_WEAPON_LOCK | 0x30 | ~22 | Store in tracker, expose as `WeaponLockEvent` |
| CAMERA_MODE | 0x27 | ~18 | Store in tracker, expose as `CameraModeEvent` |
| SHOT_TRACKING | 0x33 | ~9 | Emit `ShotTrackingEvent` |
| PLAYER_NET_STATS | 0x1D | ~10,656 | Decode and expose as queryable timeline (ping, packet loss) |

### 5d: Empty Handlers (Not Decoded)

| Packet | Hex | Action |
|---|---|---|
| CameraFreeLook | 0x2F | Decode payload structure, emit `CameraFreeLookEvent` |
| SubController | 0x31 | Decode payload structure, emit `SubControllerEvent` |
| InitFlag | 0x10 | Decode, emit event or store as metadata |
| InitMarker | 0x13 | Decode, emit event or store as metadata |

---

## Cluster 6: Avatar OWN_CLIENT Properties

**File:** `state/tracker.py`

Avatar OWN_CLIENT properties are only visible for the recording player. Currently only `privateVehicleState.ribbons` is extracted. Expose the rest:

| Property | Type | Description | Action |
|---|---|---|---|
| `privateVehicleState` | dict | Currently only `ribbons` key extracted | Expose remaining keys (weapon state, etc.) |
| `spottedEntities` | VISION type | List of detected enemies | Decode and expose — useful for "spotted by" indicators |
| `vehiclePosition` | VECTOR3 | Own ship position | Already have this from PlayerOrientation; verify consistency |
| `privateBattleLogicState` | complex | Own team's battle logic state | Decode and expose |
| `visibilityDistances` | VISIBILITY_DISTANCES | Detection range data | Decode and expose — useful for rendering detection circles |
| `attrs` | INT64 bitfield | Modifier/consumable state flags | Decode bit fields, expose as dict or named flags |
| `playerModeState` | PLAYER_MODE | Camera/control state | Decode and expose |
| `weatherParams` | WEATHER_LOGIC_PARAMS | Weather state | Currently stub parser — implement properly |
| `squadronWeatherParams` | WEATHER_LOGIC_PARAMS | Squadron weather | Same as above |

---

## Cluster 7: Property Value Decode Gaps

**From UNDECODED_AUDIT.md section 2:**

| Entity | Property | Count | Issue |
|---|---|---|---|
| Vehicle | `triggeredSkillsData` | ~584 | Variable-length blob, not decoded. Contains activated commander skill state changes. Decode (likely pickle) and expose as `SkillActivationEvent` or on `ShipState`. |

**From UNDECODED_AUDIT.md section 3 — Nested property routing gaps:**

| Entity | Property | Count | Issue |
|---|---|---|---|
| Vehicle | (unknown name) | ~1232 | Property index doesn't resolve for nested updates. Fix routing. |
| Vehicle | `state` | ~183 | Name resolves but leaf value not fully decoded. VEHICLE_STATE has sub-structures: `battery`, `buffs`, `vehicleVisualState`, `decals`, `atba`. Decode leaf values. |
| SmokeScreen | (unknown) | ~22 | Nested property routing not implemented for SmokeScreen. |

---

## Cluster 8: Noise Filtering

**From UNDECODED_AUDIT.md section 1.1:**

`onCheckGamePing` (7,724) and `onCheckCellPing` (7,554) account for ~15,000 RawEvents per replay (~52% of all RawEvents). These are per-tick latency pings with no gameplay value.

Filter these out before event creation to reduce noise. Either:
- Skip them in `EventStream.process()` (don't emit RawEvent for known noise methods)
- Or add a `noise` flag to RawEvent so consumers can filter

---

## Implementation Notes

- Each cluster can be a separate PR/commit
- Run `pytest` after each cluster to verify no regressions
- Run `ruff check src/` and `mypy src/` for lint/type checks
- The `.def` files and `alias.xml` are the source of truth for all type structures — read them before implementing decoders
- For pickle blobs: use `encoding='latin-1'` and the safe unpickler pattern from `roster.py`
- For construct-decoded method args: the args are already in `packet.method_args` as Container dicts — just read the fields
- Test with the replay file in the repo root (if available) or any `.wowsreplay` file with `wows-gamedata/data/scripts_entity/entity_defs`

## Priority Order

1. **Cluster 1** (PlayerInfo) — smallest, most impactful for renderer
2. **Cluster 5a** (BATTLE_RESULTS) — high-value single packet
3. **Cluster 2** (ShipState) — many fields, straightforward mapping
4. **Cluster 4** (entity method events) — largest cluster, do sub-clusters in order (4a→4g)
5. **Cluster 3** (BattleState) — small, easy
6. **Cluster 5b-d** (packet types) — medium effort
7. **Cluster 6** (Avatar OWN_CLIENT) — complex types, needs format analysis
8. **Cluster 7** (decode gaps) — hardest, needs debugging nested property routing
9. **Cluster 8** (noise filter) — trivial, do anytime
