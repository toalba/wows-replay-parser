"""Build-aware playersPublicInfo schema selection.

Patch 15.10 (build 13533378) inserted 12 columns into the vehicle-result
tuple, growing the row from 538 to 550 elements. The schema was recovered
from the 15.10 client bytecode (``scripts/m99f8902c.pyc``, internally
``BattleResultsShared``); 15.9 (``scripts/m865ba929.pyc``) dumped a tuple
byte-identical to the pre-existing 466-field one, so 15.10 is the only
break.

Every offset asserted here was cross-checked on real replays against
ground truth that does not come from the BattleResults schema itself:
``PlayerInfo.max_health`` from arena state, summed live ``DamageEvent``s,
and the live ribbon stream.
"""

from __future__ import annotations

from wows_replay_parser.battle_results import (
    CLIENT_PUBLIC_RESULT_FIELDS,
    CLIENT_PUBLIC_RESULT_FIELDS_15_10,
    RIBBON_TAIL_GAP,
    _decode_player,
    schema_for_row_length,
)

ROW_15_9 = 538
ROW_15_10 = 550


def _row(n: int, **at: object) -> list:
    row: list = [0] * n
    for idx, value in at.items():
        row[int(idx.lstrip("i"))] = value
    return row


class TestSchemaSelection:
    def test_15_10_schema_is_twelve_longer(self) -> None:
        assert len(CLIENT_PUBLIC_RESULT_FIELDS_15_10) == 478
        assert len(CLIENT_PUBLIC_RESULT_FIELDS) == 466

    def test_the_twelve_additions_are_pure_insertions(self) -> None:
        """No renames, no deletions: the old tuple is a subsequence."""
        new = iter(CLIENT_PUBLIC_RESULT_FIELDS_15_10)
        assert all(f in new for f in CLIENT_PUBLIC_RESULT_FIELDS)

    def test_538_row_selects_the_pre_15_10_schema(self) -> None:
        assert schema_for_row_length(ROW_15_9) == CLIENT_PUBLIC_RESULT_FIELDS

    def test_550_row_selects_the_15_10_schema(self) -> None:
        assert schema_for_row_length(ROW_15_10) == CLIENT_PUBLIC_RESULT_FIELDS_15_10

    def test_unknown_row_length_returns_no_schema(self) -> None:
        """A future patch must not be silently misread.

        The 15.10 break went unnoticed because every guard tested only for
        a *shorter* row. An unrecognised width returns None so callers can
        degrade instead of reporting plausible garbage.
        """
        assert schema_for_row_length(600) is None
        assert schema_for_row_length(503) is None


class TestFieldOffsets:
    def test_damage_shifts_by_twelve_on_15_10(self) -> None:
        """`damage` sits at index 426 pre-15.10 and 438 on 15.10.

        Verified against summed live DamageEvents: several players matched
        raw[438] exactly (49629/49629, 46292/46292) while raw[426] read ~0.
        """
        old = _decode_player(1, _row(ROW_15_9, i426=123456))
        assert old.stats["damage"] == 123456

        new = _decode_player(1, _row(ROW_15_10, i438=123456))
        assert new.stats["damage"] == 123456

    def test_max_health_is_unshifted_on_both(self) -> None:
        """Index 15 precedes the first insertion (index 66), so it moves
        on neither build. Confirmed exact for every player on both."""
        for n in (ROW_15_9, ROW_15_10):
            p = _decode_player(1, _row(n, i15=47250))
            assert p.stats["max_health"] == 47250

    def test_new_15_10_weapon_fields_are_named(self) -> None:
        p = _decode_player(1, _row(ROW_15_10, i66=5, i270=9))
        assert p.stats["shots_phaser_laser"] == 5
        assert p.stats["damage_shields"] == 9


class TestRibbonBase:
    def test_ribbon_base_follows_the_schema_length(self) -> None:
        """481 = 466 + 15 and 493 = 478 + 15 — a derivable rule, not a
        magic constant. Proven against the live ribbon stream: on 15.10
        base 493 matched 12/12 and 6/6 ribbon ids; 481 matched 0/6."""
        assert RIBBON_TAIL_GAP == 15

        old = _decode_player(1, _row(ROW_15_9, i489=7))
        assert old.ribbon_count(8) == 7

        new = _decode_player(1, _row(ROW_15_10, i501=7))
        assert new.ribbon_count(8) == 7

    def test_ribbons_are_untrusted_on_an_unknown_row(self) -> None:
        p = _decode_player(1, _row(600, i501=7))
        assert p.schema_known is False
        assert p.ribbon_count(8) == 0
        assert p.ribbon_counts() == {}

    def test_ribbons_readable_on_known_builds(self) -> None:
        for n in (ROW_15_9, ROW_15_10):
            assert _decode_player(1, _row(n)).schema_known is True


class TestRegressionGuard:
    def test_short_row_still_rejected(self) -> None:
        """Pre-15.3 rows (503 elements) were the original failure mode."""
        p = _decode_player(1, _row(503))
        assert p.schema_known is False
