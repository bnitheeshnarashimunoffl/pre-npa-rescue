"""``datagen generate``: build every task 1.1 table into ``DATA_DIR``.

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
from datagen.personas import (
    PERSONA_SEED,
    build_personas,
    persona_facts,
    to_records,
    write_json,
)
from datagen.protected import generate_protected
from datagen.salary import generate_salary
from datagen.shocks import (
    BehaviourModel,
    apply_spend_effects,
    assign_hidden_truth,
    behaviour_frame,
    shocks_frame,
)
from datagen.statements import PURCHASE_CATEGORIES, Accounts, simulate_statements
from datagen.transactions import write_transactions
from datagen.validate import check_integrity, write_parquet, write_table

PERSONAS_JSON = "demo_personas.json"
SINGLE_ROW_TABLES = {"customers", "protected_attributes", "shocks"}

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
BEHAVIOUR_SCHEMA = pa.schema(
    [
        pa.field("customer_id", pa.string(), nullable=False),
        pa.field("behaviour_type", pa.string(), nullable=False),
        pa.field("wont_pay_start_month", pa.string(), nullable=True),
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
    salary: pd.DataFrame
    shocks: pd.DataFrame
    behaviour: pd.DataFrame


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
    truth = assign_hidden_truth(
        customers["occupation_type"].to_numpy(), len(months), rng_for(cfg.seed, STREAM_TRUTH)
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
    plan, base = spend_plan(customers["monthly_income_paise"].to_numpy(np.int64), months, spend_rng)
    plan = apply_spend_effects(plan, base, truth, spend_rng)

    normal = NormalBehaviour.from_calibration(
        calibration, limit.size, rng_for(cfg.seed, STREAM_NORMAL)
    )
    policy = BehaviourModel(normal, truth, rng_for(cfg.seed, STREAM_OVERRIDES))
    account_months, monthly_spend = simulate_statements(accounts, months, policy, plan)

    salary = generate_salary(customers, months, truth, rng_for(cfg.seed, STREAM_SALARY))
    generated = {
        "customers": customers,
        "protected": protected,
        "account_months": account_months,
        "monthly_spend": monthly_spend,
        "salary": salary,
        "shocks": shocks_frame(ids, months, truth),
        "behaviour": behaviour_frame(ids, months, truth),
    }
    # Demo personas (CUST-DEMO-*) are appended after the random population; their histories
    # are scripted and identical for every seed.
    personas = build_personas(months)
    merged = {
        k: pd.concat([v, personas[k]], ignore_index=True).astype(v.dtypes.to_dict())
        for k, v in generated.items()
    }
    return GeneratedData(**merged)


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
            "salary_credits": data.salary,
            "shocks": data.shocks,
            "monthly_spend": data.monthly_spend,
        },
    )
    paths = [
        write_table(data.customers, "customers", out),
        write_table(data.protected, "protected_attributes", out),
        write_table(data.account_months, "account_months", out),
        write_table(data.salary, "salary_credits", out),
        write_table(data.shocks, "shocks", out),
    ]
    for df, name, schema in (
        (data.monthly_spend, "monthly_spend", MONTHLY_SPEND_SCHEMA),
        (data.behaviour, "behaviour_types", BEHAVIOUR_SCHEMA),
    ):
        path = out / f"{name}.parquet"
        write_parquet(df, path, schema)
        paths.append(path)
    persona_txns = None
    if cfg.write_transactions:
        n_txn, persona_txns = write_transactions(
            data.monthly_spend,
            data.account_months,
            data.customers,
            out,
            rng_for(cfg.seed, STREAM_TRANSACTIONS),
            fixed_rng=np.random.default_rng([PERSONA_SEED, STREAM_TRANSACTIONS]),
            fixed_accounts=set(data.customers.loc[is_persona(data.customers), "account_id"]),
        )
        logger.info("transactions rows=%d", n_txn)
        paths.append(out / "transactions.parquet")
    path = out / PERSONAS_JSON
    write_personas_json(persona_tables(data, persona_txns), path)
    paths.append(path)
    return paths


def is_persona(df: pd.DataFrame) -> pd.Series:
    return df["customer_id"].str.startswith("CUST-DEMO-")


def persona_tables(
    data: GeneratedData, transactions: pd.DataFrame | None = None
) -> dict[str, pd.DataFrame]:
    """Persona rows from every task 1.1 table (contract names)."""
    accounts = set(data.customers.loc[is_persona(data.customers), "account_id"])
    tables = {
        "customers": data.customers[is_persona(data.customers)],
        "protected_attributes": data.protected[is_persona(data.protected)],
        "account_months": data.account_months[data.account_months["account_id"].isin(accounts)],
        "salary_credits": data.salary[is_persona(data.salary)],
        "shocks": data.shocks[is_persona(data.shocks)],
    }
    if transactions is not None:
        tables["transactions"] = transactions
    return tables


def write_personas_json(tables: dict[str, pd.DataFrame], path: Path) -> None:
    """``demo_personas.json``: per persona, a facts block plus its rows from every table."""
    facts = persona_facts(tables["account_months"])
    doc: dict[str, Any] = {}
    for cid, persona_facts_ in facts.items():
        acc = cid.replace("CUST-", "ACC-")
        entry: dict[str, Any] = {"facts": persona_facts_}
        for name, df in tables.items():
            if "customer_id" in df.columns:
                rows = to_records(df[df["customer_id"] == cid])
            else:
                rows = to_records(df[df["account_id"] == acc])
            entry[name] = rows[0] if name in SINGLE_ROW_TABLES else rows
        doc[cid] = entry
    write_json(doc, path)


def run_generate(cfg: DatagenConfig) -> None:
    """CLI step: build and write the task 1.1 tables."""
    data = build(cfg)
    paths = write(data, cfg)
    logger.info(
        "generate done customers=%d files=%d out=%s", cfg.n_customers, len(paths), cfg.data_dir
    )
