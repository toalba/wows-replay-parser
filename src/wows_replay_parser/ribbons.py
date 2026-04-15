"""Ribbon extraction and derivation.

Recording player ribbons: extracted from privateVehicleState.ribbons
(server-authoritative cumulative counts, OWN_CLIENT property).
Other players: derived from hit/damage events (approximate).

Wire IDs (0-56) are from the SubRibbon auto-ID space in m53aea2ee.pyc,
verified by runtime inspection on the game server.
"""

from __future__ import annotations

from typing import Any

from wows_replay_parser.events.models import (
    DamageEvent,
    DeathEvent,
    GameEvent,
    RibbonEvent,
    ShotDestroyedEvent,
)

# fmt: off
# Complete wire ribbon IDs (0-56). Verified against 5 replays.
RIBBON_WIRE_IDS: dict[int, str] = {
    0:  "MAIN_CALIBER",
    1:  "TORPEDO",
    2:  "BOMB",
    3:  "PLANE",
    4:  "CRIT",
    5:  "FRAG",
    6:  "BURN",
    7:  "FLOOD",
    8:  "CITADEL",
    9:  "BASE_DEFENSE",
    10: "BASE_CAPTURE",
    11: "BASE_CAPTURE_ASSIST",
    12: "SUPPRESSED",
    13: "SECONDARY_CALIBER",
    14: "MAIN_CALIBER_OVER_PENETRATION",
    15: "MAIN_CALIBER_PENETRATION",
    16: "MAIN_CALIBER_NO_PENETRATION",
    17: "MAIN_CALIBER_RICOCHET",
    18: "BUILDING_KILL",
    19: "DETECTED",
    20: "BOMB_OVER_PENETRATION",
    21: "BOMB_PENETRATION",
    22: "BOMB_NO_PENETRATION",
    23: "BOMB_RICOCHET",
    24: "ROCKET",
    25: "ROCKET_PENETRATION",
    26: "ROCKET_NO_PENETRATION",
    27: "SPLANE",
    28: "BULGE",
    29: "BOMB_BULGE",
    30: "ROCKET_BULGE",
    31: "DBOMB",
    32: "ACOUSTIC_HIT",
    33: "DROP",
    34: "ROCKET_RICOCHET",
    35: "ROCKET_OVER_PENETRATION",
    36: "WAVE_KILL_TORPEDO",
    37: "WAVE_CUT_WAVE",
    38: "WAVE_HIT_VEHICLE",
    39: "ACOUSTIC_HIT_NEW",
    40: "ACOUSTIC_HIT_CURR",
    41: "ACOUSTIC_HIT_BLOCK",
    42: "ACID",
    43: "DBOMB_FULL_DAMAGE",
    44: "DBOMB_PARTIAL_DAMAGE",
    45: "MINE",
    46: "DEMINING_MINE",
    47: "DEMINING_MINEFIELD",
    48: "TORPEDO_PHOTON_HIT",
    49: "TORPEDO_PHOTON_SPLASH",
    50: "AIM_PULSE_TORPEDO_PHOTON",
    51: "PHASER_LASER",
    52: "SHIELD_HIT",
    53: "SHIELD_REMOVED",
    54: "ASSIST",
    55: "MISSILE_HIT",
    56: "SHOT_DOWN_MISSILE",
}
# fmt: on

# Convenience constants for common ribbon IDs
RIBBON_MAIN_CALIBER = 0
RIBBON_TORPEDO = 1
RIBBON_BOMB = 2
RIBBON_PLANE = 3
RIBBON_CRIT = 4
RIBBON_FRAG = 5
RIBBON_BURN = 6
RIBBON_FLOOD = 7
RIBBON_CITADEL = 8
RIBBON_BASE_DEFENSE = 9
RIBBON_BASE_CAPTURE = 10
RIBBON_BASE_CAPTURE_ASSIST = 11
RIBBON_SUPPRESSED = 12
RIBBON_SECONDARY_CALIBER = 13
RIBBON_OVER_PENETRATION = 14
RIBBON_PENETRATION = 15
RIBBON_NO_PENETRATION = 16
RIBBON_RICOCHET = 17
RIBBON_BUILDING_KILL = 18
RIBBON_DETECTED = 19
RIBBON_ASSIST = 54

# NB: `RIBBON_WIRE_IDS` is already id→name. A previous version inverted it
# into {name: id}, which silently broke `derive_ribbons()` (every lookup
# fell through to the default). Keep this a straight alias so `.get(int_id)`
# returns the ribbon name string.
RIBBON_NAMES: dict[int, str] = dict(RIBBON_WIRE_IDS)
# Also keep the old friendly names for display
RIBBON_DISPLAY_NAMES: dict[int, str] = {
    0: "Main Battery Hit", 1: "Torpedo Hit", 2: "Bomb Hit",
    3: "Plane Shot Down", 4: "Critical Hit", 5: "Destroyed",
    6: "Set on Fire", 7: "Caused Flooding", 8: "Citadel Hit",
    9: "Base Defense", 10: "Base Capture", 11: "Capture Assist",
    12: "Suppressed", 13: "Secondary Hit",
    14: "Over-penetration", 15: "Penetration",
    16: "Non-penetration", 17: "Ricochet",
    18: "Building Destroyed", 19: "Detected", 54: "Assist",
}

# HIT_TYPE values → ribbon mapping (simplified)
# These are approximate — exact mapping depends on game logic
_HIT_TYPE_TO_RIBBON: dict[int, int] = {
    1: RIBBON_PENETRATION,      # regular penetration
    2: RIBBON_NO_PENETRATION,   # shatter/bounce
    3: RIBBON_OVER_PENETRATION, # over-penetration
    4: RIBBON_CITADEL,          # citadel hit
}

# Damage type string → ribbon mapping
_DAMAGE_TYPE_TO_RIBBON: dict[str, int] = {
    "fire": RIBBON_BURN,
    "flooding": RIBBON_FLOOD,
    "torpedo": RIBBON_TORPEDO,
}


def derive_ribbons(events: list[GameEvent]) -> list[RibbonEvent]:
    """Derive ribbon events from existing game events.

    This is a simplified approximation of the client-side ribbon
    derivation logic. It covers the obvious cases:
    - Shell hits (penetration, citadel, over-pen, shatter)
    - Torpedo hits
    - Fire/flooding from damage events
    - Kill ribbons from death events

    Args:
        events: List of game events from EventStream.

    Returns:
        List of derived RibbonEvent objects, sorted by timestamp.
    """
    ribbons: list[RibbonEvent] = []

    for event in events:
        if isinstance(event, ShotDestroyedEvent):
            ribbon_id = _HIT_TYPE_TO_RIBBON.get(event.hit_type)
            if ribbon_id is not None:
                ribbons.append(RibbonEvent(
                    timestamp=event.timestamp,
                    entity_id=event.owner_id,
                    ribbon_id=ribbon_id,
                    ribbon_name=RIBBON_NAMES.get(
                        ribbon_id, "Unknown",
                    ),
                    vehicle_id=event.owner_id,
                    target_id=0,  # target not in ShotDestroyedEvent
                ))

        elif isinstance(event, DeathEvent):
            if event.killer_id:
                ribbons.append(RibbonEvent(
                    timestamp=event.timestamp,
                    entity_id=event.killer_id,
                    ribbon_id=RIBBON_FRAG,
                    ribbon_name=RIBBON_NAMES[RIBBON_FRAG],
                    vehicle_id=event.killer_id,
                    target_id=event.victim_id,
                ))

        elif isinstance(event, DamageEvent):
            ribbon_id = _DAMAGE_TYPE_TO_RIBBON.get(
                event.damage_type,
            )
            if ribbon_id is not None:
                ribbons.append(RibbonEvent(
                    timestamp=event.timestamp,
                    entity_id=event.entity_id,
                    ribbon_id=ribbon_id,
                    ribbon_name=RIBBON_NAMES.get(
                        ribbon_id, "Unknown",
                    ),
                    vehicle_id=event.entity_id,
                    target_id=event.target_id,
                ))

    return ribbons


def extract_recording_player_ribbons(
    history: list,
    avatar_entity_id: int,
) -> list[RibbonEvent]:
    """Extract server-authoritative ribbons for the recording player.

    Diffs consecutive privateVehicleState.ribbons cumulative snapshots
    to produce individual RibbonEvents with exact timestamps.

    Only works for the recording player (OWN_CLIENT property).
    For other players, use derive_ribbons() instead.

    Args:
        history: The tracker's _history list (list of PropertyChange).
        avatar_entity_id: The recording player's Avatar entity ID.

    Returns:
        Chronological list of RibbonEvents (derived=False).
    """
    events: list[RibbonEvent] = []
    prev_counts: dict[int, int] = {}

    for change in history:
        if (
            change.entity_id != avatar_entity_id
            or change.property_name != "privateVehicleState"
        ):
            continue

        pvs = change.new_value
        if not isinstance(pvs, dict):
            continue

        ribbons_raw = pvs.get("ribbons")
        if ribbons_raw is None:
            continue

        # Handle both list and dict formats
        entries: list[Any]
        if isinstance(ribbons_raw, dict):
            entries = list(ribbons_raw.values())
        elif isinstance(ribbons_raw, list):
            entries = ribbons_raw
        else:
            continue

        curr_counts: dict[int, int] = {}
        for entry in entries:
            if entry is None:
                continue
            rid = (
                entry.get("ribbonId")
                if isinstance(entry, dict)
                else getattr(entry, "ribbonId", None)
            )
            cnt = (
                entry.get("count")
                if isinstance(entry, dict)
                else getattr(entry, "count", None)
            )
            if rid is not None and cnt is not None:
                curr_counts[int(rid)] = int(cnt)

        # Diff against previous snapshot to find new ribbons
        for rid, cnt in curr_counts.items():
            prev = prev_counts.get(rid, 0)
            delta = cnt - prev
            if delta > 0:
                name = RIBBON_WIRE_IDS.get(rid, f"UNKNOWN_{rid}")
                for _ in range(delta):
                    events.append(RibbonEvent(
                        timestamp=change.timestamp,
                        entity_id=avatar_entity_id,
                        ribbon_id=rid,
                        ribbon_name=name,
                        vehicle_id=avatar_entity_id,
                        target_id=0,
                        derived=False,
                    ))

        prev_counts = curr_counts

    return events
