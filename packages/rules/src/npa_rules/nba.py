"""Next-best-action service (task 3.4). Implements ``npa_contracts.providers.NBAProvider``.

Turns WS2's model outputs (``RiskScore``, ``SegmentResult``, ``UpliftResult`` from an injected
``RiskProvider``) plus the compliance guard and the policy into **one** recommended action
per account. Rules, evaluated in order (first match wins):

=====  =====================================================  ==================================
 #     Condition                                              Action
=====  =====================================================  ==================================
 1     do-not-contact flag active                             ``no_contact`` (RBC 454Y(6))
 2     risk band low and segment ``not_at_risk``              ``no_contact``
 3     uplift group ``sleeping_dog``                          ``no_contact`` (statement message
                                                              only)
 4     segment ``forgot`` or uplift ``sure_thing``            ``reminder`` (SMS)
 5     segment ``cant_pay`` and estimated capacity ≈ 0        ``hardship_officer`` (call)
 6     segment ``cant_pay`` and uplift ``persuadable``        ``chat_invite`` (relief options
                                                              pre-computed)
 7     uplift ``persuadable`` (other segments)                ``chat_invite``, or ``agent_call``
                                                              after N ignored invites
 8     segment ``wont_pay`` or uplift ``lost_cause``          ``firm_process``: compliant
                                                              written notice + agent call
                                                              within the rules, never harsh
=====  =====================================================  ==================================

"Capacity ≈ 0" means the estimated affordable payment is below the policy's minimum EMI: too
little for any plan, so a person, not a bot, should talk to the customer.

``firm_process`` is procedural, never harsher in tone: every message still goes through
``check_text`` (RBC 454Z).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from npa_contracts.enums import (
    Actor,
    Channel,
    NextAction,
    RiskBand,
    Segment,
    UpliftGroup,
)
from npa_contracts.models import (
    NextBestAction,
    QueueItem,
    RiskScore,
    SegmentResult,
    UpliftResult,
)
from npa_contracts.providers import ComplianceProvider, PolicyProvider, RiskProvider
from npa_rules.policy_loader import Policy
from npa_rules.relief_calc import AccountSnapshot, estimate_affordability

__all__ = ["NextBestActionService", "QueueInput", "StaticRiskProvider", "prioritise", "priority"]

AccountLookup = Callable[[str], AccountSnapshot]

_CHANNEL: dict[NextAction, Channel | None] = {
    NextAction.NO_CONTACT: None,
    NextAction.REMINDER: Channel.SMS,
    NextAction.CHAT_INVITE: Channel.CHAT,
    NextAction.AGENT_CALL: Channel.CALL,
    NextAction.HARDSHIP_OFFICER: Channel.CALL,
    NextAction.FIRM_PROCESS: Channel.EMAIL,  # written notice first
}
_ACTOR: dict[NextAction, Actor] = {
    NextAction.AGENT_CALL: Actor.AGENT,
    NextAction.HARDSHIP_OFFICER: Actor.HARDSHIP_OFFICER,
}


def _utc_now() -> datetime:
    return datetime.now(UTC)


class NextBestActionService:
    """``NBAProvider``.

    ``accounts_by_account_id`` returns the :class:`AccountSnapshot` for an account id (WS5).
    ``chat_invites_ignored(account_id)`` counts unanswered chat invites (default: none).
    ``policy_provider``, if given, pre-computes relief options for ``chat_invite`` so the
    chatbot can offer them at once.
    """

    def __init__(
        self,
        policy: Policy,
        risk: RiskProvider,
        guard: ComplianceProvider,
        accounts_by_account_id: AccountLookup,
        *,
        policy_provider: PolicyProvider | None = None,
        chat_invites_ignored: Callable[[str], int] = lambda _account_id: 0,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._policy = policy
        self._risk = risk
        self._guard = guard
        self._accounts = accounts_by_account_id
        self._policy_provider = policy_provider
        self._ignored = chat_invites_ignored
        self._clock = clock

    def reload(self, policy: Policy) -> None:
        self._policy = policy

    def next_best_action(self, account_id: str, as_of_month: str) -> NextBestAction:
        risk = self._risk.risk(account_id, as_of_month)
        segment = self._risk.segment(account_id, as_of_month)
        uplift = self._risk.uplift(account_id, as_of_month)
        return self.decide(risk, segment, uplift)

    def decide(
        self, risk: RiskScore, segment: SegmentResult, uplift: UpliftResult
    ) -> NextBestAction:
        """Apply the rule table to already-scored outputs (used by batch scoring too)."""
        ctx = self._accounts(risk.account_id)
        action, rule = self._rule(ctx, risk, segment, uplift)
        reasons = [r.code for r in risk.reasons] + [rule]
        channel = _CHANNEL[action]
        earliest: datetime | None = None
        if channel is not None:
            now = self._clock()
            d = self._guard.check_contact(
                ctx.customer_id, channel, now, _ACTOR.get(action, Actor.SYSTEM)
            )
            earliest = now if d.allowed else d.next_allowed_at
            reasons += [f"WAIT:{rid}" for rid in d.rule_ids if not d.allowed]
        if action is NextAction.CHAT_INVITE and self._policy_provider is not None:
            afford = estimate_affordability(ctx, None, self._policy.affordability)
            if self._policy_provider.relief_options(ctx.customer_id, afford):
                reasons.append("RELIEF_OPTIONS_READY")
        return NextBestAction(
            account_id=risk.account_id,
            action=action,
            channel=channel,
            earliest_contact_at=earliest,
            reason_codes=reasons,
            risk=risk,
            segment=segment,
            uplift=uplift,
        )

    def _rule(
        self, ctx: AccountSnapshot, risk: RiskScore, seg: SegmentResult, up: UpliftResult
    ) -> tuple[NextAction, str]:
        flags = set(ctx.do_not_contact_flags) & set(self._policy.contact.do_not_contact_flags)
        s, g = seg.segment, up.uplift_group
        if flags:
            return NextAction.NO_CONTACT, "RULE_DO_NOT_CONTACT_FLAG"
        if risk.risk_band is RiskBand.LOW and s is Segment.NOT_AT_RISK:
            return NextAction.NO_CONTACT, "RULE_LOW_RISK"
        if g is UpliftGroup.SLEEPING_DOG:
            return NextAction.NO_CONTACT, "RULE_SLEEPING_DOG_PASSIVE_ONLY"
        if s is Segment.FORGOT or g is UpliftGroup.SURE_THING:
            return NextAction.REMINDER, "RULE_REMINDER"
        if s is Segment.CANT_PAY:
            capacity = estimate_affordability(ctx, None, self._policy.affordability)
            if (
                capacity.max_monthly_payment_paise
                < self._policy.options.emi_conversion.min_emi_paise
            ):
                return NextAction.HARDSHIP_OFFICER, "RULE_CANT_PAY_ZERO_CAPACITY"
            if g is UpliftGroup.PERSUADABLE:
                return NextAction.CHAT_INVITE, "RULE_CANT_PAY_PERSUADABLE"
        if g is UpliftGroup.PERSUADABLE:
            if self._ignored(ctx.account_id) >= self._policy.nba.chat_invites_ignored_before_call:
                return NextAction.AGENT_CALL, "RULE_PERSUADABLE_CHAT_IGNORED"
            return NextAction.CHAT_INVITE, "RULE_PERSUADABLE"
        # Rule 8: every uplift group except lost_cause has matched by now, so what is left is
        # segment wont_pay or uplift lost_cause.
        return NextAction.FIRM_PROCESS, "RULE_FIRM_PROCESS"


# --- collector queue -------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class QueueInput:
    nba: NextBestAction
    account: AccountSnapshot
    customer_name: str


def priority(nba: NextBestAction, outstanding_paise: int, policy: Policy) -> Decimal:
    """Expected benefit of acting: ``p_roll_forward × max(uplift_score, 0) × outstanding``.

    Hardship cases (``hardship_officer`` or segment ``cant_pay``) are boosted and never fall
    below ``p_roll_forward × outstanding × hardship_floor_weight``. ``no_contact`` is 0.
    Never "ease of extraction": a collector's queue must not reward pressing the customers
    easiest to squeeze (RBI RBC Directions para 454Q, incentives must not encourage harsh
    practices).
    """
    if nba.action is NextAction.NO_CONTACT:
        return Decimal(0)
    p = Decimal(str(nba.risk.p_roll_forward))
    u = max(Decimal(str(nba.uplift.uplift_score)), Decimal(0))
    value = p * u * outstanding_paise
    if nba.action is NextAction.HARDSHIP_OFFICER or nba.segment.segment is Segment.CANT_PAY:
        floor = p * outstanding_paise * policy.nba.hardship_floor_weight
        value = max(value * policy.nba.hardship_boost, floor)
    return value


def prioritise(items: Sequence[QueueInput], policy: Policy) -> list[QueueItem]:
    """Collector queue ordered by :func:`priority`, scaled to 0..1 within the batch."""
    raw = [priority(i.nba, i.account.total_outstanding_paise, policy) for i in items]
    top = max(raw, default=Decimal(0)) or Decimal(1)
    queue = [
        QueueItem(
            account_id=i.account.account_id,
            customer_name=i.customer_name,
            bucket=i.account.bucket,
            dpd=i.account.dpd,
            total_due_paise=i.account.total_outstanding_paise,
            nba=i.nba,
            priority=float(round(r / top, 4)),
        )
        for i, r in zip(items, raw, strict=True)
    ]
    return sorted(queue, key=lambda q: (-q.priority, q.account_id))


# --- fixture-backed RiskProvider (until WS2 ships, A10.1) ------------------------------------


class StaticRiskProvider:
    """``RiskProvider`` over fixed outputs, e.g. ``contracts/fixtures/queue.json``."""

    def __init__(self, scores: dict[str, tuple[RiskScore, SegmentResult, UpliftResult]]) -> None:
        self._scores = scores

    @classmethod
    def from_queue_fixture(cls, data: dict[str, Any]) -> StaticRiskProvider:
        scores: dict[str, tuple[RiskScore, SegmentResult, UpliftResult]] = {}
        for item in data["items"]:
            n = item["nba"]
            scores[item["account_id"]] = (
                RiskScore.model_validate(n["risk"]),
                SegmentResult.model_validate(n["segment"]),
                UpliftResult.model_validate(n["uplift"]),
            )
        return cls(scores)

    def risk(self, account_id: str, as_of_month: str) -> RiskScore:
        return self._scores[account_id][0]

    def segment(self, account_id: str, as_of_month: str) -> SegmentResult:
        return self._scores[account_id][1]

    def uplift(self, account_id: str, as_of_month: str) -> UpliftResult:
        return self._scores[account_id][2]

    def score_batch(
        self, as_of_month: str
    ) -> Iterator[tuple[RiskScore, SegmentResult, UpliftResult]]:
        return iter(self._scores.values())
