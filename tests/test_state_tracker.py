"""Unit tests for the GameStateTracker."""

from __future__ import annotations

import pytest

from wows_replay_parser.packets.types import Packet, PacketType
from wows_replay_parser.state.tracker import GameStateTracker


def _make_packet(
    ptype: PacketType,
    entity_id: int = 0,
    timestamp: float = 0.0,
    entity_type: str | None = None,
    property_name: str | None = None,
    property_value: object = None,
    method_name: str | None = None,
    method_args: dict | None = None,
    position: tuple[float, float, float] | None = None,
    direction: tuple[float, float, float] | None = None,
) -> Packet:
    """Create a synthetic Packet for testing."""
    pkt = Packet(type=ptype)
    pkt.entity_id = entity_id
    pkt.timestamp = timestamp
    pkt.entity_type = entity_type
    pkt.property_name = property_name
    pkt.property_value = property_value
    pkt.method_name = method_name
    pkt.method_args = method_args
    pkt.position = position
    pkt.direction = direction
    return pkt


class TestProcessPacket:
    def test_entity_creation_registers_type(self) -> None:
        tracker = GameStateTracker()
        pkt = _make_packet(
            PacketType.ENTITY_CREATE,
            entity_id=100,
            entity_type="Vehicle",
            timestamp=1.0,
        )
        tracker.process_packet(pkt)
        assert tracker.get_entity_type(100) == "Vehicle"

    def test_property_update_stores_value(self) -> None:
        tracker = GameStateTracker()
        # Register entity first
        tracker.process_packet(_make_packet(
            PacketType.ENTITY_CREATE,
            entity_id=100, entity_type="Vehicle", timestamp=0.5,
        ))
        # Update property
        changes = tracker.process_packet(_make_packet(
            PacketType.ENTITY_PROPERTY,
            entity_id=100, entity_type="Vehicle",
            property_name="health", property_value=50000.0,
            timestamp=1.0,
        ))
        assert len(changes) == 1
        assert changes[0].property_name == "health"
        assert changes[0].new_value == 50000.0
        assert tracker.get_entity_props(100)["health"] == 50000.0

    def test_property_update_tracks_old_value(self) -> None:
        tracker = GameStateTracker()
        tracker.process_packet(_make_packet(
            PacketType.ENTITY_CREATE,
            entity_id=100, entity_type="Vehicle", timestamp=0.5,
        ))
        tracker.process_packet(_make_packet(
            PacketType.ENTITY_PROPERTY,
            entity_id=100, property_name="health",
            property_value=50000.0, timestamp=1.0,
        ))
        changes = tracker.process_packet(_make_packet(
            PacketType.ENTITY_PROPERTY,
            entity_id=100, property_name="health",
            property_value=40000.0, timestamp=2.0,
        ))
        assert changes[0].old_value == 50000.0
        assert changes[0].new_value == 40000.0

    def test_position_stored(self) -> None:
        tracker = GameStateTracker()
        tracker.process_packet(_make_packet(
            PacketType.POSITION,
            entity_id=100, timestamp=1.0,
            position=(100.0, 0.0, 200.0),
            direction=(1.0, 0.0, 0.0),
        ))
        pos = tracker.position_at(100, 1.0)
        assert pos is not None
        assert pos[0] == pytest.approx(100.0)
        assert pos[2] == pytest.approx(200.0)

    def test_death_from_receive_vehicle_death(self) -> None:
        tracker = GameStateTracker()
        tracker.process_packet(_make_packet(
            PacketType.ENTITY_CREATE,
            entity_id=200, entity_type="Vehicle", timestamp=0.5,
        ))
        changes = tracker.process_packet(_make_packet(
            PacketType.ENTITY_METHOD,
            entity_id=1, entity_type="Avatar",
            method_name="receiveVehicleDeath",
            method_args={"arg0": 200, "arg1": 300, "arg2": 1},
            timestamp=5.0,
        ))
        assert len(changes) == 1
        assert changes[0].property_name == "isAlive"
        assert changes[0].new_value is False
        assert tracker.get_entity_props(200)["isAlive"] is False

    def test_death_from_kill_method(self) -> None:
        tracker = GameStateTracker()
        tracker.process_packet(_make_packet(
            PacketType.ENTITY_CREATE,
            entity_id=300, entity_type="Vehicle", timestamp=0.5,
        ))
        changes = tracker.process_packet(_make_packet(
            PacketType.ENTITY_METHOD,
            entity_id=300, entity_type="Vehicle",
            method_name="kill",
            method_args={},
            timestamp=10.0,
        ))
        assert len(changes) == 1
        assert tracker.get_entity_props(300)["isAlive"] is False


class TestStateAt:
    def test_state_at_returns_correct_health(self) -> None:
        tracker = GameStateTracker()
        tracker.process_packet(_make_packet(
            PacketType.ENTITY_CREATE,
            entity_id=100, entity_type="Vehicle", timestamp=0.0,
        ))
        # Ship needs a position to be visible in state_at()
        tracker.process_packet(_make_packet(
            PacketType.POSITION,
            entity_id=100, timestamp=0.5,
            position=(0.0, 0.0, 0.0),
        ))
        tracker.process_packet(_make_packet(
            PacketType.ENTITY_PROPERTY,
            entity_id=100, entity_type="Vehicle",
            property_name="health", property_value=50000.0,
            timestamp=1.0,
        ))
        tracker.process_packet(_make_packet(
            PacketType.ENTITY_PROPERTY,
            entity_id=100, entity_type="Vehicle",
            property_name="maxHealth", property_value=50000.0,
            timestamp=1.0,
        ))
        tracker.process_packet(_make_packet(
            PacketType.ENTITY_PROPERTY,
            entity_id=100, entity_type="Vehicle",
            property_name="health", property_value=30000.0,
            timestamp=5.0,
        ))

        state = tracker.state_at(3.0)
        assert 100 in state.ships
        assert state.ships[100].health == 50000.0

        state_later = tracker.state_at(6.0)
        assert state_later.ships[100].health == 30000.0

    def test_state_at_empty(self) -> None:
        tracker = GameStateTracker()
        state = tracker.state_at(0.0)
        assert len(state.ships) == 0


class TestPositionInterpolation:
    def test_interpolation_between_two_points(self) -> None:
        tracker = GameStateTracker()
        tracker.process_packet(_make_packet(
            PacketType.POSITION,
            entity_id=100, timestamp=0.0,
            position=(0.0, 0.0, 0.0),
        ))
        tracker.process_packet(_make_packet(
            PacketType.POSITION,
            entity_id=100, timestamp=10.0,
            position=(100.0, 0.0, 100.0),
        ))
        pos = tracker.position_at(100, 5.0)
        assert pos is not None
        assert pos[0] == pytest.approx(50.0)
        assert pos[2] == pytest.approx(50.0)

    def test_position_before_first_returns_none(self) -> None:
        tracker = GameStateTracker()
        tracker.process_packet(_make_packet(
            PacketType.POSITION,
            entity_id=100, timestamp=5.0,
            position=(50.0, 0.0, 50.0),
        ))
        pos = tracker.position_at(100, 0.0)
        assert pos is None  # No position recorded yet at t=0

    def test_position_after_last_returns_last(self) -> None:
        tracker = GameStateTracker()
        tracker.process_packet(_make_packet(
            PacketType.POSITION,
            entity_id=100, timestamp=5.0,
            position=(50.0, 0.0, 50.0),
        ))
        pos = tracker.position_at(100, 999.0)
        assert pos is not None
        assert pos[0] == pytest.approx(50.0)

    def test_no_positions_returns_none(self) -> None:
        tracker = GameStateTracker()
        assert tracker.position_at(999, 0.0) is None


class TestPropertyHistory:
    def test_history_returns_all_changes(self) -> None:
        tracker = GameStateTracker()
        tracker.process_packet(_make_packet(
            PacketType.ENTITY_CREATE,
            entity_id=100, entity_type="Vehicle", timestamp=0.0,
        ))
        for i, val in enumerate([50000.0, 40000.0, 30000.0]):
            tracker.process_packet(_make_packet(
                PacketType.ENTITY_PROPERTY,
                entity_id=100,
                property_name="health",
                property_value=val,
                timestamp=float(i + 1),
            ))
        history = tracker.property_history(100, "health")
        assert len(history) == 3
        assert history[0].new_value == 50000.0
        assert history[2].new_value == 30000.0


class TestGetVehicleEntityIds:
    def test_returns_only_vehicles(self) -> None:
        tracker = GameStateTracker()
        tracker.process_packet(_make_packet(
            PacketType.ENTITY_CREATE,
            entity_id=1, entity_type="Avatar", timestamp=0.0,
        ))
        tracker.process_packet(_make_packet(
            PacketType.ENTITY_CREATE,
            entity_id=2, entity_type="Vehicle", timestamp=0.0,
        ))
        tracker.process_packet(_make_packet(
            PacketType.ENTITY_CREATE,
            entity_id=3, entity_type="Vehicle", timestamp=0.0,
        ))
        tracker.process_packet(_make_packet(
            PacketType.ENTITY_CREATE,
            entity_id=4, entity_type="BattleLogic", timestamp=0.0,
        ))
        ids = tracker.get_vehicle_entity_ids()
        assert sorted(ids) == [2, 3]
