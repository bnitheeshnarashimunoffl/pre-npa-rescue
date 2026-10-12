# data/

**Owner:** WS1 (Data foundation). Generator code: [`packages/datagen`](../packages/datagen/).

| Path | Committed? | What |
|---|---|---|
| `raw/` | no (gitignored) | downloaded public data (`scripts/download_public.py`) |
| `generated/` | no (gitignored) | Parquet outputs (`$DATA_DIR`) |
| `samples/` | yes, ≤ 5 MB total | small samples for tests (`features_sample.parquet`, `labels_sample.parquet`) |
| `scripts/` | yes | `download_public.py`, `sanity_report.py` |
| `ATTRIBUTION.md` | yes | dataset licences and credits |

**Synthetic data only. Never commit real personal data or raw downloads.**

## Lineage (IS/ISO/IEC 8183:2023)

```
UCI download (raw/uci/, not committed)
  → datagen.calibrate_uci → packages/datagen/src/datagen/calibration.json (committed)
  → datagen generate      → generated/{customers, protected_attributes, account_months,
                            salary_credits, shocks, transactions/}.parquet
                            + internal monthly_spend.parquet, behaviour_types.parquet
  → datagen features      → generated/{features, labels}.parquet (+ samples/ with --samples)
  → datagen experiment    → generated/experiment.parquet          (task 1.3)
```

Same seed ⇒ byte-identical Parquet (tested by hash). Each component uses its own RNG stream
(`default_rng([seed, stream])`). The generator runs offline from the committed
`calibration.json`; CI never downloads anything.

**Internal tables** (not contract tables, never features): `monthly_spend.parquet` holds the
per-category monthly card spend that `transactions.parquet` is expanded from (so features work
with `--no-transactions`); `behaviour_types.parquet` is hidden ground truth (normal / shocked /
forgetful / won't pay) used only to build `labels.segment_truth` and the experiment.

## Calibration (UCI "Default of Credit Card Clients", 30,000 rows, Taiwan 2005)

`calibrate_uci.py` fits, and `calibration.json` stores:

| Fit | Used for |
|---|---|
| Log-normal of `LIMIT_BAL` (σ = 0.94 on log scale) | card-limit spread |
| Bill-to-limit ratio quantiles | opening utilisation in `2024-10` |
| Payment-to-bill ratio quantiles by previous month's status | how much normal customers repay |
| 4×4 month-to-month status transition matrix (duly / 1 / 2 / 3+ months late) | cure / stay / roll once delinquent |
| Default rate overall (22.1%) and by utilisation / payment-ratio band | reference only (documented, not targeted) |

**NT$ → INR by ratio, not exchange rate.** Limits are rescaled so the **median card limit is
₹1,50,000** (UCI median NT$140,000 ⇒ ratio 1.0714), keeping the UCI log-spread. All other UCI
fits are ratios (unitless), so need no conversion.

**UCI quirk.** Status `1` (one month late) almost never appears in `PAY_2..PAY_6` (34
transitions out of it vs 16,297 out of `2`), so the `late1` row is sparse. The generator borrows
the `late2` row for it by role (cure → cure, stay-or-better → stay, worse → roll); the raw fit and
row counts stay in the JSON.

**Scaling to Indian levels.** UCI is a stressed portfolio (22% default). Normal customers'
monthly probability of slipping from current into delinquency is UCI's duly → late rate
(6.1%) × `ENTRY_SCALE` 0.12 ≈ 0.7% a month. Most NPAs come from hardship shocks and won't-pay
customers. The resulting NPA rate is reported once shocks land (next PR).

The demographic UCI columns (sex, education, marriage, age) are never read.

## Still to come

- **Population and statement rules** (task 1.1).
- **Shocks, behaviour types, salary and transactions** (task 1.1).
- **Features, labels and samples** (task 1.2).
- **Demo persona numbers** (task 1.1 step 6, agreed with WS3).
- **Experiment probabilities and contact costs** (task 1.3).
