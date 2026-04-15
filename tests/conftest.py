"""Shared pytest fixtures for integration-flavoured tests.

The canonical place for real replay / gamedata artefacts is
``tests/fixtures/`` — see ``tests/fixtures/README.md`` for the policy and
filename convention. All fixtures here degrade to ``pytest.skip(...)`` when
no real artefacts are present, so the test suite passes cleanly on a fresh
clone and in CI without any fixtures available.

For backwards compatibility with pre-existing working trees, the legacy
hardcoded paths (``<repo>/20260322_172639_*.wowsreplay`` and
``<repo>/wows-gamedata/data``) are still honoured as fall-backs — they are
tried only after the ``tests/fixtures/`` locations.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from wows_replay_parser.api import ParsedReplay

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
REPLAYS_DIR = FIXTURES_DIR / "replays"
FIXTURE_GAMEDATA_ROOT = FIXTURES_DIR / "gamedata"

# Legacy fallback — the original hardcoded fixture from before this
# infrastructure existed. Honoured so existing local checkouts keep working
# without relocating files.
_LEGACY_REPLAY = (
    PROJECT_ROOT / "20260322_172639_PHSC710-Prins-Van-Oranje_56_AngelWings.wowsreplay"
)
_LEGACY_GAMEDATA_ROOT = PROJECT_ROOT / "wows-gamedata" / "data"


# ---------------------------------------------------------------------------
# Discovery helpers
# ---------------------------------------------------------------------------


def _entity_defs_under(root: Path) -> Path | None:
    """Return the ``scripts_entity/entity_defs`` dir under *root* if it exists.

    Accepts either a raw gamedata ``data/`` directory or one that already
    points at ``entity_defs`` itself.
    """
    if not root.exists():
        return None
    direct = root / "scripts_entity" / "entity_defs"
    if direct.is_dir():
        return direct
    # If the caller symlinked straight at entity_defs, accept that too.
    if root.name == "entity_defs" and root.is_dir():
        return root
    return None


def _find_fixture_replay() -> Path | None:
    if REPLAYS_DIR.is_dir():
        candidates = sorted(REPLAYS_DIR.glob("*.wowsreplay"))
        if candidates:
            return candidates[0]
    if _LEGACY_REPLAY.exists():
        return _LEGACY_REPLAY
    return None


def _find_fixture_gamedata() -> Path | None:
    fixture_defs = _entity_defs_under(FIXTURE_GAMEDATA_ROOT)
    if fixture_defs is not None:
        return fixture_defs
    legacy_defs = _entity_defs_under(_LEGACY_GAMEDATA_ROOT)
    if legacy_defs is not None:
        return legacy_defs
    return None


def _find_paired_replays() -> tuple[Path, Path] | None:
    if not REPLAYS_DIR.is_dir():
        return None
    paired = sorted(REPLAYS_DIR.glob("paired_*.wowsreplay"))
    if len(paired) >= 2:
        return paired[0], paired[1]
    return None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def fixture_replay_path() -> Path:
    """Absolute path of a sanitised ``.wowsreplay`` file for tests.

    Looks first under ``tests/fixtures/replays/``; falls back to the legacy
    hardcoded path at the repo root. Skips the test cleanly when neither is
    present.
    """
    replay = _find_fixture_replay()
    if replay is None:
        pytest.skip(
            "No replay fixture available — drop a sanitised .wowsreplay into "
            "tests/fixtures/replays/ (see tests/fixtures/README.md).",
        )
    return replay


@pytest.fixture(scope="session")
def fixture_gamedata_path() -> Path:
    """Absolute path to an ``entity_defs`` directory matching the fixture."""
    gamedata = _find_fixture_gamedata()
    if gamedata is None:
        pytest.skip(
            "No gamedata fixture available — symlink tests/fixtures/gamedata "
            "to your wows-gamedata/data checkout (see tests/fixtures/README.md).",
        )
    return gamedata


@pytest.fixture(scope="session")
def parsed_fixture(
    fixture_replay_path: Path,
    fixture_gamedata_path: Path,
) -> "ParsedReplay":
    """Parsed fixture replay, shared across the test session.

    Parsing a real replay is expensive (multiple seconds); this fixture is
    session-scoped so every consuming test reuses the same ``ParsedReplay``
    object. Treat it as read-only.
    """
    from wows_replay_parser.api import parse_replay

    return parse_replay(fixture_replay_path, fixture_gamedata_path)


# Back-compat alias — existing tests use ``parsed_replay``.
@pytest.fixture(scope="session")
def parsed_replay(parsed_fixture: "ParsedReplay") -> "ParsedReplay":
    """Alias for :func:`parsed_fixture`. Prefer ``parsed_fixture`` in new tests."""
    return parsed_fixture


@pytest.fixture
def paired_fixture_paths() -> tuple[Path, Path]:
    """A pair of replays from the *same* match, for merge tests.

    Matches ``tests/fixtures/replays/paired_*.wowsreplay`` (at least two
    files). Skips cleanly otherwise.
    """
    paired = _find_paired_replays()
    if paired is None:
        pytest.skip(
            "No paired replay fixtures — drop two paired_*.wowsreplay files "
            "from the same match into tests/fixtures/replays/.",
        )
    return paired
