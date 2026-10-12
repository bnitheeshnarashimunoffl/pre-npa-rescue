"""audit_log append-only triggers (task 5.4)

Rejects UPDATE, DELETE and (Postgres) TRUNCATE on audit_log, whoever the database user is.
If a dedicated application role ``npa_app`` exists, its UPDATE/DELETE/TRUNCATE privileges on
the table are also revoked (IS/ISO/IEC 27001:2022 A.8.15; RBI RBC Directions para 454P).

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-12
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PG_UP = [
    """
    CREATE FUNCTION audit_log_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        RAISE EXCEPTION 'audit_log is append-only (% blocked)', TG_OP;
    END
    $$
    """,
    """
    CREATE TRIGGER audit_log_no_update_delete BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_log_append_only()
    """,
    """
    CREATE TRIGGER audit_log_no_truncate BEFORE TRUNCATE ON audit_log
    FOR EACH STATEMENT EXECUTE FUNCTION audit_log_append_only()
    """,
    """
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'npa_app') THEN
            REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM npa_app;
        END IF;
    END
    $$
    """,
]
_PG_DOWN = [
    "DROP TRIGGER IF EXISTS audit_log_no_truncate ON audit_log",
    "DROP TRIGGER IF EXISTS audit_log_no_update_delete ON audit_log",
    "DROP FUNCTION IF EXISTS audit_log_append_only()",
]
_SQLITE_UP = [
    """
    CREATE TRIGGER audit_log_no_update BEFORE UPDATE ON audit_log
    BEGIN SELECT RAISE(ABORT, 'audit_log is append-only (UPDATE blocked)'); END
    """,
    """
    CREATE TRIGGER audit_log_no_delete BEFORE DELETE ON audit_log
    BEGIN SELECT RAISE(ABORT, 'audit_log is append-only (DELETE blocked)'); END
    """,
]
_SQLITE_DOWN = [
    "DROP TRIGGER IF EXISTS audit_log_no_update",
    "DROP TRIGGER IF EXISTS audit_log_no_delete",
]


def _run(statements: list[str]) -> None:
    for sql in statements:
        op.execute(sql)


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        _run(_PG_UP)
    elif dialect == "sqlite":
        _run(_SQLITE_UP)


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        _run(_PG_DOWN)
    elif dialect == "sqlite":
        _run(_SQLITE_DOWN)
