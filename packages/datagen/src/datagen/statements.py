"""Monthly statement simulator (``account_months.parquet``, task 1.1 step 3).

Vectorised over accounts, one loop iteration per month. Each cycle ``t``:

1. The behaviour policy decides the payment against the previous statement (amount mode and
   timing relative to its due date). Payments go to charges first, then principal.
2. Unpaid minimum dues are tracked per statement (oldest paid first), so DPD is counted from
   the due date of the oldest unpaid minimum amount due (RBI Credit Card Directions 2025).
3. Late fee: only if past due for more than 3 days, on the amount outstanding after the due
   date (total due minus what was paid by the due date), via :func:`dues.late_fee_vec`.
4. Interest on principal only (fees, interest and GST never earn interest), charged unless the
   previous statement was paid in full by its due date. Cash advances earn interest from the
   withdrawal (approximated as half a cycle).
5. New purchases and cash advances, capped by the available limit; cards are blocked from
   ``BLOCK_SPEND_DPD`` days past due (bank policy assumption).
6. The minimum amount due is overdue dues plus this cycle's MAD (all interest, fees and GST plus
   5% of principal, floor Rs 200), capped at the total due: no negative amortisation.

Once an account is NPA (DPD > 90) no further interest or fees are charged, following the income
recognition norms (assumption; documented in ``data/README.md``).

Ledger identity per row: ``closing = opening + purchases + cash_advance - payments + interest +
late_fee + GST`` where ``GST = round_half_up(18% x (interest + late_fee))``.
"""

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
import pandas as pd

from datagen import dues
from datagen.calendar import ordinal_to_datetime64, statement_ordinals
from npa_contracts.constants import NPA_DPD

IntArray = npt.NDArray[np.int64]
FloatArray = npt.NDArray[np.float64]

BLOCK_SPEND_DPD = 31  # card blocked for new spend from SMA-1 (bank policy assumption)

# Payment modes returned by a behaviour policy.
PAY_NONE = 0  # pay nothing
PAY_MIN_FRAC = 1  # pay frac x minimum amount due (partial)
PAY_MIN = 2  # pay exactly the minimum amount due (clears all overdue)
PAY_OLDEST = 3  # pay only the oldest unpaid minimum due (stays delinquent, no roll)
PAY_TOTAL_FRAC = 4  # pay max(minimum due, frac x total due)
PAY_FULL = 5  # pay the total amount due

PURCHASE_CATEGORIES = ("essentials", "discretionary", "travel", "utilities", "emi", "other")


@dataclass(frozen=True, slots=True)
class CycleState:
    """What a behaviour policy sees at the start of cycle ``t`` (about the last statement)."""

    t: int
    dpd: IntArray
    min_due: IntArray
    total_due: IntArray
    oldest_unpaid: IntArray


@dataclass(frozen=True, slots=True)
class PaymentDecision:
    mode: npt.NDArray[np.int8]
    frac: FloatArray
    late_days: IntArray  # payment day relative to the due date (negative = early)


Policy = Callable[[CycleState], PaymentDecision]


@dataclass(frozen=True, slots=True)
class SpendPlan:
    """Desired spend before the credit-limit cap, all int64 paise.

    ``purchases`` has shape ``(n, T, len(PURCHASE_CATEGORIES))``; ``cash_advance`` and
    ``txn_count`` have shape ``(n, T)``.
    """

    purchases: npt.NDArray[np.int64]
    cash_advance: IntArray
    txn_count: IntArray


@dataclass(frozen=True, slots=True)
class Accounts:
    account_id: npt.NDArray[np.object_]
    customer_id: npt.NDArray[np.object_]
    limit: IntArray
    bill_day: IntArray
    opening_balance: IntArray


def _payment_amount(dec: PaymentDecision, st: CycleState) -> IntArray:
    mode = dec.mode
    frac_min = np.floor(dec.frac * st.min_due).astype(np.int64)
    frac_total = np.maximum(st.min_due, np.floor(dec.frac * st.total_due).astype(np.int64))
    amount = np.select(
        [
            mode == PAY_MIN_FRAC,
            mode == PAY_MIN,
            mode == PAY_OLDEST,
            mode == PAY_TOTAL_FRAC,
            mode == PAY_FULL,
        ],
        [frac_min, st.min_due, st.oldest_unpaid, frac_total, st.total_due],
        default=0,
    )
    return np.clip(amount, 0, st.total_due).astype(np.int64)


def _oldest_unpaid_col(queue: IntArray, upto: int) -> IntArray:
    """Index of the oldest column ``< upto`` with unpaid dues, or -1."""
    unpaid = queue[:, :upto] > 0
    first = unpaid.argmax(axis=1)
    return np.where(unpaid.any(axis=1), first, -1)


def simulate_statements(
    accounts: Accounts,
    months: list[str],
    policy: Policy,
    spend: SpendPlan,
    dues_policy: dues.DuesPolicy = dues.DEFAULT_POLICY,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run the month loop; returns ``(account_months, monthly_spend)`` frames."""
    n, n_months = accounts.limit.size, len(months)
    stmt = statement_ordinals(months, accounts.bill_day)  # (n, T + 1)
    due = stmt + dues_policy.due_days_after_statement
    rows = np.arange(n)

    out: dict[str, IntArray] = {
        k: np.zeros((n, n_months), dtype=np.int64)
        for k in (
            "opening",
            "purchases",
            "cash",
            "payments",
            "pay_day",
            "total_due",
            "min_due",
            "interest",
            "late_fee",
            "closing",
            "dpd",
        )
    }
    actual = np.zeros((n, n_months, len(PURCHASE_CATEGORIES)), dtype=np.int64)
    txn_count = np.zeros((n, n_months), dtype=np.int64)

    # Opening statement (column 0): balance is all principal, MAD due 15 days later.
    principal = accounts.opening_balance.astype(np.int64).copy()
    charges = np.zeros(n, dtype=np.int64)
    queue = np.zeros((n, n_months + 1), dtype=np.int64)
    total_due = principal.copy()
    min_due = dues.minimum_amount_due_vec(
        principal, charges, dues_policy.mad_principal_bp, dues_policy.mad_floor_paise
    )
    queue[:, 0] = min_due
    dpd = np.zeros(n, dtype=np.int64)

    for t in range(n_months):
        c = t + 1  # statement column for months[t]
        s_prev, s_now, d_prev = stmt[:, c - 1], stmt[:, c], due[:, c - 1]
        cycle_days = s_now - s_prev

        oldest = _oldest_unpaid_col(queue, c)
        oldest_amt = np.where(oldest >= 0, queue[rows, np.maximum(oldest, 0)], 0)
        state = CycleState(t, dpd.copy(), min_due.copy(), total_due.copy(), oldest_amt)
        dec = policy(state)
        amount = _payment_amount(dec, state)
        pay_day = np.clip(d_prev + dec.late_days, s_prev + 1, s_now)

        # Apply the payment: charges first, then principal; dues oldest first.
        to_charges = np.minimum(amount, charges)
        charges -= to_charges
        principal -= amount - to_charges
        q = queue[:, :c]
        before = np.cumsum(q, axis=1) - q
        queue[:, :c] = q - np.clip(amount[:, None] - before, 0, q)

        oldest = _oldest_unpaid_col(queue, c)
        oldest_due = due[rows, np.maximum(oldest, 0)]
        dpd = np.where(oldest >= 0, np.maximum(0, s_now - oldest_due), 0)
        npa = dpd > NPA_DPD

        # Late fee on the post-due outstanding, only if past due > 3 days.
        covered = amount >= state.min_due
        paid_by_due = np.where(pay_day <= d_prev, amount, 0)
        outstanding_after_due = state.total_due - paid_by_due
        late_days = np.where(amount > 0, np.maximum(0, pay_day - d_prev), 0)
        fee_dpd = np.where(covered, np.where(state.min_due > 0, late_days, 0), dpd)
        fee = dues.late_fee_vec(outstanding_after_due, fee_dpd, dues_policy.late_fee_slabs)

        # New spend, capped by available limit; blocked from SMA-1.
        wanted = spend.purchases[:, t, :]
        wanted_cash = spend.cash_advance[:, t]
        wanted_total = wanted.sum(axis=1) + wanted_cash
        available = np.maximum(0, accounts.limit - principal - charges)
        available = np.where(state.dpd >= BLOCK_SPEND_DPD, 0, available)
        allowed = np.minimum(available, wanted_total)
        denom = np.maximum(wanted_total, 1)
        got = wanted * allowed[:, None] // denom[:, None]
        cash = wanted_cash * allowed // denom
        actual[:, t, :] = got
        purchases = got.sum(axis=1)
        any_spend = (purchases + cash) > 0
        scaled_count = np.round(spend.txn_count[:, t] * allowed / denom).astype(np.int64)
        txn_count[:, t] = np.where(any_spend, np.maximum(scaled_count, 1), 0)

        # Interest on principal only; free if the last statement was paid in full by its due date.
        paid_full_on_time = (amount >= state.total_due) & (pay_day <= d_prev)
        base = np.where(paid_full_on_time, 0, principal)
        interest = dues.interest_vec(base, dues_policy.annual_rate_bp, cycle_days)
        interest += dues.interest_vec(cash, dues_policy.annual_rate_bp, cycle_days // 2)
        interest = np.where(npa, 0, interest)
        fee = np.where(npa, 0, fee)
        tax = dues.gst_vec(interest + fee, dues_policy.gst_bp)

        opening = state.total_due
        principal = principal + purchases + cash
        charges = charges + interest + fee + tax
        closing = principal + charges

        overdue = queue[:, :c].sum(axis=1)
        new_mad = dues.minimum_amount_due_vec(
            principal,
            interest + fee + tax,
            dues_policy.mad_principal_bp,
            dues_policy.mad_floor_paise,
        )
        min_due = np.minimum(overdue + new_mad, closing)
        queue[:, c] = np.maximum(min_due - overdue, 0)
        total_due = closing

        for key, val in (
            ("opening", opening),
            ("purchases", purchases),
            ("cash", cash),
            ("payments", amount),
            ("pay_day", np.where(amount > 0, pay_day, 0)),
            ("total_due", total_due),
            ("min_due", min_due),
            ("interest", interest),
            ("late_fee", fee),
            ("closing", closing),
            ("dpd", dpd),
        ):
            out[key][:, t] = val

    return _frames(accounts, months, stmt, due, out, actual, txn_count)


def _frames(
    accounts: Accounts,
    months: list[str],
    stmt: IntArray,
    due: IntArray,
    out: dict[str, IntArray],
    actual: npt.NDArray[np.int64],
    txn_count: IntArray,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    from npa_contracts.constants import bucket_for_dpd

    n, n_months = out["dpd"].shape
    acc = np.repeat(accounts.account_id, n_months)
    month = np.tile(np.array(months, dtype=object), n)

    def flat(key: str) -> IntArray:
        return out[key].ravel()

    dpd = flat("dpd")
    bucket_lut = np.array([bucket_for_dpd(d).value for d in range(NPA_DPD + 2)], dtype=object)
    limit = np.repeat(accounts.limit, n_months)
    am = pd.DataFrame(
        {
            "account_id": acc,
            "customer_id": np.repeat(accounts.customer_id, n_months),
            "month": month,
            "statement_date": ordinal_to_datetime64(stmt[:, 1:].ravel()),
            "due_date": ordinal_to_datetime64(due[:, 1:].ravel()),
            "opening_balance_paise": flat("opening"),
            "purchases_paise": flat("purchases"),
            "cash_advance_paise": flat("cash"),
            "payments_paise": flat("payments"),
            "payment_date": ordinal_to_datetime64(flat("pay_day")),
            "total_due_paise": flat("total_due"),
            "min_due_paise": flat("min_due"),
            "interest_paise": flat("interest"),
            "late_fee_paise": flat("late_fee"),
            "closing_balance_paise": flat("closing"),
            "utilisation": flat("closing") / limit,
            "dpd": dpd.astype(np.int32),
            "bucket": bucket_lut[np.minimum(dpd, NPA_DPD + 1)],
        }
    )
    spend = pd.DataFrame({"account_id": acc, "month": month})
    for k, cat in enumerate(PURCHASE_CATEGORIES):
        spend[f"{cat}_paise"] = actual[:, :, k].ravel()
    spend["cash_advance_paise"] = flat("cash")
    spend["txn_count"] = txn_count.ravel()
    return am, spend
