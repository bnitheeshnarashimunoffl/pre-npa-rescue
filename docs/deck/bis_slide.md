# BIS slide — copy-ready content

## Title

17 Indian Standards (14 standard families) mapped to system evidence

## On-slide grid

| Control area | Relevant Indian Standards | Where evidence lives |
|---|---|---|
| **Govern the AI** | IS/ISO/IEC 42001:2023; 23894:2023; 38507:2022 | AI and risk registers; named owners; monitoring; human approval log |
| **Prove fairness and quality** | IS/ISO/IEC TR 24027:2021; TS 4213; 25059:2023; 22989:2022; 23053:2022; 8183:2023 | Bias swaps; model reports; robustness checks; common lifecycle vocabulary; data lineage |
| **Protect customer data** | IS/ISO/IEC 27001:2022; 27002:2022 | Role access, minimised data, audit records, encryption and incident controls |
| **Treat customers well** | IS/ISO 10002:2018; 18295-1:2017; 18295-2:2017 | Complaint docket and escalation; shared service measures across bot and human channels |
| **Include everyone** | IS 17802 Part 1:2021; Part 2:2022 | Keyboard and screen-reader support, contrast, multilingual plain language and accessibility tests |

**Footer:** 17 Indian Standards (14 standard families). Design alignment, not certification.

## Visual direction

Use five equal bands with one icon each: governance, quality, security, service and inclusion.
Keep identifiers readable. Evidence should be a verb phrase, not a paragraph. Do not reproduce
copyrighted standards text.

## Speaker notes

The standards are not a logo wall. Each area maps to an artifact or test: governance records,
model and fairness reports, security controls, complaint handling, contact-centre measures and
accessible interaction. IS/ISO/IEC 22989 and 23053 also give the architecture consistent terms
for AI system, ML model, training data, inference and human oversight.

The mapping contains 17 Indian Standards (14 standard families) across five areas. Use WS7’s
committed mapping as the authority for exact Indian editions. Never describe this prototype as
certified.

## Evidence

- Architecture vocabulary and boundaries: `docs/architecture.md`.
- Contract evidence: `contracts/schemas/Complaint.schema.json`,
  `contracts/schemas/KpiReport.schema.json`, `contracts/schemas/Scorecard.schema.json`.
- Current fixture examples: `contracts/fixtures/scorecard.json`,
  `contracts/fixtures/complaint.json`.
- Final evidence and exact grouping: `TBD – from governance/bis_mapping.md`.
- Model evidence: `TBD – from packages/models/reports/metrics.json`.
- Accessibility evidence: `TBD – from apps/web/` tests and screenshots.

## Pre-export verification

- Check every identifier and edition against `governance/bis_mapping.md`.
- Replace broad implementation phrases with links to committed artifacts and tests.
- Confirm the rendered slide says “17 Indian Standards (14 standard families)”.
- Retain the non-certification footnote on the rendered slide.
