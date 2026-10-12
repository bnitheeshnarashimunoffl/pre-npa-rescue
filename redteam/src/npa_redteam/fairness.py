"""Model-level fairness import from WS2's reports (task 7.2; IS/ISO/IEC TR 24027:2021).

WS2 writes ``packages/models/reports/metrics.json`` in task 2.5. Its format is not fixed yet,
so this reader is tolerant and only needs a ``fairness`` block shaped like::

    {"model_version": "ew-2026.10",
     "fairness": {
        "early_warning": {                      # model name
          "gender": {                           # protected attribute
            "demographic_parity_diff": 0.03,    # any number of *_diff / *_ratio metrics
            "equal_opportunity_diff": 0.02,
            "disparate_impact_ratio": 0.94,
            "groups": {"female": {"n": 1200, "positive_rate": 0.21}, ...}}}}}

Thresholds come from ``mappings.yaml`` (``fairness:``):

* **primary**: every ``*_diff`` (absolute difference between groups) above ``max_diff``
  (project value 0.05) is a gap; any gap marks IS/ISO/IEC TR 24027:2021 as failing;
* **secondary**: every ``*_ratio`` below ``min_ratio`` (four-fifths rule, 0.8) is reported as
  a warning but does not fail the standard on its own.

A missing or unreadable file is reported as "not available", never as a pass, and never breaks
the red-team run.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from npa_redteam.mappings import repo_root

__all__ = [
    "DEFAULT_MAX_DIFF",
    "DEFAULT_MIN_RATIO",
    "METRICS_PATH",
    "FairnessFinding",
    "FairnessSummary",
    "load_fairness",
]

METRICS_PATH = Path("packages/models/reports/metrics.json")
DEFAULT_MAX_DIFF = 0.05
DEFAULT_MIN_RATIO = 0.8
Status = Literal["not_available", "invalid", "within_thresholds", "gaps_found"]


class FairnessFinding(BaseModel):
    model_config = ConfigDict(frozen=True)

    model: str
    attribute: str
    metric: str
    value: float
    threshold: float
    ok: bool
    tier: Literal["primary", "secondary"] = "primary"


class FairnessSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Status
    source: str
    max_diff: float = DEFAULT_MAX_DIFF
    min_ratio: float = DEFAULT_MIN_RATIO
    model_version: str | None = None
    detail: str = ""
    findings: tuple[FairnessFinding, ...] = ()

    @property
    def gaps(self) -> list[FairnessFinding]:
        """Primary findings over threshold: these fail IS/ISO/IEC TR 24027:2021."""
        return [f for f in self.findings if not f.ok and f.tier == "primary"]

    @property
    def warnings(self) -> list[FairnessFinding]:
        """Secondary findings over threshold: reported, not failing."""
        return [f for f in self.findings if not f.ok and f.tier == "secondary"]


def _findings(block: dict[str, Any], max_diff: float, min_ratio: float) -> list[FairnessFinding]:
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
                tier: Literal["primary", "secondary"]
                if metric.endswith("_diff"):
                    ok, threshold, tier = abs(value) <= max_diff, max_diff, "primary"
                elif metric.endswith("_ratio"):
                    ok, threshold, tier = value >= min_ratio, min_ratio, "secondary"
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
                        tier=tier,
                    )
                )
    return out


def load_fairness(
    path: Path | None = None,
    *,
    max_diff: float = DEFAULT_MAX_DIFF,
    min_ratio: float = DEFAULT_MIN_RATIO,
) -> FairnessSummary:
    """Read WS2's fairness metrics; see the module docstring for the expected shape."""
    target = path or repo_root() / METRICS_PATH
    source = METRICS_PATH.as_posix() if path is None else path.as_posix()

    def summary(status: Status, detail: str = "", **extra: Any) -> FairnessSummary:
        return FairnessSummary(
            status=status,
            source=source,
            max_diff=max_diff,
            min_ratio=min_ratio,
            detail=detail,
            **extra,
        )

    if not target.exists():
        return summary("not_available", "WS2 has not published metrics yet")
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return summary("invalid", f"unreadable: {exc}")
    block = data.get("fairness") if isinstance(data, dict) else None
    if not isinstance(block, dict):
        return summary("invalid", "no 'fairness' block")
    findings = _findings(block, max_diff, min_ratio)
    if not findings:
        return summary("invalid", "no *_diff or *_ratio metrics found")
    version = data.get("model_version")
    gaps = any(not f.ok and f.tier == "primary" for f in findings)
    return summary(
        "gaps_found" if gaps else "within_thresholds",
        model_version=str(version) if version is not None else None,
        findings=tuple(findings),
    )
