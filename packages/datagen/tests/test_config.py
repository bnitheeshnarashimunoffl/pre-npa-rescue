"""DatagenConfig: defaults come from npa_contracts, env vars and kwargs override them."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from datagen import DatagenConfig
from npa_contracts import constants

ENV_VARS = ("SEED", "DATA_DIR", "RAW_DATA_DIR", "DATAGEN_N_CUSTOMERS", "AS_OF_MONTH")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for var in ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(tmp_path)  # no stray .env file


def test_defaults_match_contract_constants() -> None:
    cfg = DatagenConfig()
    assert cfg.seed == constants.DEFAULT_SEED
    assert cfg.as_of_month == constants.AS_OF_MONTH
    assert cfg.start_month == constants.SIM_START_MONTH
    assert cfg.end_month == constants.SIM_END_MONTH
    assert cfg.n_customers == 10_000
    assert cfg.data_dir == Path("data/generated")
    assert cfg.write_transactions


def test_env_vars_override_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEED", "7")
    monkeypatch.setenv("DATAGEN_N_CUSTOMERS", "2000")
    monkeypatch.setenv("DATA_DIR", "/tmp/out")
    cfg = DatagenConfig()
    assert (cfg.seed, cfg.n_customers, cfg.data_dir) == (7, 2000, Path("/tmp/out"))


def test_kwargs_override_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEED", "7")
    assert DatagenConfig(seed=11).seed == 11


@pytest.mark.parametrize(
    "kwargs",
    [{"n_customers": 0}, {"as_of_month": "2026-13"}, {"as_of_month": "2027-01"}],
)
def test_invalid_values_rejected(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        DatagenConfig(**kwargs)  # type: ignore[arg-type]
