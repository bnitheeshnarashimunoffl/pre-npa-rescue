# npa_models

**Owner:** WS2 (Analysis & classification models)

The intelligence of the **Detect** and **Decide** layers: an early-warning model (roll-forward in
30–60 days), plain-language reason codes, a forgot / can't pay / won't pay segmentation, and an
uplift model that decides who is worth contacting at all. Implements
`npa_contracts.providers.RiskProvider`.

**Tasks:** 2.1 early-warning · 2.2 explanations · 2.3 segmentation · 2.4 uplift · 2.5 evaluation report

> Status: skeleton + task 2.1 early-warning model. Reasons (2.2), segmentation (2.3), uplift
> (2.4) and the evaluation report (2.5) land in the following PRs.

## Early-warning model (task 2.1, `early_warning.py`)

- **Target:** `rolls_forward_60d`; secondary head `reaches_npa_90d`.
- **Model:** LightGBM, `class_weight="balanced"`, monotonic constraints (`MONOTONE`): risk never
  falls as `min_due_only_streak`, `months_since_full_payment`, `dpd`, `max_dpd_6m`,
  `broken_streak_flag`, `salary_missing_months_3m`, `utilisation` or `cash_advance_ratio_3m`
  rise, and never rises with `payment_ratio_3m` or `income_to_due_ratio`.
- **Baseline:** logistic regression (median impute, scale, one-hot occupation), same split.
- **Calibration:** isotonic regression fitted on the validation months only.
- **Risk bands:** high ≥ 0.35, medium ≥ 0.15, else low (`RISK_HIGH_THRESHOLD`,
  `RISK_MEDIUM_THRESHOLD`). The target is a "high" queue of about 5–8% of accounts. Training
  records the band shares on validation and the cut-off that would give 6.5%
  (`suggested_high_threshold_6_5pct` in `meta.json`); set the thresholds from that once trained on
  WS1's data. Thresholds are stored in the bundle so scoring uses the values it was trained with.
- **API:** `train(features_path, labels_path) -> ModelBundle`, `train_frames(...)`,
  `EarlyWarningModel.score(df) -> list[RiskScore]`, `.score_batch(features, as_of_month)`,
  `.score_frame(df)` (vectorised), `.save()` / `.load()`.
- **CLI:** `uv run npa-models train --all` → `$MODEL_DIR/early_warning/`.

## Segmentation (task 2.3, `segment.py`)

- **Target:** `segment_truth` (`forgot`, `cant_pay`, `wont_pay`, `not_at_risk`); multiclass
  LightGBM with `class_weight="balanced"` on the same allowlisted features.
- **Conservative rule:** if `wont_pay` is the top class but its probability is < 0.5
  (`WONT_PAY_MIN_CONFIDENCE`), output the lower-harm `cant_pay` and set `low_confidence`. A wrong
  "won't pay" sends a struggling customer down the firm route, so we prefer the less harmful
  error (RBI RBC Directions para 454D fair treatment; IS/ISO/IEC TR 24027). The briefing's wording
  applies the 0.5 to the `cant_pay` probability, which would make `wont_pay` unreachable, so the
  threshold is on the `wont_pay` probability instead.
- `low_confidence` and the per-class probabilities are in `SegmentModel.score_frame`;
  `SegmentResult` (contract) has no field for the flag.
- **Metrics:** confusion matrix, macro-F1 and per-class recall on validation and test, both raw
  (argmax) and after the rule, plus the share of rows the rule relabelled.
- **API:** `train(...)`, `train_frames(...)`, `SegmentModel.score(df) -> list[SegmentResult]`,
  `.score_batch(features, as_of_month)`, `.score_frame(df)`, `.save()` / `.load()`.
- **CLI:** `npa-models train --all` also writes `$MODEL_DIR/segment/`.

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
uv run npa-models --help            # train | score | evaluate (score/evaluate are stubs)
uv run npa-models train --all       # needs $DATA_DIR/features.parquet + labels.parquet
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
| IS/ISO/IEC TS 4213 (classification performance) | `metrics.binary_metrics`: ROC-AUC, PR-AUC, Brier, KS + base rate |
| IS/ISO/IEC 25059:2023 (explainability, controllability) | monotonic constraints in `early_warning.MONOTONE` |
| RBI card NPA rule (min due unpaid > 90 days, 16 Jul 2015) | `reaches_npa_90d` head |
