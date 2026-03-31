"""
Resolves type aliases from alias.xml.

alias.xml maps shorthand type names (e.g. ENTITY_ID, HEALTH) to their
underlying BigWorld types (INT32, FLOAT32, etc.) and compound structures
(FIXED_DICT, ARRAY, TUPLE).

The alias registry must be loaded before .def files are parsed, because
.def files reference aliases as property types.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree


@dataclass
class TypeAlias:
    """A resolved type alias."""

    name: str
    base_type: str  # e.g. "INT32", "FLOAT32", "STRING", "FIXED_DICT", "ARRAY"
    # For FIXED_DICT: ordered list of (field_name, field_type_name)
    fields: list[tuple[str, str]] = field(default_factory=list)
    # For ARRAY: element type name
    element_type: str | None = None
    # For TUPLE: ordered element types
    tuple_types: list[str] = field(default_factory=list)
    # Size override (for fixed-size types)
    size: int | None = None
    # FIXED_DICT with AllowNone
    allow_none: bool = False
    # Has <implementedBy> tag (custom Python serializer)
    # Engine treats these as variable-length regardless of field types
    has_implemented_by: bool = False
    # The converter path from <implementedBy> (e.g. "converters.ZippedBlobConverter")
    implemented_by: str | None = None


class AliasRegistry:
    """
    Loads and resolves alias.xml from wows-gamedata.

    Usage:
        registry = AliasRegistry.from_file(Path("wows-gamedata/data/scripts_entity/entity_defs/alias.xml"))
        resolved = registry.resolve("ENTITY_ID")
    """

    def __init__(self) -> None:
        self._aliases: dict[str, TypeAlias] = {}

    @classmethod
    def from_file(cls, path: Path) -> AliasRegistry:
        """Load alias.xml and build the registry."""
        instance = cls()
        instance._load(path)
        return instance

    def _load(self, path: Path) -> None:
        """Parse alias.xml and register all type aliases."""
        tree = etree.parse(str(path))
        root = tree.getroot()

        for child in root:
            alias_name = child.tag
            type_alias = self._parse_alias_element(alias_name, child)
            self._aliases[alias_name] = type_alias

    def _parse_alias_element(self, name: str, element: etree._Element) -> TypeAlias:
        """
        Parse a single alias element from alias.xml.

        Handles all five patterns:
        - Simple:     <ENTITY_ID> INT32 </ENTITY_ID>
        - FIXED_DICT: <VIS> FIXED_DICT <Properties>...</Properties> </VIS>
        - ARRAY:      <VISION> ARRAY<of>ENTITY_ID</of> </VISION>
        - TUPLE:      <INFO> TUPLE<of>INT32</of><size>2</size> </INFO>
        - USER_TYPE:  <ZIPPED_BLOB> USER_TYPE <Type>BLOB</Type> <implementedBy>...</implementedBy> </ZIPPED_BLOB>
        """
        text = (element.text or "").strip()

        # --- FIXED_DICT ---
        if text == "FIXED_DICT":
            fields: list[tuple[str, str]] = []
            allow_none = False
            props_el = element.find("Properties")
            if props_el is not None:
                for prop in props_el:
                    if not isinstance(prop.tag, str):
                        continue
                    field_name = prop.tag
                    type_el = prop.find("Type")
                    if type_el is not None:
                        field_type = self._extract_type_text(type_el)
                    else:
                        # Inline text type (rare)
                        field_type = (prop.text or "").strip()
                    fields.append((field_name, field_type))
            allow_none_el = element.find("AllowNone")
            if allow_none_el is not None:
                allow_none = (allow_none_el.text or "").strip().lower() == "true"
            impl_el = element.find("implementedBy")
            has_impl = impl_el is not None
            implemented_by = (impl_el.text or "").strip() if impl_el is not None else None
            return TypeAlias(
                name=name,
                base_type="FIXED_DICT",
                fields=fields,
                allow_none=allow_none,
                has_implemented_by=has_impl,
                implemented_by=implemented_by,
            )

        # --- ARRAY ---
        if text.startswith("ARRAY"):
            of_el = element.find("of")
            if of_el is not None and of_el.text:
                elem_type = of_el.text.strip()
            else:
                # Inline: ARRAY<of>TYPE</of> — lxml parses <of> as a child
                # but text may contain "ARRAY" and <of> is a sub-element
                elem_type = "UNKNOWN"
                for child in element:
                    if child.tag == "of" and child.text:
                        elem_type = child.text.strip()
                        break
            return TypeAlias(
                name=name, base_type="ARRAY", element_type=elem_type
            )

        # --- TUPLE ---
        if text.startswith("TUPLE"):
            of_el = element.find("of")
            size_el = element.find("size")
            elem_type = (of_el.text or "").strip() if of_el is not None else "UNKNOWN"
            count = int((size_el.text or "1").strip()) if size_el is not None else 1
            return TypeAlias(
                name=name,
                base_type="TUPLE",
                tuple_types=[elem_type] * count,
                size=count,
            )

        # --- USER_TYPE ---
        if text == "USER_TYPE":
            type_el = element.find("Type")
            underlying = (type_el.text or "BLOB").strip() if type_el is not None else "BLOB"
            impl_el = element.find("implementedBy")
            has_impl = impl_el is not None
            implemented_by = (impl_el.text or "").strip() if impl_el is not None else None
            return TypeAlias(
                name=name, base_type=underlying,
                has_implemented_by=has_impl,
                implemented_by=implemented_by,
            )

        # --- Simple alias ---
        # Text content is the base type, e.g. "INT32", "FLOAT", "STRING"
        if text:
            impl_el = element.find("implementedBy")
            has_impl = impl_el is not None
            implemented_by = (impl_el.text or "").strip() if impl_el is not None else None
            return TypeAlias(
                name=name, base_type=text,
                has_implemented_by=has_impl,
                implemented_by=implemented_by,
            )

        return TypeAlias(name=name, base_type="UNKNOWN")

    @staticmethod
    def _extract_type_text(type_el: etree._Element) -> str:
        """Extract a type string from a <Type> element.

        Handles inline compound types like ``<Type>ARRAY<of>FOO</of></Type>``
        where lxml parses ``<of>`` as a child element and the text is just
        ``"ARRAY"``.  Reconstructs the full canonical form so the alias
        registry / schema builder can resolve it later.
        """
        base = (type_el.text or "").strip()
        if not base:
            return "UNKNOWN"

        # If no children, it's a plain type reference like "INT32"
        if len(type_el) == 0:
            return base

        # Inline ARRAY<of>ELEM</of>  →  store as "ARRAY<of>ELEM</of>"
        # so the schema builder can parse it back.
        of_el = type_el.find("of")
        if of_el is not None and of_el.text:
            elem = of_el.text.strip()
            # Nested: ARRAY<of>ARRAY<of>UINT8</of></of>
            inner_of = of_el.find("of")
            if inner_of is not None and inner_of.text:
                return f"{base}<of>{(of_el.text or '').strip()}<of>{inner_of.text.strip()}</of></of>"
            return f"{base}<of>{elem}</of>"

        return base

    def resolve(self, type_name: str) -> TypeAlias | None:
        """Resolve a type name, returning None if it's a primitive."""
        return self._aliases.get(type_name)

    def has(self, type_name: str) -> bool:
        return type_name in self._aliases

    @property
    def names(self) -> list[str]:
        return list(self._aliases.keys())
