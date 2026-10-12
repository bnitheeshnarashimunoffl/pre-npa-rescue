import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import orm
from app.audit import DbContactLogger
from app.db import get_session
from app.errors import conflict, not_found
from app.providers import Deps
from app.ratelimit import RateLimits, enforce
from app.routers._common import ERRORS, access
from app.security import CurrentPrincipal, Principal
from app.services import convert
from npa_contracts.api import ChatSessionCreated, ChatSessionCreateRequest, ChatTranscript
from npa_contracts.enums import Actor, Channel, Lang, Role
from npa_contracts.models import BotReply, ChatTurnRequest, ComplianceDecision, ContactEvent


def _chat_rate_limit(principal: CurrentPrincipal) -> None:
    enforce(RateLimits.chat(), principal.username)


router = APIRouter(
    prefix="/chat",
    tags=["chat"],
    dependencies=[Depends(_chat_rate_limit)],
    responses=ERRORS,
)

DbSession = Annotated[Session, Depends(get_session)]

# Bot flags that must stop or pause collection contact (RBI RBC Directions para 454Y(6)).
FLAG_TO_CONTACT_FLAG = {
    "bereavement": "bereavement",
    "medical_emergency": "medical_emergency",
    "distress_detected": "distress",
    "do_not_contact": "do_not_contact",
}
# Sent instead of a bot reply the compliance guard rejects (never the rejected text).
BLOCKED_REPLY = {
    Lang.EN: "Sorry, something went wrong. Please try again, or ask to speak to an officer.",
    Lang.TA: "மன்னிக்கவும், ஏதோ தவறு நடந்துவிட்டது. மீண்டும் முயற்சிக்கவும் அல்லது ஒரு "
    "அதிகாரியுடன் பேசக் கேளுங்கள்.",
    Lang.HI: "क्षमा करें, कुछ गड़बड़ हो गई। कृपया फिर से कोशिश करें या किसी अधिकारी से बात करने के लिए कहें।",
}
_CUSTOMER_INITIATED = ComplianceDecision(
    allowed=True, rule_ids=[], next_allowed_at=None, explanation="Customer-initiated message."
)


def _owned_session(session: Session, sid: str, principal: Principal) -> orm.ChatSession:
    row = session.get(orm.ChatSession, sid)
    if row is None or (
        principal.role is Role.CUSTOMER and row.customer_id != principal.customer_id
    ):
        not_found("Chat session", sid)
    return row


@router.post(
    "/sessions",
    response_model=ChatSessionCreated,
    status_code=status.HTTP_201_CREATED,
    **access("customer"),
)
def create_session(
    principal: CurrentPrincipal,
    session: DbSession,
    body: ChatSessionCreateRequest | None = None,
) -> ChatSessionCreated:
    """Start a chat session tied to the logged-in customer."""
    customer = session.get(orm.Customer, principal.customer_id)
    if customer is None:
        not_found("Customer", str(principal.customer_id))
    row = orm.ChatSession(
        session_id=f"SESS-{uuid.uuid4()}",
        customer_id=customer.customer_id,
        lang=(body.lang if body and body.lang else customer.language_pref),
        created_at=datetime.now(UTC),
    )
    session.add(row)
    session.commit()
    return ChatSessionCreated(
        session_id=row.session_id,
        customer_id=row.customer_id,
        lang=row.lang,
        created_at=convert.utc(row.created_at),
    )


def _next_seq(session: Session, sid: str) -> int:
    return (
        session.scalar(select(func.max(orm.ChatTurn.seq)).where(orm.ChatTurn.session_id == sid))
        or 0
    ) + 1


def _event(
    row: orm.ChatSession,
    account_id: str,
    direction: Literal["inbound", "outbound"],
    actor: Actor,
    text: str,
    lang: Lang,
    decision: ComplianceDecision,
    ts: datetime,
) -> ContactEvent:
    # The chat UI shows the "this conversation is recorded" notice (RBI para 454P).
    return ContactEvent(
        event_id=f"EVT-{uuid.uuid4()}",
        customer_id=row.customer_id,
        account_id=account_id,
        channel=Channel.CHAT,
        direction=direction,
        actor=actor,
        ts=ts,
        content=text,
        lang=lang,
        recorded_notice_given=True,
        compliance=decision,
        outcome=None,
    )


@router.post("/sessions/{sid}/messages", response_model=BotReply, **access("customer"))
def post_message(
    sid: str,
    body: ChatTurnRequest,
    principal: CurrentPrincipal,
    session: DbSession,
    providers: Deps,
) -> BotReply:
    """One chat turn: ``ChatEngine.handle`` -> ``BotReply`` (fixture-backed until task 5.1)."""
    row = _owned_session(session, sid, principal)
    if row.closed_at is not None:
        conflict("Chat session is closed.", {"session_id": sid})
    customer = session.get(orm.Customer, row.customer_id)
    assert customer is not None
    now = datetime.now(UTC)
    in_lang = body.lang or Lang(row.lang)
    seq = _next_seq(session, sid)
    session.add(
        orm.ChatTurn(
            session_id=sid,
            seq=seq,
            actor=Actor.CUSTOMER,
            text=body.text,
            lang=in_lang,
            flags=[],
            ts=now,
        )
    )
    logger = DbContactLogger(session)
    logger.log(
        _event(
            row,
            customer.account_id,
            "inbound",
            Actor.CUSTOMER,
            body.text,
            in_lang,
            _CUSTOMER_INITIATED,
            now,
        )
    )

    reply = providers.chat.handle(sid, row.customer_id, body)
    # Every outbound customer contact goes through the compliance guard (A3.4).
    decision = providers.compliance.check_text(reply.text, reply.lang)
    if not decision.allowed:
        reply = reply.model_copy(
            update={
                "text": BLOCKED_REPLY[reply.lang],
                "offers": [],
                "quick_replies": [],
                "flags": [*reply.flags, "compliance_blocked"],
            }
        )
    sent = datetime.now(UTC)
    session.add(
        orm.ChatTurn(
            session_id=sid,
            seq=seq + 1,
            actor=Actor.BOT,
            text=reply.text,
            lang=reply.lang,
            flags=list(reply.flags),
            ts=sent,
        )
    )
    logger.log(
        _event(
            row, customer.account_id, "outbound", Actor.BOT, reply.text, reply.lang, decision, sent
        )
    )
    for flag in reply.flags:
        if flag in FLAG_TO_CONTACT_FLAG:
            session.add(
                orm.ContactFlag(
                    customer_id=row.customer_id,
                    flag=FLAG_TO_CONTACT_FLAG[flag],
                    reason=f"chat {sid}",
                    source=Actor.BOT,
                )
            )
    for offer in reply.offers:
        if session.get(orm.Offer, offer.offer_id) is None:
            session.add(convert.offer_row(offer))
    row.state = reply.state
    session.commit()
    return reply


@router.get(
    "/sessions/{sid}/stream",
    response_model=None,
    responses={200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}}},
    **access("customer"),
)
def stream(sid: str, principal: CurrentPrincipal, session: DbSession) -> StreamingResponse:
    """Optional SSE stream of reply chunks."""
    _owned_session(session, sid, principal)
    last = session.scalars(
        select(orm.ChatTurn)
        .where(orm.ChatTurn.session_id == sid, orm.ChatTurn.actor == Actor.BOT)
        .order_by(orm.ChatTurn.seq.desc())
        .limit(1)
    ).first()
    text = last.text if last else ""

    def events() -> Iterator[str]:
        for i in range(0, len(text), 40):
            yield f"data: {text[i : i + 40]}\n\n"
        yield "event: done\ndata: \n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@router.get(
    "/sessions/{sid}",
    response_model=ChatTranscript,
    **access("customer", "hardship_officer", "auditor"),
)
def transcript(sid: str, principal: CurrentPrincipal, session: DbSession) -> ChatTranscript:
    row = _owned_session(session, sid, principal)
    return ChatTranscript(
        session_id=row.session_id,
        customer_id=row.customer_id,
        created_at=convert.utc(row.created_at),
        turns=[convert.chat_turn(t) for t in row.turns],
    )
