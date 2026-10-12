"""Card transactions (``transactions.parquet``, task 1.1 step 4).

Expands the monthly category totals from the statement simulator into individual
transactions, so transaction-level and statement-level numbers always agree. Written one file
per month under ``transactions.parquet/`` (``pd.read_parquet`` reads the folder as one table),
which keeps memory flat. ``--no-transactions`` skips this; features only need the monthly
aggregates in ``monthly_spend.parquet``.
"""

from datetime import timedelta
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pandas as pd

from datagen.statements import PURCHASE_CATEGORIES
from datagen.validate import arrow_schema, table_spec, validate, write_parquet

IntArray = npt.NDArray[np.int64]

CATEGORIES = (*PURCHASE_CATEGORIES, "cash_advance")
ONLINE_SHARE = {
    "essentials": 0.25,
    "discretionary": 0.50,
    "travel": 0.60,
    "utilities": 0.80,
    "emi": 1.00,
    "other": 0.40,
}
HOME_CITY_SHARE = 0.85
IST_OFFSET = timedelta(hours=5, minutes=30)


def allocate_counts(amounts: IntArray, totals: IntArray) -> IntArray:
    """Split each row's transaction count over its non-zero categories (>= 1 each)."""
    nonzero = amounts > 0
    n_cat = nonzero.sum(axis=1)
    k = np.maximum(totals, n_cat)
    share = amounts / np.maximum(amounts.sum(axis=1, keepdims=True), 1)
    extra = np.floor((k - n_cat)[:, None] * share).astype(np.int64)
    counts = nonzero.astype(np.int64) + extra
    short = k - counts.sum(axis=1)
    counts[np.arange(len(k)), amounts.argmax(axis=1)] += np.where(n_cat > 0, short, 0)
    return np.where(nonzero, counts, 0)


def month_transactions(
    spend: pd.DataFrame,
    statement_date: npt.NDArray[np.datetime64],
    city: npt.NDArray[np.object_],
    other_cities: npt.NDArray[np.object_],
    rng: np.random.Generator,
    first_id: int,
    id_width: int,
) -> pd.DataFrame:
    """Transactions for one month; ``spend`` rows are (account, month) aggregates."""
    amounts = spend[[f"{c}_paise" for c in CATEGORIES]].to_numpy(np.int64)
    counts = allocate_counts(amounts, spend["txn_count"].to_numpy(np.int64))
    row_idx, cat_idx = np.nonzero(counts)
    group_counts = counts[row_idx, cat_idx]
    group_amount = amounts[row_idx, cat_idx]

    rows = np.repeat(row_idx, group_counts)
    cats = np.repeat(cat_idx, group_counts)
    starts = np.concatenate([[0], np.cumsum(group_counts)[:-1]]).astype(np.int64)
    weights = rng.exponential(1.0, rows.size)
    wsum = np.add.reduceat(weights, starts) if rows.size else weights
    amount = np.floor(np.repeat(group_amount / wsum, group_counts) * weights).astype(np.int64)
    if rows.size:
        amount[starts] += group_amount - np.add.reduceat(amount, starts)  # exact totals

    # Timestamp: uniform in the statement cycle, 08:00-23:00 IST, stored in UTC.
    stmt = pd.DatetimeIndex(statement_date[rows])
    cycle_start = stmt - pd.DateOffset(months=1)
    cycle_days = (stmt - cycle_start).days.to_numpy()
    offset_days = 1 + (rng.random(rows.size) * cycle_days).astype(np.int64)
    secs = rng.integers(8 * 3600, 23 * 3600, rows.size)
    local = cycle_start + pd.to_timedelta(offset_days, unit="D") + pd.to_timedelta(secs, unit="s")
    ts = (local - IST_OFFSET).tz_localize("UTC").as_unit("us")

    cat_names = np.array(CATEGORIES, dtype=object)[cats]
    online_p = np.array([ONLINE_SHARE.get(c, 0.0) for c in CATEGORIES])[cats]
    channel = np.where(rng.random(rows.size) < online_p, "online", "pos").astype(object)
    channel[cat_names == "cash_advance"] = "atm"
    home = city[rows]
    away = other_cities[rng.integers(0, other_cities.size, rows.size)]
    travel = cat_names == "travel"
    merchant_city = np.where(travel | (rng.random(rows.size) > HOME_CITY_SHARE), away, home)

    order = np.lexsort((ts.asi8, rows))
    ids = [f"TXN-{i:0{id_width}d}" for i in range(first_id, first_id + rows.size)]
    return pd.DataFrame(
        {
            "txn_id": ids,
            "account_id": spend["account_id"].to_numpy()[rows][order],
            "ts": ts[order],
            "amount_paise": amount[order],
            "category": cat_names[order],
            "merchant_city": merchant_city[order],
            "channel": channel[order],
        }
    )


def write_transactions(
    monthly_spend: pd.DataFrame,
    account_months: pd.DataFrame,
    customers: pd.DataFrame,
    out_dir: Path,
    rng: np.random.Generator,
) -> int:
    """Write ``transactions.parquet/<YYYY-MM>.parquet``; returns the number of rows."""
    folder = out_dir / "transactions.parquet"
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob("*.parquet"):
        old.unlink()
    schema = arrow_schema(table_spec("transactions"))
    city_by_acc = customers.set_index("account_id")["city"]
    other_cities = np.array(sorted(customers["city"].unique()), dtype=object)
    stmt = account_months.set_index(["account_id", "month"])["statement_date"]
    id_width = max(8, len(str(int(monthly_spend["txn_count"].sum()) * 2)))
    next_id = 1
    for _month, spend in monthly_spend.groupby("month", sort=True):
        spend = spend.reset_index(drop=True)
        keys = pd.MultiIndex.from_arrays([spend["account_id"], spend["month"]])
        txns = month_transactions(
            spend,
            stmt.loc[keys].to_numpy("datetime64[ns]"),
            city_by_acc.loc[spend["account_id"]].to_numpy(),
            other_cities,
            rng,
            next_id,
            id_width,
        )
        validate(txns, "transactions")
        write_parquet(txns, folder / f"{_month}.parquet", schema)
        next_id += len(txns)
    return next_id - 1
