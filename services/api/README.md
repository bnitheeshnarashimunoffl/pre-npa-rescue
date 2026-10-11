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

**Tasks:** 5.1 API layer · 5.2 database & data model · 5.3 auth & roles · 5.4 audit logging · 5.5 deployment
