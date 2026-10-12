"""``npa-models`` command line: ``train | score | evaluate``.

``train`` fits the early-warning (2.1) and segmentation (2.3) models; ``train --all`` also fits
the uplift model (2.4), which needs WS1's ``experiment.parquet``. ``evaluate`` writes the model
cards, ``metrics.json`` and the policy reports (2.5). Commands not built yet exit with
:data:`EXIT_NOT_IMPLEMENTED`.
"""

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

import pandas as pd

from npa_models import early_warning, evaluate, fairness, segment, uplift
from npa_models.config import ModelSettings
from npa_models.registry import ModelBundle, save_bundle

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
    train.add_argument("--all", action="store_true", help="also train the uplift model")
    train.add_argument("--features", type=Path, default=settings.data_dir / "features.parquet")
    train.add_argument("--labels", type=Path, default=settings.data_dir / "labels.parquet")
    train.add_argument("--experiment", type=Path, default=settings.data_dir / "experiment.parquet")

    score = sub.add_parser("score", help="batch-score one month to scores.parquet")
    score.add_argument("--as-of", default=settings.as_of_month, help="YYYY-MM")
    score.add_argument("--out", type=Path, default=settings.data_dir / "scores.parquet")

    ev = sub.add_parser("evaluate", help="write model cards and metrics to reports/")
    ev.add_argument("--features", type=Path, default=settings.data_dir / "features.parquet")
    ev.add_argument("--labels", type=Path, default=settings.data_dir / "labels.parquet")
    ev.add_argument("--protected", type=Path, default=settings.data_dir / fairness.PROTECTED_FILE)
    ev.add_argument("--experiment", type=Path, default=settings.data_dir / "experiment.parquet")
    ev.add_argument(
        "--potential", type=Path, default=settings.data_dir / "experiment_potential.parquet"
    )
    ev.add_argument("--out", type=Path, default=settings.reports_dir)
    ev.add_argument("--no-plots", action="store_true", help="skip the PNG plots")
    return p


def _save(bundle: ModelBundle, settings: ModelSettings) -> None:
    out = save_bundle(bundle, settings.model_dir)
    log.info("saved model=%s version=%s dir=%s", bundle.name, bundle.model_version, out)


def _train(args: argparse.Namespace, settings: ModelSettings) -> int:
    needed = [args.features, args.labels] + ([args.experiment] if args.all else [])
    for path in needed:
        if not path.is_file():
            log.error("missing input file=%s hint='run datagen all first'", path)
            return EXIT_ERROR
    for trainer in (early_warning.train, segment.train):
        _save(trainer(args.features, args.labels, settings), settings)
    if args.all:
        _save(uplift.train(args.features, args.experiment, settings), settings)
    return EXIT_OK


def _optional(path: Path) -> pd.DataFrame | None:
    if path.is_file():
        return pd.read_parquet(path)
    log.warning("optional input missing file=%s (its report section stays pending)", path)
    return None


def _evaluate(args: argparse.Namespace, settings: ModelSettings) -> int:
    for path in (args.features, args.labels, args.protected):
        if not path.is_file():
            log.error("missing input file=%s hint='run datagen all first'", path)
            return EXIT_ERROR
    try:
        models = evaluate.Models(
            early_warning=early_warning.EarlyWarningModel.load(settings.model_dir),
            segment=segment.SegmentModel.load(settings.model_dir),
        )
    except FileNotFoundError as exc:
        log.error("%s", exc)
        return EXIT_ERROR
    try:
        models.uplift = uplift.UpliftModel.load(settings.model_dir)
    except FileNotFoundError:
        log.warning(
            "no uplift model in %s (run train --all); uplift stays pending", settings.model_dir
        )
    data = evaluate.EvalData(
        features=pd.read_parquet(args.features),
        labels=pd.read_parquet(args.labels),
        protected=fairness.load_protected(args.protected),
        experiment=_optional(args.experiment),
        potential=_optional(args.potential),
    )
    report = evaluate.evaluate(models, data, as_of_month=settings.as_of_month, seed=settings.seed)
    for path in evaluate.write_reports(report, args.out, plots=not args.no_plots):
        log.info("wrote %s", path)
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    settings = ModelSettings()
    args = _parser(settings).parse_args(argv)
    if args.command == "train":
        return _train(args, settings)
    if args.command == "evaluate":
        return _evaluate(args, settings)
    log.error("command=%s status=not_implemented seed=%d", args.command, settings.seed)
    return EXIT_NOT_IMPLEMENTED
