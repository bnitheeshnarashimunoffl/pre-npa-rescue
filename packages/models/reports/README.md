# `packages/models/reports/`

Written by `uv run npa-models evaluate` (task 2.5, `npa_models.evaluate`). Everything here is
generated: don't edit by hand, re-run `evaluate`. Reports are only committed when produced
from WS1's data, never from the fake test data.

| File | What |
|---|---|
| `metrics.json` | all metrics, persona checks and the fairness block (shape below) |
| `policy_simulation.json` | pitch headline, exactly `npa_contracts.api.SimulationMetrics` (`contracts/fixtures/simulation_metrics.json`) |
| `policy_strategies.json` | call everyone vs risk-only vs uplift (ours) vs oracle (upper bound) |
| `model_card_early_warning.md`, `model_card_segment.md`, `model_card_uplift.md` | model cards (IS/ISO/IEC TS 4213, IS/ISO/IEC 25059:2023, IS/ISO/IEC TR 24027:2021) |
| `roc_early_warning.png`, `pr_early_warning.png`, `calibration_early_warning.png`, `shap_summary_early_warning.png`, `qini_uplift.png` | plots |

## `metrics.json` (schema_version 1, stable)

The keys below are a contract with WS7 (`redteam/src/npa_redteam/fairness.py`, #106). They are
kept stable: new keys may be **added**; existing keys are never renamed or removed without a
`schema_version` bump announced to WS7 first.

```jsonc
{
  "schema_version": 1,
  "generated_by": "npa-models evaluate",
  "as_of_month": "2026-09",
  "model_version": "ew-lgbm-2026.10.12-32d471",        // string: the early-warning model
  "model_versions": {"early_warning": "...", "segment": "...", "uplift": "..."},
  "data": {
    "split": {"train_end": "2026-03", "val_start": "2026-04", "val_end": "2026-06",
              "test_start": "2026-07", "test_end": "2026-09"},
    "evaluation_window": "validation" | "test",
    "test_status": "pending" | "final",                  // pending until WS1's label horizon
    "rows": {"validation": 0, "test": 0, "as_of_month": 0},
    "seed": 42,
    "bootstrap_resamples": 200
  },
  "thresholds": {"fairness_max_diff": 0.05, "fairness_min_ratio": 0.8,
                 "fairness_min_group_size": 30},
  "early_warning": {
    "target": "rolls_forward_60d", "model_version": "...", "calibration": "...",
    "thresholds": {"high": 0.35, "medium": 0.15},
    "validation": {"roll_forward": M, "npa_90d": M, "baseline": M},
    "test":       {"roll_forward": M | "pending", "npa_90d": M | "pending", "baseline": M | "pending"},
    "band_share": {"validation": {"low": 0, "medium": 0, "high": 0}, "as_of_month": {...}},
    "suggested_high_threshold_6_5pct": 0.0,
    "robustness": {"feature_noise_10pct": R, "salary_data_missing": R}
  },
  "segment": {
    "target": "segment_truth", "model_version": "...",
    "rule": {"wont_pay_min_confidence": 0.5},
    "validation": S, "test": S | "pending"
  },
  "uplift": "pending" | {
    "model_version": "...", "learner": "...", "tau": 0.05, "cure_value_paise": 500000,
    "arm_cost_paise": {"reminder": 0, "chat_invite": 0, "agent_call": 0, "relief_offer": 0},
    "evaluation_out_of_fold": {"qini_auc": 0, "uplift_auc": 0, "n": 0,
                               "group_share": {...}, "group_accuracy": 0, "group_confusion": {...}},
    "out_of_fold_matches_saved_model": true,
    "policy": "pending" | {"npa_reduction_pct_vs_call_everyone": 0,
                           "npa_reduction_pct_vs_risk_targeting": 0, "see": [...]}
  },
  "explainability": {"method": "...", "mean_abs_shap": {"<feature>": 0},
                     "high_band_with_reasons_share": 0,
                     "reason_code_share_high_band": {"<CODE>": 0}},
  "personas": [{"account_id": "ACC-DEMO-PRIYA", "check": "risk_band" | "uplift_group",
                "expected": "high", "actual": "high", "status": "pass" | "fail" | "not_available"}],

  "fairness": {                                         // WS7 reads this block
    "<model>": {                                        // early_warning | segment | uplift
      "<attribute>": {                                  // gender | religion | caste_category | region
        "<metric>_diff": 0.0,                           // largest gap between groups; > 0.05 = gap
        "<metric>_ratio": 0.0,                          // min/max rate; < 0.8 = four-fifths warning
        "flagged": ["<metric>_diff", ...],              // which of the above are over threshold
        "groups": {"<group>": {"n": 0, "<rate>": 0.0, ...}}
      }
    }
  },
  "fairness_population": {"<model>": "who was evaluated"},
  "fairness_flags": [{"model": "...", "attribute": "...", "metric": "..._diff", "value": 0.0,
                      "threshold": 0.05, "tier": "primary" | "secondary", "mitigation": "..."}]
}
```

`M` (binary metrics): `roc_auc, pr_auc, brier, ks, base_rate, n, ci95: {roc_auc, pr_auc, brier,
ks: [low, high]}`. `R`: `roc_auc, pr_auc, brier, roc_auc_change`. `S`: `labels,
confusion_matrix, macro_f1, recall: {class: value}, n, low_confidence_share, ci95: {macro_f1}`.

### Fairness metrics per model

Every `*_diff` is the largest difference between groups with at least 30 accounts (`null` when
fewer than two such groups). Every `*_ratio` is the smallest rate over the largest. All numbers
are 0..1.

| Model | `*_diff` keys (primary, flag > 0.05) | `*_ratio` keys (secondary, warn < 0.8) | `groups.<g>` keys |
|---|---|---|---|
| `early_warning` | `selection_rate_diff` (share in "high"), `equal_opportunity_diff` (TPR), `fpr_diff`, `calibration_diff` (mean predicted − observed) | `disparate_impact_ratio` (selection rate) | `n, selection_rate, tpr, fpr, observed_rate, mean_predicted, calibration_gap` |
| `segment` | `wont_pay_rate_diff`, `accuracy_diff` | — | `n, wont_pay_rate, accuracy` |
| `uplift` | `persuadable_rate_diff` (offered help), `sleeping_dog_rate_diff` (no contact) | `persuadable_ratio` | `n, persuadable_rate, sleeping_dog_rate` |

Populations: early warning and segment use the evaluation-window account-months with labels;
uplift uses the as-of-month accounts in the medium or high risk band. Protected attributes are
read only in `fairness.py`, after scoring; they are never model inputs. Groups missing from the
protected table are reported as `unknown`.

Only `*_diff` and `*_ratio` keys at the attribute level are numeric checks; `flagged`
(list of strings) and `groups` (objects) are not.

## `policy_strategies.json`

`as_of_month, experiment_month, n_accounts, horizon_days, ours: "uplift_targeting",
upper_bound: "oracle", strategies: {call_everyone | risk_targeting | uplift_targeting | oracle:
{strategy, npa_rate, cure_rate, collection_cost_paise, contacts_made, role, description}},
npa_reduction_pct: {call_everyone, risk_targeting}, illustrative, source`.

`role` is `baseline`, `comparison`, `ours` or `upper_bound`. The oracle uses hidden truth and is
an upper bound only: never present it as our result.
