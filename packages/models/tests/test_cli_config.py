"""CLI skeleton and env-driven settings (A11)."""

from pathlib import Path

import pytest

from npa_models.cli import EXIT_ERROR, EXIT_NOT_IMPLEMENTED, EXIT_OK, main
from npa_models.config import ModelSettings


def test_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("SEED", "DATA_DIR", "MODEL_DIR", "AS_OF_MONTH"):
        monkeypatch.delenv(var, raising=False)
    s = ModelSettings(_env_file=None)  # type: ignore[call-arg]
    assert s.seed == 42
    assert s.as_of_month == "2026-09"
    assert s.model_dir == Path("packages/models/artifacts")


def test_settings_read_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SEED", "7")
    monkeypatch.setenv("MODEL_DIR", str(tmp_path))
    s = ModelSettings(_env_file=None)  # type: ignore[call-arg]
    assert s.seed == 7
    assert s.model_dir == tmp_path


def test_cli_score_is_stubbed() -> None:
    assert main(["score", "--as-of", "2026-09"]) == EXIT_NOT_IMPLEMENTED


def test_cli_train_writes_artifacts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fake_data
) -> None:
    fp, lp = tmp_path / "features.parquet", tmp_path / "labels.parquet"
    fake_data.features.to_parquet(fp)
    fake_data.labels.to_parquet(lp)
    monkeypatch.setenv("MODEL_DIR", str(tmp_path / "artifacts"))
    assert main(["train", "--features", str(fp), "--labels", str(lp)]) == EXIT_OK
    assert (tmp_path / "artifacts" / "early_warning" / "meta.json").is_file()
    assert (tmp_path / "artifacts" / "segment" / "meta.json").is_file()
    assert not (tmp_path / "artifacts" / "uplift").exists()


def test_cli_train_all_includes_uplift(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fake_experiment
) -> None:
    paths = {n: tmp_path / f"{n}.parquet" for n in ("features", "labels", "experiment")}
    fake_experiment.data.features.to_parquet(paths["features"])
    fake_experiment.data.labels.to_parquet(paths["labels"])
    fake_experiment.experiment.to_parquet(paths["experiment"])
    monkeypatch.setenv("MODEL_DIR", str(tmp_path / "artifacts"))
    argv = ["train", "--all", *(f"--{n}={p}" for n, p in paths.items())]
    assert main(argv) == EXIT_OK
    assert (tmp_path / "artifacts" / "uplift" / "meta.json").is_file()


def test_cli_train_all_needs_experiment(tmp_path: Path, fake_data) -> None:
    fp, lp = tmp_path / "features.parquet", tmp_path / "labels.parquet"
    fake_data.features.to_parquet(fp)
    fake_data.labels.to_parquet(lp)
    argv = [
        "train",
        "--all",
        "--features",
        str(fp),
        "--labels",
        str(lp),
        "--experiment",
        str(tmp_path / "missing.parquet"),
    ]
    assert main(argv) == EXIT_ERROR


def test_cli_train_missing_input_fails(tmp_path: Path) -> None:
    argv = ["train", "--features", str(tmp_path / "nope.parquet"), "--labels", str(tmp_path)]
    assert main(argv) == EXIT_ERROR


def test_cli_help_exits_cleanly(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    assert "train" in capsys.readouterr().out


def test_cli_requires_a_command() -> None:
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2
