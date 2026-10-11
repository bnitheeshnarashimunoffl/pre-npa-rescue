# `demo_personas.json`

- **Producer:** WS1 (`packages/datagen/src/datagen/personas.py`)
- **Contract version:** 0.1.0

Full histories for the fixed demo customers, keyed by `customer_id`:

| customer_id | account_id | Story |
|---|---|---|
| `CUST-DEMO-PRIYA` | `ACC-DEMO-PRIYA` | Salary stopped; minimum-only payments for 3 months; high risk, `cant_pay`, `persuadable`; Tamil; accepts Rs 2,000 x 6 with late fees waived |
| `CUST-DEMO-RAVI` | `ACC-DEMO-RAVI` | Job loss, sole earner, cannot pay even Rs 500; zero-capacity path, insurance referral, hardship-officer callback at 11:00 IST |

Each entry holds the persona's rows from every table above (same column names), so tests can rebuild the demo without the full dataset.
