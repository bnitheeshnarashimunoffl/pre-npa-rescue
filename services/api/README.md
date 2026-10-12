# npa-api (FastAPI)

**Owner:** WS5

Wires the `npa_*` packages together behind `/api/v1` (A7.4) with dependency injection,
Postgres, JWT auth and audit logging.

**Bootstrap state:** every A7.4 route exists. Routes either serve `contracts/fixtures/` or
return `501 NOT_IMPLEMENTED` in the standard error envelope until their task lands.
`contracts/openapi.yaml` is generated from these routes.

```bash
uv run uvicorn app.main:app --reload --port 8000 --app-dir services/api
# docs: http://localhost:8000/docs
```

**Database (5.2):** SQLAlchemy 2.0 ORM in `app/orm.py` (18 tables; money `BIGINT` paise,
`TIMESTAMPTZ`, enum `CHECK`s), Alembic migrations in `alembic/`, seed loader in `seed/`,
collector-queue keyset pagination in `app/queries.py`. `protected_attributes` is never read by
a router (enforced by a test). Commands: see `docs/setup.md` → Database.

**Auth (5.3):** JWT HS256 + bcrypt in `app/security.py`; every route's `x-roles` are both
documented and enforced via `routers/_common.access(...)`; 404 instead of 403; rate limits in
`app/ratelimit.py`; per-role profile minimisation in `app/minimise.py`.

**Tasks:** 5.1 API layer · 5.2 database & data model · 5.3 auth & roles · 5.4 audit logging · 5.5 deployment
