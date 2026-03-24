"""Integration tests using real replay + gamedata files."""

from __future__ import annotations

from pathlib import Path

import pytest

# Paths relative to project root
PROJECT_ROOT = Path(__file__).parent.parent
REPLAY_FILE = PROJECT_ROOT / "20260322_172639_PHSC710-Prins-Van-Oranje_56_AngelWings.wowsreplay"
GAMEDATA_DIR = PROJECT_ROOT / "wows-gamedata" / "data" / "scripts_entity" / "entity_defs"


@pytest.fixture(scope="session")
def parsed_replay():
    """Parse the test replay file (session-scoped to avoid repeated parsing)."""
    if not REPLAY_FILE.exists():
        pytest.skip("No replay file available")
    if not GAMEDATA_DIR.exists():
        pytest.skip("No gamedata directory available")

    from wows_replay_parser.api import parse_replay

    return parse_replay(REPLAY_FILE, GAMEDATA_DIR)


class TestReplayParsing:
    def test_meta_is_populated(self, parsed_replay) -> None:
        assert parsed_replay.meta is not None
        assert "playerName" in parsed_replay.meta
        assert "mapName" in parsed_replay.meta

    def test_game_version_present(self, parsed_replay) -> None:
        assert parsed_replay.game_version
        # WoWs uses comma-separated version: "15,2,0,12116141"
        assert "," in parsed_replay.game_version

    def test_map_name_present(self, parsed_replay) -> None:
        assert parsed_replay.map_name

    def test_packets_decoded(self, parsed_replay) -> None:
        assert len(parsed_replay.packets) > 0

    def test_events_generated(self, parsed_replay) -> None:
        assert len(parsed_replay.events) > 0

    def test_events_sorted_by_timestamp(self, parsed_replay) -> None:
        timestamps = [e.timestamp for e in parsed_replay.events]
        assert timestamps == sorted(timestamps)

    def test_duration_positive(self, parsed_replay) -> None:
        assert parsed_replay.duration > 0

    def test_players_populated(self, parsed_replay) -> None:
        # A standard WoWs match has 24 players (12v12)
        assert len(parsed_replay.players) > 0

    def test_position_events_exist(self, parsed_replay) -> None:
        from wows_replay_parser.events.models import PositionEvent

        pos_events = parsed_replay.events_of_type(PositionEvent)
        assert len(pos_events) > 0

    def test_state_at_midgame(self, parsed_replay) -> None:
        mid = parsed_replay.duration / 2
        state = parsed_replay.state_at(mid)
        assert state is not None
        # Should have some ships
        assert len(state.ships) > 0

    def test_ships_have_tracked_properties(self, parsed_replay) -> None:
        """Verify that vehicles have property updates tracked."""
        tracker = parsed_replay._tracker
        vids = tracker.get_vehicle_entity_ids()
        assert len(vids) > 0
        # At least some vehicles should have health property tracked
        has_health = any(
            "health" in tracker.get_entity_props(vid)
            for vid in vids
        )
        assert has_health, "No vehicle had health property"


class TestReplayReader:
    def test_read_json_headers(self) -> None:
        if not REPLAY_FILE.exists():
            pytest.skip("No replay file available")

        from wows_replay_parser.replay.reader import ReplayReader

        reader = ReplayReader()
        replay = reader.read(REPLAY_FILE)

        assert replay.meta is not None
        assert len(replay.packet_data) > 0
        assert replay.game_version
        assert replay.map_name
