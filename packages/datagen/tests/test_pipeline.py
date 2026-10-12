"""End-to-end CLI steps on the small dataset, the sanity report and integrity checks."""

from pathlib import Path

import pandas as pd
import pytest

from datagen import cli
from datagen.config import DatagenConfig
from datagen.generate import GeneratedData
from datagen.personas import PERSONAS
from datagen.pipeline import run_features
from datagen.sanity import report
from datagen.validate import check_integrity, validate


def test_run_features_writes_tables_and_samples(
    small_written: Path, small_cfg: DatagenConfig, tmp_path: Path
) -> None:
    cfg = small_cfg.model_copy(update={"samples_dir": tmp_path})
    run_features(cfg)
    features = pd.read_parquet(small_written / "features.parquet")
    labels = pd.read_parquet(small_written / "labels.parquet")
    assert len(features) == (small_cfg.n_customers + len(PERSONAS)) * 24
    validate(labels, "labels")
    sample = pd.read_parquet(tmp_path / "features_sample.parquet")
    assert len(sample) == 2_000  # 200 accounts x 10 months
    assert sample["month"].min() == "2025-09" and sample["month"].max() == "2026-06"


def test_cli_generate_and_features(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "gen"
    args = ["--n", "30", "--seed", "3", "--out", str(out)]
    assert cli.main(["generate", *args, "--no-transactions"]) == 0
    assert not (out / "transactions.parquet").exists()
    assert cli.main(["features", "--out", str(out)]) == 0
    assert (out / "labels.parquet").exists()


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


def test_chunked_features_equal_single_pass(
    small_written: Path, small_cfg: DatagenConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Large populations are processed in account chunks; the content must not change."""
    import shutil

    from datagen import pipeline

    run_features(small_cfg)
    single_f = pd.read_parquet(small_written / "features.parquet")
    single_l = pd.read_parquet(small_written / "labels.parquet")

    chunked_dir = tmp_path / "chunked"
    shutil.copytree(small_written, chunked_dir)
    monkeypatch.setattr(pipeline, "FEATURE_CHUNK_ACCOUNTS", 97)  # 410 accounts -> 5 chunks
    run_features(small_cfg.model_copy(update={"data_dir": chunked_dir, "samples_dir": tmp_path}))
    pd.testing.assert_frame_equal(pd.read_parquet(chunked_dir / "features.parquet"), single_f)
    pd.testing.assert_frame_equal(pd.read_parquet(chunked_dir / "labels.parquet"), single_l)
    sample = pd.read_parquet(tmp_path / "features_sample.parquet")
    assert len(sample) == 2_000
