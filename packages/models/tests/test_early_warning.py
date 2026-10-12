"""Task 2.1 early-warning model on the seeded fake data."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from npa_contracts.enums import RiskBand
from npa_contracts.models import RiskScore
from npa_models.early_warning import (
    MONOTONE,
    EarlyWarningModel,
    RiskBands,
    threshold_for_share,
    train,
    train_frames,
)
from npa_models.features import TimeSplit, build_matrix
from npa_models.metrics import binary_metrics, ks_statistic
from npa_models.registry import MODEL_VERSION_RE

AS_OF = "2026-09"


@pytest.fixture(scope="module")
def model(fake_data) -> EarlyWarningModel:
    return train_frames(fake_data.features, fake_data.labels, seed=42)


def _as_of(fake_data) -> pd.DataFrame:
    return fake_data.features[fake_data.features["month"] == AS_OF]


# --- risk bands -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("p", "band"),
    [
        (0.0, RiskBand.LOW),
        (0.1499, RiskBand.LOW),
        (0.15, RiskBand.MEDIUM),
        (0.3499, RiskBand.MEDIUM),
        (0.35, RiskBand.HIGH),
        (1.0, RiskBand.HIGH),
    ],
)
def test_default_band_edges(p: float, band: RiskBand) -> None:
    assert RiskBands().band(p) is band
    assert RiskBands().bands([p])[0] == band.value


@pytest.mark.parametrize(("high", "medium"), [(0.1, 0.2), (0.3, 0.3), (1.0, 0.2), (0.3, 0.0)])
def test_bands_reject_bad_thresholds(high: float, medium: float) -> None:
    with pytest.raises(ValueError):
        RiskBands(high=high, medium=medium)


def test_threshold_for_share() -> None:
    p = np.linspace(0, 1, 1001)
    assert threshold_for_share(p, 0.1) == pytest.approx(0.9)
    with pytest.raises(ValueError):
        threshold_for_share(p, 0.0)


# --- metrics --------------------------------------------------------------------------------


def test_binary_metrics_perfect_and_degenerate() -> None:
    m = binary_metrics([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9])
    assert m["roc_auc"] == 1.0 and m["ks"] == 1.0 and m["base_rate"] == 0.5
    assert ks_statistic([0, 1], [0.5, 0.5]) == 0.0
    with pytest.raises(ValueError, match="both"):
        binary_metrics([1, 1], [0.2, 0.3])


# --- training -------------------------------------------------------------------------------


def test_model_learns_and_beats_base_rate(model: EarlyWarningModel) -> None:
    m = model.bundle.metadata["metrics"]["roll_forward_test"]
    assert m["roc_auc"] > 0.75
    assert m["pr_auc"] > 3 * m["base_rate"]
    assert {"brier", "ks"} <= m.keys()
    assert {"npa_90d_test", "baseline_test"} <= model.bundle.metadata["metrics"].keys()


def test_calibrated_probabilities_track_the_base_rate(model, fake_data) -> None:
    test = fake_data.features[fake_data.features["month"] >= "2026-07"]
    p = model.predict_proba(test)
    assert ((p >= 0) & (p <= 1)).all()
    base = model.bundle.metadata["metrics"]["roll_forward_test"]["base_rate"]
    assert abs(p.mean() - base) < 0.03


def test_metadata_records_thresholds_and_band_shares(model: EarlyWarningModel) -> None:
    md = model.bundle.metadata
    assert md["thresholds"] == {"high": 0.35, "medium": 0.15}
    assert sum(md["band_share_validation"].values()) == pytest.approx(1.0)
    assert 0 < md["suggested_high_threshold_6_5pct"] < 1
    assert md["split"]["train_end"] == "2026-03"


def test_demo_personas_are_high_risk(model, fake_data) -> None:
    rows = _as_of(fake_data)
    personas = rows[rows["account_id"].isin(["ACC-DEMO-PRIYA", "ACC-DEMO-RAVI"])]
    scores = {s.account_id: s for s in model.score(personas)}
    assert scores["ACC-DEMO-PRIYA"].risk_band is RiskBand.HIGH
    assert scores["ACC-DEMO-RAVI"].risk_band is RiskBand.HIGH


def test_monotone_constraint_min_due_streak(model, fake_data) -> None:
    row = _as_of(fake_data).iloc[[0]]
    grid = pd.concat([row.assign(min_due_only_streak=k) for k in range(0, 8)])
    raw = model.bundle.estimators["roll_forward"].predict_proba(build_matrix(grid))[:, 1]
    assert np.all(np.diff(raw) >= -1e-12)
    assert np.all(np.diff(model.predict_proba(grid)) >= -1e-12)
    assert MONOTONE["payment_ratio_3m"] == -1


def test_training_is_deterministic(model, fake_data) -> None:
    again = train_frames(fake_data.features, fake_data.labels, seed=42)
    assert again.model_version == model.model_version
    rows = _as_of(fake_data)
    np.testing.assert_array_equal(again.predict_proba(rows), model.predict_proba(rows))


def test_training_fails_without_validation_months(fake_data) -> None:
    early = fake_data.features[fake_data.features["month"] <= "2026-03"]
    with pytest.raises(ValueError, match="validation split is empty"):
        train_frames(early, fake_data.labels, seed=42)


def test_training_fails_with_single_class_labels(fake_data) -> None:
    labels = fake_data.labels.assign(rolls_forward_60d=False)
    with pytest.raises(ValueError, match="both classes"):
        train_frames(fake_data.features, labels, seed=42)


def test_custom_split_without_test_labels_skips_test_metrics(fake_data) -> None:
    split = TimeSplit(
        train_end="2026-03",
        val_start="2026-04",
        val_end="2026-06",
        test_start="2026-07",
        test_end="2026-09",
    )
    labels = fake_data.labels[fake_data.labels["month"] <= "2026-06"]
    m = train_frames(fake_data.features, labels, seed=42, split=split, bands=RiskBands(0.3, 0.1))
    assert m.bundle.metadata["metrics"] == {}
    assert m.bands.high == 0.3


# --- scoring --------------------------------------------------------------------------------


def test_score_returns_contract_objects(model, fake_data) -> None:
    scores = model.score_batch(fake_data.features, AS_OF)
    assert len(scores) == len(_as_of(fake_data))
    s = scores[0]
    assert isinstance(s, RiskScore)
    assert s.as_of_month == AS_OF
    assert MODEL_VERSION_RE.match(s.model_version)
    assert s.model_version.startswith("ew-lgbm-")
    assert s.reasons == []
    RiskScore.model_validate_json(s.model_dump_json())


def test_score_frame_columns(model, fake_data) -> None:
    frame = model.score_frame(_as_of(fake_data))
    assert list(frame.columns) == [
        "account_id",
        "as_of_month",
        "p_roll_forward",
        "p_npa_90d",
        "risk_band",
    ]
    assert set(frame["risk_band"]) <= {b.value for b in RiskBand}


def test_score_batch_unknown_month_fails(model, fake_data) -> None:
    with pytest.raises(ValueError, match="2030-01"):
        model.score_batch(fake_data.features, "2030-01")


def test_score_ignores_protected_columns(model, fake_data) -> None:
    rows = _as_of(fake_data)
    joined = rows.merge(fake_data.protected, on="customer_id")
    swapped = joined.assign(gender="female", religion="other", region="south")
    np.testing.assert_array_equal(model.predict_proba(joined), model.predict_proba(swapped))


# --- persistence ----------------------------------------------------------------------------


def test_train_from_parquet_save_and_load(tmp_path: Path, fake_data, model) -> None:
    fp, lp = tmp_path / "features.parquet", tmp_path / "labels.parquet"
    fake_data.features.to_parquet(fp)
    fake_data.labels.to_parquet(lp)
    bundle = train(fp, lp)
    loaded_model = EarlyWarningModel(bundle=bundle, bands=RiskBands())
    loaded_model.save(tmp_path / "artifacts")
    loaded = EarlyWarningModel.load(tmp_path / "artifacts")
    assert loaded.model_version == bundle.model_version
    rows = _as_of(fake_data)
    np.testing.assert_allclose(loaded.predict_proba(rows), model.predict_proba(rows))
