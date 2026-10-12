# npa_rules

**Owner:** WS3 (Decision & rules layer) · mypy strict

Policy engine over `policies/bank_policy.yaml` (the only source of allowed relief options),
relief/affordability calculator, compliance guard and next-best-action. Implements
`PolicyProvider`, `ComplianceProvider` and `NBAProvider`. Pure library: no database, no HTTP.

**Tasks:** 3.1 policy engine · 3.2 relief calculator · 3.3 compliance guard · 3.4 next-best-action

## Modules

| Module | What | RBI / BIS |
|---|---|---|
| `policy_engine.py` | `PolicyEngine` (`PolicyProvider`): `relief_options`, `propose_offer`, `grievance_officer`, `reload` | Prudential Framework 2019, 2023 settlement framework, RBC 454D (zero-capacity engagement), 454AA; IS/ISO/IEC 38507 (human approval) |
| `nba.py` | `NextBestActionService` (`NBAProvider`), `prioritise` (collector queue), `StaticRiskProvider` (fixture-backed `RiskProvider` until WS2 ships) | RBC 454Y(6), 454Q (no "ease of extraction" priority), 454Z (firm ≠ harsh) |
| `compliance_guard.py` | `ComplianceGuard` (`ComplianceProvider`): `check_contact`, `check_text`, `required_footer`; lexicon in `policies/compliance_lexicon.yaml` | RBC 454Y(4), 454Y(6), 454Z, 454P (recording notice), 454AA (grievance footer) |
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

## Compliance rule IDs (stable; WS7 maps them to the scorecard)

| Rule ID | Meaning | Source |
|---|---|---|
| `RBI-454Y4-WINDOW` | Outbound contact only 08:00–19:00 Asia/Kolkata (evaluated in IST whatever the input tz) | RBI RBC Directions para 454Y(4) |
| `RBI-454Y4-PREF` | Customer asked not to be contacted at this time (`avoid_contact_windows`) | para 454Y(4) |
| `RBI-454Y6-OCCASION` | Bereavement, medical emergency or customer-requested pause flag active; no `next_allowed_at` until an officer clears it | para 454Y(6) |
| `RBI-454Z4-EXCESSIVE` | More than 2 attempts/day, 6/rolling 7 days, or less than 180 min since the last attempt (**bank policy assumptions**) | para 454Z (excessive calling) |
| `RBI-454Z-ABUSIVE` | Abusive or insulting words | para 454Z |
| `RBI-454Z-THREAT` | Threats: legal action, police, visits to home/office/family, "final warning" | para 454Z |
| `RBI-454Z-MISLEADING` | False consequences: jail, family liable, property seizure, "never get a loan" | para 454Z(8) |
| `RBI-454Z-THIRD-PARTY` | Telling employer, colleagues, neighbours or relatives | para 454Z, 454O |
| `RBI-454Z-SHAMING` | Defaulter lists, social-media exposure, shaming | para 454Z |
| `INBOUND-ALLOWED` | Customer-initiated contact (or the bot's replies in it): allowed at any hour | para 454Y(4) restricts outbound recovery contact only |

`check_contact` returns `next_allowed_at`: the earliest time every contact rule passes
(window, quiet times, caps and gap combined). `check_text` applies every language's patterns
(en, hi, ta, plus romanised Hinglish/Tanglish), so code-mixed text is caught. An optional
`llm_judge(text, lang) -> list[rule_id]` hook is injected and off by default. Our own
disclosures and footer are tested to pass the filter. `required_footer(lang)` returns the
recording notice (454P) and the grievance officer's details with the Ombudsman route after
30 days (454AA).

## Policy engine behaviour

* Options are returned **only** when enabled in the policy and the account's bucket is
  eligible. Order: insurance referral → fee waiver → EMI → restructuring → settlement →
  review date (least harmful first).
* EMI: the full balance if it fits, otherwise the overdue amount (plus charges unless
  waived). When a fee waiver is eligible the EMI option also carries the waiver (`-WAIVER`
  suffix, both disclosures, `policy_ref` `emi_conversion.v1+fee_waiver.v1`).
* Zero capacity: never an EMI. Restructuring/settlement come back with
  `monthly_amount_paise = null` and `requires_human_approval = true`, plus a `review_date`.
* Restructuring and settlement **always** need human approval (enforced by the loader too).
* `propose_offer` only accepts an `option_id` returned by the last `relief_options` call for
  that customer (`UnknownOptionError` otherwise), so nothing invented can become an offer.
  Status `approved` (by `policy_engine`) when no human approval is needed, else `proposed`.
  Expiry: `offers.expiry_days` (7, bank policy assumption).
* Option ids are deterministic: `OPT-<account_id>-<KIND>[<tenure>][-WAIVER]`.
* WS5 wiring: `PolicyEngine(load_policy(), accounts=lambda cid: AccountSnapshot.from_context(ctx.context(cid)))`;
  on `PUT /admin/policy` call `engine.reload(parse_policy(body))` (raises `PolicyError` → 422).

## Next-best-action

Rule table (first match wins; full table in `nba.py`): do-not-contact flag → `no_contact`;
low risk + `not_at_risk` → `no_contact`; `sleeping_dog` → `no_contact` (statement message
only); `forgot` / `sure_thing` → `reminder` (SMS); `cant_pay` with estimated capacity below
the minimum EMI → `hardship_officer`; `cant_pay` + `persuadable` → `chat_invite` (relief options
pre-computed when a `PolicyProvider` is injected); other `persuadable` → `chat_invite`, or
`agent_call` after 2 ignored invites; `wont_pay` / `lost_cause` → `firm_process` (written
notice + agent call within the rules; **firm means procedural, never harsh**: every message
still passes `check_text`).

`earliest_contact_at` comes from `check_contact` (now, or `next_allowed_at`). `reason_codes`
are the model's reason codes, then the rule fired (`RULE_*`), then any `WAIT:<rule_id>`.

**Collector queue priority** = expected benefit = `p_roll_forward × max(uplift_score, 0) ×
outstanding`, scaled to 0..1 within the batch. Hardship cases get ×1.5 and a floor of
`p_roll_forward × outstanding × 0.1` (bank policy assumptions in `nba:`), so they are never
pushed to the bottom. `no_contact` is 0. The queue is **never** ordered by "ease of
extraction", and nothing in it rewards contact volume: RBI RBC para 454Q requires that recovery
targets and incentives do not encourage harsh practices.

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
uv run python -m npa_rules.cli validate [--policy PATH]      # validate a policy file
uv run python -m npa_rules.cli fixtures --out DIR            # WS3 contract fixtures (B4)
```

`fixtures` writes `relief_options_priya.json`, `relief_options_ravi.json`, `offer.json`,
`nba.json`, `queue.json` and `policy.json` deterministically (fixed clock 2026-10-12 11:00 IST).
`contracts/fixtures/` is owned by WS5, so WS5 copies them in through a `contract` PR.
