"""Simulation calendar helpers (A7.0): ``YYYY-MM`` months and per-account statement dates."""

from datetime import date

import numpy as np
import numpy.typing as npt

# Statement (billing) days offered by the simulated bank; capped at 25 so every month has one.
BILL_DAYS = (1, 5, 10, 15, 20, 25)


def month_range(start: str, end: str) -> list[str]:
    """Inclusive list of ``YYYY-MM`` months from ``start`` to ``end``."""
    y, m = map(int, start.split("-"))
    ey, em = map(int, end.split("-"))
    out = []
    while (y, m) <= (ey, em):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    if not out:
        raise ValueError(f"empty month range {start}..{end}")
    return out


def add_months(month: str, k: int) -> str:
    y, m = map(int, month.split("-"))
    idx = y * 12 + (m - 1) + k
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"


def statement_ordinals(months: list[str], bill_day: npt.NDArray[np.int64]) -> npt.NDArray[np.int64]:
    """Statement dates as proleptic ordinals, shape ``(n_accounts, len(months) + 1)``.

    Column 0 is the statement of the month **before** ``months[0]`` (the opening statement);
    column ``t + 1`` is the statement for ``months[t]``.
    """
    all_months = [add_months(months[0], -1), *months]
    firsts = np.array([date.fromisoformat(f"{m}-01").toordinal() for m in all_months])
    return (firsts[None, :] + (bill_day[:, None] - 1)).astype(np.int64)


def ordinal_to_datetime64(ordinals: npt.NDArray[np.int64]) -> npt.NDArray[np.datetime64]:
    """Proleptic ordinals to ``datetime64[ns]`` dates (NaT where ordinal <= 0)."""
    epoch = date(1970, 1, 1).toordinal()
    days = ordinals - epoch
    out = days.astype("datetime64[D]").astype("datetime64[ns]")
    return np.where(ordinals > 0, out, np.datetime64("NaT"))
