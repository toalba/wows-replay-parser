"""
wows-replay-parser — World of Warships replay file parser.

Dynamic schema loading from wows-gamedata entity definitions.
No hardcoded schemas, no manual updates per patch.
"""

__version__ = "0.1.0"

from wows_replay_parser.api import ParsedReplay, parse_replay
from wows_replay_parser.battle_results import (
    CLIENT_PUBLIC_RESULT_FIELDS,
    COMMON_RESULT_FIELDS,
    PLAYER_PRIVATE_RESULT_FIELDS,
    BattleResults,
    PlayerBattleResult,
)
from wows_replay_parser.ribbons import (
    RIBBON_DEATH_TIME_SEC,
    RIBBON_LIFE_TIME_SEC,
    RIBBON_WIRE_IDS,
    coalesce_ribbon_popups,
    extract_recording_player_ribbons,
)
from wows_replay_parser.ship_config import ShipConfig, parse_ship_config

__all__ = [
    "ParsedReplay", "parse_replay",
    "ShipConfig", "parse_ship_config",
    "RIBBON_WIRE_IDS", "extract_recording_player_ribbons",
    "coalesce_ribbon_popups", "RIBBON_LIFE_TIME_SEC", "RIBBON_DEATH_TIME_SEC",
    "BattleResults", "PlayerBattleResult",
    "CLIENT_PUBLIC_RESULT_FIELDS", "COMMON_RESULT_FIELDS", "PLAYER_PRIVATE_RESULT_FIELDS",
    "__version__",
]
