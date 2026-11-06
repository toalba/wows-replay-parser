"""The exported ``__version__`` must track the packaged version.

These drifted apart up to 0.1.4: ``__init__.__version__`` still read
"0.1.0" while the package shipped as 0.1.4. During a production incident on
2026-11-06 that sent an investigation down the wrong path — the deployed
container and the dev machine both self-reported "0.1.0", which looked like
a version mismatch between them when in fact both ran 0.1.4.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import wows_replay_parser

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def test_exported_version_matches_pyproject() -> None:
    packaged = tomllib.loads(PYPROJECT.read_text())["project"]["version"]
    assert wows_replay_parser.__version__ == packaged
