"""CLI generate step, the sanity report and integrity checks."""

from pathlib import Path

import pandas as pd
import pytest

from datagen import cli
from datagen.generate import GeneratedData
from datagen.sanity import report
from datagen.validate import check_integrity


def test_cli_generate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "gen"
    args = ["--n", "30", "--seed", "3", "--out", str(out)]
    assert cli.main(["generate", *args, "--no-transactions"]) == 0
    assert not (out / "transactions.parquet").exists()
    assert (out / "account_months.parquet").exists()


def test_sanity_report(small_written: Path) -> None:
    text = report(small_written, "2026-09")
    assert "NPA rate at 2026-09" in text
    assert "cash_advance" in text


def test_integrity_check_catches_errors(small_data: GeneratedData) -> None:
    c, am = small_data.customers, small_data.account_months
    with pytest.raises(ValueError, match="duplicate customer_id"):
        check_integrity(pd.concat([c, c.head(1)]), am, start_month="2024-10", end_month="2026-09")
    with pytest.raises(ValueError, match="unknown account_id"):
        check_integrity(c.iloc[1:], am, start_month="2024-10", end_month="2026-09")
    with pytest.raises(ValueError, match="outside"):
        check_integrity(c, am, start_month="2025-01", end_month="2026-09")
    bad_salary = small_data.salary.head(3).assign(customer_id="CUST-NOPE")
    with pytest.raises(ValueError, match="salary"):
        check_integrity(
            c, am, start_month="2024-10", end_month="2026-09", others={"salary": bad_salary}
        )
