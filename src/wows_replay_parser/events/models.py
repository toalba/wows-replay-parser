"""
Typed game event models.

These map from raw packet method calls to semantic game events.
The mapping is based on the ClientMethods from the .def files:

Avatar.def:
  - receiveVehicleDeath → DeathEvent
  - receiveShellInfo → DamageEvent
  - receiveArtilleryShots → ShotEvent
  - receiveTorpedoes → ShotEvent
  - onChatMessage → ChatEvent
  - onAchievementEarned → AchievementEvent
  - receive_CommonCMD → CommandEvent

Vehicle.def:
  - receiveDamagesOnShip → DamageEvent
  - kill → DeathEvent
  - onConsumableUsed → ConsumableEvent
  - shootOnClient → ShotEvent
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GameEvent:
    """Base class for all game events."""

    timestamp: float
    entity_id: int = 0
    raw_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class PositionEvent(GameEvent):
    """Entity position update."""

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    yaw: float = 0.0
    direction_x: float = 0.0
    direction_y: float = 0.0
    direction_z: float = 0.0
    rotation_x: float = 0.0
    rotation_y: float = 0.0
    rotation_z: float = 0.0
    is_on_ground: bool = False
    speed: float = 0.0
    is_alive: bool = True


@dataclass
class DamageEvent(GameEvent):
    """Damage dealt to a ship."""

    target_id: int = 0
    damage: float = 0.0
    damage_type: str = ""  # AP, HE, SAP, fire, flooding, torpedo, etc.
    ammo_id: int = 0  # GAMEPARAMS_ID identifying the shell/ammo type


@dataclass
class DeathEvent(GameEvent):
    """A vehicle was destroyed."""

    victim_id: int = 0
    killer_id: int = 0
    death_reason: int = 0


@dataclass
class ShotEvent(GameEvent):
    """Artillery/torpedo salvo fired."""

    owner_id: int = 0
    params_id: int = 0  # GAMEPARAMS_ID identifying the ammo type
    salvo_id: int = 0
    shot_count: int = 0


@dataclass
class ChatEvent(GameEvent):
    """Chat message sent."""

    sender_id: int = 0
    channel: str = ""
    message: str = ""


@dataclass
class ConsumableEvent(GameEvent):
    """Consumable used on a ship."""

    consumable_id: int = 0
    vehicle_id: int = 0
    consumable_type: int = 0
    is_used: bool = True
    work_time_left: float = 0.0


@dataclass
class ShotCreatedEvent(GameEvent):
    """One shell from Avatar.receiveArtilleryShots."""

    shot_id: int = 0
    owner_id: int = 0
    params_id: int = 0
    salvo_id: int = 0
    spawn_x: float = 0.0
    spawn_y: float = 0.0
    spawn_z: float = 0.0
    target_x: float = 0.0
    target_y: float = 0.0
    target_z: float = 0.0
    pitch: float = 0.0
    speed: float = 0.0
    gun_barrel_id: int = 0
    server_time_left: float = 0.0
    shooter_height: float = 0.0
    hit_distance: float = 0.0


@dataclass
class ShotDestroyedEvent(GameEvent):
    """Shell impact from Avatar.receiveShotKills."""

    shot_id: int = 0
    owner_id: int = 0
    hit_type: int = 0
    impact_x: float = 0.0
    impact_y: float = 0.0
    impact_z: float = 0.0
    armor_penetration: float = 0.0
    shell_impact: float = 0.0
    explosion_damage: float = 0.0
    angle_in_plane: float = 0.0


@dataclass
class TorpedoCreatedEvent(GameEvent):
    """One torpedo from Avatar.receiveTorpedoes."""

    shot_id: int = 0
    owner_id: int = 0
    params_id: int = 0
    salvo_id: int = 0
    skin_id: int = 0
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    direction_x: float = 0.0
    direction_y: float = 0.0
    direction_z: float = 0.0
    armed: bool = False


@dataclass
class CapturePointUpdateEvent(GameEvent):
    """InteractiveZone property change. Fields match alias.xml CAPTURE_LOGIC_STATE."""

    zone_entity_id: int = 0
    team_id: int = 0
    radius: float = 0.0
    progress: float = 0.0  # CAPTURE_LOGIC_STATE.progress
    capture_speed: float = 0.0  # CAPTURE_LOGIC_STATE.captureSpeed
    invader_team: int = 0  # CAPTURE_LOGIC_STATE.invaderTeam
    has_invaders: bool = False  # CAPTURE_LOGIC_STATE.hasInvaders


@dataclass
class ScoreUpdateEvent(GameEvent):
    """BattleLogic property change."""

    battle_stage: int = 0
    time_left: int = 0
    teams: Any = None


@dataclass
class PropertyUpdateEvent(GameEvent):
    """Generic property change — no data loss guarantee."""

    entity_type: str = ""
    property_name: str = ""
    value: Any = None


@dataclass
class RawEvent(GameEvent):
    """Catch-all for unmatched packets."""

    packet_type: int = 0
    method_name: str = ""
    property_name: str = ""


@dataclass
class PotentialDamageEvent(GameEvent):
    """Potential damage received (agro points). From Avatar stats methods."""

    attacker_id: int = 0
    victim_id: int = 0
    agro_points: float = 0.0


@dataclass
class ScoutingDamageEvent(GameEvent):
    """Damage dealt to a spotted target. From Avatar stats methods."""

    victim_id: int = 0
    spotter_id: int = 0
    spotters_count: int = 0
    amount: float = 0.0
    weapon_type: int = 0


@dataclass
class CapContestEvent(GameEvent):
    """Player entering/leaving a capture point. From Avatar stats methods."""

    cap_index: int = 0
    vehicle_id: int = 0
    is_entering: bool = True


@dataclass
class AchievementEvent(GameEvent):
    """Achievement earned during battle."""

    player_id: int = 0
    achievement_id: int = 0


@dataclass
class MinimapVisionEvent(GameEvent):
    """Minimap vision update from Avatar.updateMinimapVisionInfo.

    Decoded from a packed 32-bit field per vehicle (Trap 6):
      bits 0-10:  raw_x (11 bits)
      bits 11-21: raw_y (11 bits)
      bits 22-29: heading (8 bits)
      bit 30:     unknown
      bit 31:     is_disappearing
    """

    vehicle_entity_id: int = 0
    raw_x: int = 0
    raw_y: int = 0
    world_x: float = 0.0
    world_z: float = 0.0
    heading_degrees: float = 0.0
    is_disappearing: bool = False
    is_visible: bool = True  # False when raw_x==0 and raw_y==0 (sentinel)


@dataclass
class RibbonEvent(GameEvent):
    """Derived ribbon (P2). Inferred from hit events."""

    ribbon_id: int = 0
    ribbon_name: str = ""
    vehicle_id: int = 0
    target_id: int = 0
    derived: bool = True
