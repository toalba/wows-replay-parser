"""Regression tests for arena key-map loading (roster.py).

Covers the build-12668706 (patch 15.5) gamedata schema change where
``arena_key_maps.json`` switched to a server-side group format: a 7-field
``player_keys`` (the ``COMMON_DATA`` group) and a ``bot_keys`` list that
concatenates groups with duplicate field names. Indexing those blindly
shifted every field — ``clanID`` landed on the list-typed ``crewParams`` and
roster construction crashed with ``int() argument ... not 'list'``. The client
wire format is unchanged, so the loader must reject the bad JSON and fall back
to the hardcoded maps.
"""
from __future__ import annotations

import json

from wows_replay_parser.roster import (
    _FALLBACK_BOT_KEY_MAP,
    _FALLBACK_PLAYER_KEY_MAP,
    _is_valid_wire_map,
    _load_key_maps,
)


def _write_keymaps(tmp_path, data):
    """Lay out a gamedata dir and return the entity_defs path the loader wants."""
    entity_defs = tmp_path / "data" / "scripts_entity" / "entity_defs"
    entity_defs.mkdir(parents=True)
    (tmp_path / "data" / "arena_key_maps.json").write_text(json.dumps(data))
    return entity_defs


def test_is_valid_wire_map_accepts_flat_unique_list():
    assert _is_valid_wire_map(sorted(_FALLBACK_PLAYER_KEY_MAP.values()))
    assert _is_valid_wire_map(sorted(_FALLBACK_BOT_KEY_MAP.values()))


def test_is_valid_wire_map_rejects_duplicates():
    # build-12668706 bot_keys repeats accountDBID/clanID/dogTag.
    keys = sorted(_FALLBACK_PLAYER_KEY_MAP.values()) + ["clanID"]
    assert not _is_valid_wire_map(keys)


def test_is_valid_wire_map_rejects_missing_sentinels():
    # build-12668706 player_keys = COMMON_DATA, which lacks shipId.
    common_data = ["id", "accountDBID", "name", "teamId", "realm", "dogTag", "isAlive"]
    assert not _is_valid_wire_map(common_data)


def test_load_key_maps_uses_valid_json(tmp_path):
    players = sorted(_FALLBACK_PLAYER_KEY_MAP.values())
    bots = sorted(_FALLBACK_BOT_KEY_MAP.values())
    entity_defs = _write_keymaps(tmp_path, {"player_keys": players, "bot_keys": bots})

    pmap, bmap = _load_key_maps(entity_defs)

    assert pmap == dict(enumerate(players))
    assert bmap == dict(enumerate(bots))


def test_load_key_maps_falls_back_on_group_format(tmp_path):
    # The build-12668706 server-side group schema: short player_keys (COMMON_DATA)
    # and a bot_keys list with duplicate field names.
    group_format = {
        "player_keys": ["id", "accountDBID", "name", "teamId", "realm", "dogTag", "isAlive"],
        "bot_keys": [
            "id", "accountDBID", "name", "teamId", "realm", "dogTag", "isAlive",
            "accountDBID", "clanID", "clanID", "clanTag",
        ],
    }
    entity_defs = _write_keymaps(tmp_path, group_format)

    pmap, bmap = _load_key_maps(entity_defs)

    assert pmap == _FALLBACK_PLAYER_KEY_MAP
    assert bmap == _FALLBACK_BOT_KEY_MAP


def test_load_key_maps_falls_back_without_gamedata():
    pmap, bmap = _load_key_maps(None)
    assert pmap == _FALLBACK_PLAYER_KEY_MAP
    assert bmap == _FALLBACK_BOT_KEY_MAP
