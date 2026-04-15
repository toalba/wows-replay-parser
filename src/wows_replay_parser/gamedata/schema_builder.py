"""
Builds `construct` schemas dynamically from entity definitions + alias registry.

BigWorld serialization encoding (verified against real replays):

ARRAY count prefix:
  Always u8 (at ALL nesting levels). No VLH escalation for array counts.

STRING/BLOB length prefix (inside method calls):
  u8 length, if 0xFF → u16 length + 1 unknown padding byte.

For property updates (ENTITY_PROPERTY packets):
  Standard u32 prefix for BLOB/STRING (no VLH — each property is sent
  with its own u32 payload_length in the packet header).

FIXED_DICT with AllowNone:
  u8 flag: 0x00 = None, nonzero = data follows.
"""

from __future__ import annotations

import re
from typing import Any

import construct as cs

from wows_replay_parser.gamedata.alias_registry import AliasRegistry, TypeAlias
from wows_replay_parser.gamedata.blob_decoders import decode_blob, decode_pickle, decode_zipped
from wows_replay_parser.gamedata.def_loader import MethodDef, PropertyDef
from wows_replay_parser.gamedata.entity_registry import EntityRegistry


# ── Custom constructs for BigWorld wire format ─────────────────────

class _MethodBlobPrefixed(cs.Construct):
    """Length-prefixed BLOB/STRING for method args.

    Encoding: u8 length, if 0xFF → u16 length + 1 unknown byte.
    """

    def __init__(self, subcon: cs.Construct[Any, Any]) -> None:
        super().__init__()
        self.subcon = subcon
        self.flagbuildnone = getattr(subcon, "flagbuildnone", False)

    def _parse(self, stream: Any, context: Any, path: str) -> Any:
        first = cs.stream_read(stream, 1, path)[0]
        if first < 0xFF:
            length = first
        else:
            length = int.from_bytes(cs.stream_read(stream, 2, path), "little")
            _unknown = cs.stream_read(stream, 1, path)  # padding byte
        data = cs.stream_read(stream, length, path)
        if self.subcon is cs.GreedyBytes:
            return data
        return self.subcon.parse(data, **context)

    def _sizeof(self, context: Any, path: str) -> int:
        raise cs.SizeofError("MethodBlobPrefixed is variable size")


class _AllowNone(cs.Construct):
    """Wraps a construct with a u8 flag: 0=None, nonzero=parse subcon."""

    def __init__(self, subcon: cs.Construct[Any, Any]) -> None:
        super().__init__()
        self.subcon = subcon
        self.flagbuildnone = True

    def _parse(self, stream: Any, context: Any, path: str) -> Any:
        flag = cs.stream_read(stream, 1, path)[0]
        if flag == 0:
            return None
        return self.subcon._parsereport(stream, context, path)

    def _sizeof(self, context: Any, path: str) -> int:
        raise cs.SizeofError("AllowNone is variable size")


class _DecodedBlob(cs.Construct):
    """Wraps a BLOB construct and decodes the raw bytes at parse time."""

    def __init__(self, subcon: cs.Construct, alias: TypeAlias) -> None:
        super().__init__()
        self.subcon = subcon
        self.alias = alias

    def _parse(self, stream: Any, context: Any, path: str) -> Any:
        raw = self.subcon._parsereport(stream, context, path)
        return decode_blob(self.alias, raw)

    def _sizeof(self, context: Any, path: str) -> int:
        raise cs.SizeofError("DecodedBlob is variable size")


class _AutoPickleBlob(cs.Construct):
    """Wraps a raw BLOB and auto-decodes pickle if the data starts with
    a pickle protocol header (0x80). Returns raw bytes otherwise."""

    def __init__(self, subcon: cs.Construct) -> None:
        super().__init__()
        self.subcon = subcon

    def _parse(self, stream: Any, context: Any, path: str) -> Any:
        raw = self.subcon._parsereport(stream, context, path)
        if isinstance(raw, bytes) and len(raw) >= 2:
            if raw[0] == 0x80:
                return decode_pickle(raw)
            if raw[0] == 0x78:
                return decode_zipped(raw)
        return raw

    def _sizeof(self, context: Any, path: str) -> int:
        raise cs.SizeofError("AutoPickleBlob is variable size")


# ── Primitive type maps ────────────────────────────────────────────

# Fixed-size types — same in methods and properties
FIXED_PRIMITIVES: dict[str, cs.Construct[Any, Any]] = {
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
    "BOOL": cs.Int8ul,
    "MAILBOX": cs.Bytes(0),
    "VECTOR2": cs.Struct("x" / cs.Float32l, "y" / cs.Float32l),
    "VECTOR3": cs.Struct("x" / cs.Float32l, "y" / cs.Float32l, "z" / cs.Float32l),
}

# Variable-length types that need length prefix
_VARIABLE_TYPES = frozenset({"BLOB", "PYTHON", "STRING", "UNICODE_STRING"})


class SchemaBuilder:
    """Dynamically builds construct schemas from entity definitions.

    Method schemas use u8/u16 escalating prefix for BLOB/STRING, u8 for
    ARRAY counts. Property schemas use u32 prefix for BLOB/STRING.
    """

    def __init__(self, aliases: AliasRegistry, entities: EntityRegistry) -> None:
        self._aliases = aliases
        self._entities = entities
        # Per-instance schema caches — safe because fresh instances per replay
        self._method_cache: dict[tuple[str, int], cs.Construct | None] = {}
        self._property_cache: dict[tuple[str, int], cs.Construct | None] = {}
        self._inline_property_cache: dict[tuple[str, int], cs.Construct | None] = {}
        self._type_cache: dict[tuple[str, bool], cs.Construct] = {}

    def build_method_schema(
        self, entity_name: str, method_index: int,
    ) -> cs.Construct[Any, Any] | None:
        """Build a schema for a specific client method's arguments."""
        key = (entity_name, method_index)
        cached = self._method_cache.get(key)
        if cached is not None:
            return cached
        if key in self._method_cache:
            return None  # explicitly cached as None
        method = self._entities.get_client_method(entity_name, method_index)
        if method is None:
            self._method_cache[key] = None
            return None
        result = self._build_args_schema(method.args, in_method=True)
        self._method_cache[key] = result
        return result

    def build_property_schema(
        self, entity_name: str, prop_index: int,
    ) -> cs.Construct[Any, Any] | None:
        """Build a schema for a specific property value.

        Properties use u32 prefix for BLOB/STRING (standard encoding).
        """
        key = (entity_name, prop_index)
        cached = self._property_cache.get(key)
        if cached is not None:
            return cached
        if key in self._property_cache:
            return None
        prop = self._entities.get_client_property(entity_name, prop_index)
        if prop is None:
            self._property_cache[key] = None
            return None
        result = self._resolve_type(prop.type_name, in_method=False)
        self._property_cache[key] = result
        return result

    def build_inline_property_schema(
        self, entity_name: str, prop_index: int,
    ) -> cs.Construct[Any, Any] | None:
        """Build a schema for an inline state property value.

        Inline state (EntityCreate) uses vlh encoding for variable-length
        types (same as method args: u8/u16 escalating prefix, not u32).
        """
        key = (entity_name, prop_index)
        cached = self._inline_property_cache.get(key)
        if cached is not None:
            return cached
        if key in self._inline_property_cache:
            return None
        prop = self._entities.get_client_property(entity_name, prop_index)
        if prop is None:
            self._inline_property_cache[key] = None
            return None
        result = self._resolve_type(prop.type_name, in_method=True)
        self._inline_property_cache[key] = result
        return result

    def _build_args_schema(
        self, args: list[tuple[str, str]], *, in_method: bool,
    ) -> cs.Construct[Any, Any]:
        """Build a struct from a method's argument list."""
        if not args:
            return cs.Struct()

        fields: list[cs.Construct[Any, Any]] = []
        for arg_name, arg_type in args:
            label = arg_name if not arg_name.isdigit() else f"arg{arg_name}"
            con = self._resolve_type(arg_type, in_method=in_method)
            # Wrap plain BLOB args with auto-pickle detection so any
            # BLOB that happens to contain pickle data gets decoded
            # automatically without needing explicit overrides.
            if arg_type in ("BLOB", "PYTHON") and not isinstance(con, _DecodedBlob):
                con = _AutoPickleBlob(con)
            fields.append(label / con)
        return cs.Struct(*fields)

    def _resolve_type(
        self, type_name: str, *, in_method: bool,
    ) -> cs.Construct[Any, Any]:
        """Resolve a type name to a construct schema.

        Args:
            type_name: The type name from the .def/.xml file.
            in_method: True = inside a method call (use u8/u16 blob prefix),
                       False = property update (use u32 blob prefix).
        """
        key = (type_name, in_method)
        cached = self._type_cache.get(key)
        if cached is not None:
            return cached

        result = self._resolve_type_impl(type_name, in_method=in_method)
        self._type_cache[key] = result
        return result

    def _resolve_type_impl(
        self, type_name: str, *, in_method: bool,
    ) -> cs.Construct[Any, Any]:
        """Resolve a type name to a construct schema (uncached implementation)."""
        # Fixed primitive
        if type_name in FIXED_PRIMITIVES:
            return FIXED_PRIMITIVES[type_name]

        # Variable-length primitive (BLOB, STRING)
        if type_name in _VARIABLE_TYPES:
            return self._make_blob_construct(type_name, in_method=in_method)

        # Alias
        alias = self._aliases.resolve(type_name)
        if alias is not None:
            return self._resolve_alias(alias, in_method=in_method)

        # Inline compound: ARRAY<of>FOO</of>
        m = re.match(r"^ARRAY<of>(.+)</of>$", type_name)
        if m:
            elem = self._resolve_type(m.group(1), in_method=in_method)
            return cs.PrefixedArray(cs.Int8ul, elem)

        # Unknown — treat as opaque blob
        return self._make_blob_construct("BLOB", in_method=in_method)

    def _resolve_alias(
        self, alias: TypeAlias, *, in_method: bool,
    ) -> cs.Construct[Any, Any]:
        """Resolve a TypeAlias to a construct schema."""
        base = alias.base_type.strip()

        # implementedBy aliases → decode the BLOB at parse time.
        # FIXED_DICT/ARRAY/TUPLE with implementedBy still use normal struct
        # layout on the wire — only the Python-side deserialization differs.
        # USER_TYPE aliases (BLOB, UINT16, etc.) use VLH encoding on the wire
        # regardless of property vs method context (always in_method=True).
        if alias.has_implemented_by and base not in ("FIXED_DICT", "ARRAY", "TUPLE"):
            raw_con = self._make_blob_construct(
                base if base in _VARIABLE_TYPES else "BLOB", in_method=True,
            )
            return _DecodedBlob(raw_con, alias)

        # Simple alias to a fixed primitive (ENTITY_ID → INT32)
        if base in FIXED_PRIMITIVES:
            return FIXED_PRIMITIVES[base]

        # Simple alias to a variable primitive (some alias → BLOB)
        if base in _VARIABLE_TYPES:
            return self._make_blob_construct(base, in_method=in_method)

        # FIXED_DICT: ordered struct, optionally AllowNone
        if base == "FIXED_DICT":
            fields: list[cs.Construct[Any, Any]] = []
            for field_name, field_type in alias.fields:
                fields.append(
                    field_name / self._resolve_type(field_type, in_method=in_method)
                )
            struct = cs.Struct(*fields)
            if alias.allow_none:
                return _AllowNone(struct)
            return struct

        # ARRAY: u8-prefixed count + elements (always u8, never vlh)
        if base == "ARRAY" and alias.element_type:
            elem = self._resolve_type(alias.element_type, in_method=in_method)
            return cs.PrefixedArray(cs.Int8ul, elem)

        # TUPLE: fixed-size array (no count prefix, size is known)
        if base == "TUPLE" and alias.tuple_types:
            elems = [self._resolve_type(t, in_method=in_method) for t in alias.tuple_types]
            return cs.Struct(*[f"_{i}" / e for i, e in enumerate(elems)])

        # USER_TYPE: resolve to underlying type (BLOB, ZIPPED_BLOB, etc.)
        if base == "USER_TYPE":
            if alias.fields:
                for _, ft in alias.fields:
                    return self._resolve_type(ft, in_method=in_method)
            return self._make_blob_construct("BLOB", in_method=in_method)

        # Recursive alias (alias references another alias)
        if self._aliases.has(base):
            return self._resolve_type(base, in_method=in_method)

        # Final fallback
        return self._make_blob_construct("BLOB", in_method=in_method)

    def build_schema_for_method_def(
        self, method: MethodDef,
    ) -> cs.Construct[Any, Any] | None:
        """Build a schema for a MethodDef directly (bypasses index lookup).

        Used by the Tier 2 auto-detector for trial parsing candidate methods.
        """
        if not method.args:
            return cs.Struct()
        return self._build_args_schema(method.args, in_method=True)

    @staticmethod
    def _make_blob_construct(
        type_name: str, *, in_method: bool,
    ) -> cs.Construct[Any, Any]:
        """Create a length-prefixed construct for BLOB/STRING types.

        In method calls: u8 length, 0xFF → u16 + u8 padding.
        In property updates: u32 length (standard).
        """
        if in_method:
            if type_name in ("STRING", "UNICODE_STRING"):
                return _MethodBlobPrefixed(cs.GreedyString("utf-8"))
            return _MethodBlobPrefixed(cs.GreedyBytes)
        else:
            if type_name in ("STRING", "UNICODE_STRING"):
                return cs.PascalString(cs.Int32ul, "utf-8")
            return cs.Prefixed(cs.Int32ul, cs.GreedyBytes)
