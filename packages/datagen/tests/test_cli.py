"""CLI parsing and dispatch."""

from pathlib import Path

import pytest

from datagen import cli
from datagen.config import DatagenConfig


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for var in ("SEED", "DATA_DIR", "DATAGEN_N_CUSTOMERS"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(tmp_path)


def test_flags_become_config(tmp_path: Path) -> None:
    args = cli.build_parser().parse_args(
        ["generate", "--n", "500", "--seed", "3", "--out", str(tmp_path), "--no-transactions"]
    )
    cfg = cli.config_from_args(args)
    assert (cfg.n_customers, cfg.seed, cfg.data_dir) == (500, 3, tmp_path)
    assert not cfg.write_transactions


def test_command_is_required() -> None:
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args([])


def test_unimplemented_step_exits_non_zero() -> None:
    assert cli.main(["experiment"]) == 2


def test_all_runs_every_step_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[str, int]] = []

    def recorder(name: str) -> cli.Step:
        def run(cfg: DatagenConfig) -> None:
            seen.append((name, cfg.seed))

        return run

    monkeypatch.setattr(cli, "STEPS", {n: recorder(n) for n in cli.STEPS})
    assert cli.main(["all", "--seed", "5"]) == 0
    assert seen == [("generate", 5), ("features", 5), ("experiment", 5)]
