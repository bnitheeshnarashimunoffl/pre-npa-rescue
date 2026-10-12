"""CLI skeleton and env-driven settings (A11)."""

from pathlib import Path

import pytest

from npa_models.cli import EXIT_NOT_IMPLEMENTED, main
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


@pytest.mark.parametrize(
    "argv", [["train", "--all"], ["score", "--as-of", "2026-09"], ["evaluate"]]
)
def test_cli_commands_are_stubbed(argv: list[str]) -> None:
    assert main(argv) == EXIT_NOT_IMPLEMENTED


def test_cli_help_exits_cleanly(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    assert "train" in capsys.readouterr().out


def test_cli_requires_a_command() -> None:
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2
