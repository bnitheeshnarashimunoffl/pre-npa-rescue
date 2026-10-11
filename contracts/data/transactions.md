# `transactions.parquet`

- **Producer:** WS1 (`packages/datagen`), written to `$DATA_DIR/transactions.parquet`
- **Key:** `txn_id`
- **Contract version:** 0.1.0

Card transactions.

| Column | Type | Notes |
|---|---|---|
| `txn_id` | string | `TXN-00000001` |
| `account_id` | string |  |
| `ts` | timestamp[us, UTC] |  |
| `amount_paise` | int64 (paise, >= 0) |  |
| `category` | string | `essentials` / `discretionary` / `travel` / `utilities` / `cash_advance` / `emi` / `other` |
| `merchant_city` | string |  |
| `channel` | string | `pos` / `online` / `atm` |

Conventions (A7.0): money is int64 paise, never float; timestamps UTC; months `YYYY-MM`.
