"""Task 2.5 evaluation report: metrics.json shape, pending test months, cards, plots, CLI."""

import copy
import json
import re
from pathlib import Path
from typing import Any

import pytest

from npa_contracts.api import SimulationMetrics
from npa_models import early_warning, evaluate, fairness, model_cards, segment, uplift
from npa_models.cli import EXIT_ERROR, EXIT_OK, main
from npa_models.evaluate import PENDING, EvalData, Models, jsonable, write_reports
from npa_models.metrics import bootstrap_ci

AS_OF = "2026-09"
N_BOOT = 20
README = Path(__file__).resolve().parents[1] / "reports" / "README.md"


@pytest.fixture(scope="module")
def models(fake_experiment) -> Models:
    d, e = fake_experiment.data, fake_experiment
    return Models(
        early_warning=early_warning.train_frames(d.features, d.labels, seed=42),
        segment=segment.train_frames(d.features, d.labels, seed=42),
        uplift=uplift.train_frames(e.experiment, d.features, seed=42)[0],
    )


@pytest.fixture(scope="module")
def small_models(fake_data) -> Models:
    """Early warning + segmentation on the 1,000-account fake data, for the fast paths."""
    return Models(
        early_warning=early_warning.train_frames(fake_data.features, fake_data.labels, seed=42),
        segment=segment.train_frames(fake_data.features, fake_data.labels, seed=42),
    )


@pytest.fixture(scope="module")
def report(models, fake_experiment, fake_sim) -> evaluate.Report:
    d, e = fake_experiment.data, fake_experiment
    data = EvalData(d.features, d.labels, d.protected, e.experiment, e.potential)
    return evaluate.evaluate(
        models, data, as_of_month=AS_OF, seed=42, n_boot=N_BOOT, simulate=fake_sim
    )


def _check_fairness_contract(block: dict[str, Any]) -> None:
    """What WS7's reader relies on (#106)."""
    for model, attrs in block.items():
        assert model in {"early_warning", "segment", "uplift"}
        assert set(attrs) == set(fairness.ATTRIBUTES)
        for b in attrs.values():
            numeric = {k for k in b if k.endswith(("_diff", "_ratio"))}
            assert numeric, model
            assert set(b) == numeric | {"flagged", "groups"}
            assert all(b[k] is None or 0 <= b[k] <= 1 for k in numeric)
            assert all(g["n"] > 0 for g in b["groups"].values())


def test_metrics_top_level_shape(report) -> None:
    m = report.metrics
    assert m["schema_version"] == 1
    assert isinstance(m["model_version"], str) and m["model_version"].startswith("ew-lgbm-")
    assert set(m["model_versions"]) == {"early_warning", "segment", "uplift"}
    assert m["data"]["evaluation_window"] == "test" and m["data"]["test_status"] == "final"
    assert m["thresholds"]["fairness_max_diff"] == 0.05
    assert m["thresholds"]["fairness_min_ratio"] == 0.8
    _check_fairness_contract(m["fairness"])
    assert set(m["fairness_population"]) == set(m["fairness"])
    json.dumps(m, allow_nan=False)  # strict JSON: no NaN


def test_readme_documents_every_key(report) -> None:
    text = README.read_text(encoding="utf-8")
    m = report.metrics
    keys = set(m) | set(m["data"]) | set(m["early_warning"]) | set(m["uplift"])
    for b in m["fairness"].values():
        for attr in b.values():
            keys |= set(attr) - {"flagged", "groups"}
            for g in attr["groups"].values():
                keys |= set(g)
    missing = sorted(k for k in keys if not re.search(rf"\b{re.escape(k)}\b", text))
    assert missing == []


def test_metrics_carry_confidence_intervals(report) -> None:
    rf = report.metrics["early_warning"]["test"]["roll_forward"]
    lo, hi = rf["ci95"]["roc_auc"]
    assert lo <= rf["roc_auc"] <= hi
    seg = report.metrics["segment"]["test"]
    assert seg["ci95"]["macro_f1"][0] <= seg["macro_f1"] <= seg["ci95"]["macro_f1"][1]
    rob = report.metrics["early_warning"]["robustness"]
    assert set(rob) == {"feature_noise_10pct", "salary_data_missing"}


def test_personas_pass(report) -> None:
    status = {(p["account_id"], p["check"]): p["status"] for p in report.metrics["personas"]}
    assert status == {
        ("ACC-DEMO-PRIYA", "risk_band"): "pass",
        ("ACC-DEMO-RAVI", "risk_band"): "pass",
        ("ACC-DEMO-PRIYA", "uplift_group"): "pass",
    }


def test_policy_reports(report) -> None:
    SimulationMetrics.model_validate(report.policy_simulation)
    s = report.policy_strategies
    assert s is not None
    assert list(s["strategies"]) == [
        "call_everyone",
        "risk_targeting",
        "uplift_targeting",
        "oracle",
    ]
    assert s["ours"] == "uplift_targeting" and s["upper_bound"] == "oracle"
    assert s["strategies"]["oracle"]["role"] == "upper_bound"
    # The headline is ours, never the oracle.
    ours = s["strategies"]["uplift_targeting"]
    assert report.policy_simulation["ours"]["npa_rate"] == ours["npa_rate"]
    assert report.metrics["uplift"]["out_of_fold_matches_saved_model"] is True


def test_test_months_pending_without_labels(small_models, fake_data) -> None:
    labels = fake_data.labels[fake_data.labels["month"] <= "2026-06"]  # WS1's label horizon
    data = EvalData(fake_data.features, labels, fake_data.protected)
    m = evaluate.evaluate(small_models, data, as_of_month=AS_OF, seed=42, n_boot=N_BOOT).metrics
    assert m["data"] == m["data"] | {"evaluation_window": "validation", "test_status": PENDING}
    heads = ("roll_forward", "npa_90d", "baseline")
    assert m["early_warning"]["test"] == dict.fromkeys(heads, PENDING)
    assert m["segment"]["test"] == PENDING
    cards = model_cards.render_all(m, None)
    assert "Test months (2026-07..09): pending" in cards["model_card_early_warning.md"]
    assert "Pending: no uplift model" in cards["model_card_uplift.md"]


def test_uplift_pending_without_model(small_models, fake_data) -> None:
    data = EvalData(fake_data.features, fake_data.labels, fake_data.protected)
    m = evaluate.evaluate(small_models, data, as_of_month=AS_OF, seed=42, n_boot=N_BOOT).metrics
    assert m["uplift"] == PENDING
    assert "uplift" not in m["fairness"]
    assert {p["status"] for p in m["personas"] if p["check"] == "uplift_group"} == {"not_available"}


def test_policy_pending_without_potential_outcomes(models, fake_experiment) -> None:
    d, e = fake_experiment.data, fake_experiment
    up, policy, strategies, curves = evaluate._uplift(
        models.uplift,
        models.early_warning,
        EvalData(d.features, d.labels, d.protected, e.experiment),
        None,
    )
    assert isinstance(up, dict) and up["policy"] == PENDING
    assert policy is None and strategies is None and set(curves) == {"y", "treated", "uplift"}


def test_unknown_as_of_month(small_models, fake_data) -> None:
    data = EvalData(fake_data.features, fake_data.labels, fake_data.protected)
    with pytest.raises(ValueError, match="2030-01"):
        evaluate.evaluate(small_models, data, as_of_month="2030-01", seed=42)


def test_write_reports(tmp_path: Path, report) -> None:
    written = {p.name for p in write_reports(report, tmp_path)}
    assert {
        "metrics.json",
        "policy_simulation.json",
        "policy_strategies.json",
        "model_card_early_warning.md",
        "model_card_segment.md",
        "model_card_uplift.md",
        "roc_early_warning.png",
        "pr_early_warning.png",
        "calibration_early_warning.png",
        "shap_summary_early_warning.png",
        "qini_uplift.png",
    } == written
    on_disk = json.loads((tmp_path / "metrics.json").read_text(encoding="utf-8"))
    assert on_disk == report.metrics
    card = (tmp_path / "model_card_uplift.md").read_text(encoding="utf-8")
    assert "upper bound only, never our result" in card
    for name in ("model_card_early_warning.md", "model_card_segment.md", "model_card_uplift.md"):
        text = (tmp_path / name).read_text(encoding="utf-8")
        for heading in ("Intended use", "Data", "Metrics", "Limitations", "Explainability"):
            assert f"## {heading}" in text, (name, heading)
        assert "## Robustness" in text and "## Fairness" in text and "## Monitoring plan" in text
        assert "## Owner" in text and "not certification" in text


def test_write_reports_without_plots_or_policy(tmp_path: Path, report) -> None:
    bare = evaluate.Report(metrics=report.metrics)
    names = {p.name for p in write_reports(bare, tmp_path, plots=False)}
    assert "policy_simulation.json" not in names and not any(n.endswith(".png") for n in names)


def test_jsonable_and_bootstrap() -> None:
    import numpy as np

    assert jsonable({"a": np.float64(0.123456), "b": [np.int64(3), float("nan")], "c": True}) == {
        "a": 0.1235,
        "b": [3, None],
        "c": True,
    }
    assert bootstrap_ci(lambda idx: {"x": float(len(idx))}, 5, n_boot=10, seed=1) == {
        "x": [5.0, 5.0]
    }

    def always_fails(idx: Any) -> dict[str, float]:
        raise ValueError("one class")

    assert bootstrap_ci(always_fails, 5, n_boot=3, seed=1) == {}
    with pytest.raises(ValueError, match="n_boot"):
        bootstrap_ci(always_fails, 0, n_boot=3, seed=1)


# --- CLI ------------------------------------------------------------------------------------


def _write_inputs(tmp_path: Path, data: Any, experiment: Any = None) -> dict[str, Path]:
    frames = {"features": data.features, "labels": data.labels, "protected": data.protected}
    if experiment is not None:
        frames |= {"experiment": experiment.experiment, "potential": experiment.potential}
    paths = {name: tmp_path / f"{name}.parquet" for name in frames}
    for name, frame in frames.items():
        frame.to_parquet(paths[name])
    return paths


def test_cli_evaluate_end_to_end(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fake_experiment
) -> None:
    paths = _write_inputs(tmp_path, fake_experiment.data, fake_experiment)
    monkeypatch.setenv("MODEL_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setattr(evaluate, "N_BOOT", N_BOOT)

    def unavailable() -> Any:
        raise RuntimeError("datagen.experiment.simulate_policy is not available yet")

    monkeypatch.setattr(uplift, "default_simulate_policy", unavailable)
    train = ["train", "--all", *(f"--{n}={paths[n]}" for n in ("features", "labels", "experiment"))]
    assert main(train) == EXIT_OK
    out = tmp_path / "reports"
    argv = ["evaluate", "--no-plots", f"--out={out}", *(f"--{n}={p}" for n, p in paths.items())]
    assert main(argv) == EXIT_OK
    m = json.loads((out / "metrics.json").read_text(encoding="utf-8"))
    assert m["uplift"]["policy"].startswith(PENDING)
    assert m["uplift"]["out_of_fold_matches_saved_model"] is True
    assert not (out / "policy_simulation.json").exists()


def test_cli_evaluate_without_uplift_or_experiment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fake_data
) -> None:
    paths = _write_inputs(tmp_path, fake_data)
    monkeypatch.setenv("MODEL_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setattr(evaluate, "N_BOOT", N_BOOT)
    train = ["train", f"--features={paths['features']}", f"--labels={paths['labels']}"]
    assert main(train) == EXIT_OK
    out = tmp_path / "reports"
    argv = [
        "evaluate",
        "--no-plots",
        f"--out={out}",
        f"--features={paths['features']}",
        f"--labels={paths['labels']}",
        f"--protected={paths['protected']}",
        f"--experiment={tmp_path / 'none.parquet'}",
        f"--potential={tmp_path / 'none.parquet'}",
    ]
    assert main(argv) == EXIT_OK
    assert json.loads((out / "metrics.json").read_text(encoding="utf-8"))["uplift"] == PENDING


def test_cli_evaluate_needs_inputs_and_models(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fake_data
) -> None:
    paths = _write_inputs(tmp_path, fake_data)
    monkeypatch.setenv("MODEL_DIR", str(tmp_path / "no-models"))
    base = [f"--features={paths['features']}", f"--labels={paths['labels']}"]
    assert main(["evaluate", *base, f"--protected={tmp_path / 'missing.parquet'}"]) == EXIT_ERROR
    assert main(["evaluate", *base, f"--protected={paths['protected']}"]) == EXIT_ERROR


def test_fairness_groups_cover_the_population(report) -> None:
    # Group sizes add up to the evaluated population for every attribute.
    ew = report.metrics["fairness"]["early_warning"]
    totals = {sum(g["n"] for g in b["groups"].values()) for b in ew.values()}
    assert totals == {report.metrics["data"]["rows"]["test"]}


# --- edge paths -----------------------------------------------------------------------------


def test_single_class_window_is_pending() -> None:
    assert evaluate._with_ci([0, 0, 0], [0.1, 0.2, 0.3], n_boot=5, seed=1) == PENDING


def test_uplift_section_without_experiment(models, fake_experiment) -> None:
    d = fake_experiment.data
    data = EvalData(d.features, d.labels, d.protected)
    up, policy, strategies, curves = evaluate._uplift(
        models.uplift, models.early_warning, data, None
    )
    assert isinstance(up, dict) and up["policy"] == PENDING
    assert "out_of_fold_matches_saved_model" not in up
    assert (policy, strategies, curves) == (None, None, {})


def test_cards_render_pending_and_missing_parts(report) -> None:
    m = copy.deepcopy(report.metrics)
    window = m["data"]["evaluation_window"]
    m["early_warning"][window]["npa_90d"] = PENDING
    m["early_warning"]["suggested_high_threshold_6_5pct"] = None
    m["segment"][window] = PENDING
    del m["fairness"]["segment"]
    cards = model_cards.render_all(m, None)
    ew = cards["model_card_early_warning.md"]
    assert "| npa_90d | pending |" in ew and "6.5% high band: n/a" in ew
    seg = cards["model_card_segment.md"]
    assert "Pending." in seg and "Not evaluated." in seg
    assert "Pending: needs WS1's experiment" in cards["model_card_uplift.md"]


def test_plots_skip_what_the_curves_cannot_show(tmp_path: Path) -> None:
    import numpy as np

    from npa_models import plots

    assert plots.write_plots({}, tmp_path) == []
    one_class = {"early_warning": {"y": np.zeros(5), "p": np.full(5, 0.1)}}
    assert plots.write_plots(one_class, tmp_path) == []
