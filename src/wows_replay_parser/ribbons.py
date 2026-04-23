"""Ribbon extraction for the recording player.

Recording player only (OWN_CLIENT property): the server publishes ribbons
for the recording player through ``Avatar.privateVehicleState.ribbons``
nested-property updates. Other players' ribbons are only available
post-match via the BattleResults tail — see :mod:`battle_results`.

Two views over the same source data:

* :func:`extract_recording_player_ribbons` — one RibbonEvent per
  server-side update, matching the client's ``Avatar.gRibbon.fire()``
  callback. Each event's ``count`` is the delta for that update. Best
  for temporal analysis; sum of counts matches the client's final HUD
  count in most cases.

* :func:`coalesce_ribbon_popups` — same events merged by ribbon_id
  within ``LIFE_TIME`` (6.0s). Each returned event represents one
  on-screen popup with its final ``x N`` badge. Best for "what the
  player actually saw".

Wire IDs (0-59) match the declaration order of the ``Ribbon`` class in
``scripts/me087a78d.pyc`` (build 12267945). Each Ribbon is constructed
with id = ``len(Ribbon._Ribbon__all)`` at module init, so wire id ==
position in that list.
"""

from __future__ import annotations

from typing import Any

from wows_replay_parser.events.models import RibbonEvent

# fmt: off
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
    39: "ACOUSTIC_HIT_VEHICLE_NEW",
    40: "ACOUSTIC_HIT_VEHICLE_CURR",
    41: "ACOUSTIC_HIT_VEHICLE_BLOCK",
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
    55: "MISSILE",
    56: "SHOT_DOWN_MISSILE",
    57: "WAVE",
    58: "TORPEDO_PHOTON",
    59: "SHIELD",
}
# fmt: on


def extract_recording_player_ribbons(
    history: list[Any],
    avatar_entity_id: int,
) -> list[RibbonEvent]:
    """Extract server-authoritative ribbons for the recording player.

    One RibbonEvent per server-side update to
    ``Avatar.privateVehicleState.ribbons`` — matches the client's
    ``Avatar.gRibbon.fire(ribbonId, count)`` callback (which produces
    exactly one UI popup per fire) as reverse-engineered from
    ``RibbonsComponentCommon.onStateChanged`` in
    ``scripts/ma1dbb474/RibbonsComponent.pyc``.

    The wire counters in ``ribbons[].count`` are a running tally against
    currently-alive targets, not lifetime cumulative — they can decrease
    when targets die. Negative deltas are ignored (no event fires when a
    counter drops due to a target dying). When the counter later grows
    again, each positive delta produces a new RibbonEvent, matching what
    the player sees in-game.

    Only works for the recording player (OWN_CLIENT property).

    Args:
        history: The tracker's _history list (list of PropertyChange).
        avatar_entity_id: The recording player's Avatar entity ID.

    Returns:
        Chronological list of RibbonEvents.
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

        # Emit exactly one RibbonEvent per positive-delta — mirroring the
        # client's ``gRibbon.fire(ribbonId, count)`` called once per wire
        # update. The ``count`` field carries the delta (popup x N badge).
        for rid, cnt in curr_counts.items():
            prev = prev_counts.get(rid, 0)
            delta = cnt - prev
            if delta > 0:
                name = RIBBON_WIRE_IDS.get(rid, f"UNKNOWN_{rid}")
                events.append(RibbonEvent(
                    timestamp=change.timestamp,
                    entity_id=avatar_entity_id,
                    ribbon_id=rid,
                    ribbon_name=name,
                    count=delta,
                    vehicle_id=avatar_entity_id,
                    target_id=0,
                ))

        prev_counts = curr_counts

    return events


# Lifetimes from scripts/m102f8b9c/RibbonSystem.pyc constants.
RIBBON_LIFE_TIME_SEC: float = 6.0
"""Time a TempRibbon popup stays on screen before fade-out begins."""

RIBBON_DEATH_TIME_SEC: float = 0.5
"""Fade-out duration after LIFE_TIME elapses, before the popup is removed."""


def coalesce_ribbon_popups(
    events: list[RibbonEvent],
    window_sec: float = RIBBON_LIFE_TIME_SEC,
) -> list[RibbonEvent]:
    """Coalesce same-type RibbonEvents within the popup-lifetime window.

    Mirrors the client's ``RibbonSystem.__updateTempEntity`` behavior:
    any ``addRibbon`` call for a given ribbon_id within ``LIFE_TIME`` of
    the previous one for the same id **extends the existing popup**
    (refreshes ``lastUpdate`` and bumps ``tempCount``) rather than
    creating a new popup. Only after a gap greater than ``LIFE_TIME``
    does a new on-screen popup appear.

    Each returned event represents **one on-screen popup**:
      * ``timestamp``: when the popup first appeared (first fire in the window).
      * ``count``: total accumulated count over the popup's lifetime (the
        final ``x N`` badge the player saw before it faded).

    Args:
        events: chronological raw ribbon events from
            ``extract_recording_player_ribbons``.
        window_sec: merge window. Defaults to the client's LIFE_TIME=6.0s.

    Returns:
        Coalesced list with one RibbonEvent per on-screen popup.
    """
    if not events:
        return []

    # active[ribbon_id] -> (index_in_out_list, expiry_timestamp)
    active: dict[int, tuple[int, float]] = {}
    out: list[RibbonEvent] = []

    for ev in events:
        key = ev.ribbon_id
        existing = active.get(key)
        if existing is not None and ev.timestamp <= existing[1]:
            # Within the popup's remaining life: merge.
            idx = existing[0]
            out[idx].count += ev.count
            # The client refreshes lastUpdate on each fire, so expiry extends.
            active[key] = (idx, ev.timestamp + window_sec)
        else:
            # New popup (either first fire of this type or previous one expired).
            out.append(RibbonEvent(
                timestamp=ev.timestamp,
                entity_id=ev.entity_id,
                ribbon_id=ev.ribbon_id,
                ribbon_name=ev.ribbon_name,
                count=ev.count,
                vehicle_id=ev.vehicle_id,
                target_id=ev.target_id,
            ))
            active[key] = (len(out) - 1, ev.timestamp + window_sec)

    return out
