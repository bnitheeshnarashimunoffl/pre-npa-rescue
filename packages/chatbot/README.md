# npa_chat — Pre-NPA Rescue Hardship Chatbot

**Owner:** Workstream 4 (WS4: Chatbot / Conversation Logic)  
**Package:** `packages/chatbot` (`npa_chat`)

The `npa_chat` library implements an empathetic, respectful, and strictly compliant multilingual dialogue engine for credit card borrowers facing financial distress before accounts reach Non-Performing Asset (NPA) classification (90 days past due).

---

## 1. Core Principles & Architecture

- **Rules Decide, LLM Phrases:** All financial amounts, permitted relief options, fee waivers, tenure limits, and eligibility criteria are determined deterministically by `PolicyProvider`. The conversational layer never generates, assumes, or hallucinates financial relief figures.
- **Strict State Machine:** Conversation turns transition predictably through `ChatState` (Consent Notice -> Hardship Disclosure -> Affordability Assessment -> Relief Options / Zero Capacity -> Acceptance / Handoff / Closing).
- **Multilingual Support (EN, TA, HI):** Full native-language support across English, Tamil (`தமிழ்`), and Hindi (`हिन्दी`), including script detection, dynamic mid-dialogue switching, and cultural honorific preservation.
- **Privacy & Safety-First:** Built-in defenses against adversarial prompt injection, cross-account PII leakage, and unauthorized write-off demands. Output numbers are cross-verified against context and offers before transmission.

```
       [Customer Inbound]
               │
               ▼
       ┌────────────────┐
       │ CONSENT_NOTICE │ ◄── Turn 1 (RBI Para 454P & DPDP Notice)
       └───────┬────────┘
               ▼
    ┌──────────────────────┐
    │ HARDSHIP_DISCLOSURE  │ ◄── Voluntary disclosure (Job loss, Medical, Business loss)
    └──────────┬───────────┘     (Bereavement triggers Para 454Y(6) pause offer)
               │
       ┌───────┴───────────────┐
       ▼                       ▼
┌──────────────┐     ┌───────────────────┐
│ AFFORDABILITY│     │   ZERO_CAPACITY   │ ◄── Ravi path: Stop payment asks,
└──────┬───────┘     └─────────┬─────────┘     insurance referral & callback booking
       │                       │
       ▼                       ▼
 ┌───────────┐           ┌───────────┐
 │  OPTIONS  │           │  HANDOFF  │ ◄── Hardship Officer callback scheduled
 └─────┬─────┘           └───────────┘
       │
       ▼
 ┌───────────┐
 │ ACCEPTED  │ ◄── Plan confirmed + Grievance Officer details (Para 454AA)
 └───────────┘
```

---

## 2. Regulatory Compliance Matrix

| Regulatory Standard / Section | Chatbot Implementation Details | Verified By |
| :--- | :--- | :--- |
| **RBI RBC Directions 2026 Para 454P** | Mandatory recording disclosure and DPDP Act purpose limitation delivered on first turn; all contact events logged with 180-day retention metadata. | `test_first_turn_greeting_and_regulatory_notices` |
| **RBI RBC Directions 2026 Para 454Y** | Contact window checks (08:00 - 19:00 IST); statutory outreach pause offered on bereavement under Para 454Y(6). | `test_hardship_flow_bereavement_pause_enacted`, `bereavement_pause_flow.yaml` |
| **RBI RBC Directions 2026 Para 454Z** | Absolute prohibition of harsh recovery tactics, threats, or harassment; immediate cessation of payment demands upon zero repayment capacity; tone verification via `ComplianceProvider`. | `test_zero_capacity_flow_ravi`, `test_verify_output_guardrails_harsh_tone_blocked` |
| **RBI RBC Directions 2026 Para 454AA** | Mandatory Grievance Officer contact details attached to confirmed plans, complaints, and callbacks; 30-day statutory resolution SLA; direct escalation to RBI Integrated Ombudsman (`https://cms.rbi.org.in` / 14448). | `test_complaint_turn_registration`, `test_engine_priya_hardship_and_affordability_flow` |
| **RBI Credit Card Directions 2025** | Honest interest disclosures: reducing-balance calculation, non-capitalization of unpaid penal charges (`disc.emi_conversion.interest_breakdown`). | `test_render_disclosure_multilingual`, `test_offer_presentation_truthful_disclosures` |
| **RBI Prudential Framework 2019** | Mandatory disclosure warning that standard restructured accounts are downgraded to NPA and reported to credit bureaus (`disc.restructuring.npa_downgrade`). | `test_render_disclosure_multilingual` |
| **RBI Compromise Framework 2023** | Mandatory disclosure warning of 12-month minimum cooling period before fresh credit can be granted (`disc.settlement.cooling_period`). | `test_render_disclosure_multilingual` |
| **Tele-MANAS Mental Health Support** | Immediate routing to National Tele-MANAS helpline `14416` (24/7 toll-free) upon detection of severe emotional distress or suicidal ideation. | `test_distress_detection_multilingual`, `severe_distress_flow.yaml` |
| **IS/ISO 10002:2018 (Complaint Handling)** | Formal complaint registration, category classification, unique docket tracking, priority harassment escalation, and objective dispute investigation. | `test_complaint_turn_registration`, `complaint_interrupt_flow.yaml` |
| **IS 17802 (Conversational AI Systems)** | Safe, reliable, and transparent dialogue system architecture with verified guardrails and fallback routing. | `test_guardrails.py`, `test_conversations.py` |

---

## 3. Package Structure & Module Inventory

```
packages/chatbot/
├── docs/
│   └── i18n_review_notes.md       # Linguistic and honorific review notes for Tamil & Hindi
├── src/npa_chat/
│   ├── engine.py                  # Core ChatEngine and build_engine factory
│   ├── guardrails.py              # Input & Output safety guardrails
│   ├── distress.py                # Severe distress detection & Tele-MANAS routing
│   ├── language.py                # Language resolution and dynamic switching
│   ├── nlu.py                     # Intent classification, slot parsing, paise amount parsing
│   ├── state.py                   # ConversationState and SessionStore
│   ├── llm_client.py              # MockLLMClient and AnthropicLLMClient
│   ├── flows/
│   │   ├── hardship.py            # Hardship categorization & bereavement pause
│   │   ├── affordability.py       # Household budget assessment & capacity calculation
│   │   ├── offer.py               # Truthful offer presentation & acceptance
│   │   ├── zero_capacity.py       # Stop-ask, insurance referral & callback scheduler
│   │   └── complaint.py           # ISO 10002 complaint capture & Ombudsman escalation
│   └── i18n/
│       ├── en.json                # Master English string bundle
│       ├── ta.json                # Tamil localized string bundle
│       └── hi.json                # Hindi localized string bundle
└── tests/
    ├── fakes.py                   # Provider test doubles loaded from contracts/fixtures
    ├── test_engine.py             # Full dialogue orchestration tests
    ├── test_flows.py              # Specialized flow & disclosure tests
    ├── test_guardrails.py         # Prompt injection & output safety tests
    ├── test_conversations.py      # Scripted YAML scenario execution runner
    └── conversations/             # Golden multi-turn scenario YAMLs
        ├── priya_tamil_full_flow.yaml
        ├── ravi_english_zero_capacity.yaml
        ├── hindi_hardship_offer_flow.yaml
        ├── complaint_interrupt_flow.yaml
        ├── bereavement_pause_flow.yaml
        ├── severe_distress_flow.yaml
        └── prompt_injection_guardrail_flow.yaml
```

---

## 4. Verification and Testing Guide

All four quality and compliance checks must pass without warnings or errors.

```bash
# 1. Linter check
uv run ruff check packages/chatbot

# 2. Formatter check
uv run ruff format --check packages/chatbot

# 3. Type consistency check
uv run python -m mypy packages/chatbot

# 4. Comprehensive test suite
uv run pytest packages/chatbot
```

### Running Specific Test Suites
- **Scripted Conversation Suite:**
  ```bash
  uv run pytest packages/chatbot/tests/test_conversations.py -v
  ```
- **Safety & Guardrails Suite:**
  ```bash
  uv run pytest packages/chatbot/tests/test_guardrails.py -v
  ```
- **End-to-End Dialogue Flows:**
  ```bash
  uv run pytest packages/chatbot/tests/test_engine.py -v
  ```

---

## 5. Supervisor Verification Notes
1. **Priya Demo Path (Tamil):** Verified end-to-end via `priya_tamil_full_flow.yaml` and `test_engine_priya_hardship_and_affordability_flow`. Offers fee waiver and 6 x ₹2,000 EMI conversion in Tamil.
2. **Ravi Demo Path (English):** Verified end-to-end via `ravi_english_zero_capacity.yaml` and `test_zero_capacity_flow_ravi`. Zero repayment capacity triggers immediate stop-ask, insurance claim referral, and 11:00 AM hardship officer callback booking.
3. **Regulatory Auditing:** All contact events emit structured `ContactEvent` instances containing channel, actor, timestamp, language, and compliance rule citations (`RBI-454Y4-WINDOW`, `RBI-454Z-TONE`).
