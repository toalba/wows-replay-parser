"""Structural interfaces for replay sources.

Defines ``ReplaySource`` — a ``Protocol`` that both ``ParsedReplay``
(single-perspective) and ``MergedReplay`` (dual-perspective merge)
must satisfy. Renderer code should accept ``ReplaySource`` instead of
``ParsedReplay`` so either implementation plugs in interchangeably.

Kept free of imports from :mod:`wows_replay_parser.api` / ``merge`` so
there are no circular import hazards at module load time.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, TypeVar, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence

    from wows_replay_parser.events.models import GameEvent
    from wows_replay_parser.roster import PlayerInfo
    from wows_replay_parser.state.models import GameState


_T = TypeVar("_T", bound="GameEvent")


@runtime_checkable
class ReplaySource(Protocol):
    """Structural type for anything that looks like a parsed replay.

    Attributes here are the minimum surface renderers depend on. New
    helpers should be added to both :class:`ParsedReplay` and
    :class:`~wows_replay_parser.merge.MergedReplay` in lockstep.
    """

    # --- Core metadata ---------------------------------------------------
    map_name: str
    duration: float
    game_version: str
    meta: dict
    players: "Sequence[PlayerInfo]"
    events: "Sequence[GameEvent]"

    # --- Event / state queries ------------------------------------------
    def events_of_type(self, event_type: type[_T]) -> list[_T]: ...

    def state_at(self, t: float) -> "GameState": ...

    def iter_states(
        self, timestamps: "Sequence[float]",
    ) -> "Iterator[GameState]": ...

    # --- Precomputed helpers (lazy on the concrete implementation) ------
    battle_start_time: float | None
    first_seen: "Mapping[int, float]"
    aim_yaw_timeline: "Mapping[int, list[tuple[float, float]]]"
    camera_yaw_timeline: "Sequence[tuple[float, float]] | None"
    smoke_screen_lifetimes: "Mapping[int, tuple[float, float]]"
    zone_positions: "Mapping[int, Sequence[tuple[float, float, float]]]"
    zone_lifetimes: "Mapping[int, tuple[float, float]]"
    consumable_activations: "Mapping[int, Sequence[tuple[float, int, float]]]"
    crew_modifiers: "Mapping[int, object]"
