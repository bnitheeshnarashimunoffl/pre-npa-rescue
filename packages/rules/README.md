# npa_rules

**Owner:** WS3 (Decision & rules layer) · mypy strict

Policy engine over `policies/bank_policy.yaml` (the only source of allowed relief options),
relief/affordability calculator, compliance guard and next-best-action. Implements
`PolicyProvider`, `ComplianceProvider` and `NBAProvider`. Pure library: no database, no HTTP.

**Tasks:** 3.1 policy engine · 3.2 relief calculator · 3.3 compliance guard · 3.4 next-best-action

## Modules

| Module | What | RBI / BIS |
|---|---|---|
| `policy_loader.py` | `load_policy(path)` → immutable `Policy`; JSON Schema + Pydantic + RBI cross-checks (an admin edit can never weaken an RBI number or drop a mandatory disclosure) | RBI 454Y(4) window, 454Y(6) flags, 2023 settlement framework (12-month cooling, ≤ 3-month window), Prudential Framework 2019 (NPA-downgrade disclosure), Credit Card Directions (bureau update ≤ 30 days) |
| `disclosures.py` | Mandatory trade-off texts per option, en/ta/hi (ta/hi `needs_review`) | RBI 454Z(8): no misleading statements about consequences |
| `dues.py` | DPD, bucket, late fee, interest, minimum amount due (pure, integer paise) | RBI Credit Card Directions 2025 (late fee > 3 DPD on post-due outstanding; no capitalisation; no negative amortisation); RBI card NPA rule (> 90 DPD) |

RBI numbers (3-day grace, 90-day NPA, bucket bounds) come from `npa_contracts.constants`.
Late-fee slabs, the principal share of the minimum due and interest rates are **bank policy
assumptions** passed in from `bank_policy.yaml`, never RBI numbers.

## Policy file

`policies/bank_policy.yaml` simulates the bank's **board-approved policy**: it is the only
source of relief options. `POLICY_PATH` (A11) overrides its location. After changing the
`Policy` model, regenerate the schema: `uv run python -m npa_rules.policy_loader`.

Every value commented **"bank policy assumption"** in the YAML is a simulated choice of Demo
Bank, not an RBI number: contact caps (2/day, 6/week, 180-min gap), late-fee slabs, card
interest rate, MAD principal % and floor, affordability ratio 0.3, dependant allowance,
offer expiry 7 days, fee-waiver cap and frequency, EMI tenures/rate/minimum, restructuring
tenure/moratorium/rate, settlement sacrifice % and ageing, review intervals. RBI numbers
(08:00–19:00 IST, 12-month cooling, 3-month settlement window, 30-day bureau update) are
checked against `npa_contracts.constants` on every load.

## Run

```bash
uv run pytest packages/rules/tests
```
