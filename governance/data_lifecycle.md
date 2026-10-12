# Data life cycle

**Owner:** WS7 (document); WS1 (data), WS5 (storage) · **Supports:** IS/ISO/IEC 8183:2023 (data
life cycle framework), DPDP Act 2023 and DPDP Rules 2025, RBI RBC para 454O and 454P ·
**Last reviewed:** 2026-10-12 · **Design alignment, not certification.**

> **All data is synthetic.** No real person's data is collected, generated from real records,
> stored or processed. Where this document talks about consent or deletion, it describes the
> design a real deployment would need, and says so.

## Stages

| # | Stage | What happens | Where | Owner | Status |
|---|---|---|---|---|---|
| 1 | Idea / purpose | Purpose fixed: predict pre-NPA stress, choose who to help, offer policy-approved relief, prove fairness. Data is used only for these purposes (DPDP purpose limitation) | `governance/README.md`, A1 of the briefing | Team lead | Done |
| 2 | Creation | Synthetic generator, seeded (`SEED=42`, `np.random.default_rng(seed)`), Faker `en_IN` names. Optional calibration of distributions from a public dataset (UCI credit-card default) | `packages/datagen/src/datagen/` (`calibrate_uci.py`, `customers.py`, `protected.py`, `statements.py`, `transactions.py`, `salary.py`, `shocks.py`, `personas.py`) | WS1 | Planned (#1) |
| 3 | Preparation | Feature pipeline and labels; schema validation with pandera against `contracts/data/*.md` | `datagen/features.py`, `labels.py`, `validate.py` | WS1 | Planned (#2) |
| 4 | Use | Model training and scoring (WS2); rules and offers (WS3); chat (WS4); red-team bias tests (WS7) | `packages/models/`, `packages/rules/`, `packages/chatbot/`, `redteam/` | WS2–WS4, WS7 | Planned / in review |
| 5 | Storage | Parquet in `DATA_DIR` (`./data/generated`, gitignored); PostgreSQL 16 tables (ORM `services/api/app/orm.py`); small samples (≤ 5 MB) in `data/samples/` | see below | WS1, WS5 | Partial (#39) |
| 6 | Sharing | Only through the API with role checks; the LLM receives a minimised context; no export to third parties except the LLM provider for chat text | `services/api/`, `CustomerContextProvider` | WS5, WS4 | Planned (#19, #21) |
| 7 | Retention | Chat and contact records 180 days; complaints until closed plus 180 days; others for the demo's life | see below | WS5 | Planned (#22) |
| 8 | Disposal | Generated data rebuilt from seed at will; DB tables truncated on reseed; purge job for expired records | `make seed`, `services/api/seed/` | WS5 | Planned (#20, #22) |

## Datasets

| File (`DATA_DIR`) | Contains personal-like data? | Protected attributes? | Used by | Spec |
|---|---|---|---|---|
| `customers.parquet` | Yes (synthetic names, age, city, income; masked phone and email) | No | WS2 (non-name fields), WS3, WS4 via context, WS5 | `contracts/data/customers.md` |
| `protected_attributes.parquet` | Yes (synthetic) | **Yes**: `gender`, `religion`, `caste_category`, `state`, `region` | **Only** WS2 `fairness.py` (evaluation) and WS7 `bias_swap` | `contracts/data/protected_attributes.md` |
| `account_months.parquet`, `transactions.parquet`, `salary_credits.parquet` | Financial history (synthetic) | No | WS1 features, WS3 dues, WS5 | `contracts/data/` |
| `shocks.parquet` | Hidden ground truth (job loss, medical, bereavement) | No | WS1 labels only | `contracts/data/shocks.md` |
| `features.parquet`, `labels.parquet` | Derived | **Must not** contain any protected column | WS2 | `contracts/data/features.md`, `labels.md` |
| `experiment.parquet` | Simulated treatment and outcome | No | WS2 uplift, `GET /metrics/simulation` | `contracts/data/experiment.md` |
| `demo_personas.json` | Priya and Ravi (fictional) | No | Demo, WS3 personas, WS4 | `contracts/data/demo_personas.md` |

## Protected-attribute separation

1. WS1 writes protected attributes to **their own file**, `protected_attributes.parquet`, keyed by
   `customer_id`. They are never columns of `customers.parquet` or `features.parquet`.
2. Models never read them as features (briefing A3, engineering rule 1). WS2 asserts this in
   training (request in #4); WS7 adds a red-team check that `features.parquet` has no protected
   column (risk R16).
3. `CustomerContextProvider.context` returns no protected attributes, so neither the chatbot nor
   the LLM provider ever sees them.
4. In Postgres they sit in a separate `protected_attributes` table (#39) that no API route reads.
   Fairness reporting (WS2, WS7) reads the Parquet file offline, and only aggregate metrics are
   published.
5. Names can act as a proxy for gender, religion or caste. Models do not use `full_name`; the
   `bias_swap` suite swaps names on purpose to test the chatbot.

## Access by role

| Role (`npa_contracts.enums.Role`) | Can see |
|---|---|
| `customer` | Own profile (masked contact details), own offers, own chat transcript, own complaints |
| `collector` | Queue items, account summaries, risk reasons. No protected attributes, no chat content beyond summaries |
| `hardship_officer` | The above plus chat transcripts and affordability declarations for assigned callbacks |
| `admin` | Policy file, red-team runs, user management |
| `auditor` | Contact log, transcripts, red-team results, fairness reports (read only) |

Enforced in `services/api/app/security.py` (task 5.3, #21). RBI para 454O: share data with staff
only as far as recovery needs. Phone and email are stored masked (`phone_masked`,
`email_masked`) and masked again in logs (A9 security rule).

## Retention and deletion

| Record | Retention | Basis | Mechanism |
|---|---|---|---|
| Chat turns (`chat_turns`), contact events (`contact_events`) | **180 days** (`CALL_RECORD_RETENTION_DAYS`) | RBI RBC para 454P (keep records 6 months) | Purge job (planned, #22) |
| Complaints (`complaints`) | Until closed, then 180 days | IS/ISO 10002:2018 traceability | Purge job (planned) |
| Audit log (`audit_log`) | 180 days | 454P; IS/ISO/IEC 27001 logging | Purge job (planned) |
| Red-team runs (`redteam/reports/`) | Kept in git (synthetic, no personal data) | Evidence for the scorecard | Git history |
| Generated Parquet | Recreated from seed; never committed | Data minimisation | `.gitignore` covers `data/generated/` |
| Model artifacts | Current and previous version | Reproducibility | `MODEL_DIR`, gitignored |

**Real-deployment note (DPDP):** a live system would also need recorded consent per purpose, a way
for a data principal to request erasure (balanced against the 454P retention duty), and a breach
notice process to the Data Protection Board and affected people. These are **not built** in the
prototype because there are no real data principals.

## Determinism and lineage

- The same `SEED` and `DATAGEN_N_CUSTOMERS` give byte-identical outputs (A7.0). CI uses 2,000
  customers; the full demo uses 5,00,000.
- Every model output carries `model_version`; every red-team result carries `run_id`
  (`RT-YYYYMMDD-HHMM`). Together with the git commit, any number in the demo can be traced back
  to the code and seed that produced it.

## Public dataset attribution

The generator may calibrate distributions against the public **UCI "Default of Credit Card
Clients"** dataset. Only fitted parameters are used and the raw download (`data/raw/`) is
gitignored. Licence and credits are recorded by WS1 in `data/ATTRIBUTION.md`, **which does not
exist yet** (planned with task 1.1, #1). This section will link to it once it is merged.
