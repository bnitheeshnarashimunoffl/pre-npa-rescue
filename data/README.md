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
customers. Result at `2026-09` (10,000 customers, seed 42): **NPA 3.56%** (3.6–3.9% at 20,000
customers across seeds 42, 7, 123), SMA-0 4.1%, SMA-1 1.1%,
SMA-2 0.7% (target 3–6%).

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

## Behaviour and shocks (hidden ground truth)

| Type | Share | Behaviour |
|---|---|---|
| normal | 82% | UCI repayment ratios (persistent per customer), UCI cure/stay/roll |
| shocked | 12% | job loss 45%, medical 25%, business loss 20%, bereavement 10% (retirees/students: job loss → medical). Severity ~ Beta(2,2). Shock month 3rd–24th month of the window |
| forgetful | 4% | pays in full; 20% of months 1–14 days late, 4% skips a cycle then catches up |
| won't pay | 2% | income intact; discretionary ×1.4–2.0 and travel ×1.5 from 2 months before the start; minimum only for 2 months, then 85% nothing / 15% token |

**Shock timeline (the leading indicators).** From the shock month: salary credits stop (job loss)
or drop (severe medical: unpaid leave ×(1−severity) for 3 months; severe bereavement: one month
at 50%); discretionary spend × (1 − 0.7·sev), travel × (1 − 0.9·sev), essentials held (medical:
× (1 + 0.8·sev) for 3 months); cash advances of 10–40% of normal spend; payments drop to the
minimum. **Missed payments start 1–3 months later** (lead = 3 − ⌊3·sev⌋). Then: severity ≥ ⅔ →
90% nothing; ⅓–⅔ → minimum 25% / oldest due only 20% / partial 25% / nothing 30%; < ⅓ →
minimum 80%. 35% recover after 3–9 months and then catch up (50% a month pay all overdue).
Random payroll delays (0.3% of salary months) keep a missing credit from being proof of hardship.

`data/scripts/sanity_report.py` on the seed-42, 10,000-customer run (shocked accounts, ratio to
their own level 4–6 months before the first missed payment; `t+0` = first miss):

| month | discretionary | essentials | cash advance | payments |
|---|---|---|---|---|
| t−3 | 0.87 | 0.96 | 2.92 | 0.80 |
| t−2 | 0.76 | 0.97 | 4.91 | 0.69 |
| t−1 | 0.60 | 0.97 | 7.19 | 0.59 |
| t+0 | 0.47 | 0.74 | 4.78 | 0.06 |

## Features (task 1.2)

All features at month `t` use only rows at or before `t` (tested by truncation). The payment in
month `t` settles the statement of month `t−1`.

| Feature | Definition |
|---|---|
| `utilisation` | closing balance / limit |
| `utilisation_delta_3m` | utilisation now − 3 months ago (0.0 for the first 3 months) |
| `min_due_only_streak` | consecutive cycles paying ≥ MAD but ≤ 110% of MAD and < total due |
| `months_since_full_payment` | cycles since the statement was paid in full (nothing due counts as full); `t+1` if never in the window |
| `payment_ratio_3m` | payments / MAD over the last 3 cycles (1.0 if nothing due, cap 10) |
| `dpd`, `max_dpd_6m` | DPD at the statement date; max over the last 6 statements |
| `broken_streak_flag` | missed or late this cycle after ≥ 3 on-time cycles |
| `cash_advance_ratio_3m` | cash advance / (purchases + cash advance), last 3 months |
| `essentials_spend_delta_3m`, `discretionary_spend_delta_3m`, `txn_count_delta_3m` | (last-3-month total − previous 3) / max(previous 3, floor) — floor ₹100 a month or 1 txn a month; capped at 10; 0.0 for the first 5 months |
| `salary_missing_months_3m` | salaried: months in the last 3 with an expected salary and no credit; others 0 |
| `salary_delta_3m` | salaried: same relative change on credited salary; others 0.0 |
| `income_to_due_ratio` | onboarding monthly income / total due (100 if nothing due, cap 100) |
| `tenure_months` | months since the card was opened |
| `dependants`, `occupation_type`, `limit_paise` | from `customers` |

`*_3m` sums use the shorter history in the first months. Never included: protected attributes,
shocks, behaviour types (tested).

## Labels (task 1.2)

- `rolls_forward_60d`: bucket at `t+1` or `t+2` worse than at `t`.
- `reaches_npa_90d`: NPA at `t+1`, `t+2` or `t+3` (already-NPA accounts that stay NPA are `True`).
- `segment_truth` for accounts at risk at `t` (past due, rolling forward, paid late, active
  shock, or won't-pay within 2 months of its start): active shock → `cant_pay`; won't pay →
  `wont_pay`; forgetful → `forgot`; others → `forgot` if current again within 2 months else
  `cant_pay`. Not at risk → `not_at_risk`.
- Rows only for months with the full 3-month horizon: `2024-10` .. `2026-06`.

## Samples

`samples/features_sample.parquet` and `samples/labels_sample.parquet`: seed 42, 10,000
customers, **200 accounts × the last 10 labelled months (`2025-09` .. `2026-06`) = 2,000 rows**
with identical keys. Half the accounts were past due at some point in those months (so both label
classes appear), half random. Regenerate:

```bash
uv run datagen generate --n 10000 --seed 42 --no-transactions
uv run datagen features --samples data/samples
```

## Still to come

- **Demo persona numbers** (task 1.1 step 6, agreed with WS3).
- **Experiment probabilities and contact costs** (task 1.3).
