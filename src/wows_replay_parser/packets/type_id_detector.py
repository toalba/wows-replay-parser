"""
Auto-detects the entity type_id → entity_name mapping from a replay's packet stream.

The BigWorld engine assigns type IDs based on the order entities appear in
entities.xml (<ClientServerEntities> children). Since we don't ship entities.xml,
we reconstruct the mapping by scanning the replay:

1. Entity creation packets (0x00, 0x05, 0x26) give us entity_id → type_idx.
2. Method call packets (0x08) give us entity_id → max method_id used.
3. Property update packets (0x07) give us entity_id → max property_id used.
4. We match each type_idx to the entity def whose client method count
   and property count are >= the observed maximums.
"""

from __future__ import annotations

import logging
import struct
from collections import defaultdict

from wows_replay_parser.gamedata.entity_registry import EntityRegistry

log = logging.getLogger(__name__)


def detect_type_id_mapping(
    packet_data: bytes,
    registry: EntityRegistry,
) -> dict[int, str]:
    """Scan packet stream and return a type_idx → entity_name mapping.

    The registry must already have all entities registered (without type IDs).
    This function figures out WHICH type_idx maps to WHICH entity.
    """
    # Pass 1: collect entity_id → type_idx from creation packets
    entity_type_idx: dict[int, int] = {}
    # Pass 2: collect per-type_idx max method_id and max property_id
    type_max_method: dict[int, int] = defaultdict(lambda: -1)
    type_max_prop: dict[int, int] = defaultdict(lambda: -1)
    type_entity_count: dict[int, int] = defaultdict(int)

    pos = 0
    data = packet_data
    while pos + 12 <= len(data):
        try:
            size, ptype, _ = struct.unpack("<IIf", data[pos : pos + 12])
        except struct.error:
            break
        if size > 10_000_000 or pos + 12 + size > len(data):
            break

        payload = data[pos + 12 : pos + 12 + size]

        # Entity creation packets: entity_id(u32) + type_idx(u16)
        if ptype in (0x00, 0x05, 0x26) and len(payload) >= 6:
            eid, tidx = struct.unpack("<IH", payload[:6])
            entity_type_idx[eid] = tidx
            type_entity_count[tidx] += 1

        # Method call: entity_id(u32) + method_id(u32) + ...
        elif ptype == 0x08 and len(payload) >= 8:
            eid, mid = struct.unpack("<II", payload[:8])
            tidx = entity_type_idx.get(eid)
            if tidx is not None:
                type_max_method[tidx] = max(type_max_method[tidx], mid)

        # Property update: entity_id(u32) + property_id(u32) + ...
        elif ptype == 0x07 and len(payload) >= 8:
            eid, pid = struct.unpack("<II", payload[:8])
            tidx = entity_type_idx.get(eid)
            if tidx is not None:
                type_max_prop[tidx] = max(type_max_prop[tidx], pid)

        pos += 12 + size

    # Now match type_idx → entity name
    # Build candidate set: for each entity, its method count and property count
    candidates: dict[str, tuple[int, int]] = {}
    for name in registry.entity_names:
        entity = registry.get(name)
        if entity is None:
            continue
        n_methods = len(entity.client_methods_by_index)
        n_props = len(entity.client_properties)
        candidates[name] = (n_methods, n_props)

    # Greedy matching: for each type_idx (ordered by most constraining first),
    # find the entity whose counts are >= observed maximums
    mapping: dict[int, str] = {}
    used_names: set[str] = set()

    # Sort type indices by how constraining they are (higher max_method first)
    sorted_tidx = sorted(
        type_entity_count.keys(),
        key=lambda t: (type_max_method.get(t, -1), type_max_prop.get(t, -1)),
        reverse=True,
    )

    for tidx in sorted_tidx:
        needed_methods = type_max_method.get(tidx, -1) + 1  # max_id is 0-based
        needed_props = type_max_prop.get(tidx, -1) + 1

        best_name = None
        best_score = (float("inf"), float("inf"))  # prefer tightest fit

        for name, (n_methods, n_props) in candidates.items():
            if name in used_names:
                continue
            if n_methods < needed_methods or n_props < needed_props:
                continue
            # Score: prefer smallest surplus (tightest match)
            score = (n_methods - needed_methods, n_props - needed_props)
            if score < best_score:
                best_score = score
                best_name = name

        if best_name is not None:
            mapping[tidx] = best_name
            used_names.add(best_name)
            log.debug(
                "type_idx=%d → %s (need %d methods/%d props, have %d/%d)",
                tidx, best_name, needed_methods, needed_props,
                candidates[best_name][0], candidates[best_name][1],
            )

    return mapping
