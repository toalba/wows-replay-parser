"""
Transforms decoded packets into typed game events.

Maps specific entity method calls to semantic event types.
This is the layer where we go from "Avatar called method 'receiveVehicleDeath'
with args {arg0: 123, arg1: 456, arg2: 2}" to a typed DeathEvent.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from wows_replay_parser.state.tracker import GameStateTracker

from wows_replay_parser.events.models import (
    AchievementEvent,
    CapContestEvent,
    CapturePointUpdateEvent,
    ChatEvent,
    ConsumableEvent,
    DamageEvent,
    DeathEvent,
    GameEvent,
    PositionEvent,
    PotentialDamageEvent,
    PropertyUpdateEvent,
    RawEvent,
    ScoreUpdateEvent,
    ScoutingDamageEvent,
    ShotCreatedEvent,
    ShotDestroyedEvent,
    TorpedoCreatedEvent,
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
            damage=float(entry.get("damage", 0) or 0),
            raw_data=entry,
        ))
    return events if events else [DamageEvent(
        timestamp=pkt.timestamp,
        entity_id=pkt.entity_id,
        target_id=pkt.entity_id,
        raw_data=args,
    )]


def _chat(pkt: Packet) -> ChatEvent:
    """onChatMessage(0:PLAYER_ID sender, 1:STRING channel, 2:STRING body, 3:STRING extra)"""
    args = pkt.method_args or {}
    return ChatEvent(
        timestamp=pkt.timestamp,
        entity_id=pkt.entity_id,
        sender_id=_get(args, "arg0"),
        channel=_get(args, "arg1", ""),
        message=_get(args, "arg2", ""),
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


def _potential_damage(pkt: Packet) -> PotentialDamageEvent:
    """receiveDamageStat or similar — potential damage / agro points."""
    args = pkt.method_args or {}
    return PotentialDamageEvent(
        timestamp=pkt.timestamp,
        entity_id=pkt.entity_id,
        attacker_id=_get(args, "arg0", 0),
        victim_id=_get(args, "arg1", 0),
        agro_points=float(_get(args, "arg2", 0) or 0),
        raw_data=args,
    )


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
    # Stats events — matched if the method exists in the .def files
    "receiveDamageStat": _potential_damage,
    "receive_CommonCMD": _generic(RawEvent),
}


class EventStream:
    """Converts packets into typed game events."""

    def __init__(self, tracker: GameStateTracker | None = None) -> None:
        self._tracker = tracker

    def process(self, packets: list[Packet]) -> list[GameEvent]:
        """Process all packets into game events."""
        events: list[GameEvent] = []
        for packet in packets:
            result = self._to_event(packet)
            events.extend(result)
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
            return result

        # Method call packets
        elif packet.is_method_call and packet.method_name:
            factory = _METHOD_FACTORIES.get(packet.method_name)
            if factory is not None:
                out = factory(packet)
                if isinstance(out, list):
                    return out
                return [out]
            # Unknown method → RawEvent
            return [RawEvent(
                timestamp=packet.timestamp,
                entity_id=packet.entity_id,
                packet_type=int(packet.type),
                method_name=packet.method_name or "",
                raw_data=packet.method_args or {},
            )]

        # All other packet types (entity creation, camera, etc.)
        return []

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
            capture_points=(
                int(cap_logic.get("capturePoints", 0))
                if isinstance(cap_logic, dict) else 0
            ),
            capture_speed=(
                float(cap_logic.get("captureSpeed", 0))
                if isinstance(cap_logic, dict) else 0
            ),
            owner_id=(
                int(cap_logic.get("ownerId", 0))
                if isinstance(cap_logic, dict) else 0
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
