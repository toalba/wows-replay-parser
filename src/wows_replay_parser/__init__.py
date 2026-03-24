"""
wows-replay-parser — World of Warships replay file parser.

Dynamic schema loading from wows-gamedata entity definitions.
No hardcoded schemas, no manual updates per patch.
"""

__version__ = "0.1.0"

from wows_replay_parser.api import ParsedReplay, parse_replay

__all__ = ["ParsedReplay", "parse_replay", "__version__"]
