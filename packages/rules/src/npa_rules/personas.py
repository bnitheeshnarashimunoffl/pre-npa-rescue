"""Demo personas (A1) as the rules engine sees them: Priya and Ravi.

These are WS3's proposed numbers for WS1's personas (``packages/datagen`` personas must match
them; see the README section "Demo personas"). Tests, the fixture generator and other
workstreams' tests can import them; production code never does.

Priya: Rs 1,10,000 outstanding is not affordable as an EMI, so the plan covers the overdue
amount (Rs 11,492) with late charges (Rs 1,180) waived: Rs 2,000/month for 6 months at the
policy EMI rate of 15% p.a. (task 3.2 demo requirement).
"""

from npa_rules.relief_calc import AccountSnapshot

__all__ = ["PRIYA", "PRIYA_DECLARED", "RAVI", "RAVI_DECLARED"]

PRIYA = AccountSnapshot(
    customer_id="CUST-DEMO-PRIYA",
    account_id="ACC-DEMO-PRIYA",
    dpd=12,
    total_outstanding_paise=11_000_000,  # Rs 1,10,000
    overdue_paise=1_149_200,  # Rs 11,492 unpaid minimum dues
    waivable_charges_paise=118_000,  # Rs 1,000 late fee + 18% GST
    monthly_income_paise=6_500_000,
    recent_income_paise=0,  # salary credits stopped
    avg_payment_3m_paise=550_000,  # paid only the minimum for 3 months
    dependants=1,
    has_card_insurance=False,
)
PRIYA_DECLARED: dict[str, int | None] = {
    "income_paise": 2_000_000,  # Rs 20,000 (freelance work after job loss)
    "expenses_paise": 900_000,  # Rs 9,000 essentials
    "dependants": 1,
}  # -> (20,000 - 9,000 - 3,000) x 0.3 = Rs 2,400/month affordable

RAVI = AccountSnapshot(
    customer_id="CUST-DEMO-RAVI",
    account_id="ACC-DEMO-RAVI",
    dpd=45,
    total_outstanding_paise=6_480_000,  # Rs 64,800
    overdue_paise=900_000,
    waivable_charges_paise=118_000,
    monthly_income_paise=3_500_000,
    recent_income_paise=0,
    avg_payment_3m_paise=0,
    dependants=3,
    has_card_insurance=True,
    insurance_cover_type="job_loss",
)
RAVI_DECLARED: dict[str, int | None] = {"income_paise": 0, "expenses_paise": 0, "dependants": 3}
