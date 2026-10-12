"""Pre-NPA Rescue Chatbot package (WS4)."""

from npa_chat.distress import detect_distress, handle_distress
from npa_chat.engine import ChatEngine, build_engine
from npa_chat.flows import (
    classify_complaint_category,
    classify_hardship,
    estimate_affordability,
    handle_affordability_turn,
    handle_complaint_turn,
    handle_hardship_turn,
    handle_offer_turn,
    handle_zero_capacity_turn,
    present_relief_options,
    present_zero_capacity_options,
)
from npa_chat.guardrails import (
    InputGuardrailResult,
    OutputGuardrailResult,
    check_input_guardrails,
    verify_output_guardrails,
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
    "InputGuardrailResult",
    "Intent",
    "MockLLMClient",
    "NLUResult",
    "OutputGuardrailResult",
    "SessionStore",
    "__version__",
    "build_engine",
    "check_input_guardrails",
    "classify_complaint_category",
    "classify_hardship",
    "detect_distress",
    "detect_language_switch_request",
    "detect_script",
    "estimate_affordability",
    "get_bundle",
    "get_llm_client",
    "get_string",
    "handle_affordability_turn",
    "handle_complaint_turn",
    "handle_distress",
    "handle_hardship_turn",
    "handle_offer_turn",
    "handle_zero_capacity_turn",
    "parse_amount_paise",
    "present_relief_options",
    "present_zero_capacity_options",
    "resolve_language",
    "verify_output_guardrails",
]
