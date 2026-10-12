"""Seed from WS1 Parquet (and WS2 scores.parquet) with bulk loading.

Postgres: ``COPY ... FROM STDIN (FORMAT csv)`` fed from Arrow record batches written as CSV by
pyarrow (C speed, bounded memory). Other dialects (SQLite in unit tests): executemany.
Imported lazily by ``seed`` so the fixtures path works without pyarrow.
"""

import io
import json
from collections.abc import Iterable, Iterator
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pacsv
import pyarrow.parquet as pq
from sqlalchemy import JSON, Connection, Table

from app.orm import Account, AccountMonth, Customer, ProtectedAttributes, Score, table_of
from seed.errors import SeedError

BATCH_ROWS = 200_000


# --- bulk load --------------------------------------------------------------------------------
def load_batches(conn: Connection, table: Table, batches: Iterable[pa.RecordBatch]) -> int:
    """Append ``batches`` to ``table`` and return the row count. Column names must match."""
    if conn.dialect.name == "postgresql":
        return _copy_postgres(conn, table, batches)
    return _insert_generic(conn, table, batches)


def _copy_postgres(conn: Connection, table: Table, batches: Iterable[pa.RecordBatch]) -> int:
    dbapi = conn.connection.driver_connection
    assert dbapi is not None
    options = pacsv.WriteOptions(include_header=False, quoting_style="needed")
    total = 0
    with dbapi.cursor() as cur:
        for batch in batches:
            if batch.num_rows == 0:
                continue
            cols = ", ".join(f'"{name}"' for name in batch.schema.names)
            buf = io.BytesIO()
            pacsv.write_csv(batch, buf, write_options=options)
            with cur.copy(f'COPY "{table.name}" ({cols}) FROM STDIN (FORMAT csv)') as copy:
                copy.write(buf.getbuffer())
            total += batch.num_rows
    return total


def _insert_generic(conn: Connection, table: Table, batches: Iterable[pa.RecordBatch]) -> int:
    json_cols = {c.name for c in table.columns if isinstance(c.type, JSON)}
    total = 0
    for batch in batches:
        rows = batch.to_pylist()
        for row in rows:
            for col in json_cols & row.keys():
                if isinstance(row[col], str):
                    row[col] = json.loads(row[col])
        if rows:
            conn.execute(table.insert(), rows)
            total += len(rows)
    return total


# --- reading ----------------------------------------------------------------------------------
def _required(table: Table) -> set[str]:
    """Columns a file must provide: NOT NULL with no default."""
    return {
        c.name
        for c in table.columns
        if not c.nullable and c.server_default is None and c.default is None
    }


def _batches(
    path: Path, table: Table, rename: dict[str, str] | None = None
) -> Iterator[pa.RecordBatch]:
    """Record batches of ``path`` restricted to (and renamed to) ``table``'s columns."""
    rename = rename or {}
    pf = pq.ParquetFile(path)
    available = set(pf.schema_arrow.names)
    source_for = {target: src for src, target in rename.items()}
    columns = sorted(
        source_for.get(c.name, c.name)
        for c in table.columns
        if source_for.get(c.name, c.name) in available
    )
    missing = _required(table) - {rename.get(c, c) for c in columns}
    if missing:
        raise SeedError(f"{path.name} is missing columns for {table.name}: {sorted(missing)}")
    for batch in pf.iter_batches(batch_size=BATCH_ROWS, columns=columns):
        yield batch.rename_columns([rename.get(n, n) for n in batch.schema.names])


def _scores_batches(path: Path) -> Iterator[pa.RecordBatch]:
    # `reasons` may be a JSON string or a list<struct> column; store it as JSON text.
    for batch in _batches(path, table_of(Score)):
        idx = batch.schema.get_field_index("reasons")
        col = batch.column(idx)
        if not (pa.types.is_string(col.type) or pa.types.is_large_string(col.type)):
            col = pa.array([json.dumps(v, ensure_ascii=False) for v in col.to_pylist()])
        yield batch.set_column(idx, "reasons", pc.cast(col, pa.string()))


def load_parquet(conn: Connection, data_dir: Path, scores_path: Path | None) -> dict[str, int]:
    """Load WS1 tables (and WS2 scores if present). Raises SeedError on schema problems."""
    customers = data_dir / "customers.parquet"
    counts = {
        "customers": load_batches(
            conn, table_of(Customer), _batches(customers, table_of(Customer))
        ),
        "accounts": load_batches(
            conn,
            table_of(Account),
            _batches(
                customers,
                table_of(Account),
                {"card_limit_paise": "limit_paise", "card_open_date": "opened_on"},
            ),
        ),
    }
    for name, model in (
        ("protected_attributes", ProtectedAttributes),
        ("account_months", AccountMonth),
    ):
        path = data_dir / f"{name}.parquet"
        if path.exists():
            counts[name] = load_batches(conn, table_of(model), _batches(path, table_of(model)))
    if scores_path is not None and scores_path.exists():
        counts["scores"] = load_batches(conn, table_of(Score), _scores_batches(scores_path))
    return counts
