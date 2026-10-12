"""Task 2.4: uplift model, i.e. who is worth contacting at all, and how.

Data: WS1's randomised experiment (``experiment.parquet``: treatment assigned at random, 90-day
cure outcome) joined to the features as of the experiment month.

- **T-learner** (two-model): a control model (``none``) and an "any contact" model; their
  difference is ``uplift_score``, the estimated cure-probability gain if contacted. One model per
  contact arm (``reminder``, ``chat_invite``, ``agent_call``, ``relief_offer``) gives per-treatment
  uplift for choosing ``recommended_treatment``. The X-learner (causalml) is optional and not
  included yet.
- **Groups:** ``persuadable`` if uplift >= tau, ``sleeping_dog`` if uplift <= -tau; otherwise
  ``sure_thing`` when the no-contact cure probability is >= 0.5, else ``lost_cause``.
- **Treatment:** only persuadables are contacted, with the arm that maximises
  ``uplift * cure_value - mean arm cost``; everyone else gets ``none``. Sleeping dogs are left
  alone (RBI RBC Directions para 454Z: no excessive contact; the uplift evidence shows contact
  hurts them).
- **No look-ahead / no in-sample evaluation:** the experiment is one month, so evaluation uses
  K-fold cross-fitting: every account is scored by models that never saw it (Qini, AUUC, group
  agreement and the policy simulation all use these out-of-fold estimates).
- ``true_uplift_group`` is hidden truth: used only to measure agreement, never as an input
  (``features.FORBIDDEN_COLUMNS``).
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
import numpy.typing as npt
import pandas as pd
from sklearn.model_selection import StratifiedKFold
from sklift.metrics import qini_auc_score, uplift_auc_score

from npa_contracts.enums import Treatment, UpliftGroup
from npa_contracts.models import UpliftResult
from npa_models.config import ModelSettings
from npa_models.features import FEATURE_COLUMNS, build_matrix
from npa_models.registry import ModelBundle, load_bundle, make_model_version, save_bundle

log = logging.getLogger(__name__)

NAME = "uplift"
OUTCOME = "outcome_cured_90d"
CONTROL = Treatment.NONE.value
ARMS: tuple[str, ...] = tuple(t.value for t in Treatment if t is not Treatment.NONE)
GROUPS: tuple[str, ...] = tuple(g.value for g in UpliftGroup)
SURE_THING_MIN_CURE = 0.5
N_FOLDS = 3

# Small, shallow trees: each arm has only ~20% of a small experiment, and the T-learner subtracts
# two models, so variance dominates (compared on the fake experiment: see the PR for numbers).
LGBM_PARAMS: dict[str, Any] = {
    "n_estimators": 150,
    "learning_rate": 0.05,
    "num_leaves": 7,
    "min_child_samples": 40,
    "subsample": 0.8,
    "subsample_freq": 1,
    "colsample_bytree": 0.8,
    "deterministic": True,
    "force_col_wise": True,
    "verbose": -1,
}

SimulatePolicy = Callable[..., dict[str, Any]]


def experiment_frame(experiment: pd.DataFrame, features: pd.DataFrame) -> pd.DataFrame:
    """Join each experiment row to its features as of the experiment month."""
    bad = set(experiment["treatment"]) - {t.value for t in Treatment}
    if bad:
        raise ValueError(f"unknown treatment(s): {sorted(bad)}")
    cols = ["account_id", "month", "treatment", OUTCOME, "contact_cost_paise"]
    if "true_uplift_group" in experiment.columns:  # hidden truth, kept for evaluation only
        cols.append("true_uplift_group")
    df = experiment[cols].merge(
        features, on=["account_id", "month"], how="inner", validate="one_to_one"
    )
    if len(df) < len(experiment):
        raise ValueError(f"{len(experiment) - len(df)} experiment row(s) have no features")
    return df


def assign_groups(
    uplift: npt.ArrayLike, p_control: npt.ArrayLike, tau: float
) -> npt.NDArray[np.object_]:
    """Four groups from the estimated effect and the no-contact cure probability."""
    if tau <= 0:
        raise ValueError(f"tau must be > 0, got {tau}")
    u, pc = np.asarray(uplift, dtype=float), np.asarray(p_control, dtype=float)
    return np.select(
        [u >= tau, u <= -tau, pc >= SURE_THING_MIN_CURE],
        [
            UpliftGroup.PERSUADABLE.value,
            UpliftGroup.SLEEPING_DOG.value,
            UpliftGroup.SURE_THING.value,
        ],
        default=UpliftGroup.LOST_CAUSE.value,
    ).astype(object)


def recommend(
    effects: pd.DataFrame, groups: npt.ArrayLike, arm_cost: dict[str, float], cure_value: float
) -> npt.NDArray[np.object_]:
    """Best arm by ``uplift * cure_value - cost`` for persuadables (``none`` if none pays off)."""
    net = np.column_stack([effects[f"uplift_{a}"] * cure_value - arm_cost[a] for a in ARMS])
    best = np.array(ARMS, dtype=object)[net.argmax(axis=1)]
    worth_it = net.max(axis=1) > 0
    persuadable = np.asarray(groups) == UpliftGroup.PERSUADABLE.value
    return np.where(persuadable & worth_it, best, CONTROL).astype(object)


def _lgbm(seed: int) -> lgb.LGBMClassifier:
    return lgb.LGBMClassifier(**LGBM_PARAMS, random_state=seed)


def _p(model: lgb.LGBMClassifier, x: pd.DataFrame) -> npt.NDArray[np.float64]:
    return np.asarray(model.predict_proba(x), dtype=float)[:, 1]


def _fit(df: pd.DataFrame, seed: int) -> dict[str, lgb.LGBMClassifier]:
    """Control, any-contact and per-arm outcome models."""
    parts = {"control": df["treatment"] == CONTROL, "treated": df["treatment"] != CONTROL}
    parts |= {f"arm_{a}": df["treatment"] == a for a in ARMS}
    models = {}
    for name, mask in parts.items():
        y = df.loc[mask, OUTCOME].astype(int)
        if y.nunique() < 2:
            raise ValueError(f"{name} rows need both cured and not-cured outcomes")
        models[name] = _lgbm(seed).fit(build_matrix(df[mask]), y)
    return models


def _effects(models: dict[str, Any], df: pd.DataFrame) -> pd.DataFrame:
    x = build_matrix(df)
    p_control = _p(models["control"], x)
    out = {"p_control": p_control, "uplift": _p(models["treated"], x) - p_control}
    for a in ARMS:
        out[f"uplift_{a}"] = _p(models[f"arm_{a}"], x) - p_control
    return pd.DataFrame(out, index=df.index)


def cross_fit_effects(df: pd.DataFrame, seed: int, n_folds: int = N_FOLDS) -> pd.DataFrame:
    """Out-of-fold effects for every experiment row (folds stratified by treatment)."""
    folds = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=seed)
    parts = []
    for train_idx, test_idx in folds.split(df, df["treatment"]):
        models = _fit(df.iloc[train_idx], seed)
        parts.append(_effects(models, df.iloc[test_idx]))
    return pd.concat(parts).loc[df.index]


def evaluate_effects(
    df: pd.DataFrame, effects: pd.DataFrame, groups: npt.ArrayLike
) -> dict[str, Any]:
    """Qini / AUUC (any contact vs none) and, if present, agreement with the hidden groups."""
    treated = (df["treatment"] != CONTROL).astype(int)
    y = df[OUTCOME].astype(int)
    g = pd.Series(np.asarray(groups), index=df.index)
    out: dict[str, Any] = {
        "qini_auc": float(qini_auc_score(y, effects["uplift"], treated)),
        "uplift_auc": float(uplift_auc_score(y, effects["uplift"], treated)),
        "group_share": {k: float((g == k).mean()) for k in GROUPS},
        "n": len(df),
    }
    if "true_uplift_group" in df.columns:  # evaluation only (IS/ISO/IEC TS 4213)
        truth = df["true_uplift_group"]
        out["group_accuracy"] = float((truth == g).mean())
        out["group_confusion"] = {
            t: {p: int(((truth == t) & (g == p)).sum()) for p in GROUPS} for t in GROUPS
        }
    return out


@dataclass
class UpliftModel:
    bundle: ModelBundle

    @property
    def model_version(self) -> str:
        return self.bundle.model_version

    @property
    def tau(self) -> float:
        return float(self.bundle.metadata["tau"])

    def score_frame(self, df: pd.DataFrame) -> pd.DataFrame:
        """``account_id, as_of_month, uplift_score, uplift_group, recommended_treatment``, then
        ``p_control`` and the per-arm ``uplift_<arm>`` effects."""
        eff = _effects(self.bundle.estimators, df)
        groups = assign_groups(eff["uplift"], eff["p_control"], self.tau)
        md = self.bundle.metadata
        rec = recommend(eff, groups, md["arm_cost_paise"], md["cure_value_paise"])
        out = pd.DataFrame(
            {
                "account_id": df["account_id"].to_numpy(),
                "as_of_month": df["month"].to_numpy(),
                "uplift_score": eff["uplift"].to_numpy(),
                "uplift_group": groups,
                "recommended_treatment": rec,
            }
        )
        return pd.concat([out, eff.reset_index(drop=True).drop(columns="uplift")], axis=1)

    def score(self, df: pd.DataFrame) -> list[UpliftResult]:
        frame = self.score_frame(df)
        return [
            UpliftResult(
                account_id=row.account_id,
                uplift_score=float(row.uplift_score),
                uplift_group=UpliftGroup(row.uplift_group),
                recommended_treatment=Treatment(row.recommended_treatment),
                model_version=self.model_version,
            )
            for row in frame.itertuples(index=False)
        ]

    def score_batch(self, features: pd.DataFrame, as_of_month: str) -> list[UpliftResult]:
        rows = features[features["month"] == as_of_month]
        if rows.empty:
            raise ValueError(f"no feature rows for as_of_month={as_of_month}")
        return self.score(rows)

    def save(self, model_dir: Path) -> Path:
        return save_bundle(self.bundle, model_dir)

    @classmethod
    def load(cls, model_dir: Path) -> "UpliftModel":
        return cls(bundle=load_bundle(NAME, model_dir))


def train_frames(
    experiment: pd.DataFrame,
    features: pd.DataFrame,
    *,
    seed: int,
    tau: float = 0.05,
    cure_value_paise: int = 500_000,
) -> tuple[UpliftModel, pd.DataFrame]:
    """Fit the final models on the whole experiment and return them with out-of-fold scores.

    The returned frame (one row per experiment account) holds cross-fitted effects, groups and
    recommendations; use it, not in-sample scores, for evaluation and the policy simulation.
    """
    df = experiment_frame(experiment, features)
    arm_cost = {a: float(df.loc[df["treatment"] == a, "contact_cost_paise"].mean()) for a in ARMS}
    oof = cross_fit_effects(df, seed)
    oof_groups = assign_groups(oof["uplift"], oof["p_control"], tau)
    oof_rec = recommend(oof, oof_groups, arm_cost, cure_value_paise)
    evaluation = evaluate_effects(df, oof, oof_groups)

    payload = {
        "features": list(FEATURE_COLUMNS),
        "params": LGBM_PARAMS,
        "seed": seed,
        "tau": tau,
        "cure_value_paise": cure_value_paise,
        "rows": len(df),
        "cured": int(df[OUTCOME].sum()),
        "month": sorted(df["month"].unique()),
    }
    bundle = ModelBundle(
        name=NAME,
        model_version=make_model_version("uplift-tlearner", payload),
        feature_columns=FEATURE_COLUMNS,
        estimators=_fit(df, seed),
        metadata={
            "seed": seed,
            "tau": tau,
            "sure_thing_min_cure": SURE_THING_MIN_CURE,
            "cure_value_paise": cure_value_paise,
            "arm_cost_paise": arm_cost,
            "experiment_month": sorted(df["month"].unique()),
            "n_folds": N_FOLDS,
            "evaluation_out_of_fold": evaluation,
        },
    )
    oof_frame = pd.DataFrame(
        {
            "account_id": df["account_id"].to_numpy(),
            "uplift_score": oof["uplift"].to_numpy(),
            "p_control": oof["p_control"].to_numpy(),
            "uplift_group": oof_groups,
            "recommended_treatment": oof_rec,
        }
    )
    log.info(
        "model=%s version=%s qini_auc=%.4f groups=%s",
        NAME,
        bundle.model_version,
        evaluation["qini_auc"],
        evaluation["group_share"],
    )
    return UpliftModel(bundle), oof_frame


def train(
    features_path: Path, experiment_path: Path, settings: ModelSettings | None = None
) -> ModelBundle:
    """Train from parquet files and return the bundle."""
    settings = settings or ModelSettings()
    model, _ = train_frames(
        pd.read_parquet(experiment_path),
        pd.read_parquet(features_path),
        seed=settings.seed,
        tau=settings.uplift_tau,
        cure_value_paise=settings.uplift_cure_value_paise,
    )
    return model.bundle


# --- Policy simulation (the pitch headline; briefing B4 2.4) --------------------------------


def default_simulate_policy() -> SimulatePolicy:
    """WS1's ``datagen.experiment.simulate_policy`` (imported lazily: WS1 PR #101)."""
    try:
        from datagen.experiment import simulate_policy  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "datagen.experiment.simulate_policy is not available yet (WS1 task 1.3)"
        ) from exc
    return simulate_policy  # type: ignore[no-any-return]


def policy_assignments(
    oof: pd.DataFrame,
    risk: pd.Series,
    potential: pd.DataFrame,
    risk_treatment: str = Treatment.AGENT_CALL.value,
) -> dict[str, pd.DataFrame]:
    """Who each strategy contacts, and how.

    - ``risk_targeting``: the highest-risk accounts by ``p_roll_forward`` (``risk``, indexed by
      ``account_id``), as many as the uplift policy contacts, all with ``risk_treatment``.
    - ``uplift_targeting``: persuadables with their recommended treatment (ours).
    - ``oracle``: true persuadables get a chat invite (same rule as WS1's ``oracle_policy``).

    "Call everyone" is the simulator's baseline, so it needs no assignment.
    """
    ours = oof.loc[oof["recommended_treatment"] != CONTROL, ["account_id", "recommended_treatment"]]
    ours = ours.rename(columns={"recommended_treatment": "treatment"})
    missing = set(potential["account_id"]) - set(risk.index)
    if missing:
        raise ValueError(f"{len(missing)} experiment account(s) have no risk score")
    top = risk.reindex(potential["account_id"]).sort_values(ascending=False, kind="stable")
    by_risk = pd.DataFrame({"account_id": top.index[: len(ours)], "treatment": risk_treatment})
    true_p = potential.loc[
        potential["true_uplift_group"] == UpliftGroup.PERSUADABLE.value, "account_id"
    ]
    oracle = pd.DataFrame({"account_id": true_p.to_numpy(), "treatment": "chat_invite"})
    return {"risk_targeting": by_risk, "uplift_targeting": ours, "oracle": oracle}


def simulate_strategies(
    oof: pd.DataFrame,
    risk: pd.Series,
    potential: pd.DataFrame,
    simulate: SimulatePolicy | None = None,
) -> dict[str, Any]:
    """Compare (a) call everyone, (b) risk targeting, (c) uplift targeting, (d) oracle.

    Returns ``{"policy_simulation": <SimulationMetrics for (c) vs (a)>, "strategies": {...}}``.
    The first item has the exact shape of ``contracts/fixtures/simulation_metrics.json``.
    """
    sim = simulate or default_simulate_policy()
    runs = {
        name: sim(assign, potential=potential, strategy=name)
        for name, assign in policy_assignments(oof, risk, potential).items()
    }
    ours = dict(runs["uplift_targeting"])
    ours["ours"] = {**ours["ours"], "strategy": "pre_npa_rescue"}
    ours["source"] = "packages/models/reports/policy_simulation.json (npa_models.uplift)"
    strategies = {"call_everyone": runs["uplift_targeting"]["baseline"]}
    strategies |= {name: run["ours"] for name, run in runs.items()}
    return {"policy_simulation": ours, "strategies": strategies}
