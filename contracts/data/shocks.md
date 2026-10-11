# `shocks.parquet`

- **Producer:** WS1 (`packages/datagen`), written to `$DATA_DIR/shocks.parquet`
- **Key:** `customer_id`
- **Contract version:** 0.1.0

**Hidden ground truth**, used only to create labels. Never a feature.

| Column | Type | Notes |
|---|---|---|
| `customer_id` | string |  |
| `shock_type` | string | ShockType enum |
| `start_month` | string `YYYY-MM` | nullable when `none` |
| `severity` | float64 | 0-1 |
| `recovers_month` | string `YYYY-MM` | nullable |

Conventions (A7.0): money is int64 paise, never float; timestamps UTC; months `YYYY-MM`.
