"""Auto-sync wows-gamedata repo to match replay version.

When a replay's build ID doesn't match the gamedata checkout,
this module can fetch and checkout the matching tag automatically.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path  # noqa: TC003 — used at runtime in function signatures

log = logging.getLogger(__name__)

GAMEDATA_REPO_URL = "https://github.com/toalba/wows-gamedata.git"


def extract_build_id(game_version: str) -> str | None:
    """Extract build ID from a version string like '15,2,0,12116141'.

    The last comma-separated component is the build ID.
    """
    parts = game_version.replace(".", ",").split(",")
    if parts:
        build = parts[-1].strip()
        return build if build.isdigit() else None
    return None


def get_current_gamedata_version(gamedata_root: Path) -> str | None:
    """Get the current build ID from the gamedata repo's checked-out tag.

    Returns the build ID (e.g., '12116141') or None if not a git repo.
    """
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--exact-match"],
            cwd=gamedata_root,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            tag = result.stdout.strip()  # e.g., "v12116141"
            return tag.lstrip("v")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Fallback: check latest commit message for build ID
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%s"],
            cwd=gamedata_root,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            # Commit messages look like "Update game data: 12116141"
            msg = result.stdout.strip()
            parts = msg.split(":")
            if len(parts) >= 2:
                return parts[-1].strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return None


def sync_gamedata(
    gamedata_root: Path,
    replay_version: str,
    *,
    auto_clone: bool = False,
) -> bool:
    """Ensure gamedata matches the replay version.

    Compares the replay's build ID against the gamedata repo's
    current tag. If they don't match, fetches tags and checks
    out the matching one.

    Args:
        gamedata_root: Path to the wows-gamedata repo root
            (parent of the 'data/' directory).
        replay_version: The game version string from replay meta
            (e.g., '15,2,0,12116141').
        auto_clone: If True and gamedata_root doesn't exist,
            clone the repo. Defaults to False.

    Returns:
        True if gamedata is now at the correct version.
        False if sync failed (no matching tag, git error, etc.).
    """
    replay_build = extract_build_id(replay_version)
    if not replay_build:
        log.warning("Could not extract build ID from '%s'", replay_version)
        return False

    # Clone if needed
    if not gamedata_root.exists():
        if not auto_clone:
            log.warning(
                "Gamedata directory does not exist: %s. "
                "Set auto_clone=True or clone manually.",
                gamedata_root,
            )
            return False
        log.info("Cloning wows-gamedata to %s...", gamedata_root)
        try:
            subprocess.run(
                ["git", "clone", "--depth=1", GAMEDATA_REPO_URL, str(gamedata_root)],
                capture_output=True,
                text=True,
                timeout=300,
                check=True,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            log.error("Failed to clone gamedata repo: %s", e)
            return False

    # Check current version
    current_build = get_current_gamedata_version(gamedata_root)
    if current_build == replay_build:
        log.debug(
            "Gamedata already at build %s", replay_build,
        )
        return True

    log.info(
        "Gamedata version mismatch: have %s, need %s. Updating...",
        current_build or "unknown",
        replay_build,
    )

    # Check for uncommitted changes — refuse to checkout if dirty
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=gamedata_root,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            log.warning(
                "Gamedata repo has uncommitted changes, refusing to checkout. "
                "Commit or discard changes in %s first.",
                gamedata_root,
            )
            return False
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        log.error("Git not available: %s", e)
        return False

    # Fetch latest tags
    try:
        subprocess.run(
            ["git", "fetch", "--tags", "--force"],
            cwd=gamedata_root,
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        log.error("Failed to fetch tags: %s", e)
        return False

    # Try to checkout the matching tag
    tag_name = f"v{replay_build}"
    try:
        subprocess.run(
            ["git", "checkout", tag_name],
            cwd=gamedata_root,
            capture_output=True,
            text=True,
            timeout=120,
            check=True,
        )
        log.info("Gamedata updated to %s", tag_name)
        return True
    except subprocess.CalledProcessError:
        log.warning(
            "Tag %s not found in gamedata repo. "
            "The gamedata pipeline may not have run for this version yet.",
            tag_name,
        )
        return False
    except subprocess.TimeoutExpired:
        log.error("Checkout timed out for %s", tag_name)
        return False
