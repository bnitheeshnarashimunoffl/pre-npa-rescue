"""The demo's admin moment: editing the bank policy through ``PUT /admin/policy``.

WS5's handler calls ``parse_policy(body)`` and, if it succeeds, ``reload`` on all three
providers (README "How to use npa_rules"). An edit that breaks an RBI rule must be rejected
with a message the admin can act on, and nothing reloads. A legal edit must reach every
provider and change what the customer is offered.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
import yaml

from npa_contracts.enums import Actor, Lang, NextAction
from npa_rules.compliance_guard import ComplianceGuard
from npa_rules.nba import NextBestActionService, StaticRiskProvider
from npa_rules.personas import PRIYA, PRIYA_DECLARED, RAVI
from npa_rules.policy_engine import PolicyEngine
from npa_rules.policy_loader import POLICY_DIR, Policy, PolicyError, parse_policy
from npa_rules.relief_calc import estimate_affordability

IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 10, 12, 11, tzinfo=IST)
QUEUE_FIXTURE = Path(__file__).resolve().parents[3] / "contracts" / "fixtures" / "queue.json"

WINDOW_ERROR = "contact.window_local must be 08:00-19:00 Asia/Kolkata (RBI RBC para 454Y(4))"
SETTLEMENT_ERROR = (
    "settlement payment_window_months_max must be <= 3; longer is restructuring (2023)"
)
RESTRUCTURING_ERROR = "options.restructuring: requires_human_approval must be true"


def put_body() -> dict[str, Any]:
    """The body the admin UI sends: the shipped policy as JSON-like data."""
    data: dict[str, Any] = yaml.safe_load(
        (POLICY_DIR / "bank_policy.yaml").read_text(encoding="utf-8")
    )
    return data


def contact_from_07(body: dict[str, Any]) -> None:
    body["contact"]["window_local"]["start"] = "07:00"


def settlement_over_6_months(body: dict[str, Any]) -> None:
    body["options"]["compromise_settlement"]["payment_window_months_max"] = 6


def restructuring_auto_approved(body: dict[str, Any]) -> None:
    body["options"]["restructuring"]["requires_human_approval"] = False


class Providers:
    def __init__(self, policy: Policy) -> None:
        by_customer = {PRIYA.customer_id: PRIYA, RAVI.customer_id: RAVI}
        by_account = {PRIYA.account_id: PRIYA, RAVI.account_id: RAVI}
        queue: dict[str, Any] = json.loads(QUEUE_FIXTURE.read_text(encoding="utf-8"))
        self.engine = PolicyEngine(policy, by_customer.__getitem__, clock=lambda: NOW)
        self.guard = ComplianceGuard(policy, lambda _c: [], by_customer.__getitem__)
        self.nba = NextBestActionService(
            policy,
            StaticRiskProvider.from_queue_fixture(queue),
            self.guard,
            by_account.__getitem__,
            policy_provider=self.engine,
            clock=lambda: NOW,
        )

    def put_policy(self, body: dict[str, Any]) -> list[str]:
        """What WS5's handler does: validate, then hot-reload every provider (422 on errors)."""
        try:
            new_policy = parse_policy(body)
        except PolicyError as exc:
            return exc.errors
        for provider in (self.engine, self.guard, self.nba):
            provider.reload(new_policy)
        return []

    def priya_plan_waiver(self) -> int | None:
        policy = self.engine.policy
        afford = estimate_affordability(PRIYA, PRIYA_DECLARED, policy.affordability)
        options = self.engine.relief_options(PRIYA.customer_id, afford)
        plan = next(o for o in options if o.option_id.startswith("OPT-ACC-DEMO-PRIYA-EMI"))
        offer = self.engine.propose_offer(PRIYA.customer_id, plan.option_id, Actor.BOT)
        return offer.option.waiver_paise


@pytest.mark.parametrize(
    ("edit", "error"),
    [
        (contact_from_07, WINDOW_ERROR),
        (settlement_over_6_months, SETTLEMENT_ERROR),
        (restructuring_auto_approved, RESTRUCTURING_ERROR),
    ],
    ids=["contact-window-07", "settlement-6-months", "restructuring-auto-approved"],
)
def test_illegal_edit_rejected_with_clear_error(policy: Policy, edit: Any, error: str) -> None:
    body = put_body()
    edit(body)
    p = Providers(policy)
    assert p.put_policy(body) == [error]
    # Nothing reloaded: the providers still run on the shipped policy.
    assert p.engine.policy is policy
    assert p.priya_plan_waiver() == 153_400


def test_all_illegal_edits_reported_together(policy: Policy) -> None:
    # The admin sees every problem in one 422, not one at a time.
    body = put_body()
    for edit in (contact_from_07, settlement_over_6_months, restructuring_auto_approved):
        edit(body)
    with pytest.raises(PolicyError) as exc:
        parse_policy(body)
    assert exc.value.errors == [WINDOW_ERROR, SETTLEMENT_ERROR, RESTRUCTURING_ERROR]
    assert str(exc.value) == "invalid bank policy: " + "; ".join(exc.value.errors)


def test_legal_edit_reloads_into_all_three_providers(policy: Policy) -> None:
    p = Providers(policy)
    assert p.priya_plan_waiver() == 153_400

    # The admin lowers the fee-waiver cap to Rs 1,000 and updates the grievance phone line.
    body = put_body()
    body["version"] = "2026.10-v2"
    body["options"]["fee_waiver"]["max_waiver_paise"] = 100_000
    body["grievance_officer"]["phone"] = "1800-111-2222"
    assert p.put_policy(body) == []

    # PolicyEngine: the same plan now waives only the capped Rs 1,000.
    assert p.engine.policy.version == "2026.10-v2"
    afford = estimate_affordability(PRIYA, PRIYA_DECLARED, p.engine.policy.affordability)
    waiver, plan = p.engine.relief_options(PRIYA.customer_id, afford)
    assert waiver.waiver_paise == 100_000
    assert waiver.eligibility_reason.endswith("late charges Rs 1,000 within the Rs 1,000 cap.")
    assert (plan.option_id, plan.monthly_amount_paise, plan.tenure_months) == (
        "OPT-ACC-DEMO-PRIYA-EMI6-WAIVER",
        200_000,
        6,
    )
    assert plan.eligibility_reason.endswith("late charges of Rs 1,000 waived.")
    assert p.priya_plan_waiver() == 100_000

    # ComplianceGuard: the footer names the new phone line in every language and still passes.
    for lang in Lang:
        footer = p.guard.required_footer(lang)
        assert "1800-111-2222" in footer
        assert "1800-000-0000" not in footer
        assert p.guard.check_text(footer, lang).allowed

    # NextBestActionService: runs on the new policy (neither edit changes its decision) and
    # still invites Priya with options ready.
    assert p.nba._policy is p.engine.policy
    nba = p.nba.next_best_action(PRIYA.account_id, "2026-09")
    assert nba.action is NextAction.CHAT_INVITE
    assert nba.reason_codes[-1] == "RELIEF_OPTIONS_READY"
