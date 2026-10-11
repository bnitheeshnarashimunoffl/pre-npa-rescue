# Contracts changelog

Format: `## <version> — <YYYY-MM-DD>` then bullet points. Minor = additive, patch = docs/fixtures.
Breaking changes are marked **BREAKING** and need the team lead's approval.

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
