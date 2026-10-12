"""Training labels (``labels.parquet``, task 1.2). Labels may look ahead; features never do.

* ``rolls_forward_60d``: the bucket at month ``t+1`` or ``t+2`` is worse than at ``t``.
* ``reaches_npa_90d``: the account is NPA at ``t+1``, ``t+2`` or ``t+3`` (already-NPA accounts
  that stay NPA are ``True``; filter on ``dpd`` if you want new NPAs only).
* ``segment_truth``: forgot / cant_pay / wont_pay / not_at_risk from the hidden behaviour type
  (``behaviour_types.parquet``, ``shocks.parquet``) for accounts at risk at ``t``.

**Label horizon.** The generator keeps simulating ``LABEL_HORIZON_MONTHS`` (default 3) past the
window and stores only those months' DPD and bucket in ``label_horizon.parquet``. With it, every
window month gets a label (``2024-10`` to ``2026-09``); without it, only months whose full
3-month horizon is inside the window (to ``2026-06``). A label is never computed from a truncated
future. The horizon rows feed labels only: features never read them.
"""

import numpy as np
import numpy.typing as npt
import pandas as pd

from npa_contracts.enums import Bucket, Segment

HORIZON_MONTHS = 3
BUCKET_RANK = {b.value: i for i, b in enumerate(Bucket)}  # current < sma0 < ... < npa
NPA_RANK = BUCKET_RANK[Bucket.NPA.value]
CURE_LOOKAHEAD = 2  # a normal customer who is current again within 2 months "forgot"


def _month_index(values: pd.Series, months: list[str]) -> npt.NDArray[np.int64]:
    lookup = {m: i for i, m in enumerate(months)}
    big = len(months) + 10_000
    return np.array([lookup.get(v, big) if isinstance(v, str) else big for v in values])


def build_labels(
    account_months: pd.DataFrame,
    shocks: pd.DataFrame,
    behaviour: pd.DataFrame,
    horizon: pd.DataFrame | None = None,
) -> pd.DataFrame:
    am = account_months.sort_values(["account_id", "month"], kind="stable").reset_index(drop=True)
    months = sorted(am["month"].unique())
    accounts = am["account_id"].drop_duplicates().to_numpy()
    n, t_len = accounts.size, len(months)
    if len(am) != n * t_len:
        raise ValueError("account_months must be a full account x month panel")
    rank = am["bucket"].map(BUCKET_RANK).to_numpy().reshape(n, t_len)
    dpd = am["dpd"].to_numpy().reshape(n, t_len)
    if horizon is not None and len(horizon):
        # Months after the window (labels only): append their bucket and DPD to the panel.
        hz = horizon.set_index(["account_id", "month"]).sort_index()
        ext = sorted(horizon["month"].unique())
        keys = pd.MultiIndex.from_product([accounts, ext], names=["account_id", "month"])
        hz = hz.reindex(keys)
        if hz["bucket"].isna().any():
            raise ValueError("label horizon must cover every account for every extra month")
        rank = np.hstack([rank, hz["bucket"].map(BUCKET_RANK).to_numpy().reshape(n, len(ext))])
        dpd = np.hstack([dpd, hz["dpd"].to_numpy().reshape(n, len(ext))])
    last = min(t_len, rank.shape[1] - HORIZON_MONTHS)  # labelled window months: 0 .. last-1
    if last <= 0:
        raise ValueError("window too short for a 3-month label horizon")
    pay_late = (
        (am["payment_date"] > am.groupby("account_id")["due_date"].shift(1))
        .to_numpy()
        .reshape(n, t_len)
    )

    ahead2 = np.maximum(rank[:, 1 : last + 1], rank[:, 2 : last + 2])
    rolls = ahead2 > rank[:, :last]
    npa_ahead = np.stack([rank[:, k : last + k] for k in range(1, HORIZON_MONTHS + 1)]).max(0)
    reaches_npa = npa_ahead == NPA_RANK

    cust_ids = am["customer_id"].to_numpy().reshape(n, t_len)[:, 0]
    sh = shocks.set_index("customer_id").loc[cust_ids]
    bt = behaviour.set_index("customer_id").loc[cust_ids]
    kind = bt["behaviour_type"].to_numpy()[:, None]
    start = _month_index(sh["start_month"], months)[:, None]
    recovers = _month_index(sh["recovers_month"], months)[:, None]
    wont_start = _month_index(bt["wont_pay_start_month"], months)[:, None]
    t = np.arange(last)[None, :]
    d = dpd[:, :last]

    shock_active = (kind == "shocked") & (t >= start) & ((t < recovers) | (d > 0))
    wont_active = (kind == "wont_pay") & (t >= wont_start - 2)
    at_risk = (d > 0) | rolls | pay_late[:, :last] | shock_active | wont_active
    cures = dpd[:, CURE_LOOKAHEAD : last + CURE_LOOKAHEAD] == 0

    segment = np.full((n, last), Segment.NOT_AT_RISK.value, dtype=object)
    other = at_risk & ~shock_active & ~wont_active
    segment[other & cures] = Segment.FORGOT.value
    segment[other & ~cures] = Segment.CANT_PAY.value
    segment[other & (kind == "forgetful")] = Segment.FORGOT.value
    segment[wont_active] = Segment.WONT_PAY.value
    segment[shock_active] = Segment.CANT_PAY.value

    return pd.DataFrame(
        {
            "account_id": np.repeat(accounts, last),
            "month": np.tile(np.array(months[:last], dtype=object), n),
            "rolls_forward_60d": rolls.ravel(),
            "reaches_npa_90d": reaches_npa.ravel(),
            "segment_truth": segment.ravel(),
        }
    )
