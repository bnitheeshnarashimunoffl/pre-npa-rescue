"""Relief and affordability calculator (task 3.2): affordability, EMI, waiver, settlement.

Pure functions over integer paise. Every numeric parameter (affordability ratio, dependant
allowance, rates, caps) is a **bank policy assumption** read from ``bank_policy.yaml``.

Rounding (documented, A9):

* Affordability is rounded **down** to the paisa: the bank never overstates what a customer
  can pay.
* EMI uses the standard amortising formula ``P·r·(1+r)^n / ((1+r)^n − 1)`` with
  ``r = annual% / 12 / 100``, rounded half-up to the paisa. Each instalment's interest is
  rounded half-up; the **last** instalment absorbs the rounding remainder so the principal
  repaid equals ``P`` exactly (never negative amortisation).
* A settlement amount is rounded **up** to the paisa, so the sacrifice never exceeds
  ``max_sacrifice_pct``.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal, localcontext
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from npa_contracts.enums import Bucket
from npa_contracts.models import Affordability
from npa_rules.dues import bucket
from npa_rules.policy_loader import AffordabilityPolicy, EmiPolicy, FeeWaiverPolicy

__all__ = [
    "AccountSnapshot",
    "EmiPlan",
    "Instalment",
    "emi_amount",
    "emi_schedule",
    "estimate_affordability",
    "size_emi",
    "size_settlement",
    "size_waiver",
]


class AccountSnapshot(BaseModel):
    """What the rules engine needs to know about one customer's card account.

    Supplied by WS5 (from the DB / ``CustomerContextProvider``) through an injected callable;
    ``npa_rules`` never reads a database. Never contains protected attributes.
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    customer_id: str
    account_id: str
    dpd: int = Field(ge=0)
    total_outstanding_paise: int = Field(ge=0)
    overdue_paise: int = Field(ge=0, description="Unpaid minimum amounts due, excluding charges.")
    waivable_charges_paise: int = Field(ge=0, description="Late/penal charges incl. their GST.")
    monthly_income_paise: int | None = Field(default=None, ge=0)
    recent_income_paise: int | None = Field(
        default=None, ge=0, description="Income actually credited last month (salary feed)."
    )
    avg_payment_3m_paise: int = Field(default=0, ge=0)
    dependants: int = Field(default=0, ge=0)
    has_card_insurance: bool = False
    insurance_cover_type: str = "none"  # none / job_loss / death_disability / both
    fee_waivers_last_12m: int = Field(default=0, ge=0)
    do_not_contact_flags: tuple[str, ...] = ()
    avoid_contact_windows: tuple[str, ...] = Field(
        default=(), description='Customer-requested quiet times, e.g. "13:00-15:00" (IST).'
    )

    @property
    def bucket(self) -> Bucket:
        return bucket(self.dpd)

    @classmethod
    def from_context(cls, ctx: dict[str, Any]) -> AccountSnapshot:
        """Build from a ``CustomerContextProvider.context()`` dict (unknown keys ignored)."""
        return cls.model_validate(ctx)


# --- Affordability ---------------------------------------------------------------------------


def _floor(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_FLOOR))


def estimate_affordability(
    ctx: AccountSnapshot, declared: dict[str, int | None] | None, policy: AffordabilityPolicy
) -> Affordability:
    """Maximum monthly payment a plan may ask for.

    With a declaration from the chat (``income_paise``, ``expenses_paise``, ``dependants``)::

        max_monthly = max(0, income − essential_expenses − allowance × dependants) × ratio

    Without one, an estimate (``source="estimated"``; the chatbot must confirm it with the
    customer before offering a plan): the same formula on the income actually credited last
    month, with essentials at ``estimated_essentials_pct`` of it, or the customer's average
    payment over the last 3 months if that is higher (demonstrated capacity).
    """
    ratio = policy.affordability_ratio
    allowance = policy.dependant_allowance_paise
    if declared is not None and declared.get("income_paise") is not None:
        income = int(declared["income_paise"] or 0)
        expenses = int(declared.get("expenses_paise") or 0)
        deps_raw = declared.get("dependants")
        deps = ctx.dependants if deps_raw is None else int(deps_raw)
        surplus = max(0, income - expenses - allowance * deps)
        return Affordability(
            customer_id=ctx.customer_id,
            declared_income_paise=income,
            declared_expenses_paise=expenses,
            dependants=deps,
            max_monthly_payment_paise=_floor(Decimal(surplus) * ratio),
            source="declared",
        )
    recent = ctx.recent_income_paise
    est_income = recent if recent is not None else (ctx.monthly_income_paise or 0)
    essentials = Decimal(est_income) * policy.estimated_essentials_pct / 100
    surplus_dec = max(Decimal(0), Decimal(est_income) - essentials - allowance * ctx.dependants)
    estimate = max(_floor(surplus_dec * ratio), ctx.avg_payment_3m_paise)
    return Affordability(
        customer_id=ctx.customer_id,
        declared_income_paise=None,
        declared_expenses_paise=None,
        dependants=ctx.dependants,
        max_monthly_payment_paise=estimate,
        source="estimated",
    )


# --- EMI -------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Instalment:
    number: int
    amount_paise: int
    principal_paise: int
    interest_paise: int


@dataclass(frozen=True, slots=True)
class EmiPlan:
    principal_paise: int
    tenure_months: int
    annual_rate_pct: Decimal
    emi_paise: int
    schedule: tuple[Instalment, ...]

    @property
    def total_interest_paise(self) -> int:
        return sum(i.interest_paise for i in self.schedule)


def emi_amount(principal_paise: int, tenure_months: int, annual_rate_pct: Decimal) -> int:
    """Standard amortising EMI, rounded half-up to the paisa (0% rate → ceil(P / n))."""
    if principal_paise < 0:
        raise ValueError("principal_paise must be >= 0")
    if tenure_months < 1:
        raise ValueError("tenure_months must be >= 1")
    if annual_rate_pct < 0:
        raise ValueError("annual_rate_pct must be >= 0")
    if annual_rate_pct == 0:
        return -(-principal_paise // tenure_months)
    with localcontext() as c:
        c.prec = 40
        r = annual_rate_pct / 1200
        growth = (1 + r) ** tenure_months
        raw = Decimal(principal_paise) * r * growth / (growth - 1)
        return int(raw.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def emi_schedule(principal_paise: int, tenure_months: int, annual_rate_pct: Decimal) -> EmiPlan:
    """Full schedule with each instalment's principal and interest (disclosure: the customer
    sees the split, ``disc.emi.principal_interest_shown``)."""
    emi = emi_amount(principal_paise, tenure_months, annual_rate_pct)
    r = annual_rate_pct / 1200
    balance = principal_paise
    rows: list[Instalment] = []
    for n in range(1, tenure_months + 1):
        interest = int((Decimal(balance) * r).quantize(Decimal(1), rounding=ROUND_HALF_UP))
        principal = balance if n == tenure_months else min(balance, emi - interest)
        rows.append(Instalment(n, principal + interest, principal, interest))
        balance -= principal
    return EmiPlan(principal_paise, tenure_months, annual_rate_pct, emi, tuple(rows))


def size_emi(principal_paise: int, affordable_paise: int, policy: EmiPolicy) -> EmiPlan | None:
    """Shortest policy tenure whose EMI fits ``affordable_paise`` and meets ``min_emi_paise``.

    Returns ``None`` when no tenure fits: an EMI above the affordable amount is never offered.
    """
    if principal_paise <= 0 or affordable_paise <= 0:
        return None
    for tenure in sorted(policy.tenures_months):
        emi = emi_amount(principal_paise, tenure, policy.interest_rate_annual_pct)
        if emi < policy.min_emi_paise:
            continue
        if emi <= affordable_paise:
            return emi_schedule(principal_paise, tenure, policy.interest_rate_annual_pct)
    return None


# --- Waiver and settlement -------------------------------------------------------------------


def size_waiver(ctx: AccountSnapshot, policy: FeeWaiverPolicy) -> int:
    """Late/penal charges (with their GST) the bank may waive, capped at ``max_waiver_paise``."""
    return min(ctx.waivable_charges_paise, policy.max_waiver_paise)


def size_settlement(outstanding_paise: int, max_sacrifice_pct: Decimal) -> int:
    """Lowest settlement amount the policy allows: the bank gives up at most
    ``max_sacrifice_pct`` of the outstanding. Rounded up to the paisa."""
    if outstanding_paise < 0:
        raise ValueError("outstanding_paise must be >= 0")
    if not 0 <= max_sacrifice_pct <= 100:
        raise ValueError("max_sacrifice_pct must be between 0 and 100")
    keep = Decimal(outstanding_paise) * (100 - max_sacrifice_pct) / 100
    return int(keep.to_integral_value(rounding=ROUND_CEILING))
