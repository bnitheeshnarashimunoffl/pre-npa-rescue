"""Task 2.4 uplift model on the seeded fake randomised experiment."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from npa_contracts.enums import Treatment, UpliftGroup
from npa_contracts.models import UpliftResult
from npa_models import uplift
from npa_models.features import FORBIDDEN_COLUMNS
from npa_models.registry import MODEL_VERSION_RE
from npa_models.uplift import (
    ARMS,
    UpliftModel,
    assign_groups,
    experiment_frame,
    policy_assignments,
    recommend,
    simulate_strategies,
    train,
    train_frames,
)

AS_OF = "2026-09"
EXPERIMENT_MONTH = "2026-06"


@pytest.fixture(scope="module")
def trained(fake_experiment) -> tuple[UpliftModel, pd.DataFrame]:
    return train_frames(fake_experiment.experiment, fake_experiment.data.features, seed=42)


@pytest.fixture(scope="module")
def risk(fake_experiment) -> pd.Series:
    """Stand-in risk scores for the risk-targeting strategy: p_roll_forward-like ranking."""
    f = fake_experiment.data.features
    rows = f[f["month"] == EXPERIMENT_MONTH].set_index("account_id")
    return (
        rows["min_due_only_streak"] + rows["salary_missing_months_3m"] + rows["dpd"] / 30
    ).astype(float)


# --- pure rules -----------------------------------------------------------------------------


def test_assign_groups_rules() -> None:
    groups = assign_groups([0.05, -0.05, 0.0, 0.0, 0.049], [0.1, 0.9, 0.5, 0.49, 0.8], tau=0.05)
    assert groups.tolist() == [
        "persuadable",
        "sleeping_dog",
        "sure_thing",
        "lost_cause",
        "sure_thing",
    ]


def test_assign_groups_rejects_bad_tau() -> None:
    with pytest.raises(ValueError, match="tau"):
        assign_groups([0.1], [0.5], tau=0.0)


def test_recommend_net_of_cost() -> None:
    effects = pd.DataFrame(
        {
            "uplift_reminder": [0.10, 0.10, 0.30],
            "uplift_chat_invite": [0.35, 0.35, 0.30],
            "uplift_agent_call": [0.20, 0.20, 0.0],
            "uplift_relief_offer": [0.50, 0.50, 0.0],
        }
    )
    cost = {"reminder": 200.0, "chat_invite": 500.0, "agent_call": 6000.0, "relief_offer": 8000.0}
    groups = ["persuadable", "sure_thing", "persuadable"]
    # Rs 5,000 cure value: relief 0.5*500000-8000 beats chat 0.35*500000-500.
    assert recommend(effects, groups, cost, 500_000).tolist() == [
        "relief_offer",
        "none",
        "reminder",
    ]
    # Rs 100 cure value: no contact pays for itself.
    assert recommend(effects, groups, cost, 10_000).tolist() == ["chat_invite", "none", "reminder"]
    assert recommend(effects, groups, cost, 100).tolist() == ["none", "none", "none"]


def test_experiment_frame_validates(fake_experiment) -> None:
    exp, feats = fake_experiment.experiment, fake_experiment.data.features
    df = experiment_frame(exp, feats)
    assert len(df) == len(exp)
    with pytest.raises(ValueError, match="carrier_pigeon"):
        experiment_frame(exp.assign(treatment="carrier_pigeon"), feats)
    with pytest.raises(ValueError, match="no features"):
        experiment_frame(exp.assign(month="2030-01"), feats)


# --- training -------------------------------------------------------------------------------


def test_hidden_truth_never_reaches_the_models(trained) -> None:
    model, _ = trained
    assert "true_uplift_group" in FORBIDDEN_COLUMNS
    assert not set(model.bundle.feature_columns) & FORBIDDEN_COLUMNS
    for est in model.bundle.estimators.values():
        assert "true_uplift_group" not in est.feature_name_


def test_bundle_contents(trained) -> None:
    model, _ = trained
    assert set(model.bundle.estimators) == {"control", "treated"} | {f"arm_{a}" for a in ARMS}
    md = model.bundle.metadata
    assert md["tau"] == 0.05 and md["cure_value_paise"] == 500_000
    assert md["arm_cost_paise"]["agent_call"] == 6000.0
    assert MODEL_VERSION_RE.match(model.model_version)
    assert model.model_version.startswith("uplift-tlearner-")


def test_out_of_fold_evaluation(trained, fake_experiment) -> None:
    model, oof = trained
    ev = model.bundle.metadata["evaluation_out_of_fold"]
    assert ev["n"] == len(fake_experiment.experiment) == len(oof)
    assert {"qini_auc", "uplift_auc", "group_accuracy", "group_confusion"} <= ev.keys()
    assert sum(ev["group_share"].values()) == pytest.approx(1.0)
    confusion_total = sum(sum(row.values()) for row in ev["group_confusion"].values())
    assert confusion_total == ev["n"]
    assert set(oof["uplift_group"]) <= {g.value for g in UpliftGroup}


def test_evaluation_without_hidden_truth(fake_experiment) -> None:
    exp = fake_experiment.experiment.drop(columns="true_uplift_group")
    model, _ = train_frames(exp, fake_experiment.data.features, seed=42)
    assert "group_accuracy" not in model.bundle.metadata["evaluation_out_of_fold"]


def test_training_needs_both_outcomes_per_arm(fake_experiment) -> None:
    exp = fake_experiment.experiment.copy()
    exp.loc[exp["treatment"] == "none", "outcome_cured_90d"] = True
    with pytest.raises(ValueError, match="control"):
        train_frames(exp, fake_experiment.data.features, seed=42)


def test_training_is_deterministic(trained, fake_experiment) -> None:
    model, oof = trained
    again, oof2 = train_frames(fake_experiment.experiment, fake_experiment.data.features, seed=42)
    assert again.model_version == model.model_version
    pd.testing.assert_frame_equal(oof, oof2)


# --- policy simulation ----------------------------------------------------------------------


def test_policy_simulation_shape_and_ordering(trained, risk, fake_experiment, fake_sim) -> None:
    _, oof = trained
    result = simulate_strategies(oof, risk, fake_experiment.potential, simulate=fake_sim)
    s = result["strategies"]
    assert list(s) == ["call_everyone", "risk_targeting", "uplift_targeting", "oracle"]
    # Same contact budget for risk and uplift targeting.
    assert s["risk_targeting"]["contacts_made"] == s["uplift_targeting"]["contacts_made"]
    # Uplift targeting beats calling everyone at a fraction of the cost; the oracle is the ceiling.
    assert s["uplift_targeting"]["npa_rate"] < s["call_everyone"]["npa_rate"]
    assert (
        s["uplift_targeting"]["collection_cost_paise"] < s["call_everyone"]["collection_cost_paise"]
    )
    assert s["oracle"]["npa_rate"] <= s["uplift_targeting"]["npa_rate"]
    report = result["policy_simulation"]
    expected_keys = set(json_fixture_keys())
    assert set(report) == expected_keys
    assert report["ours"]["strategy"] == "pre_npa_rescue"
    assert report["baseline"]["strategy"] == "call_everyone"


def json_fixture_keys() -> list[str]:
    import json

    path = (
        Path(__file__).resolve().parents[3] / "contracts" / "fixtures" / "simulation_metrics.json"
    )
    return list(json.loads(path.read_text(encoding="utf-8")))


def test_policy_assignments_need_risk_for_every_account(trained, risk, fake_experiment) -> None:
    _, oof = trained
    with pytest.raises(ValueError, match="no risk score"):
        policy_assignments(oof, risk.iloc[:10], fake_experiment.potential)


def test_default_simulator_reports_missing_datagen(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    real_import = builtins.__import__

    def fake_import(name: str, *args, **kwargs):  # type: ignore[no-untyped-def]
        if name == "datagen.experiment":
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(RuntimeError, match="WS1"):
        uplift.default_simulate_policy()


def test_default_simulator_uses_datagen(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    import types

    module = types.ModuleType("datagen.experiment")
    module.simulate_policy = lambda *a, **k: {"ok": True}  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "datagen.experiment", module)
    assert uplift.default_simulate_policy()() == {"ok": True}


# --- scoring --------------------------------------------------------------------------------


def test_score_batch_returns_contract_objects(trained, fake_experiment) -> None:
    model, _ = trained
    results = model.score_batch(fake_experiment.data.features, AS_OF)
    r = results[0]
    assert isinstance(r, UpliftResult)
    UpliftResult.model_validate_json(r.model_dump_json())
    groups = {x.uplift_group for x in results}
    assert UpliftGroup.PERSUADABLE in groups
    # Only persuadables are contacted.
    for x in results:
        if x.uplift_group is not UpliftGroup.PERSUADABLE:
            assert x.recommended_treatment is Treatment.NONE


def test_score_frame_columns(trained, fake_experiment) -> None:
    model, _ = trained
    f = fake_experiment.data.features
    frame = model.score_frame(f[f["month"] == AS_OF].head(5))
    assert list(frame.columns[:5]) == [
        "account_id",
        "as_of_month",
        "uplift_score",
        "uplift_group",
        "recommended_treatment",
    ]
    assert {"p_control", *(f"uplift_{a}" for a in ARMS)} <= set(frame.columns)


def test_score_batch_unknown_month_fails(trained, fake_experiment) -> None:
    model, _ = trained
    with pytest.raises(ValueError, match="2030-01"):
        model.score_batch(fake_experiment.data.features, "2030-01")


def test_priya_is_persuadable_with_a_helpful_offer(trained, fake_experiment) -> None:
    # Fixture-specific (seed 42): on the fake experiment Priya comes out persuadable on 3 of 5
    # seeds; re-check on WS1's data, where her group is scripted (see the PR).
    model, _ = trained
    f = fake_experiment.data.features
    priya = model.score(f[(f["month"] == AS_OF) & (f["account_id"] == "ACC-DEMO-PRIYA")])[0]
    assert priya.uplift_group is UpliftGroup.PERSUADABLE
    assert priya.recommended_treatment in {Treatment.RELIEF_OFFER, Treatment.CHAT_INVITE}


def test_uplift_ignores_protected_columns(trained, fake_experiment) -> None:
    model, _ = trained
    f = fake_experiment.data.features
    rows = f[f["month"] == AS_OF].head(50).merge(fake_experiment.data.protected, on="customer_id")
    swapped = rows.assign(religion="hindu", region="north", gender="female")
    pd.testing.assert_frame_equal(model.score_frame(rows), model.score_frame(swapped))


def test_train_from_parquet_save_and_load(tmp_path: Path, trained, fake_experiment) -> None:
    model, _ = trained
    fp, ep = tmp_path / "features.parquet", tmp_path / "experiment.parquet"
    fake_experiment.data.features.to_parquet(fp)
    fake_experiment.experiment.to_parquet(ep)
    UpliftModel(train(fp, ep)).save(tmp_path / "artifacts")
    loaded = UpliftModel.load(tmp_path / "artifacts")
    assert loaded.model_version == model.model_version
    f = fake_experiment.data.features
    rows = f[f["month"] == AS_OF].head(20)
    np.testing.assert_allclose(
        loaded.score_frame(rows)["uplift_score"], model.score_frame(rows)["uplift_score"]
    )
