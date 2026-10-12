"""Multilingual Hardship Dialogue Engine (WS4 Task 4.1).

Orchestrates conversation state machine, NLU, regulatory notices, and provider interactions.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from npa_chat.flows import (
    handle_affordability_turn,
    handle_hardship_turn,
    handle_offer_turn,
    present_relief_options,
)
from npa_chat.i18n import get_string
from npa_chat.language import detect_language_switch_request, resolve_language
from npa_chat.nlu import NLU, Intent
from npa_chat.state import ChatState, ConversationState, InMemorySessionStore, SessionStore
from npa_contracts.enums import Actor, Channel, Lang
from npa_contracts.models import (
    BotReply,
    ChatTurnRequest,
    ComplianceDecision,
    ContactEvent,
    Offer,
    QuickReply,
)
from npa_contracts.providers import (
    CallbackScheduler,
    ComplaintSink,
    ComplianceProvider,
    ContactLogger,
    CustomerContextProvider,
    LLMClient,
    PolicyProvider,
    RiskProvider,
)

logger = logging.getLogger(__name__)


class ChatEngine:
    """Core dialogue engine governing Pre-NPA hardship conversations."""

    def __init__(
        self,
        risk_provider: RiskProvider,
        policy_provider: PolicyProvider,
        compliance_provider: ComplianceProvider,
        contact_logger: ContactLogger,
        complaint_sink: ComplaintSink,
        callback_scheduler: CallbackScheduler,
        customer_context_provider: CustomerContextProvider,
        llm_client: LLMClient,
        session_store: SessionStore | None = None,
    ) -> None:
        self.risk_provider = risk_provider
        self.policy_provider = policy_provider
        self.compliance_provider = compliance_provider
        self.contact_logger = contact_logger
        self.complaint_sink = complaint_sink
        self.callback_scheduler = callback_scheduler
        self.customer_context_provider = customer_context_provider
        self.llm_client = llm_client
        self.session_store: SessionStore = session_store or InMemorySessionStore()
        self.nlu = NLU(llm_client=llm_client)

    def handle(self, session_id: str, customer_id: str, req: ChatTurnRequest) -> BotReply:
        """Handle a single dialogue turn and produce a compliant BotReply."""
        now = datetime.now(UTC)

        # 1. Load or initialise session state
        state = self.session_store.get(session_id)
        if state is None:
            state = ConversationState(
                session_id=session_id,
                customer_id=customer_id,
            )

        # 2. Retrieve customer context
        ctx = self.customer_context_provider.context(customer_id)
        first_name = (ctx.get("full_name") or "Customer").split()[0]
        context_lang_str = str(ctx.get("language_pref", "en")).lower()
        default_lang = (
            Lang.TA
            if "ta" in context_lang_str
            else (Lang.HI if "hi" in context_lang_str else Lang.EN)
        )

        # 3. Resolve active language
        if req.lang is not None:
            active_lang = req.lang
        elif len(state.history) == 0:
            active_lang = resolve_language(req.text, default_lang)
        else:
            active_lang = resolve_language(req.text, state.lang)

        # Check for explicit language switch request
        lang_switch = detect_language_switch_request(req.text)
        is_explicit_switch = False
        if lang_switch and lang_switch != state.lang:
            active_lang = lang_switch
            state.lang = active_lang
            state.add_flag("language_switched")
            is_explicit_switch = True
        else:
            state.lang = active_lang

        # 4. Log incoming contact event (RBI para 454P)
        inbound_event = ContactEvent(
            event_id=f"EVT-{uuid.uuid4()}",
            customer_id=customer_id,
            account_id=str(ctx.get("account_id", customer_id)),
            channel=Channel.CHAT,
            direction="inbound",
            actor=Actor.CUSTOMER,
            ts=now,
            content=req.text,
            lang=state.lang,
            recorded_notice_given=state.recording_notice_given,
            compliance=ComplianceDecision(
                allowed=True,
                rule_ids=[],
                next_allowed_at=None,
                explanation="Inbound message received.",
            ),
            outcome=None,
        )
        self.contact_logger.log(inbound_event)
        state.history.append({"role": "user", "text": req.text, "ts": now.isoformat()})

        # 5. Process turn based on state machine & NLU
        quick_replies: list[QuickReply] = []
        flags_to_add: list[str] = []
        presented_offers: list[Offer] = []

        # First turn: Greeting, Recording Notice (RBI para 454P), DPDP Notice & Language Choices
        if not state.recording_notice_given:
            state.recording_notice_given = True
            state.dpdp_notice_given = True

            greeting_line = get_string("greeting", state.lang, name=first_name)
            recording_line = get_string("recording_notice", state.lang)
            dpdp_line = get_string("dpdp_notice", state.lang)

            reply_text = f"{greeting_line}\n\n{recording_line}\n{dpdp_line}"

            quick_replies = [
                QuickReply(id="lang_en", label="English"),
                QuickReply(id="lang_ta", label="தமிழ்"),
                QuickReply(id="lang_hi", label="हिन्दी"),
            ]
            state.transition_to(ChatState.CONSENT_NOTICE)

        elif is_explicit_switch:
            # Language was switched on this turn
            ack_line = get_string("language_switched", state.lang)
            next_line = get_string("hardship_prompt", state.lang)
            reply_text = f"{ack_line}\n\n{next_line}"
            state.transition_to(ChatState.HARDSHIP_DISCLOSURE)

        else:
            # Parse customer message via NLU
            nlu_res = self.nlu.parse(req.text, current_lang=state.lang)

            # Global Interrupt: Severe Distress (Task 4.4 / distress.py integration)
            if nlu_res.intent == Intent.DISTRESS or nlu_res.distress_score >= 0.8:
                state.add_flag("distress_detected")
                state.transition_to(ChatState.DISTRESS)
                distress_msg = get_string("distress_response", state.lang)
                helpline_msg = get_string("tele_manas_notice", state.lang)
                reply_text = f"{distress_msg}\n\n{helpline_msg}"
                quick_replies = [
                    QuickReply(id="speak_officer", label=get_string("lang_en", state.lang))
                ]

            # Global Interrupt: Complaint Capture (Task 4.5 / IS 10002)
            elif nlu_res.intent == Intent.COMPLAIN:
                state.add_flag("complaint_reported")
                state.transition_to(ChatState.COMPLAINT)
                complaint = self.complaint_sink.open(
                    customer_id=customer_id,
                    category="customer_complaint",
                    text=req.text,
                    lang=state.lang,
                )
                state.complaint_docket_no = complaint.docket_no
                grievance = self.policy_provider.grievance_officer()
                footer = get_string(
                    "grievance_footer",
                    state.lang,
                    name=grievance.name,
                    email=grievance.email,
                    phone=grievance.phone,
                    address=grievance.address,
                )
                reply_text = (
                    f"Your complaint has been registered with docket number {complaint.docket_no}. "
                    f"Our grievance team will review it within 30 days.\n\n{footer}"
                )

            # Consent turn / language selection transition
            elif state.current_state == ChatState.CONSENT_NOTICE:
                state.transition_to(ChatState.HARDSHIP_DISCLOSURE)
                reply_text = get_string("hardship_prompt", state.lang)

            # Hardship disclosure turn (Task 4.2)
            elif state.current_state == ChatState.HARDSHIP_DISCLOSURE:
                hardship_res = handle_hardship_turn(state, req.text, nlu_res)
                reply_text = hardship_res.reply_text
                quick_replies = hardship_res.quick_replies
                state.transition_to(hardship_res.next_state)
                if hardship_res.pause_suggested:
                    state.pause_outreach_suggested = True
                for f in hardship_res.flags:
                    state.add_flag(f)

            # Affordability assessment turn (Task 4.2)
            elif state.current_state == ChatState.AFFORDABILITY:
                aff_res = handle_affordability_turn(state, req.text, nlu_res)
                for f in aff_res.flags:
                    state.add_flag(f)

                if aff_res.next_state == ChatState.OPTIONS and aff_res.affordability:
                    state.transition_to(ChatState.OPTIONS)
                    account_id = str(ctx.get("account_id", customer_id))
                    opts_text, offers_list, q_replies = present_relief_options(
                        customer_id=customer_id,
                        account_id=account_id,
                        affordability=aff_res.affordability,
                        policy_provider=self.policy_provider,
                        lang=state.lang,
                    )
                    reply_text = opts_text
                    quick_replies = q_replies
                    state.presented_offers = offers_list
                    presented_offers = offers_list
                elif aff_res.next_state == ChatState.ZERO_CAPACITY:
                    state.transition_to(ChatState.ZERO_CAPACITY)
                    reply_text = (
                        "We understand you currently have no surplus capacity to make payments. "
                        "We will not ask you for payments right now."
                    )
                else:
                    reply_text = aff_res.reply_text
                    quick_replies = aff_res.quick_replies

            # Plan offer turn (Task 4.3)
            elif state.current_state == ChatState.OPTIONS:
                offer_res = handle_offer_turn(
                    state=state,
                    text=req.text,
                    nlu_result=nlu_res,
                    policy_provider=self.policy_provider,
                    risk_provider=self.risk_provider,
                )
                reply_text = offer_res.reply_text
                quick_replies = offer_res.quick_replies
                state.transition_to(offer_res.next_state)
                presented_offers = offer_res.offers
                for f in offer_res.flags:
                    state.add_flag(f)

            else:
                # Default safe conversational fallback
                reply_text = get_string("fallback_safe", state.lang)

        # 6. Apply compliance check to outgoing text (RBI para 454Z)
        compliance_check = self.compliance_provider.check_text(reply_text, state.lang)
        if not compliance_check.allowed:
            reply_text = get_string("fallback_safe", state.lang)
            state.add_flag("output_blocked")

        for flag in flags_to_add:
            state.add_flag(flag)

        # 7. Log outgoing contact event (RBI para 454P)
        outbound_event = ContactEvent(
            event_id=f"EVT-{uuid.uuid4()}",
            customer_id=customer_id,
            account_id=str(ctx.get("account_id", customer_id)),
            channel=Channel.CHAT,
            direction="outbound",
            actor=Actor.BOT,
            ts=datetime.now(UTC),
            content=reply_text,
            lang=state.lang,
            recorded_notice_given=True,
            compliance=compliance_check,
            outcome=None,
        )
        self.contact_logger.log(outbound_event)
        state.history.append({"role": "bot", "text": reply_text, "ts": now.isoformat()})

        # 8. Persist state
        self.session_store.save(state)

        # 9. Build and return BotReply
        return BotReply(
            session_id=session_id,
            text=reply_text,
            lang=state.lang,
            quick_replies=quick_replies,
            offers=presented_offers or state.presented_offers,
            handoff=None,
            complaint=None,
            flags=list(state.flags),
            state=state.current_state.value,
        )


def build_engine(
    risk_provider: RiskProvider,
    policy_provider: PolicyProvider,
    compliance_provider: ComplianceProvider,
    contact_logger: ContactLogger,
    complaint_sink: ComplaintSink,
    callback_scheduler: CallbackScheduler,
    customer_context_provider: CustomerContextProvider,
    llm_client: LLMClient,
    session_store: SessionStore | None = None,
) -> ChatEngine:
    """Factory creating an instance of ChatEngine conforming to ChatEngineProtocol."""
    return ChatEngine(
        risk_provider=risk_provider,
        policy_provider=policy_provider,
        compliance_provider=compliance_provider,
        contact_logger=contact_logger,
        complaint_sink=complaint_sink,
        callback_scheduler=callback_scheduler,
        customer_context_provider=customer_context_provider,
        llm_client=llm_client,
        session_store=session_store,
    )
