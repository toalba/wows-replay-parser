"""
Builds `construct` schemas dynamically from entity definitions + alias registry.

Given the resolved entity defs and alias registry, this module creates
binary parsers (construct.Struct) for each entity's properties and methods.

The key insight from alias.xml:
- Simple aliases map to primitives: ENTITY_ID → INT32, PLAYER_ID → INT32
- FIXED_DICT aliases map to ordered structs with named fields
- ARRAY aliases map to length-prefixed arrays
- USER_TYPE aliases (ZIPPED_BLOB, MSGPACK_BLOB, etc.) need special handling
- TUPLE aliases are fixed-size arrays

BigWorld serialization order:
- Properties are serialized in the order they appear in the .def file
- Method args are serialized in order of <Arg> elements
- FIXED_DICT fields serialize in order of <Properties> children
- ARRAY is prefixed with a count (typically uint8 or uint16)
"""

from __future__ import annotations

from typing import Any

import construct as cs

from wows_replay_parser.gamedata.alias_registry import AliasRegistry, TypeAlias
from wows_replay_parser.gamedata.def_loader import MethodDef, PropertyDef
from wows_replay_parser.gamedata.entity_registry import EntityRegistry


# BigWorld primitive type → construct mapping
PRIMITIVE_MAP: dict[str, cs.Construct[Any, Any]] = {
    "INT8": cs.Int8sl,
    "INT16": cs.Int16sl,
    "INT32": cs.Int32sl,
    "INT64": cs.Int64sl,
    "UINT8": cs.Int8ul,
    "UINT16": cs.Int16ul,
    "UINT32": cs.Int32ul,
    "UINT64": cs.Int64ul,
    "FLOAT": cs.Float32l,
    "FLOAT32": cs.Float32l,
    "FLOAT64": cs.Float64l,
    "BOOL": cs.Int8ul,  # BOOL is aliased to UINT8 in alias.xml
    "STRING": cs.PascalString(cs.Int32ul, "utf-8"),
    "UNICODE_STRING": cs.PascalString(cs.Int32ul, "utf-8"),
    "BLOB": cs.Prefixed(cs.Int32ul, cs.GreedyBytes),
    "PYTHON": cs.Prefixed(cs.Int32ul, cs.GreedyBytes),  # pickled Python object
    "MAILBOX": cs.Bytes(0),  # Mailbox is server-internal, skip in replays
    "VECTOR2": cs.Struct("x" / cs.Float32l, "y" / cs.Float32l),
    "VECTOR3": cs.Struct("x" / cs.Float32l, "y" / cs.Float32l, "z" / cs.Float32l),
}


class SchemaBuilder:
    """
    Dynamically builds construct schemas from entity definitions.

    Usage:
        builder = SchemaBuilder(alias_registry, entity_registry)
        schema = builder.build_method_schema("Avatar", 0)
        schema = builder.build_property_schema("Vehicle", 3)
    """

    def __init__(self, aliases: AliasRegistry, entities: EntityRegistry) -> None:
        self._aliases = aliases
        self._entities = entities
        self._cache: dict[str, cs.Construct[Any, Any]] = {}

    def resolve_type(self, type_name: str) -> cs.Construct[Any, Any]:
        """
        Resolve a type name to a construct schema.

        Resolution order:
        1. Check primitive map
        2. Check alias registry → recurse
        3. Handle ARRAY, FIXED_DICT, TUPLE inline definitions
        """
        # Cache hit
        if type_name in self._cache:
            return self._cache[type_name]

        # Primitive
        if type_name in PRIMITIVE_MAP:
            return PRIMITIVE_MAP[type_name]

        # Alias
        alias = self._aliases.resolve(type_name)
        if alias is not None:
            schema = self._resolve_alias(alias)
            self._cache[type_name] = schema
            return schema

        # Inline compound type: "ARRAY<of>FOO</of>" from FIXED_DICT fields
        import re
        m = re.match(r"^ARRAY<of>(.+)</of>$", type_name)
        if m:
            elem = self.resolve_type(m.group(1))
            schema = cs.PrefixedArray(cs.Int8ul, elem)
            self._cache[type_name] = schema
            return schema

        # Unknown — treat as opaque blob
        return cs.Prefixed(cs.Int32ul, cs.GreedyBytes)

    def _resolve_alias(self, alias: TypeAlias) -> cs.Construct[Any, Any]:
        """Resolve a TypeAlias to a construct schema."""
        base = alias.base_type.strip()

        # Simple alias to a primitive: e.g. ENTITY_ID → INT32
        if base in PRIMITIVE_MAP:
            return PRIMITIVE_MAP[base]

        # FIXED_DICT: ordered struct
        if base == "FIXED_DICT":
            fields: list[cs.Construct[Any, Any]] = []
            for field_name, field_type in alias.fields:
                fields.append(field_name / self.resolve_type(field_type))
            return cs.Struct(*fields)

        # ARRAY: length-prefixed
        if base == "ARRAY" and alias.element_type:
            elem = self.resolve_type(alias.element_type)
            return cs.PrefixedArray(cs.Int8ul, elem)

        # TUPLE: fixed-size array
        if base == "TUPLE" and alias.tuple_types:
            elems = [self.resolve_type(t) for t in alias.tuple_types]
            return cs.Struct(*[f"_{i}" / e for i, e in enumerate(elems)])

        # USER_TYPE: most are BLOB-based (ZIPPED_BLOB, MSGPACK_BLOB, etc.)
        if base == "USER_TYPE":
            # Check if there's a <Type> hint in the alias
            if alias.fields:
                # Some USER_TYPEs specify an underlying type
                for _, ft in alias.fields:
                    return self.resolve_type(ft)
            return cs.Prefixed(cs.Int32ul, cs.GreedyBytes)

        # Recursive alias (alias references another alias)
        if self._aliases.has(base):
            return self.resolve_type(base)

        return cs.Prefixed(cs.Int32ul, cs.GreedyBytes)

    def build_method_schema(self, entity_name: str, method_index: int) -> cs.Construct[Any, Any] | None:
        """Build a schema for a specific client method's arguments."""
        method = self._entities.get_client_method(entity_name, method_index)
        if method is None:
            return None
        return self._build_method_args_schema(method)

    def _build_method_args_schema(self, method: MethodDef) -> cs.Construct[Any, Any]:
        """Build a struct from a method's argument list."""
        if not method.args:
            return cs.Struct()

        fields: list[cs.Construct[Any, Any]] = []
        for arg_name, arg_type in method.args:
            label = arg_name if not arg_name.isdigit() else f"arg{arg_name}"
            fields.append(label / self.resolve_type(arg_type))

        return cs.Struct(*fields)

    def build_property_schema(self, entity_name: str, prop_index: int) -> cs.Construct[Any, Any] | None:
        """Build a schema for a specific property."""
        prop = self._entities.get_client_property(entity_name, prop_index)
        if prop is None:
            return None
        return self.resolve_type(prop.type_name)
