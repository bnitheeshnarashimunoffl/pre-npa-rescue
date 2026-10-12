"""RBI-compliant card dues arithmetic: DPD, buckets, minimum amount due, late fees, interest.

Pure functions over integer paise (A7.0). WS1 runs a parity test against these, so the
synthetic statements and the rules engine agree on every number.

Rules implemented (A3):

* DPD is counted from the statement due date of the oldest unpaid minimum amount due.
  RBI Credit Card Directions 2025.
* Late charges only when the account is past due for **more than 3 days**, and only on the
  amount outstanding after the due date, never on the total amount due.
  RBI Credit Card Directions 2025.
* No interest on unpaid charges, fees or taxes (no capitalisation).
  RBI Credit Card Directions 2025.
* Minimum amount due never causes negative amortisation: it always covers every
  non-principal component of the statement. RBI Credit Card Directions 2025.
* Bucket mapping and NPA at more than 90 DPD. RBI asset-classification rules for credit cards
  (circular of 16 July 2015).

Numbers that RBI leaves to the bank (late-fee slabs, the principal percentage in the minimum
due, the interest rate) are **arguments**, supplied from ``bank_policy.yaml``; they are bank
policy assumptions, never RBI numbers.

Rounding: half-up to the nearest paisa, only in :func:`interest_for_period` and
:func:`minimum_amount_due` (the two places a rate is applied).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from npa_contracts.constants import NPA_DPD, PAST_DUE_GRACE_DAYS, bucket_for_dpd
from npa_contracts.enums import Bucket

__all__ = [
    "LateFeeSlab",
    "StatementComponents",
    "bucket",
    "days_past_due",
    "interest_for_period",
    "is_npa",
    "is_past_due",
    "late_fee",
    "minimum_amount_due",
]

DAYS_IN_YEAR = 365  # bank policy assumption: actual/365 day count for interest


def _non_negative(name: str, value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be int paise, got {type(value).__name__}")
    if value < 0:
        raise ValueError(f"{name} must be >= 0, got {value}")
    return value


def _round_half_up(value: Decimal) -> int:
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


# --- DPD and classification ------------------------------------------------------------------


def days_past_due(oldest_unpaid_due_date: date | None, as_of: date) -> int:
    """Days past due on ``as_of``, counted from the oldest unpaid statement due date.

    ``None`` means no minimum amount due is unpaid, so DPD is 0. A due date in the future
    also gives 0. RBI Credit Card Directions 2025: DPD counted from the statement due date.
    """
    if oldest_unpaid_due_date is None:
        return 0
    return max(0, (as_of - oldest_unpaid_due_date).days)


def bucket(dpd: int) -> Bucket:
    """Delinquency bucket for ``dpd`` (delegates to ``npa_contracts.constants``)."""
    return bucket_for_dpd(dpd)


def is_past_due(dpd: int) -> bool:
    """True when the account may be reported "past due" and charged a late fee.

    RBI Credit Card Directions 2025: only after it is past due for more than 3 days.
    """
    return _non_negative("dpd", dpd) > PAST_DUE_GRACE_DAYS


def is_npa(dpd: int) -> bool:
    """True when the minimum amount due has been unpaid for more than 90 days.

    RBI asset-classification rules for credit cards (16 July 2015).
    """
    return _non_negative("dpd", dpd) > NPA_DPD


# --- Late fee --------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LateFeeSlab:
    """One slab of the bank's late-fee schedule (bank policy assumption, from the YAML).

    The fee applies when the post-due outstanding is ``<= up_to_paise``; ``None`` means
    "and above".
    """

    up_to_paise: int | None
    fee_paise: int


def late_fee(outstanding_after_due_paise: int, dpd: int, slabs: Sequence[LateFeeSlab]) -> int:
    """Late fee for one statement cycle.

    * ``0`` unless the account is past due for more than 3 days (:func:`is_past_due`).
    * The slab is chosen on ``outstanding_after_due_paise`` (what is still unpaid after the
      due date), never on the total amount due.
    * Never more than that outstanding amount itself.

    RBI Credit Card Directions 2025. ``slabs`` must be sorted by ``up_to_paise`` with an
    open-ended last slab.
    """
    _non_negative("outstanding_after_due_paise", outstanding_after_due_paise)
    if not slabs or slabs[-1].up_to_paise is not None:
        raise ValueError("late-fee slabs must end with an open-ended slab (up_to_paise=None)")
    if outstanding_after_due_paise == 0 or not is_past_due(dpd):
        return 0
    for slab in slabs:
        if slab.up_to_paise is None or outstanding_after_due_paise <= slab.up_to_paise:
            return min(_non_negative("fee_paise", slab.fee_paise), outstanding_after_due_paise)
    raise AssertionError("unreachable: open-ended slab always matches")  # pragma: no cover


# --- Interest --------------------------------------------------------------------------------


def interest_for_period(principal_paise: int, annual_rate_pct: Decimal, days: int) -> int:
    """Simple interest on **principal only** for ``days`` days (actual/365).

    The caller passes only the principal (purchases and cash advances). Unpaid charges, fees
    and taxes are never part of the base: RBI Credit Card Directions 2025, no capitalisation.
    Rounded half-up to the paisa.
    """
    _non_negative("principal_paise", principal_paise)
    if annual_rate_pct < 0:
        raise ValueError("annual_rate_pct must be >= 0")
    if days < 0:
        raise ValueError("days must be >= 0")
    raw = Decimal(principal_paise) * annual_rate_pct / 100 * days / DAYS_IN_YEAR
    return _round_half_up(raw)


# --- Minimum amount due ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class StatementComponents:
    """What a statement's total amount due is made of (all paise)."""

    principal_paise: int  # purchases + cash advances still unpaid
    interest_paise: int
    fees_paise: int  # late fee, other charges
    taxes_paise: int  # GST on interest and fees
    emi_due_paise: int = 0  # instalment of an existing EMI plan billed this cycle

    def __post_init__(self) -> None:
        for name in ("principal_paise", "interest_paise", "fees_paise", "taxes_paise"):
            _non_negative(name, getattr(self, name))
        _non_negative("emi_due_paise", self.emi_due_paise)

    @property
    def total_due_paise(self) -> int:
        return (
            self.principal_paise
            + self.interest_paise
            + self.fees_paise
            + self.taxes_paise
            + self.emi_due_paise
        )

    @property
    def non_principal_paise(self) -> int:
        return self.interest_paise + self.fees_paise + self.taxes_paise + self.emi_due_paise


def minimum_amount_due(
    components: StatementComponents, principal_pct: Decimal, floor_paise: int
) -> int:
    """Minimum amount due (MAD) for a statement, without negative amortisation.

    ``MAD = non-principal components + max(principal_pct% of principal, floor)``, capped at the
    total amount due. Because every interest, fee, tax and EMI component is always inside the
    MAD, paying the MAD never makes the balance grow. RBI Credit Card Directions 2025.

    ``principal_pct`` and ``floor_paise`` are bank policy assumptions.
    """
    if principal_pct < 0 or principal_pct > 100:
        raise ValueError("principal_pct must be between 0 and 100")
    _non_negative("floor_paise", floor_paise)
    principal_part = max(
        _round_half_up(Decimal(components.principal_paise) * principal_pct / 100), floor_paise
    )
    principal_part = min(principal_part, components.principal_paise)
    return min(components.non_principal_paise + principal_part, components.total_due_paise)
