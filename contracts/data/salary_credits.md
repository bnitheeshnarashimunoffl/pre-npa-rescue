# `salary_credits.parquet`

- **Producer:** WS1 (`packages/datagen`), written to `$DATA_DIR/salary_credits.parquet`
- **Key:** `customer_id, month`
- **Contract version:** 0.1.0

Expected vs actual salary credits.

| Column | Type | Notes |
|---|---|---|
| `customer_id` | string |  |
| `month` | string `YYYY-MM` |  |
| `expected_paise` | int64 (paise, >= 0) |  |
| `credited_paise` | int64 (paise, >= 0) | 0 if missing |

Conventions (A7.0): money is int64 paise, never float; timestamps UTC; months `YYYY-MM`.
