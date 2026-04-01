"""
Bit-packed nested property update decoder.

NestedProperty (0x23) packets update individual fields within complex
properties (FIXED_DICT, ARRAY). The payload after the header is a
bit-packed path through the property's type structure:

    cont(1 bit) + prop_idx(N bits) + [cont(1 bit) + field_idx(M bits)]...

Where N = ceil(log2(num_client_properties)) and M = ceil(log2(num_fields)).

cont=1 means "descend deeper into this field's sub-structure".
cont=0 means "apply the update value at this level".
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from wows_replay_parser.gamedata.alias_registry import AliasRegistry


class BitReader:
    """Read individual bits from a byte buffer (MSB first)."""

    def __init__(self, data: bytes) -> None:
        self._data = data
        self._bit_pos = 0

    def read_bits(self, count: int) -> int:
        """Read `count` bits and return as integer."""
        result = 0
        for _ in range(count):
            byte_idx = self._bit_pos // 8
            bit_idx = 7 - (self._bit_pos % 8)  # MSB first
            if byte_idx < len(self._data):
                result = (result << 1) | ((self._data[byte_idx] >> bit_idx) & 1)
            else:
                result <<= 1
            self._bit_pos += 1
        return result

    def remaining_bytes(self) -> bytes:
        """Return remaining data as bytes, aligned to next byte boundary."""
        byte_pos = (self._bit_pos + 7) // 8
        return self._data[byte_pos:]


_bits_for_count_cache: dict[int, int] = {}


def _bits_for_count(count: int) -> int:
    """Number of bits needed to represent indices 0..count-1."""
    cached = _bits_for_count_cache.get(count)
    if cached is not None:
        return cached
    if count <= 1:
        result = 1
    else:
        result = math.ceil(math.log2(count))
    _bits_for_count_cache[count] = result
    return result


_type_structure_cache: dict[str, dict[str, Any] | None] = {}


def _resolve_type_structure(
    type_name: str, aliases: AliasRegistry,
) -> dict[str, Any] | None:
    """Resolve a type name to its structure description for nested navigation.

    Returns a dict describing the type:
        {"kind": "dict", "fields": [(name, type_name), ...]}
        {"kind": "array", "element_type": type_name}
        {"kind": "leaf", "type_name": type_name}
    or None if unresolvable.
    """
    cached = _type_structure_cache.get(type_name)
    if cached is not None:
        return cached
    if type_name in _type_structure_cache:
        return None  # explicitly cached as None

    result = _resolve_type_structure_impl(type_name, aliases)
    _type_structure_cache[type_name] = result
    return result


def _resolve_type_structure_impl(
    type_name: str, aliases: AliasRegistry,
) -> dict[str, Any] | None:
    """Uncached implementation of _resolve_type_structure."""
    # Handle inline ARRAY<of>ELEMENT_TYPE</of> syntax (not in alias registry)
    if type_name.startswith("ARRAY<of>") and type_name.endswith("</of>"):
        element_type = type_name[9:-5]  # strip ARRAY<of> and </of>
        return {"kind": "array", "element_type": element_type}

    alias = aliases.resolve(type_name)
    if alias is None:
        return None

    if alias.base_type == "FIXED_DICT":
        return {"kind": "dict", "fields": list(alias.fields)}

    if alias.base_type == "ARRAY":
        return {"kind": "array", "element_type": alias.element_type or "BLOB"}

    if alias.base_type == "TUPLE":
        return {"kind": "array", "element_type": alias.element_type or "BLOB"}

    # Simple/primitive type — leaf node
    return {"kind": "leaf", "type_name": type_name}
