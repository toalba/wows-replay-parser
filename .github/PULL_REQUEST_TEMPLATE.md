<!--
Short imperative subject. Body should answer *why* the change is being
made — the diff already shows *what*.
-->

## Summary



## Type

<!-- Check one -->
- [ ] Bug fix
- [ ] Feature
- [ ] Refactor / cleanup
- [ ] Docs
- [ ] CI / tooling

## Test plan

<!-- How did you verify this works? Delete rows that don't apply. -->
- [ ] `uv run pytest` green
- [ ] `uv run ruff check src/ tests/` clean
- [ ] Added / updated unit tests covering the change
- [ ] Exercised against a real replay fixture locally

## Checklist

- [ ] CHANGELOG updated if this is a user-visible change
- [ ] Docstrings updated for public API touched by this change
- [ ] If fixing a parser bug, verified it against the `.def` / `alias.xml`
      source of truth

## Related issues

<!-- Fixes #123 / Closes #456 -->
