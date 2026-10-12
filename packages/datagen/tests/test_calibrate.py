"""UCI calibration: fit on a tiny UCI-shaped frame; the committed JSON is complete."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from datagen import calibrate_uci


def _uci_like(n: int = 400, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({"ID": np.arange(1, n + 1), "LIMIT_BAL": rng.choice([5e4, 1e5, 2e5], n)})
    for col in ("PAY_0", "PAY_2", "PAY_3", "PAY_4", "PAY_5", "PAY_6"):
        df[col] = rng.choice([-2, -1, 0, 1, 2, 3], n, p=[0.1, 0.3, 0.4, 0.1, 0.05, 0.05])
    for i in range(1, 7):
        df[f"BILL_AMT{i}"] = (df["LIMIT_BAL"] * rng.uniform(-0.05, 1.1, n)).round()
        df[f"PAY_AMT{i}"] = (df["LIMIT_BAL"] * rng.uniform(0, 0.2, n)).round()
    df["SEX"] = 1  # demographic columns exist in UCI but must never be read
    df["default payment next month"] = rng.random(n) < 0.2
    return df


def test_calibrate_shapes_and_scaling() -> None:
    cal = calibrate_uci.calibrate(_uci_like())
    assert cal["limit"]["target_median_inr"] == 150_000
    assert cal["limit"]["inr_per_ntd_ratio"] == pytest.approx(150_000 / 100_000)
    assert len(cal["bill_to_limit_quantiles"]) == 101
    assert set(cal["pay_to_bill_quantiles_by_prev_status"]) == set(calibrate_uci.STATUS_STATES)
    matrix = np.array(cal["status_transition_matrix"])
    assert matrix.shape == (4, 4)
    np.testing.assert_allclose(matrix.sum(axis=1), 1.0, atol=1e-5)
    assert 0 < cal["default_rate"] < 1
    assert [b["n"] for b in cal["default_rate_by_utilisation"]]


def test_quantiles_are_monotone() -> None:
    cal = calibrate_uci.calibrate(_uci_like())
    q = np.array(cal["bill_to_limit_quantiles"])
    assert np.all(np.diff(q) >= 0)
    assert q.min() >= 0 and q.max() <= 1.2


def test_ignores_demographic_columns() -> None:
    df = _uci_like()
    a = calibrate_uci.calibrate(df)
    df["SEX"] = 2
    df["AGE"] = 99
    assert calibrate_uci.calibrate(df) == a


def test_write_and_load_roundtrip(tmp_path: Path) -> None:
    cal = calibrate_uci.calibrate(_uci_like())
    path = tmp_path / "calibration.json"
    calibrate_uci.write_calibration(cal, path)
    assert calibrate_uci.load_calibration(path) == cal
    assert path.read_bytes().endswith(b"\n") and b"\r\n" not in path.read_bytes()


def test_committed_calibration_is_from_uci() -> None:
    cal = calibrate_uci.load_calibration()
    assert cal["n_rows"] == 30_000
    assert "CC BY 4.0" in cal["source"]


def test_missing_column_fails() -> None:
    with pytest.raises(KeyError):
        calibrate_uci.calibrate(_uci_like().drop(columns=["PAY_AMT1"]))
