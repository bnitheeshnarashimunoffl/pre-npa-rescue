"""Label horizon: months simulated past the window feed labels only, never features or tables."""

import hashlib
from pathlib import Path

import pandas as pd
import pytest

from datagen.config import DatagenConfig
from datagen.features import build_features
from datagen.generate import LABEL_HORIZON_FILE, GeneratedData, build, write
from datagen.labels import build_labels

WINDOW_TABLES = ("customers", "protected", "account_months", "monthly_spend", "salary", "shocks")


@pytest.fixture(scope="module")
def pair(tmp_path_factory: pytest.TempPathFactory) -> tuple[GeneratedData, GeneratedData]:
    out = tmp_path_factory.mktemp("horizon")
    with_h = build(DatagenConfig(seed=11, n_customers=150, data_dir=out, label_horizon_months=3))
    without = build(DatagenConfig(seed=11, n_customers=150, data_dir=out, label_horizon_months=0))
    return with_h, without


def test_window_tables_identical_with_or_without_horizon(
    pair: tuple[GeneratedData, GeneratedData],
) -> None:
    with_h, without = pair
    for name in (*WINDOW_TABLES, "behaviour"):
        pd.testing.assert_frame_equal(getattr(with_h, name), getattr(without, name), obj=name)
    assert with_h.account_months["month"].max() == "2026-09"


def test_no_feature_uses_extension_months(pair: tuple[GeneratedData, GeneratedData]) -> None:
    """Features from a run with the horizon equal features from a run without it."""
    with_h, without = pair

    def feats(d: GeneratedData) -> pd.DataFrame:
        return build_features(d.customers, d.account_months, d.monthly_spend, d.salary)

    f_with, f_without = feats(with_h), feats(without)
    pd.testing.assert_frame_equal(f_with, f_without)
    assert f_with["month"].max() == "2026-09"  # no extension month ever becomes a feature row


def test_horizon_rows_are_after_the_window(pair: tuple[GeneratedData, GeneratedData]) -> None:
    with_h, without = pair
    hz = with_h.label_horizon
    assert sorted(hz["month"].unique()) == ["2026-10", "2026-11", "2026-12"]
    assert list(hz.columns) == ["account_id", "month", "dpd", "bucket"]
    assert len(hz) == len(with_h.customers) * 3
    assert without.label_horizon.empty


def test_labels_cover_every_window_month(pair: tuple[GeneratedData, GeneratedData]) -> None:
    with_h, without = pair
    full = build_labels(
        with_h.account_months, with_h.shocks, with_h.behaviour, with_h.label_horizon
    )
    short = build_labels(without.account_months, without.shocks, without.behaviour)
    assert full["month"].max() == "2026-09" and short["month"].max() == "2026-06"
    # Labels inside the old range do not change.
    old = full[full["month"] <= "2026-06"].reset_index(drop=True)
    pd.testing.assert_frame_equal(old, short)
    # The new months use the horizon: Ravi keeps not paying, so he rolls forward at 2026-09.
    ravi = full.query("account_id == 'ACC-DEMO-RAVI' and month == '2026-09'").iloc[0]
    assert ravi["rolls_forward_60d"]


def test_incomplete_horizon_is_rejected(pair: tuple[GeneratedData, GeneratedData]) -> None:
    with_h, _ = pair
    with pytest.raises(ValueError, match="label horizon"):
        build_labels(
            with_h.account_months, with_h.shocks, with_h.behaviour, with_h.label_horizon.iloc[1:]
        )


def test_written_bytes_identical_except_labels(tmp_path: Path) -> None:
    def digests(horizon: int) -> dict[str, str]:
        out = tmp_path / f"h{horizon}"
        cfg = DatagenConfig(seed=5, n_customers=40, data_dir=out, label_horizon_months=horizon)
        write(build(cfg), cfg)
        return {
            p.relative_to(out).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(out.rglob("*.parquet"))
            if p.is_file()
        }

    a, b = digests(3), digests(0)
    assert set(a) - set(b) == {LABEL_HORIZON_FILE}
    assert {k: v for k, v in a.items() if k != LABEL_HORIZON_FILE} == b
