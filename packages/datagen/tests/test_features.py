"""Feature pipeline: exact contract columns, no look-ahead, no protected/hidden columns."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from datagen.features import FEATURE_COLUMNS, build_features, rolling_sum, since_last, streak
from datagen.generate import GeneratedData
from datagen.labels import build_labels
from datagen.validate import table_spec, validate

SAMPLES = Path(__file__).resolve().parents[3] / "data" / "samples"


@pytest.fixture(scope="module")
def features(small_data: GeneratedData) -> pd.DataFrame:
    d = small_data
    return build_features(d.customers, d.account_months, d.monthly_spend, d.salary)


@pytest.fixture(scope="module")
def labels(small_data: GeneratedData) -> pd.DataFrame:
    return build_labels(small_data.account_months, small_data.shocks, small_data.behaviour)


def test_columns_match_contract_exactly(features: pd.DataFrame) -> None:
    assert tuple(features.columns) == FEATURE_COLUMNS
    assert tuple(s.name for s in table_spec("features")) == FEATURE_COLUMNS
    validate(features, "features")


def test_no_protected_or_hidden_columns(features: pd.DataFrame, small_data: GeneratedData) -> None:
    keys = {"customer_id", "account_id", "month"}
    for hidden in (small_data.protected, small_data.shocks, small_data.behaviour):
        assert not (set(features.columns) & set(hidden.columns)) - keys


@pytest.mark.parametrize("cut", ["2025-03", "2025-11", "2026-06"])
def test_no_look_ahead(small_data: GeneratedData, features: pd.DataFrame, cut: str) -> None:
    """Features at month <= cut are identical when computed from data truncated at cut."""
    d = small_data
    trunc = build_features(
        d.customers,
        d.account_months[d.account_months["month"] <= cut],
        d.monthly_spend[d.monthly_spend["month"] <= cut],
        d.salary[d.salary["month"] <= cut],
    )
    full = features[features["month"] <= cut].reset_index(drop=True)
    pd.testing.assert_frame_equal(trunc, full)


def test_feature_sanity(features: pd.DataFrame) -> None:
    f = features
    assert (f["max_dpd_6m"] >= f["dpd"]).all()
    assert f["payment_ratio_3m"].between(0, 10).all()
    assert f["cash_advance_ratio_3m"].between(0, 1).all()
    assert f["salary_missing_months_3m"].between(0, 3).all()
    assert (f["tenure_months"] >= 6).all()
    first = f["month"] == "2024-10"
    assert (f.loc[first, "utilisation_delta_3m"] == 0).all()  # too little history -> 0.0
    assert f.notna().all().all()  # contract columns are non-nullable


def test_labels(labels: pd.DataFrame, small_data: GeneratedData) -> None:
    validate(labels, "labels")
    assert labels["month"].max() == "2026-06"  # 3-month horizon inside the window
    assert len(labels) == len(small_data.customers) * 21
    assert labels["rolls_forward_60d"].any()
    assert set(labels["segment_truth"]) <= {"forgot", "cant_pay", "wont_pay", "not_at_risk"}
    # Already-NPA accounts that stay NPA are reaches_npa_90d.
    am = small_data.account_months.merge(labels, on=["account_id", "month"])
    npa_now = am["bucket"] == "npa"
    assert am.loc[npa_now, "reaches_npa_90d"].mean() > 0.9


def test_leading_indicators_precede_misses(features: pd.DataFrame, labels: pd.DataFrame) -> None:
    """Accounts about to roll forward already look worse on the leading features."""
    m = features.merge(labels, on=["account_id", "month"])
    current = m[m["dpd"] == 0]
    roll, stay = current[current["rolls_forward_60d"]], current[~current["rolls_forward_60d"]]
    assert roll["min_due_only_streak"].mean() > stay["min_due_only_streak"].mean()
    assert roll["payment_ratio_3m"].mean() < stay["payment_ratio_3m"].mean()


def test_helpers() -> None:
    flag = np.array([[True, True, False, True]])
    assert streak(flag).tolist() == [[1, 2, 0, 1]]
    assert since_last(np.array([[False, True, False, False]])).tolist() == [[1, 0, 1, 2]]
    assert rolling_sum(np.array([[1.0, 2.0, 3.0, 4.0]]), 2).tolist() == [[1, 3, 5, 7]]


def test_rejects_ragged_panel(small_data: GeneratedData) -> None:
    d = small_data
    with pytest.raises(ValueError, match="panel"):
        build_features(d.customers, d.account_months.iloc[1:], d.monthly_spend, d.salary)


@pytest.mark.skipif(not (SAMPLES / "features_sample.parquet").exists(), reason="no samples")
def test_committed_samples_match_contract() -> None:
    f = pd.read_parquet(SAMPLES / "features_sample.parquet")
    lb = pd.read_parquet(SAMPLES / "labels_sample.parquet")
    validate(f, "features")
    validate(lb, "labels")
    assert 1_500 <= len(f) <= 2_500
    pd.testing.assert_frame_equal(f[["account_id", "month"]], lb[["account_id", "month"]])
