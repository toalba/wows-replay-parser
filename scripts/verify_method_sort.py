#!/usr/bin/env python3
"""Verify BigWorld method sort order against real replay data.

Compares two hypotheses:
  A — No sort (v2.0.1): methods indexed by declaration order
  B — stable_sort by streamSize (v14.4.1): fixed-size first (ascending),
      then variable-size (ascending VLH); ties broken by declaration order

Ground truth comes from semantic validators that uniquely identify method
payloads in real replay packets.
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Add project src to path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from wows_replay_parser.gamedata.alias_registry import AliasRegistry
from wows_replay_parser.gamedata.def_loader import DefLoader, EntityDef, MethodDef
from wows_replay_parser.gamedata.entity_registry import (
    INFINITY,
    EntityRegistry,
    compute_method_sort_size,
)
from wows_replay_parser.gamedata.schema_builder import SchemaBuilder
from wows_replay_parser.packets.decoder import PacketDecoder
from wows_replay_parser.packets.method_id_detector import (
    SEMANTIC_VALIDATORS,
    _try_parse_and_collect,
)
from wows_replay_parser.packets.types import PacketType
from wows_replay_parser.replay.reader import ReplayReader
from wows_replay_parser.state.tracker import GameStateTracker

log = logging.getLogger(__name__)


# ── Data structures ──────────────────────────────────────────────


@dataclass
class MethodInfo:
    """Method with computed metadata for hypothesis testing."""

    name: str
    declaration_order: int
    sort_size: int
    method_def: MethodDef

    @property
    def is_variable(self) -> bool:
        return self.sort_size >= INFINITY

    @property
    def vlh(self) -> int:
        """Variable-length header size (only meaningful for variable methods)."""
        if self.sort_size >= INFINITY:
            return self.sort_size - INFINITY
        return 0

    @property
    def engine_stream_size(self) -> int:
        """Engine streamSize convention: positive=fixed, negative=variable."""
        if self.sort_size >= INFINITY:
            return -(self.sort_size - (INFINITY - 1))
        return self.sort_size


@dataclass
class HypothesisResult:
    name: str
    method_indices: dict[str, int]  # method_name → predicted index


@dataclass
class VerificationRow:
    entity: str
    method: str
    decl_order: int
    hyp_a_idx: int
    hyp_b_idx: int
    observed_idx: int
    a_correct: bool
    b_correct: bool
    discriminating: bool  # True if hyp_a_idx != hyp_b_idx
    in_tie_group: bool = False  # True if method shares sort_size with others


# ── Step 1: Load entity definitions ─────────────────────────────


def load_entity_methods(
    gamedata_path: Path,
    entity_names: list[str],
) -> tuple[dict[str, list[MethodInfo]], AliasRegistry, EntityRegistry]:
    """Load entity defs and compute sort_size per method."""
    aliases = AliasRegistry.from_file(gamedata_path / "alias.xml")
    loader = DefLoader(gamedata_path)

    registry = EntityRegistry(aliases)
    all_entity_defs = loader.load_all()
    for edef in all_entity_defs.values():
        registry.register(edef)

    # Register type IDs from entities.xml
    entities_xml = gamedata_path / "entities.xml"
    if not entities_xml.exists():
        entities_xml = gamedata_path.parent / "entities.xml"
    if entities_xml.exists():
        from lxml import etree

        tree = etree.parse(str(entities_xml))
        root = tree.getroot()
        cs_el = root.find("ClientServerEntities")
        if cs_el is not None:
            for idx, child in enumerate(
                c for c in cs_el if isinstance(c.tag, str)
            ):
                registry.register_type_id(idx, child.tag)

    result: dict[str, list[MethodInfo]] = {}

    for ename in entity_names:
        edef = all_entity_defs.get(ename)
        if edef is None:
            log.warning("Entity %s not found in .def files", ename)
            continue

        methods: list[MethodInfo] = []
        for i, mdef in enumerate(edef.client_methods):
            ss = compute_method_sort_size(mdef, aliases)
            mdef.sort_size = ss
            methods.append(MethodInfo(
                name=mdef.name,
                declaration_order=i,
                sort_size=ss,
                method_def=mdef,
            ))
        result[ename] = methods

    return result, aliases, registry


# ── Step 2: Compute index assignments ────────────────────────────


def hypothesis_a(methods: list[MethodInfo]) -> dict[str, int]:
    """No sort — declaration order = index."""
    return {m.name: m.declaration_order for m in methods}


def hypothesis_b(methods: list[MethodInfo]) -> dict[str, int]:
    """stable_sort by engine streamSize."""

    def engine_sort_key(m: MethodInfo) -> tuple[int, int]:
        """Sort key matching the C++ comparator.

        The C++ comparator groups:
          1. Fixed-size methods (streamSize >= 0): ascending by byte count
          2. Variable-size methods (streamSize < 0): ascending by abs(streamSize) = VLH

        We encode this as a tuple (group, value):
          - Fixed:    (0, streamSize)      → sorted ascending by byte count
          - Variable: (1, vlh)             → sorted ascending by VLH size
        """
        if m.sort_size >= INFINITY:
            vlh = m.sort_size - (INFINITY - 1)
            return (1, vlh)
        else:
            return (0, m.sort_size)

    sorted_methods = sorted(
        methods,
        key=engine_sort_key,
    )
    return {m.name: i for i, m in enumerate(sorted_methods)}


# ── Step 3: Collect ground truth from replays ────────────────────


def collect_ground_truth(
    replay_paths: list[Path],
    registry: EntityRegistry,
    aliases: AliasRegistry,
    entity_methods: dict[str, list[MethodInfo]],
) -> dict[str, dict[str, int]]:
    """Parse replays, identify methods by semantic validation, return observed indices.

    Uses the full PacketDecoder to properly resolve entity types (handling
    Account→Vehicle remapping etc.), then scans raw method call packets to
    collect payloads per (entity_type, method_index). Semantic validators
    identify which method each index corresponds to.

    Returns: {entity_name: {method_name: observed_index}}
    """
    schema_builder = SchemaBuilder(aliases, registry)
    reader = ReplayReader()
    ground_truth: dict[str, dict[str, int]] = {e: {} for e in entity_methods}
    unreliable: set[tuple[str, str]] = set()

    for rpath in replay_paths:
        log.info("Processing replay: %s", rpath.name)
        try:
            replay = reader.read(rpath)
        except Exception as e:
            log.warning("Failed to read %s: %s", rpath.name, e)
            continue

        # Use the full decoder to get proper entity_id → entity_type mapping.
        # We disable method args decoding (we just need entity type resolution).
        tracker = GameStateTracker()
        decoder = PacketDecoder(schema_builder, registry, tracker=tracker)
        packets = decoder.decode_stream(replay.packet_data)

        data = replay.packet_data

        # Build entity_id → entity_type from decoded packets
        entity_types: dict[int, str] = {}
        base_player_eid: int | None = None
        for pkt in packets:
            if pkt.entity_id and pkt.entity_type:
                entity_types[pkt.entity_id] = pkt.entity_type
            # Track the base player entity (BASE_PLAYER_CREATE = 0x00)
            if pkt.type == PacketType.BASE_PLAYER_CREATE and pkt.entity_id:
                base_player_eid = pkt.entity_id

        # The base player entity is created with Vehicle type_idx but
        # actually receives Avatar method calls. Detect this by checking
        # if any method index exceeds Vehicle's method count.
        if base_player_eid is not None and "Avatar" in entity_methods:
            avatar_method_count = len(entity_methods["Avatar"])
            vehicle_method_count = len(entity_methods.get("Vehicle", []))
            # Quick scan to check max method index for this entity
            pos2 = 0
            max_mid = 0
            while pos2 + 12 <= len(data):
                try:
                    sz, pt, _ = struct.unpack("<IIf", data[pos2 : pos2 + 12])
                except struct.error:
                    break
                if sz > 10_000_000 or pos2 + 12 + sz > len(data):
                    break
                pl = data[pos2 + 12 : pos2 + 12 + sz]
                if pt == 0x08 and len(pl) >= 12:
                    eid2, mid2, _ = struct.unpack("<III", pl[:12])
                    if eid2 == base_player_eid and mid2 > max_mid:
                        max_mid = mid2
                pos2 += 12 + sz

            if max_mid >= vehicle_method_count:
                log.info(
                    "Base player entity %d: max method_idx=%d > Vehicle(%d), "
                    "remapping to Avatar",
                    base_player_eid, max_mid, vehicle_method_count,
                )
                entity_types[base_player_eid] = "Avatar"

        # Now scan raw packets again to collect method payloads per
        # (entity_type, method_index), using the properly resolved entity types.
        observations: dict[str, dict[int, list[bytes]]] = {
            e: {} for e in entity_methods
        }

        pos = 0
        while pos + 12 <= len(data):
            try:
                size, ptype, _ = struct.unpack("<IIf", data[pos : pos + 12])
            except struct.error:
                break
            if size > 10_000_000 or pos + 12 + size > len(data):
                break

            payload = data[pos + 12 : pos + 12 + size]

            # ENTITY_METHOD: entity_id(u32) + method_id(u32) + payload_length(u32) + args
            if ptype == 0x08 and len(payload) >= 12:
                eid, mid, plen = struct.unpack("<III", payload[:12])
                ename = entity_types.get(eid)
                if ename in observations:
                    if mid not in observations[ename]:
                        observations[ename][mid] = []
                    if len(observations[ename][mid]) < 10:
                        observations[ename][mid].append(payload[12 : 12 + plen])

            pos += 12 + size

        # For each entity, identify methods by two strategies:
        # 1. Payload-length matching: unique fixed-size payload → method ID
        # 2. Semantic validators: domain-specific validation of parsed data
        for ename, methods in entity_methods.items():
            entity_obs = observations.get(ename, {})
            n_indices = len(entity_obs)
            if not entity_obs:
                log.info("No method observations for %s", ename)
                continue
            log.info("%s: %d method indices observed", ename, n_indices)

            # Precompute expected payload sizes for fixed-size methods
            # (arg byte sum WITHOUT vlh — that's what appears in the packet)
            from wows_replay_parser.gamedata.entity_registry import compute_type_sort_size
            expected_sizes: dict[str, int | None] = {}
            for minfo in methods:
                total = 0
                is_fixed = True
                for _, arg_type in minfo.method_def.args:
                    s = compute_type_sort_size(arg_type, aliases)
                    if s >= INFINITY:
                        is_fixed = False
                        break
                    total += s
                expected_sizes[minfo.name] = total if is_fixed else None

            for obs_idx, sample_payloads in entity_obs.items():
                if not sample_payloads:
                    continue

                # Already identified?
                if any(
                    gt.get(mname) == obs_idx
                    for mname, gt in [(n, ground_truth[ename]) for n in ground_truth[ename]]
                ):
                    continue

                # Strategy 1: payload-length matching for fixed-size methods
                # Only accept if:
                #  - constant payload length matches exactly one method
                #  - trial parsing succeeds
                #  - observed index is within fixed-method range (not in
                #    variable section, where variable methods may coincidentally
                #    produce constant-length payloads)
                n_fixed = sum(1 for m in methods if expected_sizes[m.name] is not None)
                lengths = {len(p) for p in sample_payloads}
                if len(lengths) == 1:
                    constant_len = lengths.pop()
                    matches = [
                        minfo for minfo in methods
                        if expected_sizes[minfo.name] == constant_len
                    ]
                    if len(matches) == 1 and obs_idx < n_fixed:
                        minfo = matches[0]
                        # Verify by trial parsing
                        parsed = _try_parse_and_collect(
                            schema_builder, minfo.method_def, sample_payloads,
                        )
                        if parsed is not None:
                            mname = minfo.name
                            if mname not in ground_truth[ename]:
                                ground_truth[ename][mname] = obs_idx
                                log.info(
                                    "Ground truth (payload-length): %s.%s -> "
                                    "index %d (len=%d)",
                                    ename, mname, obs_idx, constant_len,
                                )
                                continue
                            elif ground_truth[ename][mname] != obs_idx:
                                log.warning(
                                    "Inconsistent ground truth for %s.%s: "
                                    "prev=%d, now=%d -- marking unreliable",
                                    ename, mname,
                                    ground_truth[ename][mname], obs_idx,
                                )
                                unreliable.add((ename, mname))
                                continue
                    elif len(matches) == 1 and obs_idx >= n_fixed:
                        log.debug(
                            "%s idx=%d: payload-length matches %s (len=%d) "
                            "but index is in variable section (>=%d), skipping",
                            ename, obs_idx, matches[0].name, constant_len, n_fixed,
                        )

                # Strategy 2: semantic validators
                validated_names: list[str] = []

                for minfo in methods:
                    validator = SEMANTIC_VALIDATORS.get(minfo.name)
                    if validator is None:
                        continue

                    parsed = _try_parse_and_collect(
                        schema_builder, minfo.method_def, sample_payloads,
                    )
                    if parsed is None:
                        continue

                    pass_count = sum(1 for p in parsed if validator(p))
                    if len(parsed) > 0 and pass_count / len(parsed) >= 0.7:
                        validated_names.append(minfo.name)

                if len(validated_names) == 1:
                    mname = validated_names[0]
                    if mname in ground_truth[ename]:
                        if ground_truth[ename][mname] != obs_idx:
                            log.warning(
                                "Inconsistent ground truth for %s.%s: "
                                "prev=%d, now=%d -- marking unreliable",
                                ename, mname,
                                ground_truth[ename][mname], obs_idx,
                            )
                            unreliable.add((ename, mname))
                    else:
                        ground_truth[ename][mname] = obs_idx
                        log.info(
                            "Ground truth (semantic): %s.%s -> index %d",
                            ename, mname, obs_idx,
                        )
                elif len(validated_names) > 1:
                    log.debug(
                        "%s idx=%d: multiple validators matched: %s",
                        ename, obs_idx, validated_names,
                    )

    # Remove unreliable ground truth entries
    for ename, mname in unreliable:
        if ename in ground_truth and mname in ground_truth[ename]:
            log.info(
                "Removing unreliable ground truth: %s.%s (matched multiple indices)",
                ename, mname,
            )
            del ground_truth[ename][mname]

    return ground_truth


# ── Step 4 & 5: Score and report ─────────────────────────────────


def score_and_report(
    entity_methods: dict[str, list[MethodInfo]],
    ground_truth: dict[str, dict[str, int]],
) -> dict[str, object]:
    """Score both hypotheses and print results. Returns JSON-serializable results."""

    rows: list[VerificationRow] = []
    infinity_rows: list[VerificationRow] = []

    for ename, methods in entity_methods.items():
        hyp_a = hypothesis_a(methods)
        hyp_b = hypothesis_b(methods)

        gt = ground_truth.get(ename, {})

        # Build name→MethodInfo lookup and compute tie groups
        by_name = {m.name: m for m in methods}

        # Count how many methods share each sort_size
        from collections import Counter
        ss_counts = Counter(m.sort_size for m in methods)
        tie_sizes = {ss for ss, cnt in ss_counts.items() if cnt >= 2}

        for mname, obs_idx in sorted(gt.items(), key=lambda x: x[1]):
            minfo = by_name[mname]
            a_idx = hyp_a[mname]
            b_idx = hyp_b[mname]
            in_tie = minfo.sort_size in tie_sizes
            row = VerificationRow(
                entity=ename,
                method=mname,
                decl_order=minfo.declaration_order,
                hyp_a_idx=a_idx,
                hyp_b_idx=b_idx,
                observed_idx=obs_idx,
                a_correct=(a_idx == obs_idx),
                b_correct=(b_idx == obs_idx),
                discriminating=(a_idx != b_idx),
                in_tie_group=in_tie,
            )
            rows.append(row)
            if minfo.is_variable:
                infinity_rows.append(row)

    # ── Print main table ──
    print()
    print("Method Sort Verification")
    print("=" * 80)
    print(
        f"{'Entity':<10} {'Method':<35} {'Decl':>4} {'HypA':>5} "
        f"{'HypB':>5} {'Obs':>5}  A?  B?"
    )
    print(
        f"{'------':<10} {'------':<35} {'----':>4} {'----':>5} "
        f"{'----':>5} {'----':>5}  --  --"
    )

    for r in rows:
        a_mark = "OK" if r.a_correct else "XX"
        b_mark = "OK" if r.b_correct else "XX"
        tie = "T" if r.in_tie_group else " "
        disc = " " if r.discriminating else "*"
        print(
            f"{r.entity:<10} {r.method:<35} {r.decl_order:>4} {r.hyp_a_idx:>5} "
            f"{r.hyp_b_idx:>5} {r.observed_idx:>5}  {a_mark}{disc} {b_mark}{disc} {tie}"
        )

    # ── Summary ──
    disc_rows = [r for r in rows if r.discriminating]
    non_disc = [r for r in rows if not r.discriminating]
    a_correct_disc = sum(1 for r in disc_rows if r.a_correct)
    b_correct_disc = sum(1 for r in disc_rows if r.b_correct)
    a_correct_all = sum(1 for r in rows if r.a_correct)
    b_correct_all = sum(1 for r in rows if r.b_correct)

    # Separate tie-group vs unique-sort-size methods
    unique_rows = [r for r in disc_rows if not r.in_tie_group]
    tie_rows = [r for r in disc_rows if r.in_tie_group]
    b_unique = sum(1 for r in unique_rows if r.b_correct)
    a_unique = sum(1 for r in unique_rows if r.a_correct)
    b_tie = sum(1 for r in tie_rows if r.b_correct)
    a_tie = sum(1 for r in tie_rows if r.a_correct)

    print()
    print(f"Total verified methods: {len(rows)}  (T = in tie group)")
    print(f"  Non-discriminating (A==B): {len(non_disc)} (marked with *)")
    print(f"  Discriminating (A!=B):     {len(disc_rows)}")
    print(f"    Unique sort_size:        {len(unique_rows)}")
    print(f"    In tie group:            {len(tie_rows)}")
    print()

    if disc_rows:
        a_pct = 100 * a_correct_disc / len(disc_rows)
        b_pct = 100 * b_correct_disc / len(disc_rows)
        print(f"ALL discriminating cases:")
        print(
            f"  Hypothesis A (no sort):       "
            f"{a_correct_disc}/{len(disc_rows)} correct ({a_pct:.1f}%)"
        )
        print(
            f"  Hypothesis B (stable_sort):   "
            f"{b_correct_disc}/{len(disc_rows)} correct ({b_pct:.1f}%)"
        )
        print()

        if unique_rows:
            b_u_pct = 100 * b_unique / len(unique_rows)
            a_u_pct = 100 * a_unique / len(unique_rows)
            print(f"UNIQUE sort_size only (deterministic, no tiebreaker needed):")
            print(
                f"  Hypothesis A: {a_unique}/{len(unique_rows)} ({a_u_pct:.1f}%)"
            )
            print(
                f"  Hypothesis B: {b_unique}/{len(unique_rows)} ({b_u_pct:.1f}%)"
            )
            print()

        if tie_rows:
            b_t_pct = 100 * b_tie / len(tie_rows)
            a_t_pct = 100 * a_tie / len(tie_rows)
            print(f"TIE GROUP only (tiebreaker = declaration order in both):")
            print(
                f"  Hypothesis A: {a_tie}/{len(tie_rows)} ({a_t_pct:.1f}%)"
            )
            print(
                f"  Hypothesis B: {b_tie}/{len(tie_rows)} ({b_t_pct:.1f}%)"
            )
            print()

        # Verdict based on unique-sort-size methods (the only truly discriminating ones)
        if unique_rows:
            b_u_pct = 100 * b_unique / len(unique_rows)
            a_u_pct = 100 * a_unique / len(unique_rows)
            if b_u_pct > 80 and b_u_pct > a_u_pct:
                verdict = "Hypothesis B -- stable_sort by streamSize (v14.4.1-style)"
                clear = True
            elif a_u_pct > 80 and a_u_pct > b_u_pct:
                verdict = "Hypothesis A -- no sort (v2.0.1-style declaration order)"
                clear = True
            elif b_pct > a_pct:
                verdict = (
                    "LIKELY Hypothesis B -- stable_sort (better overall, "
                    "tie groups need auto-detector)"
                )
                clear = True
            else:
                verdict = "AMBIGUOUS -- insufficient unique-sort-size ground truth"
                clear = False
        elif b_pct > 80:
            verdict = "Hypothesis B -- stable_sort by streamSize (v14.4.1-style)"
            clear = True
        elif a_pct > 80:
            verdict = "Hypothesis A -- no sort (v2.0.1-style declaration order)"
            clear = True
        else:
            verdict = "AMBIGUOUS -- neither hypothesis reaches 80%"
            clear = False
        print(f"Verdict: {verdict}")
    else:
        print("No discriminating cases found -- cannot determine verdict")
        clear = False
        verdict = "NO DATA"

    # ── INFINITY group analysis ──
    if infinity_rows:
        print()
        print("=" * 80)
        print("INFINITY Group Analysis (variable-size methods, sort_size >= 65536)")
        print("=" * 80)
        inf_disc = [r for r in infinity_rows if r.discriminating]
        inf_a = sum(1 for r in inf_disc if r.a_correct)
        inf_b = sum(1 for r in inf_disc if r.b_correct)
        print(
            f"{'Entity':<10} {'Method':<35} {'VLH':>4} {'Decl':>4} "
            f"{'HypA':>5} {'HypB':>5} {'Obs':>5}  A?  B?"
        )
        for r in infinity_rows:
            minfo = None
            for m in entity_methods[r.entity]:
                if m.name == r.method:
                    minfo = m
                    break
            vlh = minfo.vlh if minfo else "?"
            a_mark = "OK" if r.a_correct else "XX"
            b_mark = "OK" if r.b_correct else "XX"
            print(
                f"{r.entity:<10} {r.method:<35} {vlh:>4} {r.decl_order:>4} "
                f"{r.hyp_a_idx:>5} {r.hyp_b_idx:>5} {r.observed_idx:>5}  "
                f"{a_mark}  {b_mark}"
            )
        if inf_disc:
            print(
                f"\nINFINITY discriminating: A={inf_a}/{len(inf_disc)}, "
                f"B={inf_b}/{len(inf_disc)}"
            )
        else:
            print("\nNo discriminating INFINITY methods (all A==B within VLH group)")

    # ── Detailed hypothesis comparison ──
    print()
    print("=" * 80)
    print("Full Method Ordering Comparison (all methods, not just verified)")
    print("=" * 80)
    for ename, methods in entity_methods.items():
        hyp_a = hypothesis_a(methods)
        hyp_b = hypothesis_b(methods)
        diffs = [(n, hyp_a[n], hyp_b[n]) for n in hyp_a if hyp_a[n] != hyp_b[n]]
        print(f"\n{ename}: {len(methods)} methods, {len(diffs)} differ between A and B")
        if diffs:
            for name, a_idx, b_idx in sorted(diffs, key=lambda x: x[2]):
                marker = ""
                gt = ground_truth.get(ename, {})
                if name in gt:
                    obs = gt[name]
                    if obs == b_idx:
                        marker = " <- verified BOK"
                    elif obs == a_idx:
                        marker = " <- verified AOK"
                    else:
                        marker = f" <- observed={obs} (neither!)"
                print(f"  {name:<40} A={a_idx:<4} B={b_idx:<4}{marker}")

    # ── Build JSON results ──
    results = {
        "total_methods_verified": len(rows),
        "discriminating_cases": len(disc_rows),
        "non_discriminating_cases": len(non_disc),
        "hypothesis_a": {
            "name": "No sort (declaration order)",
            "discriminating_correct": a_correct_disc if disc_rows else 0,
            "total_correct": a_correct_all,
        },
        "hypothesis_b": {
            "name": "stable_sort by streamSize",
            "discriminating_correct": b_correct_disc if disc_rows else 0,
            "total_correct": b_correct_all,
        },
        "verdict": verdict,
        "clear": clear,
        "rows": [
            {
                "entity": r.entity,
                "method": r.method,
                "declaration_order": r.decl_order,
                "hypothesis_a_index": r.hyp_a_idx,
                "hypothesis_b_index": r.hyp_b_idx,
                "observed_index": r.observed_idx,
                "a_correct": r.a_correct,
                "b_correct": r.b_correct,
                "discriminating": r.discriminating,
            }
            for r in rows
        ],
    }

    return results, clear


# ── Main ─────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify BigWorld method sort order against real replays",
    )
    parser.add_argument(
        "--replay-dir",
        type=Path,
        default=_PROJECT_ROOT,
        help="Directory to search for .wowsreplay files (default: project root)",
    )
    parser.add_argument(
        "--gamedata-dir",
        type=Path,
        default=_PROJECT_ROOT / "wows-gamedata" / "data" / "scripts_entity" / "entity_defs",
        help="Path to entity_defs directory",
    )
    parser.add_argument(
        "--entity",
        type=str,
        default="Avatar,Vehicle",
        help="Comma-separated entity names to verify (default: Avatar,Vehicle)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=_PROJECT_ROOT / "verify_method_sort_results.json",
        help="Output JSON file path",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    entity_names = [e.strip() for e in args.entity.split(",")]

    # Find replay files
    replay_dir = args.replay_dir.resolve()
    replays = sorted(replay_dir.glob("*.wowsreplay"))
    if not replays:
        # Also check subdirectories one level deep
        replays = sorted(replay_dir.glob("*/*.wowsreplay"))
    if not replays:
        print(f"ERROR: No .wowsreplay files found in {replay_dir}")
        return 1
    print(f"Found {len(replays)} replay(s) in {replay_dir}")

    # Step 1: Load entity definitions
    print(f"Loading entity definitions from {args.gamedata_dir}...")
    entity_methods, aliases, registry = load_entity_methods(
        args.gamedata_dir, entity_names,
    )
    for ename, methods in entity_methods.items():
        n_fixed = sum(1 for m in methods if not m.is_variable)
        n_var = sum(1 for m in methods if m.is_variable)
        print(f"  {ename}: {len(methods)} methods ({n_fixed} fixed, {n_var} variable)")

    # Step 2: Show hypothesis predictions
    for ename, methods in entity_methods.items():
        hyp_a = hypothesis_a(methods)
        hyp_b = hypothesis_b(methods)
        diffs = sum(1 for n in hyp_a if hyp_a[n] != hyp_b[n])
        print(f"  {ename}: {diffs} methods have different index between A and B")

    # Step 3: Collect ground truth
    print("\nCollecting ground truth from replays...")
    ground_truth = collect_ground_truth(
        replays, registry, aliases, entity_methods,
    )
    total_gt = sum(len(gt) for gt in ground_truth.values())
    print(f"Ground truth: {total_gt} method(s) identified")
    for ename, gt in ground_truth.items():
        if gt:
            print(f"  {ename}: {len(gt)} methods")

    if total_gt == 0:
        print("ERROR: No ground truth collected — cannot verify hypotheses")
        return 1

    # Step 4 & 5: Score and report
    results, clear = score_and_report(entity_methods, ground_truth)

    # Write JSON output
    with open(args.output, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nFull results written to {args.output}")

    return 0 if clear else 1


if __name__ == "__main__":
    sys.exit(main())
