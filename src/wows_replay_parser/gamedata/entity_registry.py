"""
Central registry holding all loaded entity definitions.

Acts as the bridge between raw .def data and the schema builder.
Provides lookup by entity name, method index, and property index.

Methods and properties are sorted by their "sort_size" — a BigWorld convention
where the binary index in network packets corresponds to the position in a
size-sorted list, NOT the XML declaration order.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from wows_replay_parser.gamedata.alias_registry import AliasRegistry
from wows_replay_parser.gamedata.def_loader import EntityDef, MethodDef, PropertyDef

# Sentinel for variable-length types (STRING, BLOB, ARRAY with no fixed size, etc.)
INFINITY = 0xFFFF

# BigWorld primitive sort sizes
_PRIM_SORT_SIZE: dict[str, int] = {
    "INT8": 1, "UINT8": 1, "BOOL": 1,
    "INT16": 2, "UINT16": 2,
    "INT32": 4, "UINT32": 4, "FLOAT": 4, "FLOAT32": 4,
    "INT64": 8, "UINT64": 8, "FLOAT64": 8,
    "VECTOR2": 8, "VECTOR3": 12,
    "STRING": INFINITY, "UNICODE_STRING": INFINITY,
    "BLOB": INFINITY, "PYTHON": INFINITY, "MAILBOX": INFINITY,
}


def compute_type_sort_size(type_name: str, aliases: AliasRegistry) -> int:
    """Compute the sort_size for a BigWorld type, resolving aliases recursively."""
    # Primitive
    if type_name in _PRIM_SORT_SIZE:
        return _PRIM_SORT_SIZE[type_name]

    # Inline compound type: "ARRAY<of>FOO</of>" from FIXED_DICT fields
    if type_name.startswith("ARRAY<of>"):
        return INFINITY  # Variable-length arrays are always INFINITY

    # Alias
    alias = aliases.resolve(type_name)
    if alias is None:
        return INFINITY  # Unknown types treated as variable-length

    # BigWorld: implementedBy means a custom Python serializer controls the
    # wire format → FixedDictDataType::streamSize() returns -1 (variable).
    # This applies to FIXED_DICT, USER_TYPE, and simple aliases alike.
    if alias.has_implemented_by:
        return INFINITY

    base = alias.base_type.strip()

    # Simple alias → recurse to the base type
    if base in _PRIM_SORT_SIZE:
        return _PRIM_SORT_SIZE[base]

    # Recursive alias (alias → another alias)
    if base not in ("FIXED_DICT", "ARRAY", "TUPLE") and aliases.has(base):
        return compute_type_sort_size(base, aliases)

    # FIXED_DICT
    if base == "FIXED_DICT":
        if alias.allow_none:
            return INFINITY
        total = 0
        for _, field_type in alias.fields:
            s = compute_type_sort_size(field_type, aliases)
            if s >= INFINITY:
                return INFINITY
            total += s
        return min(total, INFINITY)

    # ARRAY
    if base == "ARRAY":
        if alias.element_type and alias.size is not None:
            elem_size = compute_type_sort_size(alias.element_type, aliases)
            if elem_size >= INFINITY:
                return INFINITY
            return min(alias.size * elem_size, INFINITY)
        return INFINITY

    # TUPLE
    if base == "TUPLE":
        if alias.tuple_types and alias.size is not None:
            elem_size = compute_type_sort_size(alias.tuple_types[0], aliases)
            if elem_size >= INFINITY:
                return INFINITY
            return min(alias.size * elem_size, INFINITY)
        return INFINITY

    return INFINITY


def compute_method_sort_size(method: MethodDef, aliases: AliasRegistry) -> int:
    """Compute sort_size for a method: sum(arg sizes) + variable_length_header_size."""
    total = 0
    for _, arg_type in method.args:
        s = compute_type_sort_size(arg_type, aliases)
        if s >= INFINITY:
            total = INFINITY
            break
        total += s
    result = min(total, INFINITY) + method.variable_length_header_size
    return result


def compute_property_sort_size(prop: PropertyDef, aliases: AliasRegistry) -> int:
    """Compute sort_size for a property."""
    return compute_type_sort_size(prop.type_name, aliases)


@dataclass
class ResolvedEntity:
    """Entity with indexed methods and properties for fast packet lookup."""

    name: str
    # Properties visible in replays (ALL_CLIENTS, OTHER_CLIENTS, OWN_CLIENT)
    client_properties: list[PropertyDef] = field(default_factory=list)
    # Client methods indexed by their position (method ID in packets)
    client_methods_by_index: dict[int, MethodDef] = field(default_factory=dict)
    # All properties for reference
    all_properties: list[PropertyDef] = field(default_factory=list)


# Property flags that appear in replay network packets
CLIENT_VISIBLE_FLAGS = frozenset({
    "ALL_CLIENTS",
    "OTHER_CLIENTS",
    "OWN_CLIENT",
    "BASE_AND_CLIENT",
    "CELL_PUBLIC_AND_OWN",
    "ALL_CLIENTS_AND_CELL_PUBLIC",
})


class EntityRegistry:
    """
    Resolves and indexes entity definitions for fast replay packet decoding.

    Methods and properties are sorted by sort_size to match BigWorld's
    network indexing convention.

    Usage:
        registry = EntityRegistry(alias_registry)
        registry.register(entity_def)
        method = registry.get_client_method("Avatar", 3)
    """

    def __init__(self, aliases: AliasRegistry | None = None) -> None:
        self._entities: dict[str, ResolvedEntity] = {}
        self._type_id_map: dict[int, str] = {}
        self._aliases = aliases

    def register(self, entity_def: EntityDef) -> None:
        """Register an entity definition, sorting methods/properties by sort_size."""
        resolved = ResolvedEntity(name=entity_def.name)
        resolved.all_properties = list(entity_def.properties)

        # Filter client-visible properties
        client_props = [
            p for p in entity_def.properties
            if p.flags in CLIENT_VISIBLE_FLAGS
        ]

        # Compute and sort by sort_size if alias registry is available
        if self._aliases is not None:
            for prop in client_props:
                prop.sort_size = compute_property_sort_size(prop, self._aliases)
            client_props.sort(key=lambda p: p.sort_size)

            for method in entity_def.client_methods:
                method.sort_size = compute_method_sort_size(method, self._aliases)
            sorted_methods = sorted(entity_def.client_methods, key=lambda m: m.sort_size)
        else:
            sorted_methods = list(entity_def.client_methods)

        resolved.client_properties = client_props

        # Index client methods by sorted position
        for i, method in enumerate(sorted_methods):
            resolved.client_methods_by_index[i] = method

        self._entities[entity_def.name] = resolved

    def register_type_id(self, type_id: int, entity_name: str) -> None:
        """Map a BigWorld entity type ID to an entity name."""
        self._type_id_map[type_id] = entity_name

    def get(self, entity_name: str) -> ResolvedEntity | None:
        return self._entities.get(entity_name)

    def get_by_type_id(self, type_id: int) -> ResolvedEntity | None:
        name = self._type_id_map.get(type_id)
        return self._entities.get(name) if name else None

    def get_client_method(self, entity_name: str, method_index: int) -> MethodDef | None:
        entity = self._entities.get(entity_name)
        if entity is None:
            return None
        return entity.client_methods_by_index.get(method_index)

    def get_client_property(self, entity_name: str, prop_index: int) -> PropertyDef | None:
        entity = self._entities.get(entity_name)
        if entity is None or prop_index >= len(entity.client_properties):
            return None
        return entity.client_properties[prop_index]

    def override_method_mapping(
        self, entity_name: str, mapping: dict[int, MethodDef],
    ) -> None:
        """Replace specific method index entries for an entity.

        Used by the Tier 2 auto-detector fallback when .def files are
        unavailable and tie-group ordering must be resolved from packet data.
        """
        entity = self._entities.get(entity_name)
        if entity is not None:
            entity.client_methods_by_index.update(mapping)

    @property
    def entity_names(self) -> list[str]:
        return list(self._entities.keys())

    def __repr__(self) -> str:
        return f"EntityRegistry({len(self._entities)} entities, {len(self._type_id_map)} type IDs)"
