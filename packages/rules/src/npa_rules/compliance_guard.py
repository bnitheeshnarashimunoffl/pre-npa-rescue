"""Compliance guard (task 3.3): may we contact this customer now, and may we send this text?
Implements ``npa_contracts.providers.ComplianceProvider``.

Stable rule ids (WS7 maps them to the scorecard; table in the package README):

========================  ===================================================================
``RBI-454Y4-WINDOW``      outbound contact only 08:00-19:00 Asia/Kolkata (RBC para 454Y(4))
``RBI-454Y4-PREF``        honour the borrower's request to avoid certain times (454Y(4))
``RBI-454Y6-OCCASION``    no contact during bereavement, medical emergency or a requested pause
                          (454Y(6))
``RBI-454Z4-EXCESSIVE``   daily / weekly attempt caps and minimum gap (454Z; thresholds are bank
                          policy assumptions)
``RBI-454Z-*``            harsh-practice language, see ``policies/compliance_lexicon.yaml``
``INBOUND-ALLOWED``       customer-initiated contact and replies in it are always allowed
========================  ===================================================================

Inbound customer-initiated chats are allowed at any hour and the bot may reply; only outbound
recovery contact is restricted. Pure library: contact history and account facts come from
injected callables (WS5), never a database.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

import yaml

from npa_contracts.constants import COMPLAINT_SLA_DAYS
from npa_contracts.enums import Actor, Channel, Lang
from npa_contracts.models import ComplianceDecision, ContactEvent
from npa_rules.policy_loader import POLICY_DIR, Policy
from npa_rules.relief_calc import AccountSnapshot

__all__ = [
    "ComplianceGuard",
    "Lexicon",
    "LexiconRule",
    "load_lexicon",
    "required_footer",
]

RULE_WINDOW = "RBI-454Y4-WINDOW"
RULE_PREF = "RBI-454Y4-PREF"
RULE_OCCASION = "RBI-454Y6-OCCASION"
RULE_EXCESSIVE = "RBI-454Z4-EXCESSIVE"
RULE_INBOUND = "INBOUND-ALLOWED"

LEXICON_PATH = POLICY_DIR / "compliance_lexicon.yaml"
_MAX_SEARCH_STEPS = 64

ContactHistory = Callable[[str], Sequence[ContactEvent]]
AccountLookup = Callable[[str], AccountSnapshot]
# Optional LLM judge (injected, off by default): returns extra rule ids for a text.
TextJudge = Callable[[str, Lang], list[str]]


# --- lexicon ---------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LexiconRule:
    rule_id: str
    description: str
    patterns: tuple[re.Pattern[str], ...]


@dataclass(frozen=True, slots=True)
class Lexicon:
    version: str
    rules: tuple[LexiconRule, ...]


def load_lexicon(path: str | Path = LEXICON_PATH) -> Lexicon:
    """Load and compile the harsh-practice lexicon. Raises ``ValueError`` if malformed."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    try:
        rules = tuple(
            LexiconRule(
                rule_id=str(r["rule_id"]),
                description=str(r["description"]),
                patterns=tuple(
                    re.compile(unicodedata.normalize("NFC", p), re.IGNORECASE)
                    for pats in r["patterns"].values()
                    for p in pats
                ),
            )
            for r in data["rules"]
        )
    except (KeyError, TypeError, AttributeError, re.error) as exc:
        raise ValueError(f"invalid compliance lexicon {path}: {exc}") from exc
    return Lexicon(version=str(data.get("version", "")), rules=rules)


# --- footer ----------------------------------------------------------------------------------

_FOOTER = {
    Lang.EN: (
        "This conversation may be recorded. For any complaint, contact our Grievance Officer: "
        "{name}, {email}, {phone}, {address}. If it is not resolved within {days} days, you "
        "can approach the RBI Ombudsman."
    ),
    Lang.TA: (
        "இந்த உரையாடல் பதிவு செய்யப்படலாம். புகார் இருந்தால் எங்கள் குறைதீர் அலுவலரைத் "
        "தொடர்பு கொள்ளுங்கள்: {name}, {email}, {phone}, {address}. {days} நாட்களுக்குள் "
        "தீர்வு கிடைக்காவிட்டால், நீங்கள் RBI குறைதீர்ப்பாளரை அணுகலாம்."
    ),
    Lang.HI: (
        "यह बातचीत रिकॉर्ड की जा सकती है। किसी भी शिकायत के लिए हमारे शिकायत निवारण अधिकारी से "
        "संपर्क करें: {name}, {email}, {phone}, {address}। अगर {days} दिनों में समाधान नहीं होता, "
        "तो आप RBI लोकपाल से संपर्क कर सकते हैं।"
    ),
}


def required_footer(policy: Policy, lang: Lang) -> str:
    """Footer every recovery message must carry: the call/chat recording notice
    (RBC para 454P) and the grievance officer's details with the Ombudsman route after
    30 days (para 454AA). ta/hi texts are drafts pending native review."""
    g = policy.grievance_officer
    return _FOOTER[lang].format(
        name=g.name, email=g.email, phone=g.phone, address=g.address, days=COMPLAINT_SLA_DAYS
    )


# --- guard -----------------------------------------------------------------------------------


def _parse_window(spec: str) -> tuple[time, time]:
    start, end = (time.fromisoformat(p.strip()) for p in spec.split("-"))
    return start, end


class ComplianceGuard:
    """``ComplianceProvider`` over a validated :class:`Policy`.

    ``contact_history(customer_id)`` returns past :class:`ContactEvent` records (WS5 audit log,
    RBC para 454P); ``accounts(customer_id)`` returns the :class:`AccountSnapshot` with
    do-not-contact flags and quiet-time preferences.
    """

    def __init__(
        self,
        policy: Policy,
        contact_history: ContactHistory,
        accounts: AccountLookup,
        *,
        lexicon: Lexicon | None = None,
        llm_judge: TextJudge | None = None,
    ) -> None:
        self._history = contact_history
        self._accounts = accounts
        self._lexicon = lexicon if lexicon is not None else load_lexicon()
        self._judge = llm_judge
        self.reload(policy)

    def reload(self, policy: Policy) -> None:
        """Swap in a newly validated policy (``PUT /admin/policy``)."""
        self._policy = policy
        w = policy.contact.window_local
        self._tz = ZoneInfo(w.tz)
        self._window = (w.start, w.end)

    def required_footer(self, lang: Lang) -> str:
        return required_footer(self._policy, lang)

    # --- contact -----------------------------------------------------------------------------

    def check_contact(
        self,
        customer_id: str,
        channel: Channel,
        at: datetime,
        actor: Actor,
        *,
        direction: Literal["outbound", "inbound"] = "outbound",
    ) -> ComplianceDecision:
        """Whether an outbound recovery contact may happen at ``at`` (timezone-aware).

        ``direction="inbound"`` (or ``actor=customer``) means the customer started the
        contact; that is always allowed, including the bot's replies in that session.
        """
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("at must be timezone-aware")
        if direction == "inbound" or actor is Actor.CUSTOMER:
            return ComplianceDecision(
                allowed=True,
                rule_ids=[RULE_INBOUND],
                next_allowed_at=None,
                explanation="Customer-initiated contact; replies are allowed at any hour.",
            )
        ctx = self._accounts(customer_id)
        flags = sorted(
            set(ctx.do_not_contact_flags) & set(self._policy.contact.do_not_contact_flags)
        )
        if flags:
            return ComplianceDecision(
                allowed=False,
                rule_ids=[RULE_OCCASION],
                next_allowed_at=None,
                explanation=(
                    f"Do-not-contact flag active ({', '.join(flags)}); no outbound recovery "
                    "contact until a hardship officer clears it (RBI RBC para 454Y(6))."
                ),
            )
        outbound = sorted(
            (e.ts for e in self._history(customer_id) if e.direction == "outbound"),
        )
        quiet = [_parse_window(s) for s in ctx.avoid_contact_windows]
        violations = self._violations(at, outbound, quiet)
        if not violations:
            return ComplianceDecision(
                allowed=True,
                rule_ids=[],
                next_allowed_at=None,
                explanation=f"Outbound {channel.value} contact allowed.",
            )
        return ComplianceDecision(
            allowed=False,
            rule_ids=sorted({rule for rule, _, _ in violations}),
            next_allowed_at=self._next_allowed(at, outbound, quiet),
            explanation=" ".join(msg for _, _, msg in violations),
        )

    def _violations(
        self, at: datetime, outbound: list[datetime], quiet: list[tuple[time, time]]
    ) -> list[tuple[str, datetime, str]]:
        """(rule_id, earliest time this rule could pass, explanation) for each broken rule."""
        c = self._policy.contact
        local = at.astimezone(self._tz)
        start, end = self._window
        out: list[tuple[str, datetime, str]] = []
        if not start <= local.time() < end:
            day = local.date() if local.time() < start else local.date() + timedelta(days=1)
            nxt = datetime.combine(day, start, self._tz)
            out.append((RULE_WINDOW, nxt, "Outside the 08:00-19:00 IST contact window (454Y(4))."))
        for q_start, q_end in quiet:
            if q_start <= local.time() < q_end:
                nxt = datetime.combine(local.date(), q_end, self._tz)
                out.append((RULE_PREF, nxt, "Customer asked not to be contacted at this time."))
        past = [t for t in outbound if t <= at]
        day_start = datetime.combine(local.date(), time(0), self._tz)
        today = [t for t in past if t >= day_start]
        if len(today) >= c.max_outbound_attempts_per_day:
            nxt = datetime.combine(local.date() + timedelta(days=1), start, self._tz)
            out.append((RULE_EXCESSIVE, nxt, "Daily contact attempt limit reached (454Z)."))
        week = [t for t in past if t > at - timedelta(days=7)]
        if len(week) >= c.max_outbound_attempts_per_week:
            nxt = week[len(week) - c.max_outbound_attempts_per_week] + timedelta(days=7)
            out.append((RULE_EXCESSIVE, nxt, "Weekly contact attempt limit reached (454Z)."))
        gap = timedelta(minutes=c.min_gap_minutes_between_attempts)
        if past and at - past[-1] < gap:
            out.append(
                (RULE_EXCESSIVE, past[-1] + gap, "Too soon after the previous attempt (454Z).")
            )
        return out

    def _next_allowed(
        self, at: datetime, outbound: list[datetime], quiet: list[tuple[time, time]]
    ) -> datetime | None:
        t = at
        for _ in range(_MAX_SEARCH_STEPS):
            v = self._violations(t, outbound, quiet)
            if not v:
                return t.astimezone(at.tzinfo)
            t = max(nxt for _, nxt, _ in v)
        return None  # pragma: no cover - only with contradictory preferences

    # --- text --------------------------------------------------------------------------------

    def check_text(self, text: str, lang: Lang) -> ComplianceDecision:
        """Screen an outgoing message for harsh practices (RBI RBC para 454Z): abusive words,
        threats, misleading consequences, third-party disclosure and shaming. Every
        language's patterns are applied, so code-mixed text is caught."""
        norm = unicodedata.normalize("NFC", text)
        hits = [r for r in self._lexicon.rules if any(p.search(norm) for p in r.patterns)]
        rule_ids = [r.rule_id for r in hits]
        if self._judge is not None:
            rule_ids += [rid for rid in self._judge(text, lang) if rid not in rule_ids]
        if not rule_ids:
            return ComplianceDecision(
                allowed=True, rule_ids=[], next_allowed_at=None, explanation="Text allowed."
            )
        described = {r.rule_id: r.description for r in hits}
        return ComplianceDecision(
            allowed=False,
            rule_ids=rule_ids,
            next_allowed_at=None,
            explanation="Blocked: "
            + "; ".join(described.get(rid, rid) for rid in rule_ids)
            + " (RBI RBC Directions para 454Z).",
        )
