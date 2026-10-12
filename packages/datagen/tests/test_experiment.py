"""Experiment simulator and simulate_policy (task 1.3 acceptance)."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from datagen.config import DatagenConfig
from datagen.experiment import (
    COST_RUPEES,
    CURE_BASE,
    CURE_LIFT,
    TREATMENTS,
    build_experiment,
    cure_probability,
    oracle_policy,
    random_policy,
    run_experiment,
    simulate_policy,
)
from datagen.generate import GeneratedData, build
from datagen.labels import build_labels
from datagen.pipeline import run_features
from datagen.validate import validate
from npa_contracts.api import SimulationMetrics

FIXTURE = Path(__file__).resolve().parents[3] / "contracts" / "fixtures" / "simulation_metrics.json"


def _experiment(data: GeneratedData, seed: int = 42) -> tuple[pd.DataFrame, pd.DataFrame]:
    labels = build_labels(data.account_months, data.shocks, data.behaviour)
    return build_experiment(
        labels, data.account_months, data.shocks, data.behaviour, "2026-06", seed
    )


@pytest.fixture(scope="module")
def big(tmp_path_factory: pytest.TempPathFactory) -> tuple[pd.DataFrame, pd.DataFrame]:
    """A population large enough for the acceptance comparison (~600 at-risk accounts)."""
    cfg = DatagenConfig(seed=42, n_customers=4_000, data_dir=tmp_path_factory.mktemp("exp"))
    return _experiment(build(cfg))


def test_experiment_table_matches_contract(big: tuple[pd.DataFrame, pd.DataFrame]) -> None:
    experiment, _ = big
    validate(experiment, "experiment")
    assert experiment["month"].eq("2026-06").all()
    assert experiment["account_id"].is_unique


def test_treatments_split_exactly_20_percent(big: tuple[pd.DataFrame, pd.DataFrame]) -> None:
    counts = big[0]["treatment"].value_counts()
    assert set(counts.index) == set(TREATMENTS)
    assert counts.max() - counts.min() <= 1


def test_observed_outcomes_follow_potential(big: tuple[pd.DataFrame, pd.DataFrame]) -> None:
    experiment, potential = big
    m = experiment.merge(potential, on="account_id")
    for t in TREATMENTS:
        arm = m[m["treatment"] == t]
        assert (arm["outcome_cured_90d"] == arm[f"cured_{t}"]).all()
        assert (arm["contact_cost_paise"] == arm[f"cost_{t}"]).all()
    assert not (experiment["outcome_cured_90d"] & experiment["outcome_npa_90d"]).any()


def test_costs(big: tuple[pd.DataFrame, pd.DataFrame]) -> None:
    _, potential = big
    for t in ("none", "reminder", "chat_invite", "agent_call"):
        assert (potential[f"cost_{t}"] == COST_RUPEES[t] * 100).all()
    assert (potential["cost_relief_offer"] >= 8_000).all()  # Rs 80 plus the waiver
    assert (potential["cost_relief_offer"] > 8_000).any()


def test_oracle_beats_call_everyone_and_random_does_not(
    big: tuple[pd.DataFrame, pd.DataFrame],
) -> None:
    """Task 1.3 acceptance: the simulator has signal for WS2 to find."""
    _, potential = big
    oracle = simulate_policy(oracle_policy(potential), potential=potential)
    assert oracle["ours"]["npa_rate"] < oracle["baseline"]["npa_rate"]
    assert oracle["npa_reduction_pct"] >= 5.0
    assert (
        oracle["ours"]["collection_cost_paise"] < 0.2 * oracle["baseline"]["collection_cost_paise"]
    )

    contacts = oracle["ours"]["contacts_made"]
    rand = simulate_policy(
        random_policy(potential, contacts, "chat_invite", seed=1), potential=potential
    )
    assert rand["ours"]["collection_cost_paise"] == oracle["ours"]["collection_cost_paise"]
    assert rand["npa_reduction_pct"] < 2.0  # no clear win over calling everyone
    assert rand["ours"]["npa_rate"] > oracle["ours"]["npa_rate"]


def test_simulate_policy_matches_fixture_shape(big: tuple[pd.DataFrame, pd.DataFrame]) -> None:
    _, potential = big
    out = simulate_policy(oracle_policy(potential), potential=potential)
    SimulationMetrics.model_validate(out)
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert set(out) == set(fixture)
    assert set(out["ours"]) == set(fixture["ours"])
    assert out["as_of_month"] == "2026-06" and out["horizon_days"] == 90


def test_empty_policy_is_no_contact(big: tuple[pd.DataFrame, pd.DataFrame]) -> None:
    _, potential = big
    out = simulate_policy(pd.DataFrame(columns=["account_id", "treatment"]), potential=potential)
    assert out["ours"]["contacts_made"] == 0
    assert out["ours"]["collection_cost_paise"] == 0


def test_simulate_policy_rejects_bad_input(big: tuple[pd.DataFrame, pd.DataFrame]) -> None:
    _, potential = big
    acc = potential["account_id"].iloc[0]
    with pytest.raises(ValueError, match="unknown treatment"):
        simulate_policy(
            pd.DataFrame({"account_id": [acc], "treatment": ["sms"]}), potential=potential
        )
    with pytest.raises(ValueError, match="not in the experiment"):
        simulate_policy(
            pd.DataFrame({"account_id": ["ACC-NOPE"], "treatment": ["reminder"]}),
            potential=potential,
        )
    with pytest.raises(ValueError, match="duplicate"):
        simulate_policy(
            pd.DataFrame({"account_id": [acc, acc], "treatment": ["reminder", "none"]}),
            potential=potential,
        )


def test_deterministic(small_data: GeneratedData) -> None:
    a, _ = _experiment(small_data, seed=5)
    b, _ = _experiment(small_data, seed=5)
    pd.testing.assert_frame_equal(a, b)


def test_personas_keep_scripted_groups(small_data: GeneratedData) -> None:
    experiment, _ = _experiment(small_data)
    groups = experiment.set_index("customer_id")["true_uplift_group"]
    assert groups["CUST-DEMO-PRIYA"] == "persuadable"
    assert "CUST-DEMO-JOSEPH" not in groups.index  # not at risk: not in the experiment


def test_probability_tables_are_valid() -> None:
    for g in CURE_BASE:
        probs = [cure_probability(g, t) for t in TREATMENTS]
        assert all(0.0 <= p <= 1.0 for p in probs)
        assert set(CURE_LIFT[g]) == set(TREATMENTS)
    # Sleeping dogs get worse with any contact; persuadables gain most.
    assert all(CURE_LIFT["sleeping_dog"][t] < 0 for t in TREATMENTS if t != "none")
    assert max(CURE_LIFT["persuadable"].values()) > max(CURE_LIFT["sure_thing"].values())


def test_month_without_labels_fails(small_data: GeneratedData) -> None:
    labels = build_labels(small_data.account_months, small_data.shocks, small_data.behaviour)
    with pytest.raises(ValueError, match="horizon"):
        build_experiment(
            labels,
            small_data.account_months,
            small_data.shocks,
            small_data.behaviour,
            "2026-09",
            42,
        )


def test_run_experiment_cli_step(small_written: Path, small_cfg: DatagenConfig) -> None:
    run_features(small_cfg)
    run_experiment(small_cfg)
    exp = pd.read_parquet(small_written / "experiment.parquet")
    validate(exp, "experiment")
    out = simulate_policy(exp[["account_id"]].assign(treatment="reminder"), data_dir=small_written)
    assert out["ours"]["contacts_made"] == len(exp)
    assert np.isclose(out["ours"]["collection_cost_paise"], 200 * len(exp))
