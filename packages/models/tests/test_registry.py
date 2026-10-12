"""Model bundle persistence and ``model_version`` format."""

from datetime import date
from pathlib import Path

import pytest
from sklearn.linear_model import LogisticRegression

from npa_models.features import FEATURE_COLUMNS
from npa_models.registry import (
    MODEL_VERSION_RE,
    ModelBundle,
    load_bundle,
    make_model_version,
    save_bundle,
)

DAY = date(2026, 10, 11)


def test_model_version_format_and_determinism() -> None:
    payload = {"features": list(FEATURE_COLUMNS), "seed": 42}
    v = make_model_version("ew-lgbm", payload, on=DAY)
    assert MODEL_VERSION_RE.match(v)
    assert v.startswith("ew-lgbm-2026.10.11-")
    assert v == make_model_version("ew-lgbm", payload, on=DAY)
    assert v != make_model_version("ew-lgbm", {**payload, "seed": 43}, on=DAY)


def test_model_version_defaults_to_today() -> None:
    assert MODEL_VERSION_RE.match(make_model_version("seg-lgbm", {}))


@pytest.mark.parametrize("prefix", ["", "EW", "ew_lgbm", "-ew", "ew-"])
def test_model_version_rejects_bad_prefix(prefix: str) -> None:
    with pytest.raises(ValueError):
        make_model_version(prefix, {}, on=DAY)


def test_bundle_rejects_bad_version() -> None:
    with pytest.raises(ValueError, match="model_version"):
        ModelBundle("early_warning", "v1", ("utilisation",), {})


def test_save_load_round_trip(tmp_path: Path) -> None:
    clf = LogisticRegression(random_state=42).fit([[0.0], [1.0]], [0, 1])
    bundle = ModelBundle(
        name="early_warning",
        model_version=make_model_version("ew-lr", {"seed": 42}, on=DAY),
        feature_columns=("utilisation",),
        estimators={"roll_forward": clf},
        metadata={"seed": 42, "train_end": "2026-03"},
    )
    out = save_bundle(bundle, tmp_path)
    assert out == tmp_path / "early_warning"
    loaded = load_bundle("early_warning", tmp_path)
    assert loaded.model_version == bundle.model_version
    assert loaded.feature_columns == ("utilisation",)
    assert loaded.metadata == bundle.metadata
    assert loaded.estimators["roll_forward"].predict([[1.0]])[0] == 1


def test_load_missing_bundle_fails(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="npa-models train"):
        load_bundle("early_warning", tmp_path)
