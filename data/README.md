# data/

**Owner:** WS1 (Data foundation). Generator code: [`packages/datagen`](../packages/datagen/).

| Path | Committed? | What |
|---|---|---|
| `raw/` | no (gitignored) | downloaded public data (`scripts/download_public.py`) |
| `generated/` | no (gitignored) | Parquet outputs (`$DATA_DIR`) |
| `samples/` | yes, ≤ 5 MB total | small samples for tests (`features_sample.parquet`, `labels_sample.parquet`, `protected_attributes_sample.parquet`, `demo_personas.json`) |
| `scripts/` | yes | `download_public.py`, `sanity_report.py` |
| `ATTRIBUTION.md` | yes | dataset licences and credits |

**Synthetic data only. Never commit real personal data or raw downloads.**

## Lineage (IS/ISO/IEC 8183:2023)

```
UCI download (raw/uci/, not committed)
  → datagen.calibrate_uci → packages/datagen/src/datagen/calibration.json (committed)
  → datagen generate      → generated/{customers, protected_attributes, account_months,
                            salary_credits, shocks, transactions/}.parquet, demo_personas.json
                            + internal monthly_spend.parquet, behaviour_types.parquet
  → datagen features      → generated/{features, labels}.parquet (+ samples/ with --samples)
                            (labels also read the internal label_horizon.parquet)
  → datagen experiment    → generated/experiment.parquet (+ internal experiment_potential.parquet)
```

Same seed ⇒ byte-identical Parquet (tested by hash). Each component uses its own RNG stream
(`default_rng([seed, stream])`). The generator runs offline from the committed
`calibration.json`; CI never downloads anything.

**Internal tables** (not contract tables, never features): `monthly_spend.parquet` holds the
per-category monthly card spend that `transactions.parquet` is expanded from (so features work
with `--no-transactions`); `behaviour_types.parquet` is hidden ground truth (normal / shocked /
forgetful / won't pay) used only to build `labels.segment_truth` and the experiment;
`label_horizon.parquet` holds DPD and bucket for the months simulated after the window (see
"Label horizon"), read only by the labels step.

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

## Demo personas (task 1.1 step 6)

Ten fixed customers (`CUST-DEMO-*` / `ACC-DEMO-*`) are appended to every generated population.
Their payments, spend, salary and shocks are hand-scripted in `personas.py` and run through the
same statement engine, so they obey the same RBI rules. They use a fixed RNG, so their histories
are identical for every `SEED` (tested); only their `txn_id` numbers depend on the population.
Numbers agreed with WS3 on issue #1:

| Customer | Who | Story | Bucket (DPD) at 2026-09 | Total due ₹ | Late fee ₹ | Overdue ₹ | Segment / uplift group |
|---|---|---|---|---|---|---|---|
| `CUST-DEMO-PRIYA` | Priya Subramanian, 29, Chennai, `ta` | Salary stopped 2026-06; minimum only in 07 and 08; part of the minimum in 09 | sma0 (16) | 1,07,452 | 1,300 | **11,492** | cant_pay / persuadable |
| `CUST-DEMO-RAVI` | Ravi Kumar, 41, Madurai, `ta` (chats in `en`) | Sole earner, job lost 2026-07, no payments since 2026-08, job-loss insurance | sma1 (47) | 65,541 | 1,300 | 14,422 | cant_pay / lost_cause |
| `CUST-DEMO-ANITA` | Anita Reddy, 34, Hyderabad | Pays in full; once 6 days late; forgot 2026-09 | sma0 (16) | 67,443 | 1,300 | 6,061 | forgot / sure_thing |
| `CUST-DEMO-VIKRAM` | Vikram Malhotra, 45, New Delhi | Income intact, spend up, stopped paying 2026-07 | sma2 (77) | 4,52,348 | 1,300 | 1,39,154 | wont_pay / lost_cause |
| `CUST-DEMO-MEERA` | Meera Nair, 38, Kochi | Anxious; skips and self-cures; no calls at work | sma0 (16) | 1,63,611 | 1,300 | 27,077 | forgot / sleeping_dog |
| `CUST-DEMO-ARJUN` | Arjun Rao, 31, Bengaluru | Wedding spend, minimum only for 2 months, never late | current (0) | 2,58,005 | 0 | 0 | not_at_risk / sure_thing |
| `CUST-DEMO-FATIMA` | Fatima Sheikh, 47, Lucknow | Medical shock 2026-05, half pay, paying what she can | sma1 (47) | 1,32,236 | 1,300 | 33,840 | cant_pay / persuadable |
| `CUST-DEMO-SURESH` | Suresh Patel, 52, Ahmedabad | Business loss 2025-12, no payments since 2026-02 | npa (228) | 2,37,095 | 0 | 1,27,095 | cant_pay / lost_cause |
| `CUST-DEMO-KAVYA` | Kavya Joshi, 26, Pune | Gig job lost 2025-11, recovered 2026-03, caught up | current (0) | 40,184 | 0 | 0 | not_at_risk / sure_thing |
| `CUST-DEMO-JOSEPH` | Joseph Fernandes, 36, Mumbai | Pays in full on time (control) | current (0) | 25,264 | 0 | 0 | not_at_risk / — |

- **Priya**: affordable **₹2,000/month** (declared income ₹20,000, expenses ₹9,000, one dependant).
  **Overdue ₹11,492** is the minimum due on the 2026-09 statement net of the waivable late fee
  and its GST, i.e. what she must pay to be current once the fee is waived. The 6 × ₹2,000 plan
  at the policy EMI rate of 15% p.a. covers exactly this. Her 2026-09 part-payment (₹5,684 of an
  ₹8,181 minimum) is solved at build time to hit it to the paisa. **Late fee ₹1,300 + 18% GST =
  ₹1,534** (waivable): the slab is chosen on the amount outstanding after the due date (₹98,203
  total due − ₹5,684 paid by the due date = ₹92,519), following the RBI text (decision on issue #1), and charged because she was more than
  3 days past due. Limit ₹1,80,000, no insurance, one dependant.
- **Ravi**: affordable **₹0** (zero capacity); **job-loss insurance** cover; preferred contact
  window 10:00–13:00, so the 11:00 hardship-officer callback fits both it and 08:00–19:00.
- "Overdue" is 0 for accounts that are not past due. "Segment / uplift group" are the intended
  hidden truths (in `facts`); `labels.segment_truth` is computed by the normal rules.

`demo_personas.json` (in `DATA_DIR`, and committed in `data/samples/` without transactions)
holds, per persona: `facts` (story, expectations, as-of statement numbers, affordability,
offer) and the persona's rows from `customers`, `protected_attributes`, `account_months`,
`salary_credits`, `shocks`, `transactions` (DATA_DIR copy only), `features` and `labels`, with
the same column names. Dates are `YYYY-MM-DD`; timestamps are ISO 8601 in UTC.

## Features (task 1.2)

All features at month `t` use only rows at or before `t` (tested by truncation). The payment in
month `t` settles the statement of month `t−1`.

**Missing history is filled with 0.0.** Every `features` column is non-nullable in
`contracts/data/features.md`, so the delta features that need more history than exists (the
first 3 months for `utilisation_delta_3m`, the first 5 for the spend, transaction and salary
deltas) are 0.0, read as "no observable change", never NaN (agreed with the team lead on
2026-10-12). They only occur in the first months of the window (`month` ≤ 2025-02), so models
can filter or flag them by `month`.

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
- Rows for **every window month, `2024-10` .. `2026-09`**, thanks to the label horizon below.

### Label horizon (labels only)

A label at month `t` needs buckets up to `t+3`, which for 2026-07..2026-09 lie after the window.
So the generator keeps simulating **3 more months (2026-10..2026-12, `label_horizon_months`)** and
stores only those months' `account_id, month, dpd, bucket` in the internal
`label_horizon.parquet`. Only `build_labels` reads it.

- **Window output is unchanged.** Payment policies draw their random numbers month by month, so
  the extra months come after every in-window draw. Spend in the extra months repeats each
  account's last in-window desired spend (no new draws). Personas draw their extra-month noise
  after the window's and follow a scripted after-window payment (`pay_after`: Priya keeps paying
  part of the minimum, Ravi nothing, and so on). Same seed ⇒ the same bytes for every table and
  feature; only `labels.parquet`, `label_horizon.parquet` and `demo_personas.json` (which embeds
  labels) change. Tested by hash, and by computing features with and without the horizon.
- **No feature uses the extension months.** Features are built only from the in-window tables;
  `test_label_horizon.py` proves features are identical with and without the horizon, and no
  feature row is later than 2026-09.
- Labels for 2024-10..2026-06 are identical to the no-horizon labels (tested).
- Assumption: no *new* hardship shock starts in the extension months; existing shocks continue.
  Roll-forward rates for 2026-07..09 (5.5–5.7%) match the months before (5.5–5.6%).
- `label_horizon_months=0` switches it off (labels then stop at `2026-06`).

## Experiment simulator (task 1.3)

`datagen experiment [--month 2026-06] [--months 6]` writes `experiment.parquet` (contract) and the hidden
`experiment_potential.parquet` (internal: every account's outcome under **every** treatment).

**Population (pooled):** the experiment pools `experiment_months` months (default **6**) ending
at the experiment month (default `2026-06`, so `2026-01`..`2026-06`). Every account at risk
(`labels.segment_truth` ≠ `not_at_risk`) in any of those months is enrolled **once, at its first
at-risk month**, so `experiment.parquet` stays keyed by `customer_id` and `month` is the enrolment
month. Seed 42, 10,010 accounts: **2,120 enrolled** (424 per arm), against 1,529 with a single
month: January 1,287 (everyone already at risk), then 133–192 newly at-risk accounts a month.
Many at-risk accounts stay at risk for months, so pooling adds new accounts, not repeats. Rows
scale linearly with `--n` (≈ 21% of customers), so `--n 50000` gives about 10,600 rows (2,100
per arm). `--months 1` reproduces the single-month design. The arms, costs, probabilities and
hidden uplift groups below are unchanged. **Assignment:** exactly 20% each to `none`,
`reminder`, `chat_invite`, `agent_call`, `relief_offer`, in random order.

**Hidden `true_uplift_group`** (evaluation only), drawn from the behaviour context:

| Context | persuadable | sure_thing | lost_cause | sleeping_dog |
|---|---|---|---|---|
| shocked, severity < ⅔ (partial capacity) | 75% | 5% | 12% | 8% |
| shocked, severity ≥ ⅔ | 30% | 5% | 60% | 5% |
| won't pay | 10% | 0% | 80% | 10% |
| forgetful, or "forgot" | 10% | 75% | 0% | 15% |
| other at-risk ("can't pay") | 50% | 5% | 35% | 10% |

Demo personas keep their scripted group (Priya persuadable, Ravi lost cause, Meera sleeping dog…).

**90-day outcomes** (assumptions). Cure probability = base + treatment lift (clipped to 0–1):

| Group | base | reminder | chat invite | agent call | relief offer | P(NPA \| not cured) |
|---|---|---|---|---|---|---|
| persuadable | 0.20 | +0.10 | +0.35 | +0.20 | +0.50 | 0.50 |
| sure_thing | 0.85 | +0.03 | +0.04 | +0.04 | +0.05 | 0.10 |
| lost_cause | 0.05 | 0 | +0.02 | +0.03 | +0.05 | 0.85 |
| sleeping_dog | 0.60 | −0.05 | −0.10 | −0.35 | −0.15 | 0.45 |

A cured account is never NPA. All treatments share one cure draw and one NPA draw per account
(common random numbers), so policies are compared on identical luck.

**Contact costs** (`contact_cost_paise`, assumptions): none ₹0, reminder ₹2, chat ₹5, agent call
₹60, relief offer ₹80 **plus the waiver** (late fees + GST charged in the 3 months up to the
experiment month).

**`experiment.simulate_policy(assignments)`** takes a DataFrame of `account_id, treatment` (accounts
left out get `none`), applies it to the same population and returns a dict shaped like
`contracts/fixtures/simulation_metrics.json` (`SimulationMetrics`). The baseline is "call
everyone" (an agent call for every account); `as_of_month` is the last month of the pool;
`illustrative` is `true`. Its interface is unchanged by pooling.

**Acceptance (seed 42, 10,000 customers, pool 2026-01..2026-06):**

| Strategy | Contacts | NPA rate | Cure rate | Cost |
|---|---|---|---|---|
| Call everyone (agent call) | 2,120 | 37.9% | 40.4% | ₹1,27,200 |
| Oracle (chat with true persuadables only) | 896 | 33.3% (−12.2%) | 48.4% | ₹4,480 |
| Random 896 accounts, chat | 896 | 37.0% (−2.5%) | 40.6% | ₹4,480 |

With known groups the oracle beats calling everyone on both NPA and cost; random targeting at the
same budget gets only a small fraction of that NPA gain. So the simulator has signal for WS2's uplift model to find.
These outcomes are a separate simulation; they do not rewrite the statement history after the
experiment month.

## Scale: 5 lakh customers

`uv run datagen all --n 500000 --no-transactions` on a 16-core laptop (Ryzen 9 8940HX, 31 GB
RAM), seed 42:

| Step | Wall time | Peak memory |
|---|---|---|
| generate (`--no-transactions`) | 60 s | 9.5 GB |
| features + labels (5 chunks of 1 lakh accounts) | 66 s | 8.8 GB (alone) |
| experiment | 11 s | 4.6 GB (alone) |
| **`datagen all` end to end** | **2 min 48 s** (target < 30 min) | **10.1 GB** peak working set |

Result: 500,010 accounts, NPA 3.81% at 2026-09, SMA-0 3.76%, SMA-1 1.36%, SMA-2 0.70%. Largest
files: `features.parquet` 495 MB, `account_months.parquet` 361 MB, `monthly_spend.parquet` 185 MB.

**Chunking.** Before tuning, the features step alone peaked at 14.6 GB, too close to a 16 GB
laptop. It now processes `FEATURE_CHUNK_ACCOUNTS` (1,00,000) accounts at a time: inputs are read
once as Arrow tables, each chunk is turned into features and labels, validated, and appended to
the Parquet file as row groups. Features and labels depend only on an account's own rows, so the
content is identical to a single pass (tested with a tiny chunk size); runs that fit in one chunk
(10,000 customers, the samples) keep their exact bytes. With transactions, 5 lakh customers would
be about 380 million rows (≈ 4.5 GB on disk); use `--no-transactions` at that size.

## Samples

`samples/demo_personas.json`: the ten personas (see above), regenerated by the same commands.

`samples/protected_attributes_sample.parquet`: for WS2's fairness metrics (task 2.5) and WS7's
bias tests. One row per customer in the features sample (200 rows), keyed by `customer_id`:
`gender, religion, caste_category, state, region, age_band` (`21-30`, `31-40`, `41-50`, `51-65`,
from `customers.age`). It is a **separate file and never part of the features**: join it on
`customer_id` only for evaluation (A3, IS/ISO/IEC TR 24027:2021; tested).

`samples/features_sample.parquet` and `samples/labels_sample.parquet`: seed 42, 10,000
customers, **200 accounts × 10 labelled months, pinned to `2025-09` .. `2026-06` = 2,000 rows**
with identical keys. Half the accounts were past due at some point in those months (so both label
classes appear), half random. Regenerate:

```bash
uv run datagen generate --n 10000 --seed 42 --no-transactions
uv run datagen features --samples data/samples
```

## Still to come

- Parity test against WS3's `npa_rules.dues` running for real once it is on `main`.
