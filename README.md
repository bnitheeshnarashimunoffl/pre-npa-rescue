# Pre-NPA Rescue

> **Rescue before day 90.**

We find customers who are about to struggle, work out who we can actually help, offer them a
kind and affordable plan within the bank's rules, and prove the whole thing is fair.

Pre-NPA Rescue is a fintech hackathon prototype for responsible credit-card hardship support
in India. It combines early warning, treatment-effect modelling, bank-policy rules,
multilingual conversations and adversarial compliance testing before an account reaches NPA.

## The problem

Collections often begins after a payment is missed and treats very different situations with
the same script. A customer who forgot, a customer who cannot pay and a customer who will not
pay need different responses. Delayed or unsuitable intervention can increase distress,
collection cost and the risk of an account becoming a non-performing asset.

For credit cards, the project models the RBI rule that an account becomes NPA when the minimum
amount due remains unpaid for 90 days from the statement due date. The system acts before that
day-90 cliff and keeps relief decisions inside a simulated board-approved bank policy.

## How it works

| Layer | Purpose | What the prototype does |
|---|---|---|
| **Detect** | Find emerging difficulty early | Scores the chance of rolling into the next delinquency bucket, gives plain-language reasons and separates `forgot`, `cant_pay` and `wont_pay`. |
| **Decide** | Focus effort where it can change the outcome | Uses uplift groups to identify who may benefit from contact, including who should not be contacted, then selects only policy-permitted actions. |
| **Resolve** | Offer a humane route forward | Supports English, Tamil and Hindi hardship conversations, affordability checks, human-approved offers and a zero-capacity handoff. |
| **Prove** | Test fairness and compliance | Red-teams pressure, bias swaps, prompt injection, privacy extraction, contact rules and misleading consequences. |

The core control is simple: **the AI proposes; the rules decide.** Customer-facing amounts and
relief terms come from the policy engine, not from an LLM.

## Demo story

- **Priya** has lost her salary credits and paid only the minimum for three months. The fixture
  path classifies her as high risk, `cant_pay` and `persuadable`, then presents a
  human-approved Tamil offer from bank policy.
- **Ravi** cannot afford any payment. The conversation stops asking for money, checks his card
  insurance route and hands him to a hardship officer within the permitted contact window.
- The compliance scorecard then replays adversarial cases, and the simulation compares the
  strategy with a call-everyone baseline.

Demo values currently come from versioned [contract fixtures](contracts/fixtures/) and remain
illustrative until the producing workstreams replace them with committed model and red-team
results.

## Screenshots

Collector dashboard, customer chat and compliance scorecard screenshots will be added from
`apps/web/screenshots/` when WS6 commits the demo views. This placeholder avoids presenting
design mock-ups as working product evidence.

## Quick start

See the cross-platform [setup guide](docs/setup.md) for prerequisites and plain-command
alternatives. With Docker and Make installed:

```bash
make demo
```

The current bootstrap starts the available containers and reports components that are still
pending. The API documentation is served at `http://localhost:8000/docs`; the web application
uses `http://localhost:3000` once the frontend container is present.

Useful development commands:

```bash
make setup
make test
make lint
make check-contracts
```

## Architecture

```text
Synthetic data -> ML models -> risk, segment and uplift
                                  |
                                  v
Web app -> API -> policy engine -> conversation and human oversight
             |          |                     |
             v          v                     v
          Postgres   compliance guard      audit/contact log
             ^                                |
             +--------- red-team harness -----+
```

The API depends on provider contracts rather than package internals. Shared JSON, API and
Parquet interfaces live in [`contracts/`](contracts/README.md). Detailed Mermaid diagrams are
planned in `docs/architecture.md` as the next task 8.3 deliverable.

## Repository map

| Path | Responsibility |
|---|---|
| [`packages/datagen/`](packages/datagen/) and [`data/`](data/) | Synthetic customer histories, features, labels and experiment data |
| [`packages/models/`](packages/models/) | Early warning, explanations, segmentation and uplift modelling |
| [`packages/rules/`](packages/rules/) | Bank policy, affordability, compliance checks and next-best action |
| [`packages/chatbot/`](packages/chatbot/) | Multilingual conversation state and hardship flows |
| [`services/api/`](services/api/) | FastAPI integration, persistence, authentication and audit logging |
| [`apps/web/`](apps/web/) | Customer, collector, compliance and policy interfaces |
| [`redteam/`](redteam/) and [`governance/`](governance/) | Adversarial tests, scorecards and governance evidence |
| [`docs/`](docs/) | Setup, architecture, demo script, pitch content and judges' FAQ |

## Workstreams

| Workstream | Scope | Tasks |
|---|---|---|
| WS1 | Data foundation | Synthetic data, features and experiment simulation |
| WS2 | Models | Early warning, explanations, segmentation, uplift and evaluation |
| WS3 | Decision and rules | Policy engine, affordability, compliance guard and next-best action |
| WS4 | Chatbot | Multilingual dialogue, hardship, offers, handoff, complaints and guardrails |
| WS5 | Platform | Contracts, API, database, auth, audit and deployment |
| WS6 | Frontend | Customer, collector, compliance and policy experiences |
| WS7 | Red team and compliance | Attack harness, scorecard and governance documents |
| WS8 | Pitch | Demo script, deck, README, architecture and judges' FAQ |

## RBI and BIS alignment

The prototype is designed around relevant RBI requirements, including the day-90 credit-card
NPA rule, permitted contact hours, restrictions on harsh practices, contact records,
grievance handling and policy-controlled restructuring or settlement disclosures. The RBI
Responsible Business Conduct paragraph 454 requirements are treated as a design target that
takes effect on **1 January 2027**, not as a claim that they are already in force.

It also maps its controls and evidence to relevant Indian Standards for AI governance, risk,
fairness, quality, data life cycle, information security, complaints, contact centres and ICT
accessibility. This is **design alignment, not a certification claim**.

- Current governance area: [`governance/`](governance/README.md)
- Current adversarial testing area: [`redteam/`](redteam/README.md)
- Fixture scorecard: [`contracts/fixtures/scorecard.json`](contracts/fixtures/scorecard.json)
- RBI mapping: `governance/rbi_mapping.md` — pending WS7 task 7.3
- BIS mapping: `governance/bis_mapping.md` — pending WS7 task 7.3

## Data and privacy

The repository uses synthetic data only. Protected attributes are stored separately and are
reserved for fairness evaluation; they are not model features. Raw public data and generated
customer-level data are not committed.

Dataset licence and source details will be linked from `data/ATTRIBUTION.md` when WS1 commits
that task-owned file. Until then, see the [data area](data/README.md) and the table contracts in
[`contracts/data/`](contracts/data/).

## Team

Pre-NPA Rescue is built across eight workstreams. Repository ownership and review routes are
recorded in [CODEOWNERS](.github/CODEOWNERS); contributor history is available through the
repository's commits and pull requests.

## Licence

Released under the [MIT License](LICENSE).

## Disclaimer

This is a hackathon prototype using synthetic data. It is not legal or financial advice, is
not a bank offer, and is not certified against RBI requirements or Indian Standards.
