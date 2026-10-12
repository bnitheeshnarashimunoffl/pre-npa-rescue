# npa_rules

**Owner:** WS3 (Decision & rules layer) · mypy strict

Policy engine over `policies/bank_policy.yaml` (the only source of allowed relief options),
relief/affordability calculator, compliance guard and next-best-action. Implements
`PolicyProvider`, `ComplianceProvider` and `NBAProvider`. Pure library: no database, no HTTP.

**Tasks:** 3.1 policy engine · 3.2 relief calculator · 3.3 compliance guard · 3.4 next-best-action

## Modules

| Module | What | RBI / BIS |
|---|---|---|
| `dues.py` | DPD, bucket, late fee, interest, minimum amount due (pure, integer paise) | RBI Credit Card Directions 2025 (late fee > 3 DPD on post-due outstanding; no capitalisation; no negative amortisation); RBI card NPA rule (> 90 DPD) |

RBI numbers (3-day grace, 90-day NPA, bucket bounds) come from `npa_contracts.constants`.
Late-fee slabs, the principal share of the minimum due and interest rates are **bank policy
assumptions** passed in from `bank_policy.yaml`, never RBI numbers.

## Run

```bash
uv run pytest packages/rules/tests
```
