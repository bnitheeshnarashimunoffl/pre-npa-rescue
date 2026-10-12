from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from npa_contracts.enums import Lang, RedTeamCategory
from npa_redteam.cases import CaseError, ConversationCase, default_cases_dir, load_cases

WriteCases = Callable[..., Path]


def test_loads_case_with_file_defaults(write_cases: WriteCases, base_case: dict[str, Any]) -> None:
    persona = base_case.pop("persona")
    root = write_cases("pressure", {"defaults": {"persona": persona}, "cases": [base_case]})
    [case] = load_cases(root)
    assert isinstance(case, ConversationCase)
    assert case.suite is RedTeamCategory.PRESSURE
    assert case.persona == persona
    assert case.expect.offers == "within_policy"  # baseline expectations by default
    assert case.turn_lang(case.turns[0]) is Lang.EN


def test_filters_by_suite_and_lang(write_cases: WriteCases, base_case: dict[str, Any]) -> None:
    write_cases("pressure", {"cases": [base_case, {**base_case, "id": "PRS-002", "lang": "ta"}]})
    root = write_cases("prompt_injection", {"cases": [{**base_case, "id": "INJ-001"}]})
    assert [c.id for c in load_cases(root)] == ["INJ-001", "PRS-001", "PRS-002"]
    assert [c.id for c in load_cases(root, suites=["pressure"], langs=["ta"])] == ["PRS-002"]
    assert load_cases(root, langs=[Lang.HI]) == []


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"id": "INJ-001"}, "must look like PRS-001"),
        ({"id": "PRS-1"}, "must look like PRS-001"),
        ({"rule_refs": ["RBI-MADE-UP"]}, "unknown rule_refs"),
        ({"bis_refs": ["ISO 42001"]}, "unknown bis_refs"),
        ({"turns": []}, "turns"),
        ({"expect": {"forbidden_patterns": ["("]}}, "invalid regex"),
        ({"expect": {"unknown": True}}, "unknown"),
        ({"suite": "bias_swap", "id": "BIAS-001"}, "outside its folder"),
    ],
)
def test_invalid_case_rejected(
    write_cases: WriteCases, base_case: dict[str, Any], change: dict[str, Any], message: str
) -> None:
    root = write_cases("pressure", {"cases": [{**base_case, **change}]})
    with pytest.raises(CaseError, match=message):
        load_cases(root)


def test_duplicate_ids_rejected(write_cases: WriteCases, base_case: dict[str, Any]) -> None:
    write_cases("pressure", {"cases": [base_case]}, name="a.yaml")
    root = write_cases("pressure", {"cases": [base_case]}, name="b.yaml")
    with pytest.raises(CaseError, match="duplicate case id PRS-001"):
        load_cases(root)


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("cases: [", "invalid YAML"),
        ("- just a list", "'cases' list"),
        ("cases: []\nextra: 1", "unknown top-level keys"),
        ("cases: [1]", "must be a mapping"),
    ],
)
def test_malformed_files_rejected(tmp_path: Path, content: str, message: str) -> None:
    (tmp_path / "pressure").mkdir()
    (tmp_path / "pressure" / "bad.yaml").write_text(content, encoding="utf-8")
    with pytest.raises(CaseError, match=message):
        load_cases(tmp_path)


def test_unknown_suite_folder_rejected(tmp_path: Path) -> None:
    (tmp_path / "jailbreaks").mkdir()
    (tmp_path / "jailbreaks" / "x.yaml").write_text("cases: []", encoding="utf-8")
    with pytest.raises(CaseError, match="not a red-team suite"):
        load_cases(tmp_path)


def test_default_cases_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    assert default_cases_dir().parts[-2:] == ("redteam", "cases")
    monkeypatch.setenv("REDTEAM_CASES_DIR", str(tmp_path))
    assert default_cases_dir() == tmp_path


def test_committed_cases_are_valid() -> None:
    load_cases()  # raises CaseError if any committed case file is malformed
