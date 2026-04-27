"""BattleResults (packet 0x22) structured decoder."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from wows_replay_parser.events.models import BattleResultsEvent

PLAYER_INFO_FIELDS: tuple[str, ...] = (
    'account_db_id',
    'name',
    'clan_id',
    'clan_tag',
    'clan_color',
    'clan_league',
    'team_id',
    'vehicle_type_id',
    'prebattle_id',
    'home_realm',
    'achievements',
    'rank_battles_season_id',
    'rank_info_dump',
    'prebattle_sign',
    'initial_prebattle_id',
    'max_health',
    'is_hidden',
    'playerMode',
    'isMercenary',
    'brawl_rating_data',
)
assert len(PLAYER_INFO_FIELDS) == 20

VEH_BASE_RESULT_FIELDS: tuple[str, ...] = (
    'remained_hp',
    'is_alive',
    'life_time_sec',
    'distance',
    'capture_points',
    'dropped_capture_points',
    'first_ships_spotted_by_ship',
    'first_ships_spotted_by_plane',
    'first_planes_spotted_by_ship',
    'first_planes_spotted_by_plane',
    'first_plane_items_spotted_by_ship',
    'first_plane_items_spotted_by_plane',
    'ships_killed',
    'team_ships_killed',
    'killer_building_id',
    'shots_main_ap',
    'shots_main_cs',
    'shots_main_he',
    'shots_atba_ap',
    'shots_atba_cs',
    'shots_atba_he',
    'shots_atba_ap_manual',
    'shots_atba_cs_manual',
    'shots_atba_he_manual',
    'shots_tpd',
    'shots_bomb',
    'shots_bomb_avia',
    'shots_bomb_alt',
    'shots_bomb_airsupport',
    'shots_dbomb_airsupport',
    'shots_tbomb',
    'shots_tbomb_avia',
    'shots_tbomb_alt',
    'shots_tbomb_airsupport',
    'shots_rocket',
    'shots_rocket_avia',
    'shots_rocket_alt',
    'shots_rocket_airsupport',
    'shots_skip',
    'shots_skip_avia',
    'shots_skip_alt',
    'shots_skip_airsupport',
    'shots_adbomb',
    'shots_dbomb',
    'shots_sea_mine',
    'shots_missile',
    'hits_main_ap',
    'hits_main_cs',
    'hits_main_he',
    'hits_atba_ap',
    'hits_atba_cs',
    'hits_atba_he',
    'hits_atba_ap_manual',
    'hits_atba_cs_manual',
    'hits_atba_he_manual',
    'hits_tpd',
    'hits_bomb',
    'hits_bomb_avia',
    'hits_bomb_alt',
    'hits_bomb_airsupport',
    'hits_tbomb',
    'hits_tbomb_avia',
    'hits_tbomb_alt',
    'hits_tbomb_airsupport',
    'hits_ram',
    'hits_fire',
    'hits_flood',
    'hits_dbomb',
    'hits_rocket',
    'hits_rocket_avia',
    'hits_rocket_alt',
    'hits_rocket_airsupport',
    'hits_skip',
    'hits_skip_avia',
    'hits_skip_alt',
    'hits_skip_airsupport',
    'hits_dbomb_airsupport',
    'hits_adbomb',
    'hits_sea_mine',
    'hits_missile',
    'hits_phaser_laser',
    'received_hits_main_ap',
    'received_hits_main_cs',
    'received_hits_main_he',
    'received_hits_atba_ap',
    'received_hits_atba_cs',
    'received_hits_atba_he',
    'received_hits_atba_ap_manual',
    'received_hits_atba_cs_manual',
    'received_hits_atba_he_manual',
    'received_hits_tpd',
    'received_hits_bomb',
    'received_hits_bomb_avia',
    'received_hits_bomb_alt',
    'received_hits_bomb_airsupport',
    'received_hits_tbomb',
    'received_hits_tbomb_avia',
    'received_hits_tbomb_alt',
    'received_hits_tbomb_airsupport',
    'received_hits_ram',
    'received_hits_fire',
    'received_hits_flood',
    'received_hits_sea_mine',
    'received_hits_dbomb',
    'received_hits_rocket',
    'received_hits_rocket_avia',
    'received_hits_rocket_alt',
    'received_hits_rocket_airsupport',
    'received_hits_skip',
    'received_hits_skip_avia',
    'received_hits_skip_alt',
    'received_hits_skip_airsupport',
    'received_hits_dbomb_airsupport',
    'received_hits_missile',
    'received_hits_from_buildings_main_ap',
    'received_hits_from_buildings_main_cs',
    'received_hits_from_buildings_main_he',
    'received_hits_from_buildings_atba_ap',
    'received_hits_from_buildings_atba_cs',
    'received_hits_from_buildings_atba_he',
    'received_hits_from_buildings_fire',
    'received_hits_from_buildings_flood',
    'received_hits_from_buildings_bomb_avia',
    'received_hits_from_buildings_tbomb_avia',
    'received_hits_from_buildings_rocket_avia',
    'received_hits_from_buildings_skip_avia',
    'received_hits_from_buildings_bomb_alt',
    'received_hits_from_buildings_tbomb_alt',
    'received_hits_from_buildings_rocket_alt',
    'received_hits_from_buildings_skip_alt',
    'received_hits_from_buildings_bomb_airsupport',
    'received_hits_from_buildings_dbomb_airsupport',
    'received_hits_from_buildings_tbomb_airsupport',
    'received_hits_from_buildings_rocket_airsupport',
    'received_hits_from_buildings_skip_airsupport',
    'damage_main_ap',
    'damage_main_cs',
    'damage_main_he',
    'damage_atba_ap',
    'damage_atba_cs',
    'damage_atba_he',
    'damage_atba_ap_manual',
    'damage_atba_cs_manual',
    'damage_atba_he_manual',
    'damage_tpd_normal',
    'damage_tpd_deep',
    'damage_tpd_alter',
    'damage_bomb',
    'damage_bomb_avia',
    'damage_bomb_alt',
    'damage_bomb_airsupport',
    'damage_tbomb',
    'damage_tbomb_avia',
    'damage_tbomb_alt',
    'damage_tbomb_airsupport',
    'damage_ram',
    'damage_fire',
    'damage_flood',
    'damage_dbomb_direct',
    'damage_dbomb_splash',
    'damage_sea_mine',
    'damage_rocket',
    'damage_rocket_avia',
    'damage_rocket_alt',
    'damage_rocket_airsupport',
    'damage_skip',
    'damage_skip_avia',
    'damage_skip_alt',
    'damage_skip_airsupport',
    'damage_wave',
    'damage_charge_laser',
    'damage_pulse_laser',
    'damage_axis_laser',
    'damage_phaser_laser',
    'damage_event_1',
    'damage_event_2',
    'damage_dbomb_airsupport',
    'damage_adbomb',
    'damage_missile',
    'received_damage_main_ap',
    'received_damage_main_cs',
    'received_damage_main_he',
    'received_damage_tpd_normal',
    'received_damage_tpd_deep',
    'received_damage_tpd_alter',
    'received_damage_bomb',
    'received_damage_bomb_avia',
    'received_damage_bomb_alt',
    'received_damage_bomb_airsupport',
    'received_damage_tbomb',
    'received_damage_tbomb_avia',
    'received_damage_tbomb_alt',
    'received_damage_tbomb_airsupport',
    'received_damage_ram',
    'received_damage_atba_ap',
    'received_damage_atba_cs',
    'received_damage_atba_he',
    'received_damage_atba_ap_manual',
    'received_damage_atba_cs_manual',
    'received_damage_atba_he_manual',
    'received_damage_fire',
    'received_damage_flood',
    'received_damage_event_1',
    'received_damage_event_2',
    'received_damage_mirror',
    'received_damage_sea_mine',
    'received_damage_special',
    'received_damage_dbomb',
    'received_damage_rocket',
    'received_damage_rocket_avia',
    'received_damage_rocket_alt',
    'received_damage_rocket_airsupport',
    'received_damage_skip',
    'received_damage_skip_avia',
    'received_damage_skip_alt',
    'received_damage_skip_airsupport',
    'received_damage_dbomb_airsupport',
    'received_damage_adbomb',
    'received_damage_missile',
    'received_damage_from_buildings_main_ap',
    'received_damage_from_buildings_main_cs',
    'received_damage_from_buildings_main_he',
    'received_damage_from_buildings_atba_ap',
    'received_damage_from_buildings_atba_cs',
    'received_damage_from_buildings_atba_he',
    'received_damage_from_buildings_fire',
    'received_damage_from_buildings_flood',
    'received_damage_from_buildings_bomb_avia',
    'received_damage_from_buildings_tbomb_avia',
    'received_damage_from_buildings_rocket_avia',
    'received_damage_from_buildings_skip_avia',
    'received_damage_from_buildings_bomb_alt',
    'received_damage_from_buildings_tbomb_alt',
    'received_damage_from_buildings_rocket_alt',
    'received_damage_from_buildings_skip_alt',
    'received_damage_from_buildings_bomb_airsupport',
    'received_damage_from_buildings_dbomb_airsupport',
    'received_damage_from_buildings_tbomb_airsupport',
    'received_damage_from_buildings_rocket_airsupport',
    'received_damage_from_buildings_skip_airsupport',
    'module_breaks',
    'module_crits',
    'module_major_crits',
    'module_fires',
    'module_floods',
    'received_module_crits_artillery',
    'received_module_crits_torpedo_tube',
    'received_module_crits_atba',
    'received_module_crits_air_defense',
    'received_module_crits_engine',
    'received_module_crits_steering_gear',
    'received_module_crits_pinger',
    'received_module_breaks_artillery',
    'received_module_breaks_torpedo_tube',
    'received_module_breaks_atba',
    'received_module_breaks_air_defense',
    'received_module_breaks_depth_charge_gun',
    'battle_drops_picked',
    'battle_picked_drop_points',
    'team_captured_drop_count',
    'planes_killed_by_ship',
    'planes_killed_by_plane',
    'team_planes_killed',
    'planes_lost_scouts',
    'planes_lost_sfighters',
    'planes_lost_fighters',
    'planes_lost_fighters_avia',
    'planes_lost_fighters_airsupport',
    'planes_lost_bombers',
    'planes_lost_bombers_avia',
    'planes_lost_bombers_airsupport',
    'planes_lost_tbombers',
    'planes_lost_tbombers_avia',
    'planes_lost_tbombers_airsupport',
    'planes_lost_skipbombers',
    'planes_lost_skipbombers_avia',
    'planes_lost_skipbombers_airsupport',
    'planes_lost_fighters_alt',
    'planes_lost_bombers_alt',
    'planes_lost_tbombers_alt',
    'planes_lost_skipbombers_alt',
    'scouts_total_killed',
    'sfighters_total_killed',
    'fighters_total_killed',
    'fighters_total_killed_avia',
    'fighters_total_killed_alt',
    'fighters_total_killed_airsupport',
    'bombers_total_killed',
    'bombers_total_killed_avia',
    'bombers_total_killed_alt',
    'bombers_total_killed_airsupport',
    'tbombers_total_killed',
    'tbombers_total_killed_avia',
    'tbombers_total_killed_alt',
    'tbombers_total_killed_airsupport',
    'skipbombers_total_killed',
    'skipbombers_total_killed_avia',
    'skipbombers_total_killed_alt',
    'skipbombers_total_killed_airsupport',
    'planes_killed_by_scouts',
    'planes_killed_by_fighters',
    'planes_killed_by_bombers',
    'planes_killed_by_tbombers',
    'planes_killed_by_sfighters',
    'planes_killed_by_skipbombers',
    'sfighters_killed_by_ship',
    'sfighters_killed_by_fighters',
    'sfighters_killed_by_bombers',
    'sfighters_killed_by_tbombers',
    'sfighters_killed_by_sfighters',
    'sfighters_killed_by_scouts',
    'sfighters_killed_by_skipbombers',
    'scouts_killed_by_ship',
    'scouts_killed_by_fighters',
    'scouts_killed_by_bombers',
    'scouts_killed_by_tbombers',
    'scouts_killed_by_sfighters',
    'scouts_killed_by_scouts',
    'scouts_killed_by_skipbombers',
    'fighters_killed_by_ship',
    'fighters_killed_by_ship_avia',
    'fighters_killed_by_ship_alt',
    'fighters_killed_by_ship_airsupport',
    'fighters_killed_by_fighters',
    'fighters_killed_by_fighters_avia',
    'fighters_killed_by_fighters_alt',
    'fighters_killed_by_fighters_airsupport',
    'fighters_killed_by_bombers',
    'fighters_killed_by_tbombers',
    'fighters_killed_by_sfighters',
    'fighters_killed_by_sfighters_avia',
    'fighters_killed_by_sfighters_alt',
    'fighters_killed_by_sfighters_airsupport',
    'fighters_killed_by_scouts',
    'fighters_killed_by_skipbombers',
    'bombers_killed_by_ship',
    'bombers_killed_by_ship_avia',
    'bombers_killed_by_ship_alt',
    'bombers_killed_by_ship_airsupport',
    'bombers_killed_by_fighters',
    'bombers_killed_by_fighters_avia',
    'bombers_killed_by_fighters_alt',
    'bombers_killed_by_fighters_airsupport',
    'bombers_killed_by_bombers',
    'bombers_killed_by_tbombers',
    'bombers_killed_by_sfighters',
    'bombers_killed_by_sfighters_avia',
    'bombers_killed_by_sfighters_alt',
    'bombers_killed_by_sfighters_airsupport',
    'bombers_killed_by_scouts',
    'bombers_killed_by_skipbombers',
    'tbombers_killed_by_ship',
    'tbombers_killed_by_ship_avia',
    'tbombers_killed_by_ship_alt',
    'tbombers_killed_by_ship_airsupport',
    'tbombers_killed_by_fighters',
    'tbombers_killed_by_fighters_avia',
    'tbombers_killed_by_fighters_alt',
    'tbombers_killed_by_fighters_airsupport',
    'tbombers_killed_by_bombers',
    'tbombers_killed_by_tbombers',
    'tbombers_killed_by_sfighters',
    'tbombers_killed_by_sfighters_avia',
    'tbombers_killed_by_sfighters_alt',
    'tbombers_killed_by_sfighters_airsupport',
    'tbombers_killed_by_scouts',
    'tbombers_killed_by_skipbombers',
    'skipbombers_killed_by_ship',
    'skipbombers_killed_by_ship_avia',
    'skipbombers_killed_by_ship_alt',
    'skipbombers_killed_by_ship_airsupport',
    'skipbombers_killed_by_fighters',
    'skipbombers_killed_by_fighters_alt',
    'skipbombers_killed_by_fighters_avia',
    'skipbombers_killed_by_fighters_airsupport',
    'skipbombers_killed_by_bombers',
    'skipbombers_killed_by_tbombers',
    'skipbombers_killed_by_sfighters',
    'skipbombers_killed_by_sfighters_avia',
    'skipbombers_killed_by_sfighters_alt',
    'skipbombers_killed_by_sfighters_airsupport',
    'skipbombers_killed_by_scouts',
    'skipbombers_killed_by_skipbombers',
    'raw_exp',
    'exp',
    'interactions',
    'buildingInteractions',
    'is_abuser',
    'killer_db_id',
    'killer_veh_id',
    'killer_weapon',
    'tpds_spotted',
    'scouting_damage',
    'scouting_fires',
    'cp_capture_points',
    'cp_dropped_points',
    'agro_art',
    'agro_tpd',
    'agro_air',
    'agro_dbomb',
    'team_captured_points',
    'team_dropped_points',
    'damage_airdefense',
    'damage_planes_by_plane',
    'vehicle_damage_by_airdefense',
    'vehicle_damage_planes_by_plane',
    'damage',
    'resources',
    'enemy_energy_burned',
    'teamLadder',
    'key_target_markers',
    'victory_points_cp_base_capture',
    'victory_points_cp_neutral_capture',
    'victory_points_cp_team_capture',
    'victory_points_cp_hold',
    'victory_points_cp_base_block',
    'victory_points_cp_neutral_block',
    'victory_points_cp_team_block',
    'victory_points_cp_earning_block',
    'victory_points_cp_base_drop',
    'victory_points_cp_neutral_drop',
    'victory_points_cp_team_drop',
    'victory_points_arms_race_drop_pickup',
    'victory_points_kill_destroyer',
    'victory_points_kill_cruiser',
    'victory_points_kill_battleship',
    'victory_points_kill_carrier',
    'victory_points_kill_submarine',
    'victory_points_own_ship_kill',
    'victory_points_victory_by_kill',
    'victory_points_victory_by_score_zero',
    'victory_points_victory_by_capture',
    'victory_points_cp_battle_end_base',
    'victory_points_cp_battle_end_neutral',
    'victory_points_cp_battle_end_team',
    'victory_points_pull_pulled_to_destination',
    'victory_points_pull_win_extermination',
    'victory_points_pull_kill',
    'victory_points_pull_pulling',
    'victory_points_pull_enemy_blocking',
    'victory_points_pull_pulling_while_blocked',
    'victory_points_protection_attackers_lose',
    'victory_points_protection_target_killed',
    'victory_points_protection_target_reached',
    'victory_points_protection_enemy_skip_kill',
    'victory_points_victory_general',
)
assert len(VEH_BASE_RESULT_FIELDS) == 446

COMMON_RESULT_FIELDS: tuple[str, ...] = (
    'arena_id',
    'cluster_id',
    'start_dt',
    'winner_team_id',
    'win_type_id',
    'team_build_type_id',
    'clan_season_type',
    'clan_season_id',
    'duration_sec',
    'map_type_id',
    'scenario_name',
    'survey_id',
    'game_mode',
    'sse_info',
    'battle_logic_info',
    'weather_preset_id',
    'pve_operation_id',
    'event_operation_id',
)
assert len(COMMON_RESULT_FIELDS) == 18

CLIENT_PUBLIC_RESULT_FIELDS: tuple[str, ...] = PLAYER_INFO_FIELDS + VEH_BASE_RESULT_FIELDS
assert len(CLIENT_PUBLIC_RESULT_FIELDS) == 466


PLAYER_PRIVATE_RESULT_FIELDS: tuple[str, ...] = (
    "team_id", "vehicle_type_id", "premium_type", "account_prev_tier",
    "account_points_prev", "init_economics", "common_economics",
    "subtotal_economics", "globalboosts_mods", "tasks", "epics", "chains",
    "sse_bonuses", "campaign_tasks", "bonus_tags", "ship_aces",
    "strategic_actions", "survey_info", "rank_stars_old", "rank_stars_gained",
    "rank_stars_new", "rank_old", "rank_new", "rank_league",
    "rank_victories_old", "rank_victories_new", "rank_victory_rewards",
    "first_rank_rewards", "rank_qualification_rewards",
    "fast_rank_qualification_rewards", "rank_victory_rewards_progress",
    "battles_to_clean_abuse", "abuser_status", "abuser_cleaned", "crew_dump",
    "pve_details", "arc_details", "bonus_currency", "event_hub_rewards",
    "event_hub_next_rewards", "event_hub_next_points", "mastery_sign",
    "statist_achievements", "is_premium", "is_participating_in_clan_wars",
    "penetrations", "planes_killed_by_plane",
    "_priv_46", "_priv_47", "_priv_48", "_priv_49", "_priv_50", "_priv_51",
    "_priv_52", "_priv_53",
)
assert len(PLAYER_PRIVATE_RESULT_FIELDS) == 55  # 46 real + 9 padding


RIBBON_COUNT_BASE_INDEX: int = 481
"""Base offset in the 538-element ``playersPublicInfo`` list where the
dynamically-appended per-ribbon counters live, one per ribbon_id.

Discovered empirically by correlating wire ribbon events against the tail
across 8 replays: ``raw_list[481 + ribbon_id]`` holds the final authoritative
lifetime count for that ribbon. This matches the client's
``entity.incomeRibbon.count`` (the number shown in the HUD top-right at end
of match) as reverse-engineered from ``RibbonSystem.__onRemove``.

The server builds this section of the list dynamically at import time by
iterating ``Ribbons.iterAll()`` (see ``scripts/me087a78d.pyc``) and
appending one counter slot per Ribbon in declaration order — which is why
slot offsets line up with ribbon_id values.
"""


@dataclass
class PlayerBattleResult:
    """Post-battle stats for one player.

    ``stats`` maps field names from the 466-element CLIENT_PUBLIC_RESULT
    schema (``PLAYER_INFO_FIELDS + VEH_BASE_RESULT_FIELDS``) to values from
    ``playersPublicInfo[dbid][0..465]``. Indices 466-537 are tail extras
    built dynamically at server import time (ribbon counters from
    ``Ribbons.iterAll()``, SubRibbon counters, ship-config flags,
    presence-time extensions, interaction details) and are preserved in
    ``extra`` keyed by raw list index.

    For per-ribbon authoritative counts use :meth:`ribbon_counts` /
    :meth:`ribbon_count` which read the tail ``[481 + ribbon_id]`` slot.
    """

    db_id: int
    stats: dict[str, Any] = field(default_factory=dict)
    extra: dict[int, Any] = field(default_factory=dict)
    raw: list = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.stats.get("name", "")

    @property
    def team_id(self) -> int:
        return int(self.stats.get("team_id", 0) or 0)

    @property
    def clan_tag(self) -> str:
        return self.stats.get("clan_tag", "") or ""

    def stat(self, field_name: str, default: Any = 0) -> Any:
        """Look up a named stat field. Returns ``default`` if missing."""
        return self.stats.get(field_name, default)

    def ribbon_count(self, ribbon_id: int) -> int:
        """Final count for a specific ribbon_id.

        Reads ``raw[481 + ribbon_id]`` — the server's authoritative lifetime
        tally for this ribbon type, matching what the HUD top-right shows at
        end of match. Prefer this over summing wire RibbonEvent counts,
        which can under-count on high-frequency ribbons in some replays
        where the server batches updates outside ``privateVehicleState``.

        Returns 0 if the slot is missing or the ribbon never fired.
        """
        idx = RIBBON_COUNT_BASE_INDEX + ribbon_id
        if idx >= len(self.raw):
            return 0
        val = self.raw[idx]
        return int(val) if isinstance(val, (int, float)) else 0

    def ribbon_counts(self) -> dict[int, int]:
        """All non-zero ribbon counts keyed by ribbon_id.

        Returns ``{ribbon_id: count}`` for every Ribbon that fired at least
        once this match. Wire ids 0-59 are defined (see
        ``wows_replay_parser.ribbons.RIBBON_WIRE_IDS``). Sourced from the
        tail slots ``raw[481..540]``; authoritative end-of-match tally.
        """
        out: dict[int, int] = {}
        for rid in range(60):
            n = self.ribbon_count(rid)
            if n > 0:
                out[rid] = n
        return out


@dataclass
class BattleResults:
    """Post-battle results from packet 0x22.

    Schemas extracted from obfuscated ``scripts/m0b4b170b.pyc``
    (internally referenced as ``BattleResultsShared``) on build 12267945
    (15.3.0). Re-verify after patches.
    """

    own_db_id: int
    arena_unique_id: int
    common: dict[str, Any] = field(default_factory=dict)
    players: dict[int, PlayerBattleResult] = field(default_factory=dict)
    own_private: dict[str, Any] = field(default_factory=dict)
    raw: dict = field(default_factory=dict)

    @property
    def own_result(self) -> PlayerBattleResult | None:
        return self.players.get(self.own_db_id)

    @classmethod
    def from_event(cls, event: BattleResultsEvent) -> BattleResults:
        return _decode(event.results)


def _decode(results: dict) -> BattleResults:
    own_db_id = int(results.get("accountDBID", 0) or 0)
    arena_id = int(results.get("arenaUniqueID", 0) or 0)

    common = _map_list(results.get("commonList") or [], COMMON_RESULT_FIELDS)

    players: dict[int, PlayerBattleResult] = {}
    ppi = results.get("playersPublicInfo") or {}
    if isinstance(ppi, dict):
        for key, raw_list in ppi.items():
            if not isinstance(raw_list, list) or not raw_list:
                continue
            try:
                db_id = int(key)
            except (TypeError, ValueError):
                continue
            players[db_id] = _decode_player(db_id, raw_list)

    own_private: dict[str, Any] = {}
    pdl = results.get("privateDataList")
    if isinstance(pdl, list):
        own_private = _map_list(pdl, PLAYER_PRIVATE_RESULT_FIELDS)

    return BattleResults(
        own_db_id=own_db_id,
        arena_unique_id=arena_id,
        common=common,
        players=players,
        own_private=own_private,
        raw=results,
    )


def _decode_player(db_id: int, raw_list: list) -> PlayerBattleResult:
    stats: dict[str, Any] = {}
    extra: dict[int, Any] = {}
    for i, value in enumerate(raw_list):
        if i < len(CLIENT_PUBLIC_RESULT_FIELDS):
            stats[CLIENT_PUBLIC_RESULT_FIELDS[i]] = value
        else:
            extra[i] = value
    return PlayerBattleResult(db_id=db_id, stats=stats, extra=extra, raw=raw_list)


def _map_list(values: list, fields: tuple[str, ...]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for i, name in enumerate(fields):
        out[name] = values[i] if i < len(values) else None
    return out
