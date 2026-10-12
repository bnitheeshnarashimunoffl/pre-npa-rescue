"""Generated tables: contract validity, determinism, RBI rules on every statement row."""

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from datagen import dues
from datagen.config import DatagenConfig
from datagen.generate import GeneratedData, build, write
from datagen.validate import validate
from npa_contracts.constants import NPA_DPD, bucket_for_dpd

CONTRACT_TABLES = (
    "customers",
    "protected_attributes",
    "account_months",
    "salary_credits",
    "shocks",
)


def _digest(folder: Path) -> dict[str, str]:
    return {
        p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(folder.rglob("*.parquet"))
        if p.is_file()
    }


def test_same_seed_gives_byte_identical_parquet(tmp_path: Path) -> None:
    digests = []
    for run in ("a", "b"):
        cfg = DatagenConfig(seed=7, n_customers=60, data_dir=tmp_path / run)
        write(build(cfg), cfg)
        digests.append(_digest(cfg.data_dir))
    assert digests[0] == digests[1]
    assert "transactions.parquet/2026-09.parquet" in digests[0]


def test_different_seed_differs(tmp_path: Path) -> None:
    a = build(DatagenConfig(seed=1, n_customers=50, data_dir=tmp_path))
    b = build(DatagenConfig(seed=2, n_customers=50, data_dir=tmp_path))
    assert not a.account_months["payments_paise"].equals(b.account_months["payments_paise"])


def test_written_tables_match_contract(small_written: Path) -> None:
    for table in CONTRACT_TABLES:
        df = pd.read_parquet(small_written / f"{table}.parquet")
        assert len(df) > 0, table
    txn = pd.read_parquet(small_written / "transactions.parquet")
    assert txn["txn_id"].is_unique


def test_shapes(small_data: GeneratedData, small_cfg: DatagenConfig) -> None:
    n = small_cfg.n_customers
    assert len(small_data.customers) == n
    assert len(small_data.account_months) == n * 24
    assert set(small_data.account_months["month"]) == {
        f"{y}-{m:02d}"
        for y, m in [(2024, 10), (2024, 11), (2024, 12)]
        + [(2025, k) for k in range(1, 13)]
        + [(2026, k) for k in range(1, 10)]
    }


def test_validation_rejects_bad_rows(small_data: GeneratedData) -> None:
    bad = small_data.account_months.head(5).copy()
    bad.loc[bad.index[0], "bucket"] = "sma9"
    with pytest.raises(Exception, match="bucket"):
        validate(bad, "account_months")
    extra = small_data.customers.head(3).assign(gender="female")  # protected attr leak
    with pytest.raises(Exception, match="gender"):
        validate(extra, "customers")


def test_ledger_identity_and_no_negative_balance(account_months: pd.DataFrame) -> None:
    am = account_months
    tax = dues.gst_vec(
        (am["interest_paise"] + am["late_fee_paise"]).to_numpy(np.int64), dues.DEFAULT_POLICY.gst_bp
    )
    lhs = am["closing_balance_paise"].to_numpy()
    rhs = (
        am["opening_balance_paise"]
        + am["purchases_paise"]
        + am["cash_advance_paise"]
        - am["payments_paise"]
        + am["interest_paise"]
        + am["late_fee_paise"]
    ).to_numpy() + tax
    np.testing.assert_array_equal(lhs, rhs)
    assert (am["closing_balance_paise"] >= 0).all()
    assert (am["total_due_paise"] == am["closing_balance_paise"]).all()
    prev_close = am.groupby("account_id")["closing_balance_paise"].shift(1)
    linked = prev_close.notna()
    assert (am.loc[linked, "opening_balance_paise"] == prev_close[linked]).all()


def test_rbi_rules_hold_on_every_row(account_months: pd.DataFrame) -> None:
    am = account_months
    # Minimum due never exceeds the total due (no negative amortisation is covered by MAD tests).
    assert (am["min_due_paise"] <= am["total_due_paise"]).all()
    # Bucket follows DPD exactly.
    assert (am["bucket"] == am["dpd"].map(lambda d: bucket_for_dpd(int(d)).value)).all()
    # No late fee unless the previous due date was missed by more than 3 days.
    prev_due = am.groupby("account_id")["due_date"].shift(1)
    paid_late = (am["payment_date"] - prev_due).dt.days
    prev_min = am.groupby("account_id")["min_due_paise"].shift(1)
    on_time = (am["payments_paise"] >= prev_min) & (paid_late <= 3)
    assert (am.loc[on_time, "late_fee_paise"] == 0).all()
    # No interest or fees once the account is NPA.
    npa = am["dpd"] > NPA_DPD
    assert (am.loc[npa, ["interest_paise", "late_fee_paise"]] == 0).all().all()
    # Transactors who paid in full by the due date pay no interest on purchases.
    prev_total = am.groupby("account_id")["total_due_paise"].shift(1)
    full = (am["payments_paise"] >= prev_total) & (paid_late <= 0) & (am["cash_advance_paise"] == 0)
    assert (am.loc[full, "interest_paise"] == 0).all()


def test_dates_inside_window(account_months: pd.DataFrame) -> None:
    am = account_months
    assert am["statement_date"].min() >= pd.Timestamp("2024-10-01")
    assert am["statement_date"].max() <= pd.Timestamp("2026-09-30")
    assert (am["due_date"] > am["statement_date"]).all()
    paid = am["payment_date"].notna()
    assert (am.loc[paid, "payment_date"] <= am.loc[paid, "statement_date"]).all()
    assert (am["payments_paise"] > 0).eq(paid).all()


def test_population_shape(small_data: GeneratedData) -> None:
    c = small_data.customers
    assert c["age"].between(21, 65).all()
    assert (c["card_limit_paise"] >= 1_000_000).all()
    assert c["phone_masked"].str.fullmatch(r"\+91-\d{2}XXXXX\d{3}").all()
    assert c["email_masked"].str.endswith("@example.com").all()
    assert c["account_id"].is_unique
    windows = c["preferred_contact_window"].dropna()
    assert windows.map(lambda w: w[:5] >= "08:00" and w[6:] <= "19:00").all()  # RBI 454Y(4)


def test_protected_attributes_only_in_their_table(small_data: GeneratedData) -> None:
    protected_cols = set(small_data.protected.columns) - {"customer_id"}
    for name in ("customers", "account_months", "salary", "shocks", "monthly_spend"):
        assert not protected_cols & set(getattr(small_data, name).columns), name
