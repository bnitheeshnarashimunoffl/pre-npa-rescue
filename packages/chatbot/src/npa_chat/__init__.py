"""Pre-NPA Rescue Chatbot package (WS4)."""

from npa_chat.engine import ChatEngine, build_engine
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
    "detect_language_switch_request",
    "detect_script",
    "get_bundle",
    "get_llm_client",
    "get_string",
    "parse_amount_paise",
    "resolve_language",
]
