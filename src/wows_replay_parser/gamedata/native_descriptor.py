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
            return {"kind": _VARIABLE_KIND_MAP[type_name], "mode": "method" if in_method else "u32"}

        # Inline ARRAY<of>X</of>
        m = re.match(r"^ARRAY<of>(.+)</of>$", type_name)
        if m:
            return {
                "kind": "array",
                "count_prefix": "uint8",
                "element": self.descriptor_for_type(m.group(1), in_method=in_method),
            }

        # Alias resolution
        alias = self._aliases.resolve(type_name)
        if alias is not None:
            return self._descriptor_for_alias(alias, in_method=in_method)

        raise NotImplementedError(f"descriptor for {type_name!r} not yet implemented")

    def _descriptor_for_alias(self, alias: TypeAlias, *, in_method: bool) -> dict[str, Any]:
        base = alias.base_type.strip()

        # USER_TYPE with implementedBy → marker (variable types only).
        # FIXED_DICT/ARRAY/TUPLE with implementedBy keep their normal struct
        # layout on the wire — only the Python-side deserialization differs,
        # which is handled by post_process via the stored alias.
        if alias.has_implemented_by and base not in ("FIXED_DICT", "ARRAY", "TUPLE"):
            return {
                "kind": "user_type",
                "alias": alias.name,
                "blob_mode": "method" if in_method else "u32",
            }
        if base in _PRIMITIVE_KINDS:
            return {"kind": _PRIMITIVE_KINDS[base]}
        if base in _VARIABLE_PRIMITIVES:
            return {"kind": _VARIABLE_KIND_MAP[base], "mode": "method" if in_method else "u32"}
        # FIXED_DICT/ARRAY/TUPLE composites added in Task 13
        raise NotImplementedError(f"alias {alias.name} (base {base}) not yet supported")
