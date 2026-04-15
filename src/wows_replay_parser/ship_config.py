"""Parser for SHIP_CONFIG binary blobs from onArenaStateReceived.

The shipConfigDump field in the arena state pickle contains each player's
full ship loadout: equipped modules (Units), upgrades (Modernizations),
signal flags (Exteriors), and consumables (Abilities).

Wire format (version 1):
    version(u32) + shipParamsId(u32) + numEntries(u32) + entries(u32 * N)

The entries array is NOT uniform count-prefixed sections. The Exteriors
section has extra trailing data (autobuy + colorSchemes). Actual layout:
    Units(count+ids) → reserved(count+ids, usually empty) →
    Modernizations(count+ids) →
    Exteriors(count+ids) + autobuy(u32) + colorSchemes(count + k/v u32 pairs) →
    Abilities(count+ids, 0=empty slot) → Ensigns → Ecoboosts+autobuy →
    BattleCards → navalFlagId → tail

Unit type indices (from ShipConfigConstants.UNIT_TYPE_NAMES):
    0=hull, 1=engine, 2=fireControl, 3=flightControl, 4=fighter,
    5=torpedoBomber, 6=diveBomber, 7=skipBomber, 8=artillery,
    9=torpedoes, 10=primaryWeapons, 11=secondaryWeapons,
    12=abilities, 13=sonar
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field


@dataclass
class ShipConfig:
    """Parsed ship configuration from a replay."""

    ship_params_id: int = 0
    units: list[int] = field(default_factory=list)
    modernizations: list[int] = field(default_factory=list)
    exteriors: list[int] = field(default_factory=list)
    consumables: list[int] = field(default_factory=list)


def parse_ship_config(raw: bytes | str) -> ShipConfig | None:
    """Parse a shipConfigDump blob into a ShipConfig.

    Args:
        raw: The raw bytes (or latin-1 encoded string) from the
            onArenaStateReceived pickle.

    Returns:
        Parsed ShipConfig, or None if parsing fails.
    """
    if isinstance(raw, str):
        raw = raw.encode("latin-1")

    if len(raw) < 12:
        return None

    version, ship_params_id, num_entries = struct.unpack_from("<III", raw, 0)
    if version != 1 or len(raw) < 12 + num_entries * 4:
        return None

    vals = [struct.unpack_from("<I", raw, 12 + i * 4)[0] for i in range(num_entries)]

    # Parse with special handling for Exteriors section which has extra
    # trailing data (autobuy flag + colorSchemes key/value pairs).
    #
    # Layout (from decompiled ShipConfigDescription + ShipConfig):
    #   Units(count+ids) → Modernizations(count+ids) →
    #   Exteriors(count+ids) + autobuy(1) + colorSchemes(count + k/v pairs) →
    #   Abilities(count+ids) → Ensigns(count+ids) →
    #   Ecoboosts(count+ids) + autobuy(1) →
    #   BattleCards(count+ids) → navalFlagId(1) → tail
    config = ShipConfig(ship_params_id=ship_params_id)

    idx = 0

    def read_section() -> list[int]:
        nonlocal idx
        if idx >= num_entries:
            return []
        count = vals[idx]
        idx += 1
        if count > 200 or idx + count > num_entries:
            return []
        section = vals[idx : idx + count]
        idx += count
        return section

    # Units
    config.units = [v for v in read_section() if v != 0]
    # Reserved (always empty)
    read_section()
    # Modernizations
    config.modernizations = [v for v in read_section() if v != 0]
    # Exteriors + autobuy + colorSchemes
    config.exteriors = [v for v in read_section() if v != 0]
    if idx < num_entries:
        idx += 1  # autobuy flag
    if idx < num_entries:
        cs_count = vals[idx]  # color scheme count
        idx += 1
        idx = min(idx + min(cs_count, 50) * 2, num_entries)  # key/value pairs
    # Abilities (consumables)
    config.consumables = [v for v in read_section() if v != 0]

    return config
