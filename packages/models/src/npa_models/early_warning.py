"""Task 2.1: early-warning model (roll forward to the next delinquency bucket in 30-60 days).

- LightGBM with class weighting and monotonic constraints on features whose direction is
  obviously true (a longer minimum-due-only streak never lowers risk), so explanations stay
  sensible (IS/ISO/IEC 25059:2023 explainability/controllability).
- Logistic-regression baseline trained on the same split, for comparison.
- Isotonic calibration on the validation months, so ``p_roll_forward`` behaves like a
  probability (IS/ISO/IEC TS 4213 calibration).
- Secondary head for ``reaches_npa_90d`` (RBI: card NPA when min due unpaid > 90 days).
- Time-based split only (:mod:`npa_models.features`); protected attributes never reach it.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
import numpy.typing as npt
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from npa_contracts.enums import RiskBand
from npa_contracts.models import RiskScore
from npa_models.config import ModelSettings
from npa_models.features import (
    CATEGORICAL_FEATURES,
    DEFAULT_SPLIT,
    FEATURE_COLUMNS,
    NUMERIC_FEATURES,
    OCCUPATION_TYPES,
    TimeSplit,
    build_matrix,
    time_split,
)
from npa_models.metrics import binary_metrics
from npa_models.registry import ModelBundle, load_bundle, make_model_version, save_bundle

log = logging.getLogger(__name__)

NAME = "early_warning"
TARGET = "rolls_forward_60d"
NPA_TARGET = "reaches_npa_90d"

# +1: risk can only rise with the feature; -1: only fall. Everything else is unconstrained.
MONOTONE: dict[str, int] = {
    "min_due_only_streak": 1,
    "months_since_full_payment": 1,
    "dpd": 1,
    "max_dpd_6m": 1,
    "broken_streak_flag": 1,
    "salary_missing_months_3m": 1,
    "utilisation": 1,
    "cash_advance_ratio_3m": 1,
    "payment_ratio_3m": -1,
    "income_to_due_ratio": -1,
}

LGBM_PARAMS: dict[str, Any] = {
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


@dataclass(frozen=True)
class RiskBands:
    """Cut-offs on calibrated ``p_roll_forward``: high >= ``high``, medium >= ``medium``.

    Defaults 0.35 / 0.15 (briefing B4 2.1). Tune ``high`` so the high band is a workable
    collector queue of about 5-8% of accounts; training records the resulting share.
    """

    high: float = 0.35
    medium: float = 0.15

    def __post_init__(self) -> None:
        if not 0.0 < self.medium < self.high < 1.0:
            raise ValueError(f"need 0 < medium < high < 1, got {self.medium}, {self.high}")

    def band(self, p: float) -> RiskBand:
        if p >= self.high:
            return RiskBand.HIGH
        if p >= self.medium:
            return RiskBand.MEDIUM
        return RiskBand.LOW

    def bands(self, p: npt.ArrayLike) -> npt.NDArray[np.str_]:
        arr = np.asarray(p, dtype=float)
        return np.where(
            arr >= self.high,
            RiskBand.HIGH.value,
            np.where(arr >= self.medium, RiskBand.MEDIUM.value, RiskBand.LOW.value),
        )


def threshold_for_share(p: npt.ArrayLike, share: float) -> float:
    """The probability cut-off that puts ``share`` of accounts in the high band."""
    if not 0.0 < share < 1.0:
        raise ValueError(f"share must be in (0, 1), got {share}")
    return float(np.quantile(np.asarray(p, dtype=float), 1.0 - share))


def _lgbm(seed: int) -> lgb.LGBMClassifier:
    constraints = [MONOTONE.get(c, 0) for c in FEATURE_COLUMNS]
    return lgb.LGBMClassifier(**LGBM_PARAMS, monotone_constraints=constraints, random_state=seed)


def _baseline(seed: int) -> Pipeline:
    pre = ColumnTransformer(
        [
            (
                "num",
                make_pipeline(SimpleImputer(strategy="median"), StandardScaler()),
                list(NUMERIC_FEATURES),
            ),
            (
                "cat",
                OneHotEncoder(categories=[list(OCCUPATION_TYPES)], handle_unknown="ignore"),
                list(CATEGORICAL_FEATURES),
            ),
        ]
    )
    lr = LogisticRegression(class_weight="balanced", max_iter=1000, random_state=seed)
    return Pipeline([("pre", pre), ("lr", lr)])


def _baseline_input(x: pd.DataFrame) -> pd.DataFrame:
    # One-hot encoder needs strings, not NaN categories.
    out = x.copy()
    out["occupation_type"] = out["occupation_type"].astype(object).fillna("unknown")
    return out


def _proba(model: Any, x: pd.DataFrame) -> npt.NDArray[np.float64]:
    return np.asarray(model.predict_proba(x), dtype=float)[:, 1]


def _fit_head(
    x_tr: pd.DataFrame, y_tr: pd.Series, x_val: pd.DataFrame, y_val: pd.Series, seed: int
) -> tuple[lgb.LGBMClassifier, IsotonicRegression]:
    model = _lgbm(seed).fit(x_tr, y_tr)
    cal = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    cal.fit(_proba(model, x_val), y_val.astype(int))
    return model, cal


def _check_both_classes(y: pd.Series, where: str) -> None:
    if y.nunique() < 2:
        raise ValueError(f"{where} split needs both classes of {y.name!r}; check the label months")


@dataclass
class EarlyWarningModel:
    """A trained early-warning bundle plus its risk bands."""

    bundle: ModelBundle
    bands: RiskBands

    @property
    def model_version(self) -> str:
        return self.bundle.model_version

    def _calibrated(self, df: pd.DataFrame, head: str, cal: str) -> npt.NDArray[np.float64]:
        x = build_matrix(df, self.bundle.feature_columns)
        raw = _proba(self.bundle.estimators[head], x)
        return np.asarray(self.bundle.estimators[cal].predict(raw), dtype=float)

    def predict_proba(self, df: pd.DataFrame) -> npt.NDArray[np.float64]:
        """Calibrated probability of rolling forward in 30-60 days."""
        return self._calibrated(df, "roll_forward", "roll_forward_calibrator")

    def predict_npa_proba(self, df: pd.DataFrame) -> npt.NDArray[np.float64]:
        """Calibrated probability of reaching NPA (> 90 DPD) within 90 days."""
        return self._calibrated(df, "npa_90d", "npa_90d_calibrator")

    def score_frame(self, df: pd.DataFrame) -> pd.DataFrame:
        """Vectorised scores: ``account_id, as_of_month, p_roll_forward, p_npa_90d, risk_band``."""
        p = self.predict_proba(df)
        return pd.DataFrame(
            {
                "account_id": df["account_id"].to_numpy(),
                "as_of_month": df["month"].to_numpy(),
                "p_roll_forward": p,
                "p_npa_90d": self.predict_npa_proba(df),
                "risk_band": self.bands.bands(p),
            }
        )

    def score(self, df: pd.DataFrame) -> list[RiskScore]:
        """One :class:`RiskScore` per feature row. Reasons are added by task 2.2."""
        frame = self.score_frame(df)
        return [
            RiskScore(
                account_id=row.account_id,
                as_of_month=row.as_of_month,
                p_roll_forward=float(row.p_roll_forward),
                risk_band=RiskBand(row.risk_band),
                reasons=[],
                model_version=self.model_version,
            )
            for row in frame.itertuples(index=False)
        ]

    def score_batch(self, features: pd.DataFrame, as_of_month: str) -> list[RiskScore]:
        """Score every account in ``features`` for ``as_of_month``."""
        rows = features[features["month"] == as_of_month]
        if rows.empty:
            raise ValueError(f"no feature rows for as_of_month={as_of_month}")
        return self.score(rows)

    def save(self, model_dir: Path) -> Path:
        return save_bundle(self.bundle, model_dir)

    @classmethod
    def load(cls, model_dir: Path) -> "EarlyWarningModel":
        bundle = load_bundle(NAME, model_dir)
        t = bundle.metadata["thresholds"]
        return cls(bundle=bundle, bands=RiskBands(high=t["high"], medium=t["medium"]))


def train_frames(
    features: pd.DataFrame,
    labels: pd.DataFrame,
    *,
    seed: int,
    split: TimeSplit = DEFAULT_SPLIT,
    bands: RiskBands | None = None,
) -> EarlyWarningModel:
    """Train the early-warning heads and the baseline on in-memory frames."""
    bands = bands or RiskBands()
    data = features.merge(
        labels[["account_id", "month", TARGET, NPA_TARGET]],
        on=["account_id", "month"],
        how="inner",
        validate="one_to_one",
    )
    s = time_split(data, split)
    # The test window may have no labels yet (short label horizon): then test metrics are skipped.
    for name, part in (("train", s.train), ("validation", s.val)):
        if part.empty:
            raise ValueError(f"{name} split is empty; check the months in features/labels")
    x_tr, x_val, x_te = (build_matrix(part) for part in s)

    estimators: dict[str, Any] = {}
    metrics: dict[str, dict[str, float]] = {}
    for head, target in (("roll_forward", TARGET), ("npa_90d", NPA_TARGET)):
        y_tr, y_val = s.train[target], s.val[target]
        _check_both_classes(y_tr, "train")
        _check_both_classes(y_val, "validation")
        model, cal = _fit_head(x_tr, y_tr, x_val, y_val, seed)
        estimators[head], estimators[f"{head}_calibrator"] = model, cal
        if s.test[target].nunique() == 2:
            p_te = cal.predict(_proba(model, x_te))
            metrics[f"{head}_test"] = binary_metrics(s.test[target], p_te)

    baseline = _baseline(seed).fit(_baseline_input(x_tr), s.train[TARGET])
    estimators["baseline"] = baseline
    if s.test[TARGET].nunique() == 2:
        p_base = _proba(baseline, _baseline_input(x_te))
        metrics["baseline_test"] = binary_metrics(s.test[TARGET], p_base)

    p_val = estimators["roll_forward_calibrator"].predict(_proba(estimators["roll_forward"], x_val))
    band_share = {b: float(np.mean(bands.bands(p_val) == b)) for b in (r.value for r in RiskBand)}
    payload = {
        "features": list(FEATURE_COLUMNS),
        "params": LGBM_PARAMS,
        "monotone": MONOTONE,
        "seed": seed,
        "split": split.__dict__,
        "rows": len(data),
        "positives": int(data[TARGET].sum()),
        "months": [data["month"].min(), data["month"].max()],
    }
    bundle = ModelBundle(
        name=NAME,
        model_version=make_model_version("ew-lgbm", payload),
        feature_columns=FEATURE_COLUMNS,
        estimators=estimators,
        metadata={
            "seed": seed,
            "split": split.__dict__,
            "thresholds": {"high": bands.high, "medium": bands.medium},
            "band_share_validation": band_share,
            "suggested_high_threshold_6_5pct": threshold_for_share(p_val, 0.065),
            "metrics": metrics,
            "rows": {"train": len(s.train), "validation": len(s.val), "test": len(s.test)},
        },
    )
    log.info(
        "model=%s version=%s high_share_val=%.3f metrics=%s",
        NAME,
        bundle.model_version,
        band_share[RiskBand.HIGH.value],
        metrics,
    )
    return EarlyWarningModel(bundle=bundle, bands=bands)


def train(
    features_path: Path, labels_path: Path, settings: ModelSettings | None = None
) -> ModelBundle:
    """Train from parquet files (``features.parquet``, ``labels.parquet``) and return the bundle."""
    settings = settings or ModelSettings()
    model = train_frames(
        pd.read_parquet(features_path),
        pd.read_parquet(labels_path),
        seed=settings.seed,
        bands=RiskBands(high=settings.risk_high_threshold, medium=settings.risk_medium_threshold),
    )
    return model.bundle
