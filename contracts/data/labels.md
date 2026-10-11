# `labels.parquet`

- **Producer:** WS1 (`packages/datagen`), written to `$DATA_DIR/labels.parquet`
- **Key:** `account_id, month`
- **Contract version:** 0.1.0

Training labels.

| Column | Type | Notes |
|---|---|---|
| `account_id` | string |  |
| `month` | string `YYYY-MM` |  |
| `rolls_forward_60d` | bool |  |
| `reaches_npa_90d` | bool |  |
| `segment_truth` | string | Segment enum |

Conventions (A7.0): money is int64 paise, never float; timestamps UTC; months `YYYY-MM`.
