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
| `make demo` | `docker compose up -d --build --wait` (the api migrates and seeds on first start) |
| `make demo-reset` | `docker compose exec -T api python -m seed.demo_reset` (or `uv run python -m seed.demo_reset` without Docker) |

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

## Auth (task 5.3)

```bash
curl -s -X POST localhost:8000/api/v1/auth/login -H 'content-type: application/json' \
  -d '{"username":"collector1","password":"demo"}'          # -> {"access_token": ...}
curl -s localhost:8000/api/v1/collector/queue -H "Authorization: Bearer <token>"
```

- JWT HS256 signed with `JWT_SECRET` (use 32+ random bytes on any shared deployment; the API
  logs a warning for shorter secrets), valid for `JWT_EXPIRE_MINUTES`.
- Each route's allowed roles are its `x-roles` in `contracts/openapi.yaml`; the same list is
  enforced. A role that may not use a route, or a customer asking for another customer, gets
  **404** (not 403) so IDs cannot be enumerated.
- Login failures always return the same `INVALID_CREDENTIALS` error. `/auth/login` is limited
  to `LOGIN_RATE_PER_MINUTE` per client+username and `/chat/*` to `CHAT_RATE_PER_MINUTE` per
  user (in-memory, per process) -> `429` with `Retry-After`.
- Profiles are minimised per role (`app/minimise.py`): collectors see identity, language,
  masked contact details and contact window; hardship officers also see occupation,
  insurance, limit, age and city; auditors see identity only.

## Audit log and retention (task 5.4)

- `audit_log` is append-only: database triggers (migration `0002`) reject UPDATE, DELETE and
  TRUNCATE for every user. Each row is hash-chained to the previous one
  (`row_hash = sha256(prev_hash + row)`), so any edit, deletion or reordering is detectable.
- Check the chain: `GET /api/v1/admin/audit/verify` (admin or auditor) -> `{"ok": true, ...}`,
  or `ok: false` with the first bad row id.
- Audited: every login (success and failure), every contact (`ContactLogger`), offer status
  changes with the approver, policy changes (old and new version), seed runs and retention
  purges. Audit rows never contain passwords or message content.
- `seed --reset` keeps `audit_log` (it is evidence) and records the reset in it.
- **Production hardening:** connect the API as a dedicated role, e.g. `npa_app`, that does not
  own the tables. Migration `0002` revokes its UPDATE/DELETE/TRUNCATE on `audit_log` when that
  role exists; run migrations as the owner role.

Retention (RBI RBC Directions para 454P, 180 days): call/chat records older than that are
purged by a job; audit rows, complaints and offers are kept.

```bash
uv run python -m app.retention --dry-run   # counts only (still audited)
uv run python -m app.retention             # delete contact_events / chat turns older than 180 days
```

It runs daily on the hosted demo as the Render cron job `npa-retention` (02:00 IST, see
`render.yaml`). Elsewhere, schedule `python -m app.retention` once a day (cron, or
`docker compose run --rm api python -m app.retention`). `--days` can lengthen retention but never
shorten it below 180.

## API (task 5.1)

`make api` (or the `uv run uvicorn ...` command above) serves every A7.4 route against
`DATABASE_URL`; run `make seed` first. `GET /api/v1/health` reports `status` (`degraded` if the
database is unreachable) and, per provider, whether it is `real` or a `fixture` fallback.

- Until WS2/WS3/WS4 are merged and wired (phase-2 integration PR), risk/segment/uplift come from
  the seeded `scores` table, NBA and the queue from the `nba` table, relief options from WS3's
  fixtures (demo customers only), the compliance check is the 08:00-19:00 IST window only, and
  chat replays the Priya/Ravi fixture replies.
- Responses served from a sample fixture (scorecard before any red-team run, simulation metrics
  before WS2's report, policy before seeding) carry the header `X-Data-Source: fixture`.
- `POST /redteam/runs` returns `501 REDTEAM_UNAVAILABLE` until WS7's harness is installed; it
  never fabricates results.

## Environment variables

See `.env.example` (A11). Never commit `.env`. CI always runs with `LLM_PROVIDER=mock` and
`DATAGEN_N_CUSTOMERS=2000`, with no network calls from tests.

## Deployment (task 5.5)

> **Not yet run by WS5:** Docker is not installed on the WS5 machine and there is no Render or
> Vercel access from it. The image, `docker compose up`, the demo-reset-in-container path and the
> entrypoint pass-through are exercised by the CI `docker` job on Linux; `render.yaml` and the
> Vercel steps below are untested until someone applies them. The Python parts (entrypoint,
> demo reset, URL handling) are unit-tested locally on SQLite and Postgres.

### Local demo stack (Docker)

```bash
docker compose up -d --build --wait     # postgres + api; api migrates and seeds on first start
open http://localhost:8000/docs         # demo users: priya, ravi, collector1, officer1, admin1, auditor1 / demo
make demo-reset                         # or: docker compose exec -T api python -m seed.demo_reset
docker compose down -v                  # stop and delete the database volume
```

- The api container: non-root user (uid 10001), read-only root filesystem, all Linux
  capabilities dropped, `no-new-privileges`, healthcheck on `/api/v1/health`, ports bound to
  `127.0.0.1` only.
- Startup (`python -m app.entrypoint`): wait for Postgres -> `alembic upgrade head`
  (`RUN_MIGRATIONS`) -> seed an *empty* database (`SEED_ON_START`; WS1 Parquet from
  `./data/generated` if present, else the 10 fixture accounts) -> uvicorn on `$PORT`.
  `WEB_CONCURRENCY` stays 1 (rate limits are per process). Any other command given to the image
  runs as-is (e.g. `docker compose run --rm api python -m app.retention`).

### `make demo-reset` (issue #83)

One command between demo runs; safe to repeat; prints `DEMO RESET OK (...)` or
`DEMO RESET FAILED: ...` (exit 1).

- Clears: chat sessions and turns, callbacks, complaints, offers, contact events and flags,
  red-team runs, policy versions, users.
- Re-seeds: the Priya and Ravi persona rows (profile, statements, scores, queue entry) from the
  same source as the seed, the six demo users (password `demo`) and the seed bank policy.
- Keeps: every non-demo customer as seeded, and the **audit log** (append-only evidence; the
  reset is recorded in it as `demo.reset`).
- Takes seconds even with 5 lakh customers (only persona rows are reloaded). On an empty,
  migrated database it runs the full seed instead.

### Hosted demo: API + Postgres on Render

1. Render dashboard -> **New -> Blueprint** -> select this repository. Render reads
   `render.yaml`: web service `npa-api` (Docker, `services/api/Dockerfile`, health check
   `/api/v1/health`), Postgres 16 `npa-db`, and cron job `npa-retention` (daily 02:00 IST).
   Region: Singapore.
2. In the preview, set the secrets the blueprint leaves blank:
   - `CORS_ORIGINS` = the Vercel URL(s) of the web app, comma-separated
     (e.g. `https://pre-npa-rescue.vercel.app`);
   - `ANTHROPIC_API_KEY` only if `LLM_PROVIDER` is switched to `anthropic`.
   `JWT_SECRET` is generated by Render; `DATABASE_URL` comes from `npa-db` (its `postgres://`
   scheme is converted to `postgresql+psycopg://` by the app).
3. Apply. The first deploy migrates and seeds the empty database. `autoDeploy` is off: deploy a
   chosen commit (e.g. the `demo-freeze` tag) with **Manual Deploy**.
4. Check `https://<npa-api>.onrender.com/api/v1/health` -> `"status": "ok"`.
5. Reset the hosted demo: Render shell on `npa-api` -> `python -m seed.demo_reset`.

Plans: the web service and cron job need a paid instance type (cron jobs are not available on
the free tier); Postgres `basic-256mb`. Never put secrets in Git; GitHub Actions secrets are only
needed if a workflow deploys (none does yet).

### Hosted demo: web on Vercel (WS6 app)

1. Vercel -> **Add New Project** -> import this repository; **Root Directory** `apps/web`;
   framework Next.js; install command `pnpm install --frozen-lockfile`.
2. Environment variables (Production):
   - `NEXT_PUBLIC_API_BASE_URL` = `https://<npa-api>.onrender.com/api/v1`
   - `NEXT_PUBLIC_USE_MOCKS` = `false`
3. Deploy, then add the Vercel URL to `CORS_ORIGINS` on Render and redeploy the API.

### Performance targets

API p95 < 300 ms for non-chat routes on 5 lakh customers; chat turn p95 < 4 s with the real LLM.
Measured so far (laptop, Postgres 16):
- the 5 lakh seed loads in about 4 minutes;
- `GET /collector/queue` at 5 lakh queue rows: p95 19.8 ms over 30 calls (first and deep
  cursor pages, bucket/action filters, `limit=200`). Every page is an index range scan
  (`ix_nba_queue*`, migration 0003). Re-run with
  `QUEUE_SCALE_ROWS=500000 TEST_DATABASE_URL=... uv run pytest services/api/tests/test_queue_scale.py -s`
  (CI runs it at 200k rows against the 300 ms budget);
- the other routes are measured once the real providers are wired (phase-2 integration).

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
| WS4 Chatbot | `@sharmeshms` | `/packages/chatbot/` |
| WS5 Backend & platform | `@GautamV-srg` | `/services/api/`, `/packages/contracts/`, `/contracts/`, `/.github/`, `/docs/setup.md` |
| WS6 Frontend | `@masked-garlic26` | `/apps/web/` |
| WS7 Red team & compliance | `@GautamV-srg` | `/redteam/`, `/governance/` |
| WS8 Pitch | `@bnitheeshnarashimunoffl` | `/docs/`, `/README.md` |

Every handle must be a collaborator with write access, or GitHub shows an "unknown owner"
warning for that line. Code Owner review is not required for merging (see the Owner checklist);
CODEOWNERS only requests reviews automatically.
