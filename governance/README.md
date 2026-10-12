# governance/

**Owner:** WS7 (Red team & compliance) · **Task:** 7.3 (issue #33) · **Last reviewed:** 2026-10-12

> **Design alignment, not certification.** Pre-NPA Rescue is a hackathon prototype. These
> documents show how its design lines up with RBI directions and with Indian Standards (BIS)
> adopted from ISO/IEC. No part of the system has been audited or certified against any
> standard, and nothing here should be read as a claim of conformity.

## Scope

| Item | In scope |
|---|---|
| Regulated entity simulated | An Indian **commercial bank** issuing credit cards ("Demo Bank Ltd"), the entity class that RBI Responsible Business Conduct Directions para 454 applies to |
| Effective dates | Para 454 (as amended by the Fourth Amendment Directions 2026) takes effect **1 January 2027**. We build to it ahead of time; today's date is 2026-10-12 |
| Data | **Synthetic data only** (WS1 generator, seed 42). No real customer data is collected, stored or processed |
| Product | Credit-card collections before day 90 (pre-NPA): early warning, uplift targeting, policy-gated relief offers, hardship chatbot, red-team scorecard |
| Out of scope | Loan products other than cards, field recovery agents, real credit-bureau reporting, real payments |

## Documents

| File | What it is | Standard(s) it supports |
|---|---|---|
| [`ai_register.md`](ai_register.md) | Inventory of every AI/ML component: purpose, inputs, outputs, owner, risk tier, human oversight, monitoring, version | IS/ISO/IEC 42001:2023, IS/ISO/IEC 38507:2022; RBI FREE-AI (AI inventory) |
| [`risk_register.md`](risk_register.md) | 18 risks with likelihood, impact, controls linked to code and tests, residual risk, owner | IS/ISO/IEC 23894:2023, IS/ISO 31000:2018 |
| [`bis_mapping.md`](bis_mapping.md) | Every BIS standard in the briefing: themes addressed, implementing files, evidence, status; summary table for the BIS slide | All BIS standards in the briefing (A3) |
| [`rbi_mapping.md`](rbi_mapping.md) | Every RBI requirement we implement: rule ID, code, tests, status, caveats | RBI directions listed in A3 |
| [`data_lifecycle.md`](data_lifecycle.md) | Synthetic data creation, protected-attribute separation, storage, access, retention, deletion, attribution | IS/ISO/IEC 8183:2023; DPDP Act 2023 and DPDP Rules 2025 |

## Status vocabulary (used in every table)

| Status | Meaning |
|---|---|
| **Evidenced** | Code is merged to `main` and a test or committed report proves the behaviour |
| **In review** | Code exists in an open pull request (number given) but is not merged yet |
| **Planned** | Assigned to a task issue; no code yet |
| **Partial** | Some of the requirement is covered; the gap is stated |
| **Gap** | Not covered by this prototype; stated honestly |

These statuses are a snapshot. WS7 updates them as PRs merge, and the compliance scorecard
(task 7.2, `redteam/src/npa_redteam/scorecard.py`) reads the same mapping to compute
`rbi_coverage` and `bis_coverage`, so the scorecard and these documents cannot silently diverge.

## Conventions

- BIS standards are always written in their human-readable form, for example
  `IS/ISO/IEC 42001:2023`. The scorecard (`contracts/fixtures/scorecard.json`) uses the same form.
- RBI requirement IDs are WS3's rule IDs where code enforces them (for example
  `RBI-454Y4-WINDOW`, defined in `packages/rules/src/npa_rules/compliance_guard.py`), otherwise
  WS7 IDs (for example `RBI-CC-BUREAU-NOTICE`). The full list is in `rbi_mapping.md`.
- Standards are described in our own words. We do not reproduce text from BIS or ISO
  publications.
- Owners are workstreams (WS1 to WS8, see the CODEOWNERS table in `docs/setup.md`). The team lead
  (@bnitheeshnarashimunoffl) acts as the "board" that approves the simulated bank policy and these
  documents.
