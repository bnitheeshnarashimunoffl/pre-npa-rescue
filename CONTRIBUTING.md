# Contributing (condensed A8)

Setup and commands: [docs/setup.md](docs/setup.md). Contract changes: [contracts/README.md](contracts/README.md).

## Ownership (A5)

Edit only the folders your workstream owns (see `.github/CODEOWNERS`). Read anything. Found a
bug in someone else's folder? Open a `bug` issue with their `ws:N` label, propose the patch in
the issue, and work around it locally in your own folder.

Never commit generated data, model artifacts, secrets, `.env`, `node_modules` or files > 5 MB.

## Branches

- `main` is protected: PR required, CI (`ci-passed`) must pass, squash merge only, linear
  history. No approval is required (several workstreams share one GitHub account, which can't
  approve its own PRs); the WS9 supervisor merges PRs once CI passes.
- Branch name: `ws<N>/<type>/<task-id>-<short-desc>`, e.g. `ws2/feat/2.1-early-warning-model`.
  Types: `feat fix chore docs test refactor perf data`. Contract changes: `contracts/<short-desc>`.

## Daily loop

```bash
git checkout main && git pull --ff-only origin main
git checkout -b ws2/feat/2.1-early-warning-model
# ... small commits ...
git fetch origin && git rebase origin/main      # every few hours and before opening a PR
uv sync
make lint typecheck test                        # or the uv commands in docs/setup.md
git push -u origin ws2/feat/2.1-early-warning-model   # after a rebase: --force-with-lease
gh pr create --fill --base main --label "ws:2" --label "task:2.1"
```

- Never `git push --force` to `main` or anyone else's branch.
- Never merge your own PR. Delete the branch after merge.
- Small PRs: aim for < 400 changed lines (excluding lockfiles and fixtures). Open drafts early.

## Commits (Conventional Commits)

`<type>(ws<N>): <imperative summary> [task <id>]`
e.g. `feat(ws3): add RBI late-fee calculation on post-due outstanding [task 3.2]`

## Pull requests

Fill in the template: what & why (`Closes #NN`), task id, contract impact, RBI/BIS references,
how to test, screenshots for UI, checklist.

## Issues

Every task is an issue labelled `ws:<N>`, `task:<id>`, and `mvp` or `stretch`. Other labels:
`contract`, `blocked`, `bug`, `question`, `integration`. Comment on your issue at the end of each
session: done, next, blocked.

## Dependencies and lockfiles

- Python: `uv add --package <your-package> <dep>` (updates `uv.lock`, which is allowed).
- `uv.lock` conflict during a rebase: **never hand-merge**. `git checkout --theirs uv.lock`,
  `uv lock`, commit.
- Web: only WS6 touches `apps/web/pnpm-lock.yaml`; regenerate with `pnpm install`.
- Don't upgrade shared tools (Python, ruff, mypy, pytest, Node, Next) without an ADR.

## Code conventions (A9, short)

ruff (line length 100) · type hints on public functions · Pydantic at package boundaries ·
`logging`, never `print` · money in `int` paise · timezone-aware datetimes · seeded randomness ·
tests for happy path, edge case and failure case · cite RBI/BIS references in comments.
