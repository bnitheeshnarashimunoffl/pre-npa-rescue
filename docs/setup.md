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
| `make dev-db` | `uv run --with pgserver python scripts/dev_postgres.py` (local Postgres 16, no Docker) |
| `make migrate` | `uv run python -m alembic -c services/api/alembic.ini upgrade head` |
| `make seed` | migrate, then `uv run python -m seed` (add `--reset` to replace existing rows) |
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

## Database (task 5.2)

Postgres 16. Without Docker, run a local one in its own terminal:

```bash
uv run --with pgserver python scripts/dev_postgres.py   # prints DATABASE_URL; Ctrl+C stops it
```

Then, with `DATABASE_URL` set (PowerShell: `$env:DATABASE_URL = '...'`):

```bash
uv run python -m alembic -c services/api/alembic.ini upgrade head   # create/upgrade the schema
uv run python -m seed            # WS1 Parquet if $DATA_DIR has it, else the 10 fixture accounts
uv run python -m seed --reset    # wipe all rows and seed again
```

- Seeding uses `COPY` on Postgres. A synthetic 5 lakh customers × 24 months (12M statement
  rows) seeded in ~4 minutes on a laptop.
- WS2 scores are read from `$DATA_DIR/scores.parquet`, then `$MODEL_DIR/scores.parquet`.
- Demo users (password `demo`): `priya`, `ravi` (customers), `collector1`, `officer1`
  (hardship officer), `admin1`, `auditor1`.
- New migration after changing `services/api/app/orm.py`:
  `uv run python -m alembic -c services/api/alembic.ini revision --autogenerate -m "<what>"`,
  review it, and commit it. CI runs `alembic check` and fails if the ORM and migrations drift.
- DB tests run on SQLite, and also on Postgres when `TEST_DATABASE_URL` is set (CI sets it).

**Windows note:** Smart App Control / Application Control can block pyarrow's DLLs
("DLL load failed ... Application Control policy"), intermittently. The fixtures seed path
does not need pyarrow; Parquet seeding and its tests need it (CI on Linux always runs them).

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

**Why no required approvals:** several workstreams push from the same GitHub account, and
GitHub does not let an account approve its own PRs, so a required approval (or a required
Code Owner review) would block those PRs forever. Instead, the **WS9 supervisor** (run by the
owner) reviews and squash-merges PRs once CI passes. `CODEOWNERS` is still used to request
reviews automatically; it just doesn't block merging.

Settings → Branches → Add branch protection rule → Branch name pattern `main`:

- [x] Require a pull request before merging
  - Require approvals: **0**
  - [ ] Require review from Code Owners — **off**
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
    "required_approving_review_count": 0,
    "dismiss_stale_reviews": false,
    "require_code_owner_reviews": false
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

## CODEOWNERS

| Workstream | Owner | Folders |
|---|---|---|
| Team lead (default `*`) | `@bnitheeshnarashimunoffl` | everything not listed below |
| WS1 Data foundation | `@GautamV-srg` | `/packages/datagen/`, `/data/` |
| WS2 Models | `@GautamV-srg` | `/packages/models/` |
| WS3 Rules | `@GautamV-srg` | `/packages/rules/` |
| WS4 Chatbot | `@ws4-teammate` (**placeholder**) | `/packages/chatbot/` |
| WS5 Backend & platform | `@GautamV-srg` | `/services/api/`, `/packages/contracts/`, `/contracts/`, `/.github/`, `/docs/setup.md` |
| WS6 Frontend | `@ws6-teammate` (**placeholder**) | `/apps/web/` |
| WS7 Red team & compliance | `@GautamV-srg` | `/redteam/`, `/governance/` |
| WS8 Pitch | `@bnitheeshnarashimunoffl` | `/docs/`, `/README.md` |

Replace the two placeholders with the teammates' real GitHub usernames (each must be a
collaborator with write access). Until then GitHub shows "unknown owner" warnings for those
lines. Code Owner review is not required for merging (see the Owner checklist), so the
placeholders block nothing.
