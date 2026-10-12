"""Synthetic customer population (``customers.parquet``, task 1.1 step 2).

Income is tied to occupation and city tier. Card limits follow the UCI log-normal limit fit,
rescaled by ratio so the median limit is Rs 1,50,000, and are linked to income through a
Gaussian copula so the income-to-limit relation stays plausible. Names come from Faker
``en_IN`` name pools drawn with the seeded numpy RNG. No real personal data.
"""

from datetime import date
from typing import Any

import numpy as np
import pandas as pd
from faker import Faker

from datagen.protected import STATES

OCCUPATIONS = {
    "salaried": 0.55,
    "self_employed": 0.20,
    "gig": 0.15,
    "retired": 0.05,
    "student": 0.05,
}
# Median monthly income in rupees by occupation (assumption), times a city-tier multiplier.
INCOME_MEDIAN_INR = {
    "salaried": 60_000,
    "self_employed": 65_000,
    "gig": 28_000,
    "retired": 38_000,
    "student": 15_000,
}
TIER_MULTIPLIER = {1: 1.30, 2: 1.00, 3: 0.80}
INCOME_LOG_SIGMA = 0.45
INCOME_LIMIT_RHO = 0.8  # copula correlation between log income and log limit
LIMIT_TO_INCOME_BOUNDS = (1.0, 8.0)  # limit kept within 1x-8x monthly income
LIMIT_ROUND_INR = 5_000
MIN_LIMIT_INR = 10_000

EMPLOYER_TYPES = {
    "salaried": {"private": 0.55, "mnc": 0.20, "government": 0.15, "psu": 0.10},
    "self_employed": {"self": 1.0},
    "gig": {"platform": 1.0},
}
AGE_RANGES = {
    "salaried": (22, 60),
    "self_employed": (24, 65),
    "gig": (21, 45),
    "retired": (58, 65),
    "student": (21, 25),
}
DEPENDANTS_P = (0.25, 0.25, 0.25, 0.17, 0.08)  # 0..4
INSURANCE_SHARE = 0.35
INSURANCE_TYPES = {"job_loss": 0.40, "death_disability": 0.35, "both": 0.25}
CONTACT_WINDOWS = ("08:00-10:00", "10:00-13:00", "14:00-17:00", "17:00-19:00")  # RBI 454Y(6)
CONTACT_WINDOW_SHARE = 0.2
PHONE_PREFIXES = ("98", "97", "96", "95", "94", "93", "90", "89", "88", "87", "79", "70", "63")
HINDI_BELT = {
    "Uttar Pradesh",
    "Bihar",
    "Madhya Pradesh",
    "Rajasthan",
    "Haryana",
    "Delhi",
    "Jharkhand",
    "Chhattisgarh",
    "Uttarakhand",
}
NAME_POOL_SIZE = 500


def _choice(rng: np.random.Generator, dist: dict[str, float], n: int) -> np.ndarray:
    keys = list(dist)
    p = np.array(list(dist.values()), dtype=float)
    return np.array(keys, dtype=object)[rng.choice(len(keys), size=n, p=p / p.sum())]


def _name_pools(seed: int) -> dict[str, list[str]]:
    fake = Faker("en_IN")
    fake.seed_instance(seed)
    return {
        "male": [fake.first_name_male() for _ in range(NAME_POOL_SIZE)],
        "female": [fake.first_name_female() for _ in range(NAME_POOL_SIZE)],
        "last": [fake.last_name() for _ in range(NAME_POOL_SIZE)],
    }


def language_for_state(state: str, u: float) -> str:
    """Tamil Nadu -> ``ta`` ~70%; Hindi-belt states -> ``hi`` ~65%; otherwise ``en``."""
    if state == "Tamil Nadu":
        return "ta" if u < 0.70 else "en"
    if state in HINDI_BELT:
        return "hi" if u < 0.65 else "en"
    return "en"


def generate_customers(
    protected: pd.DataFrame,
    calibration: dict[str, Any],
    start_month: str,
    rng: np.random.Generator,
    *,
    seed: int,
) -> pd.DataFrame:
    """Build ``customers`` aligned row-by-row with ``protected`` (same customer order)."""
    n = len(protected)
    states = protected["state"].to_numpy()
    gender = protected["gender"].to_numpy()

    # City and tier from the state.
    city = np.empty(n, dtype=object)
    tier = np.empty(n, dtype=np.int64)
    u_city = rng.random(n)
    for state, (_, _, cities) in STATES.items():
        idx = np.flatnonzero(states == state)
        pick = (u_city[idx] * len(cities)).astype(int)
        city[idx] = [cities[k][0] for k in pick]
        tier[idx] = [cities[k][1] for k in pick]

    occupation = _choice(rng, OCCUPATIONS, n)
    lo = np.array([AGE_RANGES[o][0] for o in occupation])
    hi = np.array([AGE_RANGES[o][1] for o in occupation])
    age = (lo + np.floor(rng.beta(2.0, 3.0, n) * (hi - lo + 1))).astype(np.int16)

    # Income (log-normal by occupation and tier) and limit (UCI log-normal) via a copula.
    z_income = rng.standard_normal(n)
    z_limit = INCOME_LIMIT_RHO * z_income + np.sqrt(1 - INCOME_LIMIT_RHO**2) * rng.standard_normal(
        n
    )
    median = np.array([INCOME_MEDIAN_INR[o] for o in occupation], dtype=float)
    median *= np.array([TIER_MULTIPLIER[t] for t in tier])
    income_inr = median * np.exp(INCOME_LOG_SIGMA * z_income)
    income_paise = (np.round(income_inr / 100) * 100 * 100).astype(np.int64)  # nearest Rs 100

    lim = calibration["limit"]
    limit_inr = lim["target_median_inr"] * np.exp(lim["log_sigma"] * z_limit)
    lo_b, hi_b = LIMIT_TO_INCOME_BOUNDS
    limit_inr = np.clip(limit_inr, lo_b * income_inr, hi_b * income_inr)
    limit_inr = np.maximum(np.round(limit_inr / LIMIT_ROUND_INR) * LIMIT_ROUND_INR, MIN_LIMIT_INR)
    limit_paise = (limit_inr * 100).astype(np.int64)

    employer = np.full(n, None, dtype=object)
    for occ, dist in EMPLOYER_TYPES.items():
        idx = np.flatnonzero(occupation == occ)
        employer[idx] = _choice(rng, dist, idx.size)

    dependants = rng.choice(len(DEPENDANTS_P), size=n, p=DEPENDANTS_P).astype(np.int16)
    dependants[occupation == "student"] = 0

    # Card opened 6-120 months before the window starts, so every account has full history.
    start = date.fromisoformat(f"{start_month}-01").toordinal()
    open_ord = start - rng.integers(6 * 30, 120 * 30, n)
    card_open = pd.to_datetime(
        [date.fromordinal(int(o)).isoformat() for o in open_ord], format="%Y-%m-%d"
    )

    insured = rng.random(n) < INSURANCE_SHARE
    cover = np.where(insured, _choice(rng, INSURANCE_TYPES, n), "none").astype(object)

    u_lang = rng.random(n)
    language = [language_for_state(s, u) for s, u in zip(states, u_lang, strict=True)]

    pools = _name_pools(seed)
    first_idx = rng.integers(0, NAME_POOL_SIZE, n)
    last_idx = rng.integers(0, NAME_POOL_SIZE, n)
    first_m = rng.random(n) < 0.5  # first-name pool for non_binary customers
    first = [
        pools["female"][i] if g == "female" or (g == "non_binary" and not m) else pools["male"][i]
        for g, i, m in zip(gender, first_idx, first_m, strict=True)
    ]
    full_name = [f"{f} {pools['last'][j]}" for f, j in zip(first, last_idx, strict=True)]

    prefix = np.array(PHONE_PREFIXES, dtype=object)[rng.integers(0, len(PHONE_PREFIXES), n)]
    tail = rng.integers(0, 1000, n)
    phone = [f"+91-{p}XXXXX{t:03d}" for p, t in zip(prefix, tail, strict=True)]
    email = [f"{f[0].lower()}****@example.com" for f in first]

    has_window = rng.random(n) < CONTACT_WINDOW_SHARE
    window = np.array(CONTACT_WINDOWS, dtype=object)[rng.integers(0, len(CONTACT_WINDOWS), n)]
    window[~has_window] = None

    ids = protected["customer_id"].to_list()
    return pd.DataFrame(
        {
            "customer_id": ids,
            "account_id": [c.replace("CUST-", "ACC-") for c in ids],
            "full_name": full_name,
            "age": age,
            "city": city,
            "language_pref": language,
            "occupation_type": occupation,
            "employer_type": employer,
            "monthly_income_paise": income_paise,
            "dependants": dependants,
            "card_limit_paise": limit_paise,
            "card_open_date": card_open,
            "has_card_insurance": insured,
            "insurance_cover_type": cover,
            "phone_masked": phone,
            "email_masked": email,
            "preferred_contact_window": window,
        }
    )
