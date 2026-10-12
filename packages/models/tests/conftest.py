"""Seeded fake features/labels/protected attributes for tests (briefing B6).

Stand-in until WS1 ships ``data/samples/*.parquet``. Columns follow ``contracts/data`` (A7.2,
A7.2.1). Risk is driven by a hidden per-account hardship shock so models have signal to learn,
and the demo personas (Priya, Ravi) are included with stories matching A1.
"""

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd
import pytest

from npa_contracts.constants import AS_OF_MONTH, DEFAULT_SEED, SIM_START_MONTH

MONTHS: list[str] = (
    pd.period_range(SIM_START_MONTH, AS_OF_MONTH, freq="M").strftime("%Y-%m").tolist()
)
OCCUPATIONS = ("salaried", "self_employed", "gig", "retired", "student")
REGIONS = {
    "Tamil Nadu": "south",
    "Uttar Pradesh": "north",
    "West Bengal": "east",
    "Maharashtra": "west",
    "Assam": "northeast",
    "Madhya Pradesh": "central",
}


@dataclass(frozen=True)
class FakeData:
    features: pd.DataFrame
    labels: pd.DataFrame
    protected: pd.DataFrame


@dataclass(frozen=True)
class _Account:
    account_id: str
    customer_id: str
    occupation: str
    dependants: int
    shock_t: int | None  # month index when hardship starts (hidden truth)
    shock_len: int  # months until recovery (like WS1's recovers_month)
    habit: str  # "normal" | "forgetful" | "strategic"


def _accounts(n: int, rng: np.random.Generator) -> list[_Account]:
    out = []
    for i in range(1, n + 1):
        habit = rng.choice(["normal", "forgetful", "strategic"], p=[0.84, 0.08, 0.08])
        shock = int(rng.integers(0, len(MONTHS))) if rng.random() < 0.15 else None
        out.append(
            _Account(
                account_id=f"ACC-{i:06d}",
                customer_id=f"CUST-{i:06d}",
                occupation=str(rng.choice(OCCUPATIONS, p=[0.55, 0.2, 0.15, 0.05, 0.05])),
                dependants=int(rng.integers(0, 4)),
                shock_t=shock,
                shock_len=int(rng.integers(4, 11)),
                habit=str(habit),
            )
        )
    last = len(MONTHS) - 1
    # Priya: salary stopped ~3 months ago, paying only the minimum (A1).
    out.append(_Account("ACC-DEMO-PRIYA", "CUST-DEMO-PRIYA", "salaried", 1, last - 2, 99, "normal"))
    # Ravi: lost his job earlier, sole earner with dependants, already past due.
    out.append(_Account("ACC-DEMO-RAVI", "CUST-DEMO-RAVI", "salaried", 3, last - 5, 99, "normal"))
    return out


def make_fake_data(n_accounts: int = 1000, seed: int = DEFAULT_SEED) -> FakeData:
    """Return a deterministic monthly panel of ``n_accounts`` (+2 personas) over 24 months."""
    rng = np.random.default_rng(seed)
    feats: list[dict[str, object]] = []
    labels: list[dict[str, object]] = []
    for acc in _accounts(n_accounts, rng):
        limit = int(rng.choice([50_000, 100_000, 200_000, 500_000])) * 100
        base_util = float(rng.uniform(0.05, 0.6))
        tenure0 = int(rng.integers(6, 120))
        for t, month in enumerate(MONTHS):
            in_shock = acc.shock_t is not None and acc.shock_t <= t < acc.shock_t + acc.shock_len
            k = t - acc.shock_t + 1 if in_shock and acc.shock_t is not None else 0
            salaried = acc.occupation == "salaried"
            salary_missing = min(k, 3) if salaried else 0
            streak = min(k, 6) if k else int(acc.habit == "strategic") * int(rng.integers(0, 4))
            dpd = 0
            if k > 3:
                dpd = min(30 * (k - 3), 120)
            elif acc.habit == "forgetful" and rng.random() < 0.25:
                dpd = int(rng.integers(1, 15))
            elif acc.habit == "strategic" and rng.random() < 0.3:
                dpd = int(rng.integers(5, 45))
            util = float(np.clip(base_util + 0.08 * k + rng.normal(0, 0.03), 0, 1.2))
            feats.append(
                {
                    "account_id": acc.account_id,
                    "customer_id": acc.customer_id,
                    "month": month,
                    "limit_paise": limit,
                    "utilisation": util,
                    "utilisation_delta_3m": 0.08 * min(k, 3) + float(rng.normal(0, 0.02)),
                    "min_due_only_streak": streak,
                    "months_since_full_payment": streak + int(rng.integers(0, 2)),
                    "payment_ratio_3m": float(
                        max(0.0, (1.1 - 0.25 * k) if k else rng.normal(3, 1))
                    ),
                    "dpd": dpd,
                    "max_dpd_6m": dpd + int(rng.integers(0, 10)) * int(dpd > 0),
                    "broken_streak_flag": dpd > 0,
                    "cash_advance_ratio_3m": (0.1 + 0.05 * min(k, 3)) if k else 0.02,
                    "essentials_spend_delta_3m": (0.2 if k else 0.0) + float(rng.normal(0, 0.05)),
                    "discretionary_spend_delta_3m": (-0.3 if k else 0.0)
                    + float(rng.normal(0, 0.05)),
                    "txn_count_delta_3m": (-0.2 if k else 0.0) + float(rng.normal(0, 0.05)),
                    "salary_missing_months_3m": salary_missing,
                    "salary_delta_3m": -salary_missing / 3,
                    "income_to_due_ratio": float(max(0.1, rng.normal(8, 2) - 2 * min(k, 3))),
                    "tenure_months": tenure0 + t,
                    "dependants": acc.dependants,
                    "occupation_type": acc.occupation,
                }
            )
            logit = -3.5 + 0.5 * streak + 0.7 * salary_missing + 0.03 * dpd + 2.0 * (util > 0.9)
            rolls = bool(rng.random() < 1 / (1 + np.exp(-logit)))
            if not rolls:
                segment = "not_at_risk"
            elif k:
                segment = "cant_pay"
            elif acc.habit == "forgetful":
                segment = "forgot"
            else:
                segment = "wont_pay"
            labels.append(
                {
                    "account_id": acc.account_id,
                    "month": month,
                    "rolls_forward_60d": rolls,
                    "reaches_npa_90d": rolls and (dpd >= 30 or bool(rng.random() < 0.2)),
                    "segment_truth": segment,
                }
            )
    features = pd.DataFrame(feats)
    for col in (
        "min_due_only_streak",
        "months_since_full_payment",
        "salary_missing_months_3m",
        "tenure_months",
        "dependants",
    ):
        features[col] = features[col].astype("int16")
    for col in ("dpd", "max_dpd_6m"):
        features[col] = features[col].astype("int32")
    features["limit_paise"] = features["limit_paise"].astype("int64")

    customers = features["customer_id"].unique()
    states = rng.choice(list(REGIONS), size=len(customers))
    protected = pd.DataFrame(
        {
            "customer_id": customers,
            "gender": rng.choice(
                ["female", "male", "other"], size=len(customers), p=[0.45, 0.5, 0.05]
            ),
            "religion": rng.choice(
                ["hindu", "muslim", "christian", "sikh", "other"], size=len(customers)
            ),
            "caste_category": rng.choice(["general", "obc", "sc", "st"], size=len(customers)),
            "state": states,
            "region": [REGIONS[s] for s in states],
        }
    )
    return FakeData(features=features, labels=pd.DataFrame(labels), protected=protected)


@pytest.fixture(scope="session")
def fake_data() -> FakeData:
    return make_fake_data()


@pytest.fixture(scope="session")
def fake_data_factory() -> Callable[..., FakeData]:
    return make_fake_data
