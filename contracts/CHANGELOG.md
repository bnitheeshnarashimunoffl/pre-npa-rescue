# Contracts changelog

Format: `## <version> — <YYYY-MM-DD>` then bullet points. Minor = additive, patch = docs/fixtures.
Breaking changes are marked **BREAKING** and need the team lead's approval.

## 0.1.1 — 2026-10-12

Fixtures only (patch). No model, schema or endpoint change. Requested in #47.

- Replaced the WS3-produced fixtures with real `npa_rules` outputs, generated with
  `uv run python -m npa_rules.cli fixtures --out contracts/fixtures` from WS3's #48 (the CLI
  reads the v0 `queue.json` for model outputs; output is deterministic):
  `relief_options_priya.json`, `relief_options_ravi.json`, `offer.json`, `nba.json`,
  `queue.json`, `policy.json`.
- **Disclosure keys are now `disc.*`** (e.g. `disc.restructuring.npa_downgrade`), not
  `disclosure.*`. Texts: `npa_rules.disclosures.disclosure_text(key, lang)`.
- **Option ids** are now `OPT-<account_id>-<KIND>`, e.g. `OPT-ACC-DEMO-PRIYA-EMI6-WAIVER`.
- Priya: `fee_waiver` (Rs 1,180) and `emi_conversion` Rs 2,000 x 6 with late fees waived.
  Both are auto-approved under the bank policy (`requires_human_approval: false`), so
  `offer.json` is `approved` with `approved_by: "policy_engine"`.
- Ravi: `insurance_referral`, `fee_waiver`, `restructuring` (officer approval), `review_date`
  (officer approval).
- `queue.json`: Priya `total_due_paise` 1318000 -> 11000000 (outstanding Rs 1,10,000);
  priorities recomputed by `npa_rules.nba.prioritise`; `ACC-001006` action `agent_call` ->
  `chat_invite`. Ravi is now 5th by priority (`hardship_officer`).
- `policy.json`: `policy` is now the real `bank_policy.yaml` shape (`npa_rules.policy_loader.Policy`,
  schema `packages/rules/policies/bank_policy.schema.json`); version `2026.10-v1`.
- `bot_reply_offer.json`: the embedded offer now matches `offer.json` (status `presented`).
- `CONTRACT_VERSION` 0.1.0 -> 0.1.1 (schemas and `openapi.yaml` regenerated; only the version
  stamp changed).

## 0.1.0 — 2026-10-12

Initial contracts from the shared briefing (A7), created in the WS5 bootstrap.

- `npa_contracts.enums`: all A7.1 enums.
- `npa_contracts.models`: all A7.3 shared objects (Pydantic v2, `extra="forbid"`,
  timezone-aware datetimes only, money as `int` paise, months as `YYYY-MM`).
- `npa_contracts.api`: REST envelopes needed by A7.4 that A7.3 does not define
  (additive): `ErrorResponse`, `LoginRequest`, `TokenResponse`, `HealthResponse`,
  `CustomerProfile`, `AccountSummary`, `QueuePage`, `ContactCheckRequest`,
  `OfferCreateRequest`, `OfferDecisionRequest`, chat session/transcript models, complaint and
  callback requests, `PolicyDocument`, `PolicyUpdateRequest`, `RedTeamRun`,
  `SimulationMetrics`, `KpiReport`, wellness models.
- `npa_contracts.providers`: all A7.5 protocols, plus `ChatEngineProtocol` (the
  `ChatEngine.handle` signature).
- `npa_contracts.constants`: regulatory constants with RBI citations, plus `bucket_for_dpd`.
- `npa_contracts.money`: paise conversion, en-IN grouping, lakh/crore formatting, `split_evenly`.
- `contracts/schemas/`, `contracts/openapi.yaml` (generated), `contracts/data/` table specs.
- `contracts/fixtures/` v0 per A7.6 (Priya: Rs 2,000 x 6 with Rs 1,180 late fees waived;
  Ravi: zero capacity, insurance referral, hardship-officer callback 12 Oct 2026 11:00 IST).
- Notes: `queue.json` is a `QueuePage` (the `GET /collector/queue` response), not a bare array.
  Stub routes that are not built yet return `501 NOT_IMPLEMENTED` in the error envelope.
