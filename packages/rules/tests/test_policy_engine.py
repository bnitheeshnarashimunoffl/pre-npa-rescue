"""Tests for npa_rules.policy_engine (PolicyProvider) including the Priya and Ravi personas."""

from datetime import UTC, datetime, timedelta

import pytest

from npa_contracts.enums import Actor, Bucket, OfferStatus, ReliefType
from npa_contracts.models import Affordability
from npa_contracts.providers import PolicyProvider
from npa_rules.personas import PRIYA, PRIYA_DECLARED, RAVI, RAVI_DECLARED
from npa_rules.policy_engine import PolicyEngine, UnknownOptionError
from npa_rules.policy_loader import Policy
from npa_rules.relief_calc import AccountSnapshot, estimate_affordability

NOW = datetime(2026, 10, 12, 5, 30, tzinfo=UTC)
ORDER = [
    ReliefType.INSURANCE_REFERRAL,
    ReliefType.FEE_WAIVER,
    ReliefType.EMI_CONVERSION,
    ReliefType.RESTRUCTURING,
    ReliefType.COMPROMISE_SETTLEMENT,
    ReliefType.REVIEW_DATE,
]


@pytest.fixture
def engine(policy: Policy, accounts: dict[str, AccountSnapshot]) -> PolicyEngine:
    return PolicyEngine(
        policy, accounts.__getitem__, clock=lambda: NOW, id_factory=lambda: "OFFER-x"
    )


def afford(policy: Policy, ctx: AccountSnapshot, declared: dict[str, int | None]) -> Affordability:
    return estimate_affordability(ctx, declared, policy.affordability)


def capacity(customer_id: str, paise: int) -> Affordability:
    return Affordability(
        customer_id=customer_id,
        declared_income_paise=None,
        declared_expenses_paise=None,
        dependants=None,
        max_monthly_payment_paise=paise,
        source="estimated",
    )


def test_engine_satisfies_protocol(engine: PolicyEngine) -> None:
    provider: PolicyProvider = engine
    assert provider.grievance_officer().email == "gro@demobank.example"


def test_priya_gets_fee_waiver_plus_six_month_plan(engine: PolicyEngine, policy: Policy) -> None:
    opts = engine.relief_options(PRIYA.customer_id, afford(policy, PRIYA, PRIYA_DECLARED))
    assert [o.type for o in opts] == [ReliefType.FEE_WAIVER, ReliefType.EMI_CONVERSION]
    plan = opts[1]
    assert (plan.monthly_amount_paise, plan.tenure_months, plan.waiver_paise) == (
        200_000,
        6,
        153_400,
    )
    assert plan.option_id == "OPT-ACC-DEMO-PRIYA-EMI6-WAIVER"
    assert not plan.requires_human_approval
    assert "disc.emi.principal_interest_shown" in plan.disclosure_keys
    assert "disc.fee_waiver.stops_growth" in plan.disclosure_keys
    assert plan.policy_ref == "bank_policy.yaml#emi_conversion.v1+fee_waiver.v1"


def test_ravi_zero_capacity_set_insurance_first(engine: PolicyEngine, policy: Policy) -> None:
    opts = engine.relief_options(RAVI.customer_id, afford(policy, RAVI, RAVI_DECLARED))
    assert [o.type for o in opts] == [
        ReliefType.INSURANCE_REFERRAL,
        ReliefType.FEE_WAIVER,
        ReliefType.RESTRUCTURING,
        ReliefType.REVIEW_DATE,
    ]
    assert all(o.monthly_amount_paise is None for o in opts)
    assert all(o.requires_human_approval for o in opts[2:])
    assert "disc.restructuring.npa_downgrade" in opts[2].disclosure_keys


@pytest.mark.parametrize("dpd", [0, 12, 45, 75, 120])
@pytest.mark.parametrize("cap", [0, 50_000, 240_000, 5_000_000])
def test_invariants_any_account(policy: Policy, dpd: int, cap: int) -> None:
    ctx = PRIYA.model_copy(
        update={"dpd": dpd, "has_card_insurance": True, "insurance_cover_type": "both"}
    )
    eng = PolicyEngine(policy, {ctx.customer_id: ctx}.__getitem__)
    opts = eng.relief_options(ctx.customer_id, capacity(ctx.customer_id, cap))
    types = [o.type for o in opts]
    assert types == sorted(types, key=ORDER.index), "least harmful first"
    for o in opts:
        # Never an instalment above what the customer can afford.
        if o.monthly_amount_paise is not None:
            assert o.monthly_amount_paise <= cap
        assert o.disclosure_keys and o.regulatory_refs and o.policy_ref.startswith("bank_policy")
        if o.type in (ReliefType.RESTRUCTURING, ReliefType.COMPROMISE_SETTLEMENT):
            assert o.requires_human_approval
    if cap == 0:
        assert ReliefType.EMI_CONVERSION not in types
        assert ReliefType.REVIEW_DATE in types


def test_full_balance_emi_when_affordable(engine: PolicyEngine) -> None:
    opts = engine.relief_options(PRIYA.customer_id, capacity(PRIYA.customer_id, 5_000_000))
    emi = next(o for o in opts if o.type is ReliefType.EMI_CONVERSION)
    assert emi.tenure_months == 3
    assert "full outstanding" in emi.eligibility_reason


def test_npa_settlement_sized_within_window(policy: Policy) -> None:
    ctx = RAVI.model_copy(update={"dpd": 120, "has_card_insurance": False})
    assert ctx.bucket is Bucket.NPA
    eng = PolicyEngine(policy, {ctx.customer_id: ctx}.__getitem__)
    opts = eng.relief_options(ctx.customer_id, capacity(ctx.customer_id, 2_000_000))
    settle = next(o for o in opts if o.type is ReliefType.COMPROMISE_SETTLEMENT)
    assert settle.settlement_amount_paise == 3_888_000  # 60% of Rs 64,800
    assert settle.tenure_months == 2
    assert settle.monthly_amount_paise == 1_944_000
    restructure = next(o for o in opts if o.type is ReliefType.RESTRUCTURING)
    assert restructure.monthly_amount_paise is not None
    assert ReliefType.FEE_WAIVER not in [o.type for o in opts]  # npa is not eligible


def test_settlement_needs_officer_when_unaffordable(policy: Policy) -> None:
    ctx = RAVI.model_copy(update={"dpd": 75})
    eng = PolicyEngine(policy, {ctx.customer_id: ctx}.__getitem__)
    opts = eng.relief_options(ctx.customer_id, capacity(ctx.customer_id, 0))
    settle = next(o for o in opts if o.type is ReliefType.COMPROMISE_SETTLEMENT)
    assert settle.monthly_amount_paise is None and settle.requires_human_approval


def test_fee_waiver_limited_per_12_months(policy: Policy) -> None:
    ctx = PRIYA.model_copy(update={"fee_waivers_last_12m": 1})
    eng = PolicyEngine(policy, {ctx.customer_id: ctx}.__getitem__)
    opts = eng.relief_options(ctx.customer_id, afford(policy, ctx, PRIYA_DECLARED))
    assert ReliefType.FEE_WAIVER not in [o.type for o in opts]
    # Without a waiver the plan also covers the charges.
    emi = next(o for o in opts if o.type is ReliefType.EMI_CONVERSION)
    assert emi.waiver_paise is None
    assert "plus charges" in emi.eligibility_reason


def test_disabled_option_never_offered(policy: Policy) -> None:
    data = policy.model_dump()
    data["options"]["fee_waiver"]["enabled"] = False
    eng = PolicyEngine(Policy.model_validate(data), {PRIYA.customer_id: PRIYA}.__getitem__)
    opts = eng.relief_options(PRIYA.customer_id, afford(policy, PRIYA, PRIYA_DECLARED))
    assert all(o.waiver_paise is None for o in opts)


def test_no_emi_when_nothing_fits(engine: PolicyEngine) -> None:
    opts = engine.relief_options(PRIYA.customer_id, capacity(PRIYA.customer_id, 50_000))
    assert ReliefType.EMI_CONVERSION not in [o.type for o in opts]


def test_affordability_for_other_customer_rejected(engine: PolicyEngine) -> None:
    with pytest.raises(ValueError):
        engine.relief_options(PRIYA.customer_id, capacity(RAVI.customer_id, 0))


def test_propose_offer_auto_approved(engine: PolicyEngine, policy: Policy) -> None:
    engine.relief_options(PRIYA.customer_id, afford(policy, PRIYA, PRIYA_DECLARED))
    offer = engine.propose_offer(PRIYA.customer_id, "OPT-ACC-DEMO-PRIYA-EMI6-WAIVER", Actor.BOT)
    assert offer.status is OfferStatus.APPROVED
    assert offer.account_id == "ACC-DEMO-PRIYA"
    assert offer.approved_by == "policy_engine"
    assert offer.offer_id == "OFFER-x"
    assert offer.expires_at - offer.created_at == timedelta(days=7)


def test_propose_offer_needs_human(engine: PolicyEngine, policy: Policy) -> None:
    engine.relief_options(RAVI.customer_id, afford(policy, RAVI, RAVI_DECLARED))
    offer = engine.propose_offer(RAVI.customer_id, "OPT-ACC-DEMO-RAVI-REVIEW-DATE", Actor.BOT)
    assert offer.status is OfferStatus.PROPOSED
    assert offer.approved_by is None


def test_propose_unknown_option_rejected(engine: PolicyEngine) -> None:
    with pytest.raises(UnknownOptionError):
        engine.propose_offer(PRIYA.customer_id, "OPT-INVENTED-PAYMENT-HOLIDAY", Actor.BOT)


def test_reload_forgets_issued_options(engine: PolicyEngine, policy: Policy) -> None:
    engine.relief_options(PRIYA.customer_id, afford(policy, PRIYA, PRIYA_DECLARED))
    engine.reload(policy)
    assert engine.policy is policy
    with pytest.raises(UnknownOptionError):
        engine.propose_offer(PRIYA.customer_id, "OPT-ACC-DEMO-PRIYA-FEE-WAIVER", Actor.BOT)


def test_default_offer_ids_and_clock(accounts: dict[str, AccountSnapshot], policy: Policy) -> None:
    eng = PolicyEngine.from_path(None, accounts.__getitem__)
    eng.relief_options(RAVI.customer_id, afford(policy, RAVI, RAVI_DECLARED))
    offer = eng.propose_offer(RAVI.customer_id, "OPT-ACC-DEMO-RAVI-INSURANCE", Actor.BOT)
    assert offer.offer_id.startswith("OFFER-") and len(offer.offer_id) == 42
    assert offer.created_at.tzinfo is not None
