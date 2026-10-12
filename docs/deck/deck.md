# Pre-NPA Rescue — deck content

This is the source of truth for slide production. Each slide keeps visible text to 30 words or
fewer; labels inside a diagram count toward that limit. Speaker notes may be longer.

Result-dependent claims remain `TBD – from <path>` until the named evidence is committed and
verified. Fixture values may guide layout but must not be presented as measured results.

## Slide 1 — Rescue before day 90

**Title:** Pre-NPA Rescue

**On-slide text (9 words):** Rescue before day 90. Responsible help, within bank rules.

**Visual:** A clean 0-to-90-day timeline. Place the product name before the NPA boundary, with
a customer and a bank icon on the same side.

**Speaker notes:** “We find customers who are about to struggle, work out who we can actually
help, offer them a kind and affordable plan within the bank’s rules, and prove the whole thing
is fair.” Do not introduce performance numbers here.

**Evidence:** `README.md`; `contracts/data/account_months.md`.

## Slide 2 — The day-90 cliff

**Title:** One missed-payment journey. Too often, one collections script.

**On-slide text (18 words):** Current → SMA-0 → SMA-1 → SMA-2 → NPA. Intervene before minimum
dues remain unpaid for 90 days.

**Visual:** A left-to-right delinquency path. Under it, contrast “same script” with three human
needs: forgot, cannot pay, will not pay.

**Speaker notes:** Explain that the prototype follows the credit-card NPA rule measured from
the statement due date. Avoid claiming a market size or bank loss without committed evidence.

**Evidence:** `contracts/data/account_months.md`;
`packages/contracts/src/npa_contracts/constants.py`.

## Slide 3 — Theme alignment

**Title:** Built for the hackathon theme

**On-slide text (15 words):** “<PASTE THE EXACT THEME HERE>” Responsible credit. Financial
inclusion. Consumer protection. Regulatory technology.

**Visual:** Put the exact quoted theme in the centre. Connect it to four equal cards: responsible
credit, inclusion, protection and regtech.

**Speaker notes:** The quoted text must remain exactly as supplied until the team lead provides
the real theme wording. Then update this slide and the claim ledger in the same PR. Connect the
project to the theme through actions: intervene early, tailor support, constrain AI with policy,
and produce auditable evidence.

**Evidence:** Exact theme wording is deliberately unresolved in the setup note. Project fit:
`README.md` and `docs/architecture.md`.

## Slide 4 — Detect, Decide, Resolve, Prove

**Title:** Four layers, one accountable intervention

**On-slide text (13 words):** Detect emerging stress. Decide who benefits. Resolve within
policy. Prove fairness and compliance.

**Visual:** Reuse the four-layer overview from `docs/architecture.md`. Show Prove testing both
Decide and Resolve rather than appearing as a final decorative step.

**Speaker notes:** Detect is ML inference. Decide combines uplift with deterministic policy and
compliance. Resolve provides multilingual support and human oversight. Prove attacks decisions
and conversations. The AI system supports decisions; the bank’s rules control what can be
offered.

**Evidence:** `docs/architecture.md`; `contracts/fixtures/nba.json`;
`contracts/fixtures/scorecard.json`.

## Slide 5 — Detect before default

**Title:** Risk that collectors can understand

**On-slide text (12 words):** Early warning + plain-language reasons + customer segment.
Model quality: TBD – from packages/models/reports/metrics.json.

**Visual:** A Priya risk card with three reason-code slots. Use no probability, accuracy or
fairness value until the committed model report exists.

**Speaker notes:** The model predicts roll-forward risk at a 30–60-day horizon and returns
reasons, a risk band and version. Segmentation distinguishes `forgot`, `cant_pay`, `wont_pay`
and `not_at_risk`. Say clearly whether the demo is using fixtures or a trained provider.

**Evidence:** `contracts/schemas/RiskScore.schema.json`;
`contracts/schemas/SegmentResult.schema.json`; pending `packages/models/reports/metrics.json`.

## Slide 6 — Decide who not to call

**Title:** Risk finds need. Uplift finds useful action.

**On-slide text (16 words):** Persuadable. Sure thing. Lost cause. Sleeping dog. The AI
proposes; bank policy and compliance rules decide.

**Visual:** A four-quadrant uplift grid feeding a policy gate. Send the sleeping-dog quadrant to
“no contact” and permitted actions through human oversight.

**Speaker notes:** A risk score estimates what may happen; uplift estimates whether treatment
changes the outcome. This prevents wasting contact on customers who pay anyway and reduces
potentially harmful contact. Monetary terms never originate in the LLM.

**Evidence:** `contracts/schemas/UpliftResult.schema.json`;
`contracts/schemas/NextBestAction.schema.json`; `packages/rules/README.md`.

## Slide 7 — Resolve without pressure

**Title:** Help that adapts to capacity

**On-slide text (17 words):** Priya: policy-approved Tamil plan. Ravi: no payment pressure,
insurance check, compliant human callback. English, Tamil and Hindi.

**Visual:** Two phone frames. Priya’s frame shows an approved offer and disclosures. Ravi’s
frame shows the zero-capacity handoff and callback confirmation.

**Speaker notes:** Priya’s exact amount and waiver are fixture-backed today; disclose that if
the real policy provider has not merged. Ravi’s path stops payment prompts after zero capacity,
then offers a policy-defined insurance referral and hardship-officer handoff.

**Evidence:** `contracts/fixtures/bot_reply_offer.json`;
`contracts/fixtures/bot_reply_zero_capacity.json`; `contracts/schemas/BotReply.schema.json`.

## Slide 8 — Prove it under attack

**Title:** Compliance is tested, not asserted

**On-slide text (16 words):** Bias swaps. Pressure. Injection. Privacy. Contact rules.
Pass rate: TBD – from `redteam/reports/<latest>/scorecard.json`.

**Visual:** Six attack tiles leading to an RBI/BIS coverage grid. Reserve clear red and green
states for the real run, including failures and fixes.

**Speaker notes:** The six fixture categories are pressure, bias swap, prompt injection,
privacy extraction, contact rules and misleading consequences. Do not quote the fixture’s pass
rate as a real test result. When evidence lands, report failures and remediation honestly.

**Evidence:** `redteam/README.md`; `contracts/schemas/Scorecard.schema.json`; pending
`redteam/reports/<latest>/scorecard.json`.

## Slide 9 — RBI controls become product controls

**Title:** RBI requirements, enforced in the flow

**On-slide text (16 words):** Day-90 classification. Contact window. No harsh practices.
Recorded engagement. Distress support. Disclosures. Grievance route. Data minimisation.

**Visual:** An eight-row requirement-to-control grid. Use a “designed for 1 January 2027” badge
beside paragraph 454 items.

**Speaker notes:** Explain enforcement rather than reciting regulation. Contact checks precede
outbound contact; text checks block harsh or misleading language; audit records preserve the
event; policy supplies disclosures; complaints carry grievance details. Paragraph 454 is a
future-effective design target, not a current-in-force claim.

**Evidence:** Copy-ready content in `docs/deck/rbi_slide.md`; pending
`governance/rbi_mapping.md`.

## Slide 10 — BIS standards shape the design

**Title:** Indian Standards mapped to concrete evidence

**On-slide text (16 words):** Govern AI. Prove fairness and quality. Protect data. Treat
customers well. Include everyone. Design alignment—not certification.

**Visual:** Five columns with standard identifiers and one implementation evidence line per
area. Keep the non-certification footnote visible.

**Speaker notes:** Cover AI governance, AI risk, human oversight, bias, ML quality and
vocabulary, data life cycle, security, complaints, contact centres and ICT accessibility. The
brief calls for 14 standards; verify grouping and edition identifiers against the committed
WS7 mapping before final export.

**Evidence:** Copy-ready content in `docs/deck/bis_slide.md`; pending
`governance/bis_mapping.md`.

## Slide 11 — Business impact

**Title:** Compare with “call everyone”

**On-slide text (14 words):** NPA rate: TBD. Cure rate: TBD. Collection cost: TBD. Source:
contracts/fixtures/simulation_metrics.json until replaced.

**Visual:** Three paired bars: NPA rate, cure rate and collection cost. Add an “illustrative”
watermark while fixture data is shown.

**Speaker notes:** The current fixture is explicitly a placeholder. Before the final deck, use
the real committed simulation output and state population, horizon, strategy definitions and
whether uncertainty was measured. Never convert fixture results into a performance claim.

**Evidence:** `contracts/fixtures/simulation_metrics.json`; final source pending
`packages/models/reports/policy_simulation.json` or the committed replacement named by WS2.

## Slide 12 — Architecture and controls

**Title:** Modular by contract; controlled at every boundary

**On-slide text (17 words):** Web → API → models, rules, chat and data. Red team attacks the
API. Humans approve relief.

**Visual:** Reuse the component diagram from `docs/architecture.md`, simplified to fit one
slide. Highlight policy, compliance and audit control points.

**Speaker notes:** Shared Pydantic and JSON/OpenAPI contracts isolate workstreams. The LLM is a
replaceable language component. Policy and compliance remain deterministic provider
boundaries. Postgres holds operational and audit state in the target architecture.

**Evidence:** `docs/architecture.md`; `contracts/README.md`; `services/api/README.md`.

## Slide 13 — Synthetic by design

**Title:** Useful evidence without real customer data

**On-slide text (17 words):** Synthetic India-specific histories. Protected attributes only
for fairness evaluation. Calibration source and licence: TBD – from data/ATTRIBUTION.md.

**Visual:** Data lineage from public calibration source to synthetic tables, features, models
and scores. Put protected attributes on a separate evaluation-only branch.

**Speaker notes:** Do not state the UCI dataset name or CC BY 4.0 licence as verified until
`data/ATTRIBUTION.md` is committed. The contract already verifies separation of protected
attributes from model features. No real personal data belongs in the repository.

**Evidence:** `contracts/data/protected_attributes.md`; `contracts/data/features.md`; pending
`data/ATTRIBUTION.md`.

## Slide 14 — Honest limits, practical next steps

**Title:** What this prototype does not prove yet

**On-slide text (20 words):** Synthetic evidence. Human translation review pending. Paragraph
454 effective 1 January 2027. Next: governed bank pilot, monitoring and independent validation.

**Visual:** Two columns: limits now and gates before pilot. Include legal/compliance review,
model validation, translation review, security testing and controlled rollout.

**Speaker notes:** This is not a certified banking system, legal opinion, credit-score model or
autonomous restructuring engine. A pilot would require bank-owned policy, governance,
monitoring, human training, customer testing and production security controls.

**Evidence:** `README.md`; pending `governance/risk_register.md`,
`governance/ai_register.md` and `governance/data_lifecycle.md`.

## Slide 15 — Close

**Title:** Rescue before day 90

**On-slide text (22 words):** Find struggle early. Help only where help changes outcomes. Stay
inside bank rules. Treat customers with dignity. Prove the system is fair.

**Visual:** Return to the opening timeline, now showing Detect, Decide, Resolve and Prove before
day 90. End on the project name.

**Speaker notes:** Repeat the one-sentence pitch exactly. Invite questions on uplift, policy
control, zero-capacity support, RBI enforcement and BIS evidence.

**Evidence:** `README.md`; `docs/architecture.md`.

## Claim ledger

Before `demo-freeze`, every row must be `verified` or `dropped`. “Verified” means the cited
path is committed and supports the exact claim; a schema or fixture does not prove a real
implementation result.

| Claim | Evidence path | Status |
|---|---|---|
| Credit-card NPA classification follows minimum due unpaid for 90 days from statement due date | `contracts/data/account_months.md`; `packages/contracts/src/npa_contracts/constants.py` | verified |
| The system has four layers: Detect, Decide, Resolve and Prove | `docs/architecture.md` | verified |
| AI proposes while bank policy and compliance decide | `packages/rules/README.md`; `contracts/schemas/ReliefOption.schema.json` | verified as architecture; implementation pending |
| Exact hackathon theme is quoted | Team lead input | pending |
| Early-warning model quality and fairness metrics | `packages/models/reports/metrics.json` | pending |
| Uplift supports persuadable, sure-thing, lost-cause and sleeping-dog groups | `contracts/schemas/UpliftResult.schema.json` | verified as contract |
| Priya receives a Tamil, human-approved policy offer | `contracts/fixtures/bot_reply_offer.json` | verified as fixture only |
| Ravi receives a zero-capacity insurance and callback path | `contracts/fixtures/bot_reply_zero_capacity.json` | verified as fixture only |
| Live chatbot supports English, Tamil and Hindi | WS4 tests and integrated demo evidence | pending |
| Red-team pass rate and fixes | `redteam/reports/<latest>/scorecard.json` | pending |
| Paragraph 454 controls are designed for the 1 January 2027 effective date | `governance/rbi_mapping.md` | pending |
| RBI controls map to implemented enforcement points | `governance/rbi_mapping.md` plus WS3/WS5 tests | pending |
| Relevant BIS standards map to concrete project evidence | `governance/bis_mapping.md` | pending |
| BIS relationship is design alignment, not certification | `docs/deck/bis_slide.md` | verified as positioning |
| NPA rate, cure rate and collection cost improve over call-everyone | `packages/models/reports/policy_simulation.json` | pending |
| Data calibration source and licence | `data/ATTRIBUTION.md` | pending |
| Protected attributes are isolated from model features | `contracts/data/protected_attributes.md`; `contracts/data/features.md` | verified as contract; implementation pending |
| Frontend screenshots represent the integrated demo | `apps/web/screenshots/` | pending |

## Final evidence replacement checklist

- Replace every `TBD – from <path>` only after opening and checking the committed file.
- Confirm the exact theme quote with the team lead.
- Replace fixture screenshots and values with integrated evidence.
- State failures and limitations alongside successful red-team results.
- Recount visible words after slide design labels are added.
- Remove or drop every claim whose evidence is still missing at `demo-freeze`.
