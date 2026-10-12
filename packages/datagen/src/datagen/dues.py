"""RBI-compliant card dues arithmetic used by the statement simulator.

Each rule exists twice: a scalar pure function (property-tested with hypothesis, and checked
against WS3's ``npa_rules.dues`` in ``test_rbi_rules_parity.py``) and a numpy-vectorised twin
that the simulator runs over every account at once. Tests assert the two agree.

Rules (A3):

* DPD is counted from the due date of the oldest unpaid minimum amount due.
  RBI Credit Card Directions 2025.
* Late charges only when past due for **more than 3 days**, and only on the amount outstanding
  after the due date, never on the total amount due. RBI Credit Card Directions 2025.
* No interest on unpaid charges, fees or taxes (no capitalisation): interest is computed on a
  principal-only base. RBI Credit Card Directions 2025.
* The minimum amount due always covers interest, fees and taxes, so paying it never grows the
  balance (no negative amortisation). RBI Credit Card Directions 2025.
* Buckets and NPA at more than 90 DPD come from ``npa_contracts.constants``. RBI asset
  classification rules for credit cards (16 July 2015).

Numbers RBI leaves to the bank (fee slabs, interest rate, MAD percentage, GST) are bank policy
assumptions mirrored from ``packages/rules/policies/bank_policy.yaml`` in :class:`DuesPolicy`.
Money is int paise; rounding is half-up, only where a rate is applied.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import numpy.typing as npt

from npa_contracts.constants import NPA_DPD, PAST_DUE_GRACE_DAYS, bucket_for_dpd
from npa_contracts.enums import Bucket

IntArray = npt.NDArray[np.int64]

DAYS_IN_YEAR = 365  # bank policy assumption: actual/365 day count


@dataclass(frozen=True, slots=True)
class LateFeeSlab:
    """Fee for a post-due outstanding ``<= up_to_paise`` (``None`` = and above)."""

    up_to_paise: int | None
    fee_paise: int


def _default_slabs() -> tuple[LateFeeSlab, ...]:
    return (
        LateFeeSlab(50_000, 0),  # up to Rs 500: nil
        LateFeeSlab(500_000, 50_000),  # up to Rs 5,000: Rs 500
        LateFeeSlab(1_000_000, 75_000),  # up to Rs 10,000: Rs 750
        LateFeeSlab(2_500_000, 100_000),  # up to Rs 25,000: Rs 1,000
        LateFeeSlab(None, 130_000),  # above: Rs 1,300
    )


@dataclass(frozen=True, slots=True)
class DuesPolicy:
    """Bank policy assumptions (mirrors ``bank_policy.yaml``; not RBI numbers)."""

    annual_rate_bp: int = 4200  # 42.0% p.a. card interest, in basis points
    mad_principal_bp: int = 500  # 5% of principal in the minimum amount due
    mad_floor_paise: int = 20_000  # Rs 200 minimum principal share
    gst_bp: int = 1800  # 18% GST on interest and fees
    due_days_after_statement: int = 15  # payment due 15 days after the statement date
    late_fee_slabs: tuple[LateFeeSlab, ...] = field(default_factory=_default_slabs)

    def __post_init__(self) -> None:
        if not self.late_fee_slabs or self.late_fee_slabs[-1].up_to_paise is not None:
            raise ValueError("late-fee slabs must end with an open-ended slab")


DEFAULT_POLICY = DuesPolicy()


def _check_paise(name: str, value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be int paise, got {type(value).__name__}")
    if value < 0:
        raise ValueError(f"{name} must be >= 0, got {value}")
    return value


def _i64(x: npt.ArrayLike) -> IntArray:
    # int64 everywhere: numpy 1.x defaults to int32 on Windows, which overflows on paise maths.
    return np.asarray(x, dtype=np.int64)


def _round_div(num: int, den: int) -> int:
    """``num / den`` rounded half-up, for non-negative integers."""
    return (2 * num + den) // (2 * den)


# --- DPD and classification -------------------------------------------------------------------


def days_past_due(oldest_unpaid_due_date: date | None, as_of: date) -> int:
    """DPD on ``as_of`` from the oldest unpaid due date (0 if none or not yet due)."""
    if oldest_unpaid_due_date is None:
        return 0
    return max(0, (as_of - oldest_unpaid_due_date).days)


def bucket(dpd: int) -> Bucket:
    """Delinquency bucket (delegates to ``npa_contracts.constants.bucket_for_dpd``)."""
    return bucket_for_dpd(dpd)


def is_past_due(dpd: int) -> bool:
    """Past due for more than 3 days: late fee and bureau reporting allowed."""
    if dpd < 0:
        raise ValueError(f"dpd must be >= 0, got {dpd}")
    return dpd > PAST_DUE_GRACE_DAYS


def is_npa(dpd: int) -> bool:
    """Minimum amount due unpaid for more than 90 days."""
    if dpd < 0:
        raise ValueError(f"dpd must be >= 0, got {dpd}")
    return dpd > NPA_DPD


# --- Late fee ---------------------------------------------------------------------------------


def late_fee(outstanding_after_due_paise: int, dpd: int, slabs: Sequence[LateFeeSlab]) -> int:
    """Late fee for one cycle: 0 unless past due > 3 days; slab chosen on the post-due
    outstanding (never the total due); never more than that outstanding."""
    _check_paise("outstanding_after_due_paise", outstanding_after_due_paise)
    if outstanding_after_due_paise == 0 or not is_past_due(dpd):
        return 0
    for slab in slabs:
        if slab.up_to_paise is None or outstanding_after_due_paise <= slab.up_to_paise:
            return min(slab.fee_paise, outstanding_after_due_paise)
    raise ValueError("late-fee slabs must end with an open-ended slab")


def late_fee_vec(outstanding: IntArray, dpd: IntArray, slabs: Sequence[LateFeeSlab]) -> IntArray:
    """Vectorised :func:`late_fee`."""
    outstanding, dpd = _i64(outstanding), _i64(dpd)
    bounds = np.array([s.up_to_paise for s in slabs[:-1]], dtype=np.int64)
    fees = np.array([s.fee_paise for s in slabs], dtype=np.int64)
    fee = fees[np.searchsorted(bounds, outstanding, side="left")]
    fee = np.minimum(fee, outstanding)
    return np.where((outstanding > 0) & (dpd > PAST_DUE_GRACE_DAYS), fee, 0).astype(np.int64)


# --- Interest and GST -------------------------------------------------------------------------


def interest_for_period(principal_paise: int, annual_rate_bp: int, days: int) -> int:
    """Simple interest on a principal-only base for ``days`` days (actual/365), half-up.

    Unpaid fees, charges and taxes are never in the base (no capitalisation).
    """
    _check_paise("principal_paise", principal_paise)
    if annual_rate_bp < 0 or days < 0:
        raise ValueError("annual_rate_bp and days must be >= 0")
    return _round_div(principal_paise * annual_rate_bp * days, 10_000 * DAYS_IN_YEAR)


def interest_vec(principal: IntArray, annual_rate_bp: int, days: IntArray) -> IntArray:
    """Vectorised :func:`interest_for_period`."""
    num = _i64(principal) * annual_rate_bp * _i64(days)
    den = 10_000 * DAYS_IN_YEAR
    return ((2 * num + den) // (2 * den)).astype(np.int64)


def gst(amount_paise: int, gst_bp: int) -> int:
    """GST on interest + fees, half-up (bank policy assumption: 18%)."""
    _check_paise("amount_paise", amount_paise)
    return _round_div(amount_paise * gst_bp, 10_000)


def gst_vec(amount: IntArray, gst_bp: int) -> IntArray:
    return ((2 * _i64(amount) * gst_bp + 10_000) // 20_000).astype(np.int64)


# --- Minimum amount due -----------------------------------------------------------------------


def minimum_amount_due(
    principal_paise: int,
    non_principal_paise: int,
    mad_principal_bp: int,
    mad_floor_paise: int,
) -> int:
    """MAD for one statement: all interest, fees and taxes plus
    ``max(pct% of principal, floor)`` of principal, capped at the total due.

    Same formula as ``npa_rules.dues.minimum_amount_due``; no negative amortisation.
    """
    _check_paise("principal_paise", principal_paise)
    _check_paise("non_principal_paise", non_principal_paise)
    principal_part = max(_round_div(principal_paise * mad_principal_bp, 10_000), mad_floor_paise)
    principal_part = min(principal_part, principal_paise)
    return non_principal_paise + principal_part


def minimum_amount_due_vec(
    principal: IntArray, non_principal: IntArray, mad_principal_bp: int, mad_floor_paise: int
) -> IntArray:
    """Vectorised :func:`minimum_amount_due`."""
    principal, non_principal = _i64(principal), _i64(non_principal)
    part = (2 * principal * mad_principal_bp + 10_000) // 20_000
    part = np.minimum(np.maximum(part, mad_floor_paise), principal)
    return (non_principal + part).astype(np.int64)
