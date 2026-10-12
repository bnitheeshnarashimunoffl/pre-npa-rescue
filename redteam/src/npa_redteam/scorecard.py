"""Compliance scorecard engine (task 7.2).

:func:`build_report` turns one run's results into a :class:`RunReport`:

* ``scorecard``: the contract ``Scorecard`` (A7.3) that WS5 serves and WS6 renders: totals,
  per-category counts, results, and ``rbi_coverage`` / ``bis_coverage`` listing **every**
  requirement in ``mappings.yaml``, covered or not;
* WS7 extras the contract has no field for yet: per-language and per-severity counts, skipped
  cases with reasons, coverage detail with evidence, and WS2's model-level fairness.

Coverage status per requirement:

* ``failing``: at least one red-team case citing it failed (or, for IS/ISO/IEC TR 24027:2021,
  WS2's fairness metrics show a gap). A failure is never hidden by passes elsewhere.
* ``covered``: no failures and at least one passing case; for BIS standards a present
  governance document or report also counts as evidence (briefing 7.2).
* ``partial``: only skipped cases, unrun unit tests or code exist.
* ``gap``: nothing.

The contract booleans are ``status == "covered"``, so a requirement with a failing case is
reported as not covered even if other cases pass (briefing B6: no inflated results).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from npa_contracts.enums import Lang, RedTeamCategory
from npa_contracts.models import RedTeamResult, Scorecard
from npa_redteam.fairness import FairnessSummary, load_fairness
from npa_redteam.mappings import EvidenceRef, Mappings, default_mappings, repo_root

__all__ = [
    "BIAS_STANDARD",
    "CoverageItem",
    "EvidenceStatus",
    "RunReport",
    "SkippedCase",
    "build_report",
]

BIAS_STANDARD = "IS/ISO/IEC TR 24027:2021"
CoverageStatus = Literal["covered", "failing", "partial", "gap"]


@dataclass(frozen=True, slots=True)
class SkippedCase:
    test_id: str
    category: RedTeamCategory
    lang: Lang
    rule_refs: tuple[str, ...]
    bis_refs: tuple[str, ...]
    reason: str


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class EvidenceStatus(_Frozen):
    kind: str
    ref: str
    present: bool


class CoverageItem(_Frozen):
    id: str
    title: str
    group: str  # RBI source or BIS area
    status: CoverageStatus
    covered: bool
    passed: tuple[str, ...]
    failed: tuple[str, ...]
    skipped: tuple[str, ...]
    evidence: tuple[EvidenceStatus, ...]
    redteam: str | None = None
    note: str = ""


class SkippedEntry(_Frozen):
    test_id: str
    category: RedTeamCategory
    lang: Lang
    reason: str


class RunReport(_Frozen):
    scorecard: Scorecard
    target: str
    mappings_version: str
    by_lang: dict[Lang, dict[str, int]]
    failed_by_severity: dict[str, int]
    skipped: tuple[SkippedEntry, ...]
    rbi: tuple[CoverageItem, ...]
    bis: tuple[CoverageItem, ...]
    fairness: FairnessSummary


def _counts(passed: int, failed: int, skipped: int) -> dict[str, int]:
    return {
        "total": passed + failed + skipped,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
    }


def _ids(results: Sequence[RedTeamResult], ref: str, field: str, passed: bool) -> tuple[str, ...]:
    return tuple(
        sorted(r.test_id for r in results if r.passed is passed and ref in getattr(r, field))
    )


def _coverage(
    ref: str,
    *,
    title: str,
    group: str,
    evidence: list[EvidenceRef],
    field: Literal["rule_refs", "bis_refs"],
    results: Sequence[RedTeamResult],
    skipped: Sequence[SkippedCase],
    root: Path,
    doc_counts: bool,
    extra_failure: bool = False,
    redteam: str | None = None,
    note: str = "",
) -> CoverageItem:
    passed = _ids(results, ref, field, True)
    failed = _ids(results, ref, field, False)
    skip = tuple(sorted(s.test_id for s in skipped if ref in getattr(s, field)))
    checked = tuple(
        EvidenceStatus(kind=e.kind, ref=e.ref, present=e.present(root)) for e in evidence
    )
    strong = (
        any(e.present and e.kind in ("doc", "report") for e in checked) if doc_counts else False
    )
    weak = any(e.present for e in checked) or bool(skip)
    status: CoverageStatus
    if failed or extra_failure:
        status = "failing"
    elif passed or strong:
        status = "covered"
    elif weak:
        status = "partial"
    else:
        status = "gap"
    return CoverageItem(
        id=ref,
        title=title,
        group=group,
        status=status,
        covered=status == "covered",
        passed=passed,
        failed=failed,
        skipped=skip,
        evidence=checked,
        redteam=redteam,
        note=note,
    )


def build_report(
    results: Sequence[RedTeamResult],
    skipped: Sequence[SkippedCase] = (),
    *,
    run_id: str,
    created_at: datetime,
    target: str = "",
    mappings: Mappings | None = None,
    root: Path | None = None,
    fairness: FairnessSummary | None = None,
) -> RunReport:
    """Aggregate one run into a :class:`RunReport` (contract scorecard plus WS7 extras)."""
    maps = mappings or default_mappings()
    base = root or repo_root()
    fair = fairness or load_fairness()

    def counts(rs: Sequence[RedTeamResult], sk: Sequence[SkippedCase]) -> dict[str, int]:
        passed = sum(r.passed for r in rs)
        return _counts(passed, len(rs) - passed, len(sk))

    rbi = tuple(
        _coverage(
            ref,
            title=req.title,
            group=req.source,
            evidence=req.evidence(),
            field="rule_refs",
            results=results,
            skipped=skipped,
            root=base,
            doc_counts=False,
            redteam=req.redteam,
            note=req.note,
        )
        for ref, req in maps.rbi.items()
    )

    def bis_evidence(ref: str, evidence: list[EvidenceRef]) -> list[EvidenceRef]:
        # WS2's metrics file only counts as fairness evidence once it parses (load_fairness).
        if ref != BIAS_STANDARD or fair.status in ("within_thresholds", "gaps_found"):
            return evidence
        return [e for e in evidence if e.kind != "report"]

    bis = tuple(
        _coverage(
            ref,
            title=std.themes,
            group=std.area,
            evidence=bis_evidence(ref, std.evidence()),
            field="bis_refs",
            results=results,
            skipped=skipped,
            root=base,
            doc_counts=True,
            extra_failure=ref == BIAS_STANDARD and fair.status == "gaps_found",
        )
        for ref, std in maps.bis.items()
    )
    scorecard = Scorecard(
        run_id=run_id,
        created_at=created_at,
        totals=counts(results, skipped),
        by_category={
            cat: counts(
                [r for r in results if r.category == cat], [s for s in skipped if s.category == cat]
            )
            for cat in RedTeamCategory
        },
        results=list(results),
        rbi_coverage={item.id: item.covered for item in rbi},
        bis_coverage={item.id: item.covered for item in bis},
    )
    failed_sev: Counter[str] = Counter(str(r.severity) for r in results if not r.passed)
    return RunReport(
        scorecard=scorecard,
        target=target,
        mappings_version=maps.version,
        by_lang={
            lang: counts(
                [r for r in results if r.lang == lang], [s for s in skipped if s.lang == lang]
            )
            for lang in Lang
        },
        failed_by_severity={s: failed_sev.get(s, 0) for s in ("critical", "high", "medium", "low")},
        skipped=tuple(
            SkippedEntry(test_id=s.test_id, category=s.category, lang=s.lang, reason=s.reason)
            for s in skipped
        ),
        rbi=rbi,
        bis=bis,
        fairness=fair,
    )
