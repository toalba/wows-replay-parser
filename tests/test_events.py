"""Unit tests for event models and factories."""

from __future__ import annotations

from wows_replay_parser.events.models import (
    CapturePointUpdateEvent,
    PositionEvent,
    PropertyUpdateEvent,
    RawEvent,
    ShotCreatedEvent,
    ShotDestroyedEvent,
    TorpedoCreatedEvent,
)
from wows_replay_parser.events.stream import (
    EventStream,
    _shots_created,
    _shots_destroyed,
    _torpedoes_created,
)
from wows_replay_parser.packets.types import Packet, PacketType


def _make_packet(**kwargs: object) -> Packet:
    pkt = Packet(type=kwargs.pop("ptype", PacketType.ENTITY_METHOD))  # type: ignore[arg-type]
    for k, v in kwargs.items():
        setattr(pkt, k, v)
    return pkt


class TestShotsCreatedFactory:
    def test_single_shot_pack(self) -> None:
        pkt = _make_packet(
            ptype=PacketType.ENTITY_METHOD,
            entity_id=1,
            timestamp=10.0,
            method_name="receiveArtilleryShots",
            method_args={
                "arg0": [
                    {
                        "paramsID": 42,
                        "ownerID": 100,
                        "salvoID": 7,
                        "shots": [
                            {
                                "pos": {"x": 1.0, "y": 2.0, "z": 3.0},
                                "tarPos": {"x": 10.0, "y": 0.0, "z": 30.0},
                                "shotID": 501,
                                "pitch": 0.5,
                                "speed": 800.0,
                                "gunBarrelID": 2,
                                "serverTimeLeft": 1.5,
                                "shooterHeight": 15.0,
                                "hitDistance": 12000.0,
                            },
                        ],
                    },
                ],
            },
        )
        events = _shots_created(pkt)
        assert len(events) == 1
        e = events[0]
        assert isinstance(e, ShotCreatedEvent)
        assert e.shot_id == 501
        assert e.owner_id == 100
        assert e.params_id == 42
        assert e.spawn_x == 1.0
        assert e.target_z == 30.0
        assert e.speed == 800.0

    def test_multiple_shots(self) -> None:
        pkt = _make_packet(
            ptype=PacketType.ENTITY_METHOD,
            entity_id=1,
            timestamp=10.0,
            method_name="receiveArtilleryShots",
            method_args={
                "arg0": [
                    {
                        "paramsID": 1,
                        "ownerID": 2,
                        "salvoID": 3,
                        "shots": [
                            {"pos": {}, "tarPos": {}, "shotID": i}
                            for i in range(5)
                        ],
                    },
                ],
            },
        )
        events = _shots_created(pkt)
        assert len(events) == 5

    def test_empty_input(self) -> None:
        pkt = _make_packet(
            ptype=PacketType.ENTITY_METHOD,
            entity_id=1,
            timestamp=0.0,
            method_name="receiveArtilleryShots",
            method_args={"arg0": []},
        )
        assert _shots_created(pkt) == []


class TestShotsDestroyedFactory:
    def test_single_kill(self) -> None:
        pkt = _make_packet(
            ptype=PacketType.ENTITY_METHOD,
            entity_id=1,
            timestamp=10.0,
            method_name="receiveShotKills",
            method_args={
                "arg0": [
                    {
                        "ownerID": 200,
                        "hitType": 3,
                        "kills": [
                            {
                                "pos": {"x": 5.0, "y": 0.0, "z": 10.0},
                                "shotID": 501,
                                "terminalBallisticsInfo": {
                                    "armorPenetration": 400.0,
                                    "shellImpact": 10.0,
                                    "explosionDamage": 0.0,
                                    "angleInPlane": 45.0,
                                },
                            },
                        ],
                    },
                ],
            },
        )
        events = _shots_destroyed(pkt)
        assert len(events) == 1
        e = events[0]
        assert isinstance(e, ShotDestroyedEvent)
        assert e.shot_id == 501
        assert e.armor_penetration == 400.0


class TestTorpedoesCreatedFactory:
    def test_single_torpedo(self) -> None:
        pkt = _make_packet(
            ptype=PacketType.ENTITY_METHOD,
            entity_id=1,
            timestamp=10.0,
            method_name="receiveTorpedoes",
            method_args={
                "arg0": [
                    {
                        "paramsID": 99,
                        "ownerID": 300,
                        "salvoID": 5,
                        "skinID": 1,
                        "torpedoes": [
                            {
                                "pos": {"x": 50.0, "y": 0.0, "z": 100.0},
                                "dir": {"x": 0.5, "y": 0.0, "z": 0.8},
                                "shotID": 601,
                                "armed": True,
                            },
                        ],
                    },
                ],
            },
        )
        events = _torpedoes_created(pkt)
        assert len(events) == 1
        e = events[0]
        assert isinstance(e, TorpedoCreatedEvent)
        assert e.shot_id == 601
        assert e.armed is True
        assert e.direction_z == 0.8


class TestEventStreamProcess:
    def test_position_event_has_direction(self) -> None:
        stream = EventStream()
        pkt = Packet(type=PacketType.POSITION)
        pkt.entity_id = 100
        pkt.timestamp = 1.0
        pkt.position = (10.0, 0.0, 20.0)
        pkt.direction = (1.0, 0.0, 0.0)
        pkt.rotation = (0.0, 0.5, 0.0)
        pkt.is_on_ground = True
        events = stream.process([pkt])
        assert len(events) == 1
        e = events[0]
        assert isinstance(e, PositionEvent)
        assert e.direction_x == 1.0
        assert e.rotation_y == 0.5
        assert e.is_on_ground is True

    def test_property_update_emits_event(self) -> None:
        stream = EventStream()
        pkt = Packet(type=PacketType.ENTITY_PROPERTY)
        pkt.entity_id = 100
        pkt.timestamp = 1.0
        pkt.property_name = "health"
        pkt.property_value = 40000.0
        pkt.entity_type = "Vehicle"
        events = stream.process([pkt])
        assert len(events) >= 1
        assert isinstance(events[0], PropertyUpdateEvent)
        assert events[0].property_name == "health"

    def test_unknown_method_emits_raw_event(self) -> None:
        stream = EventStream()
        pkt = Packet(type=PacketType.ENTITY_METHOD)
        pkt.entity_id = 100
        pkt.timestamp = 1.0
        pkt.method_name = "unknownMethod"
        pkt.method_args = {"arg0": 42}
        events = stream.process([pkt])
        assert len(events) == 1
        assert isinstance(events[0], RawEvent)
        assert events[0].method_name == "unknownMethod"

    def test_known_method_emits_typed_event(self) -> None:
        from wows_replay_parser.events.models import DeathEvent

        stream = EventStream()
        pkt = Packet(type=PacketType.ENTITY_METHOD)
        pkt.entity_id = 1
        pkt.timestamp = 5.0
        pkt.method_name = "receiveVehicleDeath"
        pkt.method_args = {"arg0": 200, "arg1": 300, "arg2": 1}
        events = stream.process([pkt])
        assert len(events) == 1
        assert isinstance(events[0], DeathEvent)
