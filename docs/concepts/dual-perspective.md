# Dual Perspective

World of Warships records one replay per client — each observer only
sees ships their team has spotted, sees smoke from their own side, and
tracks chat messages from their channel. Two replays from the **same
match** (one per team, or two players from the same team) captured
independently can be merged into a unified view where every ship from
both perspectives is visible at once.

This is what `wows_replay_parser.merge.merge_replays` does.

## Usage

```python
from wows_replay_parser import parse_replay
from wows_replay_parser.merge import merge_replays

a = parse_replay("team_red.wowsreplay", gamedata_path="...")
b = parse_replay("team_green.wowsreplay", gamedata_path="...")

merged = merge_replays(a, b)

state = merged.state_at(120.5)
print(len(state.ships))  # up to 24 for a full-lobby random battle
```

`merge_replays` validates that both replays share the same
`arenaUniqueId` (pulled from the `onArenaStateReceived` pickle) and
the same `map_name`; it raises `ValueError` otherwise.

## `MergedReplay` is a first-class `ReplaySource`

The returned object satisfies the same `ReplaySource` protocol that
`ParsedReplay` does, which means any downstream consumer (including
the reference minimap renderer) can treat it identically to a single
replay. All precomputed helpers — `first_seen`, `aim_yaw_timeline`,
`smoke_screen_lifetimes`, `consumable_activations`, etc. — are merged
across the two sources.

## Merge strategy

| Field | Rule |
|---|---|
| `ships` | Union by player-entity mapping; shared ships prefer the "owner" perspective (the replay whose team the ship belongs to). Tiebreak on a richness score. |
| `smoke_screens`, `weather_zones`, `buildings`, `aircraft`, `buff_zones` | Server-authoritative — union by raw entity id. Shared eids deduplicate via richness preference. |
| `battle.capture_points` | Union by `point_index`; prefer `is_enabled=True`, then later progress. |
| `battle` scalars (scores, timer, winner, drop_state) | `replay_a` is authoritative. |
| `camera_yaw_timeline` | `None` — a merged view has no single recording-player camera. |

## ID collision safety

Disjoint `replay_b` entity ids that don't appear in `replay_a` are
offset by `B_ID_OFFSET = 2**30` before entering the merged namespace.
This is a safety net; in practice WoWs entity ids are server-assigned
and collisions are vanishingly rare.

See the [API Reference](../api/merge.md) for the full class and
function documentation.
