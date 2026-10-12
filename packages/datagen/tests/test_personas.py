"""Demo personas: agreed numbers (issue #1), determinism across seeds, JSON output."""

import json
from pathlib import Path

import pandas as pd
import pytest

from datagen.calendar import month_range
from datagen.config import DatagenConfig
from datagen.generate import PERSONAS_JSON, GeneratedData, build
from datagen.personas import (
    PERSONAS,
    PRIYA_AFFORDABLE_PAISE,
    build_personas,
    persona_facts,
    waivable_charges,
)
from datagen.pipeline import run_features

MONTHS = month_range("2024-10", "2026-09")
SAMPLES = Path(__file__).resolve().parents[3] / "data" / "samples"


@pytest.fixture(scope="module")
def tables() -> dict[str, pd.DataFrame]:
    return build_personas(MONTHS)


@pytest.fixture(scope="module")
def facts(tables: dict[str, pd.DataFrame]) -> dict[str, dict[str, object]]:
    return persona_facts(tables["account_months"])


def _history(tables: dict[str, pd.DataFrame], key: str) -> pd.DataFrame:
    am = tables["account_months"]
    return am[am["account_id"] == f"ACC-DEMO-{key}"].set_index("month")


def test_priya_agreed_numbers(tables: dict[str, pd.DataFrame], facts: dict) -> None:
    f = facts["CUST-DEMO-PRIYA"]
    assert f["overdue_paise"] == 1_149_200  # Rs 11,492 -> 6 x Rs 2,000 at 15% p.a.
    assert f["late_fee_paise"] == 130_000  # slab on the post-due outstanding (RBI)
    assert f["waivable_charges_paise"] == 153_400  # Rs 1,300 + 18% GST
    assert f["affordable_monthly_paise"] == PRIYA_AFFORDABLE_PAISE == 200_000
    assert f["bucket"] == "sma0"
    assert 10_000_000 <= f["total_due_paise"] <= 11_500_000  # about Rs 1,10,000


def test_priya_story(tables: dict[str, pd.DataFrame]) -> None:
    h = _history(tables, "PRIYA")
    # Minimum-only in 2026-07 and 2026-08, part of the minimum in 2026-09.
    for m, prev in (("2026-07", "2026-06"), ("2026-08", "2026-07")):
        assert h.loc[m, "payments_paise"] == h.loc[prev, "min_due_paise"]
    assert 0 < h.loc["2026-09", "payments_paise"] < h.loc["2026-08", "min_due_paise"]
    assert (h.loc[:"2026-08", "dpd"] == 0).all()
    sal = tables["salary"].query("customer_id == 'CUST-DEMO-PRIYA'").set_index("month")
    assert (sal.loc["2026-06":, "credited_paise"] == 0).all()
    assert (sal.loc[:"2026-05", "credited_paise"] > 0).all()
    c = tables["customers"].set_index("customer_id").loc["CUST-DEMO-PRIYA"]
    assert (c["age"], c["city"], c["language_pref"], c["dependants"]) == (29, "Chennai", "ta", 1)
    assert c["card_limit_paise"] == 18_000_000 and not c["has_card_insurance"]


def test_ravi_agreed_numbers(tables: dict[str, pd.DataFrame], facts: dict) -> None:
    f = facts["CUST-DEMO-RAVI"]
    assert f["affordable_monthly_paise"] == 0
    assert f["bucket"] == "sma1"
    h = _history(tables, "RAVI")
    assert (h.loc[["2026-08", "2026-09"], "payments_paise"] == 0).all()
    c = tables["customers"].set_index("customer_id").loc["CUST-DEMO-RAVI"]
    assert c["insurance_cover_type"] == "job_loss" and c["has_card_insurance"]
    assert (c["age"], c["city"], c["dependants"]) == (41, "Madurai", 3)
    assert c["card_limit_paise"] == 10_000_000
    start, end = c["preferred_contact_window"].split("-")
    assert start <= "11:00" < end  # the demo callback slot fits his window and 08:00-19:00
    sal = tables["salary"].query("customer_id == 'CUST-DEMO-RAVI'").set_index("month")
    assert (sal.loc["2026-07":, "credited_paise"] == 0).all()


def test_every_persona_lands_in_its_bucket(facts: dict) -> None:
    expected = {
        "PRIYA": "sma0",
        "RAVI": "sma1",
        "ANITA": "sma0",
        "VIKRAM": "sma2",
        "MEERA": "sma0",
        "ARJUN": "current",
        "FATIMA": "sma1",
        "SURESH": "npa",
        "KAVYA": "current",
        "JOSEPH": "current",
    }
    assert {k: facts[f"CUST-DEMO-{k}"]["bucket"] for k in expected} == expected


def test_cast_covers_required_types() -> None:
    groups = {p.facts.get("expected_uplift_group") for p in PERSONAS}
    assert {"persuadable", "sure_thing", "lost_cause", "sleeping_dog"} <= groups
    segments = {p.facts["expected_segment"] for p in PERSONAS}
    assert {"forgot", "cant_pay", "wont_pay"} <= segments
    assert any(p.shock[0] == "medical" for p in PERSONAS)
    assert len(PERSONAS) == 10


def test_personas_identical_for_any_seed(tmp_path: Path) -> None:
    def persona_rows(seed: int) -> pd.DataFrame:
        d = build(DatagenConfig(seed=seed, n_customers=20, data_dir=tmp_path))
        am = d.account_months
        return am[am["account_id"].str.startswith("ACC-DEMO-")].reset_index(drop=True)

    pd.testing.assert_frame_equal(persona_rows(1), persona_rows(99))


def test_waivable_charges() -> None:
    assert waivable_charges(130_000) == 153_400
    assert waivable_charges(0) == 0


def test_persona_json(small_written: Path, small_cfg: DatagenConfig, tmp_path: Path) -> None:
    run_features(small_cfg.model_copy(update={"samples_dir": tmp_path}))
    doc = json.loads((small_written / PERSONAS_JSON).read_text(encoding="utf-8"))
    assert set(doc) == {p.customer_id for p in PERSONAS}
    priya = doc["CUST-DEMO-PRIYA"]
    assert priya["facts"]["overdue_paise"] == 1_149_200
    assert priya["customers"]["full_name"] == "Priya Subramanian"
    assert priya["protected_attributes"]["state"] == "Tamil Nadu"
    assert len(priya["account_months"]) == 24
    assert len(priya["features"]) == 24 and len(priya["labels"]) == 24
    assert priya["transactions"] and priya["transactions"][0]["ts"].endswith("+00:00")
    sample = json.loads((tmp_path / PERSONAS_JSON).read_text(encoding="utf-8"))
    assert "transactions" not in sample["CUST-DEMO-PRIYA"]


def test_priya_segment_label(small_data: GeneratedData) -> None:
    from datagen.labels import build_labels

    lb = build_labels(small_data.account_months, small_data.shocks, small_data.behaviour)
    row = lb[(lb["account_id"] == "ACC-DEMO-PRIYA") & (lb["month"] == "2026-06")].iloc[0]
    assert row["segment_truth"] == "cant_pay"  # salary stopped this month: an active shock


@pytest.mark.skipif(not (SAMPLES / PERSONAS_JSON).exists(), reason="no committed sample")
def test_committed_persona_sample() -> None:
    doc = json.loads((SAMPLES / PERSONAS_JSON).read_text(encoding="utf-8"))
    assert doc["CUST-DEMO-PRIYA"]["facts"]["overdue_paise"] == 1_149_200
    assert doc["CUST-DEMO-RAVI"]["facts"]["affordable_monthly_paise"] == 0
