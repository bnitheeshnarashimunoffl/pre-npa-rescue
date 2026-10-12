"""Pre-NPA Rescue Chatbot package (WS4)."""

from npa_chat.engine import ChatEngine, build_engine
from npa_chat.flows import (
    classify_hardship,
    estimate_affordability,
    handle_affordability_turn,
    handle_hardship_turn,
)
from npa_chat.i18n import get_bundle, get_string
from npa_chat.language import detect_language_switch_request, detect_script, resolve_language
from npa_chat.llm_client import AnthropicLLMClient, MockLLMClient, get_llm_client
from npa_chat.nlu import NLU, Intent, NLUResult, parse_amount_paise
from npa_chat.state import ChatState, ConversationState, InMemorySessionStore, SessionStore

__version__ = "0.0.1"

__all__ = [
    "NLU",
    "AnthropicLLMClient",
    "ChatEngine",
    "ChatState",
    "ConversationState",
    "InMemorySessionStore",
    "Intent",
    "MockLLMClient",
    "NLUResult",
    "SessionStore",
    "__version__",
    "build_engine",
    "classify_hardship",
    "detect_language_switch_request",
    "detect_script",
    "estimate_affordability",
    "get_bundle",
    "get_llm_client",
    "get_string",
    "handle_affordability_turn",
    "handle_hardship_turn",
    "parse_amount_paise",
    "resolve_language",
]
