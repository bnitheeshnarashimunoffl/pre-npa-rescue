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

## Population assumptions (task 1.1)

| Item | Assumption |
|---|---|
| Occupation | salaried 55%, self-employed 20%, gig 15%, retired 5%, student 5% |
| Age | 21–65; per occupation (students 21–25, retired 58–65), Beta(2,3) within the range |
| Monthly income | log-normal (σ 0.45) around occupation medians (₹60k salaried, ₹65k self-employed, ₹28k gig, ₹38k retired, ₹15k student) × city tier (1: 1.3, 2: 1.0, 3: 0.8) |
| Card limit | UCI log-normal, median ₹1,50,000, Gaussian copula with income (ρ = 0.8), kept within 1×–8× monthly income, rounded to ₹5,000, min ₹10,000 |
| Dependants | 0–4 with p = 25/25/25/17/8% (students 0) |
| Language | Tamil Nadu → `ta` 70%; Hindi-belt states → `hi` 65%; otherwise `en` |
| Insurance | 35% of cards: job loss 40%, death/disability 35%, both 25% |
| Contact window | 20% state a preferred window, always inside 08:00–19:00 (RBI 454Y(4), 454Y(6)) |
| Card age | opened 6–120 months before `2024-10` |
| Names | Faker `en_IN` name pools, sampled with the seeded RNG; phone `+91-98XXXXX123`, email `p****@example.com` |

**Protected attributes** (gender, religion, caste category, state, region) are drawn
independently of each other and of the hardship process, and live only in
`protected_attributes.parquet` (IS/ISO/IEC TR 24027:2021). Proportions are rough population
shares (assumption). City and language follow state, as in real data; no feature uses them.

## Statement rules (RBI) and bank-policy assumptions

RBI rules implemented in `dues.py` / `statements.py` (Credit Card Directions 2025; asset
classification circular 16 July 2015):

- DPD counted from the due date of the **oldest unpaid minimum amount due** (payments clear the
  oldest dues first). Buckets via `npa_contracts.constants.bucket_for_dpd`; NPA at DPD > 90.
- Late fee only when past due for **more than 3 days**, on the **amount outstanding after the
  due date** (total due − paid by the due date), never on the total amount due.
- Interest on **principal only**: unpaid interest, fees and GST never earn interest.
- MAD = all interest, fees and GST + max(5% of principal, ₹200), plus any overdue MAD, capped at
  the total due ⇒ no negative amortisation.

Bank-policy assumptions (mirroring `packages/rules/policies/bank_policy.yaml`, not RBI numbers):
statement day 1/5/10/15/20/25; due 15 days after the statement; 42% p.a. interest (actual/365);
late-fee slabs nil ≤ ₹500, ₹500 ≤ ₹5,000, ₹750 ≤ ₹10,000, ₹1,000 ≤ ₹25,000, ₹1,300 above;
18% GST on interest and fees; interest-free when the last statement was paid in full by its due
date; cash advances earn interest from withdrawal (half a cycle); new spend blocked from DPD 31;
no interest or fees once NPA (income-recognition norms).

Ledger identity on every row: `closing = opening + purchases + cash_advance − payments +
interest + late_fee + GST`, with `GST = round_half_up(18% × (interest + late_fee))`; GST is not a
separate column, it is derivable.

**DPD at the statement date.** With a 15-day due period, one missed payment shows DPD ≈ 15
(SMA-0) at the next statement, two ≈ 45 (SMA-1), three ≈ 76 (SMA-2), four ≈ 106 (NPA).

## Still to come

- **Shocks, behaviour types, salary and transactions** (task 1.1).
- **Features, labels and samples** (task 1.2).
- **Demo persona numbers** (task 1.1 step 6, agreed with WS3).
- **Experiment probabilities and contact costs** (task 1.3).
