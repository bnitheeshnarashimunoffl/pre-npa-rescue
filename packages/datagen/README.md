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
