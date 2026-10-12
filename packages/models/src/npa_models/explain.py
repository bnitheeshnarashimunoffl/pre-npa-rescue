"""Task 2.2: SHAP explanations -> plain-language reason codes in en / ta / hi.

- Per-account SHAP values come from LightGBM's built-in TreeSHAP (``pred_contrib=True``), the
  same algorithm as ``shap.TreeExplainer`` for tree models, on the raw log-odds of the
  early-warning head. Isotonic calibration is monotone, so it does not change which features
  push risk up.
- Features map to reason codes in ``reason_codes.yaml``. Contributions of a code's features are
  summed; a code is shown only when its ``when`` conditions hold on the account's own values,
  so the text is always true for that account. The top 3 positive codes are returned.
- ``weight`` is the code's share of the account's total positive contribution (0..1).
- Raw feature names never appear in the text (IS/ISO/IEC 25059:2023 explainability; A3 fair
  treatment: text describes the account, never the person).
"""

import operator
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from functools import cache
from importlib import resources
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
import numpy.typing as npt
import pandas as pd
import yaml

from npa_contracts.enums import Lang
from npa_contracts.models import ReasonCode
from npa_models.features import FEATURE_COLUMNS

TOP_K = 3
LANGS: tuple[str, ...] = tuple(lang.value for lang in Lang)

_OPS: dict[str, Callable[[Any, Any], Any]] = {
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
    "==": operator.eq,
    "!=": operator.ne,
}
_COND_RE = re.compile(r"^\s*(\w+)\s*(<=|>=|==|!=|<|>)\s*(-?\d+(?:\.\d+)?)\s*$")
_PLACEHOLDER_RE = re.compile(r"{(\w+)}")


class CatalogueError(ValueError):
    """``reason_codes.yaml`` is malformed or doesn't cover the model's features."""


@dataclass(frozen=True)
class Condition:
    feature: str
    op: str
    value: float

    @classmethod
    def parse(cls, text: str) -> "Condition":
        m = _COND_RE.match(text)
        if not m:
            raise CatalogueError(f"bad condition {text!r}; use '<feature> <op> <number>'")
        return cls(m.group(1), m.group(2), float(m.group(3)))

    def mask(self, df: pd.DataFrame) -> npt.NDArray[np.bool_]:
        values = pd.to_numeric(df[self.feature], errors="coerce").astype(float).to_numpy()
        # NaN compares False, so a missing value never triggers a reason.
        return np.asarray(_OPS[self.op](values, self.value), dtype=bool)


@dataclass(frozen=True)
class Param:
    feature: str
    scale: float = 1.0

    def render(self, value: Any) -> int:
        return round(float(value) * self.scale)


@dataclass(frozen=True)
class Reason:
    code: str
    features: tuple[str, ...]
    when: tuple[Condition, ...]
    params: Mapping[str, Param]
    plural: str | None
    text: Mapping[str, Mapping[str, str]]  # lang -> {"one"?, "other"}

    def render(self, row: Mapping[str, Any]) -> dict[str, str]:
        values = {name: p.render(row[p.feature]) for name, p in self.params.items()}
        n = values[self.plural] if self.plural is not None else None
        return {lang: _pick(forms, n).format(**values) for lang, forms in self.text.items()}


def _pick(forms: Mapping[str, str], n: int | None) -> str:
    if n is None:
        return forms["other"]
    if str(n) in forms:
        return forms[str(n)]
    if n == 1 and "one" in forms:
        return forms["one"]
    return forms["other"]


@dataclass(frozen=True)
class Catalogue:
    version: int
    reasons: tuple[Reason, ...]
    not_shown: frozenset[str]
    needs_review: tuple[str, ...]

    @property
    def codes(self) -> tuple[str, ...]:
        return tuple(r.code for r in self.reasons)


def _text_forms(code: str, lang: str, raw: Any) -> dict[str, str]:
    forms = {"other": raw} if isinstance(raw, str) else {str(k): v for k, v in (raw or {}).items()}
    if not isinstance(forms.get("other"), str) or not forms["other"].strip():
        raise CatalogueError(f"{code}: missing {lang!r} text")
    return forms


def _parse_reason(code: str, spec: Mapping[str, Any], allowed: set[str]) -> Reason:
    features = tuple(spec.get("features") or ())
    if not features:
        raise CatalogueError(f"{code}: needs at least one feature")
    when = tuple(Condition.parse(c) for c in spec.get("when") or ())
    params = {
        name: Param(p) if isinstance(p, str) else Param(p["feature"], float(p.get("scale", 1)))
        for name, p in (spec.get("params") or {}).items()
    }
    used = set(features) | {c.feature for c in when} | {p.feature for p in params.values()}
    if unknown := sorted(used - allowed):
        raise CatalogueError(f"{code}: unknown features {unknown}")
    plural = spec.get("plural")
    if plural is not None and plural not in params:
        raise CatalogueError(f"{code}: plural param {plural!r} is not in params")
    raw_text = spec.get("text") or {}
    text = {lang: _text_forms(code, lang, raw_text.get(lang)) for lang in LANGS}
    for lang, forms in text.items():
        for form in forms.values():
            if missing := set(_PLACEHOLDER_RE.findall(form)) - set(params):
                raise CatalogueError(f"{code}/{lang}: unknown placeholders {sorted(missing)}")
            for feature in allowed:
                if re.search(rf"\b{feature}\b", form):
                    raise CatalogueError(f"{code}/{lang}: raw feature name {feature!r} in text")
    return Reason(code, features, when, params, plural, text)


def parse_catalogue(
    data: Mapping[str, Any], feature_columns: Sequence[str] = FEATURE_COLUMNS
) -> Catalogue:
    """Validate a catalogue: every model feature is either explained by a code or not shown."""
    allowed = set(feature_columns)
    reasons = tuple(
        _parse_reason(code, spec, allowed) for code, spec in (data.get("codes") or {}).items()
    )
    if not reasons:
        raise CatalogueError("no reason codes")
    not_shown = frozenset(data.get("not_shown") or {})
    covered = {f for r in reasons for f in r.features}
    if overlap := sorted(covered & not_shown):
        raise CatalogueError(f"features both explained and not shown: {overlap}")
    if uncovered := sorted(allowed - covered - not_shown):
        raise CatalogueError(f"features with no reason code and not in not_shown: {uncovered}")
    return Catalogue(
        version=int(data.get("version", 1)),
        reasons=reasons,
        not_shown=not_shown,
        needs_review=tuple(data.get("needs_review") or ()),
    )


def load_catalogue(path: Path | None = None) -> Catalogue:
    """Load ``reason_codes.yaml`` (the packaged one by default)."""
    if path is None:
        return _packaged_catalogue()
    return parse_catalogue(yaml.safe_load(path.read_text(encoding="utf-8")))


@cache
def _packaged_catalogue() -> Catalogue:
    text = resources.files("npa_models").joinpath("reason_codes.yaml").read_text(encoding="utf-8")
    return parse_catalogue(yaml.safe_load(text))


def shap_values(model: lgb.LGBMClassifier, x: pd.DataFrame) -> pd.DataFrame:
    """Per-row TreeSHAP contributions (log-odds) for each feature; the bias term is dropped."""
    contrib = np.asarray(model.predict(x, pred_contrib=True), dtype=float)
    return pd.DataFrame(contrib[:, : x.shape[1]], columns=x.columns, index=x.index)


def code_scores(contrib: pd.DataFrame, values: pd.DataFrame, catalogue: Catalogue) -> pd.DataFrame:
    """Summed contribution per code, NaN where the code's conditions don't hold."""
    out = {}
    for reason in catalogue.reasons:
        score = contrib[list(reason.features)].sum(axis=1).to_numpy()
        ok = np.ones(len(values), dtype=bool)
        for cond in reason.when:
            ok &= cond.mask(values)
        out[reason.code] = np.where(ok, score, np.nan)
    return pd.DataFrame(out, index=contrib.index)


def top_reasons(
    contrib: pd.DataFrame,
    values: pd.DataFrame,
    catalogue: Catalogue | None = None,
    top_k: int = TOP_K,
) -> list[list[ReasonCode]]:
    """The ``top_k`` codes that push each account's risk up, as contract ``ReasonCode`` objects."""
    if top_k < 1:
        raise ValueError(f"top_k must be >= 1, got {top_k}")
    catalogue = catalogue or load_catalogue()
    by_code = {r.code: r for r in catalogue.reasons}
    scores = code_scores(contrib, values, catalogue)
    total = contrib.clip(lower=0).sum(axis=1).to_numpy()
    matrix = scores.to_numpy()
    # Positive scores only, largest first; ties broken by catalogue order (stable sort).
    ranked = np.argsort(-np.nan_to_num(matrix, nan=-np.inf), axis=1, kind="stable")
    records = values.to_dict("records")
    result: list[list[ReasonCode]] = []
    for i, order in enumerate(ranked):
        reasons = []
        for j in order[:top_k]:
            s = matrix[i, j]
            if not s > 0:
                break
            reason = by_code[scores.columns[j]]
            weight = round(float(s / total[i]), 4) if total[i] > 0 else 0.0
            reasons.append(
                ReasonCode(
                    code=reason.code,
                    weight=min(weight, 1.0),
                    text=reason.render(records[i]),  # type: ignore[arg-type]
                )
            )
        result.append(reasons)
    return result


def explain(
    model: lgb.LGBMClassifier,
    x: pd.DataFrame,
    catalogue: Catalogue | None = None,
    top_k: int = TOP_K,
) -> list[list[ReasonCode]]:
    """SHAP + catalogue in one step for a model input matrix ``x``."""
    return top_reasons(shap_values(model, x), x, catalogue, top_k)
