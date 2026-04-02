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
    attacker_id: int = 0
    damage: float = 0.0
    damage_type: str = ""  # AP, HE, SAP, torpedo, fire, flooding, secondary, etc.
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
class DamageReceivedStatEvent(GameEvent):
    """Cumulative damage-received stat snapshot from receiveDamageStat.

    Each event carries the delta since the previous snapshot for one
    (damage_param, stat_type) bucket.  The target is always the replay's
    own player (Avatar entity).
    """

    damage_param: str = ""  # weapon name from DAMAGE_RECEIVED_PARAMS
    stat_type: str = ""  # "ENEMY", "ALLY", "AGRO", "SPOT"
    delta_count: int = 0
    delta_total: float = 0.0
    cumulative_count: int = 0
    cumulative_total: float = 0.0

    @property
    def is_dealt(self) -> bool:
        """True when this records damage dealt to enemies."""
        return self.stat_type == "ENEMY"


# Kept for backwards compatibility — alias to the new name
PotentialDamageEvent = DamageReceivedStatEvent


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
class SquadronEvent(GameEvent):
    """CV squadron added/updated/removed on the minimap."""

    plane_id: int = 0
    params_id: int = 0
    team_id: int = 0
    x: float = 0.0
    z: float = 0.0
    num_planes: int = 0
    action: str = ""  # "add" | "update" | "remove" | "deactivate"


@dataclass
class AirSupportEvent(GameEvent):
    """Airstrike drop zone activated or deactivated."""

    plane_id: int = 0
    index: int = 0
    x: float = 0.0
    z: float = 0.0
    aim_length: float = 0.0
    action: str = ""  # "activate" | "deactivate"


@dataclass
class RibbonEvent(GameEvent):
    """Derived ribbon (P2). Inferred from hit events."""

    ribbon_id: int = 0
    ribbon_name: str = ""
    vehicle_id: int = 0
    target_id: int = 0
    derived: bool = True


@dataclass
class BattleResultsEvent(GameEvent):
    """Post-battle results blob (packet 0x22).

    The ``results`` dict mirrors the raw JSON payload from the server:
      - ``commonList``       : list[Any]  — 18 battle-level values
      - ``playersPublicInfo``: dict       — per-player public stats
      - ``privateDataList``  : list[Any]  — per-player private economics
      - ``arenaUniqueID``    : int
      - ``accountDBID``      : int
    """

    results: dict = field(default_factory=dict)


# ── Vehicle combat events ────────────────────────────────────────


@dataclass
class GunFireEvent(GameEvent):
    """Vehicle.shootOnClient — main battery salvo fired."""

    weapon_type: int = 0
    gun_bits: int = 0


@dataclass
class SecondaryFireEvent(GameEvent):
    """Vehicle.shootATBAGuns — secondary battery salvo fired."""

    weapon_type: int = 0
    gun_bits: int = 0


@dataclass
class GunStateEvent(GameEvent):
    """Vehicle.syncGun — gun turret state sync."""

    weapon_type: int = 0
    gun_id: int = 0
    yaw: float = 0.0
    pitch: float = 0.0
    alive: bool = True
    reload_perc: float = 0.0
    loaded_ammo: int = 0


@dataclass
class TorpedoTubeStateEvent(GameEvent):
    """Vehicle.syncTorpedoTube — torpedo tube state sync."""

    gun_id: int = 0
    yaw: float = 0.0
    pitch: float = 0.0
    alive: bool = True
    reload_perc: float = 0.0
    state: int = 0


@dataclass
class TorpedoSpreadEvent(GameEvent):
    """Vehicle.syncTorpedoState — torpedo spread state update."""

    state: int = 0


@dataclass
class AmmoSwitchEvent(GameEvent):
    """Vehicle.setAmmoForWeapon — ammo type switch for a weapon."""

    weapon_type: int = 0
    ammo_params_id: int = 0
    is_reload: bool = False


@dataclass
class WeaponStateSwitchEvent(GameEvent):
    """Vehicle.onWeaponStateSwitched — weapon state transition."""

    weapon_type: int = 0
    new_state: int = 0


@dataclass
class TorpedoLaunchEvent(GameEvent):
    """Vehicle.shootTorpedo — single torpedo launched."""

    id: int = 0
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    id2: int = 0
    id3: int = 0
    flag: bool = False


@dataclass
class DepthChargeLaunchEvent(GameEvent):
    """Vehicle.shootDepthCharge — depth charge dropped."""

    id: int = 0
    count: int = 0


@dataclass
class GunRotationSyncEvent(GameEvent):
    """Vehicle.receiveGunSyncRotations — packed gun rotation sync."""

    weapon_type: int = 0
    gun_directions: Any = None


@dataclass
class ModuleDamageEvent(GameEvent):
    """Vehicle.receiveHitLocationStateChange — module hit/damage state."""


@dataclass
class WeaponReloadStateEvent(GameEvent):
    """Vehicle.setReloadingStateForWeapon — weapon reload state."""

    weapon_type: int = 0


@dataclass
class ShipCracksEvent(GameEvent):
    """Vehicle.syncShipCracks — cosmetic hull crack sync."""


@dataclass
class ShipPhysicsEvent(GameEvent):
    """Vehicle.syncShipPhysics — ship physics state blob."""

    state_id: int = 0


@dataclass
class ShipDisappearEvent(GameEvent):
    """Vehicle.startDissapearing — ship disappear animation start."""


@dataclass
class RespawnEvent(GameEvent):
    """Vehicle.onRespawned — vehicle respawned (e.g. CV planes)."""

    reset_consumables_count: int = 0
    initial_speed: float = 0.0
    yaw: float = 0.0


@dataclass
class DamageControlStartEvent(GameEvent):
    """Vehicle.onCrashCrewEnable — damage control party activated."""


@dataclass
class DamageControlEndEvent(GameEvent):
    """Vehicle.onCrashCrewDisable — damage control party deactivated."""


@dataclass
class RageModeEvent(GameEvent):
    """Vehicle.syncRageMode — rage/berserk mode state sync."""

    hit_counter: int = 0
    state: int = 0
    state_time_passed: float = 0.0


@dataclass
class MirrorDamageEvent(GameEvent):
    """Vehicle.receiveMirrorDamage — reflected damage received."""

    damage: float = 0.0


# ── Sub-cluster 5a: Consumable events ────────────────────────────


@dataclass
class ConsumableSelectedEvent(GameEvent):
    """Avatar.onConsumableSelected — consumable slot selected."""

    consumable_type: int = 0
    is_selected: bool = False


@dataclass
class ConsumableEnabledEvent(GameEvent):
    """Avatar.onConsumableEnabled — consumable enabled/disabled."""

    consumable_id: int = 0
    enabled: bool = False


@dataclass
class ConsumablePausedEvent(GameEvent):
    """Avatar.onConsumablePaused — consumable paused."""

    consumable_type: int = 0


# ── Sub-cluster 5b: Avatar combat methods ────────────────────────


@dataclass
class ExplosionEvent(GameEvent):
    """Avatar.receiveExplosions — explosion effects."""


@dataclass
class MissileLaunchEvent(GameEvent):
    """Avatar.receiveMissile — missile launched."""


@dataclass
class MissileWaypointEvent(GameEvent):
    """Avatar.updateMissileWaypoints — missile waypoint update."""

    shot_id: int = 0


@dataclass
class MissileDamageEvent(GameEvent):
    """Avatar.receiveMissileDamage — missile damage dealt."""

    shot_id: int = 0
    damager_id: int = 0
    damage: float = 0.0


@dataclass
class MissileImpactEvent(GameEvent):
    """Avatar.receiveMissileKill — missile impact/kill."""

    shot_id: int = 0


@dataclass
class PlaneProjectileEvent(GameEvent):
    """Avatar.receivePlaneProjectilePack — plane projectile pack."""


@dataclass
class SkipBombEvent(GameEvent):
    """Avatar.receivePlaneSkipBombPacks — skip bomb packs."""


@dataclass
class RocketEvent(GameEvent):
    """Avatar.receivePlaneRocketPacks — rocket packs."""


@dataclass
class DepthChargeEvent(GameEvent):
    """Avatar.receiveDepthChargesPacks — depth charge packs."""


@dataclass
class LaserBeamEvent(GameEvent):
    """Avatar.receiveLaserBeams — laser beam effects."""


@dataclass
class TracerPositionEvent(GameEvent):
    """Avatar.updateOwnerlessTracersPosition — ownerless tracer position update."""


@dataclass
class TracerStartEvent(GameEvent):
    """Avatar.beginOwnerlessTracers — ownerless tracer start."""


@dataclass
class TracerEndEvent(GameEvent):
    """Avatar.endOwnerlessTracers — ownerless tracer end."""


@dataclass
class TorpedoSyncEvent(GameEvent):
    """Avatar.receiveTorpedoSynchronization — torpedo synchronization."""


@dataclass
class TorpedoArmedEvent(GameEvent):
    """Avatar.receiveTorpedoArmed — torpedo armed state change."""

    torpedo_id: int = 0
    armed_state: int = 0


# ── Sub-cluster 5c: Submarine/sonar ──────────────────────────────


@dataclass
class SonarPingEvent(GameEvent):
    """Avatar.receivePingerShot — sonar ping fired."""

    weapon_type: int = 0
    gun_id: int = 0
    yaw: float = 0.0


@dataclass
class SonarResetEvent(GameEvent):
    """Avatar.resetPinger — sonar pinger reset."""

    weapon_type: int = 0


@dataclass
class SonarHitEvent(GameEvent):
    """Avatar.onPingerWaveEnemyHit — sonar wave hit an enemy."""


@dataclass
class SonarWaveReceivedEvent(GameEvent):
    """Avatar.receiveWaveFromEnemy — sonar wave received from enemy."""


@dataclass
class SonarHitUpdateEvent(GameEvent):
    """Avatar.updateWaveEnemyHit — sonar enemy hit update."""


@dataclass
class SonarDetectionEvent(GameEvent):
    """Avatar.updateInvisibleWavedPoint — sonar detection of invisible target."""


@dataclass
class HydrophoneTargetEvent(GameEvent):
    """Avatar.addSubmarineHydrophoneTargets — hydrophone target added."""


@dataclass
class SubSurfacingEvent(GameEvent):
    """Avatar.syncSurfacingTime — submarine surfacing time sync."""

    time: int = 0


# ── Sub-cluster 5d: AA/priority sector ───────────────────────────


@dataclass
class AASectorEvent(GameEvent):
    """Avatar.onPrioritySectorSet — AA priority sector set."""

    sector_id: int = 0
    reinforcement_progress: float = 0.0


@dataclass
class AASectorQueueEvent(GameEvent):
    """Avatar.onNextPrioritySectorSet — next AA priority sector queued."""

    sector_id: int = 0


@dataclass
class AAAuraStateEvent(GameEvent):
    """Avatar.updateOwnerlessAuraState — AA aura state update."""


@dataclass
class AirDefenseStateEvent(GameEvent):
    """Avatar.setAirDefenseState — air defense state set."""


# ── Sub-cluster 5e: Squadron detailed events ─────────────────────


@dataclass
class SquadronSpawnEvent(GameEvent):
    """Avatar.receive_addSquadron — squadron spawned (detailed)."""


@dataclass
class SquadronUpdateDetailEvent(GameEvent):
    """Avatar.receive_updateSquadron — squadron updated (detailed)."""


@dataclass
class SquadronStateChangeEvent(GameEvent):
    """Avatar.receive_changeState — squadron state changed."""


@dataclass
class SquadronHealthEvent(GameEvent):
    """Avatar.receive_squadronHealth — squadron health update."""


@dataclass
class SquadronPlaneHealthEvent(GameEvent):
    """Avatar.receive_squadronPlanesHealth — squadron plane health update."""


@dataclass
class PlaneDeathEvent(GameEvent):
    """Avatar.receive_planeDeath — individual plane death."""


@dataclass
class SquadronVisibilityEvent(GameEvent):
    """Avatar.receive_squadronVisibilityChanged — squadron visibility changed."""


@dataclass
class SquadronStopManeuverEvent(GameEvent):
    """Avatar.receive_stopManeuvering — squadron stop maneuvering."""


@dataclass
class SquadronWaypointResetEvent(GameEvent):
    """Avatar.receive_resetWaypoints — squadron waypoints reset."""


@dataclass
class SquadronRefreshEvent(GameEvent):
    """Avatar.receive_refresh — squadron refresh."""


# ── Sub-cluster 5f: Game state methods ───────────────────────────


@dataclass
class GameRoomStateEvent(GameEvent):
    """Avatar.onGameRoomStateChanged — game room state changed (pickle blob)."""


@dataclass
class CooldownUpdateEvent(GameEvent):
    """Avatar.updateCoolDown — cooldown update."""


@dataclass
class PreBattleUpdateEvent(GameEvent):
    """Avatar.updatePreBattlesInfo — pre-battle info update."""


@dataclass
class ConnectedEvent(GameEvent):
    """Avatar.onConnected — client connected."""


@dataclass
class PreBattleEnterEvent(GameEvent):
    """Avatar.onEnterPreBattle — entering pre-battle phase."""


@dataclass
class AvatarInfoEvent(GameEvent):
    """Avatar.receiveAvatarInfo — avatar info received."""


@dataclass
class PlayerDataEvent(GameEvent):
    """Avatar.receivePlayerData — player data received."""


@dataclass
class PlayerSpawnedEvent(GameEvent):
    """Avatar.onNewPlayerSpawned — new player spawned."""


@dataclass
class BattleEndEvent(GameEvent):
    """Avatar.onBattleEnd — battle ended."""


@dataclass
class ShutdownTimeEvent(GameEvent):
    """Avatar.onShutdownTime — shutdown timer update."""

    shutdown_type: int = 0
    time_remaining: float = 0.0
    flags: int = 0


@dataclass
class UniqueSkillsEvent(GameEvent):
    """Avatar.setUniqueSkills — unique skills set."""


@dataclass
class ChatHistoryEvent(GameEvent):
    """Avatar.receiveChatHistory — chat history received."""


@dataclass
class WorldStateReceivedEvent(GameEvent):
    """Avatar.onWorldStateReceived — world state received."""


@dataclass
class PreBattleGrantsEvent(GameEvent):
    """Avatar.changePreBattleGrants — pre-battle grants changed."""

    grants: int = 0


@dataclass
class UniqueTriggerEvent(GameEvent):
    """Avatar.uniqueTriggerActivated — unique trigger activated."""


@dataclass
class WaveResetEvent(GameEvent):
    """Avatar.resetResettableWaveEnemyHits — resettable wave enemy hits reset."""


# ── Sub-cluster 5g: Vehicle one-shot methods ─────────────────────


@dataclass
class OwnerChangedEvent(GameEvent):
    """Vehicle.onOwnerChanged — vehicle owner changed."""

    owner_id: int = 0
    is_owner: bool = False


@dataclass
class ConsumablesSetEvent(GameEvent):
    """Vehicle.setConsumables — consumables set (pickle blob)."""


@dataclass
class HitLocationsInitEvent(GameEvent):
    """Vehicle.receiveHitLocationsInitialState — hit locations initial state (blob)."""


@dataclass
class TeleportEvent(GameEvent):
    """Vehicle.teleport — vehicle teleport."""


# ── Vehicle property events ─────────────────────────────────────


@dataclass
class SkillActivationEvent(GameEvent):
    """Vehicle.triggeredSkillsData — commander skill activation state changed.

    ``active_skills`` is the raw bitmask decoded from the pickled BLOB.
    Each bit corresponds to one commander skill slot being active (1) or
    inactive (0).  The exact bit-to-skill mapping depends on the ship's
    skill configuration and is not further decoded here.
    """

    vehicle_id: int = 0
    active_skills: Any = None  # decoded value from PICKLED_BLOB (usually int bitmask)


# ── Packet-level events (non-entity-method) ──────────────────────


@dataclass
class EntityLeaveEvent(GameEvent):
    """Entity left the game world (packet 0x04)."""


@dataclass
class CruiseStateEvent(GameEvent):
    """Cruise state update (packet 0x32)."""

    state: int = 0
    value: int = 0


@dataclass
class WeaponLockEvent(GameEvent):
    """Weapon lock state (packet 0x30)."""

    flags: int = 0
    target_id: int = 0


@dataclass
class CameraModeEvent(GameEvent):
    """Camera mode change (packet 0x27)."""

    mode: int = 0


@dataclass
class ShotTrackingEvent(GameEvent):
    """Shot tracking update (packet 0x33)."""

    tracking_entity: int = 0
    weapon_id: int = 0
    value: int = 0
