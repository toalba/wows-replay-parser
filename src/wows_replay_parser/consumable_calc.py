"""Compute effective consumable cooldowns from replay loadout data.

Uses base reload from ship_consumables.json, then applies modifiers from:
- Modernizations (upgrades) — from ShipConfig.modernizations
- Signal flags — November Foxtrot (GameParams ID 4280119216)
- Captain skills — from crewModifiersCompactParams.learnedSkills

All modifier data is loaded from wows-gamedata split JSON files.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# November Foxtrot signal flag — the only signal affecting consumable reload.
_NOVEMBER_FOXTROT_ID = 4280119216
_NOVEMBER_FOXTROT_COEFF = 0.95

# cons_type_id → consumableType string (from decompiled ConsumableIDsMap).
CONSUMABLE_TYPE_ID_MAP: dict[int, str] = {
    0: "crashCrew", 1: "scout", 2: "airDefenseDisp", 3: "speedBoosters",
    4: "artilleryBoosters", 5: "hangarBooster", 6: "smokeGenerator",
    8: "regenCrew", 9: "fighter", 10: "sonar", 11: "torpedoReloader",
    12: "rls", 19: "invulnerable", 20: "healForsage",
    21: "activeManeuvering", 22: "callFighters", 23: "regenerateHealth",
    24: "subsOxygenRegen", 25: "subsWaveGunBoost", 26: "subsFourthState",
    27: "depthCharges", 31: "buff", 35: "weaponReloadBooster",
    36: "hydrophone", 37: "fastRudders", 38: "subsEnergyFreeze",
    42: "submarineLocator",
}

# consumableType → ship_consumables.json category key.
_TYPE_TO_CATEGORY: dict[str, str] = {
    "crashCrew": "damage_control",
    "regenCrew": "repair_party",
    "regenerateHealth": "repair_party",
    "airDefenseDisp": "defensive_aa",
    "fighter": "catapult_fighter",
    "scout": "catapult_fighter",
    "speedBoosters": "engine_boost",
    "sonar": "hydroacoustic",
    "rls": "surveillance_radar",
    "smokeGenerator": "smoke_screen",
    "torpedoReloader": "torpedo_reload",
    "artilleryBoosters": "main_battery_reload",
    "hydrophone": "submarine_surveillance",
    "submarineLocator": "submarine_surveillance",
}

# Ship species indices matching crewModifiersCompactParams.learnedSkills order.
# Order is alphabetical (verified against real replay data).
SPECIES_INDEX: dict[str, int] = {
    "AirCarrier": 0, "Battleship": 1, "Cruiser": 2,
    "Destroyer": 3, "Auxiliary": 4, "Submarine": 5,
}


def compute_effective_reloads(
    ship_id: int,
    ship_species: str,
    modernization_ids: list[int],
    exterior_ids: list[int],
    learned_skill_ids: list[int],
    crew_id: int,
    gamedata_path: Path,
) -> dict[int, float]:
    """Compute effective reload per consumable type for a player.

    File-based variant: reads split JSON files from disk.
    For the in-memory variant, use ``compute_effective_reloads_from_data``.

    Args:
        ship_id: Ship GameParams ID (for base reload lookup).
        ship_species: Ship species string (Destroyer, Cruiser, etc.).
        modernization_ids: Equipped modernization GameParams IDs.
        exterior_ids: Equipped exterior (signal/camo) GameParams IDs.
        learned_skill_ids: Learned captain skill type IDs for this ship type.
        crew_id: GameParams crew ID (for skill modifier lookup).
        gamedata_path: Path to wows-gamedata entity_defs dir.

    Returns:
        Dict mapping cons_type_id (int) → effective reload time (float seconds).
    """
    gamedata_root = gamedata_path.parent.parent.parent
    split_dir = gamedata_root / "data" / "split"

    # 1. Load base reloads from ship_consumables.json
    base_reloads = _load_base_reloads(gamedata_root, ship_id)
    if not base_reloads:
        return {}

    # 2. Collect modernization modifiers
    mod_coeffs = _collect_modernization_modifiers(
        split_dir / "Modernization", modernization_ids, ship_species,
    )

    # 3. Check November Foxtrot
    has_november_foxtrot = _NOVEMBER_FOXTROT_ID in exterior_ids

    # 4. Collect captain skill modifiers
    skill_coeffs = _collect_skill_modifiers(
        split_dir / "Crew", crew_id, learned_skill_ids,
    )

    # 5. Compute
    return _compute_reloads(
        base_reloads, mod_coeffs, skill_coeffs,
        has_november_foxtrot, ship_species,
    )


def compute_effective_reloads_from_data(
    ship_consumables: dict[int, dict],
    modernizations: dict[int, dict],
    crews: dict[int, dict],
    ship_id: int,
    ship_species: str,
    modernization_ids: list[int],
    exterior_ids: list[int],
    learned_skill_ids: list[int],
    crew_id: int,
) -> dict[int, float]:
    """Compute effective reload per consumable type — in-memory variant.

    Uses pre-loaded dicts instead of reading split JSON files from disk.
    This is the fast path when GameParams data is already in memory.

    Args:
        ship_consumables: {ship_id(int): {timings: {category: reload_s}, ...}}.
        modernizations: {gp_id(int): GameParams Modernization entity dict}.
        crews: {gp_id(int): GameParams Crew entity dict}.
        ship_id: Ship GameParams ID.
        ship_species: Ship species string (Destroyer, Cruiser, etc.).
        modernization_ids: Equipped modernization GameParams IDs.
        exterior_ids: Equipped exterior (signal/camo) GameParams IDs.
        learned_skill_ids: Learned captain skill type IDs for this ship type.
        crew_id: GameParams crew ID.

    Returns:
        Dict mapping cons_type_id (int) → effective reload time (float seconds).
    """
    # 1. Base reloads
    ship_entry = ship_consumables.get(ship_id)
    if not ship_entry:
        return {}
    timings: dict[str, float] = ship_entry.get("timings", {})
    base_reloads: dict[int, float] = {}
    for cons_type_id, cons_type in CONSUMABLE_TYPE_ID_MAP.items():
        category = _TYPE_TO_CATEGORY.get(cons_type)
        if category and category in timings:
            base_reloads[cons_type_id] = timings[category]
    if not base_reloads:
        return {}

    # 2. Modernization modifiers (O(1) per equipped mod)
    mod_coeffs: dict[str, Any] = {}
    for mid in modernization_ids:
        data = modernizations.get(mid)
        if data is None:
            continue
        modifiers = data.get("modifiers", {})
        for key, val in modifiers.items():
            if "ReloadCoeff" in key or key == "ConsumableReloadTime":
                mod_coeffs[key] = val

    # 3. November Foxtrot
    has_november_foxtrot = _NOVEMBER_FOXTROT_ID in exterior_ids

    # 4. Captain skill modifiers (O(1) crew lookup)
    skill_coeffs: dict[str, Any] = {}
    crew_data = crews.get(crew_id)
    if crew_data and learned_skill_ids:
        skills = crew_data.get("Skills", {})
        for _skill_name, skill in skills.items():
            if not isinstance(skill, dict):
                continue
            skill_type = skill.get("skillType")
            if skill_type is None or skill_type not in learned_skill_ids:
                continue
            modifiers = skill.get("modifiers", {})
            for key, val in modifiers.items():
                if key == "reloadFactor":
                    excluded = modifiers.get("excludedConsumables", [])
                    skill_coeffs["reloadFactor"] = {"value": val, "excluded": excluded}
                elif key == "ConsumableReloadTime":
                    skill_coeffs["ConsumableReloadTime"] = val
                elif "ReloadCoeff" in key or "reloadCoeff" in key:
                    skill_coeffs[key] = val

    # 5. Compute
    return _compute_reloads(
        base_reloads, mod_coeffs, skill_coeffs,
        has_november_foxtrot, ship_species,
    )


@dataclass
class ConsumableChargeInfo:
    """Initial charge/capacity info for one consumable."""

    cons_type_id: int
    """Consumable type ID (maps to CONSUMABLE_TYPE_ID_MAP)."""

    charges: int
    """Initial charge count. -1 = unlimited."""

    time_based: bool
    """True if this is a time-based consumable (energy bar, not charges)."""

    max_capacity: float = 0.0
    """For time-based: total capacity in seconds."""

    regen_rate: float = 0.0
    """For time-based: capacity regen per second when inactive."""


def compute_initial_charges_from_data(
    gameparams: dict,
    modernizations: dict[int, dict],
    crews: dict[int, dict],
    ship_id: int,
    consumable_ids: list[int],
    modernization_ids: list[int],
    learned_skill_ids: list[int],
    crew_id: int,
) -> dict[int, ConsumableChargeInfo]:
    """Compute initial consumable charge info per cons_type_id.

    Returns {cons_type_id: ConsumableChargeInfo}.

    For charge-based consumables: charges = initial count (with modifiers).
    For time-based consumables: charges = -1, max_capacity = total seconds.

    Args:
        gameparams: Full decoded GameParams dict.
        modernizations: {gp_id: entity dict} pre-indexed.
        crews: {gp_id: entity dict} pre-indexed.
        ship_id: Ship GameParams ID.
        consumable_ids: Equipped consumable GameParams IDs (from ShipConfig).
        modernization_ids: Equipped modernization GameParams IDs.
        learned_skill_ids: Learned captain skill type IDs.
        crew_id: GameParams crew ID.
    """
    # Build ability_id → entity lookup
    ability_by_id: dict[int, dict] = {}
    for _, obj in gameparams.items():
        if not isinstance(obj, dict):
            continue
        ti = obj.get("typeinfo")
        if isinstance(ti, dict) and ti.get("type") == "Ability":
            aid = obj.get("id")
            if aid is not None:
                ability_by_id[aid] = obj

    # Find the ship entity to get ability variants
    ship_entity: dict | None = None
    for _, obj in gameparams.items():
        if not isinstance(obj, dict):
            continue
        if obj.get("id") == ship_id:
            ti = obj.get("typeinfo")
            if isinstance(ti, dict) and ti.get("type") == "Ship":
                ship_entity = obj
                break

    # Map ability_id → (cons_type_id, variant_name) using ship's ShipAbilities
    ability_to_variant: dict[int, str] = {}
    if ship_entity:
        sa = ship_entity.get("ShipAbilities", {})
        for slot_key in sa:
            slot_val = sa[slot_key]
            abils = slot_val.get("abils", []) if isinstance(slot_val, dict) else (
                slot_val if isinstance(slot_val, list) else []
            )
            for opt in abils:
                if isinstance(opt, (list, tuple)) and len(opt) >= 2:
                    ability_name, variant_name = opt[0], opt[1]
                    ab = ability_by_id.get(gameparams.get(ability_name, {}).get("id", -1))
                    if ab is not None:
                        ability_to_variant[ab.get("id", -1)] = variant_name

    # Collect charge modifiers from modernizations
    mod_additional_global = 0
    mod_additional_typed: dict[str, int] = {}
    for mid in modernization_ids:
        data = modernizations.get(mid)
        if data is None:
            continue
        modifiers = data.get("modifiers", {})
        for key, val in modifiers.items():
            if key == "additionalConsumables":
                mod_additional_global += int(val)
            elif key.endswith("AdditionalConsumables"):
                cons_name = key.removesuffix("AdditionalConsumables")
                mod_additional_typed[cons_name] = mod_additional_typed.get(cons_name, 0) + int(val)

    # Collect charge modifiers from captain skills
    skill_additional_global = 0
    skill_additional_typed: dict[str, int] = {}
    crew_data = crews.get(crew_id)
    if crew_data and learned_skill_ids:
        skills = crew_data.get("Skills", {})
        for _skill_name, skill in skills.items():
            if not isinstance(skill, dict):
                continue
            skill_type = skill.get("skillType")
            if skill_type is None or skill_type not in learned_skill_ids:
                continue
            modifiers = skill.get("modifiers", {})
            for key, val in modifiers.items():
                if key == "additionalConsumables":
                    skill_additional_global += int(val)
                elif key.endswith("AdditionalConsumables"):
                    cons_name = key.removesuffix("AdditionalConsumables")
                    skill_additional_typed[cons_name] = skill_additional_typed.get(cons_name, 0) + int(val)

    # Reverse lookup: consumableType string → cons_type_id
    type_name_to_id: dict[str, int] = {v: k for k, v in CONSUMABLE_TYPE_ID_MAP.items()}

    # Compute per-consumable charges
    result: dict[int, int] = {}
    for cons_gp_id in consumable_ids:
        ab = ability_by_id.get(cons_gp_id)
        if ab is None:
            continue

        # Find the correct variant for this ship
        variant_name = ability_to_variant.get(cons_gp_id, "")
        variant = ab.get(variant_name, {}) if variant_name else {}
        if not isinstance(variant, dict) or "numConsumables" not in variant:
            # Fallback: find any variant with numConsumables
            for key, val in ab.items():
                if isinstance(val, dict) and "numConsumables" in val:
                    variant = val
                    break

        is_time_based = variant.get("lifeCycleType") == 1
        base_charges = variant.get("numConsumables", -1)  # -1 = unlimited (or time-based)

        # Get consumableType directly from variant (no pattern matching)
        cons_type_name = variant.get("consumableType", "")
        cons_type_id = type_name_to_id.get(cons_type_name, -1)

        if cons_type_id < 0:
            continue

        if is_time_based:
            result[cons_type_id] = ConsumableChargeInfo(
                cons_type_id=cons_type_id,
                charges=-1,
                time_based=True,
                max_capacity=float(variant.get("maxCapacity", 0)),
                regen_rate=float(variant.get("capacityRegenCoeff", 0)),
            )
            continue

        if base_charges == -1:
            # Unlimited charge-based
            result[cons_type_id] = ConsumableChargeInfo(
                cons_type_id=cons_type_id, charges=-1, time_based=False,
            )
            continue

        # Apply charge modifiers
        effective = base_charges + mod_additional_global + skill_additional_global
        effective += mod_additional_typed.get(cons_type_name, 0)
        effective += skill_additional_typed.get(cons_type_name, 0)

        result[cons_type_id] = ConsumableChargeInfo(
            cons_type_id=cons_type_id, charges=max(0, effective), time_based=False,
        )

    return result


def _compute_reloads(
    base_reloads: dict[int, float],
    mod_coeffs: dict[str, Any],
    skill_coeffs: dict[str, Any],
    has_november_foxtrot: bool,
    ship_species: str,
) -> dict[int, float]:
    """Apply modifier stack to base reloads and return effective values."""
    result: dict[int, float] = {}
    for cons_type_id, base_reload in base_reloads.items():
        cons_type = CONSUMABLE_TYPE_ID_MAP.get(cons_type_id, "")
        factor = 1.0

        # Modernization: global ConsumableReloadTime
        if "ConsumableReloadTime" in mod_coeffs:
            crt = mod_coeffs["ConsumableReloadTime"]
            if isinstance(crt, dict):
                factor *= crt.get(ship_species, 1.0)
            else:
                factor *= crt

        # Modernization: type-specific <type>ReloadCoeff
        type_key = f"{cons_type}ReloadCoeff"
        if type_key in mod_coeffs:
            factor *= mod_coeffs[type_key]

        # November Foxtrot (-5% all consumables)
        if has_november_foxtrot:
            factor *= _NOVEMBER_FOXTROT_COEFF

        # Captain skills
        for skill_key, skill_val in skill_coeffs.items():
            if skill_key == "reloadFactor":
                excluded = skill_val.get("excluded", [])
                if cons_type not in excluded:
                    factor *= skill_val["value"]
            elif skill_key == "ConsumableReloadTime":
                coeff = skill_val
                if isinstance(coeff, dict):
                    factor *= coeff.get(ship_species, 1.0)
                else:
                    factor *= coeff
            elif skill_key == f"{cons_type}ReloadCoeff":
                factor *= skill_val

        result[cons_type_id] = base_reload * factor

    return result


_sc_cache: dict[str, dict | None] = {}


def _load_base_reloads(
    gamedata_root: Path, ship_id: int,
) -> dict[int, float]:
    """Load base reload times from ship_consumables.json."""
    sc_path = gamedata_root / "data" / "ship_consumables.json"
    cache_key = str(sc_path)

    if cache_key in _sc_cache:
        sc_data = _sc_cache[cache_key]
        if sc_data is None:
            return {}
    elif not sc_path.exists():
        logger.warning("ship_consumables.json not found at %s", sc_path)
        _sc_cache[cache_key] = None
        return {}
    else:
        with open(sc_path) as f:
            sc_data = json.load(f)
        _sc_cache[cache_key] = sc_data

    ship_entry = sc_data.get(str(ship_id))
    if not ship_entry:
        return {}

    timings: dict[str, float] = ship_entry.get("timings", {})

    # Reverse: category → cons_type_id, using timings values
    result: dict[int, float] = {}
    for cons_type_id, cons_type in CONSUMABLE_TYPE_ID_MAP.items():
        category = _TYPE_TO_CATEGORY.get(cons_type)
        if category and category in timings:
            result[cons_type_id] = timings[category]

    return result


def _collect_modernization_modifiers(
    mod_dir: Path,
    modernization_ids: list[int],
    ship_species: str,
) -> dict[str, Any]:
    """Collect reload-affecting modifiers from equipped modernizations."""
    coeffs: dict[str, Any] = {}
    if not mod_dir.exists():
        return coeffs

    # Build ID → file lookup (cached per call — could be optimized)
    for mod_file in mod_dir.glob("*.json"):
        try:
            with open(mod_file) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue

        if data.get("id") not in modernization_ids:
            continue

        modifiers = data.get("modifiers", {})
        for key, val in modifiers.items():
            if "ReloadCoeff" in key or key == "ConsumableReloadTime":
                coeffs[key] = val

    return coeffs


def _collect_skill_modifiers(
    crew_dir: Path,
    crew_id: int,
    learned_skill_ids: list[int],
) -> dict[str, Any]:
    """Collect reload-affecting modifiers from learned captain skills."""
    coeffs: dict[str, Any] = {}
    if not crew_dir.exists() or not learned_skill_ids:
        return coeffs

    # Find crew file by ID and extract skills
    skills = _load_crew_skills(crew_dir, crew_id)
    if not skills:
        return coeffs

    # Scan skills matching learned IDs
    for _skill_name, skill in skills.items():
        if not isinstance(skill, dict):
            continue
        skill_type = skill.get("skillType")
        if skill_type is None or skill_type not in learned_skill_ids:
            continue

        modifiers = skill.get("modifiers", {})
        for key, val in modifiers.items():
            if key == "reloadFactor":
                excluded = modifiers.get("excludedConsumables", [])
                coeffs["reloadFactor"] = {"value": val, "excluded": excluded}
            elif key == "ConsumableReloadTime":
                coeffs["ConsumableReloadTime"] = val
            elif "ReloadCoeff" in key or "reloadCoeff" in key:
                coeffs[key] = val

    return coeffs


def _load_crew_skills(
    crew_dir: Path, crew_id: int,
) -> dict[str, Any] | None:
    """Find crew JSON by GameParams ID and return Skills dict."""
    for crew_file in crew_dir.glob("*.json"):
        try:
            with open(crew_file) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        if data.get("id") == crew_id:
            return data.get("Skills", {})
    return None
