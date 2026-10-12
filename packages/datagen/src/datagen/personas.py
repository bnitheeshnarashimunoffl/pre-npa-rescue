"""Fixed demo personas (task 1.1 step 6): Priya, Ravi and eight more ``CUST-DEMO-*`` customers.

Histories are hand-scripted (payments, spend, salary, shocks) and run through the same
statement engine as everyone else, so every number obeys the same RBI rules. They use a fixed
RNG (``PERSONA_SEED``), so they are identical whatever ``SEED`` is. Persona numbers agreed with
WS3 on issue #1:

* **Priya**: affordable Rs 2,000/month; overdue Rs 11,492 at ``2026-09`` (the 6 x Rs 2,000 plan
  at the policy EMI rate of 15% p.a. covers it); late fee Rs 1,300 + GST = Rs 1,534 (waivable),
  charged on the amount outstanding after the due date (RBI); SMA-0.
* **Ravi**: affordable Rs 0; job-loss insurance; SMA-1.

"Overdue" here is the minimum due on the as-of statement net of the waivable late fee and its
GST: what Priya must pay to be current once the fee is waived. Her 2026-09 part-payment is
solved at build time so that this is exactly Rs 11,492 (asserted in tests).
"""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd

from datagen import dues
from datagen.statements import (
    PAY_AMOUNT,
    PAY_FULL,
    PAY_MIN,
    PAY_NONE,
    PAY_OLDEST,
    PAY_TOTAL_FRAC,
    PURCHASE_CATEGORIES,
    Accounts,
    CycleState,
    PaymentDecision,
    SpendPlan,
    simulate_statements,
)

IntArray = npt.NDArray[np.int64]

PERSONA_SEED = 20_261_012  # fixed on purpose: personas never depend on SEED
AS_OF = "2026-09"
PRIYA_OVERDUE_PAISE = 1_149_200  # Rs 11,492
PRIYA_LATE_FEE_PAISE = 130_000  # Rs 1,300 slab: post-due outstanding above Rs 25,000
PRIYA_AFFORDABLE_PAISE = 200_000  # Rs 2,000 a month

Pay = tuple[int, float, int]  # (mode, frac, late_days)


@dataclass(frozen=True)
class Persona:
    key: str  # CUST-DEMO-<key>
    customer: dict[str, Any]  # customers.parquet columns except the ids
    protected: dict[str, str]
    behaviour: str  # normal | shocked | forgetful | wont_pay
    opening_rupees: int
    bill_day: int
    spend: dict[str, int]  # base monthly rupees per purchase category
    pay_default: Pay
    pay: dict[str, Pay] = field(default_factory=dict)  # cycle month -> payment
    spend_scale: list[tuple[str, str | None, dict[str, float]]] = field(default_factory=list)
    cash: dict[str, int] = field(default_factory=dict)  # month -> rupees of cash advance
    salary_factor: list[tuple[str, str | None, float]] = field(default_factory=list)
    shock: tuple[str, str | None, float, str | None] = ("none", None, 0.0, None)
    wont_pay_start: str | None = None
    facts: dict[str, Any] = field(default_factory=dict)

    @property
    def customer_id(self) -> str:
        return f"CUST-DEMO-{self.key}"

    @property
    def account_id(self) -> str:
        return f"ACC-DEMO-{self.key}"


def _c(**kw: Any) -> dict[str, Any]:
    return kw


PERSONAS: tuple[Persona, ...] = (
    Persona(
        key="PRIYA",
        customer=_c(
            full_name="Priya Subramanian",
            age=29,
            city="Chennai",
            language_pref="ta",
            occupation_type="salaried",
            employer_type="mnc",
            monthly_income_paise=6_500_000,
            dependants=1,
            card_limit_paise=18_000_000,
            card_open_date="2021-03-15",
            has_card_insurance=False,
            insurance_cover_type="none",
            phone_masked="+91-98XXXXX214",
            email_masked="p****@example.com",
            preferred_contact_window=None,
        ),
        protected={
            "gender": "female",
            "religion": "hindu",
            "caste_category": "obc",
            "state": "Tamil Nadu",
            "region": "south",
        },
        behaviour="shocked",
        opening_rupees=60_000,
        bill_day=5,
        spend={
            "essentials": 6_000,
            "discretionary": 4_000,
            "travel": 1_000,
            "utilities": 2_000,
            "emi": 0,
            "other": 1_500,
        },
        pay_default=(PAY_TOTAL_FRAC, 0.22, -4),
        pay={
            "2026-07": (PAY_MIN, 0, -2),
            "2026-08": (PAY_MIN, 0, -1),
            "2026-09": (PAY_AMOUNT, 0, -1),
        },  # 2026-09 amount solved, see _solve_priya
        spend_scale=[("2026-06", None, {"discretionary": 0.35, "travel": 0.0, "other": 0.6})],
        cash={"2026-07": 6_000, "2026-08": 5_000},
        salary_factor=[("2026-06", None, 0.0)],
        shock=("job_loss", "2026-06", 0.55, None),
        facts={
            "story": "IT worker; salary credits stopped in 2026-06; minimum-only payments in "
            "2026-07 and 2026-08, could pay only part of the minimum in 2026-09.",
            "expected_segment": "cant_pay",
            "expected_uplift_group": "persuadable",
            "expected_risk_band": "high",
            "chat_lang": "ta",
            "affordable_monthly_paise": PRIYA_AFFORDABLE_PAISE,
            "declared": {"income_paise": 2_000_000, "expenses_paise": 900_000, "dependants": 1},
            "offer": {
                "type": "emi_conversion",
                "monthly_amount_paise": 200_000,
                "tenure_months": 6,
                "fee_waiver": True,
            },
        },
    ),
    Persona(
        key="RAVI",
        customer=_c(
            full_name="Ravi Kumar",
            age=41,
            city="Madurai",
            language_pref="ta",
            occupation_type="salaried",
            employer_type="private",
            monthly_income_paise=3_500_000,
            dependants=3,
            card_limit_paise=10_000_000,
            card_open_date="2019-07-10",
            has_card_insurance=True,
            insurance_cover_type="job_loss",
            phone_masked="+91-94XXXXX387",
            email_masked="r****@example.com",
            preferred_contact_window="10:00-13:00",
        ),
        protected={
            "gender": "male",
            "religion": "hindu",
            "caste_category": "sc",
            "state": "Tamil Nadu",
            "region": "south",
        },
        behaviour="shocked",
        opening_rupees=45_000,
        bill_day=10,
        spend={
            "essentials": 4_000,
            "discretionary": 2_000,
            "travel": 500,
            "utilities": 1_500,
            "emi": 0,
            "other": 1_000,
        },
        pay_default=(PAY_TOTAL_FRAC, 0.28, -3),
        pay={"2026-07": (PAY_MIN, 0, -1), "2026-08": (PAY_NONE, 0, 0), "2026-09": (PAY_NONE, 0, 0)},
        spend_scale=[("2026-07", None, {"discretionary": 0.2, "travel": 0.0, "other": 0.5})],
        cash={"2026-07": 4_000},
        salary_factor=[("2026-07", None, 0.0)],
        shock=("job_loss", "2026-07", 0.95, None),
        facts={
            "story": "Factory supervisor, sole earner for three dependants; lost his job in "
            "2026-07; no payments since 2026-08; cannot pay even Rs 500.",
            "expected_segment": "cant_pay",
            "expected_uplift_group": "lost_cause",
            "expected_risk_band": "high",
            "chat_lang": "en",
            "affordable_monthly_paise": 0,
            "declared": {"income_paise": 0, "expenses_paise": 0, "dependants": 3},
            "zero_capacity": True,
            "insurance_referral": "job_loss",
            "callback": "hardship officer, 11:00 IST, inside 08:00-19:00 (RBI 454Y(4))",
        },
    ),
    Persona(
        key="ANITA",
        customer=_c(
            full_name="Anita Reddy",
            age=34,
            city="Hyderabad",
            language_pref="en",
            occupation_type="salaried",
            employer_type="mnc",
            monthly_income_paise=12_000_000,
            dependants=2,
            card_limit_paise=30_000_000,
            card_open_date="2018-02-20",
            has_card_insurance=True,
            insurance_cover_type="both",
            phone_masked="+91-99XXXXX508",
            email_masked="a****@example.com",
            preferred_contact_window=None,
        ),
        protected={
            "gender": "female",
            "religion": "hindu",
            "caste_category": "general",
            "state": "Telangana",
            "region": "south",
        },
        behaviour="forgetful",
        opening_rupees=40_000,
        bill_day=15,
        spend={
            "essentials": 12_000,
            "discretionary": 10_000,
            "travel": 4_000,
            "utilities": 3_000,
            "emi": 0,
            "other": 4_000,
        },
        pay_default=(PAY_FULL, 0, -6),
        pay={"2025-12": (PAY_FULL, 0, 6), "2026-09": (PAY_NONE, 0, 0)},
        facts={
            "story": "Pays in full every month; paid six days late once (2025-12) and forgot "
            "the 2026-09 payment.",
            "expected_segment": "forgot",
            "expected_uplift_group": "sure_thing",
            "expected_risk_band": "low",
        },
    ),
    Persona(
        key="VIKRAM",
        customer=_c(
            full_name="Vikram Malhotra",
            age=45,
            city="New Delhi",
            language_pref="hi",
            occupation_type="self_employed",
            employer_type="self",
            monthly_income_paise=22_000_000,
            dependants=2,
            card_limit_paise=40_000_000,
            card_open_date="2017-11-05",
            has_card_insurance=False,
            insurance_cover_type="none",
            phone_masked="+91-98XXXXX662",
            email_masked="v****@example.com",
            preferred_contact_window=None,
        ),
        protected={
            "gender": "male",
            "religion": "hindu",
            "caste_category": "general",
            "state": "Delhi",
            "region": "north",
        },
        behaviour="wont_pay",
        opening_rupees=120_000,
        bill_day=20,
        spend={
            "essentials": 15_000,
            "discretionary": 25_000,
            "travel": 10_000,
            "utilities": 5_000,
            "emi": 8_000,
            "other": 7_000,
        },
        pay_default=(PAY_TOTAL_FRAC, 0.35, -5),
        pay={
            "2026-05": (PAY_MIN, 0, -1),
            "2026-06": (PAY_MIN, 0, -1),
            "2026-07": (PAY_NONE, 0, 0),
            "2026-08": (PAY_NONE, 0, 0),
            "2026-09": (PAY_NONE, 0, 0),
        },
        spend_scale=[("2026-05", None, {"discretionary": 1.8, "travel": 1.5})],
        wont_pay_start="2026-07",
        facts={
            "story": "Income intact; discretionary and travel spend up since 2026-05, "
            "minimum-only, then stopped paying in 2026-07.",
            "expected_segment": "wont_pay",
            "expected_uplift_group": "lost_cause",
            "expected_risk_band": "high",
        },
    ),
    Persona(
        key="MEERA",
        customer=_c(
            full_name="Meera Nair",
            age=38,
            city="Kochi",
            language_pref="en",
            occupation_type="salaried",
            employer_type="government",
            monthly_income_paise=7_000_000,
            dependants=1,
            card_limit_paise=15_000_000,
            card_open_date="2016-06-01",
            has_card_insurance=True,
            insurance_cover_type="death_disability",
            phone_masked="+91-97XXXXX145",
            email_masked="m****@example.com",
            preferred_contact_window="17:00-19:00",
        ),
        protected={
            "gender": "female",
            "religion": "hindu",
            "caste_category": "general",
            "state": "Kerala",
            "region": "south",
        },
        behaviour="normal",
        opening_rupees=60_000,
        bill_day=25,
        spend={
            "essentials": 7_000,
            "discretionary": 3_000,
            "travel": 1_000,
            "utilities": 2_000,
            "emi": 2_000,
            "other": 1_500,
        },
        pay_default=(PAY_TOTAL_FRAC, 0.12, -3),
        pay={
            "2025-08": (PAY_NONE, 0, 0),
            "2025-09": (PAY_MIN, 0, -2),
            "2026-02": (PAY_NONE, 0, 0),
            "2026-03": (PAY_MIN, 0, -2),
            "2026-09": (PAY_NONE, 0, 0),
        },
        facts={
            "story": "Anxious; asked not to be called at work. Skips a payment now and then "
            "and always catches up on her own the next month.",
            "expected_segment": "forgot",
            "expected_uplift_group": "sleeping_dog",
            "expected_risk_band": "medium",
        },
    ),
    Persona(
        key="ARJUN",
        customer=_c(
            full_name="Arjun Rao",
            age=31,
            city="Bengaluru",
            language_pref="en",
            occupation_type="salaried",
            employer_type="mnc",
            monthly_income_paise=15_000_000,
            dependants=0,
            card_limit_paise=35_000_000,
            card_open_date="2020-09-12",
            has_card_insurance=False,
            insurance_cover_type="none",
            phone_masked="+91-90XXXXX733",
            email_masked="a****@example.com",
            preferred_contact_window=None,
        ),
        protected={
            "gender": "male",
            "religion": "hindu",
            "caste_category": "general",
            "state": "Karnataka",
            "region": "south",
        },
        behaviour="normal",
        opening_rupees=150_000,
        bill_day=1,
        spend={
            "essentials": 12_000,
            "discretionary": 15_000,
            "travel": 6_000,
            "utilities": 3_000,
            "emi": 5_000,
            "other": 5_000,
        },
        pay_default=(PAY_TOTAL_FRAC, 0.40, -4),
        pay={"2026-08": (PAY_MIN, 0, -2), "2026-09": (PAY_MIN, 0, -2)},
        spend_scale=[("2026-07", "2026-08", {"discretionary": 2.5, "travel": 2.0})],
        facts={
            "story": "Wedding spend in 2026-07/08 pushed utilisation up; paying the minimum "
            "for two months but never late.",
            "expected_segment": "not_at_risk",
            "expected_uplift_group": "sure_thing",
            "expected_risk_band": "medium",
        },
    ),
    Persona(
        key="FATIMA",
        customer=_c(
            full_name="Fatima Sheikh",
            age=47,
            city="Lucknow",
            language_pref="hi",
            occupation_type="salaried",
            employer_type="government",
            monthly_income_paise=5_500_000,
            dependants=2,
            card_limit_paise=12_000_000,
            card_open_date="2015-04-18",
            has_card_insurance=True,
            insurance_cover_type="death_disability",
            phone_masked="+91-88XXXXX921",
            email_masked="f****@example.com",
            preferred_contact_window="10:00-13:00",
        ),
        protected={
            "gender": "female",
            "religion": "muslim",
            "caste_category": "obc",
            "state": "Uttar Pradesh",
            "region": "north",
        },
        behaviour="shocked",
        opening_rupees=45_000,
        bill_day=10,
        spend={
            "essentials": 6_000,
            "discretionary": 2_500,
            "travel": 500,
            "utilities": 1_500,
            "emi": 0,
            "other": 1_000,
        },
        pay_default=(PAY_TOTAL_FRAC, 0.20, -3),
        pay={
            "2026-05": (PAY_MIN, 0, -1),
            "2026-06": (PAY_MIN, 0, -1),
            "2026-07": (PAY_NONE, 0, 0),
            "2026-08": (PAY_OLDEST, 0, -1),
            "2026-09": (PAY_NONE, 0, 0),
        },
        spend_scale=[
            ("2026-05", "2026-07", {"essentials": 2.2}),
            ("2026-05", None, {"discretionary": 0.4, "travel": 0.0}),
        ],
        cash={"2026-06": 3_000},
        salary_factor=[("2026-06", "2026-07", 0.5)],
        shock=("medical", "2026-05", 0.5, None),
        facts={
            "story": "Teacher; hospital bills on the card from 2026-05 and two months of "
            "half pay (unpaid leave); paying what she can.",
            "expected_segment": "cant_pay",
            "expected_uplift_group": "persuadable",
            "expected_risk_band": "high",
        },
    ),
    Persona(
        key="SURESH",
        customer=_c(
            full_name="Suresh Patel",
            age=52,
            city="Ahmedabad",
            language_pref="en",
            occupation_type="self_employed",
            employer_type="self",
            monthly_income_paise=8_000_000,
            dependants=3,
            card_limit_paise=20_000_000,
            card_open_date="2014-01-25",
            has_card_insurance=False,
            insurance_cover_type="none",
            phone_masked="+91-79XXXXX356",
            email_masked="s****@example.com",
            preferred_contact_window=None,
        ),
        protected={
            "gender": "male",
            "religion": "hindu",
            "caste_category": "obc",
            "state": "Gujarat",
            "region": "west",
        },
        behaviour="shocked",
        opening_rupees=110_000,
        bill_day=5,
        spend={
            "essentials": 8_000,
            "discretionary": 5_000,
            "travel": 2_000,
            "utilities": 3_000,
            "emi": 3_000,
            "other": 3_000,
        },
        pay_default=(PAY_TOTAL_FRAC, 0.15, -3),
        pay={
            "2025-12": (PAY_MIN, 0, -1),
            "2026-01": (PAY_MIN, 0, -1),
            **{
                m: (PAY_NONE, 0, 0)
                for m in (
                    "2026-02",
                    "2026-03",
                    "2026-04",
                    "2026-05",
                    "2026-06",
                    "2026-07",
                    "2026-08",
                    "2026-09",
                )
            },
        },
        spend_scale=[("2025-12", None, {"discretionary": 0.2, "travel": 0.0, "other": 0.5})],
        cash={"2025-12": 8_000, "2026-01": 6_000},
        shock=("business_loss", "2025-12", 0.85, None),
        facts={
            "story": "Shop owner; business collapsed in 2025-12; no payments since 2026-02; NPA.",
            "expected_segment": "cant_pay",
            "expected_uplift_group": "lost_cause",
            "expected_risk_band": "high",
        },
    ),
    Persona(
        key="KAVYA",
        customer=_c(
            full_name="Kavya Joshi",
            age=26,
            city="Pune",
            language_pref="en",
            occupation_type="gig",
            employer_type="platform",
            monthly_income_paise=3_000_000,
            dependants=0,
            card_limit_paise=6_000_000,
            card_open_date="2022-08-08",
            has_card_insurance=False,
            insurance_cover_type="none",
            phone_masked="+91-70XXXXX489",
            email_masked="k****@example.com",
            preferred_contact_window=None,
        ),
        protected={
            "gender": "female",
            "religion": "hindu",
            "caste_category": "general",
            "state": "Maharashtra",
            "region": "west",
        },
        behaviour="shocked",
        opening_rupees=25_000,
        bill_day=15,
        spend={
            "essentials": 4_000,
            "discretionary": 2_000,
            "travel": 500,
            "utilities": 1_000,
            "emi": 0,
            "other": 1_000,
        },
        pay_default=(PAY_TOTAL_FRAC, 0.25, -3),
        pay={
            "2025-11": (PAY_MIN, 0, -1),
            "2025-12": (PAY_NONE, 0, 0),
            "2026-01": (PAY_NONE, 0, 0),
            "2026-02": (PAY_OLDEST, 0, -1),
            "2026-03": (PAY_MIN, 0, -1),
        },
        spend_scale=[("2025-11", "2026-02", {"discretionary": 0.3, "travel": 0.0})],
        shock=("job_loss", "2025-11", 0.7, "2026-03"),
        facts={
            "story": "Delivery partner deactivated 2025-11, back on the platform 2026-03 and "
            "caught up; current since.",
            "expected_segment": "not_at_risk",
            "expected_uplift_group": "sure_thing",
            "expected_risk_band": "low",
        },
    ),
    Persona(
        key="JOSEPH",
        customer=_c(
            full_name="Joseph Fernandes",
            age=36,
            city="Mumbai",
            language_pref="en",
            occupation_type="salaried",
            employer_type="private",
            monthly_income_paise=9_500_000,
            dependants=2,
            card_limit_paise=25_000_000,
            card_open_date="2019-12-01",
            has_card_insurance=True,
            insurance_cover_type="both",
            phone_masked="+91-93XXXXX270",
            email_masked="j****@example.com",
            preferred_contact_window=None,
        ),
        protected={
            "gender": "male",
            "religion": "christian",
            "caste_category": "general",
            "state": "Maharashtra",
            "region": "west",
        },
        behaviour="normal",
        opening_rupees=30_000,
        bill_day=20,
        spend={
            "essentials": 10_000,
            "discretionary": 8_000,
            "travel": 3_000,
            "utilities": 3_000,
            "emi": 0,
            "other": 3_000,
        },
        pay_default=(PAY_FULL, 0, -5),
        facts={
            "story": "Pays in full on time; the healthy control.",
            "expected_segment": "not_at_risk",
            "expected_uplift_group": None,
            "expected_risk_band": "low",
        },
    ),
)


def _in(month: str, start: str, end: str | None) -> bool:
    return month >= start and (end is None or month <= end)


@dataclass
class ScriptedPolicy:
    """Payment policy that replays each persona's script (no randomness)."""

    mode: npt.NDArray[np.int8]  # (n, T)
    frac: npt.NDArray[np.float64]
    late: IntArray
    amount: IntArray

    def __call__(self, st: CycleState) -> PaymentDecision:
        t = st.t
        return PaymentDecision(self.mode[:, t], self.frac[:, t], self.late[:, t], self.amount[:, t])


def _scripts(personas: tuple[Persona, ...], months: list[str]) -> tuple[ScriptedPolicy, SpendPlan]:
    n, t_len = len(personas), len(months)
    mode = np.zeros((n, t_len), dtype=np.int8)
    frac = np.zeros((n, t_len))
    late = np.zeros((n, t_len), dtype=np.int64)
    purchases = np.zeros((n, t_len, len(PURCHASE_CATEGORIES)), dtype=np.int64)
    cash = np.zeros((n, t_len), dtype=np.int64)
    count = np.zeros((n, t_len), dtype=np.int64)
    rng = np.random.default_rng(PERSONA_SEED)
    noise = np.exp(0.08 * rng.standard_normal((n, t_len, len(PURCHASE_CATEGORIES))))
    for i, p in enumerate(personas):
        base_total = sum(p.spend.values())
        for t, m in enumerate(months):
            mode[i, t], frac[i, t], late[i, t] = p.pay.get(m, p.pay_default)
            for k, cat in enumerate(PURCHASE_CATEGORIES):
                scale = 1.0
                for start, end, mult in p.spend_scale:
                    if _in(m, start, end):
                        scale *= mult.get(cat, 1.0)
                rupees = round(p.spend[cat] * scale * noise[i, t, k])
                purchases[i, t, k] = rupees * 100
            cash[i, t] = p.cash.get(m, 0) * 100
            total = purchases[i, t].sum() / 100
            count[i, t] = int(np.clip(round(30 * total / max(base_total, 1)), 1, 60))
    policy = ScriptedPolicy(mode, frac, late, np.zeros((n, t_len), dtype=np.int64))
    return policy, SpendPlan(purchases=purchases, cash_advance=cash, txn_count=count)


def _accounts(personas: tuple[Persona, ...]) -> Accounts:
    return Accounts(
        account_id=np.array([p.account_id for p in personas], dtype=object),
        customer_id=np.array([p.customer_id for p in personas], dtype=object),
        limit=np.array([p.customer["card_limit_paise"] for p in personas], dtype=np.int64),
        bill_day=np.array([p.bill_day for p in personas], dtype=np.int64),
        opening_balance=np.array([p.opening_rupees * 100 for p in personas], dtype=np.int64),
    )


def waivable_charges(late_fee_paise: int) -> int:
    """Late fee plus its GST (bank policy assumption 18%)."""
    return late_fee_paise + dues.gst(late_fee_paise, dues.DEFAULT_POLICY.gst_bp)


def _solve_priya(run: Callable[[int, int], pd.DataFrame], months: list[str]) -> pd.DataFrame:
    """Find Priya's 2026-09 part-payment so her overdue is exactly Rs 11,492."""
    target = PRIYA_OVERDUE_PAISE + waivable_charges(PRIYA_LATE_FEE_PAISE)
    for nudge in range(0, 50):  # rupees added to 2026-09 "other" spend if rounding skips
        amount = 500_000
        seen: set[int] = set()
        while amount not in seen:
            seen.add(amount)
            am = run(amount, nudge)
            row = am[(am["account_id"] == "ACC-DEMO-PRIYA") & (am["month"] == AS_OF)].iloc[0]
            gap = int(row["min_due_paise"]) - target
            if gap == 0:
                return am
            amount += gap
    raise RuntimeError("could not solve Priya's 2026-09 payment")  # pragma: no cover


def build_personas(months: list[str]) -> dict[str, pd.DataFrame]:
    """All persona tables (same columns as the generated tables)."""
    personas = PERSONAS
    accounts = _accounts(personas)
    policy, plan = _scripts(personas, months)
    priya = next(i for i, p in enumerate(personas) if p.key == "PRIYA")
    t_as_of = months.index(AS_OF)
    k_other = PURCHASE_CATEGORIES.index("other")
    spend_frames: dict[str, pd.DataFrame] = {}

    def run(amount: int, nudge: int) -> pd.DataFrame:
        policy.amount[priya, t_as_of] = amount
        purchases = plan.purchases.copy()
        purchases[priya, t_as_of, k_other] += nudge * 100
        p2 = SpendPlan(purchases, plan.cash_advance, plan.txn_count)
        am, spend = simulate_statements(accounts, months, policy, p2)
        spend_frames["spend"] = spend
        return am

    account_months = _solve_priya(run, months)
    monthly_spend = spend_frames["spend"]

    customers = pd.DataFrame(
        [{"customer_id": p.customer_id, "account_id": p.account_id, **p.customer} for p in personas]
    )
    customers["card_open_date"] = pd.to_datetime(customers["card_open_date"])
    for col, dtype in (("age", np.int16), ("dependants", np.int16)):
        customers[col] = customers[col].astype(dtype)
    protected = pd.DataFrame([{"customer_id": p.customer_id, **p.protected} for p in personas])

    salary_rows = []
    for p in personas:
        if p.customer["occupation_type"] != "salaried":
            continue
        for m in months:
            factor = 1.0
            for start, end, f in p.salary_factor:
                if _in(m, start, end):
                    factor = f
            expected = int(p.customer["monthly_income_paise"])
            salary_rows.append(
                {
                    "customer_id": p.customer_id,
                    "month": m,
                    "expected_paise": expected,
                    "credited_paise": int(round(expected * factor / 10_000) * 10_000),
                }
            )
    salary = pd.DataFrame(salary_rows)
    for col in ("expected_paise", "credited_paise"):
        salary[col] = salary[col].astype(np.int64)

    shocks = pd.DataFrame(
        [
            {
                "customer_id": p.customer_id,
                "shock_type": p.shock[0],
                "start_month": p.shock[1],
                "severity": float(p.shock[2]),
                "recovers_month": p.shock[3],
            }
            for p in personas
        ]
    )
    behaviour = pd.DataFrame(
        [
            {
                "customer_id": p.customer_id,
                "behaviour_type": p.behaviour,
                "wont_pay_start_month": p.wont_pay_start,
            }
            for p in personas
        ]
    )
    return {
        "customers": customers,
        "protected": protected,
        "account_months": account_months,
        "monthly_spend": monthly_spend,
        "salary": salary,
        "shocks": shocks,
        "behaviour": behaviour,
    }


def persona_facts(account_months: pd.DataFrame) -> dict[str, dict[str, Any]]:
    """Facts block per persona: story, expectations and the as-of statement numbers."""
    out: dict[str, dict[str, Any]] = {}
    last = account_months[account_months["month"] == AS_OF].set_index("account_id")
    for p in PERSONAS:
        row = last.loc[p.account_id]
        fee = int(row["late_fee_paise"])
        waivable = waivable_charges(fee)
        facts = dict(p.facts)
        facts.update(
            {
                "as_of_month": AS_OF,
                "dpd": int(row["dpd"]),
                "bucket": str(row["bucket"]),
                "total_due_paise": int(row["total_due_paise"]),
                "min_due_paise": int(row["min_due_paise"]),
                "late_fee_paise": fee,
                "waivable_charges_paise": waivable,
                # Past due only: what must be paid to be current once the fee is waived.
                "overdue_paise": int(row["min_due_paise"]) - waivable if row["dpd"] > 0 else 0,
            }
        )
        out[p.customer_id] = facts
    return out


def to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    """JSON-ready rows: dates as ``YYYY-MM-DD``, timestamps as ISO 8601 with offset."""
    out = df.copy()
    for col in out.columns:
        if isinstance(out[col].dtype, pd.DatetimeTZDtype):
            out[col] = out[col].map(lambda v: v.isoformat())
        elif pd.api.types.is_datetime64_any_dtype(out[col]):
            out[col] = out[col].dt.strftime("%Y-%m-%d").where(out[col].notna(), None)
    records: list[dict[str, Any]] = json.loads(out.to_json(orient="records"))
    return records


def write_json(doc: dict[str, Any], path: Path) -> None:
    """Deterministic JSON (sorted keys, UTF-8, LF)."""
    text = json.dumps(doc, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
