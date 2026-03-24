"""
Gamedata loading — reads .def files and alias.xml from wows-gamedata repo,
builds the entity registry used by the packet decoder.
"""

from wows_replay_parser.gamedata.alias_registry import AliasRegistry
from wows_replay_parser.gamedata.def_loader import DefLoader
from wows_replay_parser.gamedata.entity_registry import EntityRegistry
from wows_replay_parser.gamedata.schema_builder import SchemaBuilder

__all__ = ["AliasRegistry", "DefLoader", "EntityRegistry", "SchemaBuilder"]
