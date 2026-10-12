from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from npa_contracts.enums import RedTeamCategory
from npa_contracts.models import Scorecard
from npa_redteam import LibraryTarget, load_cases, run
from npa_redteam.cases import ConversationCase
from npa_redteam.cli import main
from npa_redteam.harness import execute_case, new_run_id

WriteCases = Callable[..., Path]
NOW = datetime(2026, 10, 12, 5, 0, tzinfo=UTC)


def _case(base: dict[str, Any], **change: Any) -> ConversationCase:
    return ConversationCase.model_validate({"suite": "pressure", **base, **change})


def test_run_id_is_ist() -> None:
    assert new_run_id(NOW) == "RT-20261012-1030"


def test_good_engine_passes(good_target: LibraryTarget, base_case: dict[str, Any]) -> None:
    case = _case(base_case, expect={"required_flags": ["zero_capacity"], "handoff": "required"})
    outcome = execute_case(case, good_target)
    assert outcome.status == "passed", outcome.failures
    assert "hardship officer" in outcome.output


def test_bad_engine_fails_every_baseline_check(
    bad_target: LibraryTarget, base_case: dict[str, Any]
) -> None:
    outcome = execute_case(_case(base_case), bad_target)
    assert outcome.status == "failed"
    kinds = {f.split(":")[0] for f in outcome.failures}
    assert kinds == {"harsh", "offers", "numbers", "zero-capacity", "masking", "handoff"}


def test_crash_is_a_failure(crashing_target: LibraryTarget, base_case: dict[str, Any]) -> None:
    outcome = execute_case(_case(base_case), crashing_target)
    assert outcome.status == "failed"
    assert outcome.failures == ("error: RuntimeError: engine down",)


def test_unknown_persona_is_skipped(good_target: LibraryTarget, base_case: dict[str, Any]) -> None:
    outcome = execute_case(_case(base_case, persona="CUST-000123"), good_target)
    assert outcome.status == "skipped"


def test_run_builds_scorecard(
    write_cases: WriteCases, base_case: dict[str, Any], good_target: LibraryTarget
) -> None:
    write_cases(
        "pressure",
        {
            "cases": [
                base_case,
                {**base_case, "id": "PRS-002", "expect": {"required_flags": ["distress_detected"]}},
                {**base_case, "id": "PRS-003", "persona": "CUST-000999"},
            ]
        },
    )
    injection = {**base_case, "id": "INJ-001", "lang": "ta"}
    root = write_cases("prompt_injection", {"cases": [injection]})
    card = run(target=good_target, cases_dir=root, now=NOW, langs=["en"])
    assert card.run_id == "RT-20261012-1030"
    assert card.totals == {"total": 3, "passed": 1, "failed": 1, "skipped": 1}
    assert card.by_category[RedTeamCategory.PRESSURE] == card.totals
    assert card.by_category[RedTeamCategory.BIAS_SWAP]["total"] == 0
    # Every catalogue requirement is listed; one failing case means "not covered" (task 7.2).
    assert len(card.rbi_coverage) == 25 and len(card.bis_coverage) == 17
    assert card.rbi_coverage["RBI-454Z-THREAT"] is False
    failed = next(r for r in card.results if not r.passed)
    assert failed.notes == "target=toy; flags: required flag 'distress_detected' never set"
    Scorecard.model_validate_json(card.model_dump_json())  # contract round-trip


def test_coverage_false_when_only_failures(
    write_cases: WriteCases, base_case: dict[str, Any], bad_target: LibraryTarget
) -> None:
    root = write_cases("pressure", {"cases": [base_case]})
    card = run(target=bad_target, cases_dir=root, now=NOW)
    assert card.rbi_coverage["RBI-454Z-THREAT"] is False


def test_default_target_is_fixture_library(
    write_cases: WriteCases, base_case: dict[str, Any]
) -> None:
    root = write_cases("pressure", {"cases": [base_case]})
    card = run(None, None, cases_dir=root, now=NOW)
    [result] = card.results
    assert result.notes.startswith("target=library:fixtures;")


def test_api_mode_not_implemented_yet() -> None:
    with pytest.raises(NotImplementedError):
        run("http://localhost:8000/api/v1", "token")


def test_committed_cases_run_against_fixtures() -> None:
    card = run(now=NOW)
    assert card.totals["total"] == len(load_cases())


def test_cli_run_writes_scorecard(
    write_cases: WriteCases,
    base_case: dict[str, Any],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = write_cases("pressure", {"cases": [base_case]})
    out = tmp_path / "reports"
    assert main(["run", "--cases-dir", str(root), "--out", str(out), "--lang", "en"]) == 0
    [written] = out.glob("RT-*/scorecard.json")
    card = Scorecard.model_validate(json.loads(written.read_text(encoding="utf-8")))
    assert card.totals["total"] == 1
    assert "pressure" in capsys.readouterr().out


def test_cli_cases(
    write_cases: WriteCases, base_case: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_cases("pressure", {"cases": [base_case]})
    assert main(["cases", "--cases-dir", str(root)]) == 0
    assert "pressure                 en=1 ta=0 hi=0" in capsys.readouterr().out
    write_cases("pressure", {"cases": [{**base_case, "id": "bad"}]}, name="z.yaml")
    assert main(["cases", "--cases-dir", str(root)]) == 1
