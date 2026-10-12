"""Classification metrics shared by training and the evaluation report.

IS/ISO/IEC TS 4213 (assessment of ML classification performance): discrimination (ROC-AUC,
PR-AUC, KS) and calibration (Brier) are reported side by side, always with the base rate, and
with bootstrap confidence intervals in the evaluation report.
"""

from collections.abc import Callable, Mapping

import numpy as np
import numpy.typing as npt
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score, roc_curve


def ks_statistic(y_true: npt.ArrayLike, p: npt.ArrayLike) -> float:
    """Kolmogorov-Smirnov statistic: max separation of the positive and negative score CDFs."""
    fpr, tpr, _ = roc_curve(y_true, p)
    return float(np.max(tpr - fpr))


def binary_metrics(y_true: npt.ArrayLike, p: npt.ArrayLike) -> dict[str, float]:
    """ROC-AUC, PR-AUC, Brier, KS and base rate. Needs both classes in ``y_true``."""
    y = np.asarray(y_true, dtype=int)
    if len(np.unique(y)) < 2:
        raise ValueError("binary metrics need both positive and negative examples")
    return {
        "roc_auc": float(roc_auc_score(y, p)),
        "pr_auc": float(average_precision_score(y, p)),
        "brier": float(brier_score_loss(y, p)),
        "ks": ks_statistic(y, p),
        "base_rate": float(y.mean()),
        "n": len(y),
    }


def bootstrap_ci(
    stat: Callable[[npt.NDArray[np.int_]], Mapping[str, float]],
    n: int,
    *,
    n_boot: int,
    seed: int,
    level: float = 0.95,
) -> dict[str, list[float]]:
    """Percentile bootstrap intervals for every metric ``stat(indices)`` returns.

    Resamples where ``stat`` raises ``ValueError`` (e.g. only one class drawn) are skipped.
    """
    if n < 1 or n_boot < 1:
        raise ValueError(f"need n >= 1 and n_boot >= 1, got {n}, {n_boot}")
    rng = np.random.default_rng(seed)
    draws: list[Mapping[str, float]] = []
    for _ in range(n_boot):
        try:
            draws.append(stat(rng.integers(0, n, n)))
        except ValueError:
            continue
    if not draws:
        return {}
    tail = (1.0 - level) / 2 * 100
    return {
        k: [float(np.percentile(v, tail)), float(np.percentile(v, 100 - tail))]
        for k in draws[0]
        for v in [np.array([d[k] for d in draws], dtype=float)]
    }
