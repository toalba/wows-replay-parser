"""Parser for SHIP_CONFIG binary blobs from onArenaStateReceived.

The shipConfigDump field in the arena state pickle contains each player's
full ship loadout: equipped modules (Units), upgrades (Modernizations),
signal flags (Exteriors), and consumables (Abilities).

Wire format (version 1):
    version(u32) + shipParamsId(u32) + numEntries(u32) + entries(u32 * N)

The entries array contains count-prefixed sub-arrays:
    [0]  Units:          count + u32[count]  (14 slots: hull, artillery, etc.)
    [1]  (reserved):     count + u32[count]  (usually empty)
    [2]  Modernizations: count + u32[count]  (equipped upgrades, GP IDs)
    [3]  Exteriors:      count + u32[count]  (signal flags + camouflage, GP IDs)
    [4]  (reserved):     count + u32[count]
    [5]  (reserved):     count + u32[count]
    [6]  Consumables:    count + u32[count]  (equipped abilities, GP IDs, 0=empty slot)
    [7]  (reserved):     count + u32[count]
    [8]  (reserved):     count + u32[count]
    [9]  (reserved):     count + u32[count]
    [10] (reserved):     count + u32[count]
    tail: u32                                (unknown — possibly crew skill points)

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

    # Parse count-prefixed sections
    sections: list[list[int]] = []
    idx = 0
    while idx < num_entries:
        count = vals[idx]
        idx += 1
        if idx + count > num_entries:
            # Last value isn't a count — it's the tail
            break
        section = vals[idx : idx + count]
        idx += count
        sections.append(section)

    config = ShipConfig(ship_params_id=ship_params_id)

    if len(sections) > 0:
        config.units = [v for v in sections[0] if v != 0]
    if len(sections) > 2:
        config.modernizations = [v for v in sections[2] if v != 0]
    if len(sections) > 3:
        config.exteriors = [v for v in sections[3] if v != 0]
    if len(sections) > 6:
        config.consumables = [v for v in sections[6] if v != 0]

    return config
