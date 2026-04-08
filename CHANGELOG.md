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
