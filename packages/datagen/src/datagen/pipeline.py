"""``datagen features``: read the task 1.1 tables, write features, labels and samples."""

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from datagen.config import DatagenConfig
from datagen.features import build_features
from datagen.generate import LABEL_HORIZON_FILE, PERSONAS_JSON
from datagen.labels import build_labels
from datagen.personas import to_records, write_json
from datagen.validate import (
    ChunkedTableWriter,
    arrow_schema,
    table_spec,
    validate,
    write_parquet,
    write_table,
)

logger = logging.getLogger(__name__)

SAMPLE_ACCOUNTS = 200
SAMPLE_MONTHS = 10  # 200 accounts x 10 consecutive labelled months = 2,000 rows
SAMPLE_LAST_MONTH = "2026-06"  # pinned, so the committed samples stay byte-identical
SAMPLE_STREAM = 20
FEATURE_CHUNK_ACCOUNTS = 100_000  # accounts per features chunk (~3 GB peak per chunk)


def read_inputs(data_dir: Path) -> dict[str, pd.DataFrame]:
    """All inputs of the features step as pandas frames (small and test runs)."""
    return read_chunk(_open_inputs(data_dir), None)


def _open_inputs(data_dir: Path) -> dict[str, Any]:
    """Large inputs as Arrow tables (compact strings); small ones as pandas."""
    horizon = data_dir / LABEL_HORIZON_FILE
    return {
        "account_months": pq.read_table(data_dir / "account_months.parquet"),
        "monthly_spend": pq.read_table(data_dir / "monthly_spend.parquet"),
        "salary_credits": pq.read_table(data_dir / "salary_credits.parquet"),
        "label_horizon": pq.read_table(horizon) if horizon.exists() else None,
        "customers": pd.read_parquet(data_dir / "customers.parquet"),
        "shocks": pd.read_parquet(data_dir / "shocks.parquet"),
        "behaviour_types": pd.read_parquet(data_dir / "behaviour_types.parquet"),
    }


def read_chunk(
    inputs: dict[str, Any], accounts: npt.NDArray[Any] | None
) -> dict[str, pd.DataFrame]:
    """Rows for ``accounts`` (``None`` = everyone) from every features-step input."""
    customers = inputs["customers"]
    if accounts is not None:
        customers = customers[customers["account_id"].isin(accounts)].reset_index(drop=True)

    def pick(name: str, key: str, values: npt.NDArray[Any]) -> pd.DataFrame:
        table = inputs[name]
        if table is None:
            return pd.DataFrame()
        if accounts is not None:
            table = table.filter(pc.is_in(table[key], value_set=pa.array(values)))
        frame: pd.DataFrame = table.to_pandas()
        return frame

    acc = customers["account_id"].to_numpy()
    cust = customers["customer_id"].to_numpy()
    t = {
        "customers": customers.copy(),
        "account_months": pick("account_months", "account_id", acc),
        "monthly_spend": pick("monthly_spend", "account_id", acc),
        "salary_credits": pick("salary_credits", "customer_id", cust),
        "label_horizon": pick("label_horizon", "account_id", acc),
        "shocks": inputs["shocks"],
        "behaviour_types": inputs["behaviour_types"],
    }
    for col in ("statement_date", "due_date", "payment_date"):
        t["account_months"][col] = pd.to_datetime(t["account_months"][col])
    t["customers"]["card_open_date"] = pd.to_datetime(t["customers"]["card_open_date"])
    return t


def sample_months(labels: pd.DataFrame) -> list[str]:
    """The 10 labelled months ending ``SAMPLE_LAST_MONTH``."""
    return sorted(m for m in labels["month"].unique() if m <= SAMPLE_LAST_MONTH)[-SAMPLE_MONTHS:]


def make_samples(
    features: pd.DataFrame, labels: pd.DataFrame, seed: int
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Small committed samples for WS2 tests: 200 accounts x 10 labelled months ending
    ``SAMPLE_LAST_MONTH`` (2025-09..2026-06).

    Half the accounts are drawn from those that are ever past due in the sampled months, so
    both label classes appear; the rest at random. Features and labels share the same keys.
    """
    months = sample_months(labels)
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
    """CLI step: build ``features.parquet`` and ``labels.parquet`` (and optional samples).

    Features and labels of an account depend only on that account's rows, so large populations
    are processed ``FEATURE_CHUNK_ACCOUNTS`` accounts at a time and appended as Parquet row
    groups (content identical to one big write). A single-chunk run uses the plain writer, so
    small outputs keep their exact bytes.
    """
    inputs = _open_inputs(cfg.data_dir)
    accounts = np.sort(inputs["customers"]["account_id"].to_numpy())
    chunks = [
        accounts[i : i + FEATURE_CHUNK_ACCOUNTS]
        for i in range(0, accounts.size, FEATURE_CHUNK_ACCOUNTS)
    ]
    single = len(chunks) == 1
    writers = {name: ChunkedTableWriter(name, cfg.data_dir) for name in ("features", "labels")}
    keep_f: list[pd.DataFrame] = []
    keep_l: list[pd.DataFrame] = []
    for k, chunk in enumerate(chunks):
        t = read_chunk(inputs, None if single else chunk)
        features = build_features(
            t["customers"], t["account_months"], t["monthly_spend"], t["salary_credits"]
        )
        labels = build_labels(
            t["account_months"], t["shocks"], t["behaviour_types"], t["label_horizon"]
        )
        if single:
            write_table(features, "features", cfg.data_dir)
            write_table(labels, "labels", cfg.data_dir)
            keep_f, keep_l = [features], [labels]
            break
        writers["features"].write(features)
        writers["labels"].write(labels)
        # Keep only what personas and samples need from each chunk.
        wanted = features["account_id"].str.startswith("ACC-DEMO-")
        lab_wanted = labels["account_id"].str.startswith("ACC-DEMO-")
        if cfg.samples_dir is not None:
            months = sample_months(labels)
            wanted |= features["month"].isin(months)
            lab_wanted |= labels["month"].isin(months)
        keep_f.append(features[wanted])
        keep_l.append(labels[lab_wanted])
        logger.info("features chunk=%d/%d accounts=%d", k + 1, len(chunks), chunk.size)
    for w in writers.values():
        w.close()
    features = pd.concat(keep_f, ignore_index=True)
    labels = pd.concat(keep_l, ignore_index=True)
    logger.info("features accounts=%d chunks=%d", accounts.size, len(chunks))

    personas = add_persona_features(cfg.data_dir / PERSONAS_JSON, features, labels)
    samples_dir = cfg.samples_dir
    if samples_dir is not None and personas is not None:
        # Committed copy without transactions (regenerate for those): keeps the sample small.
        lean = {
            cid: {k: v for k, v in entry.items() if k != "transactions"}
            for cid, entry in personas.items()
        }
        write_json(lean, samples_dir / PERSONAS_JSON)
    if samples_dir is not None:
        f, lb = make_samples(features, labels, cfg.seed)
        validate(f, "features")
        validate(lb, "labels")
        write_parquet(
            f, samples_dir / "features_sample.parquet", arrow_schema(table_spec("features"))
        )
        write_parquet(lb, samples_dir / "labels_sample.parquet", arrow_schema(table_spec("labels")))
        logger.info("samples rows=%d dir=%s", len(f), samples_dir)


def add_persona_features(
    path: Path, features: pd.DataFrame, labels: pd.DataFrame
) -> dict[str, Any] | None:
    """Add each persona's ``features`` and ``labels`` rows to ``demo_personas.json``."""
    if not path.exists():
        return None
    doc: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    for cid, entry in doc.items():
        acc = cid.replace("CUST-", "ACC-")
        entry["features"] = to_records(features[features["account_id"] == acc])
        entry["labels"] = to_records(labels[labels["account_id"] == acc])
    write_json(doc, path)
    return doc
