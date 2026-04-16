# wows-replay-parser

A Python library for parsing World of Warships `.wowsreplay` files with
**dynamic schema loading**. No hardcoded packet formats — the binary
layout is derived at runtime from the game's entity definition files,
so new patches only require an updated gamedata checkout.

## At a glance

```python
from wows_replay_parser import parse_replay

replay = parse_replay(
    "battle.wowsreplay",
    gamedata_path="./wows-gamedata/data/scripts_entity/entity_defs",
)

print(replay.map_name, replay.game_version, f"{replay.duration:.0f}s")
for player in replay.players:
    print(player.name, player.ship_id, player.team_id)
```

## What's in the box

- **Every packet decoded** — 24 packet types, 261 Avatar + Vehicle method
  calls, full entity state history.
- **100+ typed events** covering combat, squadrons, consumables, chat,
  minimap vision, damage stats, ribbons, and more.
- **State queries** — `state_at(t)` / `iter_states(timestamps)` for any
  point during the match.
- **Dual perspective merging** — combine two replays of the same match
  into a unified view where all ships from both teams are visible.
- **Not tied to any consumer** — the library ships a renderer-facing
  `ReplaySource` protocol but is equally useful for stat tools, data
  exports, and batch analysis.

## Next steps

- [Getting Started](getting-started.md) — install, first parse, gamedata
  setup.
- [Parser Pipeline](concepts/parser-pipeline.md) — how raw bytes become
  typed state.
- [API Reference](api/parsed-replay.md) — `ParsedReplay` and friends.
