"""The demo personas match the canonical demo values and still produce the demo outcomes."""

from decimal import ROUND_HALF_UP, Decimal

import pytest

from npa_contracts.enums import Actor, Bucket, OfferStatus, ReliefType
from npa_rules.dues import late_fee
from npa_rules.personas import (
    PRIYA,
    PRIYA_DECLARED,
    PRIYA_OUTSTANDING_AFTER_DUE_PAISE,
    RAVI,
    RAVI_DECLARED,
)
from npa_rules.policy_engine import PolicyEngine
from npa_rules.policy_loader import Policy
from npa_rules.relief_calc import AccountSnapshot, estimate_affordability

GST_PCT = Decimal(18)  # GST on card charges (tax law, not an RBI or bank-policy number)


def test_priya_matches_canonical_demo_values() -> None:
    # WS1 demo_personas.json (task 1.1) / WS9 canonical values.
    assert PRIYA.total_outstanding_paise == 10_745_200  # Rs 1,07,452 total due
    assert PRIYA.overdue_paise == 1_149_200  # Rs 11,492
    assert PRIYA_OUTSTANDING_AFTER_DUE_PAISE == 9_251_900  # Rs 92,519
    assert PRIYA.waivable_charges_paise == 153_400  # Rs 1,534
    assert (PRIYA.dpd, PRIYA.bucket) == (16, Bucket.SMA0)


def test_ravi_matches_canonical_demo_values() -> None:
    assert (RAVI.dpd, RAVI.bucket) == (47, Bucket.SMA1)
    assert (RAVI.has_card_insurance, RAVI.insurance_cover_type) == (True, "job_loss")
    assert RAVI_DECLARED["income_paise"] == 0


@pytest.mark.parametrize(
    ("persona", "post_due_outstanding"),
    [(PRIYA, PRIYA_OUTSTANDING_AFTER_DUE_PAISE), (RAVI, RAVI.total_outstanding_paise)],
    ids=["priya", "ravi"],
)
def test_persona_charges_use_post_due_outstanding_slab(
    policy: Policy, persona: AccountSnapshot, post_due_outstanding: int
) -> None:
    # RBI Credit Card Directions 2025: the slab is chosen on the amount outstanding after the
    # due date (the whole unpaid balance), never on the overdue minimum amount.
    fee = late_fee(post_due_outstanding, persona.dpd, policy.charges.slabs())
    gst = int((Decimal(fee) * GST_PCT / 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    assert fee == 130_000
    assert persona.waivable_charges_paise == fee + gst == 153_400


def test_overdue_slab_would_have_been_lower(policy: Policy) -> None:
    # The old (wrong) persona figure: slab chosen on Priya's Rs 11,492 overdue amount.
    assert late_fee(PRIYA.overdue_paise, PRIYA.dpd, policy.charges.slabs()) == 100_000


@pytest.fixture
def engine(policy: Policy, accounts: dict[str, AccountSnapshot]) -> PolicyEngine:
    return PolicyEngine(policy, accounts.__getitem__)


def test_priya_still_gets_six_by_2000_fees_waived_auto_approved(
    engine: PolicyEngine, policy: Policy
) -> None:
    afford = estimate_affordability(PRIYA, PRIYA_DECLARED, policy.affordability)
    opts = engine.relief_options(PRIYA.customer_id, afford)
    plan = next(o for o in opts if o.type is ReliefType.EMI_CONVERSION)
    assert (plan.tenure_months, plan.monthly_amount_paise, plan.waiver_paise) == (
        6,
        200_000,
        153_400,
    )
    assert not plan.requires_human_approval
    offer = engine.propose_offer(PRIYA.customer_id, plan.option_id, Actor.BOT)
    assert offer.status is OfferStatus.APPROVED


def test_ravi_still_gets_only_insurance_waiver_and_officer_options(
    engine: PolicyEngine, policy: Policy
) -> None:
    afford = estimate_affordability(RAVI, RAVI_DECLARED, policy.affordability)
    opts = engine.relief_options(RAVI.customer_id, afford)
    assert [o.type for o in opts[:2]] == [ReliefType.INSURANCE_REFERRAL, ReliefType.FEE_WAIVER]
    assert opts[2:] and all(o.requires_human_approval for o in opts[2:])
    assert all(o.monthly_amount_paise is None for o in opts)
