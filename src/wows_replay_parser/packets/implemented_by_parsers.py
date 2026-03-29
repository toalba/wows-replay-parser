"""
Parsers for implementedBy types — custom serializers used by BigWorld
for BLOB and USER_TYPE fields in .def files.

Each parser has a static parse(data: bytes) -> dict method.
The PARSERS registry maps type names to parser classes.

Return type contract:
- All parsers return dict.
- Lists are wrapped: {'items': [...]}.
- None is never returned — use {'raw': data.hex()} as fallback.
- Every fallback/error branch logs a warning.
"""

from __future__ import annotations

import logging
import pickle
import struct
import zlib
from typing import Any

log = logging.getLogger(__name__)


# ── Known full parsers ───────────────────────────────────────


class ConsumableUsageParamsParser:
    """CONSUMABLE_USAGE_PARAMS — polymorphic by byte 0 (usage_type).

    Wire values (from decompiled CommonConsumables.UsageConverter):
      0 = NONE (no params, not used in practice)
      1 = DEFAULT:  struct '<BB'   — (usage_type, consumableType)
      2 = POSITION: struct '<BBff' — (usage_type, consumableType, x, z)
      3 = ENTITY:   struct '<BBbQ' — (usage_type, consumableType, targetType, targetId)
    """

    @staticmethod
    def parse(data: bytes) -> dict[str, Any]:
        if not data:
            log.warning("ConsumableUsageParamsParser: empty data")
            return {"usage_type": 0, "raw": ""}
        usage_type = data[0]
        if usage_type == 1 and len(data) >= 2:
            return {
                "usage_type": usage_type,
                "consumable_type": data[1],
            }
        elif usage_type == 2 and len(data) >= 10:
            _, ct, x, z = struct.unpack_from("<BBff", data, 0)
            return {
                "usage_type": usage_type,
                "consumable_type": ct,
                "x": x,
                "z": z,
            }
        elif usage_type == 3 and len(data) >= 12:
            _, ct, target_type, target_id = struct.unpack_from("<BBbQ", data, 0)
            return {
                "usage_type": usage_type,
                "consumable_type": ct,
                "target_type": target_type,
                "target_id": target_id,
            }
        log.warning(
            "ConsumableUsageParamsParser: unknown usage_type=%d (%d bytes): %s",
            usage_type, len(data), data.hex(),
        )
        return {"usage_type": usage_type, "raw": data.hex()}


class GunDirectionsParser:
    """GUN_DIRECTIONS — uint32 packed bitfield, 8 guns × 2 bits.

    Each 2-bit field: stored = value + 1 → 0=left(-1), 1=center(0), 2=right(+1).
    """

    @staticmethod
    def parse(data: bytes) -> dict[str, Any]:
        if len(data) < 4:
            log.warning("GunDirectionsParser: insufficient data (%d bytes): %s", len(data), data.hex())
            return {"items": [], "raw": data.hex()}
        packed = struct.unpack_from("<I", data, 0)[0]
        directions = []
        for i in range(8):
            val = (packed >> (i * 2)) & 0x3
            directions.append(val - 1)  # -1, 0, +1
        return {"items": directions}


class ShipConfigParser:
    """SHIP_CONFIG — sectioned binary format with GameParams IDs.

    Layout (all uint32 LE):
        @0:   unknown (always 1?)
        @4:   ship_params_id (GameParams Ship ID)
        @8:   total_size_or_count
        @12+: num_modules(u32) + module_ids × N
              num_modernizations(u32) + modernization_ids × M
              num_exteriors(u32) + exterior_ids × E (signals + camo)
              section_marker(u32) + padding(u32) + num_ability_slots(u32) +
                  ability_ids × A + zeros for empty slots
              num_ensigns(u32) + ensign_ids × F
              trailer (small ints)
    """

    @staticmethod
    def parse(data: bytes) -> dict[str, Any]:
        """Parse compact ShipConfig binary format.

        Fully reconstructed from decompiled ShipConfigDescription.py
        and ShipConfig.initSlotsFromCompactDescr.

        Layout (all uint32 LE):
            shipId, numUnitTypes, uc_id × N,
            appliedExternalConfig,
            ModernizationSlots:  count + ids,
            ExteriorSlots:       count + ids + autobuy + colorSchemes(count + k/v pairs),
            AbilitySlots:        count + ids,      ← consumable GameParams IDs
            EnsignSlots:         count + ids,
            EcoboostSlots:       count + ids + autobuy,
            BattleCardSlots:     count + ids,
            navalFlagId
        """
        if len(data) < 12:
            log.warning("ShipConfigParser: insufficient data (%d bytes): %s", len(data), data.hex())
            return {"raw": data.hex()}

        off = 0

        def read_u32() -> int:
            nonlocal off
            if off + 4 > len(data):
                return 0
            val = struct.unpack_from("<I", data, off)[0]
            off += 4
            return val

        def read_section(max_count: int = 100) -> list[int]:
            count = read_u32()
            ids: list[int] = []
            for _ in range(min(count, max_count)):
                if off + 4 > len(data):
                    break
                ids.append(read_u32())
            return ids

        # The raw property data may have a small leading value (always 1)
        # that is part of BigWorld's property wire encoding, not the shipId.
        # Skip it if the first u32 is very small and the second looks like a
        # GameParams ID (> 1M).
        first = struct.unpack_from("<I", data, 0)[0]
        second = struct.unpack_from("<I", data, 4)[0]
        if first <= 1 and second > 1_000_000:
            read_u32()  # skip leading marker

        # Header: shipId, then a skipped value, then numUnitTypes
        # (decompiled: dataBuffer[1:] skips first element after shipId)
        ship_id = read_u32()
        _skipped = read_u32()  # total count or size hint — skipped by engine
        num_unit_types = read_u32()

        # Module IDs (numUnitTypes entries, 0 = empty)
        modules: list[int] = []
        for _ in range(min(num_unit_types, 50)):
            if off + 4 > len(data):
                break
            modules.append(read_u32())

        # Applied external config
        applied_external_config = read_u32() if off + 4 <= len(data) else 0

        # Modernization slots
        modernizations = read_section() if off + 4 <= len(data) else []

        # Exterior slots (has extra autobuy + colorSchemes)
        exteriors = read_section() if off + 4 <= len(data) else []
        autobuy_info = read_u32() if off + 4 <= len(data) else 0
        color_schemes: dict[int, int] = {}
        if off + 4 <= len(data):
            cs_count = read_u32()
            for _ in range(min(cs_count, 50)):
                if off + 8 > len(data):
                    break
                key = read_u32()
                value = read_u32()
                color_schemes[key] = value

        # Ability slots — consumable GameParams IDs
        raw_abilities = read_section() if off + 4 <= len(data) else []
        ability_ids = [a for a in raw_abilities if a > 0]

        # Ensign slots
        ensigns = read_section() if off + 4 <= len(data) else []

        # Ecoboost slots (has extra autobuy)
        ecoboosts = read_section() if off + 4 <= len(data) else []
        _eco_autobuy = read_u32() if off + 4 <= len(data) else 0

        # BattleCard slots
        battle_cards = read_section() if off + 4 <= len(data) else []

        # Naval flag ID
        naval_flag_id = read_u32() if off + 4 <= len(data) else 0

        return {
            "ship_id": ship_id,
            "modules": [m for m in modules if m > 0],
            "applied_external_config": applied_external_config,
            "modernizations": modernizations,
            "exteriors": exteriors,
            "color_schemes": color_schemes,
            "ability_ids": ability_ids,
            "ensigns": ensigns,
            "ecoboosts": ecoboosts,
            "battle_cards": battle_cards,
            "naval_flag_id": naval_flag_id,
        }


class ShipStateParser:
    """SHIP_STATE — FIXED_DICT: lockInfo, repairInfo, shellCost, shipConfig.

    TODO: Unverified — depends on ShipConfigParser being correct.
    Field layout (lockInfo, repairInfo, shellCost) is assumed from
    the decompiled ShipState.converter but not validated against real data.
    """

    @staticmethod
    def parse(data: bytes) -> dict[str, Any]:
        log.warning("ShipStateParser: unverified — depends on ShipConfigParser fix")
        if len(data) < 12:
            log.warning("ShipStateParser: insufficient data (%d bytes): %s", len(data), data.hex())
            return {"raw": data.hex()}
        lock_info = struct.unpack_from("<I", data, 0)[0]
        repair_info = struct.unpack_from("<I", data, 4)[0]
        shell_cost = struct.unpack_from("<I", data, 8)[0]
        ship_config_data = data[12:]
        ship_config = ShipConfigParser.parse(ship_config_data) if ship_config_data else {}
        return {
            "lock_info": lock_info,
            "repair_info": repair_info,
            "shell_cost": shell_cost,
            "ship_config": ship_config,
        }


class BattleEventParser:
    """BATTLE_EVENT — struct '<Ib' (5 bytes): id + count."""

    @staticmethod
    def parse(data: bytes) -> dict[str, Any]:
        if len(data) < 5:
            log.warning("BattleEventParser: insufficient data (%d bytes): %s", len(data), data.hex())
            return {"raw": data.hex()}
        event_id, count = struct.unpack_from("<Ib", data, 0)
        return {"id": event_id, "count": count}


class NullableVector3Parser:
    """NULLABLE_VECTOR3 — 12 bytes (x,y,z) or empty = None (returned as empty dict)."""

    @staticmethod
    def parse(data: bytes) -> dict[str, Any]:
        if not data or len(data) < 12:
            return {"is_none": True}
        x, y, z = struct.unpack_from("<fff", data, 0)
        return {"is_none": False, "x": x, "y": y, "z": z}


class NullableFloatParser:
    """NULLABLE_FLOAT — 4 bytes or empty = None (returned as empty dict)."""

    @staticmethod
    def parse(data: bytes) -> dict[str, Any]:
        if not data or len(data) < 4:
            return {"is_none": True}
        return {"is_none": False, "value": struct.unpack_from("<f", data, 0)[0]}


class FlatVectorParser:
    """FLAT_VECTOR — struct '<ff' (8 bytes): x, z. y is always 0."""

    @staticmethod
    def parse(data: bytes) -> dict[str, Any]:
        if len(data) < 8:
            log.warning("FlatVectorParser: insufficient data (%d bytes): %s", len(data), data.hex())
            return {"raw": data.hex()}
        x, z = struct.unpack_from("<ff", data, 0)
        return {"x": x, "y": 0.0, "z": z}


class QuickCommandParser:
    """QUICK_COMMAND — polymorphic, dispatched by first uint16 (command type)."""

    @staticmethod
    def parse(data: bytes) -> dict[str, Any]:
        if len(data) < 2:
            log.warning("QuickCommandParser: insufficient data (%d bytes): %s", len(data), data.hex())
            return {"raw": data.hex()}
        cmd_type = struct.unpack_from("<H", data, 0)[0]
        return {"type": cmd_type, "raw": data[2:].hex() if len(data) > 2 else ""}


class SquadronStateParser:
    """SQUADRON_STATE — FIXED_DICT with 15 fields.

    Known fields (from AirPlanes.AirplaneUtils.squadronStateConverter):
      0: planeID (u32)
      1: position (VECTOR3 = 3×f32)
      2: yaw (f32)
      3-14: unparsed — expected fields include:
        speed, health, maxHealth, squadronIndex, purpose,
        teamID, isAlive, altitude, isReturning, weaponState,
        targetPosition, planeType
    """

    @staticmethod
    def parse(data: bytes) -> dict[str, Any]:
        if len(data) < 4:
            log.warning("SquadronStateParser: insufficient data (%d bytes): %s", len(data), data.hex())
            return {"raw": data.hex()}
        off = 0
        result: dict[str, Any] = {}
        if off + 4 <= len(data):
            result["plane_id"] = struct.unpack_from("<I", data, off)[0]
            off += 4
        if off + 12 <= len(data):
            x, y, z = struct.unpack_from("<fff", data, off)
            result["position"] = {"x": x, "y": y, "z": z}
            off += 12
        if off + 4 <= len(data):
            result["yaw"] = struct.unpack_from("<f", data, off)[0]
            off += 4
        if off < len(data):
            result["unparsed"] = data[off:].hex()
        return result


class WildFireStateParser:
    """WILD_FIRE_STATE — 5 floats from WildFireDef.py.

    Fields: damage, visibility, radius, duration, intensity.
    """

    @staticmethod
    def parse(data: bytes) -> dict[str, Any]:
        if len(data) < 20:
            log.warning("WildFireStateParser: insufficient data (%d bytes): %s", len(data), data.hex())
            return {"raw": data.hex()}
        damage, visibility, radius, duration, intensity = struct.unpack_from("<fffff", data, 0)
        return {
            "damage": damage,
            "visibility": visibility,
            "radius": radius,
            "duration": duration,
            "intensity": intensity,
        }


class MasteryBadgeParser:
    """MASTERY_BADGE — shipID(u32) + masterySign(u32)."""

    @staticmethod
    def parse(data: bytes) -> dict[str, Any]:
        if len(data) < 8:
            log.warning("MasteryBadgeParser: insufficient data (%d bytes): %s", len(data), data.hex())
            return {"raw": data.hex()}
        ship_id, mastery_sign = struct.unpack_from("<II", data, 0)
        return {"ship_id": ship_id, "mastery_sign": mastery_sign}


class MinefieldInfoParser:
    """MINEFIELD_INFO — polymorphic by hasPosition bool.

    Base:     hasPosition(bool), mineID(u64), ownerID(i32),
              teamID(i16), paramsID(u32), lifetime(f32)
    Extended: + x(f32), z(f32) when hasPosition=True

    Uses manual offset parsing to avoid struct alignment issues
    with bool followed by u64.
    """

    @staticmethod
    def parse(data: bytes) -> dict[str, Any]:
        if len(data) < 23:
            log.warning("MinefieldInfoParser: insufficient data (%d bytes): %s", len(data), data.hex())
            return {"raw": data.hex()}
        # Manual offset parsing — bool(1) + u64(8) + i32(4) + i16(2) + u32(4) + f32(4) = 23
        off = 0
        has_pos = bool(data[off])
        off += 1
        mine_id = struct.unpack_from("<Q", data, off)[0]
        off += 8
        owner_id = struct.unpack_from("<i", data, off)[0]
        off += 4
        team_id = struct.unpack_from("<h", data, off)[0]
        off += 2
        params_id = struct.unpack_from("<I", data, off)[0]
        off += 4
        lifetime = struct.unpack_from("<f", data, off)[0]
        off += 4

        result: dict[str, Any] = {
            "has_position": has_pos,
            "mine_id": mine_id,
            "owner_id": owner_id,
            "team_id": team_id,
            "params_id": params_id,
            "lifetime": lifetime,
        }
        if has_pos and off + 8 <= len(data):
            x = struct.unpack_from("<f", data, off)[0]
            off += 4
            z = struct.unpack_from("<f", data, off)[0]
            result["x"] = x
            result["z"] = z
        return result


class CrewModifiersCompactParamsParser:
    """CREW_MODIFIERS_COMPACT_PARAMS — paramsId(u32), isInAdaptation(bool), learnedSkills(array)."""

    @staticmethod
    def parse(data: bytes) -> dict[str, Any]:
        if len(data) < 5:
            log.warning("CrewModifiersCompactParamsParser: insufficient data (%d bytes): %s", len(data), data.hex())
            return {"raw": data.hex()}
        params_id = struct.unpack_from("<I", data, 0)[0]
        is_in_adaptation = bool(data[4])
        remaining = data[5:]
        return {
            "params_id": params_id,
            "is_in_adaptation": is_in_adaptation,
            "learned_skills_raw": remaining.hex() if remaining else "",
        }


class TeamsDefParser:
    """TEAMS_DEF — FIXED_DICT: default + configs.

    Note: The existing construct-based decoder in the tracker already handles
    TEAMS_DEF for BattleLogic.teams. This parser should only be called as a
    fallback if the construct decoder fails.
    """

    @staticmethod
    def parse(data: bytes) -> dict[str, Any]:
        log.warning("TeamsDefParser called — expected construct decoder to handle TEAMS_DEF")
        if len(data) < 1:
            log.warning("TeamsDefParser: insufficient data (%d bytes)", len(data))
            return {"raw": ""}
        default = data[0]
        return {
            "default": default,
            "configs_raw": data[1:].hex() if len(data) > 1 else "",
        }


class MapBorderParser:
    """MAP_BORDER — paramsId(u32) + position(VECTOR3)."""

    @staticmethod
    def parse(data: bytes) -> dict[str, Any]:
        if len(data) < 16:
            log.warning("MapBorderParser: insufficient data (%d bytes): %s", len(data), data.hex())
            return {"raw": data.hex()}
        params_id = struct.unpack_from("<I", data, 0)[0]
        x, y, z = struct.unpack_from("<fff", data, 4)
        return {
            "params_id": params_id,
            "position": {"x": x, "y": y, "z": z},
        }


class DiplomacyTicketParser:
    """DIPLOMACY_TICKET — entityId(u64), startTime(f32), endTime(f32)."""

    @staticmethod
    def parse(data: bytes) -> dict[str, Any]:
        if len(data) < 16:
            log.warning("DiplomacyTicketParser: insufficient data (%d bytes): %s", len(data), data.hex())
            return {"raw": data.hex()}
        entity_id, start_time, end_time = struct.unpack_from("<Qff", data, 0)
        return {
            "entity_id": entity_id,
            "start_time": start_time,
            "end_time": end_time,
        }


# ── Generic parsers for well-known patterns ──────────────────


class ZippedBlobParser:
    """ZIPPED_BLOB — zlib decompress, then pickle.loads."""

    @staticmethod
    def parse(data: bytes) -> dict[str, Any]:
        if not data:
            return {"raw": ""}
        try:
            decompressed = zlib.decompress(data)
            result = pickle.loads(decompressed, encoding="latin-1")
            if isinstance(result, dict):
                return result
            return {"value": result}
        except Exception as e:
            log.warning("ZippedBlobParser failed: %s — raw: %s", e, data[:16].hex())
            return {"raw": data[:50].hex()}


class MsgpackBlobParser:
    """MSGPACK_BLOB — msgpack.unpack."""

    @staticmethod
    def parse(data: bytes) -> dict[str, Any]:
        try:
            import msgpack  # type: ignore[import-untyped]

            result = msgpack.unpackb(data, raw=False)
            if isinstance(result, dict):
                return result
            return {"value": result}
        except ImportError:
            log.warning("MsgpackBlobParser: msgpack not installed")
            return {"raw": data[:50].hex(), "error": "msgpack not installed"}
        except Exception as e:
            log.warning("MsgpackBlobParser failed: %s — raw: %s", e, data[:16].hex())
            return {"raw": data[:50].hex()}


class PickledBlobParser:
    """PICKLED_BLOB — pickle.loads with latin-1 encoding."""

    @staticmethod
    def parse(data: bytes) -> dict[str, Any]:
        if not data:
            return {"raw": ""}
        try:
            result = pickle.loads(data, encoding="latin-1")
            if isinstance(result, dict):
                return result
            return {"value": result}
        except Exception as e:
            log.warning("PickledBlobParser failed: %s — raw: %s", e, data[:16].hex())
            return {"raw": data[:50].hex()}


class GameParamsParser:
    """GAMEPARAMS — typically a single uint32 GameParams ID."""

    @staticmethod
    def parse(data: bytes) -> dict[str, Any]:
        if len(data) == 4:
            return {"gameparams_id": struct.unpack_from("<I", data, 0)[0]}
        log.warning("GameParamsParser: expected 4 bytes, got %d: %s", len(data), data.hex())
        return {"raw": data.hex()}


# ── Stub parsers (partial/unknown layout) ────────────────────


class _StubParser:
    """Base for stub parsers — returns raw hex with a warning."""

    _type_name: str = "UNKNOWN"

    @classmethod
    def parse(cls, data: bytes) -> dict[str, Any]:
        log.warning("Stub parser for %s: %d bytes (needs bytecode reconstruction)", cls._type_name, len(data))
        return {"raw": data.hex()}


class WeatherLogicParamsStub(_StubParser):
    _type_name = "WEATHER_LOGIC_PARAMS"


class ModifierStateStub(_StubParser):
    _type_name = "MODIFIER_STATE"


class SectorWaveShotStub(_StubParser):
    _type_name = "SECTOR_WAVE_SHOT"


class ShotDecalStub(_StubParser):
    _type_name = "SHOT_DECAL"


# ── Registry ─────────────────────────────────────────────────

PARSERS: dict[str, type] = {
    # Full parsers — method args
    "CONSUMABLE_USAGE_PARAMS": ConsumableUsageParamsParser,
    "GUN_DIRECTIONS": GunDirectionsParser,
    "QUICK_COMMAND": QuickCommandParser,
    "SQUADRON_STATE": SquadronStateParser,
    "WILD_FIRE_STATE": WildFireStateParser,
    "MASTERY_BADGE": MasteryBadgeParser,
    "MINEFIELD_INFO": MinefieldInfoParser,
    "NULLABLE_VECTOR3": NullableVector3Parser,
    "NULLABLE_FLOAT": NullableFloatParser,
    "FLAT_VECTOR": FlatVectorParser,
    # Full parsers — properties
    "SHIP_CONFIG": ShipConfigParser,
    "SHIP_STATE": ShipStateParser,
    "BATTLE_EVENT": BattleEventParser,
    "MAP_BORDER": MapBorderParser,
    "DIPLOMACY_TICKET": DiplomacyTicketParser,
    "CREW_MODIFIERS_COMPACT_PARAMS": CrewModifiersCompactParamsParser,
    "TEAMS_DEF": TeamsDefParser,
    "GAMEPARAMS": GameParamsParser,
    # Generic patterns
    "ZIPPED_BLOB": ZippedBlobParser,
    "MSGPACK_BLOB": MsgpackBlobParser,
    "PICKLED_BLOB": PickledBlobParser,
    # Stubs (partial/unknown)
    "WEATHER_LOGIC_PARAMS": WeatherLogicParamsStub,
    "MODIFIER_STATE": ModifierStateStub,
    "SECTOR_WAVE_SHOT": SectorWaveShotStub,
    "SHOT_DECAL": ShotDecalStub,
}
