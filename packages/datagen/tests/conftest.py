"""Shared fixtures: one small generated dataset per test session."""

from pathlib import Path

import pandas as pd
import pytest

from datagen.config import DatagenConfig
from datagen.generate import GeneratedData, build, write

SMALL_N = 400


@pytest.fixture(scope="session")
def small_cfg(tmp_path_factory: pytest.TempPathFactory) -> DatagenConfig:
    out = tmp_path_factory.mktemp("generated")
    return DatagenConfig(seed=42, n_customers=SMALL_N, data_dir=out, write_transactions=True)


@pytest.fixture(scope="session")
def small_data(small_cfg: DatagenConfig) -> GeneratedData:
    return build(small_cfg)


@pytest.fixture(scope="session")
def small_written(small_cfg: DatagenConfig, small_data: GeneratedData) -> Path:
    write(small_data, small_cfg)
    return small_cfg.data_dir


@pytest.fixture(scope="session")
def account_months(small_data: GeneratedData) -> pd.DataFrame:
    return small_data.account_months
