#!/usr/bin/env python3
"""Inspect all unresolved implementedBy BLOB fields from a real replay.

Collects diagnostics on every method arg or property value that is still
raw bytes or an _AttrObject (permissive pickle fallback).

Usage:
    uv run scripts/inspect_blobs.py <replay_path>
    uv run scripts/inspect_blobs.py test.wowsreplay
"""

from __future__ import annotations

import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# -- Setup paths -------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
GAMEDATA = REPO_ROOT / "wows-gamedata" / "data" / "scripts_entity" / "entity_defs"


# -- Helpers -----------------------------------------------------------

def _is_attr_object(v: Any) -> bool:
    """Check if a value is an _AttrObject instance (dynamic pickle class)."""
    return hasattr(v, "_pickle_module") or (
        hasattr(type(v), "__mro__")
        and any(c.__name__ == "_AttrObject" for c in type(v).__mro__)
    )


def _hex_preview(data: bytes, max_len: int = 64) -> str:
    return data[:max_len].hex()


def _truncate(s: str, max_len: int = 200) -> str:
    return s if len(s) <= max_len else s[:max_len] + "..."


def _collect_nested_attr_objects(v: Any, depth: int = 0) -> list[str]:
    """Recursively find _AttrObject class names in nested structures."""
    if depth > 2:
        return []
    names: list[str] = []
    if _is_attr_object(v):
        names.append(type(v).__name__)
        if hasattr(v, "__dict__"):
            for child in v.__dict__.values():
                names.extend(_collect_nested_attr_objects(child, depth + 1))
    elif isinstance(v, dict):
        for child in v.values():
            names.extend(_collect_nested_attr_objects(child, depth + 1))
    elif isinstance(v, (list, tuple)):
        for child in v:
            names.extend(_collect_nested_attr_objects(child, depth + 1))
    return names


def _is_unresolved(v: Any) -> bool:
    """True if value is raw bytes (>0 length) or an _AttrObject."""
    if isinstance(v, bytes) and len(v) > 0:
        return True
    if _is_attr_object(v):
        return True
    return False


def _walk_value(v: Any) -> list[tuple[str, Any]]:
    """Walk a decoded value and yield (path_suffix, leaf) for unresolved leaves."""
    results: list[tuple[str, Any]] = []
    if _is_unresolved(v):
        results.append(("", v))
    elif isinstance(v, dict):
        for k, child in v.items():
            if isinstance(k, str) and k.startswith("_"):
                continue
            for suffix, leaf in _walk_value(child):
                results.append((f".{k}{suffix}", leaf))
    elif isinstance(v, (list, tuple)):
        for i, child in enumerate(v):
            for suffix, leaf in _walk_value(child):
                results.append((f"[{i}]{suffix}", leaf))
    return results


# -- Data collection ---------------------------------------------------

@dataclass
class BlobRecord:
    alias_name: str
    implemented_by: str | None
    context: str  # e.g. "Avatar.receiveArtilleryShots[arg2]"
    value_type: str  # "raw_bytes" or "_AttrObject subclass: ClassName"
    first_hex: str = ""
    state_keys: list[str] = field(default_factory=list)
    attr_dict: str = ""
    nested_classes: list[str] = field(default_factory=list)
    byte_length: int = 0


@dataclass
class AliasSummary:
    alias_name: str
    implemented_by: str | None
    records: list[BlobRecord] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.records)

    @property
    def contexts(self) -> set[str]:
        return {r.context.rsplit("[", 1)[0] if "[" in r.context else r.context
                for r in self.records}


def _make_record(
    alias_name: str,
    implemented_by: str | None,
    context: str,
    value: Any,
) -> BlobRecord:
    rec = BlobRecord(
        alias_name=alias_name,
        implemented_by=implemented_by,
        context=context,
        value_type="raw_bytes",
    )
    if isinstance(value, bytes):
        rec.value_type = f"raw bytes ({len(value)} bytes)"
        rec.first_hex = _hex_preview(value)
        rec.byte_length = len(value)
    elif _is_attr_object(value):
        cls_name = type(value).__name__
        rec.value_type = f"_AttrObject subclass: {cls_name}"
        if hasattr(value, "state") and isinstance(value.state, dict):
            rec.state_keys = list(value.state.keys())
        if hasattr(value, "__dict__"):
            d = {k: v for k, v in value.__dict__.items()
                 if not k.startswith("_pickle_") and k not in ("args", "kwargs")}
            rec.attr_dict = _truncate(repr(d))
        rec.nested_classes = list(set(_collect_nested_attr_objects(value)))
    return rec


def collect_from_replay(replay_path: Path) -> dict[str, AliasSummary]:
    """Parse replay and collect all unresolved BLOB diagnostics."""
    from wows_replay_parser.api import parse_replay
    from wows_replay_parser.gamedata.alias_registry import AliasRegistry
    from wows_replay_parser.gamedata.blob_decoders import METHOD_BLOB_OVERRIDES
    from wows_replay_parser.gamedata.def_loader import DefLoader
    from wows_replay_parser.gamedata.entity_registry import EntityRegistry
    from wows_replay_parser.packets.types import PacketType

    # Use the full pipeline so type mapping, method ordering, etc. are correct
    parsed = parse_replay(str(replay_path), str(GAMEDATA))
    packets = parsed.packets

    # Reload alias registry + entity registry for alias lookups
    aliases = AliasRegistry.from_file(GAMEDATA / "alias.xml")
    loader = DefLoader(GAMEDATA)
    entity_defs = loader.load_all()
    registry = EntityRegistry(aliases)
    for ed in entity_defs.values():
        registry.register(ed)

    print(f"Parsed {len(packets)} packets")

    summaries: dict[str, AliasSummary] = {}

    def _add(alias_name: str, impl_by: str | None, context: str, value: Any) -> None:
        rec = _make_record(alias_name, impl_by, context, value)
        if alias_name not in summaries:
            summaries[alias_name] = AliasSummary(alias_name, impl_by)
        summaries[alias_name].records.append(rec)

    # -- Scan method args ----------------------------------------------
    for pkt in packets:
        if pkt.type != PacketType.ENTITY_METHOD:
            continue
        if pkt.method_args is None or pkt.entity_type is None or pkt.method_name is None:
            continue

        # Look up method definition to map arg names → types → aliases
        entity = registry._entities.get(pkt.entity_type)
        if entity is None:
            continue

        # Find the MethodDef by name
        method_def = None
        for m in entity.client_methods_by_index.values():
            if m.name == pkt.method_name:
                method_def = m
                break
        if method_def is None:
            continue

        # Build arg_name → type_name map
        arg_type_map: dict[str, str] = {}
        for arg_name, arg_type in method_def.args:
            label = arg_name if not arg_name.isdigit() else f"arg{arg_name}"
            arg_type_map[label] = arg_type

        for arg_name, arg_value in pkt.method_args.items():
            if isinstance(arg_name, str) and arg_name.startswith("_"):
                continue

            # Check for unresolved leaves
            leaves = _walk_value(arg_value)
            if not leaves:
                continue

            # Resolve the alias for this arg
            arg_type_name = arg_type_map.get(arg_name)
            if arg_type_name is None:
                continue

            # Check METHOD_BLOB_OVERRIDES
            override = METHOD_BLOB_OVERRIDES.get((pkt.method_name, arg_name))
            if override:
                alias = aliases.resolve(override)
            else:
                alias = aliases.resolve(arg_type_name)

            alias_name = alias.name if alias else arg_type_name
            impl_by = alias.implemented_by if alias else None

            for suffix, leaf in leaves:
                ctx = f"{pkt.entity_type}.{pkt.method_name}[{arg_name}{suffix}]"
                _add(alias_name, impl_by, ctx, leaf)

    # -- Scan property values ------------------------------------------
    for pkt in packets:
        if pkt.type == PacketType.ENTITY_PROPERTY:
            if pkt.property_value is None or pkt.entity_type is None or pkt.property_name is None:
                continue
            leaves = _walk_value(pkt.property_value)
            if not leaves:
                continue

            # Find the property def
            entity = registry._entities.get(pkt.entity_type)
            if entity is None:
                continue
            prop_def = None
            for p in entity.client_properties:
                if p.name == pkt.property_name:
                    prop_def = p
                    break
            if prop_def is None:
                continue

            alias = aliases.resolve(prop_def.type_name)
            alias_name = alias.name if alias else prop_def.type_name
            impl_by = alias.implemented_by if alias else None

            for suffix, leaf in leaves:
                ctx = f"{pkt.entity_type}.Properties.{pkt.property_name}{suffix}"
                _add(alias_name, impl_by, ctx, leaf)

        # -- Scan inline state (ENTITY_CREATE) -------------------------
        elif pkt.type == PacketType.ENTITY_CREATE:
            if pkt.initial_properties is None or pkt.entity_type is None:
                continue
            entity = registry._entities.get(pkt.entity_type)
            if entity is None:
                continue

            for prop_name, prop_value in pkt.initial_properties.items():
                leaves = _walk_value(prop_value)
                if not leaves:
                    continue
                prop_def = None
                for p in entity.client_properties:
                    if p.name == prop_name:
                        prop_def = p
                        break
                if prop_def is None:
                    continue

                alias = aliases.resolve(prop_def.type_name)
                alias_name = alias.name if alias else prop_def.type_name
                impl_by = alias.implemented_by if alias else None

                for suffix, leaf in leaves:
                    ctx = f"{pkt.entity_type}.InlineState.{prop_name}{suffix}"
                    _add(alias_name, impl_by, ctx, leaf)

    # -- Scan for implementedBy properties that failed to parse ---------
    # These are properties where the schema parse itself failed (property_value
    # is None) because _DecodedBlob wraps the raw BLOB but the schema around
    # it may have changed the wire format expectations.  We detect these by
    # finding ENTITY_PROPERTY packets with property_name set but property_value
    # is None, and checking if the property type has implementedBy.
    failed_props: dict[str, list[tuple[str, str, bytes]]] = defaultdict(list)
    for pkt in packets:
        if pkt.type != PacketType.ENTITY_PROPERTY:
            continue
        if pkt.property_name is None or pkt.entity_type is None:
            continue
        if pkt.property_value is not None:
            continue  # parsed OK

        entity = registry._entities.get(pkt.entity_type)
        if entity is None:
            continue
        prop_def = None
        for p in entity.client_properties:
            if p.name == pkt.property_name:
                prop_def = p
                break
        if prop_def is None:
            continue

        alias = aliases.resolve(prop_def.type_name)
        if alias is None or not alias.has_implemented_by:
            continue

        # Extract raw property data (skip 12-byte header: eid + pid + len)
        raw = pkt.raw_payload[12:] if len(pkt.raw_payload) > 12 else b""
        key = f"{alias.name}|{alias.implemented_by or ''}"
        failed_props[key].append((pkt.entity_type, pkt.property_name, raw))

    # Also scan method calls where method_args is None
    failed_methods: dict[str, list[tuple[str, str, bytes]]] = defaultdict(list)
    for pkt in packets:
        if pkt.type != PacketType.ENTITY_METHOD:
            continue
        if pkt.method_name is None or pkt.entity_type is None:
            continue
        if pkt.method_args is not None:
            continue  # parsed OK

        entity = registry._entities.get(pkt.entity_type)
        if entity is None:
            continue
        method_def = None
        for m in entity.client_methods_by_index.values():
            if m.name == pkt.method_name:
                method_def = m
                break
        if method_def is None:
            continue

        # Check if any arg type has implementedBy
        has_impl_arg = False
        for arg_name, arg_type in method_def.args:
            a = aliases.resolve(arg_type)
            if a and a.has_implemented_by:
                has_impl_arg = True
                key = f"{a.name}|{a.implemented_by or ''}"
                raw = pkt.raw_payload[12:] if len(pkt.raw_payload) > 12 else b""
                failed_methods[key].append((pkt.entity_type, pkt.method_name, raw))
                break

    return summaries, failed_props, failed_methods


# -- Report ------------------------------------------------------------

def print_report(
    summaries: dict[str, AliasSummary],
    failed_props: dict[str, list[tuple[str, str, bytes]]],
    failed_methods: dict[str, list[tuple[str, str, bytes]]],
) -> None:
    sorted_aliases = sorted(summaries.values(), key=lambda s: s.count, reverse=True)

    print("\n" + "=" * 78)
    print("SECTION 1: UNRESOLVED VALUES IN DECODED PACKETS")
    print("=" * 78)

    total = sum(s.count for s in sorted_aliases)
    print(f"\nTotal unresolved values: {total}")
    print(f"Distinct alias names: {len(sorted_aliases)}\n")

    for summary in sorted_aliases:
        impl = summary.implemented_by or "(no implementedBy)"
        print(f"\n{'-' * 78}")
        print(f"{summary.alias_name} ({impl}) -- {summary.count} occurrences")
        print(f"{'-' * 78}")

        # Unique contexts
        contexts = summary.contexts
        print(f"  contexts ({len(contexts)}):")
        for ctx in sorted(contexts):
            ctx_count = sum(1 for r in summary.records if
                           (r.context.rsplit("[", 1)[0] if "[" in r.context else r.context) == ctx)
            print(f"    {ctx}  ({ctx_count}x)")

        # Group by value type
        type_counts: dict[str, int] = defaultdict(int)
        for r in summary.records:
            type_counts[r.value_type] += 1
        print(f"  value types:")
        for vt, cnt in sorted(type_counts.items(), key=lambda x: -x[1]):
            print(f"    {vt}  ({cnt}x)")

        # First record details
        first = summary.records[0]
        if first.first_hex:
            print(f"  first bytes (hex): {first.first_hex}")
        if first.state_keys:
            print(f"  state keys: {first.state_keys}")
        if first.attr_dict:
            print(f"  attr dict: {first.attr_dict}")
        if first.nested_classes:
            nested = [c for c in first.nested_classes if c != type(first).__name__]
            if nested:
                print(f"  nested _AttrObject classes: {nested}")

        # Byte length distribution for raw bytes
        byte_records = [r for r in summary.records if r.byte_length > 0]
        if byte_records:
            lengths = [r.byte_length for r in byte_records]
            print(f"  byte lengths: min={min(lengths)}, max={max(lengths)}, "
                  f"median={sorted(lengths)[len(lengths)//2]}")

            # Show a few distinct hex prefixes
            prefixes = list({r.first_hex[:32] for r in byte_records})[:5]
            if len(prefixes) > 1:
                print(f"  distinct hex prefixes (first 16 bytes):")
                for p in prefixes:
                    print(f"    {p}")

    # -- Section 2: Failed property/method parses with implementedBy ---
    if failed_props or failed_methods:
        print(f"\n\n{'=' * 78}")
        print("SECTION 2: SCHEMA PARSE FAILURES (implementedBy types)")
        print("=" * 78)
        print("\nThese are properties/methods where the construct schema failed")
        print("entirely (property_value/method_args is None). The implementedBy")
        print("guard in _resolve_alias may have changed wire format expectations.\n")

        for key, entries in sorted(failed_props.items(), key=lambda x: -len(x[1])):
            alias_name, impl_by = key.split("|", 1)
            impl_by = impl_by or "(no implementedBy)"
            print(f"\n{'-' * 78}")
            print(f"{alias_name} ({impl_by}) -- {len(entries)} FAILED property updates")
            print(f"{'-' * 78}")

            # Group by context
            ctx_counts: dict[str, int] = defaultdict(int)
            for etype, pname, _ in entries:
                ctx_counts[f"{etype}.Properties.{pname}"] += 1
            print(f"  contexts:")
            for ctx, cnt in sorted(ctx_counts.items(), key=lambda x: -x[1]):
                print(f"    {ctx}  ({cnt}x)")

            # Show first raw payload
            first_raw = entries[0][2]
            if first_raw:
                print(f"  first raw payload ({len(first_raw)} bytes): {first_raw[:64].hex()}")

        for key, entries in sorted(failed_methods.items(), key=lambda x: -len(x[1])):
            alias_name, impl_by = key.split("|", 1)
            impl_by = impl_by or "(no implementedBy)"
            print(f"\n{'-' * 78}")
            print(f"{alias_name} ({impl_by}) -- {len(entries)} FAILED method calls")
            print(f"{'-' * 78}")

            ctx_counts = defaultdict(int)
            for etype, mname, _ in entries:
                ctx_counts[f"{etype}.{mname}"] += 1
            print(f"  contexts:")
            for ctx, cnt in sorted(ctx_counts.items(), key=lambda x: -x[1]):
                print(f"    {ctx}  ({cnt}x)")

            first_raw = entries[0][2]
            if first_raw:
                print(f"  first raw payload ({len(first_raw)} bytes): {first_raw[:64].hex()}")


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <replay_path>")
        sys.exit(1)

    replay_path = Path(sys.argv[1])
    if not replay_path.exists():
        # Try relative to repo root
        replay_path = REPO_ROOT / sys.argv[1]
    if not replay_path.exists():
        print(f"Replay not found: {sys.argv[1]}")
        sys.exit(1)

    print(f"Inspecting: {replay_path}")
    summaries, failed_props, failed_methods = collect_from_replay(replay_path)
    print_report(summaries, failed_props, failed_methods)


if __name__ == "__main__":
    main()
