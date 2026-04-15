"""Unit tests for ribbon extraction / derivation.

Regression coverage for the `RIBBON_NAMES` inversion bug where the
reverse-mapped dict was {name: id} and every name lookup in
`derive_ribbons()` silently fell through to the "Unknown" default.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from wows_replay_parser.events.models import (
    DamageEvent,
    DeathEvent,
    ShotDestroyedEvent,
)
from wows_replay_parser.ribbons import (
    RIBBON_NAMES,
    RIBBON_WIRE_IDS,
    derive_ribbons,
    extract_recording_player_ribbons,
)


class TestRibbonNamesMap:
    def test_ribbon_names_is_id_to_name(self) -> None:
        # RIBBON_NAMES must be {int_id: str_name}, NOT the inverted form.
        assert RIBBON_NAMES[0] == "MAIN_CALIBER"
        assert RIBBON_NAMES[5] == "FRAG"
        assert RIBBON_NAMES[8] == "CITADEL"
        assert RIBBON_NAMES[54] == "ASSIST"

    def test_ribbon_names_matches_wire_ids(self) -> None:
        assert RIBBON_NAMES == RIBBON_WIRE_IDS

    def test_int_get_returns_string(self) -> None:
        # The derive_ribbons callsite pattern.
        val = RIBBON_NAMES.get(5, "Unknown")
        assert val == "FRAG"
        assert isinstance(val, str)


class TestDeriveRibbons:
    def test_penetration_from_shot_destroyed(self) -> None:
        events = [
            ShotDestroyedEvent(
                timestamp=1.0, entity_id=100,
                owner_id=100, hit_type=1, shot_id=42,
            ),
        ]
        ribbons = derive_ribbons(events)
        assert len(ribbons) == 1
        assert ribbons[0].ribbon_id == 15  # PENETRATION
        assert ribbons[0].ribbon_name == "MAIN_CALIBER_PENETRATION"

    def test_citadel_from_shot_destroyed(self) -> None:
        events = [
            ShotDestroyedEvent(
                timestamp=2.0, entity_id=100,
                owner_id=100, hit_type=4,
            ),
        ]
        ribbons = derive_ribbons(events)
        assert len(ribbons) == 1
        assert ribbons[0].ribbon_id == 8
        assert ribbons[0].ribbon_name == "CITADEL"

    def test_kill_produces_frag(self) -> None:
        events = [
            DeathEvent(
                timestamp=5.0, entity_id=0,
                victim_id=200, killer_id=100,
            ),
        ]
        ribbons = derive_ribbons(events)
        assert len(ribbons) == 1
        assert ribbons[0].ribbon_id == 5  # FRAG
        assert ribbons[0].ribbon_name == "FRAG"
        assert ribbons[0].vehicle_id == 100
        assert ribbons[0].target_id == 200

    def test_kill_without_killer_skipped(self) -> None:
        events = [
            DeathEvent(timestamp=5.0, victim_id=200, killer_id=0),
        ]
        assert derive_ribbons(events) == []

    def test_fire_damage_produces_burn(self) -> None:
        events = [
            DamageEvent(
                timestamp=3.0, entity_id=100,
                target_id=200, attacker_id=300,
                damage=150.0, damage_type="fire",
            ),
        ]
        ribbons = derive_ribbons(events)
        assert len(ribbons) == 1
        assert ribbons[0].ribbon_id == 6  # BURN
        assert ribbons[0].ribbon_name == "BURN"

    def test_all_derived_ribbons_have_resolved_names(self) -> None:
        # Full suite of hit_types + damage_types + a kill. No ribbon name
        # may be the "Unknown" default (the regression symptom).
        events: list[Any] = [
            ShotDestroyedEvent(timestamp=1.0, owner_id=1, hit_type=1),
            ShotDestroyedEvent(timestamp=1.1, owner_id=1, hit_type=2),
            ShotDestroyedEvent(timestamp=1.2, owner_id=1, hit_type=3),
            ShotDestroyedEvent(timestamp=1.3, owner_id=1, hit_type=4),
            DamageEvent(timestamp=2.0, entity_id=1, damage_type="fire"),
            DamageEvent(timestamp=2.1, entity_id=1, damage_type="flooding"),
            DamageEvent(timestamp=2.2, entity_id=1, damage_type="torpedo"),
            DeathEvent(timestamp=3.0, victim_id=9, killer_id=1),
        ]
        ribbons = derive_ribbons(events)
        assert len(ribbons) == 8
        for r in ribbons:
            assert r.ribbon_name != "Unknown"
            assert r.ribbon_name != ""


@dataclass
class _FakeChange:
    entity_id: int
    property_name: str
    new_value: Any
    timestamp: float = 0.0


class TestExtractRecordingPlayerRibbons:
    def test_diffs_cumulative_counts(self) -> None:
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
        assert len(events) == 3  # 1 + delta(2)
        assert all(e.ribbon_id == 5 for e in events)
        assert all(e.ribbon_name == "FRAG" for e in events)

    def test_ignores_other_entities(self) -> None:
        history = [
            _FakeChange(
                entity_id=2, property_name="privateVehicleState",
                new_value={"ribbons": [{"ribbonId": 5, "count": 99}]},
            ),
        ]
        assert extract_recording_player_ribbons(history, avatar_entity_id=1) == []

    def test_agrees_with_derive_on_shared_cases(self) -> None:
        # Both paths should produce the same ribbon_name for a FRAG.
        derived = derive_ribbons([
            DeathEvent(timestamp=5.0, victim_id=200, killer_id=100),
        ])
        extracted = extract_recording_player_ribbons([
            _FakeChange(
                entity_id=100, property_name="privateVehicleState",
                new_value={"ribbons": [{"ribbonId": 5, "count": 1}]},
                timestamp=5.0,
            ),
        ], avatar_entity_id=100)
        assert len(derived) == 1
        assert len(extracted) == 1
        assert derived[0].ribbon_name == extracted[0].ribbon_name == "FRAG"
        assert derived[0].ribbon_id == extracted[0].ribbon_id == 5
