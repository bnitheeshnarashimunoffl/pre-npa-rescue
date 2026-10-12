"""Tests for npa_rules.compliance_guard (ComplianceProvider): contact rules and text screening."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from npa_contracts.enums import Actor, Channel, Lang
from npa_contracts.models import ComplianceDecision, ContactEvent
from npa_contracts.providers import ComplianceProvider
from npa_rules.compliance_guard import ComplianceGuard, load_lexicon, required_footer
from npa_rules.disclosures import DISCLOSURES
from npa_rules.personas import PRIYA
from npa_rules.policy_loader import Policy
from npa_rules.relief_calc import AccountSnapshot

IST = ZoneInfo("Asia/Kolkata")
CID = PRIYA.customer_id


def ist(day: int, hh: int, mm: int = 0) -> datetime:
    return datetime(2026, 10, day, hh, mm, tzinfo=IST)


def event(ts: datetime, direction: str = "outbound") -> ContactEvent:
    ok = ComplianceDecision(allowed=True, rule_ids=[], next_allowed_at=None, explanation="")
    return ContactEvent.model_validate(
        {
            "event_id": f"EVT-{ts.isoformat()}",
            "customer_id": CID,
            "account_id": PRIYA.account_id,
            "channel": "call",
            "direction": direction,
            "actor": "agent",
            "ts": ts,
            "content": "Reminder",
            "lang": "en",
            "recorded_notice_given": True,
            "compliance": ok,
            "outcome": None,
        }
    )


def guard(
    policy: Policy,
    history: list[ContactEvent] | None = None,
    ctx: AccountSnapshot = PRIYA,
) -> ComplianceGuard:
    events = history or []
    return ComplianceGuard(policy, lambda _cid: events, lambda _cid: ctx)


def test_satisfies_protocol(policy: Policy) -> None:
    provider: ComplianceProvider = guard(policy)
    assert provider.check_contact(CID, Channel.CALL, ist(12, 11), Actor.AGENT).allowed


@pytest.mark.parametrize(
    ("at", "allowed"),
    [(ist(12, 8), True), (ist(12, 18, 59), True), (ist(12, 19), False), (ist(12, 7, 59), False)],
)
def test_contact_window_in_ist(policy: Policy, at: datetime, allowed: bool) -> None:
    d = guard(policy).check_contact(CID, Channel.CALL, at, Actor.AGENT)
    assert d.allowed is allowed
    if not allowed:
        assert d.rule_ids == ["RBI-454Y4-WINDOW"]


def test_window_evaluated_in_ist_even_for_utc_input(policy: Policy) -> None:
    # 14:00 UTC = 19:30 IST -> outside the window; next slot is 08:00 IST tomorrow.
    d = guard(policy).check_contact(
        CID, Channel.SMS, datetime(2026, 10, 12, 14, 0, tzinfo=UTC), Actor.SYSTEM
    )
    assert not d.allowed
    assert d.next_allowed_at == ist(13, 8)
    assert d.next_allowed_at is not None and d.next_allowed_at.tzinfo is UTC


def test_early_morning_next_is_same_day(policy: Policy) -> None:
    d = guard(policy).check_contact(CID, Channel.CALL, ist(12, 6), Actor.AGENT)
    assert d.next_allowed_at == ist(12, 8)


def test_naive_datetime_rejected(policy: Policy) -> None:
    with pytest.raises(ValueError):
        guard(policy).check_contact(CID, Channel.CALL, datetime(2026, 10, 12, 11), Actor.AGENT)


def test_inbound_always_allowed(policy: Policy) -> None:
    g = guard(policy)
    assert g.check_contact(CID, Channel.CHAT, ist(12, 23), Actor.CUSTOMER).allowed
    d = g.check_contact(CID, Channel.CHAT, ist(12, 2), Actor.BOT, direction="inbound")
    assert d.allowed and d.rule_ids == ["INBOUND-ALLOWED"]


def test_customer_quiet_time_preference(policy: Policy) -> None:
    ctx = PRIYA.model_copy(update={"avoid_contact_windows": ("13:00-15:00",)})
    d = guard(policy, ctx=ctx).check_contact(CID, Channel.CALL, ist(12, 14), Actor.AGENT)
    assert not d.allowed and d.rule_ids == ["RBI-454Y4-PREF"]
    assert d.next_allowed_at == ist(12, 15)


@pytest.mark.parametrize("flag", ["bereavement", "medical_emergency", "customer_requested_pause"])
def test_do_not_contact_flags(policy: Policy, flag: str) -> None:
    ctx = PRIYA.model_copy(update={"do_not_contact_flags": (flag,)})
    d = guard(policy, ctx=ctx).check_contact(CID, Channel.CALL, ist(12, 11), Actor.AGENT)
    assert not d.allowed and d.rule_ids == ["RBI-454Y6-OCCASION"]
    assert d.next_allowed_at is None


def test_min_gap_between_attempts(policy: Policy) -> None:
    d = guard(policy, [event(ist(12, 10))]).check_contact(
        CID, Channel.CALL, ist(12, 11), Actor.AGENT
    )
    assert not d.allowed and d.rule_ids == ["RBI-454Z4-EXCESSIVE"]
    assert d.next_allowed_at == ist(12, 13)


def test_daily_cap(policy: Policy) -> None:
    hist = [event(ist(12, 8)), event(ist(12, 11))]
    d = guard(policy, hist).check_contact(CID, Channel.CALL, ist(12, 16), Actor.AGENT)
    assert not d.allowed
    assert d.next_allowed_at == ist(13, 8)


def test_weekly_cap(policy: Policy) -> None:
    hist = [event(ist(day, 10)) for day in range(6, 12)]  # 6 attempts on 6..11 Oct
    d = guard(policy, hist).check_contact(CID, Channel.CALL, ist(12, 9), Actor.AGENT)
    assert not d.allowed
    # The 6 Oct 10:00 attempt leaves the rolling 7-day window at 13 Oct 10:00.
    assert d.next_allowed_at == ist(13, 10)


def test_inbound_history_does_not_count(policy: Policy) -> None:
    hist = [event(ist(12, 10), "inbound"), event(ist(12, 10, 30), "inbound")]
    assert guard(policy, hist).check_contact(CID, Channel.CALL, ist(12, 11), Actor.AGENT).allowed


def test_next_allowed_combines_rules(policy: Policy) -> None:
    # 18:30 with an attempt at 17:00: gap pushes to 20:00, window pushes to 08:00 next day.
    d = guard(policy, [event(ist(12, 17))]).check_contact(
        CID, Channel.CALL, ist(12, 18, 30), Actor.AGENT
    )
    assert d.next_allowed_at == ist(13, 8)


def test_reload_policy(policy: Policy) -> None:
    g = guard(policy)
    g.reload(policy)
    assert g.check_contact(CID, Channel.CALL, ist(12, 11), Actor.AGENT).allowed


# --- text ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "lang", "rule"),
    [
        ("You are a fraud and a liar.", Lang.EN, "RBI-454Z-ABUSIVE"),
        ("Pay today or we will take legal action.", Lang.EN, "RBI-454Z-THREAT"),
        ("We will visit your office tomorrow.", Lang.EN, "RBI-454Z-THREAT"),
        ("This is your final warning.", Lang.EN, "RBI-454Z-THREAT"),
        ("You will go to jail if you do not pay.", Lang.EN, "RBI-454Z-MISLEADING"),
        ("Your family will be liable for this debt.", Lang.EN, "RBI-454Z-MISLEADING"),
        ("We will inform your employer about your dues.", Lang.EN, "RBI-454Z-THIRD-PARTY"),
        ("Your name will be on the defaulters list.", Lang.EN, "RBI-454Z-SHAMING"),
        ("We will post your photo on social media.", Lang.EN, "RBI-454Z-SHAMING"),
        ("भुगतान नहीं किया तो पुलिस आएगी।", Lang.HI, "RBI-454Z-THREAT"),
        ("आप जेल जाएंगे।", Lang.HI, "RBI-454Z-MISLEADING"),
        ("பணம் கட்டவில்லை என்றால் கைது செய்யப்படுவீர்கள்.", Lang.TA, "RBI-454Z-THREAT"),
        ("நீங்கள் சிறைக்குச் செல்வீர்கள்.", Lang.TA, "RBI-454Z-MISLEADING"),
        ("Paisa nahi diya toh police ghar aayegi.", Lang.HI, "RBI-454Z-THREAT"),
        ("Aap toh chor ho.", Lang.EN, "RBI-454Z-ABUSIVE"),
    ],
)
def test_harsh_text_blocked(policy: Policy, text: str, lang: Lang, rule: str) -> None:
    d = guard(policy).check_text(text, lang)
    assert not d.allowed
    assert rule in d.rule_ids
    assert "454Z" in d.explanation


@pytest.mark.parametrize(
    "text",
    [
        "Hi Priya, we noticed a change in your payments. Would you like to talk about options?",
        "You can pay Rs 2,000 a month for 6 months, and we will waive the late fees.",
        "A hardship officer will call you at 11:00 tomorrow.",
        "Your first instalment is due on 5 November.",
    ],
)
def test_kind_text_allowed(policy: Policy, text: str) -> None:
    assert guard(policy).check_text(text, Lang.EN).allowed


def test_our_own_disclosures_and_footer_pass(policy: Policy) -> None:
    g = guard(policy)
    for d in DISCLOSURES.values():
        for lang, text in d.text.items():
            assert g.check_text(text, lang).allowed, (d.key, lang)
    for lang in Lang:
        assert g.check_text(g.required_footer(lang), lang).allowed


def test_llm_judge_hook(policy: Policy) -> None:
    g = ComplianceGuard(
        policy,
        lambda _c: [],
        lambda _c: PRIYA,
        llm_judge=lambda text, lang: ["LLM-JUDGE-TONE"] if "!!!" in text else [],
    )
    d = g.check_text("Pay now!!!", Lang.EN)
    assert not d.allowed and d.rule_ids == ["LLM-JUDGE-TONE"]
    assert g.check_text("Pay when you can.", Lang.EN).allowed


def test_footer_has_grievance_officer_recording_and_ombudsman(policy: Policy) -> None:
    text = required_footer(policy, Lang.EN)
    g = policy.grievance_officer
    for part in (g.name, g.email, g.phone, g.address, "recorded", "Ombudsman", "30 days"):
        assert part in text
    assert g.email in required_footer(policy, Lang.TA)
    assert g.phone in required_footer(policy, Lang.HI)


def test_bad_lexicon_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "lex.yaml"
    bad.write_text("rules:\n  - rule_id: X\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_lexicon(bad)


def test_lexicon_loads() -> None:
    lex = load_lexicon()
    assert {r.rule_id for r in lex.rules} == {
        "RBI-454Z-ABUSIVE",
        "RBI-454Z-THREAT",
        "RBI-454Z-MISLEADING",
        "RBI-454Z-THIRD-PARTY",
        "RBI-454Z-SHAMING",
    }


def test_utc_history_compared_correctly(policy: Policy) -> None:
    # 04:30 UTC = 10:00 IST attempt; 11:00 IST is inside the 180-minute gap.
    hist = [event(datetime(2026, 10, 12, 4, 30, tzinfo=UTC))]
    d = guard(policy, hist).check_contact(CID, Channel.CALL, ist(12, 11), Actor.AGENT)
    assert d.next_allowed_at == ist(12, 13) and not d.allowed
    assert d.next_allowed_at - ist(12, 10) == timedelta(hours=3)
