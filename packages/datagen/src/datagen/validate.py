"""Schemas generated from ``contracts/data/*.md``, validation on write, deterministic Parquet.

The Markdown table specs are the single source of truth: each ``| `column` | type | notes |``
row becomes a pandera column check and an Arrow field. Validation runs on every write
(task 1.1 step 7); tables also get referential-integrity and window checks.
"""

import os
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from npa_contracts import enums

try:  # pandera >= 0.24 namespaces the pandas API
    import pandera.pandas as pda
except ImportError:  # pragma: no cover
    import pandera as pda  # type: ignore[no-redef]

MONTH_RE = r"^\d{4}-(0[1-9]|1[0-2])$"

# Allowed values for categorical columns (enums from npa_contracts, the rest from the specs).
CATEGORIES: dict[str, list[str]] = {
    "bucket": [b.value for b in enums.Bucket],
    "language_pref": [lang.value for lang in enums.Lang],
    "shock_type": [s.value for s in enums.ShockType],
    "treatment": [t.value for t in enums.Treatment],
    "true_uplift_group": [g.value for g in enums.UpliftGroup],
    "segment_truth": [s.value for s in enums.Segment],
    "occupation_type": ["salaried", "self_employed", "gig", "retired", "student"],
    "insurance_cover_type": ["none", "job_loss", "death_disability", "both"],
    "category": [
        "essentials",
        "discretionary",
        "travel",
        "utilities",
        "cash_advance",
        "emi",
        "other",
    ],
    "channel": ["pos", "online", "atm"],
    "region": ["north", "south", "east", "west", "northeast", "central"],
}


@dataclass(frozen=True, slots=True)
class ColumnSpec:
    name: str
    kind: str  # string | month | date | int16 | int32 | int64 | float64 | bool | timestamp
    nullable: bool
    non_negative: bool


def contracts_dir() -> Path:
    """``$CONTRACTS_DIR`` or the repo's ``contracts/`` (found from this file)."""
    env = os.environ.get("CONTRACTS_DIR")
    if env:
        return Path(env)
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "contracts" / "data"
        if candidate.is_dir():
            return candidate.parent
    raise FileNotFoundError("contracts/data not found; set CONTRACTS_DIR")


_ROW_RE = re.compile(r"^\|\s*`(?P<name>[a-z0-9_]+)`\s*\|(?P<type>[^|]*)\|(?P<notes>[^|]*)\|")


def _kind(type_text: str) -> str:
    t = type_text.strip()
    if t.startswith("string `YYYY-MM`"):
        return "month"
    if t.startswith("date"):
        return "date"
    if t.startswith("timestamp"):
        return "timestamp"
    for kind in ("int16", "int32", "int64", "float64", "bool", "string"):
        if t.startswith(kind):
            return kind
    raise ValueError(f"unknown column type in contract: {type_text!r}")


@cache
def table_spec(table: str) -> tuple[ColumnSpec, ...]:
    """Parse ``contracts/data/<table>.md`` into column specs, in contract order."""
    text = (contracts_dir() / "data" / f"{table}.md").read_text(encoding="utf-8")
    specs = []
    for line in text.splitlines():
        m = _ROW_RE.match(line)
        if not m:
            continue
        type_text, notes = m["type"], m["notes"].lower()
        specs.append(
            ColumnSpec(
                name=m["name"],
                kind=_kind(type_text),
                nullable="nullable" in notes,
                non_negative=">= 0" in type_text,
            )
        )
    if not specs:
        raise ValueError(f"no columns found in contract for {table}")
    return tuple(specs)


_ARROW: dict[str, pa.DataType] = {
    "string": pa.string(),
    "month": pa.string(),
    "date": pa.date32(),
    "timestamp": pa.timestamp("us", tz="UTC"),
    "int16": pa.int16(),
    "int32": pa.int32(),
    "int64": pa.int64(),
    "float64": pa.float64(),
    "bool": pa.bool_(),
}

_PANDAS: dict[str, str] = {
    "string": "object",
    "month": "object",
    "date": "datetime64[ns]",
    "timestamp": "datetime64[us, UTC]",
    "int16": "int16",
    "int32": "int32",
    "int64": "int64",
    "float64": "float64",
    "bool": "bool",
}


def arrow_schema(specs: tuple[ColumnSpec, ...]) -> pa.Schema:
    return pa.schema([pa.field(s.name, _ARROW[s.kind], nullable=s.nullable) for s in specs])


def pandera_schema(table: str, specs: tuple[ColumnSpec, ...]) -> pda.DataFrameSchema:
    columns = {}
    for s in specs:
        checks = []
        if s.non_negative:
            checks.append(pda.Check.ge(0))
        if s.kind == "month":
            checks.append(pda.Check.str_matches(MONTH_RE))
        if s.name in CATEGORIES:
            checks.append(pda.Check.isin(CATEGORIES[s.name]))
        if s.name == "severity":
            checks.append(pda.Check.in_range(0, 1))
        columns[s.name] = pda.Column(_PANDAS[s.kind], checks=checks, nullable=s.nullable)
    return pda.DataFrameSchema(columns, strict=True, ordered=True, name=table)


def validate(df: pd.DataFrame, table: str) -> pd.DataFrame:
    """Validate ``df`` against the contract for ``table`` (raises on any violation)."""
    specs = table_spec(table)
    return pandera_schema(table, specs).validate(df, lazy=True)


def write_parquet(df: pd.DataFrame, path: Path, schema: pa.Schema | None) -> None:
    """Write ``df`` (explicit Arrow schema, or inferred if ``None``); same input gives
    byte-identical files."""
    table = pa.Table.from_pandas(df, schema=schema, preserve_index=False)
    table = table.replace_schema_metadata(None)  # drop pandas metadata (version-dependent)
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, path, compression="zstd", write_statistics=True)


class ChunkedTableWriter:
    """Validate and append chunks of a contract table to one Parquet file (row groups).

    For outputs too large to hold in memory at once (5 lakh customers). Same settings as
    :func:`write_parquet`; the content equals a single write, the row-group layout differs.
    """

    def __init__(self, table: str, out_dir: Path) -> None:
        self.table = table
        self.path = out_dir / f"{table}.parquet"
        self.schema = arrow_schema(table_spec(table))
        self.rows = 0
        self._writer: pq.ParquetWriter | None = None

    def write(self, df: pd.DataFrame) -> None:
        validate(df, self.table)
        chunk = pa.Table.from_pandas(df, schema=self.schema, preserve_index=False)
        chunk = chunk.replace_schema_metadata(None)
        if self._writer is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._writer = pq.ParquetWriter(
                self.path, chunk.schema, compression="zstd", write_statistics=True
            )
        self._writer.write_table(chunk)
        self.rows += len(df)

    def close(self) -> None:
        if self._writer is not None:
            self._writer.close()
            self._writer = None


def write_table(df: pd.DataFrame, table: str, out_dir: Path) -> Path:
    """Validate against the contract and write ``<out_dir>/<table>.parquet``."""
    validate(df, table)
    path = out_dir / f"{table}.parquet"
    write_parquet(df, path, arrow_schema(table_spec(table)))
    return path


# --- Cross-table checks -----------------------------------------------------------------------


def check_integrity(
    customers: pd.DataFrame,
    account_months: pd.DataFrame,
    *,
    start_month: str,
    end_month: str,
    others: dict[str, pd.DataFrame] | None = None,
) -> None:
    """Referential integrity and window checks across generated tables."""
    errors: list[str] = []
    if customers["customer_id"].duplicated().any():
        errors.append("duplicate customer_id in customers")
    if customers["account_id"].duplicated().any():
        errors.append("more than one customer per account_id")
    acc_to_cust = dict(zip(customers["account_id"], customers["customer_id"], strict=True))
    unknown = set(account_months["account_id"]) - acc_to_cust.keys()
    if unknown:
        errors.append(f"account_months has unknown account_id(s): {sorted(unknown)[:5]}")
    mismatched = account_months["account_id"].map(acc_to_cust) != account_months["customer_id"]
    if mismatched.any():
        errors.append("account_months customer_id does not match customers.account_id")
    if account_months.duplicated(["account_id", "month"]).any():
        errors.append("duplicate (account_id, month) in account_months")
    months = account_months["month"]
    if (months < start_month).any() or (months > end_month).any():
        errors.append(f"account_months month outside {start_month}..{end_month}")
    known_customers = set(customers["customer_id"])
    for name, df in (others or {}).items():
        if "customer_id" in df and not set(df["customer_id"]) <= known_customers:
            errors.append(f"{name} has unknown customer_id(s)")
        if "account_id" in df and not set(df["account_id"]) <= acc_to_cust.keys():
            errors.append(f"{name} has unknown account_id(s)")
        if "month" in df and ((df["month"] < start_month) | (df["month"] > end_month)).any():
            errors.append(f"{name} month outside {start_month}..{end_month}")
    if errors:
        raise ValueError("integrity check failed: " + "; ".join(errors))
