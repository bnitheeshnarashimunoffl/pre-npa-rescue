"""Compliance scorecard (contract A7.3 ``Scorecard``).

Task 7.1 version: totals, per-category counts and coverage computed from the results' own
``rule_refs`` / ``bis_refs``. Task 7.2 extends this with ``mappings.yaml`` (governance
documents as evidence, every requirement listed even when uncovered), per-language breakdowns
and WS2's model fairness metrics.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime

from npa_contracts.enums import RedTeamCategory
from npa_contracts.models import RedTeamResult, Scorecard

__all__ = ["build_scorecard"]


def _counts(results: Sequence[RedTeamResult], skipped: int) -> dict[str, int]:
    passed = sum(r.passed for r in results)
    return {
        "total": len(results) + skipped,
        "passed": passed,
        "failed": len(results) - passed,
        "skipped": skipped,
    }


def build_scorecard(
    results: Sequence[RedTeamResult],
    *,
    run_id: str,
    created_at: datetime,
    skipped: Mapping[RedTeamCategory, int] | None = None,
) -> Scorecard:
    """Aggregate results into a :class:`Scorecard`.

    A requirement or standard counts as covered when at least one **passed** result cites it.
    Skipped cases (the target could not run them) count towards ``total`` but are neither
    passed nor failed, so the pass rate is never inflated by leaving cases out.
    """
    skipped = skipped or {}
    by_category = {
        cat: _counts([r for r in results if r.category == cat], skipped.get(cat, 0))
        for cat in RedTeamCategory
    }
    rbi = sorted({ref for r in results for ref in r.rule_refs})
    bis = sorted({ref for r in results for ref in r.bis_refs})
    return Scorecard(
        run_id=run_id,
        created_at=created_at,
        totals=_counts(results, sum(skipped.values())),
        by_category=by_category,
        results=list(results),
        rbi_coverage={ref: any(r.passed and ref in r.rule_refs for r in results) for ref in rbi},
        bis_coverage={ref: any(r.passed and ref in r.bis_refs for r in results) for ref in bis},
    )
