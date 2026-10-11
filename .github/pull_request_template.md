## What & why

<!-- Link the issue: Closes #NN -->

## Task / workstream

- Task id(s): <!-- e.g. 2.1 -->
- Workstream: <!-- ws:N -->

## Contract impact

- [ ] none
- [ ] additive (CHANGELOG entry + version bump; label `contract`)
- [ ] breaking (must follow contracts/README.md; team lead approval)

## Regulatory / BIS references implemented

<!-- e.g. RBI 454Y(4), IS/ISO 10002:2018 - or "none" -->

## How to test

```bash
uv run pytest ...
```

## Screenshots (UI changes)

## Checklist

- [ ] Tests added (happy path, one edge case, one failure case)
- [ ] `make lint test` (or the `uv run` equivalents in docs/setup.md) passes locally
- [ ] No secrets, no `.env`, no generated data or model artifacts
- [ ] No files > 5 MB
- [ ] Docs/README updated
- [ ] Fixtures updated if outputs changed
- [ ] Only files inside my workstream's folders changed (A5)
