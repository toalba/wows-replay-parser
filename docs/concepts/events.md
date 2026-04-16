# Event Stream

The parser exposes the replay as two parallel views:

1. **State snapshots** — `replay.state_at(t)` returns a `GameState` with
   the current values of every tracked property (ship health, position,
   smoke positions, capture progress, …).
2. **Event stream** — `replay.events` is a time-ordered list of 100+
   typed events that captures *what happened* rather than *what's true
   now*.

Most consumers want both. Position a ship via `state_at()` for trails,
but detect kills and damage events by iterating `replay.events`.

## Filtering

The top-level helper is `replay.events_of_type(T)`:

```python
from wows_replay_parser.events.models import (
    DeathEvent,
    ShotCreatedEvent,
    DamageEvent,
    ChatEvent,
    MinimapVisionEvent,
)

kills = replay.events_of_type(DeathEvent)
shots = replay.events_of_type(ShotCreatedEvent)
chat  = replay.events_of_type(ChatEvent)
```

## Event categories

The catalogue splits roughly into:

- **Combat** — `ShotCreatedEvent`, `ShotDestroyedEvent`, `TorpedoCreatedEvent`,
  `DepthChargeEvent`, `ExplosionEvent`, `DamageEvent`, `DamageReceivedStatEvent`,
  `DeathEvent`, `MirrorDamageEvent`, `ScoutingDamageEvent`, `ShipCracksEvent`.
- **Squadrons** — 16 `Squadron*Event` variants covering spawn, movement,
  health, death, waypoints, visibility.
- **Consumables** — `ConsumableEvent`, `ConsumableEnabledEvent`,
  `ConsumablePausedEvent`, `ConsumableSelectedEvent`, `ConsumablesSetEvent`,
  `CooldownUpdateEvent`.
- **Vision / spotting** — `MinimapVisionEvent`, `HydrophoneTargetEvent`,
  `SonarDetectionEvent`, `SonarPingEvent`, and related acoustic events.
- **Game state** — `GameRoomStateEvent`, `BattleEndEvent`, `ScoreUpdateEvent`,
  `CapturePointUpdateEvent`, `CapContestEvent`, `WorldStateReceivedEvent`.
- **Communication** — `ChatEvent`, `ChatHistoryEvent`.
- **Submarines** — `SubSurfacingEvent`.
- **Missiles** — 5 `Missile*Event` variants.
- **Low-level** — `PropertyUpdateEvent`, `RawEvent` as a catch-all for
  anything the event factory didn't specialise.

See the generated API reference for field-level details.

## Raw access

If you need the underlying packet, every event's `raw_data` dict has
the decoded method arguments. For truly unknown packets the parser
never silently drops data — anything without a typed factory surfaces
as a `RawEvent` with the full payload attached.
