"""Model-level fairness import from WS2's reports (task 7.2; IS/ISO/IEC TR 24027:2021).

WS2 writes ``packages/models/reports/metrics.json`` in task 2.5. Its format is not fixed yet,
so this reader is tolerant and only needs a ``fairness`` block shaped like::

    {"model_version": "ew-2026.10",
     "fairness": {
        "early_warning": {                      # model name
          "gender": {                           # protected attribute
            "demographic_parity_diff": 0.03,    # any number of *_diff / *_ratio metrics
            "equal_opportunity_diff": 0.02,
            "groups": {"female": {"n": 1200, "positive_rate": 0.21}, ...}}}}}

Every ``*_diff`` value is compared with ``max_gap`` (absolute difference between groups) and
every ``*_ratio`` value with ``min_ratio`` (the four-fifths rule). A missing or unreadable file
is reported as "not available", never as a pass, and never breaks the red-team run.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from npa_redteam.mappings import repo_root

__all__ = ["METRICS_PATH", "FairnessFinding", "FairnessSummary", "load_fairness"]

METRICS_PATH = Path("packages/models/reports/metrics.json")
DEFAULT_MAX_GAP = 0.1
DEFAULT_MIN_RATIO = 0.8


class FairnessFinding(BaseModel):
    model_config = ConfigDict(frozen=True)

    model: str
    attribute: str
    metric: str
    value: float
    threshold: float
    ok: bool


class FairnessSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Literal["not_available", "invalid", "within_thresholds", "gaps_found"]
    source: str
    model_version: str | None = None
    detail: str = ""
    findings: tuple[FairnessFinding, ...] = ()

    @property
    def gaps(self) -> list[FairnessFinding]:
        return [f for f in self.findings if not f.ok]


def _findings(block: dict[str, Any], max_gap: float, min_ratio: float) -> list[FairnessFinding]:
    out: list[FairnessFinding] = []
    for model, attrs in sorted(block.items()):
        if not isinstance(attrs, dict):
            continue
        for attribute, metrics in sorted(attrs.items()):
            if not isinstance(metrics, dict):
                continue
            for metric, value in sorted(metrics.items()):
                if isinstance(value, bool) or not isinstance(value, int | float):
                    continue
                if metric.endswith("_diff"):
                    ok, threshold = abs(value) <= max_gap, max_gap
                elif metric.endswith("_ratio"):
                    ok, threshold = value >= min_ratio, min_ratio
                else:
                    continue
                out.append(
                    FairnessFinding(
                        model=model,
                        attribute=attribute,
                        metric=metric,
                        value=float(value),
                        threshold=threshold,
                        ok=ok,
                    )
                )
    return out


def load_fairness(
    path: Path | None = None,
    *,
    max_gap: float = DEFAULT_MAX_GAP,
    min_ratio: float = DEFAULT_MIN_RATIO,
) -> FairnessSummary:
    """Read WS2's fairness metrics; see the module docstring for the expected shape."""
    target = path or repo_root() / METRICS_PATH
    source = METRICS_PATH.as_posix() if path is None else path.as_posix()
    if not target.exists():
        return FairnessSummary(
            status="not_available", source=source, detail="WS2 has not published metrics yet"
        )
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return FairnessSummary(status="invalid", source=source, detail=f"unreadable: {exc}")
    block = data.get("fairness") if isinstance(data, dict) else None
    if not isinstance(block, dict):
        return FairnessSummary(status="invalid", source=source, detail="no 'fairness' block")
    findings = _findings(block, max_gap, min_ratio)
    if not findings:
        return FairnessSummary(
            status="invalid", source=source, detail="no *_diff or *_ratio metrics found"
        )
    version = data.get("model_version")
    return FairnessSummary(
        status="gaps_found" if any(not f.ok for f in findings) else "within_thresholds",
        source=source,
        model_version=str(version) if version is not None else None,
        findings=tuple(findings),
    )
