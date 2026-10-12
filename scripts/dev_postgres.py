"""Run a local Postgres 16 without Docker, for development and tests (uses ``pgserver``).

Usage (from the repo root, any OS):
    uv run --with pgserver python scripts/dev_postgres.py            # data in ./.pgdata
    uv run --with pgserver python scripts/dev_postgres.py --reset    # start from empty

It prints a DATABASE_URL to export, creates the ``npa`` database, and keeps running until
Ctrl+C. ``pgserver`` is deliberately not a project dependency; ``uv run --with`` fetches it.
"""

import argparse
import shutil
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=REPO_ROOT / ".pgdata")
    parser.add_argument("--reset", action="store_true", help="delete the data dir first")
    args = parser.parse_args()

    try:
        import pgserver  # type: ignore[import-not-found]
        import psycopg
    except ImportError:
        print("Run with: uv run --with pgserver python scripts/dev_postgres.py")
        return 1

    if args.reset and args.data_dir.exists():
        shutil.rmtree(args.data_dir)
    server = pgserver.get_server(args.data_dir, cleanup_mode="stop")
    base = server.get_uri()  # postgresql://postgres:@127.0.0.1:<port>/postgres
    with psycopg.connect(base, autocommit=True) as conn:
        if not conn.execute("SELECT 1 FROM pg_database WHERE datname = 'npa'").fetchone():
            conn.execute("CREATE DATABASE npa")
    url = base.rsplit("/", 1)[0].replace("postgresql://", "postgresql+psycopg://") + "/npa"
    print(f"Postgres is running. In another terminal:\n\n  DATABASE_URL={url}\n")
    print("PowerShell:  $env:DATABASE_URL = '" + url + "'", flush=True)
    print("Ctrl+C to stop.", flush=True)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
