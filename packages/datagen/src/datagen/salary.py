"""Salary credits for salaried customers (``salary_credits.parquet``, task 1.1 step 4).

``expected_paise`` is the monthly salary (onboarding income plus April increments);
``credited_paise`` is what actually arrived (0 if missing). Shocks drive the leading signal:
job loss stops credits until recovery; a severe medical shock cuts pay for up to three months
(unpaid leave); a severe bereavement halves one month. A small share of months are missing at
random (payroll delays), so a missing credit alone is not proof of hardship.
"""

import numpy as np
import pandas as pd

from datagen.shocks import HiddenTruth
from npa_contracts.enums import ShockType

INCREMENT_MONTH = 4  # April appraisals
INCREMENT_RANGE = (0.0, 0.10)
PAYROLL_GLITCH_P = 0.003


def generate_salary(
    customers: pd.DataFrame, months: list[str], truth: HiddenTruth, rng: np.random.Generator
) -> pd.DataFrame:
    salaried = (customers["occupation_type"] == "salaried").to_numpy()
    idx = np.flatnonzero(salaried)
    n, n_months = idx.size, len(months)
    t = np.arange(n_months)[None, :]

    income = customers["monthly_income_paise"].to_numpy()[idx].astype(np.float64)
    is_april = np.array([int(m[5:]) == INCREMENT_MONTH for m in months])
    raises = 1 + rng.uniform(*INCREMENT_RANGE, (n, n_months)) * is_april[None, :]
    expected = np.round(income[:, None] * np.cumprod(raises, axis=1) / 100) * 100

    start = truth.shock_start[idx][:, None]
    rec = truth.recovers[idx][:, None]
    kind = truth.shock_type[idx][:, None]
    sev = truth.severity[idx][:, None]
    factor = np.ones((n, n_months))
    factor = np.where((kind == ShockType.JOB_LOSS) & (t >= start) & (t < rec), 0.0, factor)
    medical = (kind == ShockType.MEDICAL) & (sev > 0.5) & (t >= start) & (t < start + 3)
    factor = np.where(medical, 1 - sev, factor)
    grief = (kind == ShockType.FAMILY_BEREAVEMENT) & (sev > 0.7) & (t == start)
    factor = np.where(grief, 0.5, factor)
    factor = np.where(rng.random((n, n_months)) < PAYROLL_GLITCH_P, 0.0, factor)
    credited = np.round(expected * factor / 100) * 100

    return pd.DataFrame(
        {
            "customer_id": np.repeat(customers["customer_id"].to_numpy()[idx], n_months),
            "month": np.tile(np.array(months, dtype=object), n),
            "expected_paise": expected.ravel().astype(np.int64),
            "credited_paise": credited.ravel().astype(np.int64),
        }
    )
