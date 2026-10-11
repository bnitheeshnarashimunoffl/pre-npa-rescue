# `customers.parquet`

- **Producer:** WS1 (`packages/datagen`), written to `$DATA_DIR/customers.parquet`
- **Key:** `customer_id`
- **Contract version:** 0.1.0

One row per synthetic customer. Minimised profile; no protected attributes.

| Column | Type | Notes |
|---|---|---|
| `customer_id` | string | `CUST-000001` or `CUST-DEMO-*` |
| `account_id` | string | `ACC-000001`; one card account per customer |
| `full_name` | string | synthetic (Faker `en_IN`) |
| `age` | int16 | 18-80 |
| `city` | string |  |
| `language_pref` | string | `en` / `ta` / `hi` (Lang) |
| `occupation_type` | string | `salaried` / `self_employed` / `gig` / `retired` / `student` |
| `employer_type` | string | nullable |
| `monthly_income_paise` | int64 (paise, >= 0) |  |
| `dependants` | int16 | >= 0 |
| `card_limit_paise` | int64 (paise, >= 0) |  |
| `card_open_date` | date `YYYY-MM-DD` |  |
| `has_card_insurance` | bool |  |
| `insurance_cover_type` | string | `none` / `job_loss` / `death_disability` / `both` |
| `phone_masked` | string | e.g. `+91-98XXXXXX21`; never a real number |
| `email_masked` | string | e.g. `p****@example.com` |
| `preferred_contact_window` | string | nullable, e.g. `10:00-13:00` (RBI para 454Y(6)) |

Conventions (A7.0): money is int64 paise, never float; timestamps UTC; months `YYYY-MM`.
