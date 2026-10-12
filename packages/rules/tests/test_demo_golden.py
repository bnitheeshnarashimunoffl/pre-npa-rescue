"""Golden end-to-end test of the demo story (A1) through npa_rules, with StaticRiskProvider.

Each test walks one persona the way the demo does: NBA → affordability → relief options →
offer → texts shown to the customer. Every number and id is pinned, so any change to the
policy, the calculator or the personas that would change the demo fails here first.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from npa_contracts.enums import Actor, Channel, Lang, NextAction, OfferStatus, ReliefType
from npa_rules.compliance_guard import ComplianceGuard
from npa_rules.disclosures import disclosure_text
from npa_rules.nba import NextBestActionService, StaticRiskProvider
from npa_rules.personas import PRIYA, PRIYA_DECLARED, RAVI, RAVI_DECLARED
from npa_rules.policy_engine import PolicyEngine
from npa_rules.policy_loader import Policy
from npa_rules.relief_calc import emi_schedule, estimate_affordability

IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 10, 12, 11, tzinfo=IST)  # inside the 08:00-19:00 contact window
MONTH = "2026-09"
QUEUE_FIXTURE = Path(__file__).resolve().parents[3] / "contracts" / "fixtures" / "queue.json"


class Demo:
    """The three providers wired the way WS5 wires them, over the two personas."""

    def __init__(self, policy: Policy) -> None:
        by_customer = {PRIYA.customer_id: PRIYA, RAVI.customer_id: RAVI}
        by_account = {PRIYA.account_id: PRIYA, RAVI.account_id: RAVI}
        queue: dict[str, Any] = json.loads(QUEUE_FIXTURE.read_text(encoding="utf-8"))
        self.policy = policy
        self.engine = PolicyEngine(
            policy, by_customer.__getitem__, clock=lambda: NOW, id_factory=lambda: "OFFER-demo"
        )
        self.guard = ComplianceGuard(policy, lambda _c: [], by_customer.__getitem__)
        self.nba = NextBestActionService(
            policy,
            StaticRiskProvider.from_queue_fixture(queue),
            self.guard,
            by_account.__getitem__,
            policy_provider=self.engine,
            clock=lambda: NOW,
        )


@pytest.fixture
def demo(policy: Policy) -> Demo:
    return Demo(policy)


def test_priya_chat_invite_to_auto_approved_plan(demo: Demo) -> None:
    # 1. NBA: can't pay, persuadable, some capacity → chat invite with options ready.
    nba = demo.nba.next_best_action(PRIYA.account_id, MONTH)
    assert nba.action is NextAction.CHAT_INVITE
    assert nba.channel is Channel.CHAT
    assert nba.earliest_contact_at == NOW
    assert nba.reason_codes == [
        "SALARY_STOPPED",
        "MIN_DUE_ONLY_STREAK",
        "UTILISATION_RISING",
        "RULE_CANT_PAY_PERSUADABLE",
        "RELIEF_OPTIONS_READY",
    ]

    # 2. Before the chat, capacity is only estimated (3-month average payment, Rs 5,500).
    estimated = estimate_affordability(PRIYA, None, demo.policy.affordability)
    assert (estimated.source, estimated.max_monthly_payment_paise) == ("estimated", 550_000)

    # 3. In the chat she declares income Rs 20,000, essentials Rs 9,000, 1 dependant:
    #    (20,000 - 9,000 - 3,000) x 0.3 = Rs 2,400/month.
    afford = estimate_affordability(PRIYA, PRIYA_DECLARED, demo.policy.affordability)
    assert afford.source == "declared"
    assert afford.customer_id == "CUST-DEMO-PRIYA"
    assert (afford.declared_income_paise, afford.declared_expenses_paise) == (2_000_000, 900_000)
    assert afford.dependants == 1
    assert afford.max_monthly_payment_paise == 240_000

    # 4. Relief options, least harmful first: fee waiver, then the 6-month plan.
    waiver, plan = demo.engine.relief_options(PRIYA.customer_id, afford)
    assert waiver.option_id == "OPT-ACC-DEMO-PRIYA-FEE-WAIVER"
    assert waiver.type is ReliefType.FEE_WAIVER
    assert waiver.waiver_paise == 153_400
    assert (waiver.monthly_amount_paise, waiver.tenure_months) == (None, None)
    assert waiver.policy_ref == "bank_policy.yaml#fee_waiver.v1"
    assert waiver.disclosure_keys == ["disc.fee_waiver.stops_growth"]
    assert not waiver.requires_human_approval
    assert waiver.eligibility_reason == (
        "Account is sma0; 0 waiver(s) in the last 12 months (limit 1); late charges Rs 1,534 "
        "within the Rs 5,000 cap."
    )

    assert plan.option_id == "OPT-ACC-DEMO-PRIYA-EMI6-WAIVER"
    assert plan.type is ReliefType.EMI_CONVERSION
    assert (plan.monthly_amount_paise, plan.tenure_months, plan.waiver_paise) == (
        200_000,
        6,
        153_400,
    )
    assert plan.settlement_amount_paise is None
    assert plan.policy_ref == "bank_policy.yaml#emi_conversion.v1+fee_waiver.v1"
    assert plan.regulatory_refs == [
        "RBI Credit Card Directions 2025 - EMI transparency",
        "RBI Credit Card Directions 2025 - charges per board policy",
    ]
    assert plan.disclosure_keys == [
        "disc.emi.principal_interest_shown",
        "disc.fee_waiver.stops_growth",
    ]
    assert not plan.requires_human_approval
    assert plan.eligibility_reason == (
        "Rs 2,000/month for 6 months covers the overdue amount (Rs 11,492, total interest "
        "Rs 507.98 at 15.0% p.a.); shortest tenure within the affordable Rs 2,400/month; late "
        "charges of Rs 1,534 waived."
    )

    # The plan covers the overdue Rs 11,492 at 15% p.a.: Rs 2,000.00 exactly, Rs 507.98 interest.
    schedule = emi_schedule(
        PRIYA.overdue_paise, 6, demo.policy.options.emi_conversion.interest_rate_annual_pct
    )
    assert schedule.emi_paise == 200_000
    assert schedule.total_interest_paise == 50_798
    assert sum(i.principal_paise for i in schedule.schedule) == 1_149_200
    assert sum(i.amount_paise for i in schedule.schedule) == 1_149_200 + 50_798

    # 5. The bot proposes the plan; no human approval needed, so the policy engine approves it.
    offer = demo.engine.propose_offer(PRIYA.customer_id, plan.option_id, Actor.BOT)
    assert offer.offer_id == "OFFER-demo"
    assert (offer.customer_id, offer.account_id) == ("CUST-DEMO-PRIYA", "ACC-DEMO-PRIYA")
    assert offer.option == plan
    assert offer.status is OfferStatus.APPROVED
    assert offer.approved_by == "policy_engine"
    assert offer.proposed_by is Actor.BOT
    assert offer.created_at == NOW
    assert offer.expires_at == datetime(2026, 10, 19, 11, tzinfo=IST)  # 7-day expiry

    # 6. Everything shown with the offer passes the guard, in Tamil and English.
    for lang in (Lang.TA, Lang.EN):
        for key in plan.disclosure_keys:
            d = demo.guard.check_text(disclosure_text(key, lang), lang)
            assert d.allowed, (key, lang, d.rule_ids)
        footer = demo.guard.required_footer(lang)
        assert "gro@demobank.example" in footer
        assert "1800-000-0000" in footer
        assert demo.guard.check_text(footer, lang).allowed, lang


def test_ravi_hardship_officer_insurance_first_no_emi(demo: Demo) -> None:
    # 1. NBA: can't pay and no capacity → a hardship officer calls, not the bot.
    nba = demo.nba.next_best_action(RAVI.account_id, MONTH)
    assert nba.action is NextAction.HARDSHIP_OFFICER
    assert nba.channel is Channel.CALL
    assert nba.earliest_contact_at == NOW
    assert nba.reason_codes == [
        "SALARY_STOPPED",
        "PAYMENT_MISSED",
        "ESSENTIALS_SPEND_DOWN",
        "RULE_CANT_PAY_ZERO_CAPACITY",
    ]

    # 2. Zero capacity, estimated and declared alike.
    estimated = estimate_affordability(RAVI, None, demo.policy.affordability)
    assert (estimated.source, estimated.max_monthly_payment_paise) == ("estimated", 0)
    afford = estimate_affordability(RAVI, RAVI_DECLARED, demo.policy.affordability)
    assert (afford.source, afford.max_monthly_payment_paise, afford.dependants) == (
        "declared",
        0,
        3,
    )

    # 3. Insurance referral first; never an EMI or any monthly amount; officer options last.
    options = demo.engine.relief_options(RAVI.customer_id, afford)
    assert [o.option_id for o in options] == [
        "OPT-ACC-DEMO-RAVI-INSURANCE",
        "OPT-ACC-DEMO-RAVI-FEE-WAIVER",
        "OPT-ACC-DEMO-RAVI-RESTRUCTURE-REVIEW",
        "OPT-ACC-DEMO-RAVI-REVIEW-DATE",
    ]
    assert [o.type for o in options] == [
        ReliefType.INSURANCE_REFERRAL,
        ReliefType.FEE_WAIVER,
        ReliefType.RESTRUCTURING,
        ReliefType.REVIEW_DATE,
    ]
    assert ReliefType.EMI_CONVERSION not in {o.type for o in options}
    assert all(o.monthly_amount_paise is None and o.tenure_months is None for o in options)
    assert [o.requires_human_approval for o in options] == [False, False, True, True]

    insurance, waiver, restructuring, review = options
    assert insurance.disclosure_keys == ["disc.insurance.claim_process"]
    assert insurance.eligibility_reason == (
        "Card carries job loss insurance cover; a claim may cover dues (insurer decides)."
    )
    assert waiver.waiver_paise == 153_400
    assert restructuring.policy_ref == "bank_policy.yaml#restructuring.v1"
    assert restructuring.disclosure_keys == [
        "disc.restructuring.npa_downgrade",
        "disc.restructuring.upgrade_after_performance",
    ]
    assert restructuring.eligibility_reason == (
        "Account is sma1 and no instalment over up to 36 months fits current capacity; a "
        "hardship officer sets terms (up to 3 months' moratorium) under the board-approved "
        "policy."
    )
    assert review.disclosure_keys == ["disc.review.what_happens_next"]
    assert review.eligibility_reason == (
        "Zero repayment capacity: documented engagement and an agreed review date (in 30, 45, "
        "60 days) with a hardship officer before any escalation."
    )

    # 4. Restructuring is only proposed: a hardship officer must approve it.
    offer = demo.engine.propose_offer(RAVI.customer_id, restructuring.option_id, Actor.BOT)
    assert offer.status is OfferStatus.PROPOSED
    assert offer.approved_by is None
    assert offer.option == restructuring
    assert offer.expires_at == datetime(2026, 10, 19, 11, tzinfo=IST)

    # The insurance referral needs no approval.
    referral = demo.engine.propose_offer(RAVI.customer_id, insurance.option_id, Actor.BOT)
    assert (referral.status, referral.approved_by) == (OfferStatus.APPROVED, "policy_engine")
