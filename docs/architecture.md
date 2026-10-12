# Architecture

Pre-NPA Rescue is an AI system for intervention before credit-card accounts reach the day-90
NPA threshold. It separates ML inference from policy decisions: ML models estimate risk and
treatment effect, while deterministic bank-policy and compliance components decide which
actions are allowed. Human oversight is required for relief offers.

This document uses the lifecycle vocabulary of IS/ISO/IEC 22989:2022 and the ML framework
vocabulary of IS/ISO/IEC 23053:2022. The references indicate design alignment, not
certification.

## Four-layer overview

```mermaid
flowchart LR
    CustomerData["Synthetic customer history"] --> Detect

    subgraph AISystem["Pre-NPA Rescue AI system"]
        Detect["Detect<br/>ML inference: risk, reasons, segment"]
        Decide["Decide<br/>uplift, bank policy, compliance"]
        Resolve["Resolve<br/>multilingual support and human oversight"]
        Prove["Prove<br/>adversarial tests and scorecard"]

        Detect --> Decide --> Resolve
        Prove -. "tests decisions" .-> Decide
        Prove -. "tests conversations" .-> Resolve
    end

    Decide --> NoContact["No contact when intervention will not help"]
    Resolve --> Outcome["Policy-permitted plan or hardship handoff"]
```

Detect produces decision support, not an offer. Decide combines ML inference with the
simulated board-approved policy. Resolve presents only a permitted option and preserves human
oversight. Prove tests decision and conversation behaviour against RBI controls and relevant
Indian Standards.

Evidence: [`contracts/fixtures/nba.json`](../contracts/fixtures/nba.json),
[`contracts/fixtures/offer.json`](../contracts/fixtures/offer.json), and
[`contracts/fixtures/scorecard.json`](../contracts/fixtures/scorecard.json).

## Component architecture

```mermaid
flowchart TB
    Web["Web application<br/>customer and staff channels"]
    API["FastAPI /api/v1<br/>authentication and orchestration"]
    Models["npa_models<br/>ML model training and inference"]
    Rules["npa_rules<br/>policy, affordability, compliance, NBA"]
    Chat["npa_chat<br/>conversation state and NLU"]
    DB[("PostgreSQL 16<br/>operational and audit data")]
    LLM["LLM provider<br/>structured language understanding"]
    DataGen["datagen<br/>offline synthetic training data"]
    Artifacts["Model artifacts and reports"]
    RedTeam["npa_redteam<br/>adversarial API client"]
    Human["Collector or hardship officer<br/>human oversight"]

    Web --> API
    RedTeam --> API
    API --> Models
    API --> Rules
    API --> Chat
    API --> DB
    Chat --> LLM
    Chat --> Rules
    API --> Human
    Human --> API

    DataGen -. "training data and evaluation data" .-> Models
    Models -. "trained ML model" .-> Artifacts
    Artifacts -. "loaded for inference" .-> Models
```

The API wires packages through provider protocols in `npa_contracts`; it does not depend on
their internal implementations. The LLM extracts language intent and slots. It is not the
source of amounts, waivers or promises. Those values come from `npa_rules`, and customer
contact is checked and logged.

Evidence: [`contracts/README.md`](../contracts/README.md),
[`services/api/README.md`](../services/api/README.md),
[`packages/models/README.md`](../packages/models/README.md),
[`packages/rules/README.md`](../packages/rules/README.md), and
[`packages/chatbot/README.md`](../packages/chatbot/README.md).

## Priya: policy-controlled chat turn

```mermaid
sequenceDiagram
    autonumber
    actor Priya
    participant Web as Customer web
    participant API as API
    participant Chat as ChatEngine
    participant NLU as NLU and LLMClient
    participant Policy as PolicyProvider
    participant Human as Hardship officer
    participant Guard as ComplianceProvider
    participant Log as ContactLogger

    Priya->>Web: Explains job loss in Tamil
    Web->>API: POST chat message
    API->>Chat: handle session and customer context
    Chat->>NLU: Extract hardship intent and affordability slots
    NLU-->>Chat: Structured intent only
    Chat->>Policy: Request eligible relief options
    Policy-->>Chat: Policy references, terms and disclosures
    Chat->>Human: Request approval for selected option
    Human-->>Chat: Approve or reject with identity logged
    Chat->>Guard: check_text proposed reply
    Guard-->>Chat: Allow or block with rule identifiers
    Chat->>Log: Record compliant contact event
    Log-->>Chat: Logged
    Chat-->>API: BotReply with approved offer
    API-->>Web: Tamil reply, disclosures and actions
    Web-->>Priya: Display policy-approved plan
```

The committed fixture illustrates an approved offer of ₹2,000 per month for 6 months with
₹1,180 in late fees waived. These are fixture values, not measured results, and must be
rechecked against the integrated rules provider before `demo-freeze`.

Evidence: [`contracts/fixtures/bot_reply_offer.json`](../contracts/fixtures/bot_reply_offer.json)
and [`contracts/schemas/BotReply.schema.json`](../contracts/schemas/BotReply.schema.json).

## Ravi: zero-capacity handoff

```mermaid
sequenceDiagram
    autonumber
    actor Ravi
    participant Web as Customer web
    participant API as API
    participant Chat as ChatEngine
    participant Policy as PolicyProvider
    participant Scheduler as CallbackScheduler
    participant Guard as ComplianceProvider
    participant Officer as Hardship officer
    participant Log as ContactLogger

    Ravi->>Web: States that he cannot pay any amount
    Web->>API: POST chat message
    API->>Chat: handle zero-capacity disclosure
    Chat->>Policy: Request zero-capacity options
    Policy-->>Chat: Insurance referral and review-date path
    Chat->>Scheduler: Request available callback slots
    Scheduler->>Guard: Check slot against contact window and preferences
    Guard-->>Scheduler: Permitted slot or next allowed time
    Scheduler-->>Chat: Compliant slots
    Chat-->>Ravi: Ask Ravi to select a suitable slot
    Ravi->>Chat: Select 11:00 callback
    Chat->>Scheduler: Book hardship-officer callback
    Scheduler-->>Officer: Create handoff with minimised summary
    Chat->>Log: Record conversation and handoff
    Chat-->>API: BotReply with callback confirmation
    API-->>Web: Stop payment prompts and show confirmation
```

The compliance window is evaluated in Asia/Kolkata and is constrained to 08:00–19:00. The
customer's preferred or avoided times must further restrict the available slots. The fixture
books 11:00 IST and flags `zero_capacity` and `handoff_booked`.

Evidence:
[`contracts/fixtures/bot_reply_zero_capacity.json`](../contracts/fixtures/bot_reply_zero_capacity.json),
[`contracts/fixtures/callback.json`](../contracts/fixtures/callback.json), and
[`contracts/schemas/ComplianceDecision.schema.json`](../contracts/schemas/ComplianceDecision.schema.json).

## Data and ML lifecycle

```mermaid
flowchart LR
    UCI["Public UCI credit-card dataset<br/>calibration source"]
    Calibration["Calibration<br/>distribution parameters"]
    Generator["Synthetic data generator<br/>seeded and reproducible"]
    Tables["Synthetic tables<br/>customers, statements, transactions, salary"]
    Protected["Protected attributes<br/>evaluation only"]
    Features["Training data<br/>features and labels"]
    Training["ML model training and evaluation"]
    Reports["Model reports<br/>quality and fairness evidence"]
    Inference["ML inference<br/>risk, segment, uplift"]
    API["API provider boundary"]
    DB[("Operational database")]

    UCI --> Calibration --> Generator --> Tables --> Features --> Training
    Training --> Reports
    Training --> Inference --> API --> DB
    Generator --> Protected
    Protected -. "fairness evaluation only" .-> Reports
    Protected -. "never training features" .-> Features
```

All customer records are synthetic. The public dataset is a calibration input; it is not
served by the application. Protected attributes are separated from training features and are
used only for fairness evaluation and bias-swap tests. Model artifacts are not committed;
reports and small evidence samples are.

Evidence: [`contracts/data/customers.md`](../contracts/data/customers.md),
[`contracts/data/features.md`](../contracts/data/features.md),
[`contracts/data/protected_attributes.md`](../contracts/data/protected_attributes.md), and
[`contracts/data/experiment.md`](../contracts/data/experiment.md). Dataset attribution remains
pending from `data/ATTRIBUTION.md`.

## Trust boundaries and control points

| Boundary | Control | Evidence status |
|---|---|---|
| Training data → ML model | Synthetic lineage, deterministic seed and protected-attribute separation | Contract verified; implementation evidence pending WS1/WS2 |
| ML inference → next action | Uplift group plus deterministic policy and compliance rules | Contract fixtures verified; integrated provider pending |
| LLM → customer reply | Structured NLU only; rules supply monetary terms; output text is checked | Contract/provider design verified; integrated flow pending WS3/WS4 |
| Offer → customer | Human approval and approval identity | Fixture verified; persistence/audit integration pending WS5 |
| Outbound contact → customer | Contact-window and text checks followed by logging | Contract verified; integrated enforcement pending WS3/WS5 |
| AI system → governance | Red-team results mapped to RBI and BIS evidence | Fixture verified; real scorecard and mappings pending WS7 |

## Evidence maturity

The diagrams describe the target MVP architecture defined by committed contracts. A component
shown here is not automatically a claim that its production implementation has merged. Before
`demo-freeze`, replace fixture evidence with:

- `packages/models/reports/metrics.json` and model cards from WS2;
- `redteam/reports/<latest>/scorecard.json` from WS7;
- `governance/rbi_mapping.md` and `governance/bis_mapping.md` from WS7;
- `data/ATTRIBUTION.md` from WS1; and
- integrated API and UI evidence from WS5 and WS6.
