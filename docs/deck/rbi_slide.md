# RBI slide — copy-ready content

## Title

RBI requirements become product controls

## On-slide grid

| Requirement | How the system enforces it |
|---|---|
| **Credit-card NPA boundary** | DPD starts at the statement due date; minimum due unpaid for 90 days reaches the NPA boundary. |
| **Past-due and late-charge timing** | Rules apply the more-than-3-day grace and calculate charges only on post-due outstanding. |
| **Contact safeguards** | Compliance checks allow contact only from 08:00–19:00 Asia/Kolkata and respect customer time restrictions. |
| **No harsh or misleading practices** | Text and contact checks block pressure, threats, shaming, third-party harassment and false consequences. |
| **Recorded engagement** | Contact events preserve time, channel, content, recording notice, rule decision and outcome. |
| **Financial distress** | Zero capacity stops payment pressure and routes the customer to policy-defined options and human support. |
| **Restructuring and settlement** | Board-policy eligibility, human approval and mandatory consequence disclosures gate presentation. |
| **Grievance and privacy** | Communications provide grievance details; role-minimised data and audit boundaries limit data exposure. |

**Footer:** Paragraph 454 controls are designed for the RBI directions effective 1 January
2027. This prototype is not a legal-compliance certification.

## Visual direction

Use a two-column grid with “RBI requirement” on the left and “enforcement point” on the right.
Draw a thin line from each enforcement point to Policy, Compliance, Human oversight or Audit.
The future-effective badge must remain visible beside paragraph 454 rows.

## Speaker notes

The differentiator is enforcement inside the workflow. Before contact, the compliance provider
checks channel, time and customer preferences. Before a message leaves, text is checked for
harsh or misleading content. Offers originate in simulated bank policy and require human
approval where specified. Contacts and approvals are designed to be auditable.

Do not say paragraph 454 is already in force. Do not imply a restructuring is harmless: the
required customer disclosure must explain the regulatory consequence. Do not claim production
compliance until WS7’s mapping and the integrated test evidence are committed.

## Evidence

- Current contract evidence: `packages/contracts/src/npa_contracts/constants.py`,
  `contracts/schemas/ComplianceDecision.schema.json`,
  `contracts/schemas/ContactEvent.schema.json`, `contracts/schemas/ReliefOption.schema.json`,
  `contracts/schemas/Complaint.schema.json`.
- Fixture examples: `contracts/fixtures/bot_reply_zero_capacity.json`,
  `contracts/fixtures/complaint.json`, `contracts/fixtures/policy.json`.
- Final mapping: `TBD – from governance/rbi_mapping.md`.

## Pre-export verification

- Confirm exact RBI titles, paragraph identifiers and effective dates against WS7’s mapping.
- Confirm implemented controls against WS3, WS4 and WS5 tests.
- Remove any row that lacks evidence rather than presenting planned behaviour as shipped.
