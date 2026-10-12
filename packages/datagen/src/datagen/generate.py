"""``datagen generate``: build the task 1.1 tables into ``DATA_DIR``.

This stage builds customers, protected attributes and monthly statements for UCI-calibrated
"normal" behaviour; shocks, salary credits and transactions follow in the next PR.

Each component draws from its own RNG stream, ``default_rng([seed, stream])``, so the same
seed gives byte-identical Parquet and changing one component does not reshuffle the others.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa

from datagen.behaviour import NormalBehaviour, spend_plan
from datagen.calendar import BILL_DAYS, month_range
from datagen.calibrate_uci import load_calibration
from datagen.config import DatagenConfig
from datagen.customers import generate_customers
from datagen.protected import generate_protected
from datagen.statements import PURCHASE_CATEGORIES, Accounts, simulate_statements
from datagen.validate import check_integrity, write_parquet, write_table

logger = logging.getLogger(__name__)

# RNG stream ids (never reuse or renumber: that would change every output).
STREAM_PROTECTED = 1
STREAM_CUSTOMERS = 2
STREAM_TRUTH = 3
STREAM_NORMAL = 4
STREAM_SPEND = 5
STREAM_SALARY = 6
STREAM_TRANSACTIONS = 7
STREAM_ACCOUNTS = 8
STREAM_OVERRIDES = 9

# Internal tables (not contract tables; consumed by features/labels/experiment only).
MONTHLY_SPEND_SCHEMA = pa.schema(
    [
        pa.field("account_id", pa.string(), nullable=False),
        pa.field("month", pa.string(), nullable=False),
        *[pa.field(f"{c}_paise", pa.int64(), nullable=False) for c in PURCHASE_CATEGORIES],
        pa.field("cash_advance_paise", pa.int64(), nullable=False),
        pa.field("txn_count", pa.int64(), nullable=False),
    ]
)


def rng_for(seed: int, stream: int) -> np.random.Generator:
    return np.random.default_rng([seed, stream])


@dataclass(frozen=True)
class GeneratedData:
    customers: pd.DataFrame
    protected: pd.DataFrame
    account_months: pd.DataFrame
    monthly_spend: pd.DataFrame


def build(cfg: DatagenConfig, calibration: dict[str, Any] | None = None) -> GeneratedData:
    """Generate all task 1.1 tables in memory (no I/O)."""
    calibration = calibration or load_calibration()
    months = month_range(cfg.start_month, cfg.end_month)
    width = max(6, len(str(cfg.n_customers)))
    ids = [f"CUST-{i:0{width}d}" for i in range(1, cfg.n_customers + 1)]

    protected = generate_protected(ids, rng_for(cfg.seed, STREAM_PROTECTED))
    customers = generate_customers(
        protected, calibration, cfg.start_month, rng_for(cfg.seed, STREAM_CUSTOMERS), seed=cfg.seed
    )

    acc_rng = rng_for(cfg.seed, STREAM_ACCOUNTS)
    limit = customers["card_limit_paise"].to_numpy(np.int64)
    q = np.array(calibration["bill_to_limit_quantiles"], dtype=float)
    util0 = np.interp(acc_rng.random(limit.size), np.linspace(0, 1, q.size), q)
    opening = (np.round(util0 * limit / 100) * 100).astype(np.int64)
    accounts = Accounts(
        account_id=customers["account_id"].to_numpy(),
        customer_id=customers["customer_id"].to_numpy(),
        limit=limit,
        bill_day=np.array(BILL_DAYS, dtype=np.int64)[
            acc_rng.integers(0, len(BILL_DAYS), limit.size)
        ],
        opening_balance=opening,
    )

    spend_rng = rng_for(cfg.seed, STREAM_SPEND)
    plan, _ = spend_plan(customers["monthly_income_paise"].to_numpy(np.int64), months, spend_rng)

    policy = NormalBehaviour.from_calibration(
        calibration, limit.size, rng_for(cfg.seed, STREAM_NORMAL)
    )
    account_months, monthly_spend = simulate_statements(accounts, months, policy, plan)

    return GeneratedData(
        customers=customers,
        protected=protected,
        account_months=account_months,
        monthly_spend=monthly_spend,
    )


def write(data: GeneratedData, cfg: DatagenConfig) -> list[Path]:
    """Validate and write every table to ``cfg.data_dir``."""
    out = cfg.data_dir
    check_integrity(
        data.customers,
        data.account_months,
        start_month=cfg.start_month,
        end_month=cfg.end_month,
        others={
            "protected_attributes": data.protected,
            "monthly_spend": data.monthly_spend,
        },
    )
    paths = [
        write_table(data.customers, "customers", out),
        write_table(data.protected, "protected_attributes", out),
        write_table(data.account_months, "account_months", out),
    ]
    path = out / "monthly_spend.parquet"
    write_parquet(data.monthly_spend, path, MONTHLY_SPEND_SCHEMA)
    paths.append(path)
    return paths


def run_generate(cfg: DatagenConfig) -> None:
    """CLI step: build and write the task 1.1 tables."""
    data = build(cfg)
    paths = write(data, cfg)
    logger.info(
        "generate done customers=%d files=%d out=%s", cfg.n_customers, len(paths), cfg.data_dir
    )
