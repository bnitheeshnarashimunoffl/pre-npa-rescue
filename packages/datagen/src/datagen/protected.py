"""Protected attributes (gender, religion, caste category, state, region).

Stored **only** in ``protected_attributes.parquet`` and used only for bias evaluation (A3).
Each attribute is drawn independently, and independently of the hardship process, so any bias a
model shows is learned, not baked into the data (IS/ISO/IEC TR 24027:2021). ``state`` also
drives the customer's city and language, which is how real Indian card data looks.
"""

import numpy as np
import pandas as pd

# state -> (region, population weight, [(city, tier), ...]); weights are rough shares of
# Indian card holders (assumption, documented in data/README.md).
STATES: dict[str, tuple[str, float, list[tuple[str, int]]]] = {
    "Maharashtra": ("west", 0.14, [("Mumbai", 1), ("Pune", 1), ("Nagpur", 2), ("Nashik", 3)]),
    "Karnataka": ("south", 0.10, [("Bengaluru", 1), ("Mysuru", 2), ("Hubballi", 3)]),
    "Tamil Nadu": (
        "south",
        0.09,
        [("Chennai", 1), ("Coimbatore", 2), ("Madurai", 2), ("Tiruchirappalli", 3)],
    ),
    "Delhi": ("north", 0.08, [("New Delhi", 1)]),
    "Uttar Pradesh": ("north", 0.08, [("Lucknow", 2), ("Noida", 1), ("Kanpur", 2), ("Agra", 3)]),
    "Telangana": ("south", 0.07, [("Hyderabad", 1), ("Warangal", 3)]),
    "Gujarat": ("west", 0.07, [("Ahmedabad", 1), ("Surat", 2), ("Vadodara", 2), ("Rajkot", 3)]),
    "West Bengal": ("east", 0.06, [("Kolkata", 1), ("Siliguri", 3), ("Durgapur", 3)]),
    "Kerala": ("south", 0.05, [("Kochi", 2), ("Thiruvananthapuram", 2), ("Kozhikode", 3)]),
    "Haryana": ("north", 0.04, [("Gurugram", 1), ("Faridabad", 2)]),
    "Rajasthan": ("north", 0.04, [("Jaipur", 2), ("Jodhpur", 3), ("Udaipur", 3)]),
    "Madhya Pradesh": ("central", 0.04, [("Indore", 2), ("Bhopal", 2), ("Gwalior", 3)]),
    "Andhra Pradesh": ("south", 0.03, [("Visakhapatnam", 2), ("Vijayawada", 2)]),
    "Punjab": ("north", 0.03, [("Ludhiana", 2), ("Amritsar", 3), ("Mohali", 2)]),
    "Bihar": ("east", 0.02, [("Patna", 2), ("Gaya", 3)]),
    "Odisha": ("east", 0.02, [("Bhubaneswar", 2), ("Cuttack", 3)]),
    "Chhattisgarh": ("central", 0.01, [("Raipur", 2)]),
    "Jharkhand": ("east", 0.01, [("Ranchi", 2), ("Jamshedpur", 2)]),
    "Assam": ("northeast", 0.01, [("Guwahati", 2)]),
    "Uttarakhand": ("north", 0.01, [("Dehradun", 2)]),
}

GENDER = {"male": 0.62, "female": 0.37, "non_binary": 0.01}
RELIGION = {
    "hindu": 0.79,
    "muslim": 0.14,
    "christian": 0.023,
    "sikh": 0.017,
    "buddhist": 0.007,
    "jain": 0.004,
    "other": 0.019,
}
CASTE_CATEGORY = {"general": 0.30, "obc": 0.41, "sc": 0.19, "st": 0.10}


def _draw(rng: np.random.Generator, dist: dict[str, float], n: int) -> np.ndarray:
    keys = list(dist)
    p = np.array([dist[k] for k in keys], dtype=float)
    return np.array(keys, dtype=object)[rng.choice(len(keys), size=n, p=p / p.sum())]


def generate_protected(customer_ids: list[str], rng: np.random.Generator) -> pd.DataFrame:
    """One row per customer; every attribute drawn independently."""
    n = len(customer_ids)
    states = _draw(rng, {s: v[1] for s, v in STATES.items()}, n)
    return pd.DataFrame(
        {
            "customer_id": customer_ids,
            "gender": _draw(rng, GENDER, n),
            "religion": _draw(rng, RELIGION, n),
            "caste_category": _draw(rng, CASTE_CATEGORY, n),
            "state": states,
            "region": [STATES[s][0] for s in states],
        }
    )
