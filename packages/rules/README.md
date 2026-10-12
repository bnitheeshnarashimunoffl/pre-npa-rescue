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
| `relief_calc.py` | `estimate_affordability`, `size_emi` (shortest tenure with EMI ≤ affordable), `emi_schedule` (principal/interest split), `size_waiver`, `size_settlement`; `AccountSnapshot` input | RBI Credit Card Directions 2025 (EMI transparency); 2023 settlement framework |
| `personas.py` | Priya and Ravi as the rules engine sees them (demo inputs, shared with WS1) | — |
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

## Demo personas (task 3.2 demo requirement)

`npa_rules.personas` holds WS3's numbers; WS1's persona generator should match them.

| | Priya (`CUST-DEMO-PRIYA`) | Ravi (`CUST-DEMO-RAVI`) |
|---|---|---|
| DPD / bucket | 12 / sma0 | 45 / sma1 |
| Outstanding | ₹1,10,000 | ₹64,800 |
| Overdue (unpaid MAD) | ₹11,492 | ₹9,000 |
| Waivable charges | ₹1,180 (₹1,000 late fee + 18% GST) | ₹1,180 |
| Declared in chat | income ₹20,000, essentials ₹9,000, 1 dependant → (20,000 − 9,000 − 3,000) × 0.3 = **₹2,400/month** | income ₹0 → **₹0** |
| Card insurance | none | job-loss cover |
| Options | fee waiver ₹1,180 · **₹2,000/month × 6, late fees waived** | insurance referral · fee waiver · restructuring (officer) · review date (officer) |

The full ₹1,10,000 is not affordable at ₹2,400/month even over 12 months, so (per the
briefing) the plan covers the **overdue amount**, with the late charges waived:
EMI(₹11,492, 6 months, 15% p.a.) = ₹2,000.00 exactly (total interest ₹507.98). The formula is
not adjusted to produce this; the persona's overdue amount was chosen to match it.

Without a declaration, affordability is **estimated** (`source="estimated"`) from last month's
credited income or the average payment of the last 3 months, whichever gives more. The
chatbot must confirm it with the customer before offering a plan.

## Run

```bash
uv run pytest packages/rules/tests
```
