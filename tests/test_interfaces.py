"""Tests for the ``ReplaySource`` Protocol and ``ParsedReplay`` helpers.

Replay and gamedata paths are resolved by the shared conftest fixtures
(``parsed_replay`` is an alias for ``parsed_fixture`` — see
``tests/conftest.py``).
"""

from __future__ import annotations

from wows_replay_parser.interfaces import ReplaySource


def test_parsed_replay_is_replay_source(parsed_replay) -> None:
    """ParsedReplay must structurally satisfy the ReplaySource Protocol."""
    assert isinstance(parsed_replay, ReplaySource)


def test_battle_start_time(parsed_replay) -> None:
    val = parsed_replay.battle_start_time
    # May legitimately be None if the replay never emitted a battleStage=0
    # change, but for the canonical fixture we expect a positive float.
    assert val is None or (isinstance(val, float) and val >= 0.0)


def test_first_seen_non_empty(parsed_replay) -> None:
    fs = parsed_replay.first_seen
    assert isinstance(fs, dict)
    assert len(fs) > 0
    # All values should be finite floats.
    for eid, t in fs.items():
        assert isinstance(eid, int)
        assert isinstance(t, float)
        assert t >= 0.0


def test_aim_yaw_timeline_shape(parsed_replay) -> None:
    timelines = parsed_replay.aim_yaw_timeline
    assert isinstance(timelines, dict)
    # Most replays have at least one vehicle updating targetLocalPos.
    assert len(timelines) > 0
    for eid, series in timelines.items():
        assert isinstance(eid, int)
        assert isinstance(series, list)
        # Sorted ascending by t
        ts = [t for t, _ in series]
        assert ts == sorted(ts)
        for _, yaw in series:
            assert -3.1416 <= yaw <= 3.1416


def test_camera_yaw_timeline(parsed_replay) -> None:
    timeline = parsed_replay.camera_yaw_timeline
    # Recording-player replays have CAMERA packets; if not, spec allows None.
    assert timeline is None or isinstance(timeline, list)
    if timeline:
        ts = [t for t, _ in timeline]
        assert ts == sorted(ts)


def test_smoke_screen_lifetimes(parsed_replay) -> None:
    lifetimes = parsed_replay.smoke_screen_lifetimes
    assert isinstance(lifetimes, dict)
    for eid, (spawn_t, leave_t) in lifetimes.items():
        assert isinstance(eid, int)
        assert 0.0 <= spawn_t <= leave_t <= parsed_replay.duration + 1e-6


def test_crew_modifiers(parsed_replay) -> None:
    crew = parsed_replay.crew_modifiers
    assert isinstance(crew, dict)
    # Every key must be a known Vehicle entity_id.
    vehicle_ids = set(parsed_replay.tracker.get_vehicle_entity_ids())
    for eid in crew:
        assert eid in vehicle_ids


def test_zone_positions(parsed_replay) -> None:
    zp = parsed_replay.zone_positions
    assert isinstance(zp, dict)
    assert len(zp) > 0
    for eid, samples in zp.items():
        assert isinstance(eid, int)
        assert isinstance(samples, list)
        assert len(samples) > 0
        for entry in samples:
            assert len(entry) == 3
            t, x, z = entry
            assert isinstance(t, float)
            assert isinstance(x, float)
            assert isinstance(z, float)
            # No silent (0, 0) seed samples: an entity with only
            # zero-coord samples should have been skipped entirely.
            assert x != 0.0 or z != 0.0


def test_zone_lifetimes(parsed_replay) -> None:
    zl = parsed_replay.zone_lifetimes
    assert isinstance(zl, dict)
    assert len(zl) > 0
    for eid, (spawn_t, leave_t) in zl.items():
        assert isinstance(eid, int)
        assert 0.0 <= spawn_t <= leave_t <= parsed_replay.duration + 1e-6


def test_consumable_activations(parsed_replay) -> None:
    ca = parsed_replay.consumable_activations
    assert isinstance(ca, dict)
    assert len(ca) > 0
    vehicle_ids = set(parsed_replay.tracker.get_vehicle_entity_ids())
    for eid, acts in ca.items():
        assert eid in vehicle_ids
        assert isinstance(acts, list)
        for entry in acts:
            assert len(entry) == 3
            t, cons_id, duration = entry
            assert isinstance(t, float)
            assert isinstance(cons_id, int)
            assert isinstance(duration, float)


def test_helpers_are_cached(parsed_replay) -> None:
    """Cached properties should return the same object on repeat access."""
    assert parsed_replay.first_seen is parsed_replay.first_seen
    assert parsed_replay.aim_yaw_timeline is parsed_replay.aim_yaw_timeline
    assert parsed_replay.smoke_screen_lifetimes is parsed_replay.smoke_screen_lifetimes
    assert parsed_replay.zone_positions is parsed_replay.zone_positions
    assert parsed_replay.zone_lifetimes is parsed_replay.zone_lifetimes
    assert parsed_replay.consumable_activations is parsed_replay.consumable_activations
    assert parsed_replay.crew_modifiers is parsed_replay.crew_modifiers
