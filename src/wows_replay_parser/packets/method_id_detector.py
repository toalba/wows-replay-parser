"""
Auto-detect method_id -> method_name mapping from replay data.

The .def-based sort-size ordering is correct for most methods but has tiebreak
issues in the INFINITY group (sort_size=65536): ~15 Avatar and ~4 Vehicle methods
are placed at wrong indices. This module refines the ordering by observing actual
packet payloads and is enabled by default (auto_detect_methods=True).

Resolves method IDs by observing actual packet data:
1. Fixed-size methods: match constant payload_length to expected arg byte sum
2. Variable-size methods: trial-parse payloads with candidate schemas
2b. Semantic validation: when trial parsing is ambiguous (multiple schemas parse OK),
    validate parsed values against domain-specific rules (e.g. shell speed ranges,
    direction vector normalization, entity ID bounds) to narrow candidates
3. Elimination: if N-1 of N methods resolved, the last one is assigned
4. Fallback: keep current sort-order position for unresolved methods

Runs AFTER type_id_detector (needs entity_id -> entity_name)
and BEFORE PacketDecoder.decode_stream.
"""

from __future__ import annotations

import io
import logging
import math
import struct
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from wows_replay_parser.gamedata.alias_registry import AliasRegistry
from wows_replay_parser.gamedata.def_loader import MethodDef
from wows_replay_parser.gamedata.entity_registry import (
    INFINITY,
    EntityRegistry,
    ResolvedEntity,
    compute_type_sort_size,
)
from wows_replay_parser.gamedata.schema_builder import SchemaBuilder

log = logging.getLogger(__name__)

MAX_PAYLOAD_SAMPLES = 5
_SEMANTIC_VALIDATION_SAMPLE_SIZE = 10
_SEMANTIC_VALIDATION_PASS_THRESHOLD = 0.7  # 70% of samples must pass


# ── Data structures ──────────────────────────────────────────────


@dataclass
class _TieGroup:
    """Methods sharing the same sort_size occupying consecutive indices."""

    sort_size: int
    base_index: int
    methods: list[MethodDef]


@dataclass
class _MethodObservation:
    """Observed packet data for a specific (entity_type, method_id)."""

    payload_lengths: list[int] = field(default_factory=list)
    sample_payloads: list[bytes] = field(default_factory=list)

    def add(self, length: int, payload: bytes) -> None:
        self.payload_lengths.append(length)
        if len(self.sample_payloads) < max(MAX_PAYLOAD_SAMPLES, _SEMANTIC_VALIDATION_SAMPLE_SIZE):
            self.sample_payloads.append(payload)

    @property
    def constant_length(self) -> int | None:
        """Return the payload length if it's always the same, else None."""
        if not self.payload_lengths:
            return None
        s = set(self.payload_lengths)
        if len(s) == 1:
            return self.payload_lengths[0]
        return None


# ── Public API ───────────────────────────────────────────────────


def detect_method_id_mapping(
    packet_data: bytes,
    registry: EntityRegistry,
    schema_builder: SchemaBuilder,
    aliases: AliasRegistry,
) -> dict[str, dict[int, MethodDef]]:
    """Scan packet stream and resolve ambiguous method_id mappings.

    This is a Tier 2 fallback for when .def files are not available.
    When .def files ARE available, the deterministic sort produces the
    correct mapping and this function should NOT be called.

    Returns:
        dict mapping entity_name -> {method_index -> corrected MethodDef}.
        Only includes entries where the mapping changed.
    """
    # Step 1: entity_id -> entity_name from creation packets
    entity_names = _scan_entity_names(packet_data, registry)

    # Step 2: collect observations per (entity_name, method_id)
    observations = _collect_observations(packet_data, entity_names)

    # Step 3: for each entity, find tie groups and resolve
    result: dict[str, dict[int, MethodDef]] = {}

    for entity_name in registry.entity_names:
        entity = registry.get(entity_name)
        if entity is None:
            continue

        tie_groups = _find_tie_groups(entity)
        if not tie_groups:
            continue

        entity_obs = observations.get(entity_name, {})
        if not entity_obs:
            continue

        entity_overrides: dict[int, MethodDef] = {}
        for group in tie_groups:
            resolved = _resolve_tie_group(
                group, entity_obs, schema_builder, entity_name, aliases,
            )
            if resolved:
                entity_overrides.update(resolved)

        if entity_overrides:
            result[entity_name] = entity_overrides
            log.info(
                "method_id_detector: %s — resolved %d method(s) in %d tie group(s)",
                entity_name,
                len(entity_overrides),
                len(tie_groups),
            )

    return result


# ── Internal helpers ─────────────────────────────────────────────


def _scan_entity_names(
    packet_data: bytes,
    registry: EntityRegistry,
) -> dict[int, str]:
    """Scan creation packets to build entity_id -> entity_name mapping."""
    entity_type_idx: dict[int, int] = {}
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

        pos += 12 + size

    # Resolve type_idx -> entity_name via registry
    entity_names: dict[int, str] = {}
    for eid, tidx in entity_type_idx.items():
        entity = registry.get_by_type_id(tidx)
        if entity is not None:
            entity_names[eid] = entity.name

    return entity_names


def _collect_observations(
    packet_data: bytes,
    entity_names: dict[int, str],
) -> dict[str, dict[int, _MethodObservation]]:
    """Scan method call packets and collect payload data per (entity, method_id)."""
    obs: dict[str, dict[int, _MethodObservation]] = defaultdict(
        lambda: defaultdict(_MethodObservation),
    )

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

        # Method call: entity_id(u32) + method_id(u32) + payload_length(u32) + args
        if ptype == 0x08 and len(payload) >= 12:
            eid, mid, plen = struct.unpack("<III", payload[:12])
            ename = entity_names.get(eid)
            if ename is not None:
                arg_data = payload[12 : 12 + plen]
                obs[ename][mid].add(plen, arg_data)

        pos += 12 + size

    return obs


def _find_tie_groups(entity: ResolvedEntity) -> list[_TieGroup]:
    """Identify groups of 2+ methods with identical sort_size."""
    if not entity.client_methods_by_index:
        return []

    # Build list sorted by index
    max_idx = max(entity.client_methods_by_index.keys())
    methods_by_idx: list[tuple[int, MethodDef]] = []
    for i in range(max_idx + 1):
        m = entity.client_methods_by_index.get(i)
        if m is not None:
            methods_by_idx.append((i, m))

    groups: list[_TieGroup] = []
    i = 0
    while i < len(methods_by_idx):
        idx, method = methods_by_idx[i]
        ss = method.sort_size
        # Collect consecutive methods with same sort_size
        group_methods = [method]
        base_idx = idx
        j = i + 1
        while j < len(methods_by_idx):
            next_idx, next_method = methods_by_idx[j]
            if next_method.sort_size != ss:
                break
            group_methods.append(next_method)
            j += 1

        if len(group_methods) >= 2:
            groups.append(_TieGroup(
                sort_size=ss,
                base_index=base_idx,
                methods=group_methods,
            ))

        i = j

    return groups


def _compute_expected_payload_size(
    method: MethodDef,
    aliases: AliasRegistry,
) -> int | None:
    """Compute exact payload byte count for a fixed-size method.

    Returns None if any arg is variable-length.
    Does NOT add variable_length_header_size (that's in sort_size but not in
    the payload_length field of packets).
    """
    total = 0
    for _, arg_type in method.args:
        s = compute_type_sort_size(arg_type, aliases)
        if s >= INFINITY:
            return None
        total += s
    return total


def _try_parse(
    schema_builder: SchemaBuilder,
    method: MethodDef,
    sample_payloads: list[bytes],
) -> bool:
    """Try parsing all sample payloads with a method's schema.

    Returns True only if ALL samples parse successfully and consume
    exactly the right number of bytes.
    """
    schema = schema_builder.build_schema_for_method_def(method)
    if schema is None:
        return False

    for payload in sample_payloads:
        try:
            stream = io.BytesIO(payload)
            schema.parse_stream(stream)
            # Check that the entire payload was consumed
            remaining = stream.read()
            if remaining:
                return False
        except Exception:
            return False

    return True


def _try_parse_and_collect(
    schema_builder: SchemaBuilder,
    method: MethodDef,
    sample_payloads: list[bytes],
) -> list[Any] | None:
    """Try parsing sample payloads and return parsed results.

    Returns list of parsed results if ALL samples parse successfully
    and consume all bytes. Returns None on failure.
    """
    schema = schema_builder.build_schema_for_method_def(method)
    if schema is None:
        return None

    results: list[Any] = []
    for payload in sample_payloads:
        try:
            stream = io.BytesIO(payload)
            parsed = schema.parse_stream(stream)
            remaining = stream.read()
            if remaining:
                return None
            results.append(parsed)
        except Exception:
            return None

    return results


# ── Semantic validators ──────────────────────────────────────────
#
# Each validator takes a single parsed result (Container from construct)
# and returns True if values look like plausible game data for that method.
# Validators must be conservative — wide ranges, never reject valid data.
# The method schema wraps args in a Struct, so parsed.arg0 / parsed.arg1 etc.


def _is_finite(val: Any) -> bool:
    """Check if a numeric value is finite (not NaN or inf)."""
    return isinstance(val, (int, float)) and math.isfinite(val)


def _in_map_bounds(v: Any) -> bool:
    """Check if a VECTOR3 Container is within plausible map bounds."""
    try:
        return (
            _is_finite(v.x) and abs(v.x) <= 30000
            and _is_finite(v.y) and abs(v.y) <= 30000
            and _is_finite(v.z) and abs(v.z) <= 30000
        )
    except (AttributeError, TypeError):
        return False


def _validate_artillery_shots(parsed: Any) -> bool:
    """ARRAY<SHOTS_PACK> — paramsID(U32), ownerID(I32), salvoID(I32), shots(ARRAY<SHOT>)
    Each SHOT: pos(V3), pitch(F), speed(F), tarPos(V3), shotID(U16), ..."""
    try:
        packs = parsed.arg0
        if not isinstance(packs, (list,)) or len(packs) == 0:
            return False
        for pack in packs:
            shots = pack.shots
            if not isinstance(shots, (list,)) or len(shots) == 0 or len(shots) > 30:
                return False
            for shot in shots:
                if not _in_map_bounds(shot.pos):
                    return False
                # Artillery shell speed: 200-1500 m/s typical, allow wide range
                if not _is_finite(shot.speed) or shot.speed < 50 or shot.speed > 2500:
                    return False
                if not _in_map_bounds(shot.tarPos):
                    return False
                if not isinstance(shot.shotID, int) or shot.shotID < 0 or shot.shotID > 65535:
                    return False
        return True
    except Exception:
        return False


def _validate_torpedoes(parsed: Any) -> bool:
    """ARRAY<TORPEDOES_PACK> — paramsID(U32), ownerID(I32), salvoID(I32), skinID(U32),
    torpedoes(ARRAY<TORPEDO>)
    Each TORPEDO: pos(V3), dir(V3), shotID(U16), armed(BOOL), maneuverDump, acousticDump"""
    try:
        packs = parsed.arg0
        if not isinstance(packs, (list,)) or len(packs) == 0:
            return False
        for pack in packs:
            torps = pack.torpedoes
            if not isinstance(torps, (list,)) or len(torps) == 0 or len(torps) > 25:
                return False
            for torp in torps:
                if not _in_map_bounds(torp.pos):
                    return False
                # Direction vector should be roughly normalized
                dx, dy, dz = torp.dir.x, torp.dir.y, torp.dir.z
                if not (_is_finite(dx) and _is_finite(dy) and _is_finite(dz)):
                    return False
                dir_len = math.sqrt(dx * dx + dy * dy + dz * dz)
                if dir_len < 0.3 or dir_len > 2.0:
                    return False
                if not isinstance(torp.shotID, int) or torp.shotID < 0 or torp.shotID > 65535:
                    return False
                # armed is BOOL (u8): 0 or 1
                if torp.armed not in (0, 1):
                    return False
        return True
    except Exception:
        return False


def _validate_shot_kills(parsed: Any) -> bool:
    """ARRAY<SHOTKILLS_PACK> — ownerID(I32), hitType(U8), kills(ARRAY<SHOTKILL>)
    Each SHOTKILL: pos(V3), shotID(U16), terminalBallisticsInfo(AllowNone)"""
    try:
        packs = parsed.arg0
        if not isinstance(packs, (list,)) or len(packs) == 0:
            return False
        for pack in packs:
            # ownerID is PLAYER_ID (INT32)
            if not isinstance(pack.ownerID, int):
                return False
            # hitType is HIT_TYPE (UINT8) — small enum
            if not isinstance(pack.hitType, int) or pack.hitType < 0 or pack.hitType > 30:
                return False
            kills = pack.kills
            if not isinstance(kills, (list,)):
                return False
            for kill in kills:
                if not _in_map_bounds(kill.pos):
                    return False
        return True
    except Exception:
        return False


def _validate_chat_message(parsed: Any) -> bool:
    """Avatar: PLAYER_ID(I32), STRING, STRING, STRING"""
    try:
        # arg0 is PLAYER_ID (INT32)
        if not isinstance(parsed.arg0, int):
            return False
        # arg1, arg2, arg3 are STRINGs — at least one should be non-empty text
        has_text = False
        for attr in ("arg1", "arg2", "arg3"):
            val = getattr(parsed, attr, None)
            if isinstance(val, str) and len(val) > 0:
                has_text = True
                break
            if isinstance(val, bytes):
                try:
                    val.decode("utf-8")
                    has_text = True
                    break
                except (UnicodeDecodeError, ValueError):
                    return False
        return has_text
    except Exception:
        return False


def _validate_minimap_vision(parsed: Any) -> bool:
    """MINIMAPINFO(ARRAY<MINIMAP_USER_INFO>), MINIMAPINFO
    Each MINIMAP_USER_INFO: vehicleID(U32), packedData(U32)"""
    try:
        for attr in ("arg0", "arg1"):
            entries = getattr(parsed, attr, None)
            if not isinstance(entries, (list,)):
                return False
            for entry in entries:
                vid = entry.vehicleID
                if not isinstance(vid, int) or vid < 0 or vid > 10_000_000:
                    return False
                packed = entry.packedData
                if not isinstance(packed, int) or packed < 0 or packed > 0xFFFFFFFF:
                    return False
        return True
    except Exception:
        return False


def _validate_vehicle_death(parsed: Any) -> bool:
    """ENTITY_ID(I32), ENTITY_ID(I32), UINT32"""
    try:
        killed = parsed.arg0
        killer = parsed.arg1
        reason = parsed.arg2
        if not isinstance(killed, int) or killed < 0 or killed > 10_000_000:
            return False
        # killer can be -1 for environment kills
        if not isinstance(killer, int) or killer < -1 or killer > 10_000_000:
            return False
        if not isinstance(reason, int) or reason < 0 or reason > 200:
            return False
        return True
    except Exception:
        return False


def _validate_damage_stat(parsed: Any) -> bool:
    """Single BLOB arg — typically pickle data starting with protocol header."""
    try:
        blob = parsed.arg0
        if isinstance(blob, (bytes, bytearray)):
            # Pickle protocol 2 starts with 0x80 0x02
            if len(blob) >= 2 and blob[0] == 0x80:
                return True
            # Empty or very short blobs are suspicious
            return len(blob) > 4
        return False
    except Exception:
        return False


def _validate_arena_state(parsed: Any) -> bool:
    """INT64, INT8, BLOB, BLOB, BLOB, BLOB, BLOB"""
    try:
        arena_id = parsed.arg0
        if not isinstance(arena_id, int) or arena_id <= 0:
            return False
        team_build = parsed.arg1
        if not isinstance(team_build, int) or team_build < -1 or team_build > 50:
            return False
        # Remaining args should be bytes (BLOBs)
        for attr in ("arg2", "arg3", "arg4"):
            val = getattr(parsed, attr, None)
            if val is not None and not isinstance(val, (bytes, bytearray)):
                return False
        return True
    except Exception:
        return False


def _validate_sync_gun(parsed: Any) -> bool:
    """weaponType(U8), gunId(U8), yaw(F32), pitch(F32), flags(U32),
    reloadPerc(F32), loadedAmmo(ARRAY<STRING>)"""
    try:
        # weaponType is WEAPON_TYPE (UINT8) — small enum 0-15
        wt = parsed.weaponType
        if not isinstance(wt, int) or wt < 0 or wt > 20:
            return False
        # yaw and pitch are angles in radians
        yaw = parsed.yaw
        if not _is_finite(yaw) or abs(yaw) > 2 * math.pi + 0.1:
            return False
        pitch = parsed.pitch
        if not _is_finite(pitch) or abs(pitch) > math.pi + 0.1:
            return False
        # reloadPerc is 0.0 to 1.0 (percentage)
        reload_p = parsed.reloadPerc
        if not _is_finite(reload_p) or reload_p < -0.01 or reload_p > 1.01:
            return False
        return True
    except Exception:
        return False


def _validate_damages_on_ship(parsed: Any) -> bool:
    """ARRAY<DAMAGES> — each DAMAGES: vehicleID(ENTITY_ID/I32), damage(F32)"""
    try:
        entries = parsed.arg0
        if not isinstance(entries, (list,)):
            return False
        if len(entries) == 0:
            return False
        for entry in entries:
            vid = entry.vehicleID
            if not isinstance(vid, int) or vid < 0 or vid > 10_000_000:
                return False
            dmg = entry.damage
            if not _is_finite(dmg) or dmg < 0 or dmg > 500_000:
                return False
        return True
    except Exception:
        return False


SEMANTIC_VALIDATORS: dict[str, Callable[[Any], bool]] = {
    "receiveArtilleryShots": _validate_artillery_shots,
    "receiveTorpedoes": _validate_torpedoes,
    "receiveShotKills": _validate_shot_kills,
    "onChatMessage": _validate_chat_message,
    "updateMinimapVisionInfo": _validate_minimap_vision,
    "receiveVehicleDeath": _validate_vehicle_death,
    "receiveDamageStat": _validate_damage_stat,
    "onArenaStateReceived": _validate_arena_state,
    "syncGun": _validate_sync_gun,
    "receiveDamagesOnShip": _validate_damages_on_ship,
}


def _resolve_tie_group(
    group: _TieGroup,
    observations: dict[int, _MethodObservation],
    schema_builder: SchemaBuilder,
    entity_name: str,
    aliases: AliasRegistry,
) -> dict[int, MethodDef]:
    """Resolve a single tie group using payload matching and trial parsing."""
    n = len(group.methods)
    indices = list(range(group.base_index, group.base_index + n))

    # Track what's unresolved
    unresolved_indices: set[int] = set(indices)
    unresolved_methods: set[int] = set(range(n))  # indices into group.methods
    result: dict[int, MethodDef] = {}

    # Precompute expected sizes for fixed-size methods
    expected_sizes: dict[int, int | None] = {}
    for mi, method in enumerate(group.methods):
        expected_sizes[mi] = _compute_expected_payload_size(method, aliases)

    # ── Phase 1: Fixed-size payload matching ────────────────────
    for idx in list(unresolved_indices):
        obs = observations.get(idx)
        if obs is None:
            continue
        cl = obs.constant_length
        if cl is None:
            continue

        # Find candidate methods with this exact expected size
        candidates = [
            mi for mi in unresolved_methods
            if expected_sizes[mi] is not None and expected_sizes[mi] == cl
        ]
        if len(candidates) == 1:
            mi = candidates[0]
            result[idx] = group.methods[mi]
            unresolved_indices.discard(idx)
            unresolved_methods.discard(mi)
            log.debug(
                "method_id_detector: %s idx=%d → %s (fixed-size match, payload=%d)",
                entity_name, idx, group.methods[mi].name, cl,
            )

    # ── Phase 2: Trial parsing for variable-size methods ────────
    # Track methods that parse OK but have multiple candidates (for Phase 2b)
    multi_parse_candidates: dict[int, list[int]] = {}

    if unresolved_indices and unresolved_methods:
        for idx in list(unresolved_indices):
            obs = observations.get(idx)
            if obs is None or not obs.sample_payloads:
                continue

            successful: list[int] = []
            for mi in unresolved_methods:
                if _try_parse(schema_builder, group.methods[mi], obs.sample_payloads):
                    successful.append(mi)

            if len(successful) == 1:
                mi = successful[0]
                result[idx] = group.methods[mi]
                unresolved_indices.discard(idx)
                unresolved_methods.discard(mi)
                log.debug(
                    "method_id_detector: %s idx=%d → %s (trial parse)",
                    entity_name, idx, group.methods[mi].name,
                )
            elif len(successful) > 1:
                multi_parse_candidates[idx] = successful

    # ── Phase 2b: Semantic validation for ambiguous trial parses ─
    # When multiple methods parse successfully, use domain-specific
    # validators to narrow down to a unique match.
    if unresolved_indices and unresolved_methods and multi_parse_candidates:
        for idx in list(unresolved_indices):
            candidates = multi_parse_candidates.get(idx)
            if candidates is None:
                continue

            # Filter to still-unresolved methods
            candidates = [mi for mi in candidates if mi in unresolved_methods]
            if len(candidates) == 0:
                continue
            if len(candidates) == 1:
                # Earlier resolution in this loop narrowed to a unique match
                mi = candidates[0]
                result[idx] = group.methods[mi]
                unresolved_indices.discard(idx)
                unresolved_methods.discard(mi)
                log.debug(
                    "method_id_detector: %s idx=%d → %s (semantic narrowing)",
                    entity_name, idx, group.methods[mi].name,
                )
                continue

            obs = observations.get(idx)
            if obs is None or not obs.sample_payloads:
                continue

            # Find candidates that have a semantic validator
            validated: list[int] = []
            rejected: list[int] = []

            for mi in candidates:
                method = group.methods[mi]
                validator = SEMANTIC_VALIDATORS.get(method.name)
                if validator is None:
                    # No validator — can't confirm or deny
                    validated.append(mi)
                    continue

                # Parse samples and run validator on each
                parsed_results = _try_parse_and_collect(
                    schema_builder, method, obs.sample_payloads,
                )
                if parsed_results is None:
                    rejected.append(mi)
                    continue

                # Run validator on a sample of parsed results
                pass_count = sum(
                    1 for p in parsed_results[:_SEMANTIC_VALIDATION_SAMPLE_SIZE]
                    if validator(p)
                )
                total = min(len(parsed_results), _SEMANTIC_VALIDATION_SAMPLE_SIZE)
                if total > 0 and pass_count / total >= _SEMANTIC_VALIDATION_PASS_THRESHOLD:
                    validated.append(mi)
                else:
                    rejected.append(mi)
                    log.debug(
                        "method_id_detector: %s idx=%d — %s rejected by "
                        "semantic validation (%d/%d passed)",
                        entity_name, idx, method.name, pass_count, total,
                    )

            if len(validated) == 1:
                mi = validated[0]
                result[idx] = group.methods[mi]
                unresolved_indices.discard(idx)
                unresolved_methods.discard(mi)
                log.debug(
                    "method_id_detector: %s idx=%d → %s (semantic validation)",
                    entity_name, idx, group.methods[mi].name,
                )

    # ── Phase 3: Elimination ────────────────────────────────────
    # If only one method and one index remain, they must match
    if len(unresolved_indices) == 1 and len(unresolved_methods) == 1:
        idx = next(iter(unresolved_indices))
        mi = next(iter(unresolved_methods))
        result[idx] = group.methods[mi]
        log.debug(
            "method_id_detector: %s idx=%d → %s (elimination)",
            entity_name, idx, group.methods[mi].name,
        )
        unresolved_indices.clear()
        unresolved_methods.clear()

    # Log any unresolved ties with reason
    if unresolved_indices:
        called_unresolved = []
        uncalled_unresolved = []
        for idx in sorted(unresolved_indices):
            obs = observations.get(idx)
            if obs and obs.payload_lengths:
                called_unresolved.append(idx)
            else:
                uncalled_unresolved.append(idx)

        names = [group.methods[mi].name for mi in sorted(unresolved_methods)]
        if uncalled_unresolved and not called_unresolved:
            log.debug(
                "method_id_detector: %s — %d method(s) in tie group "
                "sort_size=%d never called in replay: %s",
                entity_name, len(unresolved_indices), group.sort_size, names,
            )
        elif called_unresolved and not uncalled_unresolved:
            log.warning(
                "method_id_detector: %s — %d method(s) in tie group "
                "sort_size=%d called but ambiguous (payloads indistinguishable): %s",
                entity_name, len(unresolved_indices), group.sort_size, names,
            )
        else:
            log.warning(
                "method_id_detector: %s — %d method(s) in tie group "
                "sort_size=%d unresolved (%d called, %d uncalled): %s",
                entity_name, len(unresolved_indices), group.sort_size,
                len(called_unresolved), len(uncalled_unresolved), names,
            )

    return result
