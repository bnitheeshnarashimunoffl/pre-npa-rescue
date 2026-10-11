# Setup — how to run everything

**Owner:** WS5. Works on Windows (PowerShell), macOS and Linux. CI runs on `ubuntu-latest`.

## Prerequisites

| Tool | Version | Notes |
|---|---|---|
| [uv](https://docs.astral.sh/uv/) | ≥ 0.5 | manages Python too: `uv python install 3.11` (no system Python needed) |
| Python | 3.11 | pinned in `.python-version`; uv picks it up |
| git | any recent | `.gitattributes` forces LF line endings on every OS |
| gh (GitHub CLI) | any recent | for PRs and issues |
| Node.js + pnpm | 20 LTS + pnpm 9 | only for `apps/web` (WS6) |
| Docker + Compose v2 | 24+ | only for `docker compose up` / the full demo |
| make | optional | every target has a plain `uv run` equivalent below |

## First run

```bash
git clone https://github.com/bnitheeshnarashimunoffl/pre-npa-rescue.git
cd pre-npa-rescue
uv sync                       # creates .venv with every workspace package + dev tools
cp .env.example .env          # PowerShell: Copy-Item .env.example .env
```

## Commands (make target → plain command)

Run from the repo root. These work in PowerShell, bash and zsh.

| make | Plain command |
|---|---|
| `make setup` | `uv sync` (+ `pnpm -C apps/web install` once WS6 adds the app) |
| `make lint` | `uv run ruff check .` and `uv run ruff format --check .` |
| `make format` | `uv run ruff check --fix .` and `uv run ruff format .` |
| `make typecheck` | `uv run python -m mypy` |
| `make test` | `uv run pytest` and `uv run pytest packages/contracts/tests --cov=npa_contracts --cov-fail-under=100 -q` |
| `make contracts` | `uv run python scripts/export_schemas.py` and `uv run python scripts/export_openapi.py` |
| `make check-contracts` | `uv run python scripts/export_schemas.py --check`, `uv run python scripts/export_openapi.py --check`, `uv run python scripts/check_contracts.py` |
| `make api` | `uv run uvicorn app.main:app --reload --port 8000 --app-dir services/api` → http://localhost:8000/docs |
| `make data` | `uv run datagen all` (once WS1 ships task 1.1) |
| `make train` | `uv run npa-models train --all` then `uv run npa-models score` (once WS2 ships) |
| `make seed` | `uv run --directory services/api python -m seed` (task 5.2) |
| `make web` | `pnpm -C apps/web dev` (once WS6 ships) |
| `make redteam` | `uv run npa-redteam run` (once WS7 ships) |
| `make demo` | `docker compose up -d --build` then seed (task 5.5) |

Running one package's tests: `uv run pytest packages/rules/tests`.
Adding a dependency to your package: `uv add --package npa-rules pyyaml`.

**Windows note:** use `uv run python -m mypy` rather than `uv run mypy`. On some Windows machines
Smart App Control / Application Control blocks the generated `mypy.exe` shim
("An Application Control policy has blocked this file"); the module form is not affected. CI
and the Makefile use the module form everywhere.

## Before you push

```bash
uv run ruff check . ; uv run ruff format --check . ; uv run python -m mypy ; uv run pytest
uv run python scripts/check_contracts.py      # if you touched contracts/ or fixtures
```

If you changed `packages/contracts` or any API route, regenerate and commit the contracts
(`make contracts`). Generated files are deterministic: the same on every OS.

## API (bootstrap state)

`make api` starts the stub API. Every A7.4 route exists; most serve `contracts/fixtures/`, the
rest return `501 NOT_IMPLEMENTED` in the standard error envelope until tasks 5.1–5.4 land. The
`/health` endpoint reports package versions and which providers are real vs fixture.

## Environment variables

See `.env.example` (A11). Never commit `.env`. CI always runs with `LLM_PROVIDER=mock` and
`DATAGEN_N_CUSTOMERS=2000`, with no network calls from tests.

## Hosting (task 5.5, planned)

API + Postgres on **Render** (web service from `services/api/Dockerfile` + managed Postgres 16);
web on **Vercel**. Secrets live in the platform env and GitHub Actions secrets only. Exact steps
are added in task 5.5.

---

## Owner checklist (for @bnitheeshnarashimunoffl — repo admin only)

WS5 has write access but not admin, so these settings must be applied by the owner.

### 1. Collaborators

Settings → Collaborators → add every workstream owner with **Write** access.

### 2. Merge settings

Settings → General → Pull Requests:

- [x] Allow squash merging — **only** this one checked
- [ ] Allow merge commits — unchecked
- [ ] Allow rebase merging — unchecked
- [x] Automatically delete head branches

Or with the CLI:

```bash
gh repo edit bnitheeshnarashimunoffl/pre-npa-rescue \
  --enable-squash-merge --enable-merge-commit=false --enable-rebase-merge=false \
  --delete-branch-on-merge
```

### 3. Branch protection for `main`

Settings → Branches → Add branch protection rule → Branch name pattern `main`:

- [x] Require a pull request before merging
  - [x] Require approvals: **1**
  - [x] Dismiss stale pull request approvals when new commits are pushed
  - [x] Require review from Code Owners
- [x] Require status checks to pass before merging
  - Required check: **`ci-passed`** (it appears in the search box after CI has run once)
  - [ ] Require branches to be up to date before merging — leave **off** (eight agents
    rebasing on every merge would stall the queue; CI still runs on `main` after each merge)
- [x] Require conversation resolution before merging
- [x] Require linear history
- [ ] Do not allow bypassing the above settings — leave **off** so the team lead can fix a red
  `main` in an emergency
- Allow force pushes: **off** · Allow deletions: **off**

Or with the CLI (same settings):

```bash
gh api -X PUT repos/bnitheeshnarashimunoffl/pre-npa-rescue/branches/main/protection \
  -H "Accept: application/vnd.github+json" --input - <<'EOF'
{
  "required_status_checks": { "strict": false, "contexts": ["ci-passed"] },
  "enforce_admins": false,
  "required_pull_request_reviews": {
    "required_approving_review_count": 1,
    "dismiss_stale_reviews": true,
    "require_code_owner_reviews": true
  },
  "restrictions": null,
  "required_linear_history": true,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "required_conversation_resolution": true
}
EOF
```

### 4. Actions

Settings → Actions → General: allow GitHub Actions and the third-party actions used in
`ci.yml` (`astral-sh/setup-uv`, `dorny/paths-filter`, `pnpm/action-setup`,
`gitleaks/gitleaks-action`). Workflow permissions: **Read repository contents** is enough.

### 5. Release tags (later)

`v0.1-mvp`, `v0.2-integrated`, `demo-freeze` are created by the team lead (A8.1).

## CODEOWNERS placeholders (to fill in)

`.github/CODEOWNERS` already has the real handles for the team lead
(`@bnitheeshnarashimunoffl`) and WS5 (`@GautamV-srg`). Replace these placeholders with real
GitHub usernames, then open a PR (WS5 + team lead review):

| Placeholder | Workstream | Folders |
|---|---|---|
| `@ws1-owner` | WS1 Data foundation | `/packages/datagen/`, `/data/` |
| `@ws2-owner` | WS2 Models | `/packages/models/` |
| `@ws3-owner` | WS3 Rules | `/packages/rules/` |
| `@ws4-owner` | WS4 Chatbot | `/packages/chatbot/` |
| `@ws6-owner` | WS6 Frontend | `/apps/web/` |
| `@ws7-owner` | WS7 Red team & compliance | `/redteam/`, `/governance/` |
| `@ws8-owner` | WS8 Pitch | `/docs/`, `/README.md` |

Until they are replaced, GitHub shows "unknown owner" warnings for those lines, and those
folders have no code owner (any approving review from a writer counts). Each handle must belong
to a collaborator with write access.
