"""Tests for npa_rules.relief_calc: affordability, EMI sizing, waiver, settlement."""

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from npa_rules.personas import PRIYA, PRIYA_DECLARED, RAVI, RAVI_DECLARED
from npa_rules.policy_loader import Policy
from npa_rules.relief_calc import (
    AccountSnapshot,
    emi_amount,
    emi_schedule,
    estimate_affordability,
    size_emi,
    size_settlement,
    size_waiver,
)

# --- affordability ---------------------------------------------------------------------------


def test_declared_affordability_formula(policy: Policy) -> None:
    a = estimate_affordability(PRIYA, PRIYA_DECLARED, policy.affordability)
    # (20,000 - 9,000 - 3,000 x 1) x 0.3 = Rs 2,400
    assert a.max_monthly_payment_paise == 240_000
    assert a.source == "declared"
    assert a.dependants == 1


def test_declared_zero_capacity(policy: Policy) -> None:
    a = estimate_affordability(RAVI, RAVI_DECLARED, policy.affordability)
    assert a.max_monthly_payment_paise == 0


def test_declared_dependants_default_to_profile(policy: Policy) -> None:
    a = estimate_affordability(
        RAVI, {"income_paise": 5_000_000, "expenses_paise": 1_000_000}, policy.affordability
    )
    # (50,000 - 10,000 - 3 x 3,000) x 0.3 = Rs 9,300
    assert a.max_monthly_payment_paise == 930_000


def test_estimated_uses_demonstrated_payments(policy: Policy) -> None:
    a = estimate_affordability(PRIYA, None, policy.affordability)
    assert a.source == "estimated"
    assert a.max_monthly_payment_paise == PRIYA.avg_payment_3m_paise


def test_estimated_from_profile_income_when_no_salary_feed(policy: Policy) -> None:
    ctx = AccountSnapshot(
        customer_id="C",
        account_id="A",
        dpd=0,
        total_outstanding_paise=0,
        overdue_paise=0,
        waivable_charges_paise=0,
        monthly_income_paise=5_000_000,
    )
    # 50,000 - 60% essentials = 20,000; x 0.3 = Rs 6,000
    assert estimate_affordability(ctx, None, policy.affordability).max_monthly_payment_paise == (
        600_000
    )


def test_estimated_zero_for_ravi(policy: Policy) -> None:
    assert estimate_affordability(RAVI, None, policy.affordability).max_monthly_payment_paise == 0


@given(
    st.integers(0, 10**9), st.integers(0, 10**9), st.integers(0, 10), st.just(None)
)  # fmt: skip
def test_affordability_never_negative_or_above_surplus(
    income: int, expenses: int, deps: int, _: None
) -> None:
    from npa_rules.policy_loader import load_policy

    pol = load_policy().affordability
    a = estimate_affordability(
        PRIYA, {"income_paise": income, "expenses_paise": expenses, "dependants": deps}, pol
    )
    assert 0 <= a.max_monthly_payment_paise <= max(0, income - expenses)


def test_snapshot_from_context_ignores_extra_keys() -> None:
    ctx = PRIYA.model_dump() | {"full_name": "Priya Raman", "phone_masked": "******1234"}
    assert AccountSnapshot.from_context(ctx) == PRIYA


# --- EMI -------------------------------------------------------------------------------------


def test_priya_emi_is_exactly_two_thousand() -> None:
    assert emi_amount(1_149_200, 6, Decimal("15")) == 200_000


def test_emi_zero_rate_rounds_up() -> None:
    assert emi_amount(1_000, 3, Decimal("0")) == 334


@pytest.mark.parametrize(
    ("p", "n", "r"), [(-1, 3, Decimal(1)), (1, 0, Decimal(1)), (1, 3, Decimal(-1))]
)
def test_emi_rejects_bad_input(p: int, n: int, r: Decimal) -> None:
    with pytest.raises(ValueError):
        emi_amount(p, n, r)


@given(
    st.integers(10_000, 10**9),  # realistic plans (>= Rs 100)
    st.sampled_from([3, 6, 9, 12, 24, 36]),
    st.sampled_from([Decimal(0), Decimal("12"), Decimal("15"), Decimal("42")]),
)
def test_schedule_repays_principal_exactly(p: int, n: int, rate: Decimal) -> None:
    plan = emi_schedule(p, n, rate)
    assert sum(i.principal_paise for i in plan.schedule) == p
    assert all(i.principal_paise >= 0 and i.interest_paise >= 0 for i in plan.schedule)
    assert len(plan.schedule) == n
    # Only the last instalment may differ from the EMI, and only by rounding.
    assert all(i.amount_paise == plan.emi_paise for i in plan.schedule[:-1])
    # <= 1 paisa of rounding drift per month, compounded at <= 3.5% a month over <= 36 months
    assert abs(plan.schedule[-1].amount_paise - plan.emi_paise) <= 4 * n


def test_size_emi_picks_shortest_affordable_tenure(policy: Policy) -> None:
    plan = size_emi(1_149_200, 240_000, policy.options.emi_conversion)
    assert plan is not None
    assert (plan.tenure_months, plan.emi_paise) == (6, 200_000)


def test_size_emi_none_when_unaffordable(policy: Policy) -> None:
    assert size_emi(11_000_000, 240_000, policy.options.emi_conversion) is None
    assert size_emi(1_149_200, 0, policy.options.emi_conversion) is None


def test_size_emi_skips_tenures_below_minimum(policy: Policy) -> None:
    # Rs 2,000 over 3 months is Rs 680 < Rs 1,000 minimum EMI -> no plan
    assert size_emi(200_000, 10**9, policy.options.emi_conversion) is None


@given(st.integers(1, 10**8), st.integers(0, 10**7))
def test_size_emi_never_exceeds_affordable(principal: int, affordable: int) -> None:
    from npa_rules.policy_loader import load_policy

    plan = size_emi(principal, affordable, load_policy().options.emi_conversion)
    if plan is not None:
        assert plan.emi_paise <= affordable


# --- waiver / settlement ---------------------------------------------------------------------


def test_waiver_capped(policy: Policy) -> None:
    assert size_waiver(PRIYA, policy.options.fee_waiver) == 153_400
    big = PRIYA.model_copy(update={"waivable_charges_paise": 10**7})
    assert size_waiver(big, policy.options.fee_waiver) == policy.options.fee_waiver.max_waiver_paise


def test_settlement_rounds_up() -> None:
    assert size_settlement(1_001, Decimal("40")) == 601  # 600.6 -> 601


def test_settlement_rejects_bad_input() -> None:
    with pytest.raises(ValueError):
        size_settlement(-1, Decimal("40"))
    with pytest.raises(ValueError):
        size_settlement(1, Decimal("101"))


@given(st.integers(0, 10**10), st.decimals(min_value=0, max_value=100, places=2))
def test_settlement_sacrifice_within_cap(outstanding: int, pct: Decimal) -> None:
    amount = size_settlement(outstanding, pct)
    assert amount <= outstanding
    assert (outstanding - amount) * 100 <= pct * outstanding
