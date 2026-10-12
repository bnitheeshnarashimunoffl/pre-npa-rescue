"""Task 2.5 fairness evaluation (IS/ISO/IEC TR 24027:2021, bias in AI systems).

This is the **only** module that reads ``protected_attributes.parquet`` (A3, briefing B3.1),
and only to evaluate model outputs per group. No protected column is ever a model input.

Per attribute (gender, religion, caste_category, region) it reports per-group rates and the
largest gap between groups:

- early warning: selection rate into the "high" band, TPR / FPR (equalised-odds gaps) and
  calibration within groups (mean predicted minus observed rate)
- segmentation: the share labelled ``wont_pay`` (the firmer route) and accuracy
- uplift: the share sent to ``sleeping_dog`` (no contact) vs ``persuadable`` (offered help)

Primary rule: a ``*_diff`` above :data:`MAX_GAP` (0.05, five percentage points) is flagged.
Secondary: a ``*_ratio`` below :data:`MIN_RATIO` (0.8, the four-fifths rule) is a warning.
Groups smaller than :data:`MIN_GROUP_SIZE` are reported but left out of the gaps, so a handful
of accounts can't create or hide a gap. The block layout is what WS7's scorecard reads (#106).
"""

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import pandas as pd

PROTECTED_FILE = "protected_attributes.parquet"
ATTRIBUTES: tuple[str, ...] = ("gender", "religion", "caste_category", "region")
MAX_GAP = 0.05
MIN_RATIO = 0.8
MIN_GROUP_SIZE = 30
UNKNOWN = "unknown"

# What we recommend when a gap is flagged. Group-specific thresholds are not an option: they
# would make the protected attribute an input to the decision.
MITIGATIONS: dict[str, str] = {
    "selection_rate_diff": (
        "Check which features drive the gap (SHAP by group) and whether they proxy the "
        "attribute; review the high-band threshold for all customers; monitor monthly."
    ),
    "equal_opportunity_diff": (
        "Missed at-risk customers in one group get help later: review features with "
        "group-dependent coverage (e.g. salary data) and recalibrate on more data."
    ),
    "fpr_diff": (
        "One group is flagged without need more often: check proxy features and keep the "
        "first contact light-touch (reminder) for medium-confidence cases."
    ),
    "calibration_diff": (
        "Scores mean different things across groups: recalibrate on a larger validation set "
        "and report calibration by group every month."
    ),
    "wont_pay_rate_diff": (
        "More customers of one group get the firmer route: keep the conservative wont_pay "
        "rule, require human review before any firm action, and audit those cases."
    ),
    "accuracy_diff": "Segment quality differs by group: collect more labelled data and recheck.",
    "persuadable_rate_diff": (
        "Help is offered unevenly: review tau and the cure-value assumption, and offer a "
        "light-touch reminder to at-risk customers not offered help."
    ),
    "sleeping_dog_rate_diff": (
        "One group is left uncontacted more often: sleeping dogs are over-predicted on small "
        "experiments; enlarge the experiment and send everyone at risk a reminder."
    ),
}


def load_protected(path: Path) -> pd.DataFrame:
    """``customer_id`` plus the protected attributes, for evaluation only."""
    df = pd.read_parquet(path)
    missing = sorted({"customer_id", *ATTRIBUTES} - set(df.columns))
    if missing:
        raise ValueError(f"{path.name} is missing columns {missing}")
    return df[["customer_id", *ATTRIBUTES]]


def attach(df: pd.DataFrame, protected: pd.DataFrame) -> pd.DataFrame:
    """Add the protected attributes to evaluation rows by ``customer_id`` (missing → unknown)."""
    if "customer_id" not in df.columns:
        raise ValueError("evaluation rows need customer_id to join protected attributes")
    out = df.drop(columns=[c for c in ATTRIBUTES if c in df.columns]).merge(
        protected, on="customer_id", how="left", validate="many_to_one"
    )
    out[list(ATTRIBUTES)] = out[list(ATTRIBUTES)].astype(object).fillna(UNKNOWN)
    out.index = df.index
    return out


def _rate(mask: pd.Series) -> float | None:
    return float(mask.mean()) if len(mask) else None


def _gap(groups: Mapping[str, Mapping[str, Any]], key: str) -> float | None:
    values = [
        g[key] for g in groups.values() if g["n"] >= MIN_GROUP_SIZE and g.get(key) is not None
    ]
    return float(max(values) - min(values)) if len(values) >= 2 else None


def _ratio(groups: Mapping[str, Mapping[str, Any]], key: str) -> float | None:
    values = [
        g[key] for g in groups.values() if g["n"] >= MIN_GROUP_SIZE and g.get(key) is not None
    ]
    if len(values) < 2 or max(values) == 0:
        return None
    return float(min(values) / max(values))


GroupStats = Callable[[pd.DataFrame], dict[str, Any]]


def _by_attribute(
    df: pd.DataFrame,
    stats: GroupStats,
    diffs: Mapping[str, str],
    ratios: Mapping[str, str],
    attributes: Sequence[str] = ATTRIBUTES,
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for attr in attributes:
        groups = {
            str(name): {"n": len(part), **stats(part)}
            for name, part in df.groupby(attr, sort=True, observed=True)
        }
        block: dict[str, Any] = {f"{m}_diff": _gap(groups, key) for m, key in diffs.items()}
        block |= {f"{m}_ratio": _ratio(groups, key) for m, key in ratios.items()}
        block["flagged"] = sorted(
            k
            for k, v in block.items()
            if v is not None
            and ((k.endswith("_diff") and v > MAX_GAP) or (k.endswith("_ratio") and v < MIN_RATIO))
        )
        block["groups"] = groups
        out[attr] = block
    return out


def risk_fairness(df: pd.DataFrame, attributes: Sequence[str] = ATTRIBUTES) -> dict[str, Any]:
    """Early warning. ``df``: attributes, ``y`` (rolled forward), ``p`` (calibrated), ``high``."""

    def stats(part: pd.DataFrame) -> dict[str, Any]:
        pos, neg = part[part["y"]], part[~part["y"]]
        observed = float(part["y"].mean())
        predicted = float(part["p"].mean())
        return {
            "selection_rate": _rate(part["high"]),
            "tpr": _rate(pos["high"]),
            "fpr": _rate(neg["high"]),
            "observed_rate": observed,
            "mean_predicted": predicted,
            "calibration_gap": predicted - observed,
        }

    return _by_attribute(
        df.assign(y=df["y"].astype(bool), high=df["high"].astype(bool)),
        stats,
        diffs={
            "selection_rate": "selection_rate",
            "equal_opportunity": "tpr",
            "fpr": "fpr",
            "calibration": "calibration_gap",
        },
        ratios={"disparate_impact": "selection_rate"},
        attributes=attributes,
    )


def segment_fairness(df: pd.DataFrame, attributes: Sequence[str] = ATTRIBUTES) -> dict[str, Any]:
    """Segmentation. ``df``: attributes, ``truth`` and ``pred`` segment labels."""

    def stats(part: pd.DataFrame) -> dict[str, Any]:
        return {
            "wont_pay_rate": _rate(part["pred"] == "wont_pay"),
            "accuracy": _rate(part["pred"] == part["truth"]),
        }

    return _by_attribute(
        df,
        stats,
        diffs={"wont_pay_rate": "wont_pay_rate", "accuracy": "accuracy"},
        ratios={},
        attributes=attributes,
    )


def uplift_fairness(df: pd.DataFrame, attributes: Sequence[str] = ATTRIBUTES) -> dict[str, Any]:
    """Uplift. ``df``: attributes and ``uplift_group`` for the at-risk accounts."""

    def stats(part: pd.DataFrame) -> dict[str, Any]:
        return {
            "persuadable_rate": _rate(part["uplift_group"] == "persuadable"),
            "sleeping_dog_rate": _rate(part["uplift_group"] == "sleeping_dog"),
        }

    return _by_attribute(
        df,
        stats,
        diffs={"persuadable_rate": "persuadable_rate", "sleeping_dog_rate": "sleeping_dog_rate"},
        ratios={"persuadable": "persuadable_rate"},
        attributes=attributes,
    )


def flags(fairness: Mapping[str, Mapping[str, Mapping[str, Any]]]) -> list[dict[str, Any]]:
    """Every flagged gap as ``{model, attribute, metric, value, threshold, tier, mitigation}``."""
    out = []
    for model, attrs in fairness.items():
        for attr, block in attrs.items():
            for metric in block["flagged"]:
                primary = metric.endswith("_diff")
                out.append(
                    {
                        "model": model,
                        "attribute": attr,
                        "metric": metric,
                        "value": block[metric],
                        "threshold": MAX_GAP if primary else MIN_RATIO,
                        "tier": "primary" if primary else "secondary",
                        "mitigation": MITIGATIONS.get(
                            metric, "Four-fifths warning: see the matching *_diff gap."
                        ),
                    }
                )
    return out
