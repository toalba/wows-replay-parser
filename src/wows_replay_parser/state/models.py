from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PropertyChange:
    """A single property value change with timestamp."""

    timestamp: float
    entity_id: int
    entity_type: str
    property_name: str
    old_value: Any
    new_value: Any


@dataclass
class ShipState:
    """Snapshot of a vehicle's state at a point in time."""

    entity_id: int
    health: float = 0.0
    max_health: float = 0.0
    regeneration_health: float = 0.0
    regenerated_health: float = 0.0
    is_alive: bool = True
    team_id: int = 0
    visibility_flags: int = 0
    burning_flags: int = 0
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    yaw: float = 0.0
    speed: float = 0.0
    # MinimapVisionInfo data (Trap 5/6)
    minimap_x: float = 0.0  # world x from minimap vision
    minimap_z: float = 0.0  # world z from minimap vision
    minimap_heading: float = 0.0  # heading in radians
    is_detected: bool = False  # whether ship is visible on minimap
    # Death position cache (Trap 13)
    death_position: tuple[float, float, float] | None = None


@dataclass
class CapturePointState:
    """Snapshot of a capture point at a point in time.

    Field names match CAPTURE_LOGIC_STATE and CONTROL_POINT_STATE in alias.xml.
    """

    entity_id: int
    radius: float = 0.0
    team_id: int = 0
    # From CAPTURE_LOGIC_STATE (nested in componentsState.captureLogic)
    progress: float = 0.0  # 0.0-1.0 capture progress
    capture_speed: float = 0.0
    invader_team: int = 0  # team currently capturing
    has_invaders: bool = False
    both_inside: bool = False
    is_enabled: bool = False
    # From CONTROL_POINT_STATE (nested in componentsState.controlPoint)
    point_type: int = 0  # cap zone type
    point_index: int = -1  # A=0, B=1, C=2, ...


@dataclass
class KillScoring:
    """Points awarded/penalized when a ship type is destroyed."""

    ship_type: str  # "Destroyer", "Cruiser", "Battleship", "AirCarrier", "Submarine"
    reward: int  # Points awarded to killing team
    penalty: int  # Points lost by dying team


@dataclass
class HoldScoring:
    """Points awarded per tick for holding capture points."""

    reward: int  # Points per tick
    period: int  # Tick interval in seconds
    cp_indices: list[int] = field(default_factory=list)  # Which cap points


@dataclass
class BattleState:
    """Snapshot of battle-level state."""

    battle_stage: int = 0
    time_left: int = 0
    team_scores: dict[int, int] = field(default_factory=dict)
    capture_points: list[CapturePointState] = field(default_factory=list)
    battle_result_winner: int = -1
    battle_result_reason: int = 0
    # Scoring config (from BattleLogic.state.missions, set once at battle start)
    team_win_score: int = 1000
    team_start_scores: dict[int, int] = field(default_factory=dict)
    kill_scoring: list[KillScoring] = field(default_factory=list)
    hold_scoring: list[HoldScoring] = field(default_factory=list)


@dataclass
class AircraftState:
    """Snapshot of a squadron/airstrike on the minimap."""

    plane_id: int  # PLANE_ID (INT64), dict key
    squadron_type: str  # "controllable" | "airstrike"
    team_id: int = 0
    params_id: int = 0  # GAMEPARAMS_ID (for icon lookup)
    x: float = 0.0  # world x
    z: float = 0.0  # world z
    is_active: bool = True
    num_planes: int = 0  # from SQUADRON_STATE.numPlanes (0 if unknown)


@dataclass
class SmokeScreenState:
    """Snapshot of a smoke screen entity."""

    entity_id: int
    radius: float = 0.0
    height: float = 0.0
    bc_radius: float = 0.0
    active_point_index: int = -1
    points: list[tuple[float, float, float]] = field(default_factory=list)
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)


@dataclass
class BuildingState:
    """Snapshot of a building entity (e.g., shore installations)."""

    entity_id: int
    params_id: int = 0
    team_id: int = 0
    is_alive: bool = True
    is_suppressed: bool = False
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)


@dataclass
class GameState:
    """Full game state snapshot at a point in time."""

    timestamp: float
    ships: dict[int, ShipState] = field(default_factory=dict)
    battle: BattleState = field(default_factory=BattleState)
    aircraft: dict[int, AircraftState] = field(default_factory=dict)
    smoke_screens: dict[int, SmokeScreenState] = field(default_factory=dict)
    buildings: dict[int, BuildingState] = field(default_factory=dict)
