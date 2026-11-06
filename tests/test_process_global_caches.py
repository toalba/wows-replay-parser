"""Process-global caches must not leak state between replays.

Both defects covered here were found on 2026-11-06 behind a single
user-visible symptom: a Discord render bot whose score bar sat frozen at the
match's opening score while every other overlay was correct, and whose
worker processes were OOM-killed at ~4.4 GB RSS every few hours.

The bot renders in a ``ProcessPoolExecutor`` whose workers are long-lived,
so any state the parser keeps at module scope outlives the replay that
created it and is inherited by the next one.
"""

from __future__ import annotations

import gc
import weakref
from pathlib import Path

from wows_replay_parser.gamedata.alias_registry import AliasRegistry
from wows_replay_parser.packets.decoder import PacketDecoder
from wows_replay_parser.packets.nested_property import _resolve_type_structure


def _write_alias_xml(path: Path, fields: list[tuple[str, str]]) -> Path:
    """Write a minimal alias.xml defining one FIXED_DICT named MISSIONS."""
    props = "\n".join(
        f"      <{name}> <Type> {type_name} </Type> </{name}>"
        for name, type_name in fields
    )
    path.write_text(
        "<root>\n"
        "  <MISSIONS> FIXED_DICT\n"
        "    <Properties>\n"
        f"{props}\n"
        "    </Properties>\n"
        "  </MISSIONS>\n"
        "</root>\n"
    )
    return path


def test_type_structure_is_resolved_per_alias_registry(tmp_path: Path) -> None:
    """Two gamedata versions defining the same type name must not share a cache.

    Patches reorder and rename the fields of a FIXED_DICT. If the structure
    for ``MISSIONS`` is memoized by type name alone, the first registry seen
    in the process wins for every later one, nested-property navigation walks
    the wrong field layout, and updates to the real field are dropped.
    """
    old = AliasRegistry.from_file(
        _write_alias_xml(
            tmp_path / "old.xml",
            [("teamWinScore", "UINT32"), ("teamsScore", "UINT32")],
        )
    )
    new = AliasRegistry.from_file(
        _write_alias_xml(
            tmp_path / "new.xml",
            [("teamWinScore", "UINT32"), ("hold", "UINT32"), ("teamsScore", "UINT32")],
        )
    )

    # Resolve against the OLD registry first, mimicking a worker that renders
    # an older-patch replay before a current one.
    old_structure = _resolve_type_structure("MISSIONS", old)
    new_structure = _resolve_type_structure("MISSIONS", new)

    assert [name for name, _ in old_structure["fields"]] == [
        "teamWinScore",
        "teamsScore",
    ]
    assert [name for name, _ in new_structure["fields"]] == [
        "teamWinScore",
        "hold",
        "teamsScore",
    ]


class _StubEntityRegistry:
    """Minimal stand-in: _find_array_paths only needs this one lookup."""

    def get_client_property(self, entity_type: str, prop_idx: int) -> None:
        return None


def test_decoder_is_collectable_after_use() -> None:
    """A decoder must not be kept alive by its own memoization.

    ``functools.lru_cache`` on an instance method makes ``self`` part of the
    cache key, so the cache — which lives on the function object, shared by
    the whole process — holds a strong reference to every decoder ever used.
    Each one pins its entity registry and schema builder, which is what grew
    prod's workers by ~40 MB per render until the cgroup killed them.
    """
    decoder = PacketDecoder(schema=None, entities=_StubEntityRegistry())
    decoder._find_array_paths("Vehicle", 47)

    ref = weakref.ref(decoder)
    del decoder
    gc.collect()

    assert ref() is None, "decoder is still reachable after being dropped"
