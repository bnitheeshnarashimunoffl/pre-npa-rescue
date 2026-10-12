"""``npa-models`` command line: ``train | score | evaluate``.

``train`` fits the early-warning (2.1) and segmentation (2.3) models; uplift joins in 2.4.
Commands not built yet exit with :data:`EXIT_NOT_IMPLEMENTED`.
"""

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

from npa_models import early_warning, segment
from npa_models.config import ModelSettings
from npa_models.registry import save_bundle

EXIT_OK = 0
EXIT_ERROR = 1
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


def _train(args: argparse.Namespace, settings: ModelSettings) -> int:
    for path in (args.features, args.labels):
        if not path.is_file():
            log.error("missing input file=%s hint='run datagen all first'", path)
            return EXIT_ERROR
    for trainer in (early_warning.train, segment.train):
        bundle = trainer(args.features, args.labels, settings)
        out = save_bundle(bundle, settings.model_dir)
        log.info("saved model=%s version=%s dir=%s", bundle.name, bundle.model_version, out)
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    settings = ModelSettings()
    args = _parser(settings).parse_args(argv)
    if args.command == "train":
        return _train(args, settings)
    log.error("command=%s status=not_implemented seed=%d", args.command, settings.seed)
    return EXIT_NOT_IMPLEMENTED
