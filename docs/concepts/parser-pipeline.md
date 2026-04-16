# Parser Pipeline

The parser turns `.wowsreplay` bytes into typed state in roughly ten
steps. Understanding the pipeline helps when you're tracking down a
decode bug or extending the event stream.

## High-level flow

```
wows-gamedata repo
   │
   ▼
AliasRegistry.from_file()      ← resolves type aliases
   │
   ▼
DefLoader.load_all()           ← parses .def XML into EntityDef structs
   │                              (with interface merging)
   ▼
EntityRegistry                 ← indexes entities, methods, properties
   │                              (sorted by sort_size)
   ▼
SchemaBuilder                  ← builds `construct` binary parsers
   │                              on-the-fly
   ▼
replay.wowsreplay
   │
   ▼
ReplayReader.read()            ← JSON headers + Blowfish ECB + zlib
   │
   ▼
type_id_detector               ← auto-maps type indices to entity names
   │
   ▼
PacketDecoder.decode_stream()  ← uses schemas to decode packets,
   │                              feeds GameStateTracker
   ▼
EventStream.process()          ← packets → typed game events
   │
   ▼
ParsedReplay                   ← events, packets, state queries
```

## Source of truth

The `.def` files and `alias.xml` in the gamedata repo are the
**single source of truth** for every entity definition, property name,
field name, method signature, and type structure. If a bug report says
"property X has the wrong value", the investigation starts there.

File locations inside the gamedata tree:

- Entity definitions: `data/scripts_entity/entity_defs/*.def`
- Interface definitions: `data/scripts_entity/entity_defs/interfaces/*.def`
- Type aliases: `data/scripts_entity/entity_defs/alias.xml`
- Entity type ID mapping: `data/scripts_entity/entities.xml`

## Packet header

Every packet uses the same 12-byte header:

| Field | Type | Notes |
|---|---|---|
| `payload_size` | u32 LE | bytes that follow the header |
| `packet_type` | u32 LE | see `PacketType` enum |
| `clock` | f32 LE | game time in seconds |

The `clock` is the timestamp surfaced on every decoded event. Getting
the header wrong causes all timestamps to drift, so it's verified
against real replays at parse time.

## Entity state tracking

`GameStateTracker` maintains per-entity property history keyed by
timestamp. Two primary query APIs:

- `state_at(t)` — O(history) one-shot query. Useful for ad-hoc lookups.
- `iter_states(timestamps)` — O(Δ) incremental cursor. Use this in
  render loops so you don't re-scan history per frame.

Both return a `GameState` with `ships`, `smoke_screens`, `weather_zones`,
`buildings`, `aircraft`, `buff_zones`, `battle` (scores, capture points,
timer), and a timestamp.

## Event stream

`EventStream.process()` transforms decoded packets into 100+ typed
events (combat, squadron, consumable, chat, ribbon, etc.). Events are
ordered by timestamp. Filter with `replay.events_of_type(T)`.

See the [API Reference](../api/events.md) for the full event catalog.
