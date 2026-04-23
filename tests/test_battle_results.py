"""Unit tests for BattleResults decoder."""

from __future__ import annotations

from dataclasses import dataclass

from wows_replay_parser.battle_results import (
    CLIENT_PUBLIC_RESULT_FIELDS,
    COMMON_RESULT_FIELDS,
    PLAYER_INFO_FIELDS,
    PLAYER_PRIVATE_RESULT_FIELDS,
    VEH_BASE_RESULT_FIELDS,
    BattleResults,
    PlayerBattleResult,
)


class TestSchemas:
    def test_player_info_count(self) -> None:
        assert len(PLAYER_INFO_FIELDS) == 20

    def test_veh_base_count(self) -> None:
        assert len(VEH_BASE_RESULT_FIELDS) == 446

    def test_client_public_concat(self) -> None:
        assert len(CLIENT_PUBLIC_RESULT_FIELDS) == 466
        assert CLIENT_PUBLIC_RESULT_FIELDS == PLAYER_INFO_FIELDS + VEH_BASE_RESULT_FIELDS

    def test_common_count(self) -> None:
        assert len(COMMON_RESULT_FIELDS) == 18

    def test_private_count(self) -> None:
        assert len(PLAYER_PRIVATE_RESULT_FIELDS) == 55

    def test_leading_identity_fields(self) -> None:
        # From the 20-tuple PLAYER_INFO starting with account_db_id
        assert CLIENT_PUBLIC_RESULT_FIELDS[0] == "account_db_id"
        assert CLIENT_PUBLIC_RESULT_FIELDS[1] == "name"
        assert CLIENT_PUBLIC_RESULT_FIELDS[2] == "clan_id"
        assert CLIENT_PUBLIC_RESULT_FIELDS[3] == "clan_tag"
        assert CLIENT_PUBLIC_RESULT_FIELDS[6] == "team_id"
        assert CLIENT_PUBLIC_RESULT_FIELDS[7] == "vehicle_type_id"
        assert CLIENT_PUBLIC_RESULT_FIELDS[9] == "home_realm"
        assert CLIENT_PUBLIC_RESULT_FIELDS[15] == "max_health"

    def test_first_stats_field(self) -> None:
        # 20-tuple ends at index 19; 21st field is remained_hp from VEH_BASE
        assert CLIENT_PUBLIC_RESULT_FIELDS[20] == "remained_hp"
        assert CLIENT_PUBLIC_RESULT_FIELDS[21] == "is_alive"
        assert CLIENT_PUBLIC_RESULT_FIELDS[22] == "life_time_sec"

    def test_common_result_leading(self) -> None:
        assert COMMON_RESULT_FIELDS[0] == "arena_id"
        assert COMMON_RESULT_FIELDS[1] == "cluster_id"
        assert COMMON_RESULT_FIELDS[3] == "winner_team_id"


@dataclass
class _FakeEvent:
    """Mimic BattleResultsEvent for from_event()."""

    results: dict


class TestDecoder:
    def _sample_results(self) -> dict:
        return {
            "accountDBID": 12345,
            "arenaUniqueID": 99999,
            "commonList": [
                7000001, 4000, 1700000000, 1, 13,
                8, "regular", 33, 600, 17,
                "cvc_domination", 0, 7, "", {},
                0, 0, 0,
            ],
            "playersPublicInfo": {
                "12345": [
                    12345,        # account_db_id
                    "Tester",     # name
                    500,          # clan_id
                    "ABC",        # clan_tag
                    0xFF00FF,     # clan_color
                    2,            # clan_league
                    1,            # team_id
                    4181636560,   # vehicle_type_id
                ] + [0] * 300,
            },
            "privateDataList": [0] * 55,
        }

    def test_decode_common(self) -> None:
        br = BattleResults.from_event(_FakeEvent(results=self._sample_results()))
        assert br.own_db_id == 12345
        assert br.arena_unique_id == 99999
        assert br.common["arena_id"] == 7000001
        assert br.common["winner_team_id"] == 1
        assert br.common["duration_sec"] == 600
        assert br.common["team_build_type_id"] == 8
        assert br.common["clan_season_type"] == "regular"

    def test_decode_own_player(self) -> None:
        br = BattleResults.from_event(_FakeEvent(results=self._sample_results()))
        own = br.own_result
        assert own is not None
        assert own.db_id == 12345
        assert own.name == "Tester"
        assert own.clan_tag == "ABC"
        assert own.team_id == 1
        assert own.stat("clan_id") == 500
        assert own.stat("vehicle_type_id") == 4181636560

    def test_raw_preserved(self) -> None:
        br = BattleResults.from_event(_FakeEvent(results=self._sample_results()))
        own = br.own_result
        assert own is not None
        assert own.raw[0] == 12345
        assert own.raw[1] == "Tester"
        assert len(own.raw) == 308  # 8 + 300

    def test_extra_fields_captured(self) -> None:
        # Raw list: 466 schema slots + 5 extras = 471 total
        results = self._sample_results()
        results["playersPublicInfo"]["12345"] = (
            list(range(466)) + [99, 98, 97, 96, 95]
        )
        br = BattleResults.from_event(_FakeEvent(results=results))
        own = br.own_result
        assert own is not None
        assert len(own.raw) == 471
        # Schema covers raw indices 0..465. Extras start at raw index 466.
        assert own.extra == {466: 99, 467: 98, 468: 97, 469: 96, 470: 95}

    def test_missing_event_returns_empty(self) -> None:
        br = BattleResults.from_event(_FakeEvent(results={}))
        assert br.own_db_id == 0
        assert br.players == {}
        assert br.own_result is None

    def test_stat_default(self) -> None:
        player = PlayerBattleResult(db_id=1, stats={"foo": 42}, raw=[])
        assert player.stat("foo") == 42
        assert player.stat("missing") == 0
        assert player.stat("missing", default=-1) == -1
