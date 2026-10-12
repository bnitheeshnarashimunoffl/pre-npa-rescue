# npa_models

**Owner:** WS2 (Analysis & classification models)

The intelligence of the **Detect** and **Decide** layers: an early-warning model (roll-forward in
30–60 days), plain-language reason codes, a forgot / can't pay / won't pay segmentation, and an
uplift model that decides who is worth contacting at all. Implements
`npa_contracts.providers.RiskProvider`.

**Tasks:** 2.1 early-warning · 2.2 explanations · 2.3 segmentation · 2.4 uplift · 2.5 evaluation report

> Status: package skeleton (config, feature allowlist and leakage guard, time split, model
> registry, CLI stub). Models land in the following PRs.

## Public API (so far)

| Name | Module | Purpose |
|---|---|---|
| `ModelSettings` | `config` | `SEED`, `DATA_DIR`, `MODEL_DIR`, `AS_OF_MONTH` from env / `.env` |
| `FEATURE_COLUMNS`, `FORBIDDEN_COLUMNS` | `features` | allowed model inputs; columns that must never be inputs |
| `assert_no_leakage`, `build_matrix`, `LeakageError` | `features` | guard + model input matrix |
| `TimeSplit`, `time_split` | `features` | month-based train ≤ 2026-03 / val 2026-04..06 / test 2026-07..09 |
| `ModelBundle`, `save_bundle`, `load_bundle` | `registry` | artifacts in `$MODEL_DIR/<name>/` |
| `make_model_version` | `registry` | e.g. `ew-lgbm-2026.10.11-a1b2c3` (date + hash of inputs) |

## How to run

```bash
uv run npa-models --help            # train | score | evaluate (stubs for now)
uv run pytest packages/models
uv run python -m mypy packages/models
```

Trained artifacts go to `$MODEL_DIR` (default `packages/models/artifacts/`, gitignored, never
committed). Model cards and metrics go to `reports/` (committed).

Until WS1's `data/samples/*.parquet` land, tests use a seeded fake-feature generator in
`tests/conftest.py` that matches `contracts/data/` (features, labels, protected attributes),
including the demo personas `CUST-DEMO-PRIYA` and `CUST-DEMO-RAVI`.

## Rules this package enforces

- **No protected attributes or hidden truth as inputs.** `gender`, `religion`, `caste_category`,
  `state`, `region`, shocks and `true_uplift_group` are in `FORBIDDEN_COLUMNS`; `build_matrix`
  and `ModelBundle` raise `LeakageError` if one is requested. `city` is excluded as a proxy for
  state/region. `protected_attributes.parquet` is read only by `fairness.py` (evaluation), which
  a test enforces.
- **No look-ahead.** Splits are by month only, never random.
- **Deterministic.** Everything is seeded from `SEED` (default 42).

## RBI / BIS references

| Item | Where |
|---|---|
| A3 rule 1, fair treatment (RBI RBC Directions) | `features.FORBIDDEN_COLUMNS`, `tests/test_leakage_guard.py` |
| IS/ISO/IEC TR 24027:2021 (bias in AI systems) | leakage guard; fairness metrics (task 2.5) |
| IS/ISO/IEC 23053:2022 (ML framework, lifecycle) | time-based split |
| IS/ISO/IEC 42001:2023, RBI FREE-AI (AI inventory) | `registry.make_model_version` on every output |
| IS/ISO/IEC TS 4213, IS/ISO/IEC 25059:2023 | model cards in `reports/` (task 2.5) |
