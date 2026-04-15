"""
Transforms decoded packets into typed game events.

Maps specific entity method calls to semantic event types.
This is the layer where we go from "Avatar called method 'receiveVehicleDeath'
with args {arg0: 123, arg1: 456, arg2: 2}" to a typed DeathEvent.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from wows_replay_parser.state.tracker import GameStateTracker

from wows_replay_parser.events.models import (
    AAAuraStateEvent,
    AASectorEvent,
    AASectorQueueEvent,
    AchievementEvent,
    AirDefenseStateEvent,
    AirSupportEvent,
    AmmoSwitchEvent,
    AvatarInfoEvent,
    BattleEndEvent,
    BattleResultsEvent,
    CameraModeEvent,
    CapContestEvent,
    CapturePointUpdateEvent,
    ChatEvent,
    ChatHistoryEvent,
    ConnectedEvent,
    ConsumableEnabledEvent,
    ConsumableEvent,
    ConsumablePausedEvent,
    ConsumableSelectedEvent,
    ConsumablesSetEvent,
    CooldownUpdateEvent,
    CruiseStateEvent,
    DamageControlEndEvent,
    DamageControlStartEvent,
    DamageEvent,
    DamageReceivedStatEvent,
    DeathEvent,
    DepthChargeEvent,
    DepthChargeLaunchEvent,
    EntityLeaveEvent,
    ExplosionEvent,
    GameEvent,
    GameRoomStateEvent,
    GunFireEvent,
    GunRotationSyncEvent,
    GunStateEvent,
    HitLocationsInitEvent,
    HydrophoneTargetEvent,
    LaserBeamEvent,
    MinimapVisionEvent,
    MirrorDamageEvent,
    MissileDamageEvent,
    MissileImpactEvent,
    MissileLaunchEvent,
    MissileWaypointEvent,
    ModuleDamageEvent,
    OwnerChangedEvent,
    PlaneDeathEvent,
    PlaneProjectileEvent,
    PlayerDataEvent,
    PlayerSpawnedEvent,
    PositionEvent,
    PreBattleEnterEvent,
    PreBattleGrantsEvent,
    PreBattleUpdateEvent,
    PropertyUpdateEvent,
    RageModeEvent,
    RawEvent,
    RespawnEvent,
    RocketEvent,
    ScoreUpdateEvent,
    ScoutingDamageEvent,
    SecondaryFireEvent,
    ShipCracksEvent,
    ShipDisappearEvent,
    ShipPhysicsEvent,
    ShotCreatedEvent,
    ShotDestroyedEvent,
    ShotTrackingEvent,
    ShutdownTimeEvent,
    SkillActivationEvent,
    SkipBombEvent,
    SonarDetectionEvent,
    SonarHitEvent,
    SonarHitUpdateEvent,
    SonarPingEvent,
    SonarResetEvent,
    SonarWaveReceivedEvent,
    SquadronEvent,
    SquadronHealthEvent,
    SquadronPlaneHealthEvent,
    SquadronRefreshEvent,
    SquadronSpawnEvent,
    SquadronStateChangeEvent,
    SquadronStopManeuverEvent,
    SquadronUpdateDetailEvent,
    SquadronVisibilityEvent,
    SquadronWaypointResetEvent,
    SubSurfacingEvent,
    TeleportEvent,
    TorpedoArmedEvent,
    TorpedoCreatedEvent,
    TorpedoLaunchEvent,
    TorpedoSpreadEvent,
    TorpedoSyncEvent,
    TorpedoTubeStateEvent,
    TracerEndEvent,
    TracerPositionEvent,
    TracerStartEvent,
    UniqueSkillsEvent,
    UniqueTriggerEvent,
    WaveResetEvent,
    WeaponLockEvent,
    WeaponReloadStateEvent,
    WeaponStateSwitchEvent,
    WorldStateReceivedEvent,
)
from wows_replay_parser.packets.types import Packet, PacketType


def _get(args: dict[str, Any], key: str, default: Any = 0) -> Any:
    """Safely get a value from method_args, supporting both named and positional keys."""
    return args.get(key, default)


# ── Event factories ─────────────────────────────────────────────

def _death_from_receive_vehicle_death(pkt: Packet) -> DeathEvent:
    """receiveVehicleDeath(0:ENTITY_ID victim, 1:ENTITY_ID killer, 2:UINT32 reason)"""
    args = pkt.method_args or {}
    return DeathEvent(
        timestamp=pkt.timestamp,
        entity_id=pkt.entity_id,
        victim_id=_get(args, "arg0"),
        killer_id=_get(args, "arg1"),
        death_reason=_get(args, "arg2"),
        raw_data=args,
    )


def _death_from_vehicle_kill(pkt: Packet) -> DeathEvent:
    """Vehicle.kill(0:INT8, 1:UINT32, 2:UINT32, 3:FLOAT, ..., 8:ENTITY_ID killer)"""
    args = pkt.method_args or {}
    return DeathEvent(
        timestamp=pkt.timestamp,
        entity_id=pkt.entity_id,
        victim_id=pkt.entity_id,
        killer_id=_get(args, "arg8"),
        death_reason=_get(args, "arg0"),
        raw_data=args,
    )


def _damage_from_receive_shell_info(pkt: Packet) -> DamageEvent:
    """receiveShellInfo(0:GAMEPARAMS_ID, 1:UINT32, 2:UINT32 damage, 3:ENTITY_ID target, ...)"""
    args = pkt.method_args or {}
    return DamageEvent(
        timestamp=pkt.timestamp,
        entity_id=pkt.entity_id,
        target_id=_get(args, "arg3"),
        damage=float(_get(args, "arg2", 0)),
        ammo_id=_get(args, "arg0", 0),
        raw_data=args,
    )


def _damage_from_receive_damages(pkt: Packet) -> list[DamageEvent]:
    """receiveDamagesOnShip(0:ARRAY<of>DAMAGES</of>).

    Each DAMAGES entry: {vehicleID: ENTITY_ID, damage: FLOAT}
    The method is called ON the target vehicle, so entity_id = target.
    vehicleID = attacker.
    """
    args = pkt.method_args or {}
    damages = _get(args, "arg0", [])
    if isinstance(damages, dict):
        damages = [damages]
    if not isinstance(damages, list):
        return [DamageEvent(
            timestamp=pkt.timestamp,
            entity_id=pkt.entity_id,
            target_id=pkt.entity_id,
            raw_data=args,
        )]
    events: list[DamageEvent] = []
    for entry in damages:
        if not isinstance(entry, dict):
            continue
        events.append(DamageEvent(
            timestamp=pkt.timestamp,
            entity_id=pkt.entity_id,
            target_id=pkt.entity_id,
            attacker_id=int(entry.get("vehicleID", 0) or 0),
            damage=float(entry.get("damage", 0) or 0),
            raw_data=entry,
        ))
    return events if events else [DamageEvent(
        timestamp=pkt.timestamp,
        entity_id=pkt.entity_id,
        target_id=pkt.entity_id,
        raw_data=args,
    )]


def _coerce_chat_str(value: object) -> str:
    """Normalize chat string fields: None → "", bytes → tolerant decode,
    strip NULs. The underlying STRING schema already decodes bytes, but
    older/partial payloads may still surface raw bytes or None."""
    if value is None:
        return ""
    if isinstance(value, (bytes, bytearray)):
        try:
            text = bytes(value).decode("utf-8")
        except UnicodeDecodeError:
            text = bytes(value).decode("latin-1")
    else:
        text = str(value)
    return text.replace("\x00", "")


def _chat(pkt: Packet) -> ChatEvent:
    """onChatMessage(0:PLAYER_ID sender, 1:STRING channel, 2:STRING body, 3:STRING extra)"""
    args = pkt.method_args or {}
    return ChatEvent(
        timestamp=pkt.timestamp,
        entity_id=pkt.entity_id,
        sender_id=_get(args, "arg0") or 0,
        channel=_coerce_chat_str(_get(args, "arg1", "")),
        message=_coerce_chat_str(_get(args, "arg2", "")),
        raw_data=args,
    )


def _consumable(pkt: Packet) -> ConsumableEvent:
    """Vehicle.onConsumableUsed(consumableUsageParams:..., workTimeLeft:FLOAT32)"""
    args = pkt.method_args or {}
    # consumableUsageParams is a USER_TYPE (opaque blob)
    # workTimeLeft is the second named arg
    work_time = args.get("workTimeLeft", 0.0)
    usage_params = args.get("consumableUsageParams")
    # Try to extract consumable type from usage_params if it's a dict
    consumable_type = 0
    if isinstance(usage_params, dict):
        consumable_type = usage_params.get("consumableType", 0) or 0
    return ConsumableEvent(
        timestamp=pkt.timestamp,
        entity_id=pkt.entity_id,
        vehicle_id=pkt.entity_id,
        consumable_type=int(consumable_type),
        work_time_left=float(work_time or 0),
        raw_data=args,
    )


def _generic(event_cls: type[GameEvent]) -> Callable[[Packet], GameEvent]:
    """Fallback factory that stores raw_data only."""
    def factory(pkt: Packet) -> GameEvent:
        return event_cls(
            timestamp=pkt.timestamp,
            entity_id=pkt.entity_id,
            raw_data=pkt.method_args or {},
        )
    return factory


def _shots_created(pkt: Packet) -> list[ShotCreatedEvent]:
    """receiveArtilleryShots: arg is ARRAY<of>SHOTS_PACK</of>."""
    events: list[ShotCreatedEvent] = []
    args = pkt.method_args or {}
    packs = _get(args, "arg0", [])
    if isinstance(packs, dict):
        packs = [packs]
    if not isinstance(packs, list):
        return events
    for pack in packs:
        if not isinstance(pack, dict):
            continue
        params_id = pack.get("paramsID", 0)
        owner_id = pack.get("ownerID", 0)
        salvo_id = pack.get("salvoID", 0)
        shots = pack.get("shots", [])
        if not isinstance(shots, list):
            continue
        for shot in shots:
            if not isinstance(shot, dict):
                continue
            pos = shot.get("pos", {})
            tar = shot.get("tarPos", {})
            if not isinstance(pos, dict):
                pos = {}
            if not isinstance(tar, dict):
                tar = {}
            events.append(ShotCreatedEvent(
                timestamp=pkt.timestamp,
                entity_id=pkt.entity_id,
                raw_data=shot,
                shot_id=shot.get("shotID", 0),
                owner_id=owner_id,
                params_id=params_id,
                salvo_id=salvo_id,
                spawn_x=float(pos.get("x", 0)),
                spawn_y=float(pos.get("y", 0)),
                spawn_z=float(pos.get("z", 0)),
                target_x=float(tar.get("x", 0)),
                target_y=float(tar.get("y", 0)),
                target_z=float(tar.get("z", 0)),
                pitch=float(shot.get("pitch", 0)),
                speed=float(shot.get("speed", 0)),
                gun_barrel_id=shot.get("gunBarrelID", 0),
                server_time_left=float(
                    shot.get("serverTimeLeft", 0)
                ),
                shooter_height=float(
                    shot.get("shooterHeight", 0)
                ),
                hit_distance=float(
                    shot.get("hitDistance", 0)
                ),
            ))
    return events


def _shots_destroyed(pkt: Packet) -> list[ShotDestroyedEvent]:
    """receiveShotKills: arg is ARRAY<of>SHOTKILLS_PACK</of>."""
    events: list[ShotDestroyedEvent] = []
    args = pkt.method_args or {}
    packs = _get(args, "arg0", [])
    if isinstance(packs, dict):
        packs = [packs]
    if not isinstance(packs, list):
        return events
    for pack in packs:
        if not isinstance(pack, dict):
            continue
        owner_id = pack.get("ownerID", 0)
        hit_type = pack.get("hitType", 0)
        kills = pack.get("kills", [])
        if not isinstance(kills, list):
            continue
        for kill in kills:
            if not isinstance(kill, dict):
                continue
            pos = kill.get("pos", {})
            tbi = kill.get("terminalBallisticsInfo", {})
            if not isinstance(pos, dict):
                pos = {}
            if not isinstance(tbi, dict):
                tbi = {}
            events.append(ShotDestroyedEvent(
                timestamp=pkt.timestamp,
                entity_id=pkt.entity_id,
                raw_data=kill,
                shot_id=kill.get("shotID", 0),
                owner_id=owner_id,
                hit_type=hit_type,
                impact_x=float(pos.get("x", 0)),
                impact_y=float(pos.get("y", 0)),
                impact_z=float(pos.get("z", 0)),
                armor_penetration=float(
                    tbi.get("armorPenetration", 0)
                ),
                shell_impact=float(
                    tbi.get("shellImpact", 0)
                ),
                explosion_damage=float(
                    tbi.get("explosionDamage", 0)
                ),
                angle_in_plane=float(
                    tbi.get("angleInPlane", 0)
                ),
            ))
    return events


def _torpedoes_created(pkt: Packet) -> list[TorpedoCreatedEvent]:
    """receiveTorpedoes: arg is ARRAY<of>TORPEDOES_PACK</of>."""
    events: list[TorpedoCreatedEvent] = []
    args = pkt.method_args or {}
    packs = _get(args, "arg0", [])
    if isinstance(packs, dict):
        packs = [packs]
    if not isinstance(packs, list):
        return events
    for pack in packs:
        if not isinstance(pack, dict):
            continue
        owner_id = pack.get("ownerID", 0)
        params_id = pack.get("paramsID", 0)
        salvo_id = pack.get("salvoID", 0)
        skin_id = pack.get("skinID", 0)
        torps = pack.get("torpedoes", [])
        if not isinstance(torps, list):
            continue
        for torp in torps:
            if not isinstance(torp, dict):
                continue
            pos = torp.get("pos", {})
            d = torp.get("dir", {})
            if not isinstance(pos, dict):
                pos = {}
            if not isinstance(d, dict):
                d = {}
            events.append(TorpedoCreatedEvent(
                timestamp=pkt.timestamp,
                entity_id=pkt.entity_id,
                raw_data=torp,
                shot_id=torp.get("shotID", 0),
                owner_id=owner_id,
                params_id=params_id,
                salvo_id=salvo_id,
                skin_id=skin_id,
                x=float(pos.get("x", 0)),
                y=float(pos.get("y", 0)),
                z=float(pos.get("z", 0)),
                direction_x=float(d.get("x", 0)),
                direction_y=float(d.get("y", 0)),
                direction_z=float(d.get("z", 0)),
                armed=bool(torp.get("armed", False)),
            ))
    return events


# receiveDamageStat is handled as a stateful method on EventStream
# (needs previous snapshot for delta computation).


def _scouting_damage(pkt: Packet) -> ScoutingDamageEvent:
    """Scouting damage event — damage dealt to spotted targets."""
    args = pkt.method_args or {}
    return ScoutingDamageEvent(
        timestamp=pkt.timestamp,
        entity_id=pkt.entity_id,
        victim_id=_get(args, "arg0", 0),
        spotter_id=_get(args, "arg1", 0),
        spotters_count=_get(args, "arg2", 0),
        amount=float(_get(args, "arg3", 0) or 0),
        weapon_type=_get(args, "arg4", 0),
        raw_data=args,
    )


def _cap_contest(pkt: Packet) -> CapContestEvent:
    """Player entering/leaving a capture point.

    CP_PLAYER_CHANGE args: (0:index, 1:wasAdded, 2:vehicleID)
    """
    args = pkt.method_args or {}
    return CapContestEvent(
        timestamp=pkt.timestamp,
        entity_id=pkt.entity_id,
        cap_index=_get(args, "arg0", 0),
        is_entering=bool(_get(args, "arg1", True)),
        vehicle_id=_get(args, "arg2", 0),
        raw_data=args,
    )


def _minimap_vision_info(pkt: Packet) -> list[MinimapVisionEvent]:
    """updateMinimapVisionInfo: ARRAY of packed vehicle vision data.

    Each entry is a dict with vehicleID (ENTITY_ID) and packedData (UINT32).
    The packedData bitfield (Trap 6):
      bits 0-10:  raw_x (11 bits)
      bits 11-21: raw_y (11 bits)
      bits 22-29: heading (8 bits)
      bit 30:     unknown
      bit 31:     is_disappearing
    """
    events: list[MinimapVisionEvent] = []
    args = pkt.method_args or {}
    # updateMinimapVisionInfo has two MINIMAPINFO args (ally + enemy vision)
    all_entries: list = []
    for arg_key in ("arg0", "arg1"):
        entries = _get(args, arg_key, [])
        if isinstance(entries, dict):
            entries = [entries]
        if isinstance(entries, list):
            all_entries.extend(entries)
    if not all_entries:
        return events

    for entry in all_entries:
        if not isinstance(entry, dict):
            continue
        vehicle_id = entry.get("vehicleID", 0)
        packed = int(entry.get("packedData", 0))

        # Unpack bitfield
        raw_x = packed & 0x7FF           # bits 0-10
        raw_y = (packed >> 11) & 0x7FF   # bits 11-21
        raw_heading = (packed >> 22) & 0xFF  # bits 22-29
        is_disappearing = bool(packed & (1 << 31))  # bit 31

        # Sentinel check: raw_x==0 && raw_y==0 means no valid position
        is_visible = not (raw_x == 0 and raw_y == 0)

        # Heading: 8-bit → degrees
        heading_degrees = raw_heading / 256.0 * 360.0 - 180.0

        # Position: raw → stored → world
        # stored_x = raw_x / 512.0 - 1.5
        # world_x = (stored_x + 1.5) * 512.0 / 2047.0 * 5000.0 - 2500.0
        # Simplified: world = raw / 2047.0 * 5000.0 - 2500.0
        world_x = raw_x / 2047.0 * 5000.0 - 2500.0 if is_visible else 0.0
        world_z = raw_y / 2047.0 * 5000.0 - 2500.0 if is_visible else 0.0

        events.append(MinimapVisionEvent(
            timestamp=pkt.timestamp,
            entity_id=pkt.entity_id,
            raw_data=entry,
            vehicle_entity_id=vehicle_id,
            raw_x=raw_x,
            raw_y=raw_y,
            world_x=world_x,
            world_z=world_z,
            heading_degrees=heading_degrees,
            is_disappearing=is_disappearing,
            is_visible=is_visible,
        ))
    return events


def _achievement(pkt: Packet) -> AchievementEvent:
    """onAchievementEarned(0:PLAYER_ID, 1:UINT32 achievementId)."""
    args = pkt.method_args or {}
    return AchievementEvent(
        timestamp=pkt.timestamp,
        entity_id=pkt.entity_id,
        player_id=_get(args, "arg0", 0),
        achievement_id=_get(args, "arg1", 0),
        raw_data=args,
    )


def _squadron_add(pkt: Packet) -> SquadronEvent:
    """receive_addMinimapSquadron(plane_id, team, params_id, pos, bool)."""
    args = pkt.method_args or {}
    pos = _get(args, "arg3", {})
    return SquadronEvent(
        timestamp=pkt.timestamp, entity_id=pkt.entity_id,
        plane_id=int(_get(args, "arg0", 0)),
        team_id=int(_get(args, "arg1", 0)),
        params_id=int(_get(args, "arg2", 0)),
        x=float(pos.get("x", 0)) if isinstance(pos, dict) else 0.0,
        z=float(pos.get("y", 0)) if isinstance(pos, dict) else 0.0,
        action="add", raw_data=args,
    )


def _squadron_update(pkt: Packet) -> SquadronEvent:
    """receive_updateMinimapSquadron(plane_id, pos)."""
    args = pkt.method_args or {}
    pos = _get(args, "arg1", {})
    return SquadronEvent(
        timestamp=pkt.timestamp, entity_id=pkt.entity_id,
        plane_id=int(_get(args, "arg0", 0)),
        x=float(pos.get("x", 0)) if isinstance(pos, dict) else 0.0,
        z=float(pos.get("y", 0)) if isinstance(pos, dict) else 0.0,
        action="update", raw_data=args,
    )


def _squadron_remove(pkt: Packet) -> SquadronEvent:
    """receive_removeMinimapSquadron / receive_removeSquadron."""
    args = pkt.method_args or {}
    return SquadronEvent(
        timestamp=pkt.timestamp, entity_id=pkt.entity_id,
        plane_id=int(_get(args, "arg0", 0)),
        action="remove", raw_data=args,
    )


def _squadron_deactivate(pkt: Packet) -> SquadronEvent:
    """receive_deactivateSquadron(plane_id, reason)."""
    args = pkt.method_args or {}
    return SquadronEvent(
        timestamp=pkt.timestamp, entity_id=pkt.entity_id,
        plane_id=int(_get(args, "arg0", 0)),
        action="deactivate", raw_data=args,
    )


def _air_support_activate(pkt: Packet) -> AirSupportEvent:
    """activateAirSupport(index, squadronID, position, aimLength, airSupportShotID)."""
    args = pkt.method_args or {}
    pos = args.get("position") or {}
    return AirSupportEvent(
        timestamp=pkt.timestamp, entity_id=pkt.entity_id,
        index=int(args.get("index", 0)),
        plane_id=int(args.get("squadronID", 0)),
        x=float(pos.get("x", 0)) if isinstance(pos, dict) else 0.0,
        z=float(pos.get("z", 0)) if isinstance(pos, dict) else 0.0,
        aim_length=float(args.get("aimLength", 0.0)),
        action="activate", raw_data=args,
    )


def _air_support_deactivate(pkt: Packet) -> AirSupportEvent:
    """deactivateAirSupport(index, squadronID)."""
    args = pkt.method_args or {}
    return AirSupportEvent(
        timestamp=pkt.timestamp, entity_id=pkt.entity_id,
        index=int(args.get("index", 0)),
        plane_id=int(args.get("squadronID", 0)),
        action="deactivate", raw_data=args,
    )


# ── Combat factory functions ─────────────────────────────────────


def _gun_fire(pkt: Packet) -> GunFireEvent:
    """shootOnClient(arg0: weapon_type, arg1: gun_bits)."""
    args = pkt.method_args or {}
    return GunFireEvent(
        timestamp=pkt.timestamp,
        entity_id=pkt.entity_id,
        weapon_type=int(_get(args, "arg0", 0)),
        gun_bits=int(_get(args, "arg1", 0)),
        raw_data=args,
    )


def _secondary_fire(pkt: Packet) -> SecondaryFireEvent:
    """shootATBAGuns(arg0: weapon_type, arg1: gun_bits)."""
    args = pkt.method_args or {}
    return SecondaryFireEvent(
        timestamp=pkt.timestamp,
        entity_id=pkt.entity_id,
        weapon_type=int(_get(args, "arg0", 0)),
        gun_bits=int(_get(args, "arg1", 0)),
        raw_data=args,
    )


def _gun_state(pkt: Packet) -> GunStateEvent:
    """syncGun(weapon_type, gun_id, yaw, pitch, alive, reload_perc, loaded_ammo)."""
    args = pkt.method_args or {}
    return GunStateEvent(
        timestamp=pkt.timestamp,
        entity_id=pkt.entity_id,
        weapon_type=int(_get(args, "arg0", 0)),
        gun_id=int(_get(args, "arg1", 0)),
        yaw=float(_get(args, "arg2", 0.0)),
        pitch=float(_get(args, "arg3", 0.0)),
        alive=bool(_get(args, "arg4", True)),
        reload_perc=float(_get(args, "arg5", 0.0)),
        loaded_ammo=int(_get(args, "arg6", 0)),
        raw_data=args,
    )


def _torpedo_tube_state(pkt: Packet) -> TorpedoTubeStateEvent:
    """syncTorpedoTube(arg0: gun_id, arg1: yaw, arg2: pitch, arg3: alive, arg4: reload_perc, arg5: state)."""
    args = pkt.method_args or {}
    return TorpedoTubeStateEvent(
        timestamp=pkt.timestamp,
        entity_id=pkt.entity_id,
        gun_id=int(_get(args, "arg0", 0)),
        yaw=float(_get(args, "arg1", 0.0)),
        pitch=float(_get(args, "arg2", 0.0)),
        alive=bool(_get(args, "arg3", True)),
        reload_perc=float(_get(args, "arg4", 0.0)),
        state=int(_get(args, "arg5", 0)),
        raw_data=args,
    )


def _torpedo_spread(pkt: Packet) -> TorpedoSpreadEvent:
    """syncTorpedoState(arg0: state)."""
    args = pkt.method_args or {}
    return TorpedoSpreadEvent(
        timestamp=pkt.timestamp,
        entity_id=pkt.entity_id,
        state=int(_get(args, "arg0", 0)),
        raw_data=args,
    )


def _ammo_switch(pkt: Packet) -> AmmoSwitchEvent:
    """setAmmoForWeapon(arg0: weapon_type, arg1: ammo_params_id, arg2: is_reload)."""
    args = pkt.method_args or {}
    return AmmoSwitchEvent(
        timestamp=pkt.timestamp,
        entity_id=pkt.entity_id,
        weapon_type=int(_get(args, "arg0", 0)),
        ammo_params_id=int(_get(args, "arg1", 0)),
        is_reload=bool(_get(args, "arg2", False)),
        raw_data=args,
    )


def _weapon_state_switch(pkt: Packet) -> WeaponStateSwitchEvent:
    """onWeaponStateSwitched(arg0: weapon_type, arg1: new_state)."""
    args = pkt.method_args or {}
    return WeaponStateSwitchEvent(
        timestamp=pkt.timestamp,
        entity_id=pkt.entity_id,
        weapon_type=int(_get(args, "arg0", 0)),
        new_state=int(_get(args, "arg1", 0)),
        raw_data=args,
    )


def _torpedo_launch(pkt: Packet) -> TorpedoLaunchEvent:
    """shootTorpedo(arg0: id, arg1: VECTOR3 position, arg2: id2, arg3: id3, arg4: flag)."""
    args = pkt.method_args or {}
    pos = args.get("arg1") or {}
    if isinstance(pos, dict):
        px = float(pos.get("x", 0))
        py = float(pos.get("y", 0))
        pz = float(pos.get("z", 0))
    else:
        px, py, pz = 0.0, 0.0, 0.0
    return TorpedoLaunchEvent(
        timestamp=pkt.timestamp,
        entity_id=pkt.entity_id,
        id=int(_get(args, "arg0", 0)),
        position=(px, py, pz),
        id2=int(_get(args, "arg2", 0)),
        id3=int(_get(args, "arg3", 0)),
        flag=bool(_get(args, "arg4", False)),
        raw_data=args,
    )


def _depth_charge_launch(pkt: Packet) -> DepthChargeLaunchEvent:
    """shootDepthCharge(arg0: id, arg1: count)."""
    args = pkt.method_args or {}
    return DepthChargeLaunchEvent(
        timestamp=pkt.timestamp,
        entity_id=pkt.entity_id,
        id=int(_get(args, "arg0", 0)),
        count=int(_get(args, "arg1", 0)),
        raw_data=args,
    )


def _gun_rotation_sync(pkt: Packet) -> GunRotationSyncEvent:
    """receiveGunSyncRotations(arg0: weapon_type, arg1: gun_directions)."""
    args = pkt.method_args or {}
    return GunRotationSyncEvent(
        timestamp=pkt.timestamp,
        entity_id=pkt.entity_id,
        weapon_type=int(_get(args, "arg0", 0)),
        gun_directions=_get(args, "arg1"),
        raw_data=args,
    )


def _respawn(pkt: Packet) -> RespawnEvent:
    """onRespawned(arg0: reset_consumables_count, arg1: initial_speed, arg2: yaw)."""
    args = pkt.method_args or {}
    return RespawnEvent(
        timestamp=pkt.timestamp,
        entity_id=pkt.entity_id,
        reset_consumables_count=int(_get(args, "arg0", 0)),
        initial_speed=float(_get(args, "arg1", 0.0)),
        yaw=float(_get(args, "arg2", 0.0)),
        raw_data=args,
    )


def _rage_mode(pkt: Packet) -> RageModeEvent:
    """syncRageMode(arg0: hit_counter, arg1: state, arg2: state_time_passed)."""
    args = pkt.method_args or {}
    return RageModeEvent(
        timestamp=pkt.timestamp,
        entity_id=pkt.entity_id,
        hit_counter=int(_get(args, "arg0", 0)),
        state=int(_get(args, "arg1", 0)),
        state_time_passed=float(_get(args, "arg2", 0.0)),
        raw_data=args,
    )


def _weapon_reload_state(pkt: Packet) -> WeaponReloadStateEvent:
    """setReloadingStateForWeapon(arg0: weapon_type, arg1: state_blob)."""
    args = pkt.method_args or {}
    return WeaponReloadStateEvent(
        timestamp=pkt.timestamp,
        entity_id=pkt.entity_id,
        weapon_type=int(_get(args, "arg0", 0)),
        raw_data=args,
    )


def _ship_physics(pkt: Packet) -> ShipPhysicsEvent:
    """syncShipPhysics(arg0: state_id, arg1: blob)."""
    args = pkt.method_args or {}
    return ShipPhysicsEvent(
        timestamp=pkt.timestamp,
        entity_id=pkt.entity_id,
        state_id=int(_get(args, "arg0", 0)),
        raw_data=args,
    )


def _mirror_damage(pkt: Packet) -> MirrorDamageEvent:
    """receiveMirrorDamage(arg0: damage)."""
    args = pkt.method_args or {}
    return MirrorDamageEvent(
        timestamp=pkt.timestamp,
        entity_id=pkt.entity_id,
        damage=float(_get(args, "arg0", 0.0)),
        raw_data=args,
    )


# ── Phase 5 factory functions ────────────────────────────────────

# 5a: Consumable events

def _consumable_selected(pkt: Packet) -> ConsumableSelectedEvent:
    """onConsumableSelected(arg0: consumable_type, arg1: is_selected)."""
    args = pkt.method_args or {}
    return ConsumableSelectedEvent(
        timestamp=pkt.timestamp,
        entity_id=pkt.entity_id,
        consumable_type=int(_get(args, "arg0", 0)),
        is_selected=bool(_get(args, "arg1", False)),
        raw_data=args,
    )


def _consumable_enabled(pkt: Packet) -> ConsumableEnabledEvent:
    """onConsumableEnabled(arg0: consumable_id, arg1: enabled)."""
    args = pkt.method_args or {}
    return ConsumableEnabledEvent(
        timestamp=pkt.timestamp,
        entity_id=pkt.entity_id,
        consumable_id=int(_get(args, "arg0", 0)),
        enabled=bool(_get(args, "arg1", False)),
        raw_data=args,
    )


def _consumable_paused(pkt: Packet) -> ConsumablePausedEvent:
    """onConsumablePaused(arg0: consumable_type)."""
    args = pkt.method_args or {}
    return ConsumablePausedEvent(
        timestamp=pkt.timestamp,
        entity_id=pkt.entity_id,
        consumable_type=int(_get(args, "arg0", 0)),
        raw_data=args,
    )


# 5b: Avatar combat methods (small factories only — rest use _generic)

def _missile_waypoint(pkt: Packet) -> MissileWaypointEvent:
    """updateMissileWaypoints(arg0: shot_id, ...)."""
    args = pkt.method_args or {}
    return MissileWaypointEvent(
        timestamp=pkt.timestamp,
        entity_id=pkt.entity_id,
        shot_id=int(_get(args, "arg0", 0)),
        raw_data=args,
    )


def _missile_damage(pkt: Packet) -> MissileDamageEvent:
    """receiveMissileDamage(arg0: shot_id, arg1: damager_id, arg2: damage)."""
    args = pkt.method_args or {}
    return MissileDamageEvent(
        timestamp=pkt.timestamp,
        entity_id=pkt.entity_id,
        shot_id=int(_get(args, "arg0", 0)),
        damager_id=int(_get(args, "arg1", 0)),
        damage=float(_get(args, "arg2", 0.0)),
        raw_data=args,
    )


def _missile_impact(pkt: Packet) -> MissileImpactEvent:
    """receiveMissileKill(arg0: shot_id, ...)."""
    args = pkt.method_args or {}
    return MissileImpactEvent(
        timestamp=pkt.timestamp,
        entity_id=pkt.entity_id,
        shot_id=int(_get(args, "arg0", 0)),
        raw_data=args,
    )


def _torpedo_armed(pkt: Packet) -> TorpedoArmedEvent:
    """receiveTorpedoArmed(arg0: torpedo_id, arg1: armed_state)."""
    args = pkt.method_args or {}
    return TorpedoArmedEvent(
        timestamp=pkt.timestamp,
        entity_id=pkt.entity_id,
        torpedo_id=int(_get(args, "arg0", 0)),
        armed_state=int(_get(args, "arg1", 0)),
        raw_data=args,
    )


# 5c: Submarine/sonar

def _sonar_ping(pkt: Packet) -> SonarPingEvent:
    """receivePingerShot(arg0: weapon_type, arg1: gun_id, arg2: yaw)."""
    args = pkt.method_args or {}
    return SonarPingEvent(
        timestamp=pkt.timestamp,
        entity_id=pkt.entity_id,
        weapon_type=int(_get(args, "arg0", 0)),
        gun_id=int(_get(args, "arg1", 0)),
        yaw=float(_get(args, "arg2", 0.0)),
        raw_data=args,
    )


def _sonar_reset(pkt: Packet) -> SonarResetEvent:
    """resetPinger(arg0: weapon_type)."""
    args = pkt.method_args or {}
    return SonarResetEvent(
        timestamp=pkt.timestamp,
        entity_id=pkt.entity_id,
        weapon_type=int(_get(args, "arg0", 0)),
        raw_data=args,
    )


def _sub_surfacing(pkt: Packet) -> SubSurfacingEvent:
    """syncSurfacingTime(arg0: time)."""
    args = pkt.method_args or {}
    return SubSurfacingEvent(
        timestamp=pkt.timestamp,
        entity_id=pkt.entity_id,
        time=int(_get(args, "arg0", 0)),
        raw_data=args,
    )


# 5d: AA/priority sector

def _aa_sector(pkt: Packet) -> AASectorEvent:
    """onPrioritySectorSet(arg0: sector_id, arg1: reinforcement_progress)."""
    args = pkt.method_args or {}
    return AASectorEvent(
        timestamp=pkt.timestamp,
        entity_id=pkt.entity_id,
        sector_id=int(_get(args, "arg0", 0)),
        reinforcement_progress=float(_get(args, "arg1", 0.0)),
        raw_data=args,
    )


def _aa_sector_queue(pkt: Packet) -> AASectorQueueEvent:
    """onNextPrioritySectorSet(arg0: sector_id)."""
    args = pkt.method_args or {}
    return AASectorQueueEvent(
        timestamp=pkt.timestamp,
        entity_id=pkt.entity_id,
        sector_id=int(_get(args, "arg0", 0)),
        raw_data=args,
    )


# 5f: Game state methods (small factories only — rest use _generic)

def _shutdown_time(pkt: Packet) -> ShutdownTimeEvent:
    """onShutdownTime(arg0: shutdown_type, arg1: time_remaining, arg2: flags)."""
    args = pkt.method_args or {}
    return ShutdownTimeEvent(
        timestamp=pkt.timestamp,
        entity_id=pkt.entity_id,
        shutdown_type=int(_get(args, "arg0", 0)),
        time_remaining=float(_get(args, "arg1", 0.0)),
        flags=int(_get(args, "arg2", 0)),
        raw_data=args,
    )


def _pre_battle_grants(pkt: Packet) -> PreBattleGrantsEvent:
    """changePreBattleGrants(arg0: grants)."""
    args = pkt.method_args or {}
    return PreBattleGrantsEvent(
        timestamp=pkt.timestamp,
        entity_id=pkt.entity_id,
        grants=int(_get(args, "arg0", 0)),
        raw_data=args,
    )


# 5g: Vehicle one-shot methods

def _owner_changed(pkt: Packet) -> OwnerChangedEvent:
    """onOwnerChanged(arg0: owner_id, arg1: is_owner)."""
    args = pkt.method_args or {}
    return OwnerChangedEvent(
        timestamp=pkt.timestamp,
        entity_id=pkt.entity_id,
        owner_id=int(_get(args, "arg0", 0)),
        is_owner=bool(_get(args, "arg1", False)),
        raw_data=args,
    )


# Method name → factory function
_METHOD_FACTORIES: dict[str, Callable[[Packet], GameEvent | list[GameEvent]]] = {
    "receiveVehicleDeath": _death_from_receive_vehicle_death,
    "receiveShellInfo": _damage_from_receive_shell_info,
    "receiveArtilleryShots": _shots_created,  # type: ignore[dict-item]
    "receiveTorpedoes": _torpedoes_created,  # type: ignore[dict-item]
    "receiveShotKills": _shots_destroyed,  # type: ignore[dict-item]
    "onChatMessage": _chat,
    "receiveDamagesOnShip": _damage_from_receive_damages,  # type: ignore[dict-item]
    "kill": _death_from_vehicle_kill,
    "onConsumableUsed": _consumable,
    "onAchievementEarned": _achievement,
    # Minimap vision
    "updateMinimapVisionInfo": _minimap_vision_info,  # type: ignore[dict-item]
    # receiveDamageStat: handled separately in EventStream (stateful)
    "receive_CommonCMD": _generic(RawEvent),
    # Squadrons
    "receive_addMinimapSquadron": _squadron_add,
    "receive_updateMinimapSquadron": _squadron_update,
    "receive_removeMinimapSquadron": _squadron_remove,
    "receive_removeSquadron": _squadron_remove,
    "receive_deactivateSquadron": _squadron_deactivate,
    # Air support
    "activateAirSupport": _air_support_activate,
    "deactivateAirSupport": _air_support_deactivate,
    # Combat
    "shootOnClient": _gun_fire,
    "shootATBAGuns": _secondary_fire,
    "syncGun": _gun_state,
    "syncTorpedoTube": _torpedo_tube_state,
    "syncTorpedoState": _torpedo_spread,
    "setAmmoForWeapon": _ammo_switch,
    "onWeaponStateSwitched": _weapon_state_switch,
    "shootTorpedo": _torpedo_launch,
    "shootDepthCharge": _depth_charge_launch,
    "receiveGunSyncRotations": _gun_rotation_sync,
    "receiveHitLocationStateChange": _generic(ModuleDamageEvent),
    "setReloadingStateForWeapon": _weapon_reload_state,
    "syncShipCracks": _generic(ShipCracksEvent),
    "syncShipPhysics": _ship_physics,
    "startDissapearing": _generic(ShipDisappearEvent),
    "onRespawned": _respawn,
    "onCrashCrewEnable": _generic(DamageControlStartEvent),
    "onCrashCrewDisable": _generic(DamageControlEndEvent),
    "syncRageMode": _rage_mode,
    "receiveMirrorDamage": _mirror_damage,
    # Consumables
    "onConsumableSelected": _consumable_selected,
    "onConsumableEnabled": _consumable_enabled,
    "onConsumablePaused": _consumable_paused,
    # Avatar combat
    "receiveExplosions": _generic(ExplosionEvent),
    "receiveMissile": _generic(MissileLaunchEvent),
    "updateMissileWaypoints": _missile_waypoint,
    "receiveMissileDamage": _missile_damage,
    "receiveMissileKill": _missile_impact,
    "receivePlaneProjectilePack": _generic(PlaneProjectileEvent),
    "receivePlaneSkipBombPacks": _generic(SkipBombEvent),
    "receivePlaneRocketPacks": _generic(RocketEvent),
    "receiveDepthChargesPacks": _generic(DepthChargeEvent),
    "receiveLaserBeams": _generic(LaserBeamEvent),
    "updateOwnerlessTracersPosition": _generic(TracerPositionEvent),
    "beginOwnerlessTracers": _generic(TracerStartEvent),
    "endOwnerlessTracers": _generic(TracerEndEvent),
    "receiveTorpedoSynchronization": _generic(TorpedoSyncEvent),
    "receiveTorpedoArmed": _torpedo_armed,
    # Submarine
    "receivePingerShot": _sonar_ping,
    "resetPinger": _sonar_reset,
    "onPingerWaveEnemyHit": _generic(SonarHitEvent),
    "receiveWaveFromEnemy": _generic(SonarWaveReceivedEvent),
    "updateWaveEnemyHit": _generic(SonarHitUpdateEvent),
    "updateInvisibleWavedPoint": _generic(SonarDetectionEvent),
    "addSubmarineHydrophoneTargets": _generic(HydrophoneTargetEvent),
    "syncSurfacingTime": _sub_surfacing,
    # AA
    "onPrioritySectorSet": _aa_sector,
    "onNextPrioritySectorSet": _aa_sector_queue,
    "updateOwnerlessAuraState": _generic(AAAuraStateEvent),
    "setAirDefenseState": _generic(AirDefenseStateEvent),
    # Squadrons
    "receive_addSquadron": _generic(SquadronSpawnEvent),
    "receive_updateSquadron": _generic(SquadronUpdateDetailEvent),
    "receive_changeState": _generic(SquadronStateChangeEvent),
    "receive_squadronHealth": _generic(SquadronHealthEvent),
    "receive_squadronPlanesHealth": _generic(SquadronPlaneHealthEvent),
    "receive_planeDeath": _generic(PlaneDeathEvent),
    "receive_squadronVisibilityChanged": _generic(SquadronVisibilityEvent),
    "receive_stopManeuvering": _generic(SquadronStopManeuverEvent),
    "receive_resetWaypoints": _generic(SquadronWaypointResetEvent),
    "receive_refresh": _generic(SquadronRefreshEvent),
    # Game state
    "onGameRoomStateChanged": _generic(GameRoomStateEvent),
    "updateCoolDown": _generic(CooldownUpdateEvent),
    "updatePreBattlesInfo": _generic(PreBattleUpdateEvent),
    "onConnected": _generic(ConnectedEvent),
    "onEnterPreBattle": _generic(PreBattleEnterEvent),
    "receiveAvatarInfo": _generic(AvatarInfoEvent),
    "receivePlayerData": _generic(PlayerDataEvent),
    "onNewPlayerSpawned": _generic(PlayerSpawnedEvent),
    "onBattleEnd": _generic(BattleEndEvent),
    "onShutdownTime": _shutdown_time,
    "setUniqueSkills": _generic(UniqueSkillsEvent),
    "receiveChatHistory": _generic(ChatHistoryEvent),
    "onWorldStateReceived": _generic(WorldStateReceivedEvent),
    "changePreBattleGrants": _pre_battle_grants,
    "uniqueTriggerActivated": _generic(UniqueTriggerEvent),
    "resetResettableWaveEnemyHits": _generic(WaveResetEvent),
    # Vehicle one-shot
    "onOwnerChanged": _owner_changed,
    "setConsumables": _generic(ConsumablesSetEvent),
    "receiveHitLocationsInitialState": _generic(HitLocationsInitEvent),
    "teleport": _generic(TeleportEvent),
}


_NOISE_METHODS: frozenset[str] = frozenset({
    "onCheckGamePing",
    "onCheckCellPing",
})


_AMMO_TYPE_MAP: dict[str, str] = {
    "AP": "AP",
    "HE": "HE",
    "CS": "SAP",  # Common Shell = SAP
    "torpedo": "torpedo",
    "torpedo_alternative": "torpedo",
    "torpedo_deepwater": "torpedo",
    "depthcharge": "depth_charge",
    "missile": "missile",
}


def _build_ammo_lookup(gamedata_path: str | Path | None) -> dict[int, str]:
    """Build GAMEPARAMS_ID → damage_type string from projectiles.json.

    projectiles.json is a compact lookup: {id_str: {"a": ammoType, "c": caliber}}.
    Searched in data/ dir and sibling wows-gamedata repo.
    """
    if gamedata_path is None:
        return {}
    # gamedata_path is entity_defs dir: .../data/scripts_entity/entity_defs
    gp = Path(gamedata_path).resolve()
    data_dir = gp.parent.parent  # .../data/
    repo_root = data_dir.parent  # .../wows-gamedata/
    candidates = [
        data_dir / "projectiles.json",
        repo_root.parent / "wows-gamedata" / "data" / "projectiles.json",
    ]
    proj_file = next((c for c in candidates if c.is_file()), None)
    if proj_file is None:
        return {}
    try:
        raw = json.loads(proj_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    lookup: dict[int, str] = {}
    for gp_id_str, info in raw.items():
        ammo_type = info.get("a", "") if isinstance(info, dict) else ""
        if ammo_type:
            lookup[int(gp_id_str)] = _AMMO_TYPE_MAP.get(ammo_type, ammo_type)
    return lookup


# DamageStatWeapon: from mc15a2792.pyc enum_weapon, game version 15.1
_DAMAGE_STAT_WEAPONS: dict[int, str] = {
    0: "DEFAULT", 1: "MAIN_AP", 2: "MAIN_HE", 3: "ATBA_AP", 4: "ATBA_HE",
    5: "MAIN_AI_AP", 6: "MAIN_AI_HE", 7: "TORPEDO", 8: "ANTIAIR", 9: "SCOUT",
    10: "BOMBER_AP", 11: "BOMBER_HE", 12: "TBOMBER", 13: "FIGHTER",
    14: "SFIGHTER", 15: "TURRET", 16: "SPOT", 17: "BURN", 18: "RAM",
    19: "TERRAIN", 20: "FLOOD", 21: "MIRROR", 22: "RADAR", 23: "XRAY",
    24: "CONS_SPOT", 25: "SEA_MINE", 26: "FEL", 27: "DEPTH_CHARGE",
    28: "ROCKET_HE", 29: "AA_NEAR", 30: "AA_MEDIUM", 31: "AA_FAR",
    32: "MAIN_CS", 33: "ATBA_CS", 34: "PORTAL", 35: "TORPEDO_ACC",
    36: "TORPEDO_MAG", 37: "PING", 38: "PING_SLOW", 39: "PING_FAST",
    40: "TORPEDO_ACC_OFF", 41: "ROCKET_AP", 42: "SKIP_HE", 43: "SKIP_AP",
    44: "ACID", 45: "SECTOR_WAVE", 46: "MATCH", 47: "TIMER",
    48: "CHARGE_LASER", 49: "PULSE_LASER", 50: "AXIS_LASER",
    51: "BOMBER_AP_ASUP", 52: "BOMBER_HE_ASUP", 53: "TBOMBER_ASUP",
    54: "ROCKET_HE_ASUP", 55: "ROCKET_AP_ASUP", 56: "SKIP_HE_ASUP",
    57: "SKIP_AP_ASUP", 58: "DEPTH_CHARGE_ASUP", 59: "TORPEDO_DEEP",
    60: "TORPEDO_ALTER", 61: "AIR_SUPPORT", 62: "BOMBER_AP_ALTER",
    63: "BOMBER_HE_ALTER", 64: "TBOMBER_ALTER", 65: "ROCKET_HE_ALTER",
    66: "ROCKET_AP_ALTER", 67: "SKIP_HE_ALTER", 68: "SKIP_AP_ALTER",
    69: "DEPTH_CHARGE_ALTER", 70: "RECON", 71: "BOMBER_AP_TC",
    72: "BOMBER_HE_TC", 73: "TBOMBER_TC", 74: "ROCKET_HE_TC",
    75: "ROCKET_AP_TC", 76: "SKIP_HE_TC", 77: "SKIP_AP_TC",
    78: "DEPTH_CHARGE_TC", 79: "PHASER_LASER", 80: "EVENT1", 81: "EVENT2",
    82: "TORPEDO_PHOTON", 83: "MISSILE", 84: "ANTI_MISSILE",
}

# DamageStatCategory: from DamageStatsType in mc15a2792.pyc, game version 15.1
_DAMAGE_STAT_CATEGORIES: dict[int, str] = {
    0: "ENEMY", 1: "ALLY", 2: "SPOT", 3: "AGRO",
}


class EventStream:
    """Converts packets into typed game events."""

    def __init__(
        self,
        tracker: GameStateTracker | None = None,
        gamedata_path: str | Path | None = None,
    ) -> None:
        self._tracker = tracker
        self._ammo_lookup = _build_ammo_lookup(gamedata_path)
        # State for receiveDamageStat delta computation
        self._prev_damage_stat: dict[tuple[int, int], tuple[float, float]] = {}

    def process(self, packets: list[Packet]) -> list[GameEvent]:
        """Process all packets into game events."""
        events: list[GameEvent] = []
        for packet in packets:
            result = self._to_event(packet)
            events.extend(result)
        # Enrich DamageEvents with damage_type from ammo lookup
        if self._ammo_lookup:
            for event in events:
                if isinstance(event, DamageEvent) and event.ammo_id and not event.damage_type:
                    dtype = self._ammo_lookup.get(event.ammo_id)
                    if dtype:
                        event.damage_type = dtype
        return events

    def _to_event(self, packet: Packet) -> list[GameEvent]:
        """Convert a single packet to game event(s)."""
        # Position packets
        if packet.type == PacketType.POSITION:
            if packet.position is None:
                return []
            x, y, z = packet.position
            dx, dy, dz = 0.0, 0.0, 0.0
            rx, ry, rz = 0.0, 0.0, 0.0
            yaw = 0.0
            if packet.direction:
                dx, dy, dz = packet.direction
                yaw = math.atan2(dx, dz)
            if packet.rotation:
                rx, ry, rz = packet.rotation
            speed = 0.0
            is_alive = True
            if self._tracker:
                props = self._tracker.get_entity_props(
                    packet.entity_id,
                )
                raw_speed = props.get("serverSpeedRaw", 0)
                speed = float(raw_speed) if raw_speed is not None else 0.0
                raw_alive = props.get("isAlive", True)
                is_alive = bool(raw_alive) if raw_alive is not None else True
            return [PositionEvent(
                timestamp=packet.timestamp,
                entity_id=packet.entity_id,
                x=x, y=y, z=z, yaw=yaw,
                direction_x=dx, direction_y=dy, direction_z=dz,
                rotation_x=rx, rotation_y=ry, rotation_z=rz,
                is_on_ground=packet.is_on_ground,
                speed=speed,
                is_alive=is_alive,
            )]

        # Property update packets
        elif packet.is_property_update:
            if not packet.property_name:
                return [RawEvent(
                    timestamp=packet.timestamp,
                    entity_id=packet.entity_id,
                    packet_type=int(packet.type),
                    property_name="",
                )]
            result: list[GameEvent] = []
            entity_type = packet.entity_type or ""
            result.append(PropertyUpdateEvent(
                timestamp=packet.timestamp,
                entity_id=packet.entity_id,
                entity_type=entity_type,
                property_name=packet.property_name,
                value=packet.property_value,
                raw_data={
                    "property_name": packet.property_name,
                    "property_value": packet.property_value,
                },
            ))
            # InteractiveZone → CapturePointUpdateEvent
            if entity_type == "InteractiveZone":
                result.extend(
                    self._cap_point_events(packet)
                )
            # BattleLogic → ScoreUpdateEvent
            if entity_type == "BattleLogic":
                result.extend(
                    self._score_events(packet)
                )
            # Vehicle.triggeredSkillsData → SkillActivationEvent
            if (
                entity_type == "Vehicle"
                and packet.property_name == "triggeredSkillsData"
                and packet.property_value is not None
            ):
                result.append(SkillActivationEvent(
                    timestamp=packet.timestamp,
                    entity_id=packet.entity_id,
                    vehicle_id=packet.entity_id,
                    active_skills=packet.property_value,
                    raw_data={
                        "property_name": "triggeredSkillsData",
                        "active_skills": packet.property_value,
                    },
                ))
            return result

        # Method call packets
        elif packet.is_method_call and packet.method_name:
            # Stateful handler for receiveDamageStat (needs delta tracking)
            if packet.method_name == "receiveDamageStat":
                return self._damage_stat_events(packet)
            factory = _METHOD_FACTORIES.get(packet.method_name)
            if factory is not None:
                out = factory(packet)
                if isinstance(out, list):
                    return out
                return [out]
            if packet.method_name in _NOISE_METHODS:
                return []
            # Unknown method → RawEvent
            return [RawEvent(
                timestamp=packet.timestamp,
                entity_id=packet.entity_id,
                packet_type=int(packet.type),
                method_name=packet.method_name or "",
                raw_data=packet.method_args or {},
            )]

        # BattleResults (0x22) — post-battle statistics
        elif packet.type == PacketType.BATTLE_RESULTS:
            data = getattr(packet, "battle_results_data", None)
            if isinstance(data, dict):
                return [BattleResultsEvent(
                    timestamp=packet.timestamp,
                    entity_id=packet.entity_id,
                    results=data,
                )]
            return []

        # EntityLeave (0x04) — entity left Area of Interest
        elif packet.type == PacketType.ENTITY_LEAVE:
            return [EntityLeaveEvent(
                timestamp=packet.timestamp,
                entity_id=packet.entity_id,
            )]

        # CruiseState (0x32) — cruise control state update
        elif packet.type == PacketType.CRUISE_STATE:
            return [CruiseStateEvent(
                timestamp=packet.timestamp,
                entity_id=packet.entity_id,
                state=getattr(packet, "cruise_state", None) or 0,
                value=getattr(packet, "cruise_value", None) or 0,
            )]

        # SetWeaponLock (0x30) — weapon lock state
        elif packet.type == PacketType.SET_WEAPON_LOCK:
            return [WeaponLockEvent(
                timestamp=packet.timestamp,
                entity_id=packet.entity_id,
                flags=getattr(packet, "weapon_lock_flags", None) or 0,
                target_id=getattr(packet, "weapon_lock_target", None) or 0,
            )]

        # CameraMode (0x27) — camera mode change
        elif packet.type == PacketType.CAMERA_MODE:
            return [CameraModeEvent(
                timestamp=packet.timestamp,
                entity_id=packet.entity_id,
                mode=getattr(packet, "camera_mode", None) or 0,
            )]

        # ShotTracking (0x33) — shot tracking update
        elif packet.type == PacketType.SHOT_TRACKING:
            return [ShotTrackingEvent(
                timestamp=packet.timestamp,
                entity_id=packet.entity_id,
                tracking_entity=getattr(packet, "shot_tracking_entity", None) or 0,
                weapon_id=getattr(packet, "shot_tracking_weapon", None) or 0,
                value=getattr(packet, "shot_tracking_value", None) or 0,
            )]

        # All other packet types (entity creation, camera, etc.)
        return []

    def _damage_stat_events(self, packet: Packet) -> list[DamageReceivedStatEvent]:
        """Convert receiveDamageStat cumulative snapshot into delta events.

        Payload: {(param_id, stat_type): [count, total_damage]}
        The target is always self (the replay player's Avatar).
        """
        args = packet.method_args or {}
        stat_dict = args.get("arg0")
        if not isinstance(stat_dict, dict):
            return []

        # Resolve own vehicle ID for entity_id on events
        own_vehicle = (
            self._tracker.own_vehicle_id if self._tracker else None
        ) or packet.entity_id

        events: list[DamageReceivedStatEvent] = []
        for (param_id, stat_type_id), values in stat_dict.items():
            if not isinstance(values, (list, tuple)) or len(values) < 2:
                continue
            count, total = float(values[0]), float(values[1])
            key = (int(param_id), int(stat_type_id))

            prev_count, prev_total = self._prev_damage_stat.get(key, (0.0, 0.0))
            delta_count = count - prev_count
            delta_total = total - prev_total
            self._prev_damage_stat[key] = (count, total)

            # Skip entries with no new damage this tick
            if delta_count == 0 and delta_total == 0.0:
                continue

            param_name = _DAMAGE_STAT_WEAPONS.get(
                param_id, f"unknown_{param_id}",
            )
            stat_name = _DAMAGE_STAT_CATEGORIES.get(
                stat_type_id, f"unknown_{stat_type_id}",
            )

            events.append(DamageReceivedStatEvent(
                timestamp=packet.timestamp,
                entity_id=own_vehicle,
                damage_param=param_name,
                stat_type=stat_name,
                delta_count=int(delta_count),
                delta_total=delta_total,
                cumulative_count=int(count),
                cumulative_total=total,
                raw_data=args,
            ))
        return events

    def _cap_point_events(
        self, packet: Packet,
    ) -> list[CapturePointUpdateEvent]:
        """Extract CapturePointUpdateEvent from InteractiveZone property updates."""
        if packet.property_name not in (
            "componentsState", "teamId", "radius",
        ):
            return []
        props: dict[str, Any] = {}
        if self._tracker:
            props = self._tracker.get_entity_props(
                packet.entity_id,
            )
        cs = props.get("componentsState", {})
        cap_logic: dict[str, Any] = {}
        if isinstance(cs, dict):
            cap_logic = cs.get("captureLogic") or {}
        return [CapturePointUpdateEvent(
            timestamp=packet.timestamp,
            entity_id=packet.entity_id,
            zone_entity_id=packet.entity_id,
            team_id=int(props.get("teamId", 0)),
            radius=float(props.get("radius", 0)),
            progress=(
                float(cap_logic.get("progress", 0))
                if isinstance(cap_logic, dict) else 0.0
            ),
            capture_speed=(
                float(cap_logic.get("captureSpeed", 0))
                if isinstance(cap_logic, dict) else 0.0
            ),
            invader_team=(
                int(cap_logic.get("invaderTeam", 0))
                if isinstance(cap_logic, dict) else 0
            ),
            has_invaders=(
                bool(cap_logic.get("hasInvaders", False))
                if isinstance(cap_logic, dict) else False
            ),
        )]

    def _score_events(
        self, packet: Packet,
    ) -> list[ScoreUpdateEvent]:
        """Extract ScoreUpdateEvent from BattleLogic property updates."""
        if packet.property_name not in (
            "teams", "timeLeft", "battleStage", "battleResult",
        ):
            return []
        props: dict[str, Any] = {}
        if self._tracker:
            props = self._tracker.get_entity_props(
                packet.entity_id,
            )
        return [ScoreUpdateEvent(
            timestamp=packet.timestamp,
            entity_id=packet.entity_id,
            battle_stage=int(props.get("battleStage", 0)),
            time_left=int(props.get("timeLeft", 0)),
            teams=props.get("teams"),
        )]
