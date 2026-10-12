"""Policy engine (task 3.1): the only place relief options come from. Implements
``npa_contracts.providers.PolicyProvider``.

The AI proposes; the rules decide. An option is returned only when the bank policy enables it
and the account is eligible; every amount is sized by :mod:`npa_rules.relief_calc`; every
option carries its ``policy_ref``, ``regulatory_refs`` and mandatory ``disclosure_keys``.

Order is least harmful first: insurance referral → fee waiver → EMI → restructuring →
settlement → review date.

Zero capacity (``max_monthly_payment_paise == 0``): only insurance referral (if covered), fee
waiver (if eligible), and restructuring / settlement / review date with
``requires_human_approval = True``. Never an EMI the customer cannot pay
(RBI RBC Directions para 454D: documented engagement before escalation).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from npa_contracts.enums import Actor, OfferStatus, ReliefType
from npa_contracts.models import Affordability, GrievanceOfficer, Offer, ReliefOption
from npa_rules.policy_loader import OptionPolicy, Policy, load_policy
from npa_rules.relief_calc import (
    AccountSnapshot,
    emi_amount,
    size_emi,
    size_settlement,
    size_waiver,
)

__all__ = ["PolicyEngine", "UnknownOptionError"]

AccountLookup = Callable[[str], AccountSnapshot]


class UnknownOptionError(KeyError):
    """``propose_offer`` was called with an option id that ``relief_options`` never returned."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _new_offer_id() -> str:
    return f"OFFER-{uuid.uuid4()}"


def _rupees(paise: int) -> str:
    rupees, rem = divmod(paise, 100)
    return f"Rs {rupees:,}" + (f".{rem:02d}" if rem else "")


class PolicyEngine:
    """``PolicyProvider`` over a validated :class:`Policy`.

    ``accounts`` returns the :class:`AccountSnapshot` for a customer id (WS5 injects a DB-backed
    callable; tests inject a dict lookup). ``clock`` and ``id_factory`` are injectable for
    deterministic tests. Options computed by :meth:`relief_options` are remembered per customer
    so :meth:`propose_offer` can only offer what the rules actually returned.
    """

    def __init__(
        self,
        policy: Policy,
        accounts: AccountLookup,
        *,
        clock: Callable[[], datetime] = _utc_now,
        id_factory: Callable[[], str] = _new_offer_id,
    ) -> None:
        self._policy = policy
        self._accounts = accounts
        self._clock = clock
        self._id_factory = id_factory
        self._issued: dict[str, dict[str, tuple[str, ReliefOption]]] = {}

    @classmethod
    def from_path(cls, path: str | None, accounts: AccountLookup) -> PolicyEngine:
        return cls(load_policy(path), accounts)

    @property
    def policy(self) -> Policy:
        return self._policy

    def reload(self, policy: Policy) -> None:
        """Swap in a newly validated policy (``PUT /admin/policy``); forget issued options."""
        self._policy = policy
        self._issued.clear()

    # --- PolicyProvider ----------------------------------------------------------------------

    def grievance_officer(self) -> GrievanceOfficer:
        """RBI RBC Directions para 454AA: shown on every recovery communication."""
        return self._policy.grievance_officer

    def relief_options(self, customer_id: str, affordability: Affordability) -> list[ReliefOption]:
        if affordability.customer_id != customer_id:
            raise ValueError("affordability belongs to a different customer")
        ctx = self._accounts(customer_id)
        capacity = affordability.max_monthly_payment_paise
        options = [
            o
            for o in (
                self._insurance(ctx),
                self._fee_waiver(ctx),
                self._emi(ctx, capacity),
                self._restructuring(ctx, capacity),
                self._settlement(ctx, capacity),
                self._review_date(ctx, capacity),
            )
            if o is not None
        ]
        self._issued[customer_id] = {o.option_id: (ctx.account_id, o) for o in options}
        return options

    def propose_offer(self, customer_id: str, option_id: str, actor: Actor) -> Offer:
        """Offer for an option previously returned to this customer.

        Status ``approved`` when the option needs no human approval, else ``proposed`` (a
        hardship officer approves it: IS/ISO/IEC 38507 human oversight). Expires after
        ``offers.expiry_days`` (bank policy assumption).
        """
        try:
            account_id, option = self._issued[customer_id][option_id]
        except KeyError:
            raise UnknownOptionError(
                f"{option_id!r} was not returned by relief_options for {customer_id!r}"
            ) from None
        now = self._clock()
        auto = not option.requires_human_approval
        return Offer(
            offer_id=self._id_factory(),
            customer_id=customer_id,
            account_id=account_id,
            option=option,
            status=OfferStatus.APPROVED if auto else OfferStatus.PROPOSED,
            proposed_by=actor,
            approved_by="policy_engine" if auto else None,
            created_at=now,
            expires_at=now + timedelta(days=self._policy.offers.expiry_days),
        )

    # --- option builders ---------------------------------------------------------------------

    def _make(
        self,
        name: str,
        rtype: ReliefType,
        ctx: AccountSnapshot,
        suffix: str,
        reason: str,
        *,
        monthly: int | None = None,
        tenure: int | None = None,
        waiver: int | None = None,
        settlement: int | None = None,
        force_human: bool = False,
        extra: OptionPolicy | None = None,
        extra_name: str | None = None,
    ) -> ReliefOption:
        opt = self._policy.option(name)
        regs = list(opt.regulatory_refs)
        keys = list(opt.disclosure_keys)
        human = opt.requires_human_approval or force_human
        if extra is not None:
            regs += [r for r in extra.regulatory_refs if r not in regs]
            keys += [k for k in extra.disclosure_keys if k not in keys]
            human = human or extra.requires_human_approval
        policy_ref = self._policy.policy_ref(name)
        if extra_name is not None:
            policy_ref += f"+{self._policy.option(extra_name).policy_ref}"
        return ReliefOption(
            option_id=f"OPT-{ctx.account_id}-{suffix}",
            type=rtype,
            monthly_amount_paise=monthly,
            tenure_months=tenure,
            waiver_paise=waiver,
            settlement_amount_paise=settlement,
            policy_ref=policy_ref,
            regulatory_refs=regs,
            disclosure_keys=keys,
            requires_human_approval=human,
            eligibility_reason=reason,
        )

    def _eligible(self, name: str, ctx: AccountSnapshot) -> bool:
        opt = self._policy.option(name)
        return opt.enabled and ctx.bucket in opt.eligible_buckets

    def _insurance(self, ctx: AccountSnapshot) -> ReliefOption | None:
        if not self._eligible("insurance_referral", ctx):
            return None
        if not ctx.has_card_insurance or ctx.insurance_cover_type == "none":
            return None
        cover = ctx.insurance_cover_type.replace("_", " ")
        return self._make(
            "insurance_referral",
            ReliefType.INSURANCE_REFERRAL,
            ctx,
            "INSURANCE",
            f"Card carries {cover} insurance cover; a claim may cover dues (insurer decides).",
        )

    def _waiver_amount(self, ctx: AccountSnapshot) -> int:
        fw = self._policy.options.fee_waiver
        if (
            not self._eligible("fee_waiver", ctx)
            or ctx.fee_waivers_last_12m >= fw.max_times_per_12m
        ):
            return 0
        return size_waiver(ctx, fw)

    def _fee_waiver(self, ctx: AccountSnapshot) -> ReliefOption | None:
        waiver = self._waiver_amount(ctx)
        if waiver == 0:
            return None
        fw = self._policy.options.fee_waiver
        return self._make(
            "fee_waiver",
            ReliefType.FEE_WAIVER,
            ctx,
            "FEE-WAIVER",
            f"Account is {ctx.bucket.value}; {ctx.fee_waivers_last_12m} waiver(s) in the last 12 "
            f"months (limit {fw.max_times_per_12m}); late charges {_rupees(waiver)} within the "
            f"{_rupees(fw.max_waiver_paise)} cap.",
            waiver=waiver,
        )

    def _emi(self, ctx: AccountSnapshot, capacity: int) -> ReliefOption | None:
        if capacity == 0 or not self._eligible("emi_conversion", ctx):
            return None
        policy = self._policy.options.emi_conversion
        waiver = self._waiver_amount(ctx)
        # Whole balance if affordable; otherwise only the overdue amount (plus the charges,
        # unless they are waived). Briefing B3 task 3.2.
        plan = size_emi(ctx.total_outstanding_paise, capacity, policy)
        scope = "the full outstanding balance"
        if plan is None:
            base = ctx.overdue_paise + (0 if waiver else ctx.waivable_charges_paise)
            plan = size_emi(base, capacity, policy)
            scope = "the overdue amount" + ("" if waiver else " plus charges")
        if plan is None:
            return None
        suffix = f"EMI{plan.tenure_months}" + ("-WAIVER" if waiver else "")
        reason = (
            f"{_rupees(plan.emi_paise)}/month for {plan.tenure_months} months covers {scope} "
            f"({_rupees(plan.principal_paise)}, total interest "
            f"{_rupees(plan.total_interest_paise)} at {policy.interest_rate_annual_pct}% p.a.); "
            f"shortest tenure within the affordable {_rupees(capacity)}/month"
        )
        if waiver:
            reason += f"; late charges of {_rupees(waiver)} waived"
        return self._make(
            "emi_conversion",
            ReliefType.EMI_CONVERSION,
            ctx,
            suffix,
            reason + ".",
            monthly=plan.emi_paise,
            tenure=plan.tenure_months,
            waiver=waiver or None,
            extra=self._policy.options.fee_waiver if waiver else None,
            extra_name="fee_waiver" if waiver else None,
        )

    def _restructuring(self, ctx: AccountSnapshot, capacity: int) -> ReliefOption | None:
        if not self._eligible("restructuring", ctx):
            return None
        rp = self._policy.options.restructuring
        principal = ctx.total_outstanding_paise
        tenure = next(
            (
                n
                for n in range(1, rp.max_tenure_months + 1)
                if capacity > 0
                and emi_amount(principal, n, rp.interest_rate_annual_pct) <= capacity
            ),
            None,
        )
        if tenure is None:
            return self._make(
                "restructuring",
                ReliefType.RESTRUCTURING,
                ctx,
                "RESTRUCTURE-REVIEW",
                f"Account is {ctx.bucket.value} and no instalment over up to "
                f"{rp.max_tenure_months} months fits current capacity; a hardship officer sets "
                f"terms (up to {rp.moratorium_months_max} months' moratorium) under the "
                "board-approved policy.",
                force_human=True,
            )
        monthly = emi_amount(principal, tenure, rp.interest_rate_annual_pct)
        return self._make(
            "restructuring",
            ReliefType.RESTRUCTURING,
            ctx,
            f"RESTRUCTURE{tenure}",
            f"Account is {ctx.bucket.value}; {_rupees(monthly)}/month for {tenure} months fits "
            f"the affordable {_rupees(capacity)}/month. Account will be classified NPA on "
            "restructuring (Prudential Framework 2019).",
            monthly=monthly,
            tenure=tenure,
        )

    def _settlement(self, ctx: AccountSnapshot, capacity: int) -> ReliefOption | None:
        sp = self._policy.options.compromise_settlement
        if not self._eligible("compromise_settlement", ctx) or ctx.dpd < sp.min_ageing_dpd:
            return None
        amount = size_settlement(ctx.total_outstanding_paise, sp.max_sacrifice_pct)
        months = next(
            (
                m
                for m in range(1, sp.payment_window_months_max + 1)
                if capacity > 0 and -(-amount // m) <= capacity
            ),
            None,
        )
        base_reason = (
            f"Account is {ctx.bucket.value} at {ctx.dpd} DPD (policy minimum {sp.min_ageing_dpd}); "
            f"settlement of at least {_rupees(amount)} (bank sacrifice at most "
            f"{sp.max_sacrifice_pct}%)"
        )
        if months is None:
            return self._make(
                "compromise_settlement",
                ReliefType.COMPROMISE_SETTLEMENT,
                ctx,
                "SETTLEMENT-REVIEW",
                base_reason + "; payment terms set by a hardship officer.",
                settlement=amount,
                force_human=True,
            )
        return self._make(
            "compromise_settlement",
            ReliefType.COMPROMISE_SETTLEMENT,
            ctx,
            f"SETTLEMENT{months}",
            base_reason + f", payable over {months} month(s) (at most "
            f"{sp.payment_window_months_max}; longer counts as restructuring).",
            monthly=-(-amount // months),
            tenure=months,
            settlement=amount,
        )

    def _review_date(self, ctx: AccountSnapshot, capacity: int) -> ReliefOption | None:
        if capacity > 0 or not self._eligible("review_date", ctx):
            return None
        days = ", ".join(str(d) for d in self._policy.options.review_date.review_after_days)
        return self._make(
            "review_date",
            ReliefType.REVIEW_DATE,
            ctx,
            "REVIEW-DATE",
            "Zero repayment capacity: documented engagement and an agreed review date "
            f"(in {days} days) with a hardship officer before any escalation.",
            force_human=True,
        )
