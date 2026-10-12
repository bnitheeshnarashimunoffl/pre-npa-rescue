"""Run reports on disk (task 7.2).

Each run writes ``<out>/RT-YYYYMMDD-HHMM/``:

* ``scorecard.json``: the contract ``Scorecard`` (what WS5 serves and WS6 renders);
* ``report.json``: the full :class:`~npa_redteam.scorecard.RunReport` (per-language counts,
  coverage detail with evidence, skipped cases, fairness);
* ``summary.md``: the same for people (judges, reviewers, the WS8 deck).

Commit only demo runs against the real system to ``redteam/reports/``; runs against the fixture
fakes prove the harness, not the system, and say so in their summary.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from npa_redteam.scorecard import CoverageItem, RunReport

__all__ = ["render_summary", "write_run"]

_STATUS = {
    "covered": "✅ covered",
    "failing": "❌ failing",
    "partial": "🟡 partial",
    "gap": "⬜ gap",
}
_AREAS = (
    "Govern the AI",
    "Prove it is fair and accurate",
    "Protect customer data",
    "Treat customers well",
    "Include everyone",
)
_MAX_FAILURES = 25


def _pct(passed: int, run: int) -> str:
    return f"{100 * passed / run:.0f}%" if run else "n/a"


def _row(cells: Iterable[object]) -> str:
    return "| " + " | ".join(str(c).replace("|", "\\|") for c in cells) + " |"


def _coverage_rows(items: Iterable[CoverageItem], *, scope: bool) -> list[str]:
    head = ["Requirement", "Status", "Cases (pass/fail/skip)", "Other evidence present"]
    lines = [
        _row(head + (["Red-team scope"] if scope else [])),
        _row(["---"] * (len(head) + scope)),
    ]
    for item in items:
        evidence = [e.ref for e in item.evidence if e.present]
        cells: list[object] = [
            f"`{item.id}` {item.title}",
            _STATUS[item.status],
            f"{len(item.passed)}/{len(item.failed)}/{len(item.skipped)}",
            ", ".join(f"`{e}`" for e in evidence) or "none",
        ]
        if scope:
            cells.append(item.redteam or "")
        lines.append(_row(cells))
    return lines


def render_summary(report: RunReport) -> str:
    card = report.scorecard
    t = card.totals
    run = t["passed"] + t["failed"]
    lines = [
        f"# Red-team run {card.run_id}",
        "",
        f"Created {card.created_at.isoformat()} · target `{report.target}` · "
        f"mappings `{report.mappings_version}`",
        "",
        "> Design alignment, not certification. Counts are the real results of this run:",
        "> failures are listed, skipped cases are shown and are never counted as passes.",
    ]
    if report.target.endswith(":fixtures"):
        lines += [
            ">",
            "> **This run used the fixture fakes, not the real system.** It proves the harness",
            "> works; do not quote its pass rate as a system result.",
        ]
    lines += [
        "",
        f"**{t['passed']}/{run} passed ({_pct(t['passed'], run)})** · {t['failed']} failed · "
        f"{t['skipped']} skipped · {t['total']} cases",
        "",
        "## By suite",
        "",
        _row(["Suite", "Passed", "Failed", "Skipped", "Pass rate"]),
        _row(["---"] * 5),
    ]
    for cat, c in card.by_category.items():
        lines.append(
            _row(
                [
                    cat.value,
                    c["passed"],
                    c["failed"],
                    c["skipped"],
                    _pct(c["passed"], c["passed"] + c["failed"]),
                ]
            )
        )
    lines += [
        "",
        "## By language",
        "",
        _row(["Language", "Passed", "Failed", "Skipped"]),
        _row(["---"] * 4),
    ]
    for lang, c in report.by_lang.items():
        lines.append(_row([lang.value, c["passed"], c["failed"], c["skipped"]]))
    sev = report.failed_by_severity
    lines += [
        "",
        "## Failures",
        "",
        "Failed by severity: " + ", ".join(f"{k} {v}" for k, v in sev.items()),
        "",
    ]
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    failures = sorted(
        (r for r in card.results if not r.passed), key=lambda r: (order[r.severity], r.test_id)
    )
    if failures:
        lines += [_row(["Case", "Severity", "Lang", "Finding"]), _row(["---"] * 4)]
        for r in failures[:_MAX_FAILURES]:
            finding = r.notes.split("; ", 1)[-1]
            lines.append(_row([r.test_id, r.severity, r.lang.value, finding[:200]]))
        if len(failures) > _MAX_FAILURES:
            lines.append(f"\n…and {len(failures) - _MAX_FAILURES} more in `report.json`.")
    else:
        lines.append("No failures.")
    lines += ["", "## RBI requirements", "", *_coverage_rows(report.rbi, scope=True)]
    lines += ["", "## BIS standards", ""]
    for area in _AREAS:
        items = [b for b in report.bis if b.group == area]
        if items:
            lines += [f"### {area}", "", *_coverage_rows(items, scope=False), ""]
    fair = report.fairness
    lines += [
        "## Model fairness (WS2)",
        "",
        f"Source `{fair.source}`: **{fair.status}**" + (f" ({fair.detail})" if fair.detail else ""),
        "",
        f"Thresholds: **primary** `|*_diff| ≤ {fair.max_diff:.2f}` (a gap fails "
        f"IS/ISO/IEC TR 24027:2021) · **secondary** `*_ratio ≥ {fair.min_ratio:.2f}` "
        "(warning only). Set in `mappings.yaml` → `fairness`.",
        "",
    ]
    if fair.findings:
        lines += [
            f"{len(fair.gaps)} primary gap(s), {len(fair.warnings)} secondary warning(s).",
            "",
            _row(["Model", "Attribute", "Metric", "Tier", "Value", "Threshold", "Result"]),
            _row(["---"] * 7),
        ]
        for f in fair.findings:
            result = "ok" if f.ok else ("**gap**" if f.tier == "primary" else "warning")
            lines.append(
                _row(
                    [
                        f.model,
                        f.attribute,
                        f.metric,
                        f.tier,
                        f"{f.value:.3f}",
                        f"{f.threshold:.2f}",
                        result,
                    ]
                )
            )
    if report.skipped:
        lines += ["", "## Skipped", ""]
        reasons: dict[str, list[str]] = {}
        for s in report.skipped:
            reasons.setdefault(s.reason, []).append(s.test_id)
        lines += [f"- {reason}: {', '.join(ids)}" for reason, ids in sorted(reasons.items())]
    return "\n".join(lines) + "\n"


def write_run(report: RunReport, out_dir: Path) -> Path:
    """Write ``scorecard.json``, ``report.json`` and ``summary.md``; return the run folder."""
    folder = out_dir / report.scorecard.run_id
    folder.mkdir(parents=True, exist_ok=True)
    files = {
        "scorecard.json": report.scorecard.model_dump_json(indent=2) + "\n",
        "report.json": report.model_dump_json(indent=2) + "\n",
        "summary.md": render_summary(report),
    }
    for name, text in files.items():
        (folder / name).write_text(text, encoding="utf-8", newline="\n")
    return folder
