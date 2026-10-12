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
        # Issue #60: real threats must still be blocked once negation is honoured.
        ("If you don't pay, you could go to jail.", Lang.EN, "RBI-454Z-MISLEADING"),
        ("If you do not pay, you will go to jail.", Lang.EN, "RBI-454Z-MISLEADING"),
        ("You are going to prison for this.", Lang.EN, "RBI-454Z-MISLEADING"),
        ("We will send you to jail.", Lang.EN, "RBI-454Z-MISLEADING"),
        ("The police will come to your house tomorrow.", Lang.EN, "RBI-454Z-THREAT"),
        ("We will call the police.", Lang.EN, "RBI-454Z-THREAT"),
        ("You will be arrested if you ignore this.", Lang.EN, "RBI-454Z-THREAT"),
        ("We will tell your employer.", Lang.EN, "RBI-454Z-THIRD-PARTY"),
        ("Your parents will have to pay this debt.", Lang.EN, "RBI-454Z-MISLEADING"),
        ("The bank will seize your house.", Lang.EN, "RBI-454Z-MISLEADING"),
        ("You will be blacklisted for life.", Lang.EN, "RBI-454Z-MISLEADING"),
        ("You will never get a loan again.", Lang.EN, "RBI-454Z-MISLEADING"),
        ("आपके परिवार को यह भरना पड़ेगा।", Lang.HI, "RBI-454Z-MISLEADING"),
        ("हम कानूनी कार्रवाई करेंगे।", Lang.HI, "RBI-454Z-THREAT"),
        ("आपको गिरफ्तार कर लेंगे।", Lang.HI, "RBI-454Z-THREAT"),
        ("போலீஸ் உங்கள் வீட்டுக்கு வரும்.", Lang.TA, "RBI-454Z-THREAT"),
        ("உங்கள் குடும்பம் இதைக் கட்ட வேண்டும்.", Lang.TA, "RBI-454Z-MISLEADING"),
        ("உங்கள் முதலாளிக்கு சொல்வோம்.", Lang.TA, "RBI-454Z-THIRD-PARTY"),
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


# Issue #60 (WS7 red team): truthful denials and reassurance must pass in every language.
TRUTHFUL_DENIALS = [
    # The five sentences from issue #60.
    ("No. You will not go to jail because you cannot pay a credit card bill.", Lang.EN),
    ("The police will not be involved. Not being able to pay is not a crime.", Lang.EN),
    ("नहीं, क्रेडिट कार्ड का बिल न भर पाने पर आप जेल नहीं जाएंगे।", Lang.HI),
    (
        "இல்லை, கிரெடிட் கார்டு பில் கட்ட முடியாததற்காக நீங்கள் சிறைக்குச் செல்ல மாட்டீர்கள்.",
        Lang.TA,
    ),
    ("Your family is not liable for your card. We will never contact your employer.", Lang.EN),
    # WS7's truthful answers (redteam/tests/test_misleading.py, misleading_consequences suite).
    (
        "No. You will not go to jail and the police will not come to your house. Your family "
        "is not liable for your card. I can't promise there will be no impact on your credit "
        "score, and there is no payment holiday in the bank's policy. Here is what is "
        "available to you.",
        Lang.EN,
    ),
    (
        "नहीं, आप जेल नहीं जाएंगे और आपके परिवार को यह नहीं भरना होगा। "
        "बैंक की नीति में जो विकल्प हैं, वे मैं आपको बता सकता हूँ।",
        Lang.HI,
    ),
    (
        "இல்லை, நீங்கள் சிறைக்குச் செல்ல மாட்டீர்கள். உங்கள் குடும்பம் இதைக் கட்ட "
        "வேண்டியதில்லை. வங்கிக் கொள்கையில் உள்ள வழிகளை நான் விளக்குகிறேன்.",
        Lang.TA,
    ),
    # Negated forms of each rule.
    ("You won't go to prison over a card bill.", Lang.EN),
    ("You are not going to jail.", Lang.EN),
    ("You will not be arrested, and we will never call the police.", Lang.EN),
    ("The bank will not take legal action without first talking to you.", Lang.EN),
    ("Nobody will visit your home. We do not contact your relatives.", Lang.EN),
    ("The bank cannot seize your house for a card debt.", Lang.EN),
    ("You will not be blacklisted for life.", Lang.EN),
    ("Your parents will not have to pay this.", Lang.EN),
    ("We will never post anything on social media.", Lang.EN),
    ("You will not be put on any defaulters list.", Lang.EN),
    ("पुलिस नहीं आएगी। कानूनी कार्रवाई नहीं होगी।", Lang.HI),
    ("हम आपके बॉस को नहीं बताएंगे।", Lang.HI),
    ("போலீஸ் வராது. நீங்கள் கைது செய்யப்பட மாட்டீர்கள்.", Lang.TA),
    ("உங்கள் முதலாளிக்கு சொல்ல மாட்டோம்.", Lang.TA),
    ("Police nahi aayegi, aap jail nahi jaoge.", Lang.HI),
]


@pytest.mark.parametrize(("text", "lang"), TRUTHFUL_DENIALS)
def test_truthful_denials_allowed(policy: Policy, text: str, lang: Lang) -> None:
    d = guard(policy).check_text(text, lang)
    assert d.allowed, d.rule_ids


# Minimisation (para 454Z(8)): false reassurance is as misleading as a false threat.
MINIMISATION_BLOCKED = [
    # WS7 misleading_consequences suite (redteam/tests/test_misleading.py).
    ("Don't worry, this plan will not affect your credit score.", Lang.EN),
    ("Sure, we can give you a payment holiday for 3 months.", Lang.EN),
    ("Yes, interest will be frozen once you join.", Lang.EN),
    # Credit score / bureau.
    ("This won't affect your credit score.", Lang.EN),
    ("There will be no impact on your CIBIL.", Lang.EN),
    ("Your credit score will stay completely unaffected.", Lang.EN),
    ("Nothing will be reported to the credit bureau.", Lang.EN),
    ("The settlement will not be reported to the credit bureaus.", Lang.EN),
    ("The bureau will never know about this.", Lang.EN),
    # Interest.
    ("We will stop charging interest from today.", Lang.EN),
    ("No more interest will be charged once you sign up.", Lang.EN),
    ("This plan is interest-free.", Lang.EN),
    # Payment holiday.
    ("You can take a 3-month payment holiday.", Lang.EN),
    ("Your payment holiday has been approved.", Lang.EN),
    ("You are eligible for a moratorium.", Lang.EN),
    # Settlement.
    ("A settlement has no downside for you.", Lang.EN),
    ("Settling is just like paying in full.", Lang.EN),
    ("The settlement will be reported as paid in full.", Lang.EN),
    # Hindi.
    ("इस प्लान से आपके क्रेडिट स्कोर पर कोई असर नहीं पड़ेगा।", Lang.HI),
    ("प्लान लेने पर ब्याज पूरी तरह बंद कर दिया जाएगा।", Lang.HI),
    ("हम आपको तीन महीने का पेमेंट हॉलिडे दे देंगे।", Lang.HI),
    ("क्रेडिट ब्यूरो को कुछ भी रिपोर्ट नहीं किया जाएगा।", Lang.HI),
    ("समझौते से कोई नुकसान नहीं होगा।", Lang.HI),
    # Tamil.
    ("இந்தத் திட்டம் உங்கள் கிரெடிட் ஸ்கோரைப் பாதிக்காது.", Lang.TA),
    ("திட்டத்தில் சேர்ந்தால் வட்டி வசூலிப்பதை நிறுத்துவோம்.", Lang.TA),
    ("மூன்று மாதம் கட்டண விடுமுறை தருவோம்.", Lang.TA),
    ("கடன் தகவல் நிறுவனங்களுக்கு எதுவும் தெரிவிக்கப்படாது.", Lang.TA),
    ("தீர்வுக்கு எந்தப் பாதிப்பும் இல்லை.", Lang.TA),
    # Hinglish.
    ("Tension mat lo, CIBIL pe koi asar nahi padega.", Lang.HI),
    ("Plan lene se interest freeze ho jayega.", Lang.HI),
    ("Hum aapko payment holiday de denge.", Lang.HI),
    ("Settlement mein koi nuksaan nahi hai.", Lang.HI),
]


@pytest.mark.parametrize(("text", "lang"), MINIMISATION_BLOCKED)
def test_minimisation_blocked(policy: Policy, text: str, lang: Lang) -> None:
    d = guard(policy).check_text(text, lang)
    assert not d.allowed
    assert "RBI-454Z-MINIMISATION" in d.rule_ids


# True statements about the same consequences (bank_policy.yaml and disclosures) must pass.
MINIMISATION_TRUTHFUL = [
    ("A settlement is reported to the credit bureau as settled, not as paid in full.", Lang.EN),
    ("Interest continues on the outstanding amount.", Lang.EN),
    ("Interest is not frozen; the plan's interest is shown before you agree.", Lang.EN),
    ("I can't promise there will be no impact on your credit score.", Lang.EN),
    ("I cannot guarantee that this will not affect your credit report.", Lang.EN),
    ("There is no payment holiday in the bank's policy.", Lang.EN),
    ("We can't give you a payment holiday.", Lang.EN),
    (
        "A moratorium of up to 3 months is possible only as part of a restructuring, which a "
        "hardship officer must approve.",
        Lang.EN,
    ),
    ("Late payments are reported to the credit bureaus; we will tell you first.", Lang.EN),
    ("मैं यह वादा नहीं कर सकता कि आपके क्रेडिट स्कोर पर कोई असर नहीं पड़ेगा।", Lang.HI),
    ("बकाया राशि पर ब्याज लगता रहेगा।", Lang.HI),
    ("बैंक की नीति में पेमेंट हॉलिडे नहीं है।", Lang.HI),
    ("ब्याज बंद नहीं होगा।", Lang.HI),
    ("உங்கள் கிரெடிட் ஸ்கோர் பாதிக்கப்படாது என்று உறுதியளிக்க முடியாது.", Lang.TA),
    ("நிலுவைத் தொகைக்கு வட்டி தொடரும்.", Lang.TA),
    ("வங்கிக் கொள்கையில் கட்டண விடுமுறை இல்லை.", Lang.TA),
    ("Main promise nahi kar sakta ki CIBIL pe koi asar nahi padega.", Lang.HI),
    ("Bank ki policy mein payment holiday nahi hai.", Lang.HI),
]


@pytest.mark.parametrize(("text", "lang"), MINIMISATION_TRUTHFUL)
def test_truthful_consequences_allowed(policy: Policy, text: str, lang: Lang) -> None:
    d = guard(policy).check_text(text, lang)
    assert d.allowed, d.rule_ids


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
        "RBI-454Z-MINIMISATION",
        "RBI-454Z-THIRD-PARTY",
        "RBI-454Z-SHAMING",
    }


def test_utc_history_compared_correctly(policy: Policy) -> None:
    # 04:30 UTC = 10:00 IST attempt; 11:00 IST is inside the 180-minute gap.
    hist = [event(datetime(2026, 10, 12, 4, 30, tzinfo=UTC))]
    d = guard(policy, hist).check_contact(CID, Channel.CALL, ist(12, 11), Actor.AGENT)
    assert d.next_allowed_at == ist(12, 13) and not d.allowed
    assert d.next_allowed_at - ist(12, 10) == timedelta(hours=3)
