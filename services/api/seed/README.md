# seed/

**Owner:** WS5 (task 5.2). Loads the database for development and the demo.

```bash
uv run python -m seed [--reset] [--source auto|parquet|fixtures] [--data-dir DIR] [--scores FILE]
```

| Source | When | Loads |
|---|---|---|
| `parquet` | `$DATA_DIR/customers.parquet` exists (WS1) | `customers`, `accounts`, `protected_attributes`, `account_months`; WS2 `scores.parquet` if found |
| `fixtures` | no Parquet yet | the 10 accounts in `contracts/fixtures/queue.json` (incl. Priya and Ravi) → `customers`, `accounts`, `scores`, `nba` |

Always: the six A7.4 demo users (bcrypt) and the initial active `policy_versions` row (WS3's
`bank_policy.yaml` if present, else `contracts/fixtures/policy.json`).

- One transaction: a failure leaves nothing half-loaded.
- Refuses a database that already has customers unless `--reset`.
- Postgres uses `COPY` from Arrow batches (bounded memory); other dialects use executemany.
- Column specs: `contracts/data/*.md`. Extra Parquet columns are ignored; missing required
  columns fail with a clear message.
