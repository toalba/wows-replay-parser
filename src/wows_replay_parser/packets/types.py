"""
Packet type definitions for the BigWorld network protocol.

Values verified against:
- landaire/wows-toolkit (crates/wows-replays, packet2.rs)
- Monstrofil/replays_unpack (post-12.6 mapping)

Uses the >=12.6.0 mapping. Older replays may use different values.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any


class PacketType(IntEnum):
    """BigWorld packet types found in replay streams (>=12.6 mapping)."""

    BASE_PLAYER_CREATE = 0x00
    CELL_PLAYER_CREATE = 0x01
    ENTITY_CONTROL = 0x02
    ENTITY_ENTER = 0x03
    ENTITY_LEAVE = 0x04
    ENTITY_CREATE = 0x05

    ENTITY_PROPERTY = 0x07
    ENTITY_METHOD = 0x08

    POSITION = 0x0A

    SERVER_TICK = 0x0E
    SERVER_TIMESTAMP = 0x0F
    INIT_FLAG = 0x10
    INIT_MARKER = 0x13
    VERSION = 0x16
    GUN_MARKER = 0x18
    PLAYER_NET_STATS = 0x1D
    OWN_SHIP = 0x20
    BATTLE_RESULTS = 0x22
    NESTED_PROPERTY = 0x23
    CAMERA = 0x25
    BASE_PLAYER_CREATE_STUB = 0x26
    CAMERA_MODE = 0x27
    MAP = 0x28
    NON_VOLATILE_POSITION = 0x2A
    PLAYER_ORIENTATION = 0x2C
    CAMERA_FREE_LOOK = 0x2F
    SET_WEAPON_LOCK = 0x30
    SUB_CONTROLLER = 0x31
    CRUISE_STATE = 0x32
    SHOT_TRACKING = 0x33

    UNKNOWN = 0xFF


@dataclass
class Packet:
    """A decoded network packet from the replay stream."""

    type: PacketType
    entity_id: int = 0
    timestamp: float = 0.0
    raw_payload: bytes = b""

    # Decoded payload (set by packet decoder based on type)
    method_name: str | None = None
    method_args: dict[str, Any] | None = None
    property_name: str | None = None
    property_value: Any = None
    position: tuple[float, float, float] | None = None
    direction: tuple[float, float, float] | None = None
    rotation: tuple[float, float, float] | None = None
    is_on_ground: bool = False

    # Metadata
    entity_type: str | None = None  # e.g. "Avatar", "Vehicle"
    size: int = 0

    @property
    def is_method_call(self) -> bool:
        return self.type == PacketType.ENTITY_METHOD

    @property
    def is_property_update(self) -> bool:
        return self.type == PacketType.ENTITY_PROPERTY
