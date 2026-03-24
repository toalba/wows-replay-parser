"""Ribbon derivation from hit/damage events.

Since ~patch 14.8, ribbons are derived client-side from hit events,
not sent as network packets. This module reimplements basic ribbon
derivation from the events the parser produces.
"""

from __future__ import annotations

from wows_replay_parser.events.models import (
    DamageEvent,
    DeathEvent,
    GameEvent,
    RibbonEvent,
    ShotDestroyedEvent,
)

# Ribbon IDs from extracted_constants.json (RibbonsType enum)
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
RIBBON_BUILDING_KILL = 18
RIBBON_DETECTED = 19

RIBBON_NAMES: dict[int, str] = {
    RIBBON_MAIN_CALIBER: "Main Battery Hit",
    RIBBON_TORPEDO: "Torpedo Hit",
    RIBBON_BOMB: "Bomb Hit",
    RIBBON_PLANE: "Plane Shot Down",
    RIBBON_CRIT: "Critical Hit",
    RIBBON_FRAG: "Destroyed",
    RIBBON_BURN: "Set on Fire",
    RIBBON_FLOOD: "Caused Flooding",
    RIBBON_CITADEL: "Citadel Hit",
    RIBBON_BASE_DEFENSE: "Base Defense",
    RIBBON_BASE_CAPTURE: "Base Capture",
    RIBBON_BASE_CAPTURE_ASSIST: "Capture Assist",
    RIBBON_SUPPRESSED: "Suppressed",
    RIBBON_SECONDARY_CALIBER: "Secondary Hit",
    RIBBON_OVER_PENETRATION: "Over-penetration",
    RIBBON_PENETRATION: "Penetration",
    RIBBON_NO_PENETRATION: "Non-penetration",
    RIBBON_BUILDING_KILL: "Building Destroyed",
    RIBBON_DETECTED: "Detected",
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
