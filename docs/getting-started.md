# Getting Started

## Requirements

- Python 3.11 or newer.
- [uv](https://github.com/astral-sh/uv) (recommended) or pip.
- A World of Warships gamedata tree (see
  [Get gamedata](#get-gamedata) below).

## Install

From PyPI once it's published:

```bash
pip install wows-replay-parser            # library only
pip install "wows-replay-parser[cli]"     # with the `wowsreplay` CLI
```

From source:

```bash
git clone https://github.com/toalba/wows-replay-parser.git
cd wows-replay-parser
uv venv && source .venv/bin/activate
uv sync
```

## Get gamedata

The parser builds binary schemas at runtime from the game's entity
definition files (`.def` + `alias.xml`). These are proprietary game
assets, not redistributed.

!!! note "Public gamedata repo"
    A sanitised public `wows-gamedata` repository is in preparation.
    Until then, extract the relevant directories from your own World
    of Warships installation using
    [wowsunpack](https://github.com/landaire/wowsunpack) and point
    `gamedata_path` at `…/scripts_entity/entity_defs`.

The canonical layout the parser expects:

```
wows-gamedata/
└── data/
    ├── scripts_entity/
    │   ├── entity_defs/
    │   │   ├── *.def
    │   │   ├── alias.xml
    │   │   └── interfaces/
    │   └── entities.xml
    └── scripts_decrypted/
        └── extracted_constants.json
```

## First parse

```python
from wows_replay_parser import parse_replay

replay = parse_replay(
    "battle.wowsreplay",
    gamedata_path="./wows-gamedata/data/scripts_entity/entity_defs",
)

print(f"Map: {replay.map_name}")
print(f"Version: {replay.game_version}")
print(f"Duration: {replay.duration:.0f}s")
print(f"Players: {len(replay.players)}")

# Query state at the 3-minute mark
state = replay.state_at(180.0)
print(f"Ships alive at 3:00: {sum(1 for s in state.ships.values() if s.is_alive)}")

# Iterate events
from wows_replay_parser.events.models import DeathEvent
for event in replay.events_of_type(DeathEvent):
    print(f"{event.timestamp:.1f}s: {event.victim_id} killed by {event.killer_id}")
```

## CLI

```bash
wowsreplay info battle.wowsreplay --gamedata ./wows-gamedata/data/scripts_entity/entity_defs
wowsreplay events battle.wowsreplay --gamedata ...
wowsreplay export battle.wowsreplay --gamedata ... -o replay.json
```

## Next

- [Parser Pipeline](concepts/parser-pipeline.md) for the data flow.
- [API Reference](api/parsed-replay.md) for the full public surface.
