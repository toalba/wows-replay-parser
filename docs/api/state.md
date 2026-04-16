# State Models

Dataclasses returned by `ParsedReplay.state_at()` /
`ParsedReplay.iter_states()`.

::: wows_replay_parser.state.models
    options:
      show_root_toc_entry: true
      members_order: source
      filters:
        - "!^_"

## Tracker

::: wows_replay_parser.state.tracker.GameStateTracker
    options:
      show_root_toc_entry: true
      members:
        - state_at
        - iter_states
        - battle_start_time
