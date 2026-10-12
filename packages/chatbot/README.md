# npa_chat — Pre-NPA Rescue Hardship Chatbot

**Owner:** WS4 (Chatbot / Conversation Logic)

Multilingual (English, Tamil, Hindi) hardship chatbot library designed for empathetic, respectful, and policy-compliant resolution of distressed credit card accounts before NPA classification (90 days).

## Architecture & Principles
- **Rules decide, LLM phrases:** All financial figures, relief options, waivers, and tenures come strictly from `PolicyProvider` and board-approved policies. The LLM never invents numbers.
- **State machine driven:** Conversation flow is strictly governed by `ConversationState` transitions.
- **Privacy & Compliance:** Adheres to DPDP Act 2023, RBI Responsible Business Conduct Directions 2026 (Para 454P recording notice, Para 454Y contact windows, Para 454Z harsh practices prohibition, Para 454AA grievance redressal).

## Components (Tasks 4.1 - 4.6)
- `engine.py`: `ChatEngine` dialogue engine orchestrating turns and `build_engine` factory.
- `guardrails.py`: Input guardrails (prompt injection defense across en/ta/hi, PII/cross-account protection, system prompt leak defense, out-of-policy demand handling) and output guardrails (strict number verification against verified context/offers and respectful tone check per RBI para 454Z).
- `flows/hardship.py`: Hardship disclosure classifier (`job_loss`, `medical`, `family_bereavement`, `business_loss`, `prefer_not_to_say`), empathetic acknowledgment, and bereavement/medical outreach pause per RBI para 454Y(6).
- `flows/affordability.py`: Household budget assessment, `estimate_affordability` surplus calculation, and capacity confirmation in INR.
- `flows/offer.py`: Relief option presentation (at most 3 cards), dynamic regulatory disclosures (`disc.*`), plan acceptance/rejection, why-contacted explanations via `RiskScore.reasons`, and RBI para 454AA grievance officer contact footer.
- `flows/zero_capacity.py`: Zero repayment capacity path, stopping payment asks, credit card insurance referral (`job_loss`), and hardship officer callback booking (`CallbackScheduler`) with single-story summary.
- `flows/complaint.py`: Formal complaint capture (IS/ISO 10002:2018), category classification (`harassment`, `wrong_charges`, `privacy`, `service`, `other`), priority harassment escalation, 30-day SLA enforcement, and RBI Ombudsman escalation guidance (cms.rbi.org.in / 14448).
- `distress.py`: Multilingual severe emotional distress detection and compassionate support routing with Tele-MANAS helpline (14416).
- `nlu.py`: `NLU` intent and slot parser with multilingual amount extraction to paise (en/ta/hi).
- `language.py`: Script-based language detection and dynamic switching across en/ta/hi.
- `llm_client.py`: `AnthropicLLMClient` (lazy SDK loading) and `MockLLMClient` implementing `LLMClient` protocol.
- `state.py`: `ConversationState` model and `InMemorySessionStore` implementing `SessionStore`.
- `i18n/`: String bundles for `en`, `ta`, and `hi` with parameter interpolation and fallback.
- `tests/fakes.py`: Provider test doubles loaded from `contracts/fixtures/`.
- `tests/conversations/`: Scripted YAML multi-turn conversation scenarios (Priya Tamil full flow, Ravi English zero-capacity, Hindi business flow, Complaint interrupt, Bereavement outreach pause, Severe distress intervention, and Prompt injection attack).

## Running Checks
```bash
uv run ruff check packages/chatbot
uv run ruff format --check packages/chatbot
uv run python -m mypy packages/chatbot
uv run pytest packages/chatbot
```
