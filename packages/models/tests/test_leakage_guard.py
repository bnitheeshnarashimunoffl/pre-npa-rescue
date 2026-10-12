"""Leakage guard (briefing B3.1): no protected attribute or hidden truth may reach a model.

IS/ISO/IEC TR 24027:2021 (bias in AI systems); A3 engineering rule 1.
"""

from pathlib import Path

import pandas as pd
import pytest

from npa_models.features import (
    FEATURE_COLUMNS,
    FORBIDDEN_COLUMNS,
    HIDDEN_TRUTH_COLUMNS,
    LABEL_COLUMNS,
    PROTECTED_COLUMNS,
    LeakageError,
    assert_no_leakage,
    build_matrix,
)
from npa_models.registry import ModelBundle

SRC = Path(__file__).resolve().parents[1] / "src" / "npa_models"


def test_feature_allowlist_has_no_forbidden_column() -> None:
    assert not set(FEATURE_COLUMNS) & FORBIDDEN_COLUMNS


def test_forbidden_covers_every_protected_and_hidden_column() -> None:
    expected = {"gender", "religion", "caste_category", "state", "region", "true_uplift_group"}
    assert expected <= FORBIDDEN_COLUMNS
    assert PROTECTED_COLUMNS | HIDDEN_TRUTH_COLUMNS | LABEL_COLUMNS <= FORBIDDEN_COLUMNS
    assert "city" in FORBIDDEN_COLUMNS  # mild proxy for state/region (B8)


@pytest.mark.parametrize("col", sorted(FORBIDDEN_COLUMNS))
def test_build_matrix_rejects_each_forbidden_column(col: str) -> None:
    df = pd.DataFrame({"utilisation": [0.5], col: ["x"]})
    with pytest.raises(LeakageError, match=col):
        build_matrix(df, ["utilisation", col])


def test_protected_columns_in_input_frame_never_reach_the_matrix(fake_data) -> None:
    joined = fake_data.features.merge(fake_data.protected, on="customer_id")
    assert set(joined.columns) >= PROTECTED_COLUMNS
    x = build_matrix(joined)
    assert list(x.columns) == list(FEATURE_COLUMNS)
    assert not set(x.columns) & FORBIDDEN_COLUMNS


def test_model_bundle_refuses_forbidden_features() -> None:
    with pytest.raises(LeakageError, match="gender"):
        ModelBundle(
            name="early_warning",
            model_version="ew-lgbm-2026.10.12-abcdef",
            feature_columns=("utilisation", "gender"),
            estimators={},
        )


def test_assert_no_leakage_accepts_allowed_columns() -> None:
    assert_no_leakage(FEATURE_COLUMNS)


def test_only_fairness_module_reads_protected_attributes_table() -> None:
    offenders = [
        p.name
        for p in SRC.rglob("*.py")
        if p.name != "fairness.py" and "protected_attributes" in p.read_text(encoding="utf-8")
    ]
    assert offenders == []
