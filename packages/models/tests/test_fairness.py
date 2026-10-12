"""Task 2.5 fairness block (IS/ISO/IEC TR 24027:2021): gaps, four-fifths and flags."""

from pathlib import Path

import pandas as pd
import pytest

from npa_models import fairness
from npa_models.fairness import (
    MAX_GAP,
    MIN_GROUP_SIZE,
    attach,
    flags,
    load_protected,
    risk_fairness,
    segment_fairness,
    uplift_fairness,
)


def _risk_rows(rates: dict[str, tuple[int, float, float]]) -> pd.DataFrame:
    """Per group: (n, share flagged high, share rolled forward); flagged rows roll forward first."""
    parts = []
    for group, (n, high_share, pos_share) in rates.items():
        n_high, n_pos = round(n * high_share), round(n * pos_share)
        parts.append(
            pd.DataFrame(
                {
                    "gender": group,
                    "high": [i < n_high for i in range(n)],
                    "y": [i < n_pos for i in range(n)],
                    "p": [pos_share] * n,
                }
            )
        )
    return pd.concat(parts, ignore_index=True)


def test_equal_groups_have_no_gaps() -> None:
    df = _risk_rows({"female": (100, 0.1, 0.2), "male": (100, 0.1, 0.2)})
    block = risk_fairness(df, attributes=("gender",))["gender"]
    assert block["selection_rate_diff"] == 0
    assert block["equal_opportunity_diff"] == 0
    assert block["calibration_diff"] == 0
    assert block["disparate_impact_ratio"] == 1
    assert block["flagged"] == []
    assert block["groups"]["female"] == pytest.approx(
        {
            "n": 100,
            "selection_rate": 0.1,
            "tpr": 0.5,
            "fpr": 0.0,
            "observed_rate": 0.2,
            "mean_predicted": 0.2,
            "calibration_gap": 0.0,
        }
    )


def test_gap_above_five_points_is_flagged_and_four_fifths_warns() -> None:
    df = _risk_rows({"female": (200, 0.10, 0.2), "male": (200, 0.20, 0.2)})
    block = risk_fairness(df, attributes=("gender",))["gender"]
    assert block["selection_rate_diff"] == pytest.approx(0.10)
    assert block["disparate_impact_ratio"] == pytest.approx(0.5)
    assert {"selection_rate_diff", "disparate_impact_ratio"} <= set(block["flagged"])
    found = flags({"early_warning": {"gender": block}})
    by_metric = {f["metric"]: f for f in found}
    assert by_metric["selection_rate_diff"]["tier"] == "primary"
    assert by_metric["selection_rate_diff"]["threshold"] == MAX_GAP
    assert by_metric["disparate_impact_ratio"]["tier"] == "secondary"
    assert all(f["mitigation"] for f in found)


def test_small_groups_are_reported_but_not_gapped() -> None:
    df = _risk_rows({"female": (100, 0.1, 0.2), "male": (100, 0.1, 0.2), "other": (5, 1.0, 1.0)})
    block = risk_fairness(df, attributes=("gender",))["gender"]
    assert block["groups"]["other"]["n"] < MIN_GROUP_SIZE
    assert block["selection_rate_diff"] == 0


def test_single_group_gives_null_gaps() -> None:
    block = risk_fairness(_risk_rows({"female": (100, 0.1, 0.2)}), attributes=("gender",))
    assert block["gender"]["selection_rate_diff"] is None
    assert block["gender"]["disparate_impact_ratio"] is None
    assert block["gender"]["flagged"] == []


def test_ratio_is_null_when_no_group_is_selected() -> None:
    block = risk_fairness(_risk_rows({"a": (50, 0.0, 0.2), "b": (50, 0.0, 0.2)}), ("gender",))
    assert block["gender"]["disparate_impact_ratio"] is None


def test_segment_and_uplift_blocks() -> None:
    seg = pd.DataFrame(
        {
            "region": ["north"] * 40 + ["south"] * 40,
            "truth": ["wont_pay"] * 80,
            "pred": ["wont_pay"] * 40 + ["cant_pay"] * 40,
        }
    )
    s = segment_fairness(seg, attributes=("region",))["region"]
    assert s["wont_pay_rate_diff"] == 1.0 and s["accuracy_diff"] == 1.0
    assert set(s) == {"wont_pay_rate_diff", "accuracy_diff", "flagged", "groups"}

    up = pd.DataFrame(
        {
            "region": ["north"] * 40 + ["south"] * 40,
            "uplift_group": ["persuadable"] * 40 + ["persuadable"] * 30 + ["sleeping_dog"] * 10,
        }
    )
    u = uplift_fairness(up, attributes=("region",))["region"]
    assert u["persuadable_rate_diff"] == pytest.approx(0.25)
    assert u["sleeping_dog_rate_diff"] == pytest.approx(0.25)
    assert u["persuadable_ratio"] == pytest.approx(0.75)
    assert set(u["flagged"]) == {
        "persuadable_rate_diff",
        "sleeping_dog_rate_diff",
        "persuadable_ratio",
    }


def test_attach_and_load(tmp_path: Path, fake_data) -> None:
    path = tmp_path / fairness.PROTECTED_FILE
    fake_data.protected.to_parquet(path)
    protected = load_protected(path)
    assert list(protected.columns) == ["customer_id", *fairness.ATTRIBUTES]
    rows = pd.DataFrame({"customer_id": ["CUST-NOT-THERE", protected["customer_id"].iloc[0]]})
    out = attach(rows, protected)
    assert out.loc[0, "gender"] == fairness.UNKNOWN
    assert out.loc[1, "gender"] == protected["gender"].iloc[0]
    with pytest.raises(ValueError, match="customer_id"):
        attach(pd.DataFrame({"x": [1]}), protected)
    protected.drop(columns="region").to_parquet(path)
    with pytest.raises(ValueError, match="region"):
        load_protected(path)
