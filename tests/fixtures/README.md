# Test fixtures

This directory holds the **sanitised** replay and gamedata artefacts used by the
integration-flavoured tests in `tests/`. None of the binary fixtures are checked
into the repository — see [What gets committed](#what-gets-committed) below.

If this directory is empty, every test that depends on a real replay will
`pytest.skip(...)` cleanly. That is the expected state in CI and on a fresh
clone. You only need to populate this directory if you are working on one of
the code paths that exercise real decoded replays end-to-end.

---

## Layout

```
tests/fixtures/
├── README.md                 # (this file — committed)
├── replays/                  # .wowsreplay files (NOT committed)
│   ├── 15_2_0_solo_dd.wowsreplay
│   ├── 15_2_0_solo_cv.wowsreplay
│   ├── paired_alpha.wowsreplay      # pair half for merge tests
│   └── paired_bravo.wowsreplay      # pair half for merge tests
└── gamedata/                 # entity_defs tree (NOT committed — typically a symlink)
    └── scripts_entity/entity_defs/...
```

### Filename convention

`{version}_{scenario}.wowsreplay` with `version` written with underscores
(mirroring the replay's internal comma-separated game version, e.g. `15,2,0` →
`15_2_0`). Keep `scenario` short, lower-case, snake-cased, and descriptive of
the test surface the replay exercises:

- `15_2_0_solo_dd.wowsreplay` — single-perspective DD replay (default fixture).
- `15_2_0_solo_cv.wowsreplay` — CV, for squadron / airstrike coverage.
- `15_2_0_clan_bb.wowsreplay` — clan battle, for clan-tag / majority logic.
- `paired_alpha.wowsreplay` / `paired_bravo.wowsreplay` — two perspectives of
  the **same** match (same `arenaUniqueId`), for `merge_replays` tests.

Any `.wowsreplay` file in `replays/` will be picked up by the shared
`fixture_replay_path` pytest fixture. When multiple files are present the first
one (lexicographic order) wins for the plain `fixture_replay_path`; the
`paired_fixture_paths` fixture specifically matches `paired_*.wowsreplay`.

---

## Sanitisation policy

Replay files contain PII — player account IDs, player names, clan tags, plus
arbitrary chat text. We do not want any of that entering the repository, even
transitively via CI logs or bug reports. A replay is considered **sanitised**
when:

1. All human player names have been replaced with `Player1 .. PlayerN` (stable
   mapping per replay, but the N→real-name map is discarded before the file
   leaves the author's machine).
2. All clan tags have been replaced with `[CL1] .. [CLN]` (again stable per
   replay, map discarded). Clan colours are left untouched.
3. `accountDBID` is zeroed out for every player (both in the JSON meta header
   and in the `onArenaStateReceived` pickle payload).
4. All `ChatEvent` / `onChatMessage` payloads are replaced with `chat_N`
   placeholders in declaration order.
5. The filename no longer contains any real player name / clan tag — rename to
   the convention above before dropping into `replays/`.

Bot accounts, ship IDs, map names, scores, positions, and all combat data are
**not** sanitised. Those are mechanical game state and carry no PII.

### Sanitisation script (TODO)

There is no in-repo sanitisation tool yet. The slot reserved for it is:

```
scripts/sanitise_replay.py  <input.wowsreplay>  <output.wowsreplay>
```

Implementation notes for whoever writes it:
- Parse the replay JSON header, rewrite `playerName` per-vehicle and the
  recorder's own `playerName`, zero `accountDBID`.
- Re-pickle `onArenaStateReceived.playersStates` with patched name / clan_tag /
  accountDBID fields (see `src/wows_replay_parser/roster.py` for the key map).
- Walk the packet stream and rewrite `onChatMessage` payloads in-place.
- Re-compress + re-encrypt (Blowfish ECB, same key the reader uses).

Until that script exists, replays must be sanitised by hand. Keep the fixtures
you use locally — the repo does not want them.

---

## Gamedata

The parser needs an `entity_defs` tree that matches the replay's game version.
`fixture_gamedata_path` resolves it in this order:

1. `tests/fixtures/gamedata/` if the directory exists (symlink is fine).
2. `wows-gamedata/data/` at the repo root (the default dev checkout path).
3. Otherwise `pytest.skip(...)`.

The simplest setup is a symlink:

```bash
cd tests/fixtures
ln -s ../../wows-gamedata/data gamedata
```

If you are testing against a pinned version that differs from your working
gamedata checkout, point the symlink at a dedicated `git worktree` of
`wows-gamedata` at the right tag.

---

## What gets committed

| Path                            | Committed? |
| ------------------------------- | ---------- |
| `tests/fixtures/README.md`      | yes        |
| `tests/fixtures/replays/*.wowsreplay` | **no**  |
| `tests/fixtures/gamedata/`      | **no**     |

See the repo `.gitignore` — both patterns are ignored. Replay files are
potentially copyrighted game artefacts even after PII sanitisation, and
bloat the git history quickly; contributors generate them locally.

---

## Adding a new fixture

1. Record a replay in-client, or pick one from your own archive.
2. Sanitise it (manually for now, per the policy above).
3. Rename it to the `{version}_{scenario}` convention.
4. Drop it into `tests/fixtures/replays/`.
5. Make sure `tests/fixtures/gamedata/` resolves to an `entity_defs` tree for
   the matching version.
6. `uv run pytest tests/` — the previously-skipping tests should now run.
