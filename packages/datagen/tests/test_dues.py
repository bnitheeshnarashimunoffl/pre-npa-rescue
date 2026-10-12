"""Property tests for the RBI dues arithmetic, and scalar/vector agreement."""

from datetime import date, timedelta

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from datagen import dues
from npa_contracts.enums import Bucket

POLICY = dues.DEFAULT_POLICY
paise = st.integers(min_value=0, max_value=10**10)
dpds = st.integers(min_value=0, max_value=400)


@given(paise, dpds)
def test_no_late_fee_within_grace(outstanding: int, dpd: int) -> None:
    fee = dues.late_fee(outstanding, dpd, POLICY.late_fee_slabs)
    if dpd <= 3:  # RBI: only after past due for more than 3 days
        assert fee == 0
    assert 0 <= fee <= outstanding


@given(paise)
def test_late_fee_is_slab_on_post_due_outstanding(outstanding: int) -> None:
    fee = dues.late_fee(outstanding, 10, POLICY.late_fee_slabs)
    expected = next(
        s.fee_paise
        for s in POLICY.late_fee_slabs
        if s.up_to_paise is None or outstanding <= s.up_to_paise
    )
    assert fee == min(expected, outstanding)


@given(st.lists(st.tuples(paise, dpds), min_size=1, max_size=50))
def test_late_fee_vec_matches_scalar(cases: list[tuple[int, int]]) -> None:
    out = np.array([c[0] for c in cases], dtype=np.int64)
    dpd = np.array([c[1] for c in cases], dtype=np.int64)
    vec = dues.late_fee_vec(out, dpd, POLICY.late_fee_slabs)
    assert vec.tolist() == [dues.late_fee(o, d, POLICY.late_fee_slabs) for o, d in cases]


@given(paise, st.integers(0, 10_000), st.integers(0, 62))
def test_interest_vec_matches_scalar_and_is_monotone(principal: int, bp: int, days: int) -> None:
    scalar = dues.interest_for_period(principal, bp, days)
    vec = dues.interest_vec(np.array([principal]), bp, np.array([days]))
    assert vec[0] == scalar
    assert scalar >= 0
    assert dues.interest_for_period(principal + 100, bp, days) >= scalar


@given(paise, paise)
def test_mad_covers_non_principal_and_never_exceeds_total(principal: int, other: int) -> None:
    mad = dues.minimum_amount_due(principal, other, POLICY.mad_principal_bp, POLICY.mad_floor_paise)
    # No negative amortisation: interest, fees and taxes are always inside the MAD.
    assert other <= mad <= principal + other
    vec = dues.minimum_amount_due_vec(
        np.array([principal]), np.array([other]), POLICY.mad_principal_bp, POLICY.mad_floor_paise
    )
    assert vec[0] == mad


@given(paise)
def test_gst_vec_matches_scalar(amount: int) -> None:
    assert dues.gst_vec(np.array([amount]), POLICY.gst_bp)[0] == dues.gst(amount, POLICY.gst_bp)


def test_interest_half_up_rounding() -> None:
    # 36500 paise at 10% for 1 day = 10 paise exactly; 18250 -> 5 paise
    assert dues.interest_for_period(36_500, 1000, 1) == 10
    assert dues.interest_for_period(18_250, 1000, 1) == 5
    assert dues.interest_for_period(1_825, 1000, 1) == 1  # 0.5 rounds up


@pytest.mark.parametrize(
    ("dpd", "bucket"),
    [
        (0, Bucket.CURRENT),
        (1, Bucket.SMA0),
        (30, Bucket.SMA0),
        (31, Bucket.SMA1),
        (60, Bucket.SMA1),
        (61, Bucket.SMA2),
        (90, Bucket.SMA2),
        (91, Bucket.NPA),
    ],
)
def test_bucket_boundaries(dpd: int, bucket: Bucket) -> None:
    assert dues.bucket(dpd) is bucket
    assert dues.is_npa(dpd) is (dpd > 90)


def test_days_past_due() -> None:
    due = date(2026, 9, 20)
    assert dues.days_past_due(None, due) == 0
    assert dues.days_past_due(due, due - timedelta(days=5)) == 0
    assert dues.days_past_due(due, due + timedelta(days=4)) == 4
    assert not dues.is_past_due(3)
    assert dues.is_past_due(4)


@pytest.mark.parametrize(
    "call",
    [
        lambda: dues.late_fee(-1, 5, POLICY.late_fee_slabs),
        lambda: dues.interest_for_period(-5, 100, 1),
        lambda: dues.is_past_due(-1),
        lambda: dues.minimum_amount_due(100, -1, 500, 0),
    ],
)
def test_rejects_negative_inputs(call: object) -> None:
    with pytest.raises(ValueError):
        call()  # type: ignore[operator]


def test_rejects_float_money() -> None:
    with pytest.raises(TypeError):
        dues.gst(1.5, 1800)  # type: ignore[arg-type]


def test_policy_requires_open_ended_last_slab() -> None:
    with pytest.raises(ValueError):
        dues.DuesPolicy(late_fee_slabs=(dues.LateFeeSlab(100, 10),))
