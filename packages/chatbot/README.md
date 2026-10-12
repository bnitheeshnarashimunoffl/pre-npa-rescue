# npa_chat — Pre-NPA Rescue Hardship Chatbot

**Owner:** WS4 (Chatbot / Conversation Logic)

Multilingual (English, Tamil, Hindi) hardship chatbot library designed for empathetic, respectful, and policy-compliant resolution of distressed credit card accounts before NPA classification (90 days).

## Architecture & Principles
- **Rules decide, LLM phrases:** All financial figures, relief options, waivers, and tenures come strictly from `PolicyProvider` and board-approved policies. The LLM never invents numbers.
- **State machine driven:** Conversation flow is strictly governed by `ConversationState` transitions.
- **Privacy & Compliance:** Adheres to DPDP Act 2023, RBI Responsible Business Conduct Directions 2026 (Para 454P recording notice, Para 454Y contact windows, Para 454Z harsh practices prohibition, Para 454AA grievance redressal).

## Components (Task 4.1 Skeleton)
- `llm_client.py`: `AnthropicLLMClient` (lazy SDK loading) and `MockLLMClient` implementing `LLMClient` protocol.
- `state.py`: `ConversationState` model and `InMemorySessionStore` implementing `SessionStore`.
- `i18n/`: String bundles for `en`, `ta`, and `hi` with parameter interpolation and fallback.
- `tests/fakes.py`: Provider test doubles loaded from `contracts/fixtures/`.

## Running Checks
```bash
uv run ruff check packages/chatbot
uv run ruff format --check packages/chatbot
uv run python -m mypy packages/chatbot
uv run pytest packages/chatbot
```
