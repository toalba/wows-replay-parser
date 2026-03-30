"""
wows-replay-parser — World of Warships replay file parser.

Dynamic schema loading from wows-gamedata entity definitions.
No hardcoded schemas, no manual updates per patch.
"""

__version__ = "0.1.0"

from wows_replay_parser.api import ParsedReplay, parse_replay
from wows_replay_parser.ship_config import ShipConfig, parse_ship_config

__all__ = ["ParsedReplay", "parse_replay", "ShipConfig", "parse_ship_config", "__version__"]
