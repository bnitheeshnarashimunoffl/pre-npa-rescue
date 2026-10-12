"""Feature pipeline (``features.parquet``, task 1.2).

One row per account per month with exactly the A7.2.1 columns. Every value at month ``t`` uses
only rows at or before ``t`` (no look-ahead; ``test_features.py`` proves it by truncation).
Protected attributes and hidden shock / behaviour columns are never read here.

Conventions (documented in ``data/README.md``):

* The payment in month ``t`` settles the statement of month ``t-1``.
* ``*_3m`` sums and maxima use the history available when it is shorter than the window
  (first months of the simulation); ``*_delta_3m`` features compare the last 3 months with the 3
  before (``utilisation_delta_3m``: this month vs 3 months ago). Until both windows exist they
  are 0.0 ("no observable change"), because the contract columns are non-nullable. Spend and
  salary deltas are relative changes ``(recent - prior) / max(prior, floor)`` (floor Rs 100 a
  month, 1 transaction a month), capped at ``DELTA_CAP`` (10 = +1000%).
* ``payment_ratio_3m`` = payments / minimum due over the last 3 cycles (1.0 when nothing was
  due, capped at 10).
* ``income_to_due_ratio`` = onboarding monthly income / total due (100 when nothing is due,
  capped at 100).
"""

from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd

FloatArray = npt.NDArray[np.float64]
IntArray = npt.NDArray[np.int64]

FEATURE_COLUMNS = (
    "account_id",
    "customer_id",
    "month",
    "limit_paise",
    "utilisation",
    "utilisation_delta_3m",
    "min_due_only_streak",
    "months_since_full_payment",
    "payment_ratio_3m",
    "dpd",
    "max_dpd_6m",
    "broken_streak_flag",
    "cash_advance_ratio_3m",
    "essentials_spend_delta_3m",
    "discretionary_spend_delta_3m",
    "txn_count_delta_3m",
    "salary_missing_months_3m",
    "salary_delta_3m",
    "income_to_due_ratio",
    "tenure_months",
    "dependants",
    "occupation_type",
)
MIN_ONLY_TOLERANCE = 1.10  # paid at most 10% above the minimum due counts as "minimum only"
ON_TIME_STREAK = 3  # cycles on time before a miss counts as a broken streak
SPEND_DELTA_FLOOR_PAISE = 10_000  # Rs 100
RATIO_CAP = 10.0
DELTA_CAP = 10.0
INCOME_DUE_CAP = 100.0


def panel(df: pd.DataFrame, col: str, n: int, t: int) -> npt.NDArray[np.generic]:
    """Reshape a column of a frame sorted by (account, month) into ``(n, t)``."""
    return df[col].to_numpy().reshape(n, t)


def rolling_sum(x: FloatArray, w: int) -> FloatArray:
    """Trailing sum over the last ``w`` columns (shorter at the start)."""
    c = np.cumsum(np.nan_to_num(x), axis=1)
    out = c.copy()
    out[:, w:] = c[:, w:] - c[:, :-w]
    return out


def rolling_max(x: FloatArray, w: int) -> FloatArray:
    out = x.copy()
    for k in range(1, w):
        out[:, k:] = np.maximum(out[:, k:], x[:, :-k])
    return out


def window_delta(x: FloatArray, w: int, floor: float) -> FloatArray:
    """Relative change of the last-``w`` mean vs the ``w`` before; 0.0 until both exist."""
    s = rolling_sum(x, w)
    out = np.zeros_like(x, dtype=np.float64)
    recent, prior = s[:, 2 * w - 1 :], s[:, w - 1 : -w]
    out[:, 2 * w - 1 :] = np.minimum((recent - prior) / np.maximum(prior, floor * w), DELTA_CAP)
    return out


def streak(flag: npt.NDArray[np.bool_]) -> IntArray:
    """Length of the run of True values ending at each column."""
    out = np.zeros(flag.shape, dtype=np.int64)
    run = np.zeros(flag.shape[0], dtype=np.int64)
    for t in range(flag.shape[1]):
        run = np.where(flag[:, t], run + 1, 0)
        out[:, t] = run
    return out


def since_last(flag: npt.NDArray[np.bool_]) -> IntArray:
    """Columns since the last True (0 if True now); ``t + 1`` if never seen."""
    out = np.zeros(flag.shape, dtype=np.int64)
    last = np.full(flag.shape[0], -1, dtype=np.int64)
    for t in range(flag.shape[1]):
        last = np.where(flag[:, t], t, last)
        out[:, t] = t - last
    return out


def _shift(x: npt.NDArray[Any], fill: object) -> npt.NDArray[Any]:
    """Value at ``t - 1`` (``fill`` at t = 0)."""
    out = np.empty_like(x)
    out[:, 0] = fill
    out[:, 1:] = x[:, :-1]
    return out


def build_features(
    customers: pd.DataFrame,
    account_months: pd.DataFrame,
    monthly_spend: pd.DataFrame,
    salary: pd.DataFrame,
) -> pd.DataFrame:
    """Build the feature table (one row per account-month present in ``account_months``)."""
    am = account_months.sort_values(["account_id", "month"], kind="stable").reset_index(drop=True)
    months = sorted(am["month"].unique())
    accounts = am["account_id"].drop_duplicates().to_numpy()
    n, t_len = accounts.size, len(months)
    if len(am) != n * t_len:
        raise ValueError("account_months must be a full account x month panel")
    sp = (
        monthly_spend.set_index(["account_id", "month"])
        .reindex(pd.MultiIndex.from_frame(am[["account_id", "month"]]))
        .reset_index()
    )
    if sp.isna().any().any():
        raise ValueError("monthly_spend is missing account-months present in account_months")

    def p(col: str, df: pd.DataFrame = am) -> FloatArray:
        return panel(df, col, n, t_len).astype(np.float64)

    payments, min_due, total_due = p("payments_paise"), p("min_due_paise"), p("total_due_paise")
    closing, dpd = p("closing_balance_paise"), p("dpd")
    purchases, cash = p("purchases_paise"), p("cash_advance_paise")
    pay_date = panel(am, "payment_date", n, t_len).astype("datetime64[ns]")
    due_date = panel(am, "due_date", n, t_len).astype("datetime64[ns]")

    cust = customers.set_index("account_id").loc[accounts]
    limit = cust["card_limit_paise"].to_numpy(np.float64)

    min_prev = _shift(min_due, np.nan)
    total_prev = _shift(total_due, np.nan)
    due_prev = _shift(due_date, np.datetime64("NaT"))
    known = ~np.isnan(min_prev)

    paid_full = known & ((total_prev <= 0) | (payments >= total_prev))
    min_only = (
        known
        & (min_prev > 0)
        & (payments >= min_prev)
        & (payments <= MIN_ONLY_TOLERANCE * min_prev)
        & (payments < total_prev)
    )
    with np.errstate(invalid="ignore"):
        on_time = known & ((min_prev <= 0) | ((payments >= min_prev) & (pay_date <= due_prev)))
    missed = known & ~on_time
    prior_on_time = _shift(streak(on_time), 0)
    broken = missed & (prior_on_time >= ON_TIME_STREAK)

    pay_3m = rolling_sum(payments, 3)
    min_3m = rolling_sum(np.nan_to_num(min_prev), 3)
    payment_ratio = np.where(min_3m > 0, np.minimum(pay_3m / np.maximum(min_3m, 1), RATIO_CAP), 1.0)

    util = closing / limit[:, None]
    util_delta = np.zeros_like(util)
    util_delta[:, 3:] = util[:, 3:] - util[:, :-3]

    spend_3m = rolling_sum(purchases + cash, 3)
    cash_ratio = np.where(spend_3m > 0, rolling_sum(cash, 3) / np.maximum(spend_3m, 1), 0.0)

    floor = SPEND_DELTA_FLOOR_PAISE
    ess_delta = window_delta(p("essentials_paise", sp), 3, floor)
    disc_delta = window_delta(p("discretionary_paise", sp), 3, floor)
    txn_delta = window_delta(p("txn_count", sp), 3, 1.0)

    # Salary: salaried customers only; others get 0 missing months and 0.0 delta.
    cust_ids = cust["customer_id"].to_numpy()
    sal_missing = np.zeros((n, t_len))
    sal_delta = np.zeros((n, t_len))
    if len(salary):
        full = pd.MultiIndex.from_product([cust_ids, months], names=["customer_id", "month"])
        sal = salary.set_index(["customer_id", "month"]).reindex(full)
        has = panel(sal.reset_index(), "expected_paise", n, t_len).astype(np.float64)
        credited = panel(sal.reset_index(), "credited_paise", n, t_len).astype(np.float64)
        salaried = ~np.isnan(has).all(axis=1)
        missing = (np.nan_to_num(has) > 0) & (np.nan_to_num(credited) == 0)
        sal_missing = np.where(salaried[:, None], rolling_sum(missing.astype(float), 3), 0)
        delta = window_delta(np.nan_to_num(credited), 3, SPEND_DELTA_FLOOR_PAISE)
        sal_delta = np.where(salaried[:, None], delta, 0.0)

    income = cust["monthly_income_paise"].to_numpy(np.float64)
    income_due = np.where(
        total_due > 0,
        np.minimum(income[:, None] / np.maximum(total_due, 1), INCOME_DUE_CAP),
        INCOME_DUE_CAP,
    )

    open_date = pd.to_datetime(cust["card_open_date"])
    open_idx = (open_date.dt.year * 12 + open_date.dt.month - 1).to_numpy()
    month_idx = np.array([int(m[:4]) * 12 + int(m[5:]) - 1 for m in months])
    tenure = month_idx[None, :] - open_idx[:, None]

    def rep(values: npt.NDArray[np.generic]) -> npt.NDArray[np.generic]:
        return np.repeat(values, t_len)

    return pd.DataFrame(
        {
            "account_id": am["account_id"].to_numpy(),
            "customer_id": am["customer_id"].to_numpy(),
            "month": am["month"].to_numpy(),
            "limit_paise": rep(cust["card_limit_paise"].to_numpy(np.int64)),
            "utilisation": util.ravel(),
            "utilisation_delta_3m": util_delta.ravel(),
            "min_due_only_streak": streak(min_only).ravel().astype(np.int16),
            "months_since_full_payment": since_last(paid_full).ravel().astype(np.int16),
            "payment_ratio_3m": payment_ratio.ravel(),
            "dpd": dpd.ravel().astype(np.int32),
            "max_dpd_6m": rolling_max(dpd, 6).ravel().astype(np.int32),
            "broken_streak_flag": broken.ravel(),
            "cash_advance_ratio_3m": cash_ratio.ravel(),
            "essentials_spend_delta_3m": ess_delta.ravel(),
            "discretionary_spend_delta_3m": disc_delta.ravel(),
            "txn_count_delta_3m": txn_delta.ravel(),
            "salary_missing_months_3m": sal_missing.ravel().astype(np.int16),
            "salary_delta_3m": np.asarray(sal_delta, dtype=np.float64).ravel(),
            "income_to_due_ratio": income_due.ravel(),
            "tenure_months": tenure.ravel().astype(np.int16),
            "dependants": rep(cust["dependants"].to_numpy(np.int16)),
            "occupation_type": rep(cust["occupation_type"].to_numpy()),
        }
    )
