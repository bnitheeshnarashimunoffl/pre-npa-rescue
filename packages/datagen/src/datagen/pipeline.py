"""``datagen features``: read the task 1.1 tables, write features, labels and samples."""

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from datagen.config import DatagenConfig
from datagen.features import build_features
from datagen.labels import build_labels
from datagen.validate import arrow_schema, table_spec, validate, write_parquet, write_table

logger = logging.getLogger(__name__)

SAMPLE_ACCOUNTS = 200
SAMPLE_MONTHS = 10  # 200 accounts x 10 consecutive labelled months = 2,000 rows
SAMPLE_STREAM = 20


def read_inputs(data_dir: Path) -> dict[str, pd.DataFrame]:
    names = ("customers", "account_months", "monthly_spend", "salary_credits", "shocks")
    tables = {name: pd.read_parquet(data_dir / f"{name}.parquet") for name in names}
    tables["behaviour_types"] = pd.read_parquet(data_dir / "behaviour_types.parquet")
    for col in ("statement_date", "due_date", "payment_date"):
        tables["account_months"][col] = pd.to_datetime(tables["account_months"][col])
    tables["customers"]["card_open_date"] = pd.to_datetime(tables["customers"]["card_open_date"])
    return tables


def make_samples(
    features: pd.DataFrame, labels: pd.DataFrame, seed: int
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Small committed samples for WS2 tests: 200 accounts x the last 10 labelled months.

    Half the accounts are drawn from those that are ever past due in the sampled months, so
    both label classes appear; the rest at random. Features and labels share the same keys.
    """
    months = sorted(labels["month"].unique())[-SAMPLE_MONTHS:]
    lab = labels[labels["month"].isin(months)]
    feat = features[features["month"].isin(months)]
    risky = feat.loc[feat["dpd"] > 0, "account_id"].unique()
    all_acc = feat["account_id"].unique()
    rng = np.random.default_rng([seed, SAMPLE_STREAM])
    half = min(SAMPLE_ACCOUNTS // 2, risky.size)
    pick_risky = rng.choice(np.sort(risky), size=half, replace=False)
    rest = np.setdiff1d(all_acc, pick_risky)
    pick_rest = rng.choice(rest, size=min(SAMPLE_ACCOUNTS - half, rest.size), replace=False)
    chosen = set(pick_risky) | set(pick_rest)
    f = feat[feat["account_id"].isin(chosen)].sort_values(["account_id", "month"])
    lb = lab[lab["account_id"].isin(chosen)].sort_values(["account_id", "month"])
    return f.reset_index(drop=True), lb.reset_index(drop=True)


def run_features(cfg: DatagenConfig) -> None:
    """CLI step: build ``features.parquet`` and ``labels.parquet`` (and optional samples)."""
    t = read_inputs(cfg.data_dir)
    features = build_features(
        t["customers"], t["account_months"], t["monthly_spend"], t["salary_credits"]
    )
    labels = build_labels(t["account_months"], t["shocks"], t["behaviour_types"])
    write_table(features, "features", cfg.data_dir)
    write_table(labels, "labels", cfg.data_dir)
    logger.info("features rows=%d labels rows=%d", len(features), len(labels))
    samples_dir = cfg.samples_dir
    if samples_dir is not None:
        f, lb = make_samples(features, labels, cfg.seed)
        validate(f, "features")
        validate(lb, "labels")
        write_parquet(
            f, samples_dir / "features_sample.parquet", arrow_schema(table_spec("features"))
        )
        write_parquet(lb, samples_dir / "labels_sample.parquet", arrow_schema(table_spec("labels")))
        logger.info("samples rows=%d dir=%s", len(f), samples_dir)
