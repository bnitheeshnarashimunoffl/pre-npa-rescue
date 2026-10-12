"""Task 2.3: segmentation classifier (forgot / can't pay / won't pay / not at risk).

Multiclass LightGBM on the same allowlisted features as the early-warning model (protected
attributes never reach it). Class weighting keeps recall on the small at-risk classes.

**Conservative rule (fair treatment).** Calling someone "won't pay" routes them to the firm
process, so a wrong ``wont_pay`` does more harm than a wrong ``cant_pay``. When ``wont_pay`` is the
top class but its probability is below :data:`WONT_PAY_MIN_CONFIDENCE`, we output the lower-harm
``cant_pay`` and set ``low_confidence``. This follows the fair-treatment and financial-distress
principles in the RBI Responsible Business Conduct Directions (para 454D: documented engagement
before escalation) and IS/ISO/IEC TR 24027 (bias in AI: prefer the less harmful error).

Briefing B4 2.3 words the rule as "``cant_pay`` confidence < 0.5 and ``wont_pay`` is the argmax".
Read literally that fires on almost every ``wont_pay`` (if ``wont_pay`` leads, ``cant_pay`` is
nearly always < 0.5), which would make ``wont_pay`` unreachable; we apply the threshold to the
``wont_pay`` confidence instead.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
import numpy.typing as npt
import pandas as pd
from sklearn.metrics import confusion_matrix, f1_score, recall_score

from npa_contracts.enums import Segment
from npa_contracts.models import SegmentResult
from npa_models.config import ModelSettings
from npa_models.features import (
    DEFAULT_SPLIT,
    FEATURE_COLUMNS,
    TimeSplit,
    build_matrix,
    labelled_splits,
)
from npa_models.registry import ModelBundle, load_bundle, make_model_version, save_bundle

log = logging.getLogger(__name__)

NAME = "segment"
TARGET = "segment_truth"
CLASSES: tuple[str, ...] = tuple(s.value for s in Segment)
WONT_PAY_MIN_CONFIDENCE = 0.5
LOW_CONFIDENCE = "low_confidence"

LGBM_PARAMS: dict[str, Any] = {
    "objective": "multiclass",
    "n_estimators": 300,
    "learning_rate": 0.05,
    "num_leaves": 31,
    "min_child_samples": 20,
    "subsample": 0.8,
    "subsample_freq": 1,
    "colsample_bytree": 0.8,
    "class_weight": "balanced",
    "deterministic": True,
    "force_col_wise": True,
    "verbose": -1,
}


def apply_conservative_rule(
    proba: pd.DataFrame, min_wont_pay: float = WONT_PAY_MIN_CONFIDENCE
) -> pd.DataFrame:
    """Turn class probabilities (columns = :data:`CLASSES`) into ``segment, confidence, flag``.

    ``confidence`` is the probability of the segment that is output, so a relabelled row carries
    its (low) ``cant_pay`` probability.
    """
    missing = set(CLASSES) - set(proba.columns)
    if missing:
        raise KeyError(f"probability columns missing: {sorted(missing)}")
    p = proba.loc[:, list(CLASSES)]
    top = p.idxmax(axis=1)
    top_p = p.max(axis=1)
    relabel = (top == Segment.WONT_PAY.value) & (top_p < min_wont_pay)
    segment = top.where(~relabel, Segment.CANT_PAY.value)
    confidence = top_p.where(~relabel, p[Segment.CANT_PAY.value])
    return pd.DataFrame(
        {"segment": segment, "confidence": confidence, LOW_CONFIDENCE: relabel},
        index=proba.index,
    )


def classification_report(y_true: npt.ArrayLike, y_pred: npt.ArrayLike) -> dict[str, Any]:
    """Confusion matrix (rows = truth, columns = prediction, order :data:`CLASSES`), macro-F1 and
    per-class recall (IS/ISO/IEC TS 4213)."""
    labels = list(CLASSES)
    recall = recall_score(y_true, y_pred, labels=labels, average=None, zero_division=0)
    macro_f1 = f1_score(y_true, y_pred, labels=labels, average="macro", zero_division=0)
    return {
        "labels": labels,
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=labels).tolist(),
        "macro_f1": float(macro_f1),
        "recall": {c: float(r) for c, r in zip(labels, recall, strict=True)},
        "n": len(np.asarray(y_true)),
    }


def _class_proba(model: Any, df: pd.DataFrame) -> pd.DataFrame:
    p = np.asarray(model.predict_proba(build_matrix(df)), dtype=float)
    frame = pd.DataFrame(p, columns=[str(c) for c in model.classes_], index=df.index)
    # A class absent from training gets probability 0.
    return frame.reindex(columns=list(CLASSES), fill_value=0.0)


@dataclass
class SegmentModel:
    bundle: ModelBundle

    @property
    def model_version(self) -> str:
        return self.bundle.model_version

    def predict_proba(self, df: pd.DataFrame) -> pd.DataFrame:
        """Class probabilities, one column per :data:`CLASSES` entry."""
        return _class_proba(self.bundle.estimators["segment"], df)

    def score_frame(self, df: pd.DataFrame) -> pd.DataFrame:
        """``account_id, as_of_month, segment, confidence, low_confidence, p_<class>...``."""
        proba = self.predict_proba(df)
        decided = apply_conservative_rule(proba)
        out = pd.concat([decided, proba.add_prefix("p_")], axis=1)
        out.insert(0, "as_of_month", df["month"].to_numpy())
        out.insert(0, "account_id", df["account_id"].to_numpy())
        return out.reset_index(drop=True)

    def score(self, df: pd.DataFrame) -> list[SegmentResult]:
        frame = self.score_frame(df)
        return [
            SegmentResult(
                account_id=row.account_id,
                segment=Segment(row.segment),
                confidence=float(row.confidence),
                model_version=self.model_version,
            )
            for row in frame.itertuples(index=False)
        ]

    def score_batch(self, features: pd.DataFrame, as_of_month: str) -> list[SegmentResult]:
        rows = features[features["month"] == as_of_month]
        if rows.empty:
            raise ValueError(f"no feature rows for as_of_month={as_of_month}")
        return self.score(rows)

    def save(self, model_dir: Path) -> Path:
        return save_bundle(self.bundle, model_dir)

    @classmethod
    def load(cls, model_dir: Path) -> "SegmentModel":
        return cls(bundle=load_bundle(NAME, model_dir))


def train_frames(
    features: pd.DataFrame,
    labels: pd.DataFrame,
    *,
    seed: int,
    split: TimeSplit = DEFAULT_SPLIT,
) -> SegmentModel:
    """Train the segmentation model and report validation/test metrics (raw and after the rule)."""
    s = labelled_splits(features, labels, (TARGET,), split)
    unknown = set(s.train[TARGET]) - set(CLASSES)
    if unknown:
        raise ValueError(f"unknown segment label(s): {sorted(unknown)}")
    if s.train[TARGET].nunique() < 2:
        raise ValueError("segmentation needs at least two segment classes in the train split")
    model = lgb.LGBMClassifier(**LGBM_PARAMS, random_state=seed)
    model.fit(build_matrix(s.train), s.train[TARGET])

    metrics: dict[str, Any] = {}
    for name, part in (("validation", s.val), ("test", s.test)):
        if part.empty:
            continue
        proba = _class_proba(model, part)
        metrics[f"{name}_raw"] = classification_report(part[TARGET], proba.idxmax(axis=1))
        decided = apply_conservative_rule(proba)
        metrics[name] = classification_report(part[TARGET], decided["segment"])
        metrics[name]["low_confidence_share"] = float(decided[LOW_CONFIDENCE].mean())

    data = pd.concat(s)
    payload = {
        "features": list(FEATURE_COLUMNS),
        "params": LGBM_PARAMS,
        "seed": seed,
        "split": split.__dict__,
        "rows": len(data),
        "class_counts": data[TARGET].value_counts().sort_index().to_dict(),
        "rule": WONT_PAY_MIN_CONFIDENCE,
    }
    bundle = ModelBundle(
        name=NAME,
        model_version=make_model_version("seg-lgbm", payload),
        feature_columns=FEATURE_COLUMNS,
        estimators={"segment": model},
        metadata={
            "seed": seed,
            "split": split.__dict__,
            "classes": list(CLASSES),
            "wont_pay_min_confidence": WONT_PAY_MIN_CONFIDENCE,
            "metrics": metrics,
            "rows": {"train": len(s.train), "validation": len(s.val), "test": len(s.test)},
        },
    )
    log.info(
        "model=%s version=%s macro_f1_test=%s",
        NAME,
        bundle.model_version,
        metrics.get("test", {}).get("macro_f1"),
    )
    return SegmentModel(bundle)


def train(
    features_path: Path, labels_path: Path, settings: ModelSettings | None = None
) -> ModelBundle:
    """Train from parquet files and return the bundle."""
    settings = settings or ModelSettings()
    model = train_frames(
        pd.read_parquet(features_path), pd.read_parquet(labels_path), seed=settings.seed
    )
    return model.bundle
