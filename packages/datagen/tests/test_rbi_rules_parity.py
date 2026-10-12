"""Parity with WS3's ``npa_rules.dues``: the synthetic statements and the rules engine must
agree on every number. Skipped until ``npa_rules.dues`` exists on main."""

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from datagen import dues

rules_dues = pytest.importorskip("npa_rules.dues")

POLICY = dues.DEFAULT_POLICY
paise = st.integers(min_value=0, max_value=10**10)


def _slabs() -> list[object]:
    return [rules_dues.LateFeeSlab(s.up_to_paise, s.fee_paise) for s in POLICY.late_fee_slabs]


@given(paise, st.integers(0, 400))
def test_late_fee_parity(outstanding: int, dpd: int) -> None:
    assert dues.late_fee(outstanding, dpd, POLICY.late_fee_slabs) == rules_dues.late_fee(
        outstanding, dpd, _slabs()
    )


@given(paise, st.integers(0, 62))
def test_interest_parity(principal: int, days: int) -> None:
    rate = Decimal(POLICY.annual_rate_bp) / 100
    assert dues.interest_for_period(
        principal, POLICY.annual_rate_bp, days
    ) == rules_dues.interest_for_period(principal, rate, days)


@given(paise, paise, paise, paise)
def test_minimum_amount_due_parity(principal: int, interest: int, fees: int, taxes: int) -> None:
    comp = rules_dues.StatementComponents(principal, interest, fees, taxes)
    pct = Decimal(POLICY.mad_principal_bp) / 100
    assert dues.minimum_amount_due(
        principal, interest + fees + taxes, POLICY.mad_principal_bp, POLICY.mad_floor_paise
    ) == rules_dues.minimum_amount_due(comp, pct, POLICY.mad_floor_paise)


@given(st.integers(0, 400))
def test_classification_parity(dpd: int) -> None:
    assert dues.bucket(dpd) == rules_dues.bucket(dpd)
    assert dues.is_npa(dpd) == rules_dues.is_npa(dpd)
    assert dues.is_past_due(dpd) == rules_dues.is_past_due(dpd)
