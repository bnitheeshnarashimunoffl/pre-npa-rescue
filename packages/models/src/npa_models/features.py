"""Model inputs: the feature allowlist, the leakage guard and the time-based split.

This module is the only place that decides which columns a model may see.

- RBI Responsible Business Conduct (fair treatment) and A3 rule 1: protected attributes
  (``gender``, ``religion``, ``caste_category``, ``state``, ``region``) are never model inputs.
  They are read only by ``fairness.py`` for evaluation (IS/ISO/IEC TR 24027:2021, bias in AI).
- Hidden ground truth (``shocks.*``, ``true_uplift_group``) and labels are never inputs.
- ``city`` is kept out as a mild proxy for ``state``/``region`` (briefing B8).
- Splits are by month only, never random (no look-ahead; IS/ISO/IEC 23053:2022 ML lifecycle).
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import NamedTuple

import pandas as pd

# A7.2.1 feature columns usable by the models (identifiers excluded).
NUMERIC_FEATURES: tuple[str, ...] = (
    "limit_paise",
    "utilisation",
    "utilisation_delta_3m",
    "min_due_only_streak",
    "months_since_full_payment",
    "payment_ratio_3m",
    "dpd",
    "max_dpd_6m",
    "broken_streak_flag",
    "cash_advance_ratio_3m",
    "essentials_spend_delta_3m",
    "discretionary_spend_delta_3m",
    "txn_count_delta_3m",
    "salary_missing_months_3m",
    "salary_delta_3m",
    "income_to_due_ratio",
    "tenure_months",
    "dependants",
)
CATEGORICAL_FEATURES: tuple[str, ...] = ("occupation_type",)
FEATURE_COLUMNS: tuple[str, ...] = NUMERIC_FEATURES + CATEGORICAL_FEATURES

OCCUPATION_TYPES: tuple[str, ...] = ("salaried", "self_employed", "gig", "retired", "student")

PROTECTED_COLUMNS: frozenset[str] = frozenset(
    {"gender", "religion", "caste_category", "state", "region"}
)
HIDDEN_TRUTH_COLUMNS: frozenset[str] = frozenset(
    {"shock_type", "start_month", "severity", "recovers_month", "true_uplift_group"}
)
LABEL_COLUMNS: frozenset[str] = frozenset(
    {
        "rolls_forward_60d",
        "reaches_npa_90d",
        "segment_truth",
        "outcome_cured_90d",
        "outcome_npa_90d",
        "treatment",
    }
)
IDENTIFIER_COLUMNS: frozenset[str] = frozenset(
    {"account_id", "customer_id", "month", "full_name", "phone_masked", "email_masked"}
)
PROXY_COLUMNS: frozenset[str] = frozenset({"city"})

FORBIDDEN_COLUMNS: frozenset[str] = (
    PROTECTED_COLUMNS | HIDDEN_TRUTH_COLUMNS | LABEL_COLUMNS | IDENTIFIER_COLUMNS | PROXY_COLUMNS
)

_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class LeakageError(ValueError):
    """A forbidden column (protected, hidden truth, label, identifier or proxy) reached a model."""


def assert_no_leakage(columns: Iterable[str]) -> None:
    """Raise :class:`LeakageError` if any column is forbidden as a model input."""
    bad = sorted(set(columns) & FORBIDDEN_COLUMNS)
    if bad:
        raise LeakageError(f"forbidden model input column(s): {', '.join(bad)}")


def build_matrix(
    df: pd.DataFrame, feature_columns: Iterable[str] = FEATURE_COLUMNS
) -> pd.DataFrame:
    """Return the model input matrix for ``df``.

    Checks the requested columns against the leakage guard, then selects them in order,
    casts booleans to ``int8`` and ``occupation_type`` to a fixed categorical (unknown values
    become missing, which LightGBM handles).
    """
    cols = list(feature_columns)
    assert_no_leakage(cols)
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise KeyError(f"feature column(s) missing from input: {', '.join(missing)}")
    x = df.loc[:, cols].copy()
    for col in cols:
        if col in CATEGORICAL_FEATURES:
            x[col] = pd.Categorical(x[col], categories=list(OCCUPATION_TYPES))
        elif pd.api.types.is_bool_dtype(x[col]):
            x[col] = x[col].astype("int8")
    return x


@dataclass(frozen=True)
class TimeSplit:
    """Month boundaries (inclusive) for train / validation / test (briefing B3.2)."""

    train_end: str = "2026-03"
    val_start: str = "2026-04"
    val_end: str = "2026-06"
    test_start: str = "2026-07"
    test_end: str = "2026-09"

    def __post_init__(self) -> None:
        bounds = (self.train_end, self.val_start, self.val_end, self.test_start, self.test_end)
        for month in bounds:
            if not _MONTH_RE.match(month):
                raise ValueError(f"month must be YYYY-MM, got {month!r}")
        # YYYY-MM strings sort chronologically.
        if not (self.train_end < self.val_start <= self.val_end < self.test_start <= self.test_end):
            raise ValueError(f"split boundaries overlap or are out of order: {bounds}")


DEFAULT_SPLIT = TimeSplit()


class Splits(NamedTuple):
    train: pd.DataFrame
    val: pd.DataFrame
    test: pd.DataFrame


def time_split(
    df: pd.DataFrame, split: TimeSplit = DEFAULT_SPLIT, month_col: str = "month"
) -> Splits:
    """Split rows by month. Rows between windows or after ``test_end`` are dropped."""
    if month_col not in df.columns:
        raise KeyError(f"column {month_col!r} missing; time splits need a month column")
    m = df[month_col]
    return Splits(
        train=df[m <= split.train_end],
        val=df[(m >= split.val_start) & (m <= split.val_end)],
        test=df[(m >= split.test_start) & (m <= split.test_end)],
    )
