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
    assert f["total_due_paise"] == 10_745_200  # Rs 1,07,452 (canonical)


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
    assert f["total_due_paise"] == 6_480_000  # Rs 64,800
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


# --- Drift guard: the agreed persona numbers, exactly, as the generator produces them ---------

PRIYA_EXPECTED = {
    "total_due_paise": 10_745_200,  # Rs 1,07,452 outstanding (canonical)
    "overdue_paise": 1_149_200,  # Rs 11,492: covered by the 6 x Rs 2,000 plan
    "waivable_charges_paise": 153_400,  # Rs 1,300 late fee + 18% GST
    "late_fee_paise": 130_000,
    "capacity_monthly_paise": 240_000,  # Rs 2,400 a month from her declared budget
    "affordable_monthly_paise": 200_000,  # Rs 2,000 plan instalment
    "dpd": 16,
    "bucket": "sma0",
}
RAVI_EXPECTED = {
    "total_due_paise": 6_480_000,  # Rs 64,800
    # Rs 14,385.13, not the Rs 9,000 in the request: two unpaid minimums plus the current one on
    # Rs 64,800 at 42% p.a. cannot be below ~Rs 12,000 (see data/README.md, "Demo personas").
    "overdue_paise": 1_438_513,
    "waivable_charges_paise": 153_400,
    "late_fee_paise": 130_000,
    "capacity_monthly_paise": 0,  # zero capacity
    "affordable_monthly_paise": 0,
    "dpd": 47,
    "bucket": "sma1",
}


def _check(facts: dict, expected: dict) -> None:
    got = {k: facts[k] for k in expected}
    assert got == expected


def test_persona_numbers_do_not_drift(facts: dict, tables: dict[str, pd.DataFrame]) -> None:
    _check(facts["CUST-DEMO-PRIYA"], PRIYA_EXPECTED)
    _check(facts["CUST-DEMO-RAVI"], RAVI_EXPECTED)
    h = _history(tables, "PRIYA")
    post_due = h.loc["2026-08", "total_due_paise"] - h.loc["2026-09", "payments_paise"]
    assert post_due == 9_251_900  # Rs 92,519 outstanding after the due date (canonical)
    assert facts["CUST-DEMO-PRIYA"]["offer"] == {
        "type": "emi_conversion",
        "monthly_amount_paise": 200_000,
        "tenure_months": 6,
        "fee_waiver": True,
    }
    c = tables["customers"].set_index("customer_id").loc["CUST-DEMO-RAVI"]
    assert c["insurance_cover_type"] == "job_loss"


def test_generator_output_has_the_persona_numbers(
    small_written: Path, small_cfg: DatagenConfig, tmp_path: Path
) -> None:
    """Same numbers from the real pipeline (generate + features), not just build_personas."""
    run_features(small_cfg.model_copy(update={"samples_dir": tmp_path}))
    doc = json.loads((small_written / PERSONAS_JSON).read_text(encoding="utf-8"))
    _check(doc["CUST-DEMO-PRIYA"]["facts"], PRIYA_EXPECTED)
    _check(doc["CUST-DEMO-RAVI"]["facts"], RAVI_EXPECTED)
    am = pd.read_parquet(small_written / "account_months.parquet")
    last = am[am["month"] == "2026-09"].set_index("account_id")
    assert last.loc["ACC-DEMO-PRIYA", "total_due_paise"] == 10_745_200
    assert last.loc["ACC-DEMO-RAVI", "total_due_paise"] == 6_480_000
