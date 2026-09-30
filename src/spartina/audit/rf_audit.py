"""Random-forest low-threshold audit on TRAIN/VAL artifacts only.

The frozen ``rf.joblib`` of each official RF run is reloaded on CPU and
scored on the VALIDATION mosaic (never embargoed). Nothing is refit and
TEST is never accessed. The audit verifies the positive-class column
selection, class balance, ranking quality (AUPRC/AUROC), calibration and
the probability mass near the 0.05 threshold-grid boundary.
"""

from __future__ import annotations

import math
from typing import Any

import joblib
import numpy as np
import pandas as pd

from spartina.audit.paths import RunArtifact
from spartina.data.dataset import grid_view_masks
from spartina.data.pilot0 import (
    VARIANT_BANDS,
    split_coverage_mask,
    train_unique_pixel_mask,
)
from spartina.evaluation.metrics import auprc, calibration
from spartina.models.baselines.random_forest import rf_predict_proba

# Fixed probability-mass bins (fractions reported per bin).
HIST_EDGES: tuple[float, ...] = (
    0.0, 0.01, 0.05, 0.10, 0.20, 0.30, 0.50, 0.70, 0.90, 0.95, 1.01)


def _hist_fractions(p: np.ndarray[Any, Any]) -> dict[str, float]:
    idx = np.clip(np.digitize(p, HIST_EDGES[1:-1]), 0, len(HIST_EDGES) - 2)
    counts = np.bincount(idx, minlength=len(HIST_EDGES) - 1)
    frac = counts / max(int(counts.sum()), 1)
    return {f"prob_mass_{lo:0.2f}_{hi:0.2f}".replace(".", "p"): float(f)
            for lo, hi, f in zip(HIST_EDGES[:-1], HIST_EDGES[1:], frac, strict=False)}


def _quantiles(p: np.ndarray[Any, Any], prefix: str) -> dict[str, float]:
    qs = np.quantile(p, [0.0, 0.05, 0.5, 0.95, 1.0])
    return {f"{prefix}_min": float(qs[0]), f"{prefix}_p05": float(qs[1]),
            f"{prefix}_median": float(qs[2]), f"{prefix}_p95": float(qs[3]),
            f"{prefix}_max": float(qs[4])}


def _train_balance(
    run: RunArtifact, env: dict[str, Any],
) -> dict[str, int | float | bool]:
    """Static TRAIN counts per variant (TRAIN was never embargoed)."""
    sources, grid = env["sources"], env["grid"]
    bands = VARIANT_BANDS[run.variant]
    views = grid_view_masks(sources, grid, run.variant)
    valid_inputs = np.all(grid.valid[bands], axis=0)
    domain = train_unique_pixel_mask(sources) & views["arbitrated_core"] \
        & valid_inputs
    y = sources.silver[domain].astype(np.int8)
    n_pos = int(y.sum())
    n_neg = int(y.size - n_pos)
    n_fit = int(run.manifest.get("n_train_pixels", -1))
    return {
        "train_domain_pixels": int(y.size),
        "train_domain_positive": n_pos,
        "train_domain_negative": n_neg,
        "train_domain_positive_fraction": (
            n_pos / y.size if y.size else math.nan),
        "fitted_pixels_manifest": n_fit,
        "subsample_cap_binds": (
            n_fit >= 0 and n_fit < int(y.size)),
    }


def rf_val_diagnostics(
    run: RunArtifact, env: dict[str, Any],
) -> dict[str, Any]:
    """Reload frozen RF and score VAL arbitrated_core (CPU)."""
    from sklearn.metrics import roc_auc_score  # local: sklearn optional

    sources, grid = env["sources"], env["grid"]
    blob = joblib.load(run.dir / "rf.joblib")
    rf = blob["rf"]
    bands = blob["bands"]
    val_cov = split_coverage_mask(sources, "val")
    valid_inputs = np.all(grid.valid[bands], axis=0)
    prob = rf_predict_proba(rf, grid.norm[bands], val_cov & valid_inputs)
    views = grid_view_masks(sources, grid, run.variant)
    valid = views["arbitrated_core"] & val_cov & ~np.isnan(prob)
    p = np.nan_to_num(prob)[valid]
    y = sources.silver[valid].astype(np.int8)

    classes = [int(c) for c in rf.classes_]
    pos_col = int(np.flatnonzero(rf.classes_ == 1)[0])
    out: dict[str, Any] = {
        "rf_classes": ",".join(map(str, classes)),
        "positive_class_label": 1,
        "positive_column_index": pos_col,
        "class_index_inversion": (not classes) or classes != sorted(classes)
        or pos_col != len(classes) - 1,
        "val_n_pixels": int(y.size),
        "val_positive_pixels": int(y.sum()),
        "val_positive_fraction": float(y.mean()),
        "val_auprc": auprc(np.nan_to_num(prob), sources.silver, valid),
        "val_auroc": float(roc_auc_score(y, p)),
        "stored_val_threshold": float(run.manifest["val_threshold"]),
        "threshold_at_lower_bound": float(run.manifest["val_threshold"])
        <= 0.0500001,
        "val_frac_pixels_below_0p05": float((p < 0.05).mean()),
        "val_pred_positive_fraction_at_thr": float(
            (p >= float(run.manifest["val_threshold"])).mean()),
    }
    out.update(calibration(np.nan_to_num(prob), sources.silver, valid))
    out.update(_quantiles(p, "prob"))
    if y.any():
        out.update(_quantiles(p[y.astype(bool)], "prob_pos_ref"))
    if (~y.astype(bool)).any():
        out.update(_quantiles(p[~y.astype(bool)], "prob_neg_ref"))
    out.update(_hist_fractions(p))
    out.update(_train_balance(run, env))

    # cross-check recomputed threshold-grid optimum against stored value
    from spartina.evaluation.metrics import (
        THRESHOLD_GRID_DEFAULT,
        choose_threshold,
    )
    thr, _ = choose_threshold(
        np.nan_to_num(prob), sources.silver, valid,
        np.array(THRESHOLD_GRID_DEFAULT))
    out["recomputed_val_threshold"] = float(thr)
    out["threshold_matches_stored"] = (
        abs(thr - float(run.manifest["val_threshold"])) < 1e-12)
    return out


def build_rf_audit(
    runs: list[RunArtifact], env: dict[str, Any],
) -> pd.DataFrame:
    """One row per official completed RF run (12)."""
    rf_runs = sorted(
        (r for r in runs if r.model == "random_forest"
         and r.phase == "official" and r.status == "COMPLETED"),
        key=lambda r: (r.variant, r.seed or -1))
    rows: list[dict[str, Any]] = []
    for run in rf_runs:
        row: dict[str, Any] = {
            "run_id": run.run_id, "variant": run.variant, "seed": run.seed}
        row.update(rf_val_diagnostics(run, env))
        rows.append(row)
    return pd.DataFrame(rows)
