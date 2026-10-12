# RBI requirements mapping

**Owner:** WS7 · **Source for:** the scorecard's `rbi_coverage` (task 7.2) · **Last reviewed:** 2026-10-12

> **Design alignment, not certification.** This is a prototype for an Indian **commercial
> bank** using synthetic data. RBI Responsible Business Conduct (RBC) Directions para 454, as
> amended by the Fourth Amendment Directions 2026, **takes effect on 1 January 2027** and applies
> to commercial banks; we build to it ahead of time. The FREE-AI report contains
> **recommendations, not binding rules**.

## Requirement IDs

- IDs owned by **WS3** are the stable rule IDs returned in `ComplianceDecision.rule_ids` by
  `packages/rules/src/npa_rules/compliance_guard.py` (rule table in `packages/rules/README.md`).
- IDs owned by **WS7** (marked ◆) name requirements that are enforced by policy data, arithmetic
  or process rather than by a single guard rule. They are used only in the scorecard and
  `redteam/src/npa_redteam/mappings.yaml`.
- Tests named below live in `packages/rules/tests/` unless a path is given. They are in WS3's open
  PRs #40–#46, so the status is **In review** until they merge.

## Summary

| ID | Requirement (paraphrased) | Source | Status |
|---|---|---|---|
| ◆ `RBI-CC-NPA-90` | Card account is an NPA when the minimum due is unpaid for more than 90 days from the due date | RBI card asset-classification circular, 16 Jul 2015 | In review (#40) |
| ◆ `RBI-CC-PAST-DUE-3D` | Report "past due" and levy late charges only after more than 3 days past due; DPD counted from the due date | Credit Card Directions 2025 | In review (#40) |
| ◆ `RBI-CC-LATE-FEE-BASE` | Late charges only on the amount outstanding after the due date; no interest on fees, charges or taxes; no negative amortisation | Credit Card Directions 2025 | In review (#40) |
| ◆ `RBI-CC-BUREAU-NOTICE` | Tell the cardholder before reporting a default; update the bureau within 30 days of settlement | Credit Card Directions 2025 | Partial (#42) |
| ◆ `RBI-454D-DISTRESS` | Structured framework for financial distress: documented engagement before escalation; guidance on resolution options | RBC para 454D | Partial (#44, #46; chatbot #16) |
| `RBI-454Y4-WINDOW` | Contact only 08:00–19:00 | RBC para 454Y(4) | In review (#45) |
| `RBI-454Y4-PREF` | Honour the borrower's request to avoid certain times | RBC para 454Y(4) | In review (#45) |
| `RBI-454Y6-OCCASION` | Avoid bereavement, medical emergencies and similar occasions | RBC para 454Y(6) | In review (#45) |
| `RBI-454Z4-EXCESSIVE` | No excessive calling or messaging | RBC para 454Z | In review (#45) |
| `RBI-454Z-ABUSIVE` | No abusive language | RBC para 454Z | In review (#45) |
| `RBI-454Z-THREAT` | No threats or minatory language | RBC para 454Z | In review (#45) |
| `RBI-454Z-THIRD-PARTY` | No harassing relatives, colleagues or others | RBC para 454Z | In review (#45) |
| `RBI-454Z-SHAMING` | No public or social-media shaming | RBC para 454Z | In review (#45) |
| `RBI-454Z-MISLEADING` | No false or misleading statements about the debt or the consequences of non-payment | RBC para 454Z(8) | In review (#42, #45) |
| ◆ `RBI-454Z-ANONYMOUS` | No anonymous calls | RBC para 454Z | Partial |
| ◆ `RBI-454P-RECORDING` | Log time and number of calls; record content; keep 6 months; tell the borrower the call is recorded | RBC para 454P | Partial (#45, #39, #22) |
| ◆ `RBI-454Q-INCENTIVES` | Recovery targets and incentives must not encourage harsh practices | RBC para 454Q | In review (#46) |
| ◆ `RBI-454O-DATA` | Share borrower data with staff or agents only as far as recovery needs | RBC para 454O | Planned (#21) |
| ◆ `RBI-454AA-GRIEVANCE` | Grievance officer name, email, phone and address on every recovery communication; Ombudsman after 30 days | RBC para 454AA; Credit Card Directions | In review (#45) |
| ◆ `RBI-PF2019-RESTRUCTURE` | Restructuring only under board-approved policy; a restructured standard account is downgraded to NPA | Prudential Framework, 7 Jun 2019 | In review (#42, #44) |
| ◆ `RBI-CS2023-SETTLEMENT` | Settlement only under board-approved policy; payment over more than 3 months counts as restructuring; at least 12 months' cooling period | Compromise Settlement Framework, 8 Jun 2023 | In review (#42, #43) |
| ◆ `DPDP-2023` | Consent, purpose limitation, data minimisation, breach notice | DPDP Act 2023, DPDP Rules 2025 | Partial (see `data_lifecycle.md`) |
| ◆ `RBI-FREEAI-GOV` | Board-approved AI policy, AI inventory, explainability, consumer protection | FREE-AI report, Aug 2025 (non-binding) | Partial (this folder) |
| ◆ `BANK-POLICY-ONLY` | Every relief option must exist in the board-approved policy (our ground rule, derived from the Prudential and Settlement frameworks) | Prudential Framework 2019; Settlement Framework 2023 | In review (#44) |

## Detail

### Dues, classification and credit reporting

| ID | Implementing code | Tests | Caveats |
|---|---|---|---|
| `RBI-CC-NPA-90` | `NPA_DPD = 90`, `bucket_for_dpd` in `packages/contracts/src/npa_contracts/constants.py` (**on `main`**); `dues.is_npa`, `dues.bucket` in `npa_rules/dues.py` | `packages/contracts/tests/test_constants_enums.py` (on `main`); `test_npa_only_after_ninety_days`, `test_npa_iff_bucket_npa`, `test_bucket_boundaries` | — |
| `RBI-CC-PAST-DUE-3D` | `PAST_DUE_GRACE_DAYS = 3` (constants, on `main`); `dues.days_past_due`, `dues.is_past_due` | `test_past_due_needs_more_than_three_days`, `test_days_past_due_counts_from_due_date`, `test_no_late_fee_within_grace` | No real bureau reporting; the flag drives disclosures only |
| `RBI-CC-LATE-FEE-BASE` | `dues.late_fee` (slabs on post-due outstanding), `dues.interest_for_period`, `dues.minimum_amount_due` | `test_late_fee_uses_post_due_outstanding_slab`, `test_late_fee_properties`, `test_mad_no_negative_amortisation`, `test_mad_covers_charges_plus_principal_share` | The slab amounts are **bank policy assumptions** in `bank_policy.yaml`, not RBI numbers |
| `RBI-CC-BUREAU-NOTICE` | `credit_bureau.notify_before_default_report` and `update_after_settlement_days ≤ 30` in `bank_policy.yaml`, cross-checked by `policy_loader.regulatory_violations` | `test_rbi_cross_checks` | **Partial:** the policy enforces the setting, but no code path sends the pre-reporting notice yet. The chatbot must not promise "no bureau impact" (red-team `misleading_consequences`) |

### Financial distress (para 454D)

| ID | Implementing code | Tests | Caveats |
|---|---|---|---|
| `RBI-454D-DISTRESS` | Zero-capacity path: `PolicyEngine.relief_options` returns insurance referral, restructuring or settlement (officer) and `review_date`, never an EMI (`npa_rules/policy_engine.py`). NBA routes to `HARDSHIP_OFFICER` (`npa_rules/nba.py`). Chatbot zero-capacity flow `npa_chat/flows/zero_capacity.py` stops asking and books a callback | `test_ravi_zero_capacity_set_insurance_first`, `test_ravi_gets_hardship_officer`; red-team `pressure` cases ("I can't pay anything", then no further ask) | **Partial:** documented engagement before escalation depends on the audit log (#22) and the chatbot (#16) |

### Contact rules (para 454Y)

| ID | Implementing code | Tests | Caveats |
|---|---|---|---|
| `RBI-454Y4-WINDOW` | `ComplianceGuard.check_contact`, window from `bank_policy.yaml` cross-checked against `CONTACT_WINDOW` (constants, on `main`); evaluated in Asia/Kolkata | `test_contact_window_in_ist`, `test_window_evaluated_in_ist_even_for_utc_input`, `test_early_morning_next_is_same_day`; red-team `contact_rules` at 07:59, 19:01 and 23:00 IST | Customer-initiated (inbound) chat is allowed at any hour (`INBOUND-ALLOWED`); the window restricts outbound recovery contact |
| `RBI-454Y4-PREF` | `check_contact` with `avoid_contact_windows` from the account snapshot; `preferred_contact_window` in `customers.parquet` | `test_customer_quiet_time_preference`, `test_next_allowed_combines_rules` | — |
| `RBI-454Y6-OCCASION` | `do_not_contact_flags: [bereavement, medical_emergency, customer_requested_pause]`; no `next_allowed_at` until an officer clears the flag | `test_do_not_contact_flags`, `test_do_not_contact_flag_wins` (NBA) | Flags are set by staff or distress detection (#16); there is no automatic medical or bereavement detection outside chat |

### Harsh practices (para 454Z)

| ID | Implementing code | Tests | Caveats |
|---|---|---|---|
| `RBI-454Z4-EXCESSIVE` | `check_contact` caps: 2/day, 6/rolling 7 days, 180-minute gap (`bank_policy.yaml` → `contact`) | `test_daily_cap`, `test_weekly_cap`, `test_min_gap_between_attempts`, `test_inbound_history_does_not_count` | RBI does not set numbers; **the caps are bank policy assumptions** |
| `RBI-454Z-ABUSIVE`, `-THREAT`, `-THIRD-PARTY`, `-SHAMING` | `ComplianceGuard.check_text` with `packages/rules/policies/compliance_lexicon.yaml` (en, hi, ta, romanised) | `test_harsh_text_blocked`, `test_kind_text_allowed`, `test_our_own_disclosures_and_footer_pass`; red-team `pressure` suite | A lexicon is a floor, not a ceiling: paraphrases can slip through, so the LLM tone judge runs on demo runs and the `llm_judge` hook exists |
| `RBI-454Z-MISLEADING` | Same lexicon (jail, family liable, property seizure, "never get a loan"); mandatory disclosures in `npa_rules/disclosures.py` | `test_harsh_text_blocked`, `test_disclosures_never_make_banned_promises`, `test_restructuring_disclosure_text_is_the_briefed_wording`; red-team `misleading_consequences` suite | ta/hi disclosures are flagged `needs_review` |
| `RBI-454Z-ANONYMOUS` | Every `ContactEvent` carries `actor` and `channel`; the bot identifies itself as the bank's assistant; the footer names the bank | Red-team case planned | **Partial:** no voice channel in the prototype |

### Records, incentives and data sharing

| ID | Implementing code | Tests | Caveats |
|---|---|---|---|
| `RBI-454P-RECORDING` | Recording notice in `required_footer()` (`compliance_guard.py`); `ContactEvent.recorded_notice_given`; `chat_turns` and `contact_events` tables retained 180 days (`CALL_RECORD_RETENTION_DAYS`, on `main`; ORM in #39); `services/api/app/audit.py` (#22) | `test_footer_has_grievance_officer_recording_and_ombudsman` | **Partial:** the purge job and the audit writer are not built yet |
| `RBI-454Q-INCENTIVES` | Collector queue priority = expected benefit (`p_roll_forward × uplift`), not "ease of extraction"; nothing rewards contact volume (`npa_rules/nba.py` `priority`) | `test_queue_priorities` | No agent incentive scheme is modelled |
| `RBI-454O-DATA` | Role-minimised `GET /customers/{id}`; `CustomerContextProvider.context` (no protected attributes, masked contact details); masked columns in `customers` (#39) | Red-team `privacy_extraction` (ID enumeration returns 404) | **Planned:** the bootstrap API has no auth yet (#21) |

### Grievance (para 454AA)

| ID | Implementing code | Tests | Caveats |
|---|---|---|---|
| `RBI-454AA-GRIEVANCE` | `grievance_officer` in `bank_policy.yaml`; `PolicyProvider.grievance_officer()`; `required_footer()` adds name, email, phone, address and the Ombudsman route after `COMPLAINT_SLA_DAYS = 30`; `Complaint.sla_due_at` | `test_footer_has_grievance_officer_recording_and_ombudsman`; red-team check that every bot reply carries the footer or a grievance quick reply | Officer details are fictional (`gro@demobank.example`) |

### Resolution frameworks

| ID | Implementing code | Tests | Caveats |
|---|---|---|---|
| `RBI-PF2019-RESTRUCTURE` | `options.restructuring` in `bank_policy.yaml` with the mandatory NPA-downgrade disclosure; always `requires_human_approval` (loader cross-check) | `test_restructuring_disclosure_text_is_the_briefed_wording`, `test_propose_offer_needs_human`, `test_rbi_cross_checks` | The upgrade after satisfactory performance is disclosed, not simulated |
| `RBI-CS2023-SETTLEMENT` | `options.compromise_settlement`; `MIN_SETTLEMENT_COOLING_MONTHS = 12`, `SETTLEMENT_RESTRUCTURING_THRESHOLD_MONTHS = 3` (constants, on `main`); `relief_calc.size_settlement` | `test_cooling_period_constant_matches_policy`, `test_npa_settlement_sized_within_window`, `test_settlement_sacrifice_within_cap` | — |
| `BANK-POLICY-ONLY` | `PolicyEngine.propose_offer` accepts only issued option IDs | `test_propose_unknown_option_rejected`, `test_disabled_option_never_offered`; red-team `prompt_injection` | — |

### Data protection and AI governance

| ID | Implementing code / document | Evidence | Caveats |
|---|---|---|---|
| `DPDP-2023` | `governance/data_lifecycle.md`; protected-attribute separation; masking; retention | Document; red-team `privacy_extraction` | Synthetic data means no real data principals; consent capture is designed, not built |
| `RBI-FREEAI-GOV` | `governance/ai_register.md`, `governance/risk_register.md`, reason codes (`npa_models/reason_codes.yaml`) | Documents | Non-binding recommendations; the "board" is the team lead |

## Not implemented (honest gaps)

- No real credit-bureau integration, so the pre-reporting notice is a policy setting and a
  disclosure, not a sent message.
- No field visits, voice calls or recovery-agent empanelment, so the parts of para 454 on agents
  are out of scope.
- Para 454 is not yet in force (effective 1 Jan 2027); the citations follow the amendment as
  summarised in the project briefing and have not been checked against the final gazetted text.
