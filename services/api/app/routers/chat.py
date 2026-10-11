from fastapi import APIRouter, status

from app.errors import not_implemented
from app.fixtures import load_fixture
from app.routers._common import PROTECTED, roles
from npa_contracts.api import ChatSessionCreated, ChatSessionCreateRequest, ChatTranscript
from npa_contracts.models import BotReply, ChatTurnRequest

router = APIRouter(prefix="/chat", tags=["chat"], **PROTECTED)


@router.post(
    "/sessions",
    response_model=ChatSessionCreated,
    status_code=status.HTTP_201_CREATED,
    openapi_extra=roles("customer"),
)
def create_session(body: ChatSessionCreateRequest | None = None) -> ChatSessionCreated:
    """Start a chat session tied to the logged-in customer."""
    not_implemented("5.1")


@router.post("/sessions/{sid}/messages", response_model=BotReply, openapi_extra=roles("customer"))
def post_message(sid: str, body: ChatTurnRequest) -> BotReply:
    """One chat turn: ``ChatEngine.handle`` -> ``BotReply`` (fixture-backed until task 5.1)."""
    reply = BotReply.model_validate(load_fixture("bot_reply_offer.json"))
    return reply.model_copy(update={"session_id": sid})


@router.get(
    "/sessions/{sid}/stream",
    response_model=None,
    responses={200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}}},
    openapi_extra=roles("customer"),
)
def stream(sid: str) -> None:
    """Optional SSE stream of reply chunks."""
    not_implemented("5.1")


@router.get(
    "/sessions/{sid}",
    response_model=ChatTranscript,
    openapi_extra=roles("customer", "hardship_officer", "auditor"),
)
def transcript(sid: str) -> ChatTranscript:
    not_implemented("5.1")
