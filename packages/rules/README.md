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
| `RBI-454Z-MINIMISATION` | False reassurance: "won't affect your credit score", "interest is frozen", a payment holiday, "nothing is reported to the bureau", "settlement has no downside" | para 454Z(8) |
| `RBI-454Z-THIRD-PARTY` | Telling employer, colleagues, neighbours or relatives | para 454Z, 454O |
| `RBI-454Z-SHAMING` | Defaulter lists, social-media exposure, shaming | para 454Z |
| `INBOUND-ALLOWED` | Customer-initiated contact (or the bot's replies in it): allowed at any hour | para 454Y(4) restricts outbound recovery contact only |

`check_contact` returns `next_allowed_at`: the earliest time every contact rule passes
(window, quiet times, caps and gap combined). `check_text` applies every language's patterns
(en, hi, ta, plus romanised Hinglish/Tanglish), so code-mixed text is caught. Patterns match
**assertions, not mentions** (issue #60): "you will go to jail" is blocked, but the truthful
denial "you will not go to jail" passes, so the bot can answer "will I go to jail?" honestly.
English skips a phrase directly preceded by "not", "never" or "n't". Negation in another
clause doesn't count: "If you don't pay, you will go to jail" is still blocked. Hindi and
Tamil list only affirmative verb forms ("जेल जाएंगे", "சிறைக்குச் செல்வீர்கள்"), because the
negation sits between the noun and the verb. `RBI-454Z-MINIMISATION` covers the opposite
error, playing consequences down. Its statements are themselves negative ("this won't affect
your credit score"), so it is guarded differently. It skips a statement introduced by
"promise / guarantee / say (that)" in English or "कि" in Hindi, or followed by "என்று" in
Tamil. So "I can't promise there will be no impact on your credit score" passes. The bank
policy has no payment holiday, interest keeps running, and settlements are reported as
"settled". Lexicon version `2026.10-v4`. An optional
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

**Collector queue.** `prioritise()` puts the queue in two bands:

1. **Hardship band** (`hardship_officer` actions, when `nba.hardship_first: true`): ordered by
   risk-weighted exposure `p_roll_forward × outstanding`, scaled into (0.5, 1].
2. **Everyone else:** ordered by expected benefit
   `p_roll_forward × max(uplift_score, 0) × outstanding`, scaled into [0, 0.5].

Why a band, not a multiplier: uplift measures how much contact raises the chance of a cure,
and for a customer who cannot pay it is close to 0, so no multiplier on expected benefit lifts
them reliably. Those customers still need documented engagement with a person before any
escalation (RBC para 454D). `no_contact` is 0, and so is any case with no positive expected
benefit. A `priority` above 0.5 always means a hardship case. The queue is **never** ordered
by "ease of extraction", and nothing in it rewards contact volume: RBC para 454Q requires
that recovery targets and incentives do not encourage harsh practices.

## How to use npa_rules

Import from the modules (the package root re-exports nothing). All examples below run as
written against the shipped policy and the demo personas.

**1. Load the policy and build the three providers** (WS5, `app/deps.py`):

```python
from npa_contracts.enums import Actor, Channel, Lang
from npa_rules.compliance_guard import ComplianceGuard
from npa_rules.nba import NextBestActionService, StaticRiskProvider
from npa_rules.policy_engine import PolicyEngine
from npa_rules.policy_loader import load_policy, parse_policy, PolicyError
from npa_rules.relief_calc import AccountSnapshot

policy = load_policy()  # POLICY_PATH env var, else packages/rules/policies/bank_policy.yaml

# You supply three lookups from the DB (npa_rules never reads a database):
#   account_for_customer(customer_id) -> AccountSnapshot
#   account_for_account(account_id)   -> AccountSnapshot
#   contact_history(customer_id)      -> list[ContactEvent]   (audit log, RBC 454P)
# AccountSnapshot.from_context(ctx_dict) builds one from a CustomerContextProvider dict.

policy_provider = PolicyEngine(policy, account_for_customer)  # PolicyProvider
compliance = ComplianceGuard(policy, contact_history, account_for_customer)  # ComplianceProvider
nba = NextBestActionService(  # NBAProvider
    policy,
    risk_provider,
    compliance,
    account_for_account,
    policy_provider=policy_provider,  # optional: pre-computes options for chat invites
)
nba.next_best_action("ACC-DEMO-PRIYA", "2026-09").action  # NextAction.CHAT_INVITE

# Until WS2 ships: risk_provider = StaticRiskProvider.from_queue_fixture(json_of_queue_fixture)

# PUT /admin/policy: validate, then hot-reload every provider (PolicyError -> HTTP 422).
try:
    new_policy = parse_policy(body)
except PolicyError as exc:
    errors = exc.errors  # list[str], one per problem
else:
    for provider in (policy_provider, compliance, nba):
        provider.reload(new_policy)
```

**2. Relief options for an `Affordability`, then an offer** (WS4 offer flow):

```python
from npa_rules.relief_calc import estimate_affordability

ctx = account_for_customer("CUST-DEMO-PRIYA")
afford = estimate_affordability(
    ctx,
    {"income_paise": 2_000_000, "expenses_paise": 900_000, "dependants": 1},  # from the chat
    policy.affordability,
)  # declared=None gives source="estimated": confirm with the customer before offering
options = policy_provider.relief_options("CUST-DEMO-PRIYA", afford)  # least harmful first
plan = next(o for o in options if o.type == "emi_conversion")  # 200000 paise x 6
offer = policy_provider.propose_offer("CUST-DEMO-PRIYA", plan.option_id, Actor.BOT)
offer.status  # "approved", or "proposed" when option.requires_human_approval
```

Show only these options and amounts. `propose_offer` raises `UnknownOptionError` for any
`option_id` that `relief_options` did not just return for that customer.

**3. Contact and text checks** (every outbound message, every bot reply):

```python
from datetime import datetime
from zoneinfo import ZoneInfo

now = datetime(2026, 10, 12, 21, 0, tzinfo=ZoneInfo("Asia/Kolkata"))  # must be tz-aware
d = compliance.check_contact("CUST-DEMO-PRIYA", Channel.SMS, now, Actor.SYSTEM)
d.allowed, d.rule_ids, d.next_allowed_at  # False, ['RBI-454Y4-WINDOW'], 2026-10-13 08:00 IST

# The customer started the chat: the bot may reply at any hour.
compliance.check_contact("CUST-DEMO-PRIYA", Channel.CHAT, now, Actor.BOT, direction="inbound")

v = compliance.check_text("Pay today or we will take legal action.", Lang.EN)
v.allowed, v.rule_ids  # False, ['RBI-454Z-THREAT']: do not send
```

**4. Disclosure texts and the mandatory footer:**

```python
from npa_rules.disclosures import disclosure_text

for key in plan.disclosure_keys:  # show every one whenever the option is presented
    text = disclosure_text(key, Lang.TA)  # KeyError for an unknown key
footer = compliance.required_footer(Lang.HI)  # recording notice + grievance officer + Ombudsman
```

## Demo personas (task 3.2 demo requirement)

`npa_rules.personas` holds WS3's numbers; WS1's persona generator should match them.

| | Priya (`CUST-DEMO-PRIYA`) | Ravi (`CUST-DEMO-RAVI`) |
|---|---|---|
| DPD / bucket | 12 / sma0 | 45 / sma1 |
| Outstanding | ₹1,10,000 | ₹64,800 |
| Overdue (unpaid MAD) | ₹11,492 | ₹9,000 |
| Late charges (slab on post-due outstanding) | ₹1,534 (₹1,300 top slab on ₹1,10,000 + 18% GST) | ₹1,534 (₹1,300 top slab on ₹64,800 + 18% GST) |
| Declared in chat | income ₹20,000, essentials ₹9,000, 1 dependant → (20,000 − 9,000 − 3,000) × 0.3 = **₹2,400/month** | income ₹0 → **₹0** |
| Card insurance | none | job-loss cover |
| Options | fee waiver ₹1,534 · **₹2,000/month × 6, late fees waived** | insurance referral · fee waiver · restructuring (officer) · review date (officer) |

The full ₹1,10,000 is not affordable at ₹2,400/month even over 12 months, so (per the
briefing) the plan covers the **overdue amount**, with the late charges waived:
EMI(₹11,492, 6 months, 15% p.a.) = ₹2,000.00 exactly (total interest ₹507.98). The formula is
not adjusted to produce this; the persona's overdue amount was chosen to match it.

Late charges follow the RBI rule in `dues.late_fee`: the slab is chosen on the **amount
outstanding after the due date** (the whole unpaid balance), not on the overdue minimum (issue
#1 decision). Both personas owe more than ₹25,000 after the due date, so both are in the top
slab: ₹1,300 + 18% GST = ₹1,534. `tests/test_personas.py` recomputes this from the policy
slabs.

Without a declaration, affordability is **estimated** (`source="estimated"`) from last month's
credited income or the average payment of the last 3 months, whichever gives more. The
chatbot must confirm it with the customer before offering a plan.

## Tamil and Hindi texts to review

Every customer-facing ta/hi string in this package is a first draft. English is the reviewed
source. The disclosures are marked `needs_review` in `disclosures.py`, and the footer
templates live in `compliance_guard.py`. A Tamil or Hindi speaker can check them all here in
one pass: tick a box when the text is accurate, plain and no harsher or softer than the
English. Send corrections to WS3, who also clears `needs_review` for the reviewed language.
`tests/test_review_list.py` fails if a string in this list no longer matches the code.

1. `disc.fee_waiver.stops_growth`
   - en (source): We will remove the late fees shown in this offer, so those fees no longer add to what you owe. Interest on your remaining card balance still applies as shown in your statement.
   - [ ] ta: இந்தச் சலுகையில் காட்டப்பட்டுள்ள தாமதக் கட்டணங்களை நாங்கள் நீக்குவோம்; அவை இனி உங்கள் நிலுவையில் சேராது. மீதமுள்ள அட்டை நிலுவைக்கான வட்டி உங்கள் அறிக்கையில் காட்டியபடி தொடரும்.
   - [ ] hi: इस ऑफ़र में दिखाए गए विलंब शुल्क हम हटा देंगे, इसलिए वे आपकी बकाया राशि में नहीं जुड़ेंगे। बचे हुए कार्ड बैलेंस पर ब्याज आपके स्टेटमेंट के अनुसार लगता रहेगा।
2. `disc.emi.principal_interest_shown`
   - en (source): Each monthly instalment is shown split into the amount you owe and the interest on it. You will see the total interest for the whole plan before you agree.
   - [ ] ta: ஒவ்வொரு மாதத் தவணையும் நீங்கள் செலுத்த வேண்டிய தொகை மற்றும் அதற்கான வட்டி எனப் பிரித்துக் காட்டப்படும். ஒப்புக்கொள்வதற்கு முன் முழுத் திட்டத்திற்கான மொத்த வட்டியைப் பார்க்கலாம்.
   - [ ] hi: हर मासिक किस्त में मूल बकाया और उस पर ब्याज अलग-अलग दिखाया जाता है। सहमति देने से पहले आप पूरी योजना का कुल ब्याज देख सकेंगे।
3. `disc.restructuring.npa_downgrade`
   - en (source): If your repayment plan is restructured, your account will be classified as a non-performing asset. It can be upgraded after you repay as agreed for the required period.
   - [ ] ta: உங்கள் திருப்பிச் செலுத்தும் திட்டம் மறுசீரமைக்கப்பட்டால், உங்கள் கணக்கு செயல்படாத சொத்தாக (NPA) வகைப்படுத்தப்படும். ஒப்புக்கொண்டபடி தேவையான காலம் செலுத்திய பிறகு அது மேம்படுத்தப்படலாம்.
   - [ ] hi: अगर आपकी भुगतान योजना का पुनर्गठन होता है, तो आपका खाता गैर-निष्पादित आस्ति (NPA) के रूप में वर्गीकृत होगा। तय अवधि तक सहमति के अनुसार भुगतान करने के बाद इसे अपग्रेड किया जा सकता है।
4. `disc.restructuring.upgrade_after_performance`
   - en (source): Your account returns to standard status only after you have paid as agreed for the period set in the bank's policy. A hardship officer will tell you that period before you agree.
   - [ ] ta: வங்கியின் கொள்கையில் குறிப்பிட்ட காலம் வரை ஒப்புக்கொண்டபடி செலுத்திய பிறகே உங்கள் கணக்கு சாதாரண நிலைக்குத் திரும்பும். நீங்கள் ஒப்புக்கொள்வதற்கு முன் அந்தக் காலத்தை கஷ்டநிலை அலுவலர் உங்களுக்குத் தெரிவிப்பார்.
   - [ ] hi: बैंक की नीति में तय अवधि तक सहमति के अनुसार भुगतान करने के बाद ही आपका खाता मानक स्थिति में लौटता है। सहमति से पहले हार्डशिप अधिकारी आपको यह अवधि बताएंगे।
5. `disc.settlement.cooling_period`
   - en (source): After a settlement, the bank will not offer you new credit for at least 12 months.
   - [ ] ta: தீர்வுக்குப் பிறகு, குறைந்தது 12 மாதங்களுக்கு வங்கி உங்களுக்குப் புதிய கடன் வழங்காது.
   - [ ] hi: समझौते के बाद, बैंक आपको कम से कम 12 महीनों तक नया क्रेडिट नहीं देगा।
6. `disc.settlement.over_3_months_is_restructuring`
   - en (source): If a settlement is paid over more than 3 months, it is treated as a restructuring, and the restructuring rules explained to you also apply.
   - [ ] ta: தீர்வுத் தொகை 3 மாதங்களுக்கு மேல் செலுத்தப்பட்டால், அது மறுசீரமைப்பாகக் கருதப்படும்; உங்களுக்கு விளக்கப்பட்ட மறுசீரமைப்பு விதிகளும் பொருந்தும்.
   - [ ] hi: अगर समझौते की राशि 3 महीने से अधिक समय में चुकाई जाती है, तो इसे पुनर्गठन माना जाता है और आपको बताए गए पुनर्गठन के नियम भी लागू होते हैं।
7. `disc.settlement.bureau_reporting`
   - en (source): A settlement is reported to credit bureaus as settled, not as paid in full, and this can affect future loans. The bank updates the credit bureaus within 30 days of the settlement.
   - [ ] ta: தீர்வு, முழுமையாகச் செலுத்தப்பட்டதாக அல்லாமல் 'தீர்வு செய்யப்பட்டது' என்று கடன் தகவல் நிறுவனங்களுக்குத் தெரிவிக்கப்படும்; இது எதிர்காலக் கடன்களைப் பாதிக்கலாம். தீர்வுக்குப் பின் 30 நாட்களுக்குள் வங்கி அவற்றைப் புதுப்பிக்கும்.
   - [ ] hi: समझौते की जानकारी क्रेडिट ब्यूरो को 'पूरा भुगतान' नहीं, बल्कि 'सेटल्ड' के रूप में दी जाती है, और इससे भविष्य के ऋण प्रभावित हो सकते हैं। बैंक समझौते के 30 दिनों के भीतर क्रेडिट ब्यूरो को अपडेट करता है।
8. `disc.insurance.claim_process`
   - en (source): Your card may include insurance cover. The insurer decides a claim under the policy terms, so payment is not guaranteed. A hardship officer can help you start a claim.
   - [ ] ta: உங்கள் அட்டையில் காப்பீட்டுப் பாதுகாப்பு இருக்கலாம். காப்பீட்டு விதிமுறைகளின்படி காப்பீட்டு நிறுவனமே கோரிக்கையை முடிவு செய்யும்; எனவே பணம் கிடைக்கும் என்று உறுதி இல்லை. கோரிக்கையைத் தொடங்க கஷ்டநிலை அலுவலர் உதவுவார்.
   - [ ] hi: आपके कार्ड में बीमा कवर हो सकता है। दावे का फ़ैसला बीमा कंपनी पॉलिसी की शर्तों के अनुसार करती है, इसलिए भुगतान की गारंटी नहीं है। दावा शुरू करने में हार्डशिप अधिकारी आपकी मदद कर सकते हैं।
9. `disc.review.what_happens_next`
   - en (source): No payment is asked from you now. A hardship officer will review your situation with you on the agreed date. Your dues stay on your account and appear in your statements, and charges may still apply under your card terms.
   - [ ] ta: இப்போது உங்களிடம் எந்தப் பணமும் கேட்கப்படவில்லை. ஒப்புக்கொண்ட தேதியில் கஷ்டநிலை அலுவலர் உங்களுடன் உங்கள் நிலையை மறுபரிசீலனை செய்வார். உங்கள் நிலுவை கணக்கில் தொடர்ந்து அறிக்கைகளில் காட்டப்படும்; அட்டை விதிமுறைகளின்படி கட்டணங்கள் பொருந்தலாம்.
   - [ ] hi: अभी आपसे कोई भुगतान नहीं माँगा जा रहा है। तय तारीख़ पर हार्डशिप अधिकारी आपके साथ आपकी स्थिति की समीक्षा करेंगे। आपकी बकाया राशि खाते में बनी रहेगी और स्टेटमेंट में दिखेगी, और कार्ड की शर्तों के अनुसार शुल्क लग सकते हैं।
10. Footer: `required_footer(lang)` with the shipped policy
   - en (source): This conversation may be recorded. For any complaint, contact our Grievance Officer: Grievance Redressal Officer, gro@demobank.example, 1800-000-0000, Demo Bank Ltd, Chennai 600001. If it is not resolved within 30 days, you can approach the RBI Ombudsman.
   - [ ] ta: இந்த உரையாடல் பதிவு செய்யப்படலாம். புகார் இருந்தால் எங்கள் குறைதீர் அலுவலரைத் தொடர்பு கொள்ளுங்கள்: Grievance Redressal Officer, gro@demobank.example, 1800-000-0000, Demo Bank Ltd, Chennai 600001. 30 நாட்களுக்குள் தீர்வு கிடைக்காவிட்டால், நீங்கள் RBI குறைதீர்ப்பாளரை அணுகலாம்.
   - [ ] hi: यह बातचीत रिकॉर्ड की जा सकती है। किसी भी शिकायत के लिए हमारे शिकायत निवारण अधिकारी से संपर्क करें: Grievance Redressal Officer, gro@demobank.example, 1800-000-0000, Demo Bank Ltd, Chennai 600001। अगर 30 दिनों में समाधान नहीं होता, तो आप RBI लोकपाल से संपर्क कर सकते हैं।

## Run

```bash
uv run pytest packages/rules/tests
uv run python -m npa_rules.cli validate [--policy PATH]      # validate a policy file
uv run python -m npa_rules.cli fixtures --out DIR            # WS3 contract fixtures (B4)
```

`fixtures` writes `relief_options_priya.json`, `relief_options_ravi.json`, `offer.json`,
`nba.json`, `queue.json` and `policy.json` deterministically (fixed clock 2026-10-12 11:00 IST).
`contracts/fixtures/` is owned by WS5, so WS5 copies them in through a `contract` PR.
