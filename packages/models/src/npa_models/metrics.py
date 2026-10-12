"""Classification metrics shared by training and the evaluation report.

IS/ISO/IEC TS 4213 (assessment of ML classification performance): discrimination (ROC-AUC,
PR-AUC, KS) and calibration (Brier) are reported side by side, always with the base rate.
"""

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
