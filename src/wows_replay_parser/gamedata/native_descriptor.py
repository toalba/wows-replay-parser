"""Builds wows_native schema descriptors from BigWorld entity defs.

Walks the AliasRegistry / EntityRegistry that SchemaBuilder also uses,
emitting the dict-descriptor format consumed by wows_native.compile_schema.
Reference: docs/superpowers/specs/2026-04-30-rust-schema-executor-design.md
"""
from __future__ import annotations

import re
from typing import Any

from wows_replay_parser.gamedata.alias_registry import AliasRegistry, TypeAlias
from wows_replay_parser.gamedata.entity_registry import EntityRegistry

_PRIMITIVE_KINDS = {
    "INT8": "int8", "INT16": "int16", "INT32": "int32", "INT64": "int64",
    "UINT8": "uint8", "UINT16": "uint16", "UINT32": "uint32", "UINT64": "uint64",
    "FLOAT": "float32", "FLOAT32": "float32", "FLOAT64": "float64",
    "BOOL": "bool", "MAILBOX": "mailbox",
    "VECTOR2": "vector2", "VECTOR3": "vector3",
}

_VARIABLE_PRIMITIVES = {"STRING", "UNICODE_STRING", "BLOB", "PYTHON"}

_VARIABLE_KIND_MAP = {
    "STRING": "string", "UNICODE_STRING": "unicode_string",
    "BLOB": "blob", "PYTHON": "python",
}


class NativeDescriptorBuilder:
    """Produces wows_native dict descriptors from BigWorld type names + aliases."""

    def __init__(self, aliases: AliasRegistry, registry: EntityRegistry) -> None:
        self._aliases = aliases
        self._registry = registry

    def descriptor_for_type(self, type_name: str, *, in_method: bool = True) -> dict[str, Any]:
        """Resolve a BigWorld type name to a wows_native descriptor.

        ``in_method`` controls the length-prefix mode for variable primitives:
        method-call args use u8/0xFF→u16+pad encoding; property updates and
        inline state use 4-byte u32 prefixes.
        """
        type_name = type_name.strip()
        if type_name in _PRIMITIVE_KINDS:
            return {"kind": _PRIMITIVE_KINDS[type_name]}
        if type_name in _VARIABLE_PRIMITIVES:
            mode = "method" if in_method else "u32"
            return {"kind": _VARIABLE_KIND_MAP[type_name], "mode": mode}
        # alias chain / composites added in Tasks 12 and 13
        raise NotImplementedError(f"descriptor for {type_name!r} not yet implemented")
