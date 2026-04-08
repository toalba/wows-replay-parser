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
    operation_type: str | None = None  # "set", "set_key", "set_range", "delete", "clear"


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
    is_on_forsage: bool = False
    engine_power: int = 0
    engine_dir: int = 0
    speed_sign_dir: int = 0
    max_speed: float = 0.0
    rudder_angle: float = 0.0
    deep_rudder_angle: float = 0.0
    selected_weapon: int = 0
    is_invisible: bool = False
    has_active_squadron: bool = False
    is_in_rage_mode: bool = False
    respawn_time: float = 0.0
    blocked_controls: int = 0
    oil_leak_state: int = 0
    owner: int = 0
    regen_crew_hp_limit: float = 0.0
    buoyancy: float = 0.0
    air_defense_disp_radius: float = 0.0
    weapon_lock_flags: int = 0
    target_local_pos: int = 0
    torpedo_local_pos: int = 0
    turret_yaws: dict[int, float] = field(default_factory=dict)  # gun_id → yaw radians
    is_bot: bool = False
    has_air_targets_in_range: bool = False
    is_anti_air_mode: bool = False
    atba_yaws: dict[int, float] = field(default_factory=dict)  # gun_id → yaw radians (secondary battery)
    torpedo_yaws: dict[int, float] = field(default_factory=dict)  # gun_id → yaw radians (torpedo tubes)
    battery: dict | None = None  # BATTERY_STATE from Vehicle state.battery
    buffs: list | None = None  # BUFFS_STATE from Vehicle state.buffs
    atba_targets: list | None = None  # ATBA_STATE from Vehicle state.atba


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
    is_visible: bool = True
    capture_time: float = 0.0
    buoy_visual_id: int = 0
    next_control_point: int = 0
    timer_name: str = ""


@dataclass
class BuffZoneState:
    """Snapshot of a buff drop zone (InteractiveZone type==6)."""

    entity_id: int
    zone_id: int = 0  # from DROP_ITEM_STATE.zoneId
    params_id: int = 0  # from DROP_ITEM_STATE.paramsId
    radius: float = 0.0
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    is_active: bool = True


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
    battle_type: int = 0
    duration: int = 0
    map_border: dict | None = None
    drop_state: dict | None = None  # Raw DROP_STATE from BattleLogic.state.drop


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
    owner_id: int = 0  # Vehicle entity_id of the owning ship (0 if unknown)


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
    spawn_point_effect: str = ""
    live_point_effect: str = ""


@dataclass
class BuildingState:
    """Snapshot of a building entity (e.g., shore installations)."""

    entity_id: int
    params_id: int = 0
    team_id: int = 0
    is_alive: bool = True
    is_suppressed: bool = False
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    target_pos: tuple[float, float, float] | None = None


@dataclass
class WeatherZoneState:
    """Snapshot of a weather zone (InteractiveZone type==5)."""

    entity_id: int
    name: str = ""
    radius: float = 0.0
    params_id: int = 0
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    inner_radius: float = 0.0
    owner_id: int = 0  # Ship the zone is attached to (if any)


@dataclass
class GameState:
    """Full game state snapshot at a point in time."""

    timestamp: float
    ships: dict[int, ShipState] = field(default_factory=dict)
    battle: BattleState = field(default_factory=BattleState)
    aircraft: dict[int, AircraftState] = field(default_factory=dict)
    smoke_screens: dict[int, SmokeScreenState] = field(default_factory=dict)
    buildings: dict[int, BuildingState] = field(default_factory=dict)
    weather_zones: dict[int, WeatherZoneState] = field(default_factory=dict)
    buff_zones: dict[int, BuffZoneState] = field(default_factory=dict)
