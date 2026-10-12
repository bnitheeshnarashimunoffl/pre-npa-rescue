"""``npa-models`` command line: ``train | score | evaluate``.

Skeleton: the commands parse their arguments and exit with :data:`EXIT_NOT_IMPLEMENTED` until
tasks 2.1-2.5 fill them in.
"""

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

from npa_models.config import ModelSettings

EXIT_NOT_IMPLEMENTED = 3

log = logging.getLogger("npa_models.cli")


def _parser(settings: ModelSettings) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="npa-models", description="Train, score and evaluate the Pre-NPA Rescue models."
    )
    sub = p.add_subparsers(dest="command", required=True)

    train = sub.add_parser("train", help="train models from features/labels parquet")
    train.add_argument("--all", action="store_true", help="train every model")
    train.add_argument("--features", type=Path, default=settings.data_dir / "features.parquet")
    train.add_argument("--labels", type=Path, default=settings.data_dir / "labels.parquet")

    score = sub.add_parser("score", help="batch-score one month to scores.parquet")
    score.add_argument("--as-of", default=settings.as_of_month, help="YYYY-MM")
    score.add_argument("--out", type=Path, default=settings.data_dir / "scores.parquet")

    sub.add_parser("evaluate", help="write model cards and metrics to reports/")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    settings = ModelSettings()
    args = _parser(settings).parse_args(argv)
    log.error("command=%s status=not_implemented seed=%d", args.command, settings.seed)
    return EXIT_NOT_IMPLEMENTED
