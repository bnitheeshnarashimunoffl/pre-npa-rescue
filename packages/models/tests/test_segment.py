"""Task 2.3 segmentation classifier on the seeded fake data."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from npa_contracts.enums import Segment
from npa_contracts.models import SegmentResult
from npa_models.registry import MODEL_VERSION_RE
from npa_models.segment import (
    CLASSES,
    LOW_CONFIDENCE,
    SegmentModel,
    apply_conservative_rule,
    classification_report,
    train,
    train_frames,
)

AS_OF = "2026-09"
PERSONAS = {
    "ACC-DEMO-PRIYA": Segment.CANT_PAY,
    "ACC-DEMO-RAVI": Segment.CANT_PAY,
    "ACC-DEMO-FORGOT": Segment.FORGOT,
    "ACC-DEMO-WONTPAY": Segment.WONT_PAY,
}


@pytest.fixture(scope="module")
def model(fake_data) -> SegmentModel:
    return train_frames(fake_data.features, fake_data.labels, seed=42)


def _as_of(fake_data) -> pd.DataFrame:
    return fake_data.features[fake_data.features["month"] == AS_OF]


def _proba(**rows: list[float]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=list(CLASSES))


# --- conservative rule ----------------------------------------------------------------------


def test_low_confidence_wont_pay_becomes_cant_pay() -> None:
    p = _proba(forgot=[0.1], cant_pay=[0.3], wont_pay=[0.45], not_at_risk=[0.15])
    out = apply_conservative_rule(p)
    assert out["segment"].iloc[0] == "cant_pay"
    assert out["confidence"].iloc[0] == pytest.approx(0.3)
    assert bool(out[LOW_CONFIDENCE].iloc[0])


def test_confident_wont_pay_is_kept() -> None:
    p = _proba(forgot=[0.0], cant_pay=[0.2], wont_pay=[0.5], not_at_risk=[0.3])
    out = apply_conservative_rule(p)
    assert out["segment"].iloc[0] == "wont_pay"
    assert out["confidence"].iloc[0] == pytest.approx(0.5)
    assert not out[LOW_CONFIDENCE].iloc[0]


def test_rule_leaves_other_classes_alone() -> None:
    p = _proba(forgot=[0.4, 0.1], cant_pay=[0.3, 0.2], wont_pay=[0.0, 0.3], not_at_risk=[0.3, 0.4])
    out = apply_conservative_rule(p)
    assert out["segment"].tolist() == ["forgot", "not_at_risk"]
    assert not out[LOW_CONFIDENCE].any()


def test_rule_needs_every_class_column() -> None:
    with pytest.raises(KeyError, match="wont_pay"):
        apply_conservative_rule(pd.DataFrame({"forgot": [1.0], "cant_pay": [0.0]}))


def test_classification_report_shape() -> None:
    r = classification_report(["forgot", "cant_pay", "cant_pay"], ["forgot", "cant_pay", "forgot"])
    assert r["labels"] == list(CLASSES)
    assert np.array(r["confusion_matrix"]).shape == (4, 4)
    assert r["recall"]["cant_pay"] == 0.5
    assert r["recall"]["wont_pay"] == 0.0  # absent class: zero, not an error
    assert 0 < r["macro_f1"] < 1


# --- training and metrics -------------------------------------------------------------------


def test_metrics_reported_for_validation_and_test(model: SegmentModel) -> None:
    m = model.bundle.metadata["metrics"]
    assert {"validation", "validation_raw", "test", "test_raw"} <= m.keys()
    test = m["test"]
    assert test["macro_f1"] > 0.5
    assert test["recall"]["cant_pay"] > 0.7
    assert 0.0 <= test["low_confidence_share"] <= 1.0
    assert sum(map(sum, test["confusion_matrix"])) == test["n"]


@pytest.mark.parametrize(("account_id", "expected"), list(PERSONAS.items()))
def test_persona_segments(model, fake_data, account_id: str, expected: Segment) -> None:
    rows = _as_of(fake_data)
    result = model.score(rows[rows["account_id"] == account_id])[0]
    assert result.segment is expected


def test_probabilities_sum_to_one(model, fake_data) -> None:
    p = model.predict_proba(_as_of(fake_data))
    assert list(p.columns) == list(CLASSES)
    np.testing.assert_allclose(p.sum(axis=1), 1.0, atol=1e-9)


def test_training_is_deterministic(model, fake_data) -> None:
    again = train_frames(fake_data.features, fake_data.labels, seed=42)
    assert again.model_version == model.model_version
    rows = _as_of(fake_data)
    pd.testing.assert_frame_equal(again.predict_proba(rows), model.predict_proba(rows))


def test_training_rejects_unknown_labels(fake_data) -> None:
    labels = fake_data.labels.assign(segment_truth="lazy")
    with pytest.raises(ValueError, match="lazy"):
        train_frames(fake_data.features, labels, seed=42)


def test_training_needs_two_classes(fake_data) -> None:
    labels = fake_data.labels.assign(segment_truth="not_at_risk")
    with pytest.raises(ValueError, match="two segment classes"):
        train_frames(fake_data.features, labels, seed=42)


def test_missing_class_in_training_gets_zero_probability(fake_data) -> None:
    labels = fake_data.labels.copy()
    labels.loc[labels["segment_truth"] == "forgot", "segment_truth"] = "not_at_risk"
    m = train_frames(fake_data.features, labels, seed=42)
    assert (m.predict_proba(_as_of(fake_data))["forgot"] == 0.0).all()


def test_no_test_labels_skips_test_metrics(fake_data) -> None:
    labels = fake_data.labels[fake_data.labels["month"] <= "2026-06"]
    m = train_frames(fake_data.features, labels, seed=42)
    assert "test" not in m.bundle.metadata["metrics"]


# --- scoring --------------------------------------------------------------------------------


def test_score_batch_returns_contract_objects(model, fake_data) -> None:
    results = model.score_batch(fake_data.features, AS_OF)
    assert len(results) == len(_as_of(fake_data))
    r = results[0]
    assert isinstance(r, SegmentResult)
    assert MODEL_VERSION_RE.match(r.model_version) and r.model_version.startswith("seg-lgbm-")
    SegmentResult.model_validate_json(r.model_dump_json())


def test_score_frame_columns(model, fake_data) -> None:
    frame = model.score_frame(_as_of(fake_data))
    assert list(frame.columns) == [
        "account_id",
        "as_of_month",
        "segment",
        "confidence",
        LOW_CONFIDENCE,
        *(f"p_{c}" for c in CLASSES),
    ]


def test_score_batch_unknown_month_fails(model, fake_data) -> None:
    with pytest.raises(ValueError, match="2030-01"):
        model.score_batch(fake_data.features, "2030-01")


def test_segment_ignores_protected_columns(model, fake_data) -> None:
    joined = _as_of(fake_data).merge(fake_data.protected, on="customer_id")
    swapped = joined.assign(gender="male", caste_category="general", state="Maharashtra")
    pd.testing.assert_frame_equal(model.predict_proba(joined), model.predict_proba(swapped))


def test_train_from_parquet_save_and_load(tmp_path: Path, fake_data, model) -> None:
    fp, lp = tmp_path / "features.parquet", tmp_path / "labels.parquet"
    fake_data.features.to_parquet(fp)
    fake_data.labels.to_parquet(lp)
    SegmentModel(train(fp, lp)).save(tmp_path / "artifacts")
    loaded = SegmentModel.load(tmp_path / "artifacts")
    assert loaded.model_version == model.model_version
    rows = _as_of(fake_data)
    pd.testing.assert_frame_equal(loaded.predict_proba(rows), model.predict_proba(rows))
