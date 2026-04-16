# Contributing

Thanks for taking the time to contribute. This project is small enough that
the process is informal, but a few conventions keep things tidy.

## Development setup

```bash
git clone https://github.com/toalba/wows-replay-parser.git
cd wows-replay-parser
uv venv
source .venv/bin/activate
uv sync --all-extras
```

Tests and the canary workflow need a `.wowsreplay` fixture plus the gamedata
tree. See [tests/fixtures/README.md](https://github.com/toalba/wows-replay-parser/blob/main/tests/fixtures/README.md)
for details. Without fixtures, integration tests skip cleanly — you can
still work on unit-test coverage.

## Running checks locally

```bash
uv run ruff check src/ tests/     # style + lint
uv run mypy src/                  # type-check (advisory)
uv run pytest                     # tests
```

CI mirrors these on every push and pull request.

## Style

- Line length: **120** characters.
- `from __future__ import annotations` at the top of every module.
- Type hints on every public function and dataclass field.
- Docstrings on public API surface (`ParsedReplay`, events, state models).
- Prefer `@cached_property` for expensive derived data over eager computation.

Ruff enforces most of this. If a rule gets in the way of readability, open
a PR that disables it in `pyproject.toml` with a short rationale — don't
work around it with `# noqa`.

## Commits

Short imperative subject line. Body for the *why* when the change isn't
self-evident.

```
Fix RIBBON_NAMES inversion

The lookup was keyed on names instead of wire ids, so every
derive_ribbons() call fell through to "Unknown". ...
```

## Pull requests

- Branch from `main`.
- Keep PRs focused — one logical change per PR.
- Tests passing (CI will verify).
- Reasonable commit history — squash trivial fix-ups before requesting review.
- Update `CHANGELOG.md` if the change is user-facing.

## Parser-specific guidance

- The `.def` files and `alias.xml` in the gamedata repo are the single source
  of truth for entity definitions. If your change depends on a structural
  assumption, verify it against those files first.
- Never work around a parser bug inside the renderer. If decoded data is
  wrong, fix the decode.
- See [CLAUDE.md](https://github.com/toalba/wows-replay-parser/blob/main/CLAUDE.md) for deeper architectural notes.
