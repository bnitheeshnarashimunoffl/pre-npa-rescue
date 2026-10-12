"""PNG plots for the evaluation report (task 2.5): ROC, PR, calibration, Qini, SHAP summary."""

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")  # headless: no display on CI or servers

import matplotlib.pyplot as plt
import numpy as np
from sklearn.calibration import calibration_curve
from sklearn.metrics import precision_recall_curve, roc_curve
from sklift.metrics import qini_curve

SHAP_TOP = 12


def _save(fig: Any, path: Path) -> Path:
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path


def write_plots(curves: dict[str, Any], out_dir: Path) -> list[Path]:
    """Write whatever plots the curves allow; returns the files written."""
    written: list[Path] = []
    ew = curves.get("early_warning") or {}
    if ew and len(np.unique(ew["y"])) == 2:
        y, p = ew["y"], ew["p"]
        fig, ax = plt.subplots(figsize=(5, 4))
        fpr, tpr, _ = roc_curve(y, p)
        ax.plot(fpr, tpr, label="early warning")
        ax.plot([0, 1], [0, 1], "--", color="grey", label="chance")
        ax.set(xlabel="False positive rate", ylabel="True positive rate", title="ROC")
        ax.legend()
        written.append(_save(fig, out_dir / "roc_early_warning.png"))

        fig, ax = plt.subplots(figsize=(5, 4))
        prec, rec, _ = precision_recall_curve(y, p)
        ax.plot(rec, prec, label="early warning")
        ax.axhline(float(np.mean(y)), linestyle="--", color="grey", label="base rate")
        ax.set(xlabel="Recall", ylabel="Precision", title="Precision-recall")
        ax.legend()
        written.append(_save(fig, out_dir / "pr_early_warning.png"))

        fig, ax = plt.subplots(figsize=(5, 4))
        obs, pred = calibration_curve(y, p, n_bins=10, strategy="quantile")
        ax.plot(pred, obs, marker="o", label="early warning")
        ax.plot([0, 1], [0, 1], "--", color="grey", label="perfect")
        ax.set(xlabel="Predicted probability", ylabel="Observed rate", title="Calibration")
        ax.legend()
        written.append(_save(fig, out_dir / "calibration_early_warning.png"))

    if ew and "shap" in ew:
        mean_abs = ew["shap"].abs().mean().sort_values().tail(SHAP_TOP)
        fig, ax = plt.subplots(figsize=(6, 4.5))
        ax.barh(mean_abs.index, mean_abs.to_numpy())
        ax.set(xlabel="Mean |SHAP| (log-odds)", title="SHAP summary: early warning")
        written.append(_save(fig, out_dir / "shap_summary_early_warning.png"))

    up = curves.get("uplift") or {}
    if up:
        x, q = qini_curve(up["y"], up["uplift"], up["treated"])
        fig, ax = plt.subplots(figsize=(5, 4))
        ax.plot(x, q, label="uplift model")
        ax.plot([0, x[-1]], [0, q[-1]], "--", color="grey", label="random")
        ax.set(xlabel="Accounts targeted", ylabel="Incremental cures", title="Qini (out-of-fold)")
        ax.legend()
        written.append(_save(fig, out_dir / "qini_uplift.png"))
    return written
