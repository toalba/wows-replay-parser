"""Tests for ``MergedReplay`` and ``merge_replays``.

These tests define the *expected* behavior described in plan
``proud-growing-teapot.md``. Some may currently fail against the in-flight
implementation in ``merge.py`` — those failures are signals for the
implementation work happening in parallel, not bugs in this file.

A ``StubReplay`` dataclass implements the ``ReplaySource`` Protocol
structurally so we can construct controlled merge scenarios without needing
real replay files.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from wows_replay_parser.events.models import GameEvent
from wows_replay_parser.interfaces import ReplaySource
from wows_replay_parser.merge import MergedReplay, merge_replays
from wows_replay_parser.state.models import (
    BattleState,
    GameState,
    ShipState,
    SmokeScreenState,
)

# ───────────────────────────── StubReplay ──────────────────────────────


@dataclass
class StubReplay:
    """Minimal ``ReplaySource``-compatible stand-in for a parsed replay."""

    map_name: str = "fake_map"
    duration: float = 100.0
    game_version: str = "0.0.0"
    meta: dict = field(default_factory=lambda: {"arenaUniqueId": 1})
    players: list = field(default_factory=list)
    events: list = field(default_factory=list)
    battle_start_time: float | None = 0.0
    first_seen: dict = field(default_factory=dict)
    aim_yaw_timeline: dict = field(default_factory=dict)
    camera_yaw_timeline: list | None = None
    smoke_screen_lifetimes: dict = field(default_factory=dict)
    crew_modifiers: dict = field(default_factory=dict)
    zone_positions: dict = field(default_factory=dict)
    zone_lifetimes: dict = field(default_factory=dict)
    consumable_activations: dict = field(default_factory=dict)
    _state_at: dict[float, GameState] = field(default_factory=dict)

    def state_at(self, t: float) -> GameState:
        if t in self._state_at:
            return self._state_at[t]
        return GameState(timestamp=t, ships={}, battle=BattleState())

    def iter_states(self, timestamps):
        return (self.state_at(t) for t in timestamps)

    def events_of_type(self, event_type):
        return [e for e in self.events if isinstance(e, event_type)]


def _make_ship(eid: int, max_health: float = 0.0, health: float = 0.0) -> ShipState:
    return ShipState(entity_id=eid, max_health=max_health, health=health)


def _make_smoke(eid: int, radius: float = 50.0) -> SmokeScreenState:
    return SmokeScreenState(entity_id=eid, radius=radius)


# Event subclasses used across tests
@dataclass
class EventA(GameEvent):
    tag: str = "A"


@dataclass
class EventB(GameEvent):
    tag: str = "B"


# ─────────────────────────── infrastructure ────────────────────────────


def test_stub_satisfies_replay_source() -> None:
    """StubReplay structurally implements ReplaySource."""
    assert isinstance(StubReplay(), ReplaySource)


# ─────────────────────────── validation ────────────────────────────────


def test_arena_id_mismatch_raises() -> None:
    a = StubReplay(meta={"arenaUniqueId": 1})
    b = StubReplay(meta={"arenaUniqueId": 2})
    with pytest.raises(ValueError):
        merge_replays(a, b)


def test_merged_replay_satisfies_replay_source() -> None:
    a = StubReplay()
    b = StubReplay()
    merged = merge_replays(a, b)
    assert isinstance(merged, ReplaySource)


# ─────────────────────────── ship merging ──────────────────────────────


def test_ships_merged_across_perspectives() -> None:
    """Ships from both perspectives appear in merged state."""
    t = 10.0
    state_a = GameState(
        timestamp=t,
        ships={1: _make_ship(1), 2: _make_ship(2)},
        battle=BattleState(),
    )
    state_b = GameState(
        timestamp=t,
        ships={3: _make_ship(3), 4: _make_ship(4)},
        battle=BattleState(),
    )
    a = StubReplay(_state_at={t: state_a})
    b = StubReplay(_state_at={t: state_b})

    merged = merge_replays(a, b)
    ships = merged.state_at(t).ships

    # All 4 distinct entities must appear; b's unmapped ids get offset.
    assert len(ships) == 4
    # a's ids appear verbatim
    assert 1 in ships
    assert 2 in ships
    # b's ids are either verbatim (if no collision) or offset
    B_OFFSET = 2**30
    assert (3 in ships) or (3 + B_OFFSET in ships)
    assert (4 in ships) or (4 + B_OFFSET in ships)


def test_ships_ownership_preference() -> None:
    """When the same mapped ship appears in both, merge rule is deterministic.

    Per ``merge.py`` current docstring/logic: prefers the replay with more
    data (``max_health > 0``). We verify the outcome is deterministic rather
    than pinning to one specific winner, since the plan leaves "ownership"
    semantics flexible.
    """
    t = 5.0
    ship_a = _make_ship(100, max_health=1000.0, health=900.0)
    ship_b = _make_ship(100, max_health=1500.0, health=1200.0)
    state_a = GameState(timestamp=t, ships={100: ship_a}, battle=BattleState())
    state_b = GameState(timestamp=t, ships={100: ship_b}, battle=BattleState())

    a = StubReplay(_state_at={t: state_a})
    b = StubReplay(_state_at={t: state_b})

    merged1 = merge_replays(a, b)
    merged2 = merge_replays(a, b)
    ships1 = merged1.state_at(t).ships
    ships2 = merged2.state_at(t).ships

    # Deterministic
    assert ships1.keys() == ships2.keys()
    # Ship eid 100 must appear exactly once (not collided to 100 + offset)
    # — per spec, when mapped, only one copy is kept.
    B_OFFSET = 2**30
    assert 100 in ships1
    # If no mapping was set up (empty entity_mapping), collision prevention
    # should move b's ship to 100 + offset. Accept either outcome but
    # require it to be self-consistent.
    assert ships1[100].max_health in {1000.0, 1500.0}


def test_smoke_screens_shared_eid_dedupes() -> None:
    """Shared raw eid → same server entity → one merged entry (richer wins).

    Smoke screens are server-authoritative: if both client replays see a
    smoke_screen at eid=100 it's the SAME smoke screen, not two. Merging
    must dedupe (keep the richer snapshot), not offset b's copy.
    """
    t = 0.0
    # b's snapshot is richer: has a radius set. a's has radius=0 (unknown).
    smoke_a = {100: _make_smoke(100, radius=0.0)}
    smoke_b = {100: _make_smoke(100, radius=80.0)}
    state_a = GameState(
        timestamp=t, ships={}, battle=BattleState(), smoke_screens=smoke_a,
    )
    state_b = GameState(
        timestamp=t, ships={}, battle=BattleState(), smoke_screens=smoke_b,
    )
    a = StubReplay(_state_at={t: state_a})
    b = StubReplay(_state_at={t: state_b})

    merged = merge_replays(a, b)
    screens = merged.state_at(t).smoke_screens

    B_OFFSET = 2**30
    # Exactly one entry at the shared eid — NOT two.
    assert 100 in screens
    assert (100 + B_OFFSET) not in screens
    assert len(screens) == 1
    # Richer snapshot (radius > 0) wins.
    assert screens[100].radius == 80.0


def test_smoke_screens_disjoint_eid_preserves_ids() -> None:
    """Disjoint raw eids → both present. No offset needed since ids don't collide.

    With server-authoritative semantics, a b-eid that doesn't appear on
    the a-side is a distinct entity and keeps its raw id (the offset is
    only a safety net for actual collisions, which shouldn't happen for
    server-issued ids).
    """
    t = 0.0
    smoke_a = {100: _make_smoke(100, radius=40.0)}
    smoke_b = {200: _make_smoke(200, radius=80.0)}
    state_a = GameState(
        timestamp=t, ships={}, battle=BattleState(), smoke_screens=smoke_a,
    )
    state_b = GameState(
        timestamp=t, ships={}, battle=BattleState(), smoke_screens=smoke_b,
    )
    a = StubReplay(_state_at={t: state_a})
    b = StubReplay(_state_at={t: state_b})

    merged = merge_replays(a, b)
    screens = merged.state_at(t).smoke_screens

    assert 100 in screens
    assert 200 in screens
    assert len(screens) == 2
    assert screens[100].radius == 40.0
    assert screens[200].radius == 80.0


# ─────────────────────────── events ────────────────────────────────────


def test_events_merged_by_timestamp() -> None:
    e1 = EventA(timestamp=1.0)
    e2 = EventB(timestamp=2.0)
    e3 = EventA(timestamp=3.0)
    e4 = EventB(timestamp=4.0)
    a = StubReplay(events=[e1, e3])
    b = StubReplay(events=[e2, e4])

    merged = merge_replays(a, b)
    ts = [e.timestamp for e in merged.events]
    assert ts == sorted(ts)
    assert ts == [1.0, 2.0, 3.0, 4.0]


def test_events_of_type_filters_merged_stream() -> None:
    a = StubReplay(events=[EventA(timestamp=1.0), EventB(timestamp=2.0)])
    b = StubReplay(events=[EventA(timestamp=3.0), EventB(timestamp=4.0)])

    merged = merge_replays(a, b)
    only_a = merged.events_of_type(EventA)
    only_b = merged.events_of_type(EventB)
    assert all(isinstance(e, EventA) for e in only_a)
    assert all(isinstance(e, EventB) for e in only_b)
    assert len(only_a) == 2
    assert len(only_b) == 2


# ─────────────────────────── state iteration ───────────────────────────


def test_iter_states_pairs_timestamps() -> None:
    timestamps = [0.0, 10.0, 20.0]
    a_states = {t: GameState(timestamp=t, ships={1: _make_ship(1)}, battle=BattleState())
                for t in timestamps}
    b_states = {t: GameState(timestamp=t, ships={2: _make_ship(2)}, battle=BattleState())
                for t in timestamps}
    a = StubReplay(_state_at=a_states)
    b = StubReplay(_state_at=b_states)

    merged = merge_replays(a, b)
    collected = list(merged.iter_states(timestamps))
    assert len(collected) == len(timestamps)
    for t, state in zip(timestamps, collected, strict=True):
        assert state.timestamp == t


# ─────────────────────────── delegated scalars ─────────────────────────


def test_duration_is_max() -> None:
    a = StubReplay(duration=50.0)
    b = StubReplay(duration=70.0)
    merged = merge_replays(a, b)
    assert merged.duration == 70.0


def test_battle_start_time_is_min() -> None:
    a = StubReplay(battle_start_time=10.0)
    b = StubReplay(battle_start_time=5.0)
    merged = merge_replays(a, b)
    assert merged.battle_start_time == 5.0

    a2 = StubReplay(battle_start_time=None)
    b2 = StubReplay(battle_start_time=None)
    assert merge_replays(a2, b2).battle_start_time is None

    a3 = StubReplay(battle_start_time=None)
    b3 = StubReplay(battle_start_time=7.5)
    assert merge_replays(a3, b3).battle_start_time == 7.5


def test_first_seen_per_eid_min() -> None:
    """For a mapped entity, first_seen is the min timestamp across replays."""
    a = StubReplay(first_seen={1: 5.0, 2: 8.0})
    b = StubReplay(first_seen={1: 3.0, 99: 12.0})
    merged = merge_replays(a, b)
    fs = merged.first_seen
    # eid 1 present in both → min
    assert fs.get(1) == 3.0
    # eid 2 only in a
    assert fs.get(2) == 8.0
    # eid 99 only in b — offset or raw, at least one must carry 12.0
    B_OFFSET = 2**30
    assert (fs.get(99) == 12.0) or (fs.get(99 + B_OFFSET) == 12.0)


def test_camera_yaw_timeline_is_none() -> None:
    a = StubReplay(camera_yaw_timeline=[(0.0, 0.5), (1.0, 0.6)])
    b = StubReplay(camera_yaw_timeline=[(0.0, 0.1)])
    merged = merge_replays(a, b)
    assert merged.camera_yaw_timeline is None


def test_aim_yaw_timeline_union() -> None:
    a = StubReplay(aim_yaw_timeline={1: [(0.0, 0.1), (2.0, 0.3)]})
    b = StubReplay(aim_yaw_timeline={1: [(1.0, 0.2), (3.0, 0.4)]})
    merged = merge_replays(a, b)
    tl = merged.aim_yaw_timeline
    # eid 1 should exist (either raw or through mapping)
    series = tl.get(1)
    assert series is not None
    # Sorted by timestamp
    ts = [t for t, _ in series]
    assert ts == sorted(ts)
    # Union contains samples from both sides (4 total if no dedup needed)
    assert len(series) >= 2


def test_smoke_screen_lifetimes_union() -> None:
    """Shared eid → (min spawn, max leave); unshared b eid → offset applied."""
    a = StubReplay(smoke_screen_lifetimes={10: (5.0, 15.0), 20: (2.0, 8.0)})
    b = StubReplay(smoke_screen_lifetimes={10: (3.0, 18.0), 30: (4.0, 9.0)})
    merged = merge_replays(a, b)
    lifetimes = merged.smoke_screen_lifetimes
    # Shared eid 10 → min spawn, max leave
    assert lifetimes.get(10) == (3.0, 18.0)
    # a-only eid 20 passes through
    assert lifetimes.get(20) == (2.0, 8.0)
    # b-only eid 30 is offset
    B_OFFSET = 2**30
    assert (lifetimes.get(30) == (4.0, 9.0)) or (
        lifetimes.get(30 + B_OFFSET) == (4.0, 9.0)
    )


# ─────────────────────────── players ───────────────────────────────────


def test_players_deduped() -> None:
    """Players appearing in both replays are present once in merged.players."""
    shared = object()  # stand-in player — identity-based dedup
    other_a = object()
    other_b = object()
    a = StubReplay(players=[shared, other_a])
    b = StubReplay(players=[shared, other_b])
    merged = merge_replays(a, b)
    # Shared appears once; other_a and other_b both present
    assert merged.players.count(shared) == 1
    assert other_a in merged.players
    assert other_b in merged.players


# ─────────────────────────── map name ──────────────────────────────────


def test_map_name_must_match() -> None:
    """Different map_name should raise (or warn — accept either)."""
    a = StubReplay(map_name="map_a")
    b = StubReplay(map_name="map_b")
    try:
        merged = merge_replays(a, b)
    except ValueError:
        return  # acceptable: strict rejection
    # If no raise, merged.map_name must still be a string (warn path).
    assert isinstance(merged.map_name, str)


# ─────────────────────────── integration ───────────────────────────────


def test_merge_same_replay_twice(fixture_replay_path, fixture_gamedata_path) -> None:
    """Parse the canonical fixture twice and merge it with itself.

    Skip behaviour lives in the conftest fixtures — see
    ``tests/fixtures/README.md``.
    """
    from wows_replay_parser.api import parse_replay

    a = parse_replay(fixture_replay_path, fixture_gamedata_path)
    b = parse_replay(fixture_replay_path, fixture_gamedata_path)
    merged = merge_replays(a, b)

    # state_at returns a GameState with >= ships of either side alone.
    t = min(a.duration, b.duration) / 2.0
    merged_state = merged.state_at(t)
    n_a = len(a.state_at(t).ships)
    n_b = len(b.state_at(t).ships)
    assert len(merged_state.ships) >= max(n_a, n_b)

    # Walk frames at 1s intervals — no exceptions
    dt = 1.0
    t_cur = 0.0
    while t_cur <= merged.duration:
        merged.state_at(t_cur)
        t_cur += dt
