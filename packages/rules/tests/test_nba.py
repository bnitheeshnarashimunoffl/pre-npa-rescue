"""Tests for npa_rules.nba (NBAProvider) and the collector queue, against contracts fixtures."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from npa_contracts.enums import Bucket, Channel, NextAction, RiskBand, Segment, UpliftGroup
from npa_contracts.providers import NBAProvider
from npa_rules.compliance_guard import ComplianceGuard
from npa_rules.nba import NextBestActionService, QueueInput, StaticRiskProvider, prioritise
from npa_rules.personas import PRIYA, RAVI
from npa_rules.policy_engine import PolicyEngine
from npa_rules.policy_loader import Policy
from npa_rules.relief_calc import AccountSnapshot

IST = ZoneInfo("Asia/Kolkata")
QUEUE_FIXTURE = Path(__file__).resolve().parents[3] / "contracts" / "fixtures" / "queue.json"
MONTH = "2026-09"


def queue_data() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(QUEUE_FIXTURE.read_text(encoding="utf-8"))
    return data


def snapshots() -> dict[str, AccountSnapshot]:
    """Personas plus generic snapshots for the other fixture accounts."""
    out = {PRIYA.account_id: PRIYA, RAVI.account_id: RAVI}
    for item in queue_data()["items"]:
        if item["account_id"] not in out:
            out[item["account_id"]] = AccountSnapshot(
                customer_id="CUST-" + item["account_id"][4:],
                account_id=item["account_id"],
                dpd=item["dpd"],
                total_outstanding_paise=item["total_due_paise"],
                overdue_paise=item["total_due_paise"] // 10,
                waivable_charges_paise=0,
                monthly_income_paise=5_000_000,
                avg_payment_3m_paise=300_000,
            )
    return out


def service(
    policy: Policy,
    at: datetime,
    accounts: dict[str, AccountSnapshot] | None = None,
    ignored: int = 0,
    with_engine: bool = False,
) -> NextBestActionService:
    accts = accounts or snapshots()
    by_customer = {a.customer_id: a for a in accts.values()}
    guard = ComplianceGuard(policy, lambda _c: [], by_customer.__getitem__)
    engine = PolicyEngine(policy, by_customer.__getitem__) if with_engine else None
    return NextBestActionService(
        policy,
        StaticRiskProvider.from_queue_fixture(queue_data()),
        guard,
        accts.__getitem__,
        policy_provider=engine,
        chat_invites_ignored=lambda _a: ignored,
        clock=lambda: at,
    )


def test_satisfies_protocol(policy: Policy) -> None:
    provider: NBAProvider = service(policy, datetime(2026, 10, 12, 11, tzinfo=IST))
    assert provider.next_best_action(PRIYA.account_id, MONTH).account_id == PRIYA.account_id


def test_priya_gets_chat_invite_with_options(policy: Policy) -> None:
    now = datetime(2026, 10, 12, 11, tzinfo=IST)
    nba = service(policy, now, with_engine=True).next_best_action(PRIYA.account_id, MONTH)
    assert nba.action is NextAction.CHAT_INVITE
    assert nba.channel is Channel.CHAT
    assert nba.earliest_contact_at == now
    assert nba.reason_codes[:3] == ["SALARY_STOPPED", "MIN_DUE_ONLY_STREAK", "UTILISATION_RISING"]
    assert "RULE_CANT_PAY_PERSUADABLE" in nba.reason_codes
    assert "RELIEF_OPTIONS_READY" in nba.reason_codes


def test_ravi_gets_hardship_officer(policy: Policy) -> None:
    now = datetime(2026, 10, 12, 11, tzinfo=IST)
    nba = service(policy, now).next_best_action(RAVI.account_id, MONTH)
    assert nba.action is NextAction.HARDSHIP_OFFICER
    assert nba.channel is Channel.CALL
    assert "RULE_CANT_PAY_ZERO_CAPACITY" in nba.reason_codes


def test_earliest_contact_respects_window(policy: Policy) -> None:
    late = datetime(2026, 10, 12, 21, tzinfo=IST)
    nba = service(policy, late).next_best_action(PRIYA.account_id, MONTH)
    assert nba.earliest_contact_at == datetime(2026, 10, 13, 8, tzinfo=IST)
    assert "WAIT:RBI-454Y4-WINDOW" in nba.reason_codes


@pytest.mark.parametrize(
    ("account_id", "action"),
    [
        ("ACC-001006", NextAction.CHAT_INVITE),
        ("ACC-000509", NextAction.FIRM_PROCESS),
        ("ACC-000117", NextAction.REMINDER),
        ("ACC-000954", NextAction.REMINDER),
        ("ACC-000778", NextAction.NO_CONTACT),
    ],
)
def test_fixture_accounts(policy: Policy, account_id: str, action: NextAction) -> None:
    nba = service(policy, datetime(2026, 10, 12, 11, tzinfo=IST)).next_best_action(
        account_id, MONTH
    )
    assert nba.action is action
    if action is NextAction.NO_CONTACT:
        assert nba.channel is None and nba.earliest_contact_at is None


def test_do_not_contact_flag_wins(policy: Policy) -> None:
    accts = snapshots()
    accts[PRIYA.account_id] = PRIYA.model_copy(update={"do_not_contact_flags": ("bereavement",)})
    nba = service(policy, datetime(2026, 10, 12, 11, tzinfo=IST), accts).next_best_action(
        PRIYA.account_id, MONTH
    )
    assert nba.action is NextAction.NO_CONTACT
    assert "RULE_DO_NOT_CONTACT_FLAG" in nba.reason_codes


def _variant(svc: NextBestActionService, account_id: str, **changes: Any) -> NextAction:
    risk, seg, up = (
        svc._risk.risk(account_id, MONTH),
        svc._risk.segment(account_id, MONTH),
        svc._risk.uplift(account_id, MONTH),
    )
    if "band" in changes:
        risk = risk.model_copy(update={"risk_band": changes["band"]})
    if "segment" in changes:
        seg = seg.model_copy(update={"segment": changes["segment"]})
    if "group" in changes:
        up = up.model_copy(update={"uplift_group": changes["group"]})
    return svc.decide(risk, seg, up).action


def test_rule_table_order(policy: Policy) -> None:
    svc = service(policy, datetime(2026, 10, 12, 11, tzinfo=IST))
    a = "ACC-001006"
    assert _variant(svc, a, band=RiskBand.LOW, segment=Segment.NOT_AT_RISK) is NextAction.NO_CONTACT
    assert _variant(svc, a, group=UpliftGroup.SLEEPING_DOG) is NextAction.NO_CONTACT
    assert _variant(svc, a, segment=Segment.FORGOT) is NextAction.REMINDER
    assert _variant(svc, a, group=UpliftGroup.SURE_THING) is NextAction.REMINDER
    assert _variant(svc, a, segment=Segment.WONT_PAY) is NextAction.CHAT_INVITE  # persuadable
    assert (
        _variant(svc, a, segment=Segment.WONT_PAY, group=UpliftGroup.LOST_CAUSE)
        is NextAction.FIRM_PROCESS
    )
    assert _variant(svc, a, group=UpliftGroup.LOST_CAUSE) is NextAction.FIRM_PROCESS
    assert (
        _variant(svc, a, segment=Segment.NOT_AT_RISK, band=RiskBand.MEDIUM,
                 group=UpliftGroup.LOST_CAUSE)
        is NextAction.FIRM_PROCESS
    )  # fmt: skip


def test_persuadable_escalates_to_agent_call_after_ignored_invites(policy: Policy) -> None:
    svc = service(policy, datetime(2026, 10, 12, 11, tzinfo=IST), ignored=2)
    a = "ACC-001006"
    assert _variant(svc, a, segment=Segment.WONT_PAY) is NextAction.AGENT_CALL


# --- queue -----------------------------------------------------------------------------------


def test_queue_priorities(policy: Policy) -> None:
    accts = snapshots()
    svc = service(policy, datetime(2026, 10, 12, 11, tzinfo=IST), accts)
    names = {i["account_id"]: i["customer_name"] for i in queue_data()["items"]}
    items = [QueueInput(svc.next_best_action(a, MONTH), accts[a], names[a]) for a in names]
    queue = prioritise(items, policy)
    assert len(queue) == 10
    assert queue[0].priority == 1.0
    assert [q.priority for q in queue] == sorted((q.priority for q in queue), reverse=True)
    by_id = {q.account_id: q for q in queue}
    assert by_id["ACC-000778"].priority == 0.0  # no_contact
    # Hardship cases are never deprioritised to zero even with ~0 uplift.
    assert by_id[RAVI.account_id].priority > by_id["ACC-000117"].priority
    assert by_id[PRIYA.account_id].bucket is Bucket.SMA0


def test_queue_empty(policy: Policy) -> None:
    assert prioritise([], policy) == []


def test_static_provider_batch() -> None:
    provider = StaticRiskProvider.from_queue_fixture(queue_data())
    assert len(list(provider.score_batch(MONTH))) == 10
    with pytest.raises(KeyError):
        provider.risk("ACC-UNKNOWN", MONTH)
