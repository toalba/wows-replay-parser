"""
Loads .def files from wows-gamedata entity_defs/.

Each .def file (Avatar.def, Vehicle.def, etc.) defines an entity type with:
- Properties: typed fields with flags (OWN_CLIENT, ALL_CLIENTS, CELL_PUBLIC, etc.)
- ClientMethods: methods the server can call on the client (these appear in replays)
- CellMethods: methods callable on the cell entity
- BaseMethods: methods callable on the base entity

For replay parsing, we care about:
1. Properties with ALL_CLIENTS or OTHER_CLIENTS flags (visible in replays)
2. ClientMethods (called via entity method packets in replays)

The .def files also reference <Implements> for interface .def files
in the interfaces/ subdirectory.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from wows_replay_parser.gamedata.alias_registry import AliasRegistry


@dataclass
class PropertyDef:
    """A property definition from a .def file."""

    name: str
    type_name: str
    flags: str = ""  # e.g. "ALL_CLIENTS", "OWN_CLIENT", "CELL_PRIVATE"
    allow_none: bool = False
    # Computed sort size (set by EntityRegistry during registration)
    sort_size: int = 0


@dataclass
class MethodDef:
    """A method definition from a .def file."""

    name: str
    # Ordered list of (arg_name_or_index, type_name)
    args: list[tuple[str, str]] = field(default_factory=list)
    # Exposed to which side
    section: str = ""  # "ClientMethods", "CellMethods", "BaseMethods"
    variable_length_header_size: int = 1
    # Computed sort size (set by EntityRegistry during registration)
    sort_size: int = 0


@dataclass
class EntityDef:
    """Complete entity definition from a .def file."""

    name: str
    properties: list[PropertyDef] = field(default_factory=list)
    client_methods: list[MethodDef] = field(default_factory=list)
    cell_methods: list[MethodDef] = field(default_factory=list)
    base_methods: list[MethodDef] = field(default_factory=list)
    implements: list[str] = field(default_factory=list)  # interface names


class DefLoader:
    """
    Loads all .def files from a wows-gamedata entity_defs directory.

    Usage:
        loader = DefLoader(Path("wows-gamedata/data/scripts_entity/entity_defs"))
        entities = loader.load_all()
        avatar = loader.load("Avatar")
    """

    def __init__(self, entity_defs_dir: Path) -> None:
        self._dir = entity_defs_dir
        self._interfaces_dir = entity_defs_dir / "interfaces"

    def load_all(self) -> dict[str, EntityDef]:
        """Load all .def files in the directory."""
        entities: dict[str, EntityDef] = {}
        for def_file in sorted(self._dir.glob("*.def")):
            name = def_file.stem
            entities[name] = self.load(name)
        return entities

    def load(self, entity_name: str) -> EntityDef:
        """Load a single entity .def file, resolving interfaces.

        Uses the BigWorld depth-first interface merge algorithm:
        1. For each interface (in XML document order), recursively
           resolve its sub-interfaces, then append its methods.
        2. Then append the entity's own methods.
        3. Deduplicate by name — first definition wins.
        """
        path = self._dir / f"{entity_name}.def"
        if not path.exists():
            raise FileNotFoundError(f"Entity def not found: {path}")

        tree = etree.parse(str(path))
        root = tree.getroot()
        entity = EntityDef(name=entity_name)

        # Parse <Implements> list (for reference only)
        implements_el = root.find("Implements")
        if implements_el is not None:
            for iface in implements_el:
                if not isinstance(iface.tag, str):
                    continue
                entity.implements.append(iface.text.strip() if iface.text else iface.tag)

        # Depth-first merge: interfaces first, entity's own methods last.
        # _parse_section handles the recursion.
        seen_methods: set[str] = set()
        seen_props: set[str] = set()
        self._parse_section(root, entity, seen_methods, seen_props)

        return entity

    # Legacy methods removed — replaced by _parse_properties_dedup
    # and _parse_methods_dedup with correct depth-first merge order.

    def _parse_section(
        self,
        root: etree._Element,
        entity: EntityDef,
        seen_methods: set[str],
        seen_props: set[str],
        *,
        _visited: set[str] | None = None,
    ) -> None:
        """Depth-first BigWorld merge: interfaces first, own methods last.

        For each <Implements> interface (in XML document order):
            recursively parse_section(interface)
        Then parse this node's own ClientMethods/Properties.

        Methods are deduplicated by name — first definition wins.
        """
        if _visited is None:
            _visited = set()

        # 1. Recurse into interfaces (depth-first, XML document order)
        impl_el = root.find("Implements")
        if impl_el is not None:
            for child in impl_el:
                if not isinstance(child.tag, str):
                    continue
                iface_name = child.text.strip() if child.text else child.tag
                if iface_name in _visited:
                    continue
                _visited.add(iface_name)

                iface_path = self._interfaces_dir / f"{iface_name}.def"
                if not iface_path.exists():
                    continue

                tree = etree.parse(str(iface_path))
                iface_root = tree.getroot()
                self._parse_section(
                    iface_root, entity, seen_methods, seen_props,
                    _visited=_visited,
                )

        # 2. Append this node's own properties (deduplicating by name)
        self._parse_properties_dedup(root, entity, seen_props)

        # 3. Append this node's own methods (deduplicating by name)
        for section in ("ClientMethods", "CellMethods", "BaseMethods"):
            self._parse_methods_dedup(root, entity, section, seen_methods)

    def _parse_properties_dedup(
        self, root: etree._Element, entity: EntityDef, seen: set[str],
    ) -> None:
        """Parse <Properties>, skipping names already seen."""
        props_el = root.find("Properties")
        if props_el is None:
            return

        for prop_el in props_el:
            if not isinstance(prop_el.tag, str):
                continue
            prop_name = prop_el.tag
            if prop_name in seen:
                continue
            seen.add(prop_name)

            type_el = prop_el.find("Type")
            flags_el = prop_el.find("Flags")
            allow_none_el = prop_el.find("AllowNone")

            type_name = AliasRegistry._extract_type_text(type_el) if type_el is not None else "UNKNOWN"
            flags = flags_el.text.strip() if flags_el is not None and flags_el.text else ""
            allow_none = False
            if allow_none_el is not None and allow_none_el.text:
                allow_none = allow_none_el.text.strip().lower() == "true"

            entity.properties.append(PropertyDef(
                name=prop_name,
                type_name=type_name,
                flags=flags,
                allow_none=allow_none,
            ))

    def _parse_methods_dedup(
        self, root: etree._Element, entity: EntityDef,
        section: str, seen: set[str],
    ) -> None:
        """Parse a methods section, skipping names already seen."""
        section_el = root.find(section)
        if section_el is None:
            return

        target = {
            "ClientMethods": entity.client_methods,
            "CellMethods": entity.cell_methods,
            "BaseMethods": entity.base_methods,
        }[section]

        for method_el in section_el:
            if not isinstance(method_el.tag, str):
                continue
            if method_el.tag in seen:
                continue
            seen.add(method_el.tag)

            method = MethodDef(name=method_el.tag, section=section)

            vlh_el = method_el.find("VariableLengthHeaderSize")
            if vlh_el is not None and vlh_el.text:
                try:
                    method.variable_length_header_size = int(vlh_el.text.strip())
                except ValueError:
                    pass

            arg_counter = 0
            for child in method_el:
                if child.tag == "Arg":
                    arg_type = AliasRegistry._extract_type_text(child)
                    method.args.append((str(arg_counter), arg_type))
                    arg_counter += 1
                elif child.tag == "Args":
                    for named_arg in child:
                        arg_type = AliasRegistry._extract_type_text(named_arg)
                        method.args.append((named_arg.tag, arg_type))

            target.append(method)
