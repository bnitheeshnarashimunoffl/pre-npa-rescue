# BIS standards mapping

**Owner:** WS7 · **Source for:** WS8's BIS slide (task 8.2) and the scorecard's `bis_coverage`
(task 7.2) · **Last reviewed:** 2026-10-12

> **Design alignment, not certification.** Each standard is described in our own words. We
> claim only that the listed design choices address the standard's themes. Nothing has been
> audited.

## Summary (for the BIS slide)

| Area | Indian Standards | What we do | Status |
|---|---|---|---|
| **Govern the AI** | IS/ISO/IEC 42001:2023 · IS/ISO/IEC 23894:2023 with IS/ISO 31000:2018 · IS/ISO/IEC 38507:2022 · IS/ISO/IEC 22989:2022 · IS/ISO/IEC 23053:2022 | AI register with owners and oversight points; 18-risk register; *the AI proposes, the rules decide*: every relief offer comes from the board-approved policy and big decisions need a human | Documents in place; controls in review |
| **Prove it is fair and accurate** | IS/ISO/IEC TR 24027:2021 · IS/ISO/IEC TS 4213 · IS/ISO/IEC 25059:2023 | Bias-swap red-team tests (same story, swapped name, gender, religion, caste, region, language must give the same offer); model report cards with fairness metrics | Planned |
| **Protect customer data** | IS/ISO/IEC 27001:2022 · IS/ISO/IEC 27002:2022 · IS/ISO/IEC 8183:2023 | Synthetic data only; protected attributes in a separate table that models never read; masked phone and email; role checks; audit log; 180-day retention; prompt-injection and privacy red-team suites | Partial |
| **Treat customers well** | IS/ISO 10002:2018 · IS/ISO 18295-1:2017 · IS/ISO 18295-2:2017 | Complaint docket with a 30-day route to the RBI Ombudsman; grievance officer on every message; the same service rules for bot and human agents; contact-centre KPIs | Partial (in review) |
| **Include everyone** | IS 17802 (Part 1):2021 · IS 17802 (Part 2):2022 | Tamil, Hindi and English everywhere; screen-reader and keyboard support; plain language | Planned |

Status as of 2026-10-12: WS3's rules are in open PRs #40–#46; WS2 (models), WS4 (chatbot), WS6
(web) and WS7's harness have not shipped. The vocabulary is defined in [README.md](README.md).

## Detail per standard

### Govern the AI

#### IS/ISO/IEC 42001:2023: AI management system

| | |
|---|---|
| Themes addressed | Defining the scope and context of the AI system; leadership accountability and an AI policy; planning based on risks and impacts; documented roles and competence; controls across the AI life cycle; evaluating performance; improving after incidents and findings |
| How | Scope and context: `governance/README.md`. AI inventory, owners, oversight and monitoring: `governance/ai_register.md`. Risk planning: `governance/risk_register.md`. Simulated board-approved policy: `packages/rules/policies/bank_policy.yaml`. Change control: PRs with CODEOWNERS (`.github/CODEOWNERS`). Improvement loop: red-team failures filed as `bug` + `redteam` issues and re-tested |
| Evidence | This folder; `redteam/reports/RT-*/` (after #31); issue history |
| Status | **Partial**: documents are done, operational evidence (red-team runs) is planned |

#### IS/ISO/IEC 23894:2023 with IS/ISO 31000:2018: AI risk management

| | |
|---|---|
| Themes addressed | Applying the generic risk process (identify, analyse, evaluate, treat, monitor, communicate) to AI-specific sources of risk such as bias, opacity, lack of robustness and misuse |
| How | `governance/risk_register.md`: 18 risks with likelihood × impact, controls linked to code and tests, residual risk and owner. Monitoring through red-team runs and model reports |
| Evidence | `governance/risk_register.md`; controls' tests in `packages/rules/tests/` (#40–#46) |
| Status | **Partial**: the register is done; residual risks are targets until controls merge |

#### IS/ISO/IEC 38507:2022: governance implications of AI use

| | |
|---|---|
| Themes addressed | The governing body remains accountable for decisions made with AI; setting limits on what AI may decide alone; keeping human oversight where the impact on people is high |
| How | The AI never creates an offer: `PolicyEngine.propose_offer` (`packages/rules/src/npa_rules/policy_engine.py`) accepts only option IDs it issued. Restructuring and settlement always set `requires_human_approval = true`, enforced by `policy_loader.py`. The approval is recorded in `Offer.approved_by` and `POST /offers/{id}/approve`. Zero-capacity customers go to a human hardship officer |
| Evidence | `test_propose_unknown_option_rejected`, `test_propose_offer_needs_human`, `test_ravi_gets_hardship_officer` (#44, #46); approval log in the `audit_log` table (#22) |
| Status | **In review** (#44, #46); approval log planned (#22) |

#### IS/ISO/IEC 22989:2022 and IS/ISO/IEC 23053:2022: AI concepts and ML framework

| | |
|---|---|
| Themes addressed | Shared vocabulary for AI systems and stakeholders; describing an ML system as data → training → model → deployment → monitoring |
| How | `governance/ai_register.md` uses these terms (AI component, model, inputs and outputs, human oversight, monitoring). The ML life cycle is visible in the code layout: `packages/datagen/` (data) → `packages/models/` (training, `registry.py`) → `services/api/` (deployment) → `packages/models/reports/` (monitoring). WS8's `docs/architecture.md` (#36) uses the same terms |
| Evidence | `governance/ai_register.md`; `docs/architecture.md` (planned) |
| Status | **Partial** |

### Prove it is fair and accurate

#### IS/ISO/IEC TR 24027:2021: bias in AI systems

| | |
|---|---|
| Themes addressed | Where unwanted bias comes from (data, design, human); measuring it with group metrics; reducing it across the life cycle |
| How | Protected attributes kept apart from features (`contracts/data/protected_attributes.md`). WS2 group fairness metrics (`packages/models/src/npa_models/fairness.py` → `packages/models/reports/metrics.json`). WS7 `bias_swap` suite (`redteam/cases/bias_swap/`): paired conversations and paired synthetic accounts that differ only in protected attributes must get the same offer type, amount, tenure, next action and eligibility. Synthetic-data bias is a named risk (R12) |
| Evidence | `redteam/reports/RT-*/scorecard.json` bias section; model card fairness tables |
| Status | **Planned** (#6, #8, #31) |

#### IS/ISO/IEC TS 4213: assessing ML classification performance

| | |
|---|---|
| Themes addressed | Reporting classifier performance with suitable, clearly defined metrics and their uncertainty, on a held-out test set, including per-class results |
| How | Model report cards for the early-warning and segmentation models in `packages/models/reports/` (task 2.5): ROC-AUC, PR-AUC, calibration, confusion matrix at the chosen threshold, per-class precision and recall, time-based split |
| Evidence | `packages/models/reports/*.md` and `metrics.json` |
| Status | **Planned** (#8) |

#### IS/ISO/IEC 25059:2023: quality model for AI systems

| | |
|---|---|
| Themes addressed | Quality characteristics specific to AI, such as user controllability, transparency, functional adaptability, robustness and intervenability |
| How | Transparency: reason codes in three languages (`npa_models/reason_codes.yaml`). Controllability and intervenability: hardship-officer handoff, human approval, and admin policy updates validated by `policy_loader.regulatory_violations`. Robustness: the `prompt_injection` and `pressure` red-team suites. Correctness: hypothesis property tests on dues (`packages/rules/tests/test_dues.py`) |
| Evidence | Tests in #40–#46; red-team runs |
| Status | **Partial** (in review) |

### Protect customer data

#### IS/ISO/IEC 27001:2022 and IS/ISO/IEC 27002:2022: information security

| | |
|---|---|
| Themes addressed | A risk-based security management system, plus controls for access, cryptography, logging, secure development, supplier (LLM API) use and incident response |
| How | Access control: JWT and roles (`services/api/app/security.py`, #21), with 404 on another customer's ID. Logging: `services/api/app/audit.py` (#22). Secure development: CI with ruff, mypy, tests and a gitleaks secret scan (`.github/workflows/ci.yml`); no secrets in git (`.env.example` has an empty `ANTHROPIC_API_KEY`). Supplier: the LLM goes through the `LLMClient` protocol and receives a minimised context with no protected attributes. Red-team `privacy_extraction` and `prompt_injection` suites |
| Evidence | CI config on `main`; red-team runs (planned) |
| Status | **Partial**: CI and secret scan are in place; auth, audit and the red-team suites are planned |

#### IS/ISO/IEC 8183:2023: data life cycle framework

| | |
|---|---|
| Themes addressed | Managing data through every stage: idea, collection or creation, preparation, use, sharing, storage, retention and disposal |
| How | `governance/data_lifecycle.md` covers every stage for our synthetic data, with seeds, file paths, access roles and retention |
| Evidence | `governance/data_lifecycle.md` |
| Status | **Partial**: the document is done; deletion jobs are planned (#22) |

### Treat customers well

#### IS/ISO 10002:2018: complaints handling

| | |
|---|---|
| Themes addressed | Making it easy to complain; acknowledging every complaint with a reference; tracking and escalating it; responding within a stated time; learning from complaints |
| How | Complaint flow `packages/chatbot/src/npa_chat/flows/complaint.py` (#17). `ComplaintSink.open` returns a docket `CMP-YYYYMMDD-NNNN` with `sla_due_at` = created + 30 days (`COMPLAINT_SLA_DAYS` in `npa_contracts/constants.py`). Escalation through `ComplaintStatus` and `escalation_level` (`PATCH /complaints/{docket_no}`). Grievance officer details and the Ombudsman route in `required_footer()` (`npa_rules/compliance_guard.py`) |
| Evidence | `test_footer_has_grievance_officer_recording_and_ombudsman` (#45); `contracts/fixtures/complaint.json` |
| Status | **Partial**: footer in review; complaint flow planned |

#### IS/ISO 18295-1:2017 and IS/ISO 18295-2:2017: customer contact centres

| | |
|---|---|
| Themes addressed | Part 1: service requirements for the contact centre (staff, process, performance measures). Part 2: what the client organisation must provide and set out for the contact centre |
| How | The same compliance guard and lexicon apply to bot and human agents (`ComplianceGuard.check_contact` / `check_text`). Contact-window and cap rules. KPIs at `GET /metrics/kpis` (`KpiReport` schema). Clear handoff from bot to human (`Callback`, hardship officer). The bank's requirements on the contact centre are the policy file (`bank_policy.yaml`) |
| Evidence | `contracts/schemas/KpiReport.schema.json`; compliance guard tests (#45) |
| Status | **Partial** (in review; KPIs planned in #19) |

### Include everyone

#### IS 17802 (Part 1):2021 and IS 17802 (Part 2):2022: ICT accessibility

| | |
|---|---|
| Themes addressed | Part 1: accessibility requirements for ICT products and services. Part 2: how to test and determine conformance with them |
| How | WS6: shadcn/ui on Radix primitives, keyboard access and visible focus, contrast, `@axe-core/playwright` checks in e2e (`apps/web/e2e/`), next-intl for en/ta/hi (task 6.6). Bot texts in plain language in three languages (`npa_chat/i18n/`) |
| Evidence | axe reports from Playwright runs; screenshots |
| Status | **Planned** (#29) |

## How the scorecard uses this file

`redteam/src/npa_redteam/mappings.yaml` (task 7.2) lists, for each standard string above, its
evidence: red-team case IDs and/or governance documents. `bis_coverage[standard]` is true only if
at least one piece of evidence exists and, for test evidence, passed in the run. A standard with
only planned evidence shows as not covered.
