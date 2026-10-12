"""Fit generator distributions from the UCI "Default of Credit Card Clients" dataset.

Usage (after ``data/scripts/download_public.py``)::

    uv run python -m datagen.calibrate_uci

writes ``calibration.json`` next to this module (committed, small). The generator only ever
reads that JSON, so it runs with no downloaded data at all.

UCI columns (Taiwan, April-September 2005, NT$): ``PAY_0, PAY_2..PAY_6`` are repayment status
for Sep..Apr (-2/-1/0 = paid duly or revolving, k = k months late), ``BILL_AMT1..6`` the bills
for Sep..Apr and ``PAY_AMT1..6`` the amount paid in Sep..Apr (paying the previous month's bill).
The demographic columns (sex, education, marriage, age) are never read.

Scaling to India is by ratio, not exchange rate: limits are rescaled so the median card limit is
Rs 1,50,000 (see ``data/README.md``).
"""

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from datagen.config import DatagenConfig
from datagen.download import uci_xls_path

logger = logging.getLogger(__name__)

CALIBRATION_PATH = Path(__file__).with_name("calibration.json")
TARGET_MEDIAN_LIMIT_INR = 150_000
STATUS_STATES = ("duly", "late1", "late2", "late3plus")
QUANTILE_GRID = np.linspace(0.0, 1.0, 101)
UTIL_BANDS = (0.0, 0.3, 0.6, 0.9, np.inf)
PAY_RATIO_BANDS = (0.0, 0.05, 0.2, 1.0, np.inf)

# Newest -> oldest month, as in the UCI file.
_STATUS_COLS = ("PAY_0", "PAY_2", "PAY_3", "PAY_4", "PAY_5", "PAY_6")
_BILL_COLS = tuple(f"BILL_AMT{i}" for i in range(1, 7))
_PAID_COLS = tuple(f"PAY_AMT{i}" for i in range(1, 7))
_DEFAULT_COL = "default payment next month"


def load_uci(path: Path) -> pd.DataFrame:
    """Read the UCI spreadsheet (header is on the second row)."""
    return pd.read_excel(path, header=1)


def _state(status: pd.Series) -> pd.Series:
    """Map UCI status to 0=duly (<=0), 1, 2, 3=3+ months late."""
    return status.clip(lower=0, upper=3).astype(int)


def _quantiles(values: np.ndarray) -> list[float]:
    return [round(float(q), 6) for q in np.quantile(values, QUANTILE_GRID)]


def _band_rates(x: pd.Series, y: pd.Series, bands: tuple[float, ...]) -> list[dict[str, Any]]:
    cut = pd.cut(x, bins=list(bands), right=False, include_lowest=True)
    out = []
    for interval, grp in y.groupby(cut, observed=False):
        out.append(
            {
                "lower": float(interval.left),
                "upper": None if np.isinf(interval.right) else float(interval.right),
                "n": int(grp.size),
                "default_rate": round(float(grp.mean()), 6) if grp.size else None,
            }
        )
    return out


def calibrate(df: pd.DataFrame) -> dict[str, Any]:
    """Fit every distribution the generator needs from a UCI-shaped frame."""
    limit = df["LIMIT_BAL"].astype(float)
    log_limit = np.log(limit)
    median_ntd = float(np.median(limit))

    # Bill-to-limit ratio over all six months (negative bills = credit balances, dropped).
    bills = df[list(_BILL_COLS)].to_numpy(float)
    ratio = bills / limit.to_numpy()[:, None]
    bill_to_limit = np.clip(ratio[bills >= 0], 0, 1.2)

    # Payment-to-bill: PAY_AMT_k pays BILL_AMT_{k+1}; condition on the status of month k+1.
    pay_by_state: dict[str, list[float]] = {}
    pairs = []
    for k in range(5):
        bill_prev = df[_BILL_COLS[k + 1]].astype(float)
        paid = df[_PAID_COLS[k]].astype(float)
        prev_state = _state(df[_STATUS_COLS[k + 1]])
        mask = bill_prev > 0
        pairs.append(
            pd.DataFrame(
                {"ratio": (paid[mask] / bill_prev[mask]).clip(0, 1.5), "state": prev_state[mask]}
            )
        )
    pay = pd.concat(pairs, ignore_index=True)
    for i, name in enumerate(STATUS_STATES):
        values = pay.loc[pay["state"] == i, "ratio"].to_numpy()
        pay_by_state[name] = _quantiles(values) if values.size else []

    # Month-to-month transition matrix of status (older -> newer).
    counts = np.zeros((4, 4))
    for older, newer in zip(_STATUS_COLS[1:], _STATUS_COLS[:-1], strict=True):
        np.add.at(counts, (_state(df[older]).to_numpy(), _state(df[newer]).to_numpy()), 1)
    rows = counts.sum(axis=1, keepdims=True)
    matrix = np.divide(counts, rows, out=np.full_like(counts, np.nan), where=rows > 0)

    # Default rate vs latest utilisation and latest payment ratio.
    default = df[_DEFAULT_COL].astype(float)
    util_latest = (df["BILL_AMT1"].clip(lower=0) / limit).astype(float)
    pay_ratio_latest = (df["PAY_AMT1"] / df["BILL_AMT2"].where(df["BILL_AMT2"] > 0)).fillna(1.0)

    return {
        "source": "UCI ML Repository dataset 350, Default of Credit Card Clients (CC BY 4.0)",
        "n_rows": len(df),
        "limit": {
            "log_mu_ntd": round(float(log_limit.mean()), 6),
            "log_sigma": round(float(log_limit.std(ddof=0)), 6),
            "median_ntd": median_ntd,
            "target_median_inr": TARGET_MEDIAN_LIMIT_INR,
            "inr_per_ntd_ratio": round(TARGET_MEDIAN_LIMIT_INR / median_ntd, 6),
        },
        "quantile_grid_step": 0.01,
        "bill_to_limit_quantiles": _quantiles(bill_to_limit),
        "pay_to_bill_quantiles_by_prev_status": pay_by_state,
        "status_states": list(STATUS_STATES),
        "status_transition_matrix": [[round(float(v), 6) for v in row] for row in matrix],
        # UCI quirk: status 1 almost never appears in PAY_2..PAY_6, so the late1 row is sparse.
        "status_transition_row_counts": [int(v) for v in rows.ravel()],
        "default_rate": round(float(default.mean()), 6),
        "default_rate_by_utilisation": _band_rates(util_latest, default, UTIL_BANDS),
        "default_rate_by_payment_ratio": _band_rates(pay_ratio_latest, default, PAY_RATIO_BANDS),
    }


def write_calibration(calibration: dict[str, Any], path: Path = CALIBRATION_PATH) -> None:
    text = json.dumps(calibration, indent=2, sort_keys=True, allow_nan=False) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


def load_calibration(path: Path = CALIBRATION_PATH) -> dict[str, Any]:
    """Read the committed calibration (no download needed)."""
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    xls = uci_xls_path(DatagenConfig().raw_data_dir)
    calibration = calibrate(load_uci(xls))
    write_calibration(calibration)
    logger.info("calibration written path=%s rows=%s", CALIBRATION_PATH, calibration["n_rows"])


if __name__ == "__main__":
    main()
