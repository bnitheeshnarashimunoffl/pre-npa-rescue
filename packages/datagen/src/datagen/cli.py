"""Command line entry point: ``datagen generate|features|experiment|all``.

Command-line flags override environment variables (see :class:`datagen.config.DatagenConfig`).
"""

import argparse
import logging
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from datagen.config import DatagenConfig
from datagen.generate import run_generate

logger = logging.getLogger("datagen")

Step = Callable[[DatagenConfig], None]


def _not_implemented(task: str) -> Step:
    def run(cfg: DatagenConfig) -> None:
        raise NotImplementedError(f"not implemented yet (task {task})")

    return run


STEPS: dict[str, Step] = {
    "generate": run_generate,
    "features": _not_implemented("1.2"),
    "experiment": _not_implemented("1.3"),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="datagen", description=__doc__)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--seed", type=int, help="RNG seed (env SEED, default 42)")
    common.add_argument("--out", type=Path, help="output directory (env DATA_DIR)")
    common.add_argument("--log-level", default="INFO", help="logging level (default INFO)")

    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("generate", "all"):
        p = sub.add_parser(name, parents=[common], help=f"run '{name}'")
        p.add_argument("--n", type=int, help="number of customers (env DATAGEN_N_CUSTOMERS)")
        p.add_argument(
            "--no-transactions",
            action="store_true",
            help="skip transactions.parquet; keep only the monthly aggregates features need",
        )
    feat = sub.add_parser("features", parents=[common], help="build features and labels (task 1.2)")
    feat.add_argument("--samples", type=Path, help="also write the small samples to this folder")
    sub.add_parser("experiment", parents=[common], help="simulate the experiment (task 1.3)")
    return parser


def config_from_args(args: argparse.Namespace) -> DatagenConfig:
    overrides: dict[str, Any] = {}
    if args.seed is not None:
        overrides["seed"] = args.seed
    if args.out is not None:
        overrides["data_dir"] = args.out
    if getattr(args, "n", None) is not None:
        overrides["n_customers"] = args.n
    if getattr(args, "samples", None) is not None:
        overrides["samples_dir"] = args.samples
    if getattr(args, "no_transactions", False):
        overrides["write_transactions"] = False
    return DatagenConfig(**overrides)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=args.log_level.upper(), format="%(levelname)s %(name)s %(message)s")
    cfg = config_from_args(args)
    names = list(STEPS) if args.command == "all" else [args.command]
    for name in names:
        logger.info("step=%s seed=%s out=%s", name, cfg.seed, cfg.data_dir)
        try:
            STEPS[name](cfg)
        except NotImplementedError as exc:
            logger.error("step=%s error=%s", name, exc)
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
