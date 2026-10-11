# scripts/

**Owner:** WS5. Dev helpers, run from the repo root with `uv run python scripts/<name>.py`.

| Script | Purpose |
|---|---|
| `export_schemas.py [--check]` | Generate `contracts/schemas/` from `npa_contracts` |
| `export_openapi.py [--check]` | Generate `contracts/openapi.yaml` from the API routes |
| `check_contracts.py` | Validate schemas, OpenAPI and every fixture |
| `contract_io.py` | Deterministic (sorted, UTF-8, LF) writers used by the above |
