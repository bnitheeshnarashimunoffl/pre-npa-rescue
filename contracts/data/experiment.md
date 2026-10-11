# `experiment.parquet`

- **Producer:** WS1 (`packages/datagen`), written to `$DATA_DIR/experiment.parquet`
- **Key:** `customer_id`
- **Contract version:** 0.1.0

Simulated treatment experiment (task 1.3) for uplift modelling.

| Column | Type | Notes |
|---|---|---|
| `customer_id` | string |  |
| `account_id` | string |  |
| `month` | string `YYYY-MM` |  |
| `treatment` | string | Treatment enum |
| `outcome_cured_90d` | bool |  |
| `outcome_npa_90d` | bool |  |
| `contact_cost_paise` | int64 (paise, >= 0) |  |
| `true_uplift_group` | string | UpliftGroup enum; **hidden, evaluation only** |

Conventions (A7.0): money is int64 paise, never float; timestamps UTC; months `YYYY-MM`.
