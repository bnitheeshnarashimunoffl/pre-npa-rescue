# AI register

**Owner:** WS7 · **Supports:** IS/ISO/IEC 42001:2023 (AI inventory, roles, oversight, monitoring),
IS/ISO/IEC 38507:2022 (governance of AI use), RBI FREE-AI committee report, Aug 2025 (AI inventory;
a recommendation, not binding) · **Last reviewed:** 2026-10-12 · **Design alignment, not certification.**

This register lists every component that uses machine learning or a large language model (LLM).
Deterministic rule components (policy engine, compliance guard, next-best-action) are not AI.
They are listed at the end because they are the **controls** that sit around the AI: *the AI
proposes, the rules decide.*

## Risk tiers

| Tier | Meaning in this system | Minimum oversight |
|---|---|---|
| **High** | Output can reach a customer, or can change what relief or contact a customer gets | Rule gate on every output, plus a human approval or a human review point, plus a red-team suite |
| **Medium** | Output influences staff decisions (ranking, explanations) but never reaches a customer directly | Rule gate or staff review, plus a fairness and performance report |
| **Low** | Internal tooling only; output never touches a customer or a decision | Fixed seed, mocked in CI, results reviewed by a person |

## Register

### AI-01 Early-warning model

| Field | Value |
|---|---|
| Task / owner | 2.1 · **WS2** (`packages/models/`) |
| Purpose | Predict the probability that a card account rolls into the next delinquency bucket within 30–60 days, so that help starts before day 90 |
| Technique | Gradient-boosted trees (LightGBM / XGBoost), seeded |
| Inputs | `features.parquet` columns (contract `contracts/data/features.md`). **Never** the columns in `protected_attributes.parquet` |
| Outputs | `RiskScore` (`p_roll_forward`, `risk_band`, top 3 `reasons`, `model_version`), served via `RiskProvider.risk` (`packages/models/src/npa_models/provider.py`) |
| Risk tier | **Medium**. It ranks accounts for staff; it cannot by itself contact anyone or offer anything |
| Human oversight | Collectors see the score and reasons in the dashboard (`GET /collector/queue`); every resulting contact still passes `ComplianceGuard.check_contact` |
| Monitoring | AUC / PR-AUC, calibration and a confusion matrix at the chosen threshold (IS/ISO/IEC TS 4213 style), population stability of the score, fairness gaps by protected group. All in `packages/models/reports/` (task 2.5) |
| Version | `model_version` on every `RiskScore`; artifacts in `MODEL_DIR` via `npa_models/registry.py` |
| Status | **Planned** (#4) |

### AI-02 Explanation layer

| Field | Value |
|---|---|
| Task / owner | 2.2 · **WS2** (`packages/models/src/npa_models/explain.py`, `reason_codes.yaml`) |
| Purpose | Turn SHAP attributions into plain-language reason codes (for example `SALARY_STOPPED`) in en/ta/hi |
| Inputs | Early-warning model and one account's feature row |
| Outputs | `ReasonCode[]` (`code`, `weight`, `text` in three languages) inside `RiskScore.reasons` |
| Risk tier | **Medium**. Wrong reasons could mislead a collector or, if shown to a customer, upset them |
| Human oversight | Reason texts are a fixed, reviewed catalogue (`reason_codes.yaml`), not free LLM text. Tamil and Hindi entries need native review |
| Monitoring | Agreement between the top SHAP feature and the stated reason; catalogue coverage (every code has three languages) |
| Version | Tied to the early-warning `model_version` and to the git revision of `reason_codes.yaml` |
| Status | **Planned** (#5) |

### AI-03 Segmentation classifier

| Field | Value |
|---|---|
| Task / owner | 2.3 · **WS2** (`packages/models/src/npa_models/segment.py`) |
| Purpose | Classify an at-risk account as `forgot`, `cant_pay`, `wont_pay` or `not_at_risk` so that treatment matches the situation |
| Inputs | Same feature set as AI-01; no protected attributes |
| Outputs | `SegmentResult` (`segment`, `confidence`, `model_version`) |
| Risk tier | **High**. The segment drives the next-best-action (for example a chat invite or a hardship officer) and a `wont_pay` label could lead to a firmer process |
| Human oversight | `wont_pay` never triggers anything harsh: `NextAction.FIRM_PROCESS` still passes the compliance guard and the harsh-practice lexicon. A hardship officer reviews any zero-capacity account |
| Monitoring | Per-class precision and recall, confusion matrix, false-`wont_pay` rate per protected group (WS2 `fairness.py`), bias-swap red-team suite |
| Version | `model_version` on every `SegmentResult` |
| Status | **Planned** (#6) |

### AI-04 Uplift model

| Field | Value |
|---|---|
| Task / owner | 2.4 · **WS2** (`packages/models/src/npa_models/uplift.py`) |
| Purpose | Estimate whether contacting the customer changes the outcome, and sort accounts into `persuadable`, `sure_thing`, `lost_cause`, `sleeping_dog` |
| Technique | Meta-learner uplift (causalml) trained on WS1's simulated experiment (`experiment.parquet`), evaluated with Qini / AUUC |
| Inputs | Feature set plus the treatment assignment from the experiment; no protected attributes |
| Outputs | `UpliftResult` (`uplift_score`, `uplift_group`, `recommended_treatment`, `model_version`) |
| Risk tier | **High**. A wrong `sleeping_dog` or `lost_cause` label could withhold help from someone who needs it |
| Human oversight | Uplift only ranks; it never removes options. A customer who starts a chat always gets the policy engine's full option set. Collector queue priority (`npa_rules/nba.py`) is expected benefit, not "ease of extraction" (RBI para 454Q) |
| Monitoring | Qini / AUUC against the simulated ground truth (`true_uplift_group`), uplift-group distribution by protected group, cure-rate gain in the simulation (`GET /metrics/simulation`) |
| Version | `model_version` on every `UpliftResult` |
| Status | **Planned** (#7) |

### AI-05 Chatbot NLU (intent and slot extraction)

| Field | Value |
|---|---|
| Task / owner | 4.1 · **WS4** (`packages/chatbot/src/npa_chat/nlu.py`) |
| Purpose | Read the customer's message (en/ta/hi, including code-mixed text) and extract intent and slots: hardship type, declared income and expenses, dependants, "can't pay", complaint, language switch |
| Technique | LLM call through the `LLMClient` protocol with a JSON schema (`complete(..., json_schema=...)`); `MockLLMClient` in tests and CI |
| Inputs | Customer text, conversation state, minimised context from `CustomerContextProvider` (no protected attributes, masked phone and email) |
| Outputs | Structured intent and slots. **Declared amounts become inputs to the rules engine (`Affordability`); they never go into customer text directly** |
| Risk tier | **High**. A mis-read "I can't pay" or income figure changes the offer |
| Human oversight | The bot confirms declared figures back to the customer before an offer. Distress signals (`npa_chat/distress.py`) hand off to a human hardship officer. Restructuring and settlement always need a human approval (`requires_human_approval = true`, enforced in WS3's policy loader) |
| Monitoring | Intent accuracy on a labelled test set per language, the `distress_detected` and `zero_capacity` flag rates, red-team `pressure` and `prompt_injection` suites |
| Version | `LLM_MODEL` env (default `claude-sonnet-5-5`) plus the git revision of `npa_chat/prompts/*.md` |
| Status | **Planned** (#13, #14) |

### AI-06 Chatbot phrasing LLM

| Field | Value |
|---|---|
| Task / owner | 4.1–4.6 · **WS4** (`packages/chatbot/src/npa_chat/llm_client.py`, `prompts/`, `guardrails.py`) |
| Purpose | Phrase replies kindly and in plain language in en/ta/hi around fixed facts |
| Inputs | Conversation state, i18n strings (`npa_chat/i18n/{en,ta,hi}.json`), policy-approved `ReliefOption`s and disclosure texts (`npa_rules/disclosures.py`) |
| Outputs | `BotReply.text` |
| Risk tier | **High**. This is the only free text a customer reads |
| Human oversight / controls | (1) **Numbers come only from the rules engine**: every amount in the reply must equal a field of an offered `ReliefOption` (red-team number-consistency judge). (2) Every reply passes `ComplianceGuard.check_text` (`RBI-454Z-*` lexicon) before sending. (3) Output guardrails in `guardrails.py` block system-prompt leaks and invented products such as a "payment holiday". (4) The recording notice and grievance footer come from `required_footer()` (WS3), not from the LLM. (5) Hardship-officer handoff for zero capacity |
| Monitoring | Red-team pass rate for all six suites (`redteam/reports/RT-*/scorecard.json`), `check_text` block rate, complaint rate per 100 chats |
| Version | `LLM_MODEL` env plus the prompt file revision; temperature 0.2 (A7.5 default) |
| Status | **Planned** (#13–#18) |

### AI-07 Red-team LLM judge

| Field | Value |
|---|---|
| Task / owner | 7.1 · **WS7** (`redteam/src/npa_redteam/judges.py`, `redteam/src/npa_redteam/prompts/judge.md`) |
| Purpose | Score bot replies 1–5 for tone, empathy and truthfulness, as a second opinion after the deterministic checks |
| Inputs | Attack case input, bot reply, the expected properties of the case |
| Outputs | JSON verdict (scores and a short rationale) stored in `RedTeamResult.notes` |
| Risk tier | **Low**. Internal assurance tool; never customer-facing; cannot change an offer |
| Human oversight | Deterministic checks decide pass/fail first. An LLM-judge result can only add a failure, which a person reviews before an issue is filed. Disabled (mocked) in CI; demo runs use a fixed seed and temperature 0 |
| Monitoring | Agreement rate with the deterministic checks; a manual sample review of each demo run |
| Version | `LLM_MODEL` env plus the git revision of `prompts/judge.md` |
| Status | **Planned** (#31) |

### AI-08 Compliance-guard LLM hook (optional)

| Field | Value |
|---|---|
| Task / owner | 3.3 · **WS3** (`packages/rules/src/npa_rules/compliance_guard.py`, `llm_judge` parameter) |
| Purpose | Optional extra check for harsh or misleading text that the regex lexicon misses |
| Risk tier | **Low** while off. **Off by default**; it can only *add* rule IDs (block more), never unblock |
| Status | **In review** (#45); hook only, no LLM wired |

## Controls around the AI (not AI, listed for completeness)

| Component | File | Role as a control | Status |
|---|---|---|---|
| Bank policy | `packages/rules/policies/bank_policy.yaml` | The only source of relief options and amounts; simulates the board-approved policy | In review (#42) |
| Policy loader | `packages/rules/src/npa_rules/policy_loader.py` | Rejects any policy edit that weakens an RBI number or drops a mandatory disclosure (`regulatory_violations`) | In review (#42) |
| Policy engine | `packages/rules/src/npa_rules/policy_engine.py` | `propose_offer` accepts only an `option_id` it issued itself, so an LLM cannot invent an offer | In review (#44) |
| Compliance guard | `packages/rules/src/npa_rules/compliance_guard.py` | Contact window, preferences, occasions, caps, harsh-language lexicon | In review (#45) |
| Next-best-action | `packages/rules/src/npa_rules/nba.py` | Combines model outputs with rules; do-not-contact flags win | In review (#46) |
| Audit log | `services/api/app/audit.py` | Records every contact and decision (RBI para 454P) | Planned (#22) |
| Role checks | `services/api/app/security.py` | Limits who sees which data (RBI para 454O) | Planned (#21) |

## Change control

A new AI component, a new model version used in the demo, or a new `LLM_MODEL` value needs a PR
that updates this register (owner WS7 reviews). The team lead approves it as the simulated board.
