"""Tests for npa_rules.dues: examples plus hypothesis properties for the RBI money rules."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from npa_contracts.constants import NPA_DPD, PAST_DUE_GRACE_DAYS
from npa_contracts.enums import Bucket
from npa_rules.dues import (
    LateFeeSlab,
    StatementComponents,
    bucket,
    days_past_due,
    interest_for_period,
    is_npa,
    is_past_due,
    late_fee,
    minimum_amount_due,
)

SLABS = (
    LateFeeSlab(up_to_paise=50_000, fee_paise=0),
    LateFeeSlab(up_to_paise=500_000, fee_paise=50_000),
    LateFeeSlab(up_to_paise=2_500_000, fee_paise=100_000),
    LateFeeSlab(up_to_paise=None, fee_paise=130_000),
)

paise = st.integers(min_value=0, max_value=10**11)
dpds = st.integers(min_value=0, max_value=400)
components = st.builds(
    StatementComponents,
    principal_paise=paise,
    interest_paise=paise,
    fees_paise=paise,
    taxes_paise=paise,
    emi_due_paise=paise,
)


# --- DPD / bucket ----------------------------------------------------------------------------


def test_days_past_due_counts_from_due_date() -> None:
    assert days_past_due(date(2026, 9, 5), date(2026, 9, 17)) == 12


def test_days_past_due_zero_when_nothing_unpaid_or_not_yet_due() -> None:
    assert days_past_due(None, date(2026, 9, 17)) == 0
    assert days_past_due(date(2026, 9, 20), date(2026, 9, 17)) == 0


@pytest.mark.parametrize(
    ("dpd", "expected"),
    [(0, Bucket.CURRENT), (1, Bucket.SMA0), (30, Bucket.SMA0), (31, Bucket.SMA1),
     (60, Bucket.SMA1), (61, Bucket.SMA2), (90, Bucket.SMA2), (91, Bucket.NPA)],
)  # fmt: skip
def test_bucket_boundaries(dpd: int, expected: Bucket) -> None:
    assert bucket(dpd) is expected


def test_past_due_needs_more_than_three_days() -> None:
    assert not is_past_due(PAST_DUE_GRACE_DAYS)
    assert is_past_due(PAST_DUE_GRACE_DAYS + 1)


def test_npa_only_after_ninety_days() -> None:
    assert not is_npa(NPA_DPD)
    assert is_npa(NPA_DPD + 1)


def test_negative_dpd_is_rejected() -> None:
    with pytest.raises(ValueError):
        is_npa(-1)


@given(st.dates(), st.integers(min_value=0, max_value=1000))
def test_dpd_property(due: date, delta: int) -> None:
    assert days_past_due(due, due + timedelta(days=delta)) == delta


@given(dpds)
def test_npa_iff_bucket_npa(dpd: int) -> None:
    assert is_npa(dpd) == (bucket(dpd) is Bucket.NPA)


# --- Late fee --------------------------------------------------------------------------------


def test_late_fee_uses_post_due_outstanding_slab() -> None:
    # Rs 3,000 still unpaid after the due date -> Rs 500 slab, whatever the total due was.
    assert late_fee(300_000, dpd=10, slabs=SLABS) == 50_000


def test_no_late_fee_within_grace() -> None:
    assert late_fee(300_000, dpd=PAST_DUE_GRACE_DAYS, slabs=SLABS) == 0


def test_late_fee_open_ended_slab() -> None:
    assert late_fee(10**9, dpd=40, slabs=SLABS) == 130_000


def test_late_fee_requires_open_ended_slab() -> None:
    with pytest.raises(ValueError):
        late_fee(100, dpd=10, slabs=(LateFeeSlab(up_to_paise=1000, fee_paise=10),))


def test_late_fee_rejects_float() -> None:
    with pytest.raises(TypeError):
        late_fee(100.0, dpd=10, slabs=SLABS)  # type: ignore[arg-type]


@given(paise, dpds)
def test_late_fee_properties(outstanding: int, dpd: int) -> None:
    fee = late_fee(outstanding, dpd, SLABS)
    assert 0 <= fee <= outstanding
    if dpd <= PAST_DUE_GRACE_DAYS:
        assert fee == 0


@given(paise, paise, dpds)
def test_late_fee_monotonic_in_outstanding(a: int, b: int, dpd: int) -> None:
    lo, hi = sorted((a, b))
    assert late_fee(lo, dpd, SLABS) <= late_fee(hi, dpd, SLABS)


# --- Interest --------------------------------------------------------------------------------


def test_interest_simple_actual_365() -> None:
    # Rs 1,00,000 at 36% p.a. for 30 days = Rs 2,958.90 (rounded half-up to the paisa)
    assert interest_for_period(10_000_000, Decimal("36"), 30) == 295_890


def test_interest_zero_days_or_rate() -> None:
    assert interest_for_period(10_000_000, Decimal("36"), 0) == 0
    assert interest_for_period(10_000_000, Decimal("0"), 30) == 0


def test_interest_rejects_negative_inputs() -> None:
    with pytest.raises(ValueError):
        interest_for_period(-1, Decimal("36"), 30)
    with pytest.raises(ValueError):
        interest_for_period(1, Decimal("-1"), 30)
    with pytest.raises(ValueError):
        interest_for_period(1, Decimal("1"), -1)


@given(paise, paise, st.integers(min_value=0, max_value=62))
def test_interest_is_additive_up_to_rounding(a: int, b: int, days: int) -> None:
    rate = Decimal("42")
    total = interest_for_period(a + b, rate, days)
    assert abs(total - interest_for_period(a, rate, days) - interest_for_period(b, rate, days)) <= 1


# --- Minimum amount due ----------------------------------------------------------------------


def test_mad_covers_charges_plus_principal_share() -> None:
    c = StatementComponents(
        principal_paise=10_000_000, interest_paise=300_000, fees_paise=50_000, taxes_paise=63_000
    )
    # 5% of Rs 1,00,000 = Rs 5,000 + Rs 3,000 + Rs 500 + Rs 630
    assert minimum_amount_due(c, Decimal("5"), floor_paise=20_000) == 913_000


def test_mad_floor_capped_by_total_due() -> None:
    c = StatementComponents(principal_paise=5_000, interest_paise=0, fees_paise=0, taxes_paise=0)
    assert minimum_amount_due(c, Decimal("5"), floor_paise=20_000) == 5_000


def test_mad_rejects_bad_pct() -> None:
    c = StatementComponents(principal_paise=1, interest_paise=0, fees_paise=0, taxes_paise=0)
    with pytest.raises(ValueError):
        minimum_amount_due(c, Decimal("101"), floor_paise=0)


def test_components_reject_negative() -> None:
    with pytest.raises(ValueError):
        StatementComponents(principal_paise=-1, interest_paise=0, fees_paise=0, taxes_paise=0)


@given(components, st.decimals(min_value=0, max_value=100, places=2), paise)
def test_mad_no_negative_amortisation(c: StatementComponents, pct: Decimal, floor: int) -> None:
    mad = minimum_amount_due(c, pct, floor)
    assert mad <= c.total_due_paise
    # Paying the MAD always clears every non-principal component: the balance never grows.
    assert mad >= c.non_principal_paise
    assert c.total_due_paise - mad <= c.principal_paise
