"""Save and load trained model bundles, and build ``model_version`` strings.

Artifacts live in ``$MODEL_DIR/<name>/`` (gitignored): ``model.joblib`` holds the estimators and
``meta.json`` the version, feature list and training metadata. The version string is carried on
every output object (``RiskScore.model_version`` etc.) for traceability (IS/ISO/IEC 42001:2023
AI inventory; RBI FREE-AI recommendations on model inventory).
"""

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import joblib

from npa_contracts.constants import BUSINESS_TZ
from npa_models.features import assert_no_leakage

MODEL_VERSION_RE = re.compile(r"^[a-z]+(-[a-z0-9]+)*-\d{4}\.\d{2}\.\d{2}-[0-9a-f]{6}$")
_PREFIX_RE = re.compile(r"^[a-z]+(-[a-z0-9]+)*$")
_MODEL_FILE = "model.joblib"
_META_FILE = "meta.json"


def make_model_version(prefix: str, payload: Mapping[str, Any], on: date | None = None) -> str:
    """Return e.g. ``ew-lgbm-2026.10.11-a1b2c3``.

    The suffix is a hash of ``payload`` (features, hyper-parameters, seed, data fingerprint), so
    the same inputs on the same day always give the same version.
    """
    if not _PREFIX_RE.match(prefix):
        raise ValueError(f"prefix must be lowercase words joined by '-', got {prefix!r}")
    day = on or datetime.now(ZoneInfo(BUSINESS_TZ)).date()
    blob = json.dumps(payload, sort_keys=True, default=str).encode()
    digest = hashlib.sha256(blob).hexdigest()[:6]
    return f"{prefix}-{day:%Y.%m.%d}-{digest}"


@dataclass
class ModelBundle:
    """A trained model plus what is needed to use and audit it."""

    name: str
    model_version: str
    feature_columns: tuple[str, ...]
    estimators: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        assert_no_leakage(self.feature_columns)
        if not MODEL_VERSION_RE.match(self.model_version):
            raise ValueError(f"invalid model_version {self.model_version!r}")


def save_bundle(bundle: ModelBundle, model_dir: Path) -> Path:
    """Write ``bundle`` to ``model_dir/<name>/`` and return that directory."""
    out = model_dir / bundle.name
    out.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle.estimators, out / _MODEL_FILE)
    meta = {
        "name": bundle.name,
        "model_version": bundle.model_version,
        "feature_columns": list(bundle.feature_columns),
        "metadata": bundle.metadata,
    }
    (out / _META_FILE).write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
    return out


def load_bundle(name: str, model_dir: Path) -> ModelBundle:
    """Load a bundle saved by :func:`save_bundle`.

    Raises ``FileNotFoundError`` if it has not been trained yet. Only load artifacts this project
    produced: joblib files can execute code when unpickled.
    """
    src = model_dir / name
    meta_path = src / _META_FILE
    if not meta_path.is_file():
        raise FileNotFoundError(
            f"no trained model {name!r} in {model_dir}; run `npa-models train --all` first"
        )
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    estimators = joblib.load(src / _MODEL_FILE)
    return ModelBundle(
        name=meta["name"],
        model_version=meta["model_version"],
        feature_columns=tuple(meta["feature_columns"]),
        estimators=estimators,
        metadata=meta.get("metadata", {}),
    )
