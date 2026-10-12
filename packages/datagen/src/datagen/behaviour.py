"""Customer behaviour: who pays what, when, and how much they want to spend.

Normal customers follow the UCI calibration:

* **Repayment amount**: payment-to-bill ratio drawn from the UCI quantiles for customers who
  paid duly the month before, with a persistent per-customer component so transactors stay
  transactors and revolvers stay revolvers.
* **Becoming delinquent**: UCI's paid-duly -> late probability, scaled by
  ``ENTRY_SCALE`` to Indian card delinquency levels (UCI's 22% default rate is a stressed 2005
  Taiwan portfolio).
* **Once delinquent**: UCI's month-to-month status transitions decide cure (pay all overdue),
  stay (pay only the oldest due) or roll (pay little or nothing).

Hardship shocks and the forgetful / won't-pay behaviour types are layered on top in
``shocks.py``.
"""

from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt

from datagen.statements import (
    PAY_FULL,
    PAY_MIN,
    PAY_MIN_FRAC,
    PAY_NONE,
    PAY_OLDEST,
    PAY_TOTAL_FRAC,
    PURCHASE_CATEGORIES,
    CycleState,
    PaymentDecision,
    SpendPlan,
)

FloatArray = npt.NDArray[np.float64]

ENTRY_SCALE = 0.12  # scales UCI's duly -> late probability to Indian levels (assumption)
PAY_RATIO_PERSISTENCE = 0.8  # correlation of a customer's repayment ratio month to month
FULL_PAY_THRESHOLD = 0.98  # a drawn ratio at or above this pays the statement in full
EARLY_DAYS_MAX = 10  # on-time payers pay 0-10 days before the due date
MIN_ROW_OBS = 200  # sparser UCI transition rows fall back to the next worse status

# Spend: share of monthly income spent on the card, and default category shares.
SPEND_FRAC_MEDIAN = 0.30
SPEND_FRAC_SIGMA = 0.35
CATEGORY_SHARES = {
    "essentials": 0.34,
    "discretionary": 0.24,
    "travel": 0.08,
    "utilities": 0.12,
    "emi": 0.08,
    "other": 0.14,
}
CATEGORY_CONCENTRATION = 40.0  # Dirichlet concentration of per-customer shares
MONTHLY_NOISE_SIGMA = 0.12
CASH_USER_SHARE = 0.06  # customers who take a small cash advance most months
TXN_COUNT_RANGE = (15, 60)
# Festive season lifts discretionary spend (Oct-Nov), holidays lift travel (May, Dec).
SEASONAL = {"discretionary": {10: 1.25, 11: 1.20}, "travel": {5: 1.20, 12: 1.25}}


def _norm_cdf(x: FloatArray) -> FloatArray:
    """Standard normal CDF (tanh approximation, |error| < 2e-4; enough for sampling)."""
    return 0.5 * (1.0 + np.tanh(0.7978845608 * (x + 0.044715 * x**3)))


def _status(dpd: npt.NDArray[np.int64]) -> npt.NDArray[np.int64]:
    """UCI-style status from DPD: 0 duly, 1 (1-30), 2 (31-60), 3 (>60)."""
    return np.select([dpd <= 0, dpd <= 30, dpd <= 60], [0, 1, 2], default=3)


def transition_matrix(calibration: dict[str, Any]) -> FloatArray:
    """UCI status transitions; a sparse row borrows the next worse status's row by role
    (cure stays cure, any non-worsening late move becomes "stay", worsening becomes "roll")."""
    m = np.array(calibration["status_transition_matrix"], dtype=float)
    counts = calibration.get("status_transition_row_counts", [MIN_ROW_OBS] * len(m))
    for s in range(len(m) - 2, 0, -1):
        if counts[s] < MIN_ROW_OBS:
            donor = m[s + 1]
            row = np.zeros(len(m))
            row[0] = donor[0]
            row[s] = donor[1 : s + 2].sum()
            row[s + 1] = donor[s + 2 :].sum()
            m[s] = row
    return m


@dataclass
class NormalBehaviour:
    """Payment policy for customers without a special behaviour type."""

    pay_quantiles: FloatArray  # UCI pay-to-bill quantiles after a paid-duly month
    transition: FloatArray  # 4x4 UCI status transition matrix
    z: FloatArray  # persistent per-customer repayment propensity
    rng: np.random.Generator

    @classmethod
    def from_calibration(
        cls, calibration: dict[str, Any], n: int, rng: np.random.Generator
    ) -> "NormalBehaviour":
        q = np.array(calibration["pay_to_bill_quantiles_by_prev_status"]["duly"], dtype=float)
        return cls(q, transition_matrix(calibration), rng.standard_normal(n), rng)

    def __call__(self, st: CycleState) -> PaymentDecision:
        n = st.dpd.size
        rng = self.rng
        rho = PAY_RATIO_PERSISTENCE
        u = _norm_cdf(rho * self.z + np.sqrt(1 - rho**2) * rng.standard_normal(n))
        ratio = np.interp(u, np.linspace(0, 1, self.pay_quantiles.size), self.pay_quantiles)

        mode = np.where(ratio >= FULL_PAY_THRESHOLD, PAY_FULL, PAY_TOTAL_FRAC).astype(np.int8)
        frac = ratio.copy()
        late = -rng.integers(0, EARLY_DAYS_MAX + 1, n)

        status = _status(st.dpd)
        draw = rng.random(n)
        partial = rng.random(n) < 0.4
        part_frac = rng.uniform(0.1, 0.8, n)

        # Current accounts: occasional slip into delinquency.
        p_entry = (1 - self.transition[0, 0]) * ENTRY_SCALE
        slip = (status == 0) & (st.min_due > 0) & (draw < p_entry)

        # Delinquent accounts: UCI cure / stay / roll. Moving to a better late status counts
        # half as a cure, half as a stay. UCI's top state is "3+ months late", so staying
        # there means getting later still: for that state "stay" is a roll.
        m = self.transition
        better = np.array([m[s, 1:s].sum() if s > 1 else 0.0 for s in range(4)])
        p_cure = (m[:, 0] + 0.5 * better)[status]
        p_stay = np.array(
            [m[s, s] + 0.5 * better[s] if s < 3 else 0.5 * better[s] for s in range(4)]
        )[status]
        delinquent = status > 0
        cure = delinquent & (draw < p_cure)
        stay = delinquent & ~cure & (draw < p_cure + p_stay)
        roll = delinquent & ~cure & ~stay

        miss = slip | roll
        mode = np.where(cure, PAY_MIN, mode)
        mode = np.where(stay, PAY_OLDEST, mode)
        mode = np.where(miss, np.where(partial, PAY_MIN_FRAC, PAY_NONE), mode).astype(np.int8)
        frac = np.where(miss, part_frac, frac)
        late = np.where(delinquent | miss, rng.integers(0, 10, n), late)
        return PaymentDecision(mode, frac, late.astype(np.int64))


def spend_plan(
    income_paise: npt.NDArray[np.int64],
    months: list[str],
    rng: np.random.Generator,
) -> tuple[SpendPlan, FloatArray]:
    """Desired monthly spend per category before the limit cap.

    Returns the plan and each customer's base monthly spend (paise, float) so shocks can
    rescale categories.
    """
    n, n_months = income_paise.size, len(months)
    frac = np.clip(SPEND_FRAC_MEDIAN * np.exp(SPEND_FRAC_SIGMA * rng.standard_normal(n)), 0.05, 0.8)
    base = income_paise * frac
    shares = rng.dirichlet(np.array(list(CATEGORY_SHARES.values())) * CATEGORY_CONCENTRATION, n)
    noise = np.exp(MONTHLY_NOISE_SIGMA * rng.standard_normal((n, n_months, len(CATEGORY_SHARES))))
    seasonal = np.ones((n_months, len(CATEGORY_SHARES)))
    month_num = [int(m[5:]) for m in months]
    for cat, by_month in SEASONAL.items():
        k = PURCHASE_CATEGORIES.index(cat)
        seasonal[:, k] = [by_month.get(mn, 1.0) for mn in month_num]
    purchases = base[:, None, None] * shares[:, None, :] * noise * seasonal[None, :, :]

    cash_user = rng.random(n) < CASH_USER_SHARE
    cash = np.where(
        cash_user[:, None] & (rng.random((n, n_months)) < 0.7),
        base[:, None] * rng.uniform(0.02, 0.08, (n, n_months)),
        0.0,
    )
    lo, hi = TXN_COUNT_RANGE
    base_count = rng.integers(lo, hi + 1, n)
    count = np.clip(base_count[:, None] + rng.integers(-3, 4, (n, n_months)), lo, hi)

    plan = SpendPlan(
        purchases=np.round(purchases / 100).astype(np.int64) * 100,  # whole rupees
        cash_advance=np.round(cash / 10_000).astype(np.int64) * 10_000,  # Rs 100 notes
        txn_count=count.astype(np.int64),
    )
    return plan, base
