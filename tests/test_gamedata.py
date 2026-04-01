"""Tests for the gamedata loading layer."""

from pathlib import Path

import pytest


class TestAliasRegistry:
    """Test alias.xml parsing."""

    def test_placeholder(self) -> None:
        """Placeholder — needs real alias.xml fixture."""
        # TODO: Copy alias.xml from wows-gamedata into tests/fixtures/
        # and test resolution of common aliases
        pass


class TestDefLoader:
    """Test .def file parsing."""

    def test_placeholder(self) -> None:
        """Placeholder — needs real .def file fixtures."""
        pass


class TestEntityRegistry:
    """Test entity registry indexing."""

    def test_register_and_lookup(self) -> None:
        from wows_replay_parser.gamedata.def_loader import EntityDef, MethodDef, PropertyDef
        from wows_replay_parser.gamedata.entity_registry import EntityRegistry

        registry = EntityRegistry()

        entity = EntityDef(
            name="TestEntity",
            properties=[
                PropertyDef(name="health", type_name="FLOAT32", flags="ALL_CLIENTS"),
                PropertyDef(name="internal", type_name="INT32", flags="CELL_PRIVATE"),
            ],
            client_methods=[
                MethodDef(name="onDamage", args=[("0", "FLOAT32"), ("1", "ENTITY_ID")]),
                MethodDef(name="onKill", args=[]),
            ],
        )
        registry.register(entity)

        assert registry.get("TestEntity") is not None
        assert registry.get_client_method("TestEntity", 0) is not None
        assert registry.get_client_method("TestEntity", 0).name == "onDamage"
        assert registry.get_client_method("TestEntity", 1).name == "onKill"
        assert registry.get_client_method("TestEntity", 2) is None


class TestSchemaBuilder:
    """Test dynamic schema building."""

    def test_primitive_resolution(self) -> None:
        from wows_replay_parser.gamedata.alias_registry import AliasRegistry
        from wows_replay_parser.gamedata.entity_registry import EntityRegistry
        from wows_replay_parser.gamedata.schema_builder import SchemaBuilder

        aliases = AliasRegistry()
        entities = EntityRegistry()
        builder = SchemaBuilder(aliases, entities)

        # Primitives should resolve directly
        schema = builder._resolve_type("INT32", in_method=False)
        assert schema is not None

        result = schema.parse(b"\x2a\x00\x00\x00")
        assert result == 42
