# Judges’ FAQ

Use these answers after the five-minute demo. Lead with the first sentence, then add the
second only if the judge wants detail. Do not substitute fixture values for final results.

## 1. Isn’t this just a risk score plus a chatbot?

No. The differentiator is the decision and proof layer between prediction and conversation.
Risk estimates who may struggle; uplift estimates who benefits from contact; deterministic
policy and compliance providers constrain the action; a red-team scorecard tests the result.

**Evidence:** `docs/architecture.md`; `contracts/schemas/NextBestAction.schema.json`;
`contracts/schemas/Scorecard.schema.json`.

## 2. Why use uplift instead of contacting every high-risk customer?

A risk model estimates what may happen without telling us whether contact will change it.
Uplift separates customers who may respond to help from those who pay anyway, will not respond,
or may react negatively, enabling a deliberate no-contact action.

**Evidence:** `contracts/schemas/UpliftResult.schema.json`;
`contracts/fixtures/queue.json`.

## 3. How do you stop the LLM inventing a waiver or payment plan?

The LLM is a language component, not the authority for money or eligibility. Relief options
carry policy references, mandatory disclosures and human-approval requirements from the rules
provider; proposed reply text also passes through a compliance check.

**Evidence:** `packages/rules/README.md`; `contracts/schemas/ReliefOption.schema.json`;
`contracts/schemas/ComplianceDecision.schema.json`.

## 4. What happens when the LLM is unavailable?

The demo and tests use a deterministic mock provider, and the state machine can present
policy-defined quick replies and handoffs without live generation. In a bank deployment, an
LLM failure should degrade to structured flows or a human, never bypass rules.

**Evidence:** `packages/chatbot/README.md`; `.env.example`; `docs/demo_script.md`.

## 5. Is the customer data real?

No. The prototype uses synthetic customer histories and commits no real personal data.
Calibration source and licence remain `TBD – from data/ATTRIBUTION.md`; we will not assert the
final attribution until that file is committed.

**Evidence:** `data/README.md`; `contracts/data/customers.md`; pending
`data/ATTRIBUTION.md`.

## 6. Why create protected attributes if models must not use them?

They are isolated for evaluation, not prediction. Keeping them in a separate table allows
fairness measurement and bias-swap tests while the feature contract excludes them from model
training and inference.

**Evidence:** `contracts/data/protected_attributes.md`; `contracts/data/features.md`.

## 7. How do you know the system is not biased?

We do not claim bias has been eliminated. Fairness gaps above 0.05 are flagged. Red-team
results report case pass rate as N/144 and strict coverage as X of 15 in-scope RBI
requirements, plus planned and out-of-scope counts. Final values are `TBD – from
redteam/reports/<latest>/scorecard.json` and model fairness results are `TBD – from
packages/models/reports/metrics.json`.

**Evidence:** the two pending paths above; fixture shape in
`contracts/fixtures/scorecard.json`.

## 8. What if the customer cannot pay anything?

The zero-capacity path stops asking for payment. It can surface a policy-defined insurance
referral, agree a review route and book a compliant hardship-officer callback rather than
inventing an unaffordable token payment.

**Evidence:** `contracts/fixtures/bot_reply_zero_capacity.json`;
`contracts/fixtures/relief_options_ravi.json`.

## 9. Does restructuring hurt the customer?

It can carry serious consequences, so the system must not present it as a harmless rescue.
Eligibility comes from board-approved policy, human approval is required, and the customer
must receive the applicable NPA or settlement disclosure before accepting.

**Evidence:** `contracts/fixtures/policy.json`;
`contracts/schemas/ReliefOption.schema.json`; final regulatory detail pending
`governance/rbi_mapping.md`.

## 10. What RBI requirements are enforced rather than merely documented?

The target control points cover DPD classification, contact timing, harsh or misleading text,
contact records, policy-defined relief, human approval, grievances and data minimisation.
Implementation-by-implementation proof remains `TBD – from governance/rbi_mapping.md` and the
owning workstream tests.

**Evidence:** `docs/deck/rbi_slide.md`; `contracts/schemas/ContactEvent.schema.json`;
pending `governance/rbi_mapping.md`.

## 11. Are the RBI paragraph 454 requirements already in force?

No. The project treats those controls as a design target effective 1 January 2027. We state
that date explicitly and do not present future-effective directions as current law.

**Evidence:** `README.md`; `docs/deck/rbi_slide.md`; final source mapping pending
`governance/rbi_mapping.md`.

## 12. Which BIS standards matter here, and how exactly?

The mapping covers 17 Indian Standards (14 standard families): AI governance and risk, human
oversight, bias and model quality, data life cycle, information security, complaints,
contact-centre service and ICT accessibility. Each maps to a concrete artifact or test.

**Evidence:** `docs/deck/bis_slide.md`; pending `governance/bis_mapping.md`.

## 13. Are you claiming BIS certification?

No. This is design alignment with relevant Indian Standards, not certification. Independent
certification or conformity assessment would be a separate process outside this hackathon
prototype.

**Evidence:** `README.md`; `docs/deck/bis_slide.md`.

## 14. How good are the Tamil and Hindi conversations?

The contract and string architecture support English, Tamil and Hindi, but language coverage
does not prove linguistic quality. Final claims require automated tests, native-speaker review
and screenshots; those are still pending from WS4 and WS6.

**Evidence:** `packages/chatbot/README.md`; `contracts/schemas/BotReply.schema.json`;
pending `apps/web/screenshots/`.

## 15. What is the cost per account, and what business improvement do you achieve?

We will answer only from WS2’s committed results, framed “among at-risk accounts, in
simulation.” The oracle is an upper bound, not an achievable strategy. NPA rate, cure rate,
collection cost and contacts are `TBD – from packages/models/reports/policy_simulation.json`.

**Evidence:** pending path above; illustrative schema fixture in
`contracts/fixtures/simulation_metrics.json`.

## 16. How would a bank deploy this safely?

Start with offline validation, then a monitored staff-assist pilot rather than autonomous
customer treatment. The bank must own policy, approvals, model validation, access controls,
audit retention, translation review, incident response and phased rollout gates.

**Evidence:** `docs/architecture.md`; final governance controls pending
`governance/ai_register.md` and `governance/risk_register.md`.

## 17. Where is human oversight?

Relief options declare whether approval is required, and approved offers record the approver’s
identity. Zero-capacity customers are handed to a hardship officer, while collectors retain an
explainable queue rather than receiving an opaque automated command.

**Evidence:** `contracts/schemas/ReliefOption.schema.json`;
`contracts/schemas/Offer.schema.json`; `contracts/fixtures/callback.json`.

## 18. How do you protect privacy and prevent staff from seeing too much?

The target architecture uses role-minimised customer profiles, masked contact details and
provider boundaries that exclude protected attributes from serving paths. Production proof of
authorization, encryption and audit enforcement remains pending WS5 and WS7 evidence.

**Evidence:** `contracts/schemas/CustomerProfile.schema.json`;
`contracts/data/protected_attributes.md`; pending `governance/bis_mapping.md`.

## 19. What happens when a customer complains?

The shared complaint object creates a docket, status, escalation level, SLA time and grievance
officer details. The target flow acknowledges the complaint and preserves a route to the RBI
Ombudsman when the applicable waiting period is reached.

**Evidence:** `contracts/schemas/Complaint.schema.json`;
`contracts/fixtures/complaint.json`; final wording pending `governance/rbi_mapping.md`.

## 20. What remains before this is production-ready?

Substantially more than a successful demo: real bank data governance, independent model
validation, security and privacy review, native-language validation, operational resilience,
staff training, monitoring, customer research, legal review and a controlled pilot.

**Evidence:** current limitations in `README.md` and `docs/deck/deck.md`; final risk inventory
pending `governance/risk_register.md`.

## Answer discipline

- Say whether evidence is a contract, fixture, integrated test or measured result.
- Report red-team case pass rate as N/144 and strict requirement coverage as X of 15 in-scope
  RBI requirements, plus planned and out-of-scope counts.
- Never quote a fixture pass rate or simulation delta as achieved performance; quote only WS2’s
  real simulation numbers and call the oracle an upper bound.
- Never say “RBI compliant” or “BIS certified.” Describe the exact control and evidence.
- If a path is still pending, say so and explain what would verify it.
- For policy or legal interpretation, point to the mapping and recommend bank legal/compliance
  review rather than improvising.
