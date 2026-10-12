# Risk register

**Owner:** WS7 · **Supports:** IS/ISO/IEC 23894:2023 (AI risk management) applied through the
IS/ISO 31000:2018 process (identify → analyse → evaluate → treat → monitor) · **Last reviewed:**
2026-10-12 · **Design alignment, not certification.**

## Method

- **Likelihood (L)** and **impact (I)** are scored 1–5. **Inherent score = L × I** before controls.
- **Residual** is our judgement after the listed controls work as designed: **Low** (≤ 4),
  **Medium** (5–9), **High** (≥ 10). While a control is only *In review* or *Planned*, the
  residual is shown as the target, marked †.
- **Impact** is judged on harm to the customer first (distress, unfair treatment, wrong money),
  then on regulatory breach, then on the bank.
- Controls link to code and tests. File paths under `packages/rules/` are in open WS3 PRs
  #40–#46 until merged; paths under `redteam/` are WS7 tasks #31/#32.
- Review cadence: every red-team run, and whenever a PR changes a listed control.

## Summary

| ID | Risk | L | I | Inherent | Residual | Owner |
|---|---|---|---|---|---|---|
| R01 | Wrong or invented offer | 3 | 5 | 15 | Low † | WS3 |
| R02 | Harmful or threatening reply | 3 | 5 | 15 | Low † | WS4 |
| R03 | Discrimination | 3 | 5 | 15 | Medium † | WS2 |
| R04 | Prompt injection | 4 | 4 | 16 | Low † | WS4 |
| R05 | Data leak | 3 | 5 | 15 | Medium † | WS5 |
| R06 | Model drift | 3 | 3 | 9 | Medium † | WS2 |
| R07 | Over-contact | 3 | 4 | 12 | Low † | WS3 |
| R08 | Misleading consequences | 3 | 5 | 15 | Low † | WS3 / WS4 |
| R09 | Tamil / Hindi translation errors | 4 | 4 | 16 | Medium † | WS4 |
| R10 | LLM outage | 3 | 3 | 9 | Low † | WS4 |
| R11 | Incorrect dues calculation | 2 | 5 | 10 | Low † | WS3 |
| R12 | Bias in the synthetic data | 4 | 3 | 12 | Medium † | WS1 |
| R13 | Over-reliance on automation | 3 | 4 | 12 | Medium † | WS3 / WS6 |
| R14 | Insurance mis-referral | 2 | 4 | 8 | Low † | WS3 / WS4 |
| R15 | Complaint loss | 2 | 4 | 8 | Low † | WS4 / WS5 |
| R16 | Protected attribute leaks into model features | 2 | 5 | 10 | Low † | WS2 |
| R17 | Distress missed (bereavement, medical, suicidal language) | 3 | 5 | 15 | Medium † | WS4 |
| R18 | Red-team results inflated or stale | 3 | 3 | 9 | Low † | WS7 |

## Detail

### R01 Wrong or invented offer
- **Cause:** the LLM states an amount, tenure or product (for example a "payment holiday") that the
  policy does not provide, or the engine picks an option the customer is not eligible for.
- **Controls:** relief options come only from `packages/rules/policies/bank_policy.yaml` via
  `PolicyEngine.relief_options`. `PolicyEngine.propose_offer` rejects any `option_id` it did not
  issue (`test_propose_unknown_option_rejected`). Disabled options are never offered
  (`test_disabled_option_never_offered`). EMIs never exceed affordability
  (`test_size_emi_never_exceeds_affordable`). Red-team number-consistency judge: every amount in
  `BotReply.text` must equal a field of an offered `ReliefOption`. The `prompt_injection` suite
  tries to set amounts.
- **Residual:** Low †.

### R02 Harmful or threatening reply
- **Cause:** LLM phrasing that is minatory, shaming, or mentions employers or relatives (RBI para 454Z).
- **Controls:** `ComplianceGuard.check_text` with `policies/compliance_lexicon.yaml` across
  en/hi/ta and romanised text (`test_harsh_text_blocked`, `test_kind_text_allowed`). Output
  guardrails in `packages/chatbot/src/npa_chat/guardrails.py` (#18). Red-team `pressure` suite
  (≥ 20 cases × 3 languages) with an LLM tone judge on demo runs.
- **Residual:** Low †. A lexicon cannot catch every paraphrase, so the tone judge and human
  review of the demo runs remain.

### R03 Discrimination
- **Cause:** different offers, actions or tone by gender, religion, caste or region, directly or
  through proxies (city, name, language).
- **Controls:** protected attributes live only in `protected_attributes.parquet` (see R16).
  WS2 fairness metrics in `packages/models/reports/metrics.json` (task 2.5). Red-team
  `bias_swap` suite: same story and financials with only the name and protected attributes
  swapped, which must give an identical offer, action and eligibility. Model-level pairs are run
  through NBA. The scorecard imports the model fairness metrics (task 7.2).
- **Residual:** Medium †. Proxy effects through `city` or language preference can remain; we
  measure them rather than claim they are absent.

### R04 Prompt injection
- **Cause:** "ignore your rules", fake system messages, role-play, instructions hidden in pasted
  letters, ta/hi jailbreaks, system-prompt extraction.
- **Controls:** the LLM has no authority. Amounts and options come from the rules engine (R01),
  so a successful injection can change wording but not the offer. `guardrails.py` input and output
  filters set the `injection_blocked` flag. Red-team `prompt_injection` suite (≥ 20 cases, three
  languages).
- **Residual:** Low †.

### R05 Data leak
- **Cause:** the bot or API reveals another customer's data, unmasked phone or email, or protected
  attributes; ID enumeration on `/customers/{id}`.
- **Controls:** `CustomerContextProvider.context` returns a minimised profile with no protected
  attributes. Phone and email are stored masked (`phone_masked`, `email_masked`, WS5 #39).
  Role checks on every route (`services/api/app/security.py`, #21) return 404 on another
  customer's ID. The bot refuses to ask for OTP or CVV. Red-team `privacy_extraction` suite.
- **Residual:** Medium †. Role checks are not yet merged; the bootstrap API serves fixtures to
  anyone.

### R06 Model drift
- **Cause:** income or spending patterns change, so risk scores and uplift groups stop matching reality.
- **Controls:** `model_version` on every output, population stability of the score and calibration
  in the model report card (`packages/models/reports/`, #8). Retraining needs a PR plus an
  `ai_register.md` update.
- **Residual:** Medium †. Synthetic data cannot show real drift; monitoring is designed, not exercised.

### R07 Over-contact
- **Cause:** too many calls or messages, calls outside 08:00–19:00 IST, or contact during
  bereavement or medical emergencies (RBI para 454Y(4), 454Y(6), 454Z).
- **Controls:** `ComplianceGuard.check_contact`: `RBI-454Y4-WINDOW` (`test_contact_window_in_ist`,
  `test_window_evaluated_in_ist_even_for_utc_input`), `RBI-454Y4-PREF`
  (`test_customer_quiet_time_preference`), `RBI-454Y6-OCCASION` (`test_do_not_contact_flags`),
  `RBI-454Z4-EXCESSIVE` at 2/day, 6/week and a 180-minute gap, all bank policy assumptions
  (`test_daily_cap`, `test_weekly_cap`, `test_min_gap_between_attempts`). Red-team
  `contact_rules` suite. The uplift `sleeping_dog` group gets no contact.
- **Residual:** Low †.

### R08 Misleading consequences
- **Cause:** the bot exaggerates (jail, police, family liable, property seized, CIBIL "forever")
  or minimises ("no impact on your credit score") (RBI para 454Z(8)).
- **Controls:** `RBI-454Z-MISLEADING` lexicon. Mandatory disclosure texts in
  `packages/rules/src/npa_rules/disclosures.py` (`test_disclosures_never_make_banned_promises`,
  `test_restructuring_disclosure_text_is_the_briefed_wording`). Red-team
  `misleading_consequences` suite.
- **Residual:** Low †.

### R09 Tamil / Hindi translation errors
- **Cause:** machine-drafted ta/hi texts change meaning, sound harsh, or drop a disclosure.
- **Controls:** every disclosure exists in all three languages (`test_every_policy_disclosure_has_three_languages`).
  ta/hi texts are flagged `needs_review` (`test_translations_flagged_for_review`). The lexicon covers
  ta/hi patterns. Red-team cases are spread across en/ta/hi.
- **Residual:** Medium †. No native-speaker review has been recorded yet. **Action:** obtain one
  before the demo and record the reviewer and date here.

### R10 LLM outage
- **Cause:** the Anthropic API is unavailable, slow, or returns malformed JSON.
- **Controls:** everything goes through the `LLMClient` protocol, with `MockLLMClient` in CI and as
  a fallback. Fixed i18n templates (`npa_chat/i18n/`) carry every fact. On failure the bot offers a
  hardship-officer callback instead of guessing.
- **Residual:** Low †.

### R11 Incorrect dues calculation
- **Cause:** wrong DPD, bucket, late fee, interest on fees, or negative amortisation.
- **Controls:** `packages/rules/src/npa_rules/dues.py` with integer paise and hypothesis property
  tests: `test_no_late_fee_within_grace`, `test_late_fee_uses_post_due_outstanding_slab`,
  `test_mad_no_negative_amortisation`, `test_npa_only_after_ninety_days`, `test_dpd_property`.
  RBI constants in `packages/contracts/src/npa_contracts/constants.py` (on `main`).
- **Residual:** Low †.

### R12 Bias in the synthetic data
- **Cause:** the generator (`packages/datagen/`) encodes stereotypes, for example linking region or
  religion to default, so models learn them and fairness tests pass on biased ground truth.
- **Controls:** generator parameters are documented in `data_lifecycle.md`. Hardship shocks are
  drawn independently of protected attributes unless a documented calibration says otherwise. The
  `bias_swap` suite checks treatment parity regardless of the base rates. The limitation is stated
  in model cards.
- **Residual:** Medium †.

### R13 Over-reliance on automation
- **Cause:** staff accept model scores or bot outcomes without judgement, or customers cannot
  reach a human.
- **Controls:** restructuring and settlement always need human approval (`requires_human_approval`,
  enforced by `policy_loader.py`; `test_propose_offer_needs_human`). Zero-capacity customers go to
  a hardship officer (`test_ravi_gets_hardship_officer`). Every reply carries the grievance route.
  Dashboard reasons are shown with every score (WS6 #26).
- **Residual:** Medium †.

### R14 Insurance mis-referral
- **Cause:** telling a customer they are covered when they are not, or promising that a claim will pay.
- **Controls:** the insurance referral is offered only when `has_card_insurance` is true
  (`test_ravi_zero_capacity_set_insurance_first`). The disclosure `disc.insurance.claim_process`
  states that the insurer decides the claim. A red-team case asks "will insurance pay my bill?"
- **Residual:** Low †.

### R15 Complaint loss
- **Cause:** a complaint made in chat is not recorded, gets no docket, or misses the 30-day route
  to the Ombudsman (IS/ISO 10002:2018; RBI para 454AA).
- **Controls:** complaint flow `npa_chat/flows/complaint.py` (#17) calls `ComplaintSink.open`,
  which returns a docket `CMP-YYYYMMDD-NNNN` with `sla_due_at = created_at + 30 days`
  (`COMPLAINT_SLA_DAYS`). Persisted in the `complaints` table (WS5 #39). Grievance footer on every
  message (`test_footer_has_grievance_officer_recording_and_ombudsman`).
- **Residual:** Low †.

### R16 Protected attribute leaks into model features
- **Cause:** `gender`, `religion`, `caste_category`, `state` or `region` is joined into training data.
- **Controls:** separate table `protected_attributes.parquet` (`contracts/data/protected_attributes.md`).
  WS2 must assert that feature lists exclude these columns (requested in #4). A WS7 red-team
  check will scan `features.parquet` columns.
- **Residual:** Low †.

### R17 Distress missed
- **Cause:** a customer mentions bereavement, a medical emergency or self-harm and the bot keeps
  discussing payment.
- **Controls:** `npa_chat/distress.py` (#16) stops recovery talk and hands off to a human. The
  `RBI-454Y6-OCCASION` flag blocks outbound contact until an officer clears it. Red-team
  `pressure` cases include distress statements in all three languages.
- **Residual:** Medium †. Distress detection in ta/hi is the weakest part and needs native review.

### R18 Red-team results inflated or stale
- **Cause:** cases check wording instead of properties, the scorecard is not re-run after fixes,
  or failures are hidden.
- **Controls:** judges check properties (amounts, offer types, rule IDs, absence of banned
  content). Every run is committed under `redteam/reports/RT-*/`. Failures are filed as issues
  labelled `bug` and `redteam` and re-tested. The scorecard reports the real pass rate.
- **Residual:** Low †.
