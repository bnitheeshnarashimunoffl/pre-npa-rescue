"""Tests for npa_rules.cli (policy validation and fixture generation)."""

import json
from pathlib import Path

import pytest

from npa_contracts.models import NextBestAction, Offer, QueueItem, ReliefOption
from npa_rules.cli import main

REPO = Path(__file__).resolve().parents[3]
QUEUE = REPO / "contracts" / "fixtures" / "queue.json"


def test_validate_ok() -> None:
    assert main(["validate"]) == 0


def test_validate_bad_policy(tmp_path: Path) -> None:
    bad = tmp_path / "p.yaml"
    bad.write_text("version: 1\n", encoding="utf-8")
    assert main(["validate", "--policy", str(bad)]) == 1


def test_fixtures_written_and_valid(tmp_path: Path) -> None:
    assert main(["fixtures", "--out", str(tmp_path), "--queue-fixture", str(QUEUE)]) == 0
    load = lambda name: json.loads((tmp_path / name).read_text(encoding="utf-8"))  # noqa: E731
    priya = [ReliefOption.model_validate(o) for o in load("relief_options_priya.json")]
    assert any(o.monthly_amount_paise == 200_000 and o.tenure_months == 6 for o in priya)
    ravi = [ReliefOption.model_validate(o) for o in load("relief_options_ravi.json")]
    assert ravi[0].type == "insurance_referral"
    offer = Offer.model_validate(load("offer.json"))
    assert offer.status == "approved"
    assert NextBestAction.model_validate(load("nba.json")).action == "chat_invite"
    queue = [QueueItem.model_validate(i) for i in load("queue.json")["items"]]
    assert len(queue) == 10
    assert load("policy.json")["policy"]["version"] == "2026.10-v1"


def test_fixtures_are_deterministic(tmp_path: Path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    for out in (a, b):
        assert main(["fixtures", "--out", str(out), "--queue-fixture", str(QUEUE)]) == 0
    for f in a.iterdir():
        assert f.read_bytes() == (b / f.name).read_bytes()


def test_command_required() -> None:
    with pytest.raises(SystemExit):
        main([])
