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
        """Load a single entity .def file, resolving interfaces."""
        path = self._dir / f"{entity_name}.def"
        if not path.exists():
            raise FileNotFoundError(f"Entity def not found: {path}")

        tree = etree.parse(str(path))
        root = tree.getroot()
        entity = EntityDef(name=entity_name)

        # Parse <Implements>
        implements_el = root.find("Implements")
        if implements_el is not None:
            for iface in implements_el:
                if not isinstance(iface.tag, str):
                    continue
                entity.implements.append(iface.text.strip() if iface.text else iface.tag)

        # Parse <Properties>
        self._parse_properties(root, entity)

        # Parse method sections
        for section in ("ClientMethods", "CellMethods", "BaseMethods"):
            self._parse_methods(root, entity, section)

        # Merge interfaces in reverse order — each _merge_interface prepends,
        # so reversing ensures the final order is: iface[0] + iface[1] + ... + entity
        for iface_name in reversed(entity.implements):
            self._merge_interface(entity, iface_name)

        return entity

    def _parse_properties(
        self, root: etree._Element, entity: EntityDef, *, prepend: bool = False,
    ) -> None:
        """Parse <Properties> section."""
        props_el = root.find("Properties")
        if props_el is None:
            return

        new_props: list[PropertyDef] = []
        for prop_el in props_el:
            if not isinstance(prop_el.tag, str):
                continue  # skip XML comments
            prop_name = prop_el.tag
            type_el = prop_el.find("Type")
            flags_el = prop_el.find("Flags")
            allow_none_el = prop_el.find("AllowNone")

            type_name = type_el.text.strip() if type_el is not None and type_el.text else "UNKNOWN"
            flags = flags_el.text.strip() if flags_el is not None and flags_el.text else ""
            allow_none = False
            if allow_none_el is not None and allow_none_el.text:
                allow_none = allow_none_el.text.strip().lower() == "true"

            new_props.append(PropertyDef(
                name=prop_name,
                type_name=type_name,
                flags=flags,
                allow_none=allow_none,
            ))

        if prepend:
            entity.properties[:] = new_props + entity.properties
        else:
            entity.properties.extend(new_props)

    def _parse_methods(
        self, root: etree._Element, entity: EntityDef, section: str,
        *, prepend: bool = False,
    ) -> None:
        """Parse a methods section (ClientMethods, CellMethods, BaseMethods)."""
        section_el = root.find(section)
        if section_el is None:
            return

        target = {
            "ClientMethods": entity.client_methods,
            "CellMethods": entity.cell_methods,
            "BaseMethods": entity.base_methods,
        }[section]

        new_methods: list[MethodDef] = []

        for method_el in section_el:
            if not isinstance(method_el.tag, str):
                continue  # skip XML comments and processing instructions
            method = MethodDef(name=method_el.tag, section=section)

            # Parse VariableLengthHeaderSize
            vlh_el = method_el.find("VariableLengthHeaderSize")
            if vlh_el is not None and vlh_el.text:
                try:
                    method.variable_length_header_size = int(vlh_el.text.strip())
                except ValueError:
                    pass

            # Parse args
            arg_counter = 0
            for child in method_el:
                if child.tag == "Arg":
                    arg_type = child.text.strip() if child.text else "UNKNOWN"
                    method.args.append((str(arg_counter), arg_type))
                    arg_counter += 1
                elif child.tag == "Args":
                    for named_arg in child:
                        arg_type = named_arg.text.strip() if named_arg.text else "UNKNOWN"
                        method.args.append((named_arg.tag, arg_type))

            new_methods.append(method)

        if prepend:
            # Interface methods go before entity's own methods
            target[:] = new_methods + target
        else:
            target.extend(new_methods)

    def _merge_interface(
        self, entity: EntityDef, iface_name: str, *, _visited: set[str] | None = None,
    ) -> None:
        """Load an interface .def and merge its properties/methods into the entity.

        Interface methods are prepended so they come before the entity's own
        methods in the pre-sort list. Handles one level of nested interfaces.
        """
        if _visited is None:
            _visited = set()
        if iface_name in _visited:
            return
        _visited.add(iface_name)

        iface_path = self._interfaces_dir / f"{iface_name}.def"
        if not iface_path.exists():
            return

        tree = etree.parse(str(iface_path))
        root = tree.getroot()

        # Recursively merge sub-interfaces first
        impl_el = root.find("Implements")
        if impl_el is not None:
            for child in impl_el:
                if not isinstance(child.tag, str):
                    continue
                sub_name = child.text.strip() if child.text else child.tag
                self._merge_interface(entity, sub_name, _visited=_visited)

        # Merge properties (prepend — interface props before entity's own)
        self._parse_properties(root, entity, prepend=True)

        # Merge methods (prepend — interface methods before entity's own)
        for section in ("ClientMethods", "CellMethods", "BaseMethods"):
            self._parse_methods(root, entity, section, prepend=True)
