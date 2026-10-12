"""Feature matrix construction and the time-based split (no look-ahead, B3.2)."""

import re
from pathlib import Path

import pandas as pd
import pytest

from npa_models.features import (
    DEFAULT_SPLIT,
    FEATURE_COLUMNS,
    TimeSplit,
    build_matrix,
    time_split,
)

CONTRACTS = Path(__file__).resolve().parents[3] / "contracts" / "data"


def _contract_columns(table: str) -> list[str]:
    text = (CONTRACTS / f"{table}.md").read_text(encoding="utf-8")
    return re.findall(r"^\| `([a-z0-9_]+)` \|", text, flags=re.MULTILINE)


def test_feature_columns_are_in_the_data_contract() -> None:
    assert set(FEATURE_COLUMNS) <= set(_contract_columns("features"))


def test_fake_data_matches_data_contracts(fake_data) -> None:
    assert list(fake_data.features.columns) == _contract_columns("features")
    assert list(fake_data.labels.columns) == _contract_columns("labels")
    assert list(fake_data.protected.columns) == _contract_columns("protected_attributes")


def test_fake_data_is_deterministic(fake_data, fake_data_factory) -> None:
    again = fake_data_factory()
    pd.testing.assert_frame_equal(fake_data.features, again.features)
    pd.testing.assert_frame_equal(fake_data.labels, again.labels)


def test_build_matrix_types(fake_data) -> None:
    x = build_matrix(fake_data.features)
    assert list(x.columns) == list(FEATURE_COLUMNS)
    assert isinstance(x["occupation_type"].dtype, pd.CategoricalDtype)
    assert x["broken_streak_flag"].dtype == "int8"
    assert len(x) == len(fake_data.features)


def test_build_matrix_unknown_occupation_becomes_missing(fake_data) -> None:
    df = fake_data.features.head(2).copy()
    df["occupation_type"] = ["salaried", "astronaut"]
    x = build_matrix(df)
    assert x["occupation_type"].iloc[0] == "salaried"
    assert pd.isna(x["occupation_type"].iloc[1])


def test_build_matrix_missing_column_fails(fake_data) -> None:
    with pytest.raises(KeyError, match="dpd"):
        build_matrix(fake_data.features.drop(columns=["dpd"]))


def test_time_split_windows_do_not_overlap(fake_data) -> None:
    s = time_split(fake_data.features)
    assert s.train["month"].max() <= DEFAULT_SPLIT.train_end
    assert s.val["month"].min() >= DEFAULT_SPLIT.val_start
    assert s.val["month"].max() <= DEFAULT_SPLIT.val_end
    assert s.test["month"].min() >= DEFAULT_SPLIT.test_start
    assert s.train["month"].max() < s.val["month"].min() < s.test["month"].min()
    assert set(s.test["month"]) == {"2026-07", "2026-08", "2026-09"}


def test_time_split_drops_months_after_test_end(fake_data) -> None:
    split = TimeSplit(
        train_end="2025-12",
        val_start="2026-01",
        val_end="2026-03",
        test_start="2026-04",
        test_end="2026-06",
    )
    s = time_split(fake_data.features, split)
    assert s.test["month"].max() == "2026-06"
    assert sum(map(len, s)) < len(fake_data.features)


def test_time_split_requires_month_column() -> None:
    with pytest.raises(KeyError, match="month"):
        time_split(pd.DataFrame({"x": [1]}))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"train_end": "2026-04"},  # overlaps validation
        {"val_end": "2026-08"},  # overlaps test
        {"test_end": "2026-13"},  # bad month
        {"train_end": "2026-3"},  # bad format
    ],
)
def test_time_split_rejects_bad_boundaries(kwargs: dict[str, str]) -> None:
    with pytest.raises(ValueError):
        TimeSplit(**kwargs)


def test_fake_data_round_trips_through_parquet(fake_data, tmp_path) -> None:
    # Guards the pyarrow pin: pyarrow >= 21 needs numpy 2, but A6 pins numpy 1.26.
    path = tmp_path / "features.parquet"
    fake_data.features.to_parquet(path)
    pd.testing.assert_frame_equal(pd.read_parquet(path), fake_data.features)
