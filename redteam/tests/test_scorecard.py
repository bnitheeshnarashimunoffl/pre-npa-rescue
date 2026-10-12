from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from npa_contracts.enums import Lang, RedTeamCategory
from npa_contracts.models import RedTeamResult, Scorecard
from npa_redteam.cases import load_cases
from npa_redteam.fairness import FairnessFinding, FairnessSummary, load_fairness
from npa_redteam.mappings import EvidenceRef, Mappings, default_mappings, repo_root
from npa_redteam.reports import render_summary, write_run
from npa_redteam.scorecard import BIAS_STANDARD, RunReport, SkippedCase, build_report

NOW = datetime(2026, 10, 12, 5, 0, tzinfo=UTC)
NO_FAIRNESS = FairnessSummary(status="not_available", source="x")
MAPS = Mappings.model_validate(
    {
        "version": "t",
        "rbi": {
            "R-A": {"title": "a", "source": "s", "redteam": "in_scope"},
            "R-B": {
                "title": "b",
                "source": "s",
                "redteam": "out_of_scope",
                "tests": ["t.py::test_ok"],
            },
            "R-C": {"title": "c", "source": "s", "redteam": "planned", "docs": ["missing.md"]},
        },
        "bis": {
            "S-DOC": {"area": "Govern the AI", "themes": "t", "docs": ["doc.md"]},
            "S-CODE": {"area": "Include everyone", "themes": "t", "code": ["code.py"]},
            BIAS_STANDARD: {
                "area": "Prove it is fair and accurate",
                "themes": "t",
                "reports": ["metrics.json"],
            },
        },
    }
)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "t.py").write_text("def test_ok():\n    pass\n", encoding="utf-8")
    (tmp_path / "doc.md").write_text("# doc", encoding="utf-8")
    (tmp_path / "code.py").write_text("", encoding="utf-8")
    (tmp_path / "metrics.json").write_text("{}", encoding="utf-8")
    return tmp_path


def _result(
    test_id: str, passed: bool, rules: list[str], bis: list[str], **kw: object
) -> RedTeamResult:
    data: dict[str, object] = {
        "test_id": test_id,
        "run_id": "RT-20261012-1030",
        "category": "pressure",
        "lang": "en",
        "input": "i",
        "output": "o",
        "passed": passed,
        "severity": "high",
        "rule_refs": rules,
        "bis_refs": bis,
        "notes": "target=toy; finding | with pipe",
    }
    return RedTeamResult.model_validate({**data, **kw})


def _report(
    results: list[RedTeamResult],
    root: Path,
    *,
    skipped: list[SkippedCase] | None = None,
    fairness: FairnessSummary = NO_FAIRNESS,
    target: str = "toy",
) -> RunReport:
    return build_report(
        results,
        skipped or [],
        run_id="RT-20261012-1030",
        created_at=NOW,
        target=target,
        mappings=MAPS,
        root=root,
        fairness=fairness,
    )


def test_every_requirement_listed_and_statuses(root: Path) -> None:
    skip = SkippedCase("PRS-009", RedTeamCategory.PRESSURE, Lang.TA, ("R-C",), (), "no API")
    report = _report([_result("PRS-001", True, ["R-A"], ["S-DOC"])], root, skipped=[skip])
    rbi = {i.id: i for i in report.rbi}
    assert rbi["R-A"].status == "covered" and rbi["R-A"].passed == ("PRS-001",)
    assert rbi["R-B"].status == "partial"  # unit test exists but a red-team pass is required
    assert rbi["R-C"].status == "partial" and rbi["R-C"].skipped == ("PRS-009",)
    assert not rbi["R-C"].evidence[0].present
    assert report.scorecard.rbi_coverage == {"R-A": True, "R-B": False, "R-C": False}
    bis = {i.id: i for i in report.bis}
    assert bis["S-DOC"].status == "covered"
    assert bis["S-CODE"].status == "partial"  # code alone is not BIS evidence
    assert bis[BIAS_STANDARD].status == "gap"  # metrics file exists but WS2 data not usable


def test_one_failure_means_not_covered(root: Path) -> None:
    report = _report(
        [_result("PRS-001", True, ["R-A"], []), _result("PRS-002", False, ["R-A"], ["S-DOC"])], root
    )
    item = next(i for i in report.rbi if i.id == "R-A")
    assert item.status == "failing" and item.failed == ("PRS-002",)
    assert report.scorecard.rbi_coverage["R-A"] is False
    assert report.scorecard.bis_coverage["S-DOC"] is False  # docs do not hide a failing case


def test_gap_when_nothing(tmp_path: Path) -> None:
    report = _report([], tmp_path)
    assert {i.id: i.status for i in report.rbi} == {"R-A": "gap", "R-B": "gap", "R-C": "gap"}


def test_fairness_feeds_the_bias_standard(root: Path) -> None:
    ok = FairnessSummary(
        status="within_thresholds",
        source="m",
        findings=(
            FairnessFinding(
                model="ew", attribute="gender", metric="dp_diff", value=0.01, threshold=0.1, ok=True
            ),
        ),
    )
    assert {i.id: i.status for i in _report([], root, fairness=ok).bis}[BIAS_STANDARD] == "covered"
    gaps = ok.model_copy(update={"status": "gaps_found"})
    assert {i.id: i.status for i in _report([], root, fairness=gaps).bis}[
        BIAS_STANDARD
    ] == "failing"


def test_counts_by_category_language_and_severity(root: Path) -> None:
    results = [
        _result("PRS-001", True, ["R-A"], []),
        _result("PRS-002", False, ["R-A"], [], lang="ta", severity="critical"),
        _result("INJ-001", False, ["R-A"], [], category="prompt_injection", lang="hi"),
    ]
    skip = SkippedCase("PRIV-007", RedTeamCategory.PRIVACY_EXTRACTION, Lang.EN, (), (), "api")
    report = _report(results, root, skipped=[skip])
    card = report.scorecard
    assert card.totals == {"total": 4, "passed": 1, "failed": 2, "skipped": 1}
    assert set(card.by_category) == set(RedTeamCategory)
    assert card.by_category[RedTeamCategory.PRIVACY_EXTRACTION]["skipped"] == 1
    assert report.by_lang[Lang.EN] == {"total": 2, "passed": 1, "failed": 0, "skipped": 1}
    assert report.failed_by_severity == {"critical": 1, "high": 1, "medium": 0, "low": 0}
    Scorecard.model_validate_json(card.model_dump_json())  # still the contract


def test_reports_written_and_summary_is_honest(root: Path, tmp_path: Path) -> None:
    report = _report([_result("PRS-002", False, ["R-A"], [])], root, target="library:fixtures")
    folder = write_run(report, tmp_path / "out")
    assert folder.name == "RT-20261012-1030"
    assert {p.name for p in folder.iterdir()} == {"scorecard.json", "report.json", "summary.md"}
    Scorecard.model_validate_json((folder / "scorecard.json").read_text(encoding="utf-8"))
    assert json.loads((folder / "report.json").read_text(encoding="utf-8"))["target"] == (
        "library:fixtures"
    )
    summary = render_summary(report)
    assert "fixture fakes, not the real system" in summary
    assert "finding \\| with pipe" in summary  # table cells stay intact
    assert "❌ failing" in summary and "Design alignment, not certification" in summary


def test_evidence_presence(root: Path) -> None:
    assert EvidenceRef(kind="test", ref="t.py::test_ok").present(root)
    assert not EvidenceRef(kind="test", ref="t.py::test_missing").present(root)
    assert not EvidenceRef(kind="doc", ref="nope.md").present(root)
    assert EvidenceRef(kind="code", ref="t.py").present(root)


# --- the real catalogue ------------------------------------------------------------------------

CASES = load_cases()
CITED_RBI = {r for c in CASES for r in c.rule_refs}
CITED_BIS = {b for c in CASES for b in c.bis_refs}


def test_catalogue_matches_governance_lists() -> None:
    maps = default_mappings()
    assert len(maps.rbi) == 24 and len(maps.bis) == 17
    assert all(" " in std and std.startswith("IS") for std in maps.bis)  # human-readable form


@pytest.mark.parametrize("ref", sorted(default_mappings().rbi))
def test_red_team_scope_matches_the_cases(ref: str) -> None:
    req = default_mappings().rbi[ref]
    if req.redteam == "in_scope":
        assert ref in CITED_RBI, f"{ref} is in_scope but no case cites it"
    else:
        assert ref not in CITED_RBI, f"{ref} is cited by cases; mark it in_scope"
        assert req.note, f"{ref} needs a note explaining its scope"


def test_every_bis_standard_has_some_evidence_route() -> None:
    for std, item in default_mappings().bis.items():
        assert item.evidence() or std in CITED_BIS, std


def test_evidence_paths_on_main_resolve() -> None:
    """Evidence already on main must be spelled correctly (others land with their PRs)."""
    ref = EvidenceRef(
        kind="test", ref="packages/contracts/tests/test_constants_enums.py::test_bucket_for_dpd"
    )
    assert ref.present(repo_root())


def test_fairness_reader(tmp_path: Path) -> None:
    assert load_fairness(tmp_path / "none.json").status == "not_available"
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert load_fairness(bad).status == "invalid"
    bad.write_text('{"fairness": {"ew": {"gender": {"n": 3}}}}', encoding="utf-8")
    assert load_fairness(bad).detail == "no *_diff or *_ratio metrics found"
    good = tmp_path / "metrics.json"
    good.write_text(
        json.dumps(
            {
                "model_version": "ew-1",
                "fairness": {
                    "early_warning": {
                        "gender": {
                            "demographic_parity_diff": -0.04,
                            "disparate_impact_ratio": 0.92,
                            "groups": {"female": {"n": 10}},
                        },
                        "region": {"equal_opportunity_diff": 0.15},
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    summary = load_fairness(good)
    assert summary.status == "gaps_found" and summary.model_version == "ew-1"
    assert [(f.attribute, f.metric) for f in summary.gaps] == [("region", "equal_opportunity_diff")]
    assert len(summary.findings) == 3
