# `features.parquet`

- **Producer:** WS1 (`packages/datagen`), written to `$DATA_DIR/features.parquet`
- **Key:** `account_id, month`
- **Contract version:** 0.1.0

Model features (task 1.2). New columns may be **added** with a CHANGELOG entry; renames/removals need a contract change.

| Column | Type | Notes |
|---|---|---|
| `account_id` | string |  |
| `customer_id` | string |  |
| `month` | string `YYYY-MM` |  |
| `limit_paise` | int64 (paise, >= 0) |  |
| `utilisation` | float64 |  |
| `utilisation_delta_3m` | float64 |  |
| `min_due_only_streak` | int16 |  |
| `months_since_full_payment` | int16 |  |
| `payment_ratio_3m` | float64 | payments / min_due |
| `dpd` | int32 |  |
| `max_dpd_6m` | int32 |  |
| `broken_streak_flag` | bool |  |
| `cash_advance_ratio_3m` | float64 |  |
| `essentials_spend_delta_3m` | float64 |  |
| `discretionary_spend_delta_3m` | float64 |  |
| `txn_count_delta_3m` | float64 |  |
| `salary_missing_months_3m` | int16 |  |
| `salary_delta_3m` | float64 |  |
| `income_to_due_ratio` | float64 |  |
| `tenure_months` | int16 |  |
| `dependants` | int16 |  |
| `occupation_type` | string |  |

Conventions (A7.0): money is int64 paise, never float; timestamps UTC; months `YYYY-MM`.
