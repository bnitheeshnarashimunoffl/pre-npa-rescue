# `account_months.parquet`

- **Producer:** WS1 (`packages/datagen`), written to `$DATA_DIR/account_months.parquet`
- **Key:** `account_id, month`
- **Contract version:** 0.1.0

Monthly statements. DPD counted from the statement due date (RBI Credit Card Directions 2025).

| Column | Type | Notes |
|---|---|---|
| `account_id` | string |  |
| `customer_id` | string |  |
| `month` | string `YYYY-MM` | 2024-10 .. 2026-09 |
| `statement_date` | date `YYYY-MM-DD` |  |
| `due_date` | date `YYYY-MM-DD` |  |
| `opening_balance_paise` | int64 (paise, >= 0) |  |
| `purchases_paise` | int64 (paise, >= 0) |  |
| `cash_advance_paise` | int64 (paise, >= 0) |  |
| `payments_paise` | int64 (paise, >= 0) |  |
| `payment_date` | date `YYYY-MM-DD` | nullable |
| `total_due_paise` | int64 (paise, >= 0) |  |
| `min_due_paise` | int64 (paise, >= 0) |  |
| `interest_paise` | int64 (paise, >= 0) | never charged on fees/charges/taxes (no capitalisation) |
| `late_fee_paise` | int64 (paise, >= 0) | only on amount outstanding after due date, only if > 3 days past due |
| `closing_balance_paise` | int64 (paise, >= 0) |  |
| `utilisation` | float64 | closing balance / limit |
| `dpd` | int32 | >= 0 |
| `bucket` | string | Bucket enum; see `npa_contracts.constants.bucket_for_dpd` |

Conventions (A7.0): money is int64 paise, never float; timestamps UTC; months `YYYY-MM`.
