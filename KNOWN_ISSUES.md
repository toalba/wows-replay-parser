# Known Issues

## Architecture

### A-1: O(n) timestamp list rebuild per bisect lookup

`camera_at()`, `net_stats_at()`, and `position_at()` rebuild a temporary
timestamp list from the full timeline on every call. With ~10k entries per
timeline, this costs ~0.2ms per call — fine for one-shot queries but adds
~5s overhead when called per-frame for a full replay render (30fps x 780s).

**Files:** `state/tracker.py` — `camera_at`, `net_stats_at`, `position_at`

**Fix:** Split storage into parallel `_timestamps` + `_values` lists so
bisect can operate directly on the pre-built timestamp list.

---

### A-2: Triple state rebuild for OWN_CLIENT queries at same timestamp

`own_player_vehicle_state(t)`, `spotted_entities_at(t)`, and
`visibility_distances_at(t)` each independently call `_rebuild_state_at(t)`.
If a caller queries all three at the same `t`, three full state rebuilds occur.

**Files:** `state/tracker.py` — `_avatar_props_at`

**Fix:** Add a combined `avatar_data_at(t) -> dict | None` method that
returns all Avatar props in one rebuild, letting callers extract what they need.

---

### ~~A-4: Duplicate ShipState constructors~~ FIXED

`iter_states()` now calls `_build_ship_state()` with cached position data
(`cached_pos`, `cached_yaw`, `cached_mm` keyword args) instead of duplicating
the constructor inline. O(delta) cursor optimization preserved.

---

## Minor

### M-1: Raw speed units in ShipState

`ShipState.speed` (from `serverSpeedRaw`) and `ShipState.max_speed` (from
`maxServerSpeedRaw`) store the game's internal fixed-point integer, not
human-readable knots. Field names suggest readable values.

**Fix:** Rename to `speed_raw` / `max_speed_raw`, or document the unit
and add a conversion helper.

---

### M-2: SubSurfacingEvent.time may truncate

`SubSurfacingEvent.time` is typed `int` but `syncSurfacingTime` may send
a float (seconds). Needs verification against Vehicle.def.

---

### M-3: Wire ribbon_id remapping in some game modes

In a subset of replays (observed in one CB replay on AngelWings) the
wire emits `ribbon_id=10` at positions where BattleResults'
`tail[481 + ribbon_id]` lists the count under `MAIN_CALIBER_PENETRATION`
(slot `481+15`). Our `recording_player_ribbons()` therefore labels 108
events as `BASE_CAPTURE` while
`battle_results().own_result.ribbon_counts()` reports
BASE_CAPTURE=0 / MAIN_CALIBER_PENETRATION=108.

Root cause unconfirmed. Possibilities:
- Per-match Ribbon enum remapping driven by `battle_type` / `game_mode`.
- Schema drift in `RIBBON_STATE` for specific game modes (e.g. an extra
  field shifts our INT8 read).

**Current recommendation:** trust
`replay.battle_results().own_result.ribbon_counts()` for lifetime totals
(reads `tail[481 + ribbon_id]`); treat
`recording_player_ribbons()` labels as best-effort and cross-check
against BR when counts look unusual.

**Files:** `ribbons.py` — `RIBBON_WIRE_IDS`, `extract_recording_player_ribbons`.

**Fix:** Dump raw bytes of the affected `privateVehicleState.ribbons`
nested updates and manually decode to determine whether it's a schema
or a remapping issue.

---

## Nested Property Decode (98.7%)

48 of 3,677 nested property packets remain unresolved. All are
`Vehicle.state.atba.atbaTargets` SetElement operations where the server's
array shrank (AA targets left detection range) but the tracker still holds
the old larger length. Downward speculative decode was attempted but produces
silent data corruption (fewer index bits cause value bit-shift), so these
are left unresolved. The data is cosmetic (secondary battery target IDs).
