"""Unit tests for recording-player ribbon extraction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from wows_replay_parser.events.models import RibbonEvent
from wows_replay_parser.ribbons import (
    RIBBON_LIFE_TIME_SEC,
    coalesce_ribbon_popups,
    extract_recording_player_ribbons,
)


@dataclass
class _FakeChange:
    entity_id: int
    property_name: str
    new_value: Any
    timestamp: float = 0.0


class TestExtractRecordingPlayerRibbons:
    def test_one_event_per_wire_update(self) -> None:
        # Wire sends two updates: one per privateVehicleState snapshot.
        # Client's ``gRibbon.fire`` is called once per update, so we emit
        # one RibbonEvent per positive-delta snapshot. The ``count`` field
        # carries the delta (popup's x N badge).
        history = [
            _FakeChange(
                entity_id=1, property_name="privateVehicleState",
                new_value={"ribbons": [{"ribbonId": 5, "count": 1}]},
                timestamp=1.0,
            ),
            _FakeChange(
                entity_id=1, property_name="privateVehicleState",
                new_value={"ribbons": [{"ribbonId": 5, "count": 3}]},
                timestamp=2.0,
            ),
        ]
        events = extract_recording_player_ribbons(history, avatar_entity_id=1)
        assert len(events) == 2  # one event per wire update
        assert events[0].ribbon_id == 5
        assert events[0].ribbon_name == "FRAG"
        assert events[0].count == 1   # 0 -> 1
        assert events[0].timestamp == 1.0
        assert events[1].count == 2   # 1 -> 3 (delta = 2)
        assert events[1].timestamp == 2.0

    def test_ignores_count_resets(self) -> None:
        # When counter resets (target dies), no event fires. When it
        # rebuilds, each positive delta emits a new event.
        history = [
            _FakeChange(
                entity_id=1, property_name="privateVehicleState",
                new_value={"ribbons": [{"ribbonId": 6, "count": 5}]},
                timestamp=1.0,
            ),
            _FakeChange(
                entity_id=1, property_name="privateVehicleState",
                new_value={"ribbons": [{"ribbonId": 6, "count": 1}]},
                timestamp=2.0,  # reset — target died
            ),
            _FakeChange(
                entity_id=1, property_name="privateVehicleState",
                new_value={"ribbons": [{"ribbonId": 6, "count": 2}]},
                timestamp=3.0,
            ),
        ]
        events = extract_recording_player_ribbons(history, avatar_entity_id=1)
        # t=1.0 emits 1 event (0→5 delta=5), t=2.0 silent (reset), t=3.0 emits 1 (1→2)
        assert len(events) == 2
        assert events[0].count == 5
        assert events[1].count == 1

    def test_ignores_other_entities(self) -> None:
        history = [
            _FakeChange(
                entity_id=2, property_name="privateVehicleState",
                new_value={"ribbons": [{"ribbonId": 5, "count": 99}]},
            ),
        ]
        assert extract_recording_player_ribbons(history, avatar_entity_id=1) == []

    def test_ignores_ribbon_id_leaf_set_burst(self) -> None:
        # M-3: in some replays the server rewrites slot 0's ribbonId
        # through a burst of values at match start. The slot's true
        # ribbonId is the one it was *created* with — subsequent
        # ribbonId changes on the same slot must not produce ghost
        # events, and later count increments must attribute to the
        # original ribbonId (not the last one rewritten in).
        history = [
            # SLICE insert: slot 0 created with ribbonId=15 (PEN), count=1
            _FakeChange(
                entity_id=1, property_name="privateVehicleState",
                new_value={"ribbons": [{"ribbonId": 15, "count": 1}]},
                timestamp=1.0,
            ),
            # Server init burst: slot 0's ribbonId flipped with count held
            _FakeChange(
                entity_id=1, property_name="privateVehicleState",
                new_value={"ribbons": [{"ribbonId": 2, "count": 1}]},
                timestamp=1.1,
            ),
            _FakeChange(
                entity_id=1, property_name="privateVehicleState",
                new_value={"ribbons": [{"ribbonId": 10, "count": 1}]},
                timestamp=1.2,
            ),
            # Real count increments on slot 0 (still "id=10" on wire)
            _FakeChange(
                entity_id=1, property_name="privateVehicleState",
                new_value={"ribbons": [{"ribbonId": 10, "count": 5}]},
                timestamp=2.0,
            ),
        ]
        events = extract_recording_player_ribbons(history, avatar_entity_id=1)
        # Expected: 2 events, both attributed to the authored ribbonId=15,
        # no ghost BOMB (2) or BASE_CAPTURE (10) events from the flip burst.
        assert len(events) == 2
        assert all(e.ribbon_id == 15 for e in events)
        assert all(e.ribbon_name == "MAIN_CALIBER_PENETRATION" for e in events)
        assert events[0].count == 1   # initial
        assert events[1].count == 4   # 1 -> 5 on slot 0
        total = sum(e.count for e in events)
        assert total == 5  # matches the final slot-0 count


def _ev(ts: float, rid: int, name: str = "BURN", count: int = 1) -> RibbonEvent:
    return RibbonEvent(
        timestamp=ts, entity_id=1, ribbon_id=rid,
        ribbon_name=name, count=count, vehicle_id=1, target_id=0,
    )


class TestCoalesceRibbonPopups:
    def test_empty(self) -> None:
        assert coalesce_ribbon_popups([]) == []

    def test_single(self) -> None:
        events = [_ev(1.0, 6)]
        out = coalesce_ribbon_popups(events)
        assert len(out) == 1
        assert out[0].timestamp == 1.0
        assert out[0].count == 1

    def test_rapid_same_id_merges(self) -> None:
        # Three BURN events within the 6s window — merge into ONE popup,
        # count accumulates.
        events = [_ev(1.0, 6), _ev(3.0, 6), _ev(5.0, 6)]
        out = coalesce_ribbon_popups(events)
        assert len(out) == 1
        assert out[0].timestamp == 1.0   # first fire timestamp
        assert out[0].count == 3         # accumulated

    def test_gap_creates_new_popup(self) -> None:
        # First popup fires at t=1, second fires at t=10 — that's 9s later,
        # past the 6s window. Should produce TWO popups.
        events = [_ev(1.0, 6), _ev(10.0, 6)]
        out = coalesce_ribbon_popups(events)
        assert len(out) == 2
        assert out[0].count == 1
        assert out[1].count == 1

    def test_refreshing_extends_popup(self) -> None:
        # Client's __updateTempEntity resets lastUpdate on each fire.
        # Fires at 0, 5, 10, 15 — each within 6s of the previous.
        # Should merge into one popup (popup keeps getting refreshed).
        events = [_ev(0.0, 6), _ev(5.0, 6), _ev(10.0, 6), _ev(15.0, 6)]
        out = coalesce_ribbon_popups(events)
        assert len(out) == 1
        assert out[0].count == 4

    def test_different_ids_dont_merge(self) -> None:
        # BURN and CITADEL at the same tick are two separate popups.
        events = [_ev(1.0, 6, "BURN"), _ev(1.0, 8, "CITADEL")]
        out = coalesce_ribbon_popups(events)
        assert len(out) == 2
        assert {e.ribbon_id for e in out} == {6, 8}

    def test_custom_window(self) -> None:
        # Override the window to a shorter value.
        events = [_ev(0.0, 6), _ev(2.0, 6)]
        out = coalesce_ribbon_popups(events, window_sec=1.0)
        assert len(out) == 2  # 2s gap > 1s window

    def test_life_time_constant(self) -> None:
        # Sanity check: client constant is 6.0s per decoded bytecode.
        assert RIBBON_LIFE_TIME_SEC == 6.0
