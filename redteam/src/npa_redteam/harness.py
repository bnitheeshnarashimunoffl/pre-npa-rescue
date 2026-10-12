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
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from npa_contracts.constants import BUSINESS_TZ, DEFAULT_SEED
from npa_contracts.enums import Lang, RedTeamCategory
from npa_contracts.models import RedTeamResult, Scorecard
from npa_redteam.cases import AttackCase, ConversationCase, load_cases
from npa_redteam.fairness import FairnessSummary
from npa_redteam.fakes import UnknownPersonaError
from npa_redteam.judges import Lexicon, default_lexicon
from npa_redteam.llm_judge import LlmJudge
from npa_redteam.mappings import Mappings
from npa_redteam.scorecard import RunReport, SkippedCase, build_report
from npa_redteam.suites import SUITES
from npa_redteam.targets import LibraryTarget, Target, UnsupportedCaseError

__all__ = [
    "CaseOutcome",
    "UnsupportedCaseError",
    "execute_case",
    "new_run_id",
    "run",
    "run_cases",
    "run_report",
]

log = logging.getLogger(__name__)


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


def execute_case(
    case: AttackCase,
    target: Target,
    lexicon: Lexicon | None = None,
    llm_judge: LlmJudge | None = None,
) -> CaseOutcome:
    """Run one case. Target errors count as failures; unsupported cases are skipped.

    With ``llm_judge`` set, cases with ``expect.min_judge_score`` are also scored by the LLM.
    """
    input_text = case.input_text()
    try:
        execution = SUITES[case.suite].execute(case, target, lexicon or default_lexicon())
    except (UnsupportedCaseError, UnknownPersonaError) as exc:
        return CaseOutcome(case, "skipped", input_text, "", (f"skipped: {exc}",))
    except Exception as exc:  # the system under test crashed: that is a finding
        log.warning("redteam case=%s error=%r", case.id, exc)
        return CaseOutcome(case, "failed", input_text, "", (f"error: {type(exc).__name__}: {exc}",))
    failures = list(execution.failures)
    minimum = case.expect.min_judge_score if isinstance(case, ConversationCase) else None
    if llm_judge is not None and minimum is not None:
        failures += llm_judge.failures(
            title=case.title,
            lang=case.lang.value,
            customer=execution.input,
            bot=execution.output,
            minimum=minimum,
        )
    status: Literal["passed", "failed"] = "failed" if failures else "passed"
    return CaseOutcome(case, status, execution.input, execution.output, tuple(failures))


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
    llm_judge: LlmJudge | None = None,
    mappings: Mappings | None = None,
    root: Path | None = None,
    fairness: FairnessSummary | None = None,
) -> RunReport:
    """Execute ``cases`` against ``target`` and build the run report (task 7.2)."""
    results: list[RedTeamResult] = []
    skipped: list[SkippedCase] = []
    for case in cases:
        outcome = execute_case(case, target, lexicon, llm_judge)
        if outcome.status == "skipped":
            reason = outcome.failures[0].removeprefix("skipped: ") if outcome.failures else ""
            skipped.append(
                SkippedCase(case.id, case.suite, case.lang, case.rule_refs, case.bis_refs, reason)
            )
            continue
        results.append(_result(outcome, run_id, target))
    log.info(
        "redteam run_id=%s target=%s results=%d skipped=%d",
        run_id,
        target.name,
        len(results),
        len(skipped),
    )
    return build_report(
        results,
        skipped,
        run_id=run_id,
        created_at=created_at,
        target=target.name,
        mappings=mappings,
        root=root,
        fairness=fairness,
    )


def run_report(
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
    llm_judge: LlmJudge | None = None,
    fairness: FairnessSummary | None = None,
) -> RunReport:
    """Like :func:`run`, but return the full :class:`RunReport` (scorecard plus WS7 extras)."""
    if target is None:
        if api_base_url:
            raise NotImplementedError("API mode is not implemented yet; use library mode")
        target = LibraryTarget.from_fixtures(seed=seed)
    created_at = now or datetime.now(UTC)
    cases = load_cases(cases_dir, suites=suites, langs=langs)
    return run_cases(
        cases,
        target,
        run_id=new_run_id(created_at),
        created_at=created_at,
        lexicon=lexicon,
        llm_judge=llm_judge,
        fairness=fairness,
    )


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
    llm_judge: LlmJudge | None = None,
) -> Scorecard:
    """Run the red-team suites and return a :class:`Scorecard` (stable entry point for WS5).

    ``suites=None`` runs all six. ``target`` overrides the mode chosen from ``api_base_url``.
    ``llm_judge`` is off by default (CI); demo runs pass one built on a real ``LLMClient``.
    """
    return run_report(
        api_base_url,
        token,
        suites,
        langs,
        seed,
        target=target,
        cases_dir=cases_dir,
        now=now,
        lexicon=lexicon,
        llm_judge=llm_judge,
    ).scorecard
