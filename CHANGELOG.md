# Changelog

All notable changes to `wows-replay-parser` are documented here.

## [Unreleased]

### Added
- **Gamedata auto-sync** — `sync_gamedata()` checks out the correct git tag matching the replay's game version
  - Falls back to closest version tag when exact tag is missing (smallest absolute build-ID delta)
  - SSH URL for gamedata repo clone
  - Dirty-repo detection: refuses checkout if tracked files have uncommitted changes
  - Increased git timeouts for cross-filesystem setups (WSL over `/mnt/c/`)
- **Airstrike params_id preservation** — `activateAirSupport` no longer overwrites the real `params_id`/`team_id` from `receive_addMinimapSquadron`
- **BattleResults decoder** (`battle_results.py`) — decodes the post-match 0x22 packet into a typed `BattleResults` with per-player stats, battle metadata, and own-player private economics
  - 466-field `CLIENT_PUBLIC_RESULTS` schema (PLAYER_INFO 20 + VEH_BASE_RESULTS 446) extracted via Stage-1..4 decompilation of obfuscated `scripts/m0b4b170b.pyc` (aka `BattleResultsShared`) on build 12267945
  - `PlayerBattleResult.stat(name)` named-field lookup + `.raw` / `.extra` for unmapped tail slots
  - `PlayerBattleResult.ribbon_count(ribbon_id)` / `.ribbon_counts()` read the authoritative end-of-match ribbon tallies from `raw[481 + ribbon_id]` — the server's `incomeRibbon.count` post-popup-expiry
- **Ribbon popup coalescing** — `replay.recording_player_ribbon_popups()` merges same-type ribbon events within the client's `LIFE_TIME=6.0s` window to match on-screen popups, reverse-engineered from `RibbonSystem.__updateTempEntity` in `scripts/m102f8b9c/RibbonSystem.pyc`
- **`RibbonEvent.count`** field — delta for the wire update (popup `x N` badge)
- **Three new ribbon IDs** — 57 `WAVE`, 58 `TORPEDO_PHOTON`, 59 `SHIELD`

### Changed
- **Ribbon extraction semantics** — `recording_player_ribbons()` now emits **one RibbonEvent per server wire update** (matching `Avatar.gRibbon.fire()` invocations) instead of `delta` events per snapshot, fixing over-count on replays with counter resets
- **Ribbon wire-id names** corrected: 39-41 renamed `ACOUSTIC_HIT_*` → `ACOUSTIC_HIT_VEHICLE_*`; 55 renamed `MISSILE_HIT` → `MISSILE`

### Removed
- **`derive_ribbons()`** — the hit-event-inferred ribbon path is removed; ribbons are now exclusively server-authoritative from `privateVehicleState.ribbons`. Also removed the vestigial `RibbonEvent.derived` flag, `RIBBON_DISPLAY_NAMES` dict, and per-id convenience constants (`RIBBON_MAIN_CALIBER`, etc.) that only existed to serve the deleted function.

## [0.1.0] — 2026-04-02

### Added
- **Full replay parsing** — parse `.wowsreplay` files with complete state tracking (positions, properties, events)
- **State query API** — `state_at(t)` for random access, `iter_states()` for O(delta) sequential access (24x faster)
- **100% method decode** — deterministic method ID resolution from `.def` files via sort_size stable sort with depth-first interface merge order
- **Auto-detect method IDs** — runtime refinement by observing packet payloads (fixed-size matching, trial-parse, semantic validation, elimination)
- **Self-player tracking** — position via `PLAYER_ORIENTATION` packets, team detection from `ENTITY_CREATE` state data
- **27 packet types** decoded — all known BigWorld packet types including entity methods, property updates, position, nested properties
- **Nested property decoder** — handles deep updates, array slices, and speculative array-length decoding
- **65 event types** — damage, kills, ribbons, consumables, capture points, chat, vision, aircraft, scores, and more
- **37 model fields** exposed across PlayerInfo, ShipState, BattleState, DamageEvent, etc.
- **6 API methods** — `parse_replay()`, `state_at()`, `iter_states()`, `position_at()`, `events`, `packets`
- **Squadron and airstrike tracking** — CV squadrons (controllable) and airstrike planes in GameState
- **SmokeScreenState and BuildingState** — smoke puff positions and building entities tracked
- **Capture zone inline state** — hardened decoding of capture point progress from BattleLogic
- **DamageEvent fields** — `attacker_id` and `damage_type` populated from decoded BLOB args
- **Server-authoritative ribbon API** — recording player ribbon counts from `receiveDamageStat`
- **Auto-decode BLOBs** — all known `implementedBy` BLOBs and plain BLOB args decoded at parse time
- **SHIP_CONFIG binary decoder** — full ship loadout parsing (modules, consumables, skills, camos)
- **CLI export** — `wows-export` command for structured JSON output with optional state snapshots
- **Clan color extraction** — `clan_color` field from `onArenaStateReceived` into PlayerInfo
- **Consumable calc module** — `compute_effective_reloads()` for cooldown computation from GameParams
- **LearnedSkills decoding** — commander skill tree parsing with correct ship type index order
- **Gamedata disk cache** — schema caching and copy-on-write snapshots for performance
- **Blowfish optimization** — bulk ECB + struct XOR chain (9x faster decrypt)

### Fixed
- Team ID in PlayerInfo derived from relation field (not raw packet data)
- ShipState.team_id injected from roster into tracker + snapshots
- Only ships with position data included in `state_at()`/`iter_states()`
- Parser traps: MinimapVisionInfo, NonVolatilePosition, death position cache
- `iter_states()` no longer uses stale end-of-match state as starting point
- Container mutation no longer corrupts history; `position_at()` no longer returns future positions
- Nested property decoder handles array slices and missing properties correctly
- Airstrike team_id derived from own Vehicle, not Avatar
- ShipConfigParser wire format corrected
- `implementedBy` parser fixes for tracker compatibility
- Snapshot shallow-copy bug: deep-copy mutable property values
- 1-based entity type_idx mapping from entities.xml
- Fix `learnedSkills` ship type index order to alphabetical
- Stale test: `position_at()` returns None before first recorded position
