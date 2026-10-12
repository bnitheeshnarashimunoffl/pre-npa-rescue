"""CLI: ``uv run python -m seed [--reset] [--source auto|parquet|fixtures]``."""

import argparse
import logging
import sys
from pathlib import Path

from app.config import get_settings
from app.db import make_engine
from seed import SeedError, seed_database


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(prog="python -m seed", description=__doc__)
    parser.add_argument("--reset", action="store_true", help="delete all rows first")
    parser.add_argument("--source", choices=["auto", "parquet", "fixtures"], default="auto")
    parser.add_argument("--database-url", default=settings.database_url)
    parser.add_argument("--data-dir", type=Path, default=settings.data_dir)
    parser.add_argument(
        "--scores",
        type=Path,
        default=None,
        help="WS2 scores.parquet (default: DATA_DIR, then MODEL_DIR)",
    )
    parser.add_argument("--as-of-month", default=settings.as_of_month)
    args = parser.parse_args(argv)
    logging.basicConfig(level=settings.log_level, format="%(levelname)s %(name)s %(message)s")
    log = logging.getLogger("seed")

    scores = args.scores
    if scores is None:
        candidates = [args.data_dir / "scores.parquet", settings.model_dir / "scores.parquet"]
        scores = next((p for p in candidates if p.exists()), None)
    try:
        report = seed_database(
            make_engine(args.database_url),
            data_dir=args.data_dir,
            contracts_dir=settings.contracts_dir,
            policy_path=settings.policy_path,
            as_of_month=args.as_of_month,
            scores_path=scores,
            source=args.source,
            reset=args.reset,
        )
    except SeedError as exc:
        log.error("seed failed: %s", exc)
        return 1
    for warning in report.warnings:
        log.warning(warning)
    counts = " ".join(f"{k}={v}" for k, v in sorted(report.counts.items()))
    log.info("seeded source=%s seconds=%s %s", report.source, report.seconds, counts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
