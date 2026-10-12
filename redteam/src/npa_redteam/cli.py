"""``npa-redteam`` command line (``make redteam``).

npa-redteam run   [--suite S]... [--lang L]... [--seed N] [--cases-dir D] [--out DIR]
npa-redteam cases [--cases-dir D]       # validate case files and count them per suite/lang
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from npa_contracts.constants import DEFAULT_SEED
from npa_contracts.enums import Lang, RedTeamCategory
from npa_contracts.models import Scorecard
from npa_redteam.cases import CaseError, load_cases
from npa_redteam.harness import run_report
from npa_redteam.reports import write_run

__all__ = ["main"]


def _summary(card: Scorecard) -> str:
    t = card.totals
    lines = [
        f"{card.run_id}: {t['passed']}/{t['total']} passed, {t['failed']} failed, "
        f"{t['skipped']} skipped",
    ]
    for cat, c in card.by_category.items():
        if c["total"]:
            lines.append(
                f"  {cat.value:<24} {c['passed']:>3} passed {c['failed']:>3} failed "
                f"{c['skipped']:>3} skipped"
            )
    return "\n".join(lines) + "\n"


def _cmd_run(args: argparse.Namespace) -> int:
    report = run_report(
        suites=args.suite,
        langs=args.lang or [lang.value for lang in Lang],
        seed=args.seed,
        cases_dir=args.cases_dir,
    )
    sys.stdout.write(_summary(report.scorecard))
    if args.out:
        folder = write_run(report, Path(args.out))
        sys.stdout.write(f"wrote {folder}\n")
    return 0


def _cmd_cases(args: argparse.Namespace) -> int:
    try:
        cases = load_cases(args.cases_dir)
    except CaseError as exc:
        sys.stderr.write(f"invalid cases: {exc}\n")
        return 1
    counts = Counter((c.suite.value, c.lang.value) for c in cases)
    sys.stdout.write(f"{len(cases)} cases\n")
    for cat in RedTeamCategory:
        per_lang = " ".join(f"{lang.value}={counts[(cat.value, lang.value)]}" for lang in Lang)
        sys.stdout.write(f"  {cat.value:<24} {per_lang}\n")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="npa-redteam", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p_run = sub.add_parser("run", help="run the suites and print the scorecard summary")
    p_run.add_argument("--suite", action="append", choices=[c.value for c in RedTeamCategory])
    p_run.add_argument("--lang", action="append", choices=[lang.value for lang in Lang])
    p_run.add_argument("--seed", type=int, default=int(os.environ.get("SEED", DEFAULT_SEED)))
    p_run.add_argument("--cases-dir", type=Path)
    p_run.add_argument("--out", help="write <out>/<run_id>/{scorecard.json,report.json,summary.md}")
    p_run.set_defaults(func=_cmd_run)
    p_cases = sub.add_parser("cases", help="validate and count the case files")
    p_cases.add_argument("--cases-dir", type=Path)
    p_cases.set_defaults(func=_cmd_cases)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    args = _parser().parse_args(argv)
    code: int = args.func(args)
    return code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
