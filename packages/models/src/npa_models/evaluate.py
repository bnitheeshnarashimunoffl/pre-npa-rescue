"""Task 2.5: model evaluation report, written to ``packages/models/reports/``.

``evaluate()`` computes everything in memory and ``write_reports()`` writes:

- ``metrics.json``: all metrics, persona checks and the fairness block; the exact keys are
  documented in ``reports/README.md`` and are kept stable (WS7 reads it, #106)
- ``policy_simulation.json``: the pitch headline, exactly ``npa_contracts.api.SimulationMetrics``
- ``policy_strategies.json``: call everyone vs risk-only vs uplift (ours) vs the oracle, which
  is an upper bound built from hidden truth and never our result
- ``model_card_early_warning.md``, ``model_card_segment.md``, ``model_card_uplift.md``
  (IS/ISO/IEC TS 4213 and IS/ISO/IEC 25059:2023 headings)
- PNG plots: ROC, PR, calibration, Qini, SHAP summary

Metrics come with 95% bootstrap intervals. Test-month (2026-07..09) numbers are reported only
when the test months have labels; until WS1 extends the label horizon they are ``"pending"``
and the report uses the validation months, which also fitted the calibrator (noted in the
cards). Fairness uses :mod:`npa_models.fairness`, the only reader of protected attributes.
"""

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd

from npa_contracts.api import SimulationMetrics
from npa_contracts.enums import RiskBand
from npa_models import fairness, segment, uplift
from npa_models.early_warning import NPA_TARGET, TARGET, EarlyWarningModel
from npa_models.explain import shap_values
from npa_models.features import (
    DEFAULT_SPLIT,
    NUMERIC_FEATURES,
    TimeSplit,
    build_matrix,
    labelled_splits,
)
from npa_models.metrics import binary_metrics, bootstrap_ci
from npa_models.segment import SegmentModel, classification_report
from npa_models.uplift import UpliftModel

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1
N_BOOT = 200
NOISE_SHARE = 0.10  # robustness: Gaussian noise with sd = 10% of each feature's spread
SALARY_FEATURES = ("salary_missing_months_3m", "salary_delta_3m", "income_to_due_ratio")
PENDING = "pending"
OWNER = "WS2 (Analysis & classification models), packages/models"

# Persona checks for the demo (briefing B4 2.1 / 2.4; A1 stories).
PERSONA_CHECKS: tuple[tuple[str, str, str], ...] = (
    ("ACC-DEMO-PRIYA", "risk_band", RiskBand.HIGH.value),
    ("ACC-DEMO-RAVI", "risk_band", RiskBand.HIGH.value),
    ("ACC-DEMO-PRIYA", "uplift_group", "persuadable"),
)


@dataclass
class Models:
    early_warning: EarlyWarningModel
    segment: SegmentModel
    uplift: UpliftModel | None = None


@dataclass
class EvalData:
    features: pd.DataFrame
    labels: pd.DataFrame
    protected: pd.DataFrame
    experiment: pd.DataFrame | None = None
    potential: pd.DataFrame | None = None


@dataclass
class Report:
    metrics: dict[str, Any]
    policy_simulation: dict[str, Any] | None = None
    policy_strategies: dict[str, Any] | None = None
    curves: dict[str, Any] = field(default_factory=dict)  # arrays for the plots only


# --- helpers --------------------------------------------------------------------------------


def jsonable(obj: Any, digits: int = 4) -> Any:
    """Plain JSON types: numpy scalars unwrapped, floats rounded, NaN/inf → null."""
    if isinstance(obj, Mapping):
        return {str(k): jsonable(v, digits) for k, v in obj.items()}
    if isinstance(obj, list | tuple | np.ndarray):
        return [jsonable(v, digits) for v in obj]
    if isinstance(obj, bool | np.bool_):
        return bool(obj)
    if isinstance(obj, int | np.integer):
        return int(obj)
    if isinstance(obj, float | np.floating):
        f = float(obj)
        return round(f, digits) if np.isfinite(f) else None
    return obj


def _with_ci(y: npt.ArrayLike, p: npt.ArrayLike, *, n_boot: int, seed: int) -> dict[str, Any] | str:
    y_arr, p_arr = np.asarray(y, dtype=int), np.asarray(p, dtype=float)
    if len(np.unique(y_arr)) < 2:
        return PENDING
    out: dict[str, Any] = binary_metrics(y_arr, p_arr)

    def stat(idx: npt.NDArray[np.int_]) -> dict[str, float]:
        m = binary_metrics(y_arr[idx], p_arr[idx])
        return {k: m[k] for k in ("roc_auc", "pr_auc", "brier", "ks")}

    out["ci95"] = bootstrap_ci(stat, len(y_arr), n_boot=n_boot, seed=seed)
    return out


def _has_labels(part: pd.DataFrame, target: str) -> bool:
    return not part.empty and part[target].nunique() == 2


def _band_share(bands: npt.ArrayLike) -> dict[str, float]:
    arr = np.asarray(bands)
    return {b.value: float(np.mean(arr == b.value)) for b in RiskBand}


# --- early warning --------------------------------------------------------------------------


def _robustness(
    model: EarlyWarningModel, rows: pd.DataFrame, y: pd.Series, seed: int
) -> dict[str, Any]:
    """Performance under 10% feature noise and with salary data missing (IS/ISO/IEC 25059)."""
    rng = np.random.default_rng(seed)
    noisy = rows.copy()
    for col in NUMERIC_FEATURES:
        values = noisy[col].astype(float)
        noisy[col] = values + rng.normal(0.0, NOISE_SHARE * float(values.std() or 0.0), len(values))
    no_salary = rows.assign(**{c: np.nan for c in SALARY_FEATURES})
    out: dict[str, Any] = {}
    clean = binary_metrics(y, model.predict_proba(rows))
    for name, frame in (("feature_noise_10pct", noisy), ("salary_data_missing", no_salary)):
        m = binary_metrics(y, model.predict_proba(frame))
        out[name] = {k: m[k] for k in ("roc_auc", "pr_auc", "brier")}
        out[name]["roc_auc_change"] = m["roc_auc"] - clean["roc_auc"]
    return out


def _early_warning(
    model: EarlyWarningModel,
    val: pd.DataFrame,
    test: pd.DataFrame,
    eval_rows: pd.DataFrame,
    as_of_rows: pd.DataFrame,
    *,
    n_boot: int,
    seed: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    def window(part: pd.DataFrame) -> dict[str, Any]:
        if not _has_labels(part, TARGET):
            return {"roll_forward": PENDING, "npa_90d": PENDING, "baseline": PENDING}
        return {
            "roll_forward": _with_ci(
                part[TARGET], model.predict_proba(part), n_boot=n_boot, seed=seed
            ),
            "npa_90d": _with_ci(
                part[NPA_TARGET], model.predict_npa_proba(part), n_boot=n_boot, seed=seed
            ),
            "baseline": _with_ci(
                part[TARGET], model.predict_baseline_proba(part), n_boot=n_boot, seed=seed
            ),
        }

    p_eval = model.predict_proba(eval_rows)
    contrib = shap_values(
        model.bundle.estimators["roll_forward"],
        build_matrix(eval_rows, model.bundle.feature_columns),
    )
    as_of_scores = model.score(as_of_rows)
    high = [s for s in as_of_scores if s.risk_band is RiskBand.HIGH]
    codes = pd.Series([r.code for s in high for r in s.reasons], dtype=object)
    section = {
        "target": TARGET,
        "model_version": model.model_version,
        "calibration": "isotonic, fitted on the validation months",
        "thresholds": {"high": model.bands.high, "medium": model.bands.medium},
        "validation": window(val),
        "test": window(test),
        "band_share": {
            "validation": _band_share(model.bands.bands(model.predict_proba(val))),
            "as_of_month": _band_share([s.risk_band.value for s in as_of_scores]),
        },
        "suggested_high_threshold_6_5pct": model.bundle.metadata.get(
            "suggested_high_threshold_6_5pct"
        ),
        "robustness": _robustness(model, eval_rows, eval_rows[TARGET], seed),
    }
    explainability = {
        "method": "TreeSHAP (LightGBM pred_contrib) on the roll-forward head, log-odds",
        "mean_abs_shap": contrib.abs().mean().sort_values(ascending=False).to_dict(),
        "high_band_with_reasons_share": (
            float(np.mean([bool(s.reasons) for s in high])) if high else None
        ),
        "reason_code_share_high_band": (
            (codes.value_counts() / len(high)).to_dict() if len(high) else {}
        ),
    }
    section["_curves"] = {
        "y": eval_rows[TARGET].astype(int).to_numpy(),
        "p": p_eval,
        "shap": contrib,
    }
    return section, explainability


# --- segmentation ---------------------------------------------------------------------------


def _segment(
    model: SegmentModel, val: pd.DataFrame, test: pd.DataFrame, *, n_boot: int, seed: int
) -> dict[str, Any]:
    def window(part: pd.DataFrame) -> dict[str, Any] | str:
        if part.empty or part[segment.TARGET].nunique() < 2:
            return PENDING
        decided = model.score_frame(part)
        truth = part[segment.TARGET].to_numpy()
        pred = decided["segment"].to_numpy()
        out = classification_report(truth, pred)
        out["low_confidence_share"] = float(decided[segment.LOW_CONFIDENCE].mean())

        def stat(idx: npt.NDArray[np.int_]) -> dict[str, float]:
            return {"macro_f1": classification_report(truth[idx], pred[idx])["macro_f1"]}

        out["ci95"] = bootstrap_ci(stat, len(truth), n_boot=n_boot, seed=seed)
        return out

    return {
        "target": segment.TARGET,
        "model_version": model.model_version,
        "rule": {"wont_pay_min_confidence": segment.WONT_PAY_MIN_CONFIDENCE},
        "validation": window(val),
        "test": window(test),
    }


# --- uplift ---------------------------------------------------------------------------------


def _uplift(
    model: UpliftModel | None,
    ew: EarlyWarningModel,
    data: EvalData,
    simulate: uplift.SimulatePolicy | None,
) -> tuple[dict[str, Any] | str, dict[str, Any] | None, dict[str, Any] | None, dict[str, Any]]:
    if model is None:
        return PENDING, None, None, {}
    md = model.bundle.metadata
    section: dict[str, Any] = {
        "model_version": model.model_version,
        "learner": "T-learner (LightGBM), 3-fold cross-fitted evaluation",
        "tau": md["tau"],
        "cure_value_paise": md["cure_value_paise"],
        "arm_cost_paise": md["arm_cost_paise"],
        "evaluation_out_of_fold": md["evaluation_out_of_fold"],
        "policy": PENDING,
    }
    if data.experiment is None:
        return section, None, None, {}
    refit, oof = uplift.train_frames(
        data.experiment,
        data.features,
        seed=int(md["seed"]),
        tau=float(md["tau"]),
        cure_value_paise=int(md["cure_value_paise"]),
    )
    section["out_of_fold_matches_saved_model"] = refit.model_version == model.model_version
    exp = uplift.experiment_frame(data.experiment, data.features)
    curves = {
        "y": exp[uplift.OUTCOME].astype(int).to_numpy(),
        "treated": (exp["treatment"] != uplift.CONTROL).astype(int).to_numpy(),
        "uplift": oof["uplift_score"].to_numpy(),
    }
    if data.potential is None:
        return section, None, None, curves
    month = md["experiment_month"][0]
    rows = data.features[data.features["month"] == month]
    risk = pd.Series(ew.predict_proba(rows), index=rows["account_id"].to_numpy())
    try:
        result = uplift.simulate_strategies(oof, risk, data.potential, simulate=simulate)
    except RuntimeError as exc:
        section["policy"] = f"{PENDING}: {exc}"
        return section, None, None, curves
    policy = SimulationMetrics.model_validate(result["policy_simulation"]).model_dump(mode="json")
    strategies = _strategies(policy, result["strategies"], month)
    section["policy"] = {
        "npa_reduction_pct_vs_call_everyone": strategies["npa_reduction_pct"]["call_everyone"],
        "npa_reduction_pct_vs_risk_targeting": strategies["npa_reduction_pct"]["risk_targeting"],
        "see": ["policy_simulation.json", "policy_strategies.json"],
    }
    return section, policy, strategies, curves


def _reduction(base: Mapping[str, Any], ours: Mapping[str, Any]) -> float | None:
    b = float(base["npa_rate"])
    return round((b - float(ours["npa_rate"])) / b * 100, 2) if b > 0 else None


ROLES = {
    "call_everyone": ("baseline", "Call everyone at risk with an agent call."),
    "risk_targeting": (
        "comparison",
        "Agent calls to the highest-risk accounts, same number of contacts as ours.",
    ),
    "uplift_targeting": (
        "ours",
        "Contact only predicted persuadables, with the treatment worth its cost.",
    ),
    "oracle": (
        "upper_bound",
        "Uses the hidden true groups, which no real system has. An upper bound for "
        "comparison only, never our result.",
    ),
}


def _strategies(
    policy: Mapping[str, Any], runs: Mapping[str, Mapping[str, Any]], month: str
) -> dict[str, Any]:
    ours = runs["uplift_targeting"]
    return {
        "as_of_month": policy["as_of_month"],
        "experiment_month": month,
        "n_accounts": policy["n_accounts"],
        "horizon_days": policy["horizon_days"],
        "ours": "uplift_targeting",
        "upper_bound": "oracle",
        "strategies": {
            name: {**runs[name], "role": ROLES[name][0], "description": ROLES[name][1]}
            for name in ROLES
        },
        "npa_reduction_pct": {
            "call_everyone": _reduction(runs["call_everyone"], ours),
            "risk_targeting": _reduction(runs["risk_targeting"], ours),
        },
        "illustrative": policy["illustrative"],
        "source": "packages/models/reports/policy_strategies.json (npa-models evaluate)",
    }


# --- personas and fairness ------------------------------------------------------------------


def _personas(models: Models, as_of_rows: pd.DataFrame) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for account_id, check, expected in PERSONA_CHECKS:
        rows = as_of_rows[as_of_rows["account_id"] == account_id]
        actual: str | None = None
        if not rows.empty and check == "risk_band":
            actual = str(models.early_warning.score_frame(rows)["risk_band"].iloc[0])
        elif not rows.empty and check == "uplift_group" and models.uplift is not None:
            actual = str(models.uplift.score_frame(rows)["uplift_group"].iloc[0])
        status = "pass" if actual == expected else ("not_available" if actual is None else "fail")
        out.append(
            {
                "account_id": account_id,
                "check": check,
                "expected": expected,
                "actual": actual,
                "status": status,
            }
        )
    return out


def _fairness(
    models: Models, data: EvalData, eval_rows: pd.DataFrame, as_of_rows: pd.DataFrame
) -> tuple[dict[str, Any], dict[str, str]]:
    ew = models.early_warning
    p = ew.predict_proba(eval_rows)
    risk_rows = fairness.attach(
        pd.DataFrame(
            {
                "customer_id": eval_rows["customer_id"].to_numpy(),
                "y": eval_rows[TARGET].astype(bool).to_numpy(),
                "p": p,
                "high": ew.bands.bands(p) == RiskBand.HIGH.value,
            }
        ),
        data.protected,
    )
    seg = models.segment.score_frame(eval_rows)
    seg_rows = fairness.attach(
        pd.DataFrame(
            {
                "customer_id": eval_rows["customer_id"].to_numpy(),
                "truth": eval_rows[segment.TARGET].to_numpy(),
                "pred": seg["segment"].to_numpy(),
            }
        ),
        data.protected,
    )
    block: dict[str, Any] = {
        "early_warning": fairness.risk_fairness(risk_rows),
        "segment": fairness.segment_fairness(seg_rows),
    }
    population = {
        "early_warning": "evaluation-window account-months with labels",
        "segment": "evaluation-window account-months with labels",
    }
    if models.uplift is not None:
        bands = ew.score_frame(as_of_rows)["risk_band"].to_numpy()
        at_risk = as_of_rows[bands != RiskBand.LOW.value]
        up_rows = fairness.attach(
            pd.DataFrame(
                {
                    "customer_id": at_risk["customer_id"].to_numpy(),
                    "uplift_group": models.uplift.score_frame(at_risk)["uplift_group"].to_numpy(),
                }
            ),
            data.protected,
        )
        block["uplift"] = fairness.uplift_fairness(up_rows)
        population["uplift"] = "as-of-month accounts in the medium or high risk band"
    return block, population


# --- main entry points ----------------------------------------------------------------------


def evaluate(
    models: Models,
    data: EvalData,
    *,
    as_of_month: str,
    seed: int,
    split: TimeSplit = DEFAULT_SPLIT,
    n_boot: int | None = None,
    simulate: uplift.SimulatePolicy | None = None,
) -> Report:
    """Compute the whole evaluation report in memory (``n_boot`` defaults to :data:`N_BOOT`)."""
    n_boot = N_BOOT if n_boot is None else n_boot
    s = labelled_splits(data.features, data.labels, (TARGET, NPA_TARGET, segment.TARGET), split)
    final = _has_labels(s.test, TARGET)
    eval_rows = s.test if final else s.val
    as_of_rows = data.features[data.features["month"] == as_of_month]
    if as_of_rows.empty:
        raise ValueError(f"no feature rows for as_of_month={as_of_month}")

    ew_section, explainability = _early_warning(
        models.early_warning, s.val, s.test, eval_rows, as_of_rows, n_boot=n_boot, seed=seed
    )
    ew_curves = ew_section.pop("_curves")
    up_section, policy, strategies, up_curves = _uplift(
        models.uplift, models.early_warning, data, simulate
    )
    fair, population = _fairness(models, data, eval_rows, as_of_rows)
    versions = {"early_warning": models.early_warning.model_version}
    versions["segment"] = models.segment.model_version
    if models.uplift is not None:
        versions["uplift"] = models.uplift.model_version

    metrics: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_by": "npa-models evaluate",
        "as_of_month": as_of_month,
        "model_version": models.early_warning.model_version,
        "model_versions": versions,
        "data": {
            "split": split.__dict__,
            "evaluation_window": "test" if final else "validation",
            "test_status": "final" if final else PENDING,
            "rows": {"validation": len(s.val), "test": len(s.test), "as_of_month": len(as_of_rows)},
            "seed": seed,
            "bootstrap_resamples": n_boot,
        },
        "thresholds": {
            "fairness_max_diff": fairness.MAX_GAP,
            "fairness_min_ratio": fairness.MIN_RATIO,
            "fairness_min_group_size": fairness.MIN_GROUP_SIZE,
        },
        "early_warning": ew_section,
        "segment": _segment(models.segment, s.val, s.test, n_boot=n_boot, seed=seed),
        "uplift": up_section,
        "explainability": explainability,
        "personas": _personas(models, as_of_rows),
        "fairness": fair,
        "fairness_population": population,
        "fairness_flags": fairness.flags(fair),
    }
    curves = {"early_warning": ew_curves, "uplift": up_curves}
    log.info(
        "evaluation window=%s test_status=%s fairness_flags=%d",
        metrics["data"]["evaluation_window"],
        metrics["data"]["test_status"],
        len(metrics["fairness_flags"]),
    )
    return Report(jsonable(metrics), policy, strategies, curves)


def write_reports(report: Report, out_dir: Path, *, plots: bool = True) -> list[Path]:
    """Write ``metrics.json``, the policy files, the model cards and (optionally) the plots."""
    from npa_models import model_cards

    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    def dump(name: str, obj: Any) -> None:
        path = out_dir / name
        path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        written.append(path)

    dump("metrics.json", report.metrics)
    if report.policy_simulation is not None:
        dump("policy_simulation.json", report.policy_simulation)
    if report.policy_strategies is not None:
        dump("policy_strategies.json", jsonable(report.policy_strategies))
    for name, text in model_cards.render_all(report.metrics, report.policy_strategies).items():
        path = out_dir / name
        path.write_text(text, encoding="utf-8")
        written.append(path)
    if plots:
        from npa_models import plots as plotting

        written += plotting.write_plots(report.curves, out_dir)
    return written
