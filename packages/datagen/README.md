# datagen

**Owner:** WS1 (Data foundation) · **Tasks:** 1.1 synthetic data generator · 1.2 feature
pipeline · 1.3 experiment simulator · **Issues:** #1, #2, #3

Builds reproducible, India-specific synthetic credit-card histories (up to 5 lakh customers,
`2024-10` → `2026-09`), calibrated on the public UCI "Default of Credit Card Clients" dataset,
plus the feature table, labels and a randomised collections experiment. Output is Parquet in
`$DATA_DIR`; table specs are in [`contracts/data/`](../../contracts/data/). Every assumption and
probability is documented in [`data/README.md`](../../data/README.md).

**Synthetic data only.** No real personal data is read or written.

## Status

| Step | Command | Status |
|---|---|---|
| Generate tables (1.1) | `uv run datagen generate` | customers, protected attributes, statements, salary, shocks, transactions |
| Demo personas (1.1 step 6) | part of `generate` | 10 fixed `CUST-DEMO-*` customers, `demo_personas.json` |
| Features + labels (1.2) | `uv run datagen features [--samples data/samples]` | done |
| Experiment (1.3) | `uv run datagen experiment [--month 2026-06] [--months 6]` | randomised experiment pooled over 6 months + `simulate_policy()` |
| Everything | `uv run datagen all` | runs the steps in order |

## How to run

```bash
uv run datagen generate --n 10000 --seed 42 --out data/generated   # ~17 s with transactions
uv run datagen generate --no-transactions                          # large runs
uv run datagen features                                            # ~2 s for 10,000 customers
uv run datagen experiment                                          # task 1.3
uv run datagen all --n 10000 --seed 42                             # everything, ~26 s
uv run datagen all --n 500000 --no-transactions                    # 5 lakh: ~3 min, ~10 GB peak
uv run python data/scripts/sanity_report.py                        # NPA rate, leading indicators
uv run datagen --help
```

Refreshing the calibration (needs network; never in CI):

```bash
uv run python data/scripts/download_public.py
uv run python -m datagen.calibrate_uci
```

Flags override environment variables; see `.env.example` (A11).

| Env var | Default | Flag |
|---|---|---|
| `SEED` | `42` (`npa_contracts.constants.DEFAULT_SEED`) | `--seed` |
| `DATA_DIR` | `./data/generated` | `--out` |
| `RAW_DATA_DIR` | `./data/raw` | — |
| `DATAGEN_N_CUSTOMERS` | `10000` (CI `2000`, full demo `500000`) | `--n` |
| `AS_OF_MONTH` | `2026-09` | — |
| `CONTRACTS_DIR` | repo `contracts/` | — |

## Outputs

Contract tables: `customers`, `protected_attributes`, `account_months`, `salary_credits`,
`shocks`, `transactions` (folder, one file per month), `features`, `labels`, plus
`demo_personas.json` and `experiment`. Internal tables
(not features, not contracts): `monthly_spend` (category totals per account-month),
`behaviour_types` (hidden ground truth), `label_horizon` (DPD/bucket for 3 months after the
window, labels only) and `experiment_potential` (hidden potential outcomes).
Same seed ⇒ byte-identical Parquet.

## Public API

| Module | What |
|---|---|
| `datagen.DatagenConfig` | pydantic-settings config; calendar and seed defaults from `npa_contracts.constants` |
| `datagen.generate.build(cfg)` / `write(data, cfg)` | task 1.1 tables in memory / validated to disk |
| `datagen.features.build_features(...)` | task 1.2 features (no look-ahead) |
| `datagen.labels.build_labels(...)` | task 1.2 labels |
| `datagen.personas` | the ten demo personas (`PERSONAS`, `build_personas`, `persona_facts`) |
| `datagen.experiment.simulate_policy(assignments)` | apply a targeting policy to the experiment population; `SimulationMetrics`-shaped dict vs "call everyone" |
| `datagen.dues` | RBI dues rules as pure functions (+ vectorised twins) |
| `datagen.validate` | pandera / Arrow schemas generated from `contracts/data/*.md` |

## Module map

`calibrate_uci` (UCI fits) · `customers`, `protected` (population) · `personas` (demo customers) · `behaviour` (UCI-driven
repayment, spend plan) · `shocks` (hidden behaviour types and shocks) · `statements` (month loop)
· `dues` (RBI arithmetic) · `salary` · `transactions` · `features` · `labels` · `experiment` · `pipeline`
(features step + samples) · `validate` · `sanity` · `cli`.

## Data card

**What it is.** A fully synthetic, reproducible panel of Indian credit-card customers (default
10,000; up to 5 lakh) over 24 months (`2024-10` to `2026-09`, as-of month `2026-09`). It has
statements that follow RBI rules, hidden hardship ground truth, features, labels and a
randomised collections experiment. Built for the Pre-NPA Rescue hackathon prototype:
early-warning, segmentation and uplift models (WS2), the rules engine and personas (WS3/WS4),
API seeding (WS5) and bias tests (WS7).

**Sources.**

| Source | Use | Licence |
|---|---|---|
| UCI ML Repository dataset 350, *Default of Credit Card Clients* (Yeh, 2009; 30,000 Taiwanese cardholders, April–September 2005), https://doi.org/10.24432/C55S3H | Calibration only: limit spread, bill-to-limit and payment-to-bill ratios, repayment-status transitions, default rates | CC BY 4.0 (credited in `data/ATTRIBUTION.md`) |
| Faker `en_IN` | Name pools for synthetic customers | MIT |
| Our own assumptions | Population mix, income, shocks, behaviour types, experiment probabilities and costs, bank-policy numbers (mirroring WS3's `bank_policy.yaml`) | documented in `data/README.md` |

No other dataset is used. The raw UCI file is downloaded to `data/raw/` (gitignored) and never
committed. Only the fitted parameters (`calibration.json`, about 20 KB) are committed. The UCI
demographic columns (sex, education, marriage, age) are never read.

**Calibration.** `calibrate_uci.py` fits on all 30,000 rows:
- a log-normal limit fit (σ = 0.94)
- bill-to-limit quantiles (opening utilisation)
- payment-to-bill quantiles by previous status (how much normal customers repay)
- a 4×4 status transition matrix (cure / stay / roll once delinquent)
- default rates by band (reference only)

Money is converted **by ratio, not exchange rate**: limits are rescaled so the median card
limit is ₹1,50,000. UCI's duly → late rate is scaled by 0.12 to Indian delinquency levels, so
NPA at 2026-09 is 3.6% (10,000 customers) to 3.8% (5 lakh), inside the 3–6% target. The sparse
UCI `late1` row (34 observations) borrows the `late2` row by role. Full detail: `data/README.md`.

**Synthetic only.** Every person, account, transaction and number is generated. Names come
from Faker pools; phone numbers and emails are masked (`+91-98XXXXX123`, `p****@example.com`).
No row corresponds to a real individual, so no DPDP Act personal data is processed. Protected
attributes (gender, religion, caste category, state, region) live only in
`protected_attributes.parquet` and the separate `protected_attributes_sample.parquet`; tests
check they never reach the features.

**Intended use / out of scope.** Use it to develop and demonstrate models, rules and UI, to
test fairness tooling, and for illustrative policy simulations (`simulate_policy` output is
marked `illustrative: true`). Do **not** use it to estimate real Indian portfolio risk, to set
credit policy, or to quote real-world effect sizes: every relationship below was designed by us.

**Known biases and limitations in the synthetic data.**
1. **Foreign, dated calibration.** Repayment behaviour comes from a stressed 2005 Taiwanese
   portfolio (22% default), rescaled with assumed factors. Indian card behaviour (e.g. UPI-era
   spend, EMI-on-card habits) is not learned from data.
2. **Designed hardship signals.** Shock rates, severities, lead times (1–3 months) and their
   leading indicators are our assumptions. They are cleaner and more regular than real life, so
   model performance here will overstate real-world performance.
3. **Protected attributes are independent of hardship by construction.** That makes bias tests
   meaningful (any gap is the model's), but it is not how real data looks. **Proxy pathways
   still exist**: state drives city, and city tier drives income (median monthly income by
   region ranges from ₹49,900 (east) to ₹56,400 (north)), which drives limits and therefore
   utilisation features. Language also follows state. Regional gaps in model outputs can
   therefore appear through these proxies even though no protected attribute is a feature.
4. **Assumed population shares.** Gender (61% male, 38% female, 1% non-binary), religion and
   caste-category shares are rough population assumptions, not cardholder statistics.
5. **Names carry gender.** Faker first names are gender-consistent; names are never features,
   but anything that reads names (e.g. a chatbot) sees a gender proxy.
6. **Simplified economics.** Income is log-normal by occupation and city tier, with no informal
   income, seasonality in income, or multiple cards. There is one card per customer and no
   bureau data.
7. **Utilisation drift.** Median utilisation rises from 0.24 (2024-10) to 0.41 (2026-09) as
   revolvers accumulate balances; the early months are not a steady state.
8. **Label horizon.** Labels for 2026-07..09 use three simulated months after the window, in
   which no new hardship shock starts.
9. **Experiment.** Uplift groups and treatment effects are assumed probabilities. The
   experiment "proves" signal only for the effects we put in.
10. **Missing history.** Features needing more history than exists are 0.0 ("no change"),
    because the contract columns are non-nullable.
11. **Personas are hand-scripted** and solved to exact agreed numbers. They are illustrations,
    not samples of the population.

**How to regenerate.**

```bash
uv sync
uv run datagen all --n 10000 --seed 42                          # everything (offline, ~26 s)
uv run datagen features --samples data/samples                  # refresh committed samples
uv run python data/scripts/sanity_report.py                     # NPA rate, leading indicators
uv run datagen all --n 500000 --no-transactions                 # 5 lakh: ~3 min, ~10 GB peak
# Optional, needs network: refresh the calibration from UCI
uv run python data/scripts/download_public.py && uv run python -m datagen.calibrate_uci
```

Same seed ⇒ byte-identical Parquet. Lineage, every probability and every assumption are in
[`data/README.md`](../../data/README.md) (IS/ISO/IEC 8183:2023 data life cycle, design alignment,
not certification).

## Regulations and standards

| Reference | Where |
|---|---|
| RBI Credit Card Directions 2025: late fee only after > 3 days past due, on the post-due outstanding; no interest on fees/charges/taxes; no negative amortisation; DPD from the due date | `dues.py`, `statements.py` |
| RBI asset classification for credit cards (16 July 2015): NPA when MAD unpaid > 90 days | `npa_contracts.constants.bucket_for_dpd` via `dues.py` |
| RBI RBC Directions para 454Y(4), 454Y(6): contact window 08:00–19:00, preferred times | `customers.preferred_contact_window` always inside the window |
| IS/ISO/IEC 8183:2023 data life cycle | lineage, retention and assumptions in `data/README.md` |
| IS/ISO/IEC TR 24027:2021 bias | protected attributes independent of hardship, only in `protected_attributes.parquet`; tested never to reach features |
| DPDP Act 2023 data minimisation | synthetic data only; masked phone/email |

WS3's `npa_rules.dues` implements the same rules; `tests/test_rbi_rules_parity.py` checks the two
agree (skipped until `npa_rules.dues` is on `main`).

## Tests

```bash
uv run pytest packages/datagen        # ~6 s, 97% line coverage
```
