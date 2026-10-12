"""Attack harness entry point (task 7.1).

``run(...)`` is called by WS5 from ``POST /redteam/runs`` and by ``npa-redteam run``. Keep its
signature stable; new options are keyword-only.

Modes:

* **Library mode** (``api_base_url=None``): providers are called in-process. Until WS3 and WS4
  merge, the default target is :meth:`LibraryTarget.from_fixtures`; pass ``target=`` to attack
  real providers.
* **API mode** (``api_base_url`` set): the real HTTP API. Planned for phase 2
  (``ws7/feat/api-mode-and-demo-run``); it raises ``NotImplementedError`` until then.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from npa_contracts.constants import BUSINESS_TZ, DEFAULT_SEED
from npa_contracts.enums import Lang, RedTeamCategory
from npa_contracts.models import RedTeamResult, Scorecard
from npa_redteam.cases import AttackCase, load_cases
from npa_redteam.fakes import UnknownPersonaError
from npa_redteam.judges import Lexicon, default_lexicon
from npa_redteam.scorecard import build_scorecard
from npa_redteam.suites import SUITES
from npa_redteam.targets import LibraryTarget, Target

__all__ = ["CaseOutcome", "UnsupportedCaseError", "execute_case", "new_run_id", "run"]

log = logging.getLogger(__name__)


class UnsupportedCaseError(Exception):
    """The target cannot run this case (for example an API-only probe in library mode)."""


@dataclass(frozen=True, slots=True)
class CaseOutcome:
    case: AttackCase
    status: Literal["passed", "failed", "skipped"]
    input: str
    output: str
    failures: tuple[str, ...]


def new_run_id(now: datetime) -> str:
    """``RT-YYYYMMDD-HHMM`` in IST (A7.0 ID format)."""
    return now.astimezone(ZoneInfo(BUSINESS_TZ)).strftime("RT-%Y%m%d-%H%M")


def execute_case(case: AttackCase, target: Target, lexicon: Lexicon | None = None) -> CaseOutcome:
    """Run one case. Target errors count as failures; unsupported cases are skipped."""
    input_text = "\n---\n".join(t.text for t in case.turns)
    try:
        execution = SUITES[case.suite].execute(case, target, lexicon or default_lexicon())
    except (UnsupportedCaseError, UnknownPersonaError) as exc:
        return CaseOutcome(case, "skipped", input_text, "", (f"skipped: {exc}",))
    except Exception as exc:  # the system under test crashed: that is a finding
        log.warning("redteam case=%s error=%r", case.id, exc)
        return CaseOutcome(case, "failed", input_text, "", (f"error: {type(exc).__name__}: {exc}",))
    status: Literal["passed", "failed"] = "failed" if execution.failures else "passed"
    return CaseOutcome(case, status, execution.input, execution.output, tuple(execution.failures))


def _result(outcome: CaseOutcome, run_id: str, target: Target) -> RedTeamResult:
    case = outcome.case
    detail = "; ".join(outcome.failures) or "all checks passed"
    return RedTeamResult(
        test_id=case.id,
        run_id=run_id,
        category=case.suite,
        lang=case.lang,
        input=outcome.input,
        output=outcome.output,
        passed=outcome.status == "passed",
        severity=case.severity,
        rule_refs=list(case.rule_refs),
        bis_refs=list(case.bis_refs),
        notes=f"target={target.name}; {detail}",
    )


def run_cases(
    cases: Sequence[AttackCase],
    target: Target,
    *,
    run_id: str,
    created_at: datetime,
    lexicon: Lexicon | None = None,
) -> Scorecard:
    """Execute ``cases`` against ``target`` and build the scorecard."""
    results: list[RedTeamResult] = []
    skipped: Counter[RedTeamCategory] = Counter()
    for case in cases:
        outcome = execute_case(case, target, lexicon)
        if outcome.status == "skipped":
            skipped[case.suite] += 1
            continue
        results.append(_result(outcome, run_id, target))
    log.info(
        "redteam run_id=%s target=%s results=%d skipped=%d",
        run_id,
        target.name,
        len(results),
        sum(skipped.values()),
    )
    return build_scorecard(results, run_id=run_id, created_at=created_at, skipped=skipped)


def run(
    api_base_url: str | None = None,
    token: str | None = None,
    suites: Iterable[RedTeamCategory | str] | None = None,
    langs: Iterable[Lang | str] = ("en", "ta", "hi"),
    seed: int = DEFAULT_SEED,
    *,
    target: Target | None = None,
    cases_dir: Path | None = None,
    now: datetime | None = None,
    lexicon: Lexicon | None = None,
) -> Scorecard:
    """Run the red-team suites and return a :class:`Scorecard`.

    ``suites=None`` runs all six. ``target`` overrides the mode chosen from ``api_base_url``.
    """
    if target is None:
        if api_base_url:
            raise NotImplementedError("API mode is not implemented yet; use library mode")
        target = LibraryTarget.from_fixtures(seed=seed)
    created_at = now or datetime.now(UTC)
    cases = load_cases(cases_dir, suites=suites, langs=langs)
    return run_cases(
        cases, target, run_id=new_run_id(created_at), created_at=created_at, lexicon=lexicon
    )
