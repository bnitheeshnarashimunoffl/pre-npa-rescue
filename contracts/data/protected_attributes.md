# `protected_attributes.parquet`

- **Producer:** WS1 (`packages/datagen`), written to `$DATA_DIR/protected_attributes.parquet`
- **Key:** `customer_id`
- **Contract version:** 0.1.0

**Evaluation and bias tests only. Never a model feature (A3).** No API route exposes this table.

| Column | Type | Notes |
|---|---|---|
| `customer_id` | string | FK customers |
| `gender` | string |  |
| `religion` | string |  |
| `caste_category` | string |  |
| `state` | string |  |
| `region` | string | north / south / east / west / northeast / central |

Conventions (A7.0): money is int64 paise, never float; timestamps UTC; months `YYYY-MM`.
