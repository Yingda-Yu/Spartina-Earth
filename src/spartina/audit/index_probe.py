"""NDVI / SAI label-association diagnostics on TRAIN/VAL only.

Question (Issue #10 A4): do the spectral indices carry complementary
information, or do they behave like a near-direct label proxy? These are
DIAGNOSTIC associations — they cannot establish causal necessity and they
use no TEST pixels:

* positive-vs-negative reference distributions of NDVI and SAI,
* Pearson correlation and histogram-based mutual information,
* univariate/bivariate logistic probes fitted on TRAIN unique pixels and
  evaluated on VAL (AUPRC + threshold-grid IoU).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from spartina.data.dataset import grid_view_masks
from spartina.data.pilot0 import (
    VARIANT_BANDS,
    split_coverage_mask,
    train_unique_pixel_mask,
)
from spartina.evaluation.metrics import (
    THRESHOLD_GRID_DEFAULT,
    choose_threshold,
)
from spartina.models.baselines.spectral import NDVI_BAND, SAI_BAND

PROBE_VARIANT = "optical_indices"
MI_SAMPLE_CAP = 50_000
PROBE_SEED = 17


def _domain(
    env: dict[str, Any], split: str,
) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any]]:
    sources, grid = env["sources"], env["grid"]
    bands = VARIANT_BANDS[PROBE_VARIANT]
    valid_inputs = np.all(grid.valid[bands], axis=0)
    views = grid_view_masks(sources, grid, PROBE_VARIANT)
    cov = (train_unique_pixel_mask(sources) if split == "train"
           else split_coverage_mask(sources, split))
    valid = views["arbitrated_core"] & cov & valid_inputs
    ndvi = sources.stack[NDVI_BAND]
    sai = sources.stack[SAI_BAND]
    finite = np.isfinite(ndvi) & np.isfinite(sai) & valid
    return np.stack([ndvi[finite], sai[finite]], axis=1).astype(
        np.float64), sources.silver[finite].astype(np.int8)


def _dist_rows(
    X: np.ndarray[Any, Any], y: np.ndarray[Any, Any], split: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for j, name in enumerate(("NDVI", "SAI")):
        for cls in (0, 1):
            v = X[y == cls, j]
            qs = np.quantile(v, [0.05, 0.5, 0.95])
            rows.append({
                "split": split, "feature": name,
                "reference_class": ("spartina" if cls == 1
                                    else "background"),
                "n": int(v.size), "mean": float(v.mean()),
                "std": float(v.std()), "p05": float(qs[0]),
                "median": float(qs[1]), "p95": float(qs[2])})
    return rows


def _mi_hist(x: np.ndarray[Any, Any], y: np.ndarray[Any, Any],
             bins: int = 64) -> float:
    """Histogram-based mutual information I(X;Y) in bits."""
    edges = np.quantile(x, np.linspace(0.0, 1.0, bins + 1))
    edges = np.unique(edges)
    xb = np.clip(np.digitize(x, edges[1:-1]), 0, len(edges) - 2)
    joint = np.zeros((len(edges) - 1, 2), dtype=np.float64)
    for cls in (0, 1):
        joint[:, cls] = np.bincount(xb[y == cls],
                                    minlength=len(edges) - 1)
    pxy = joint / joint.sum()
    px = pxy.sum(axis=1, keepdims=True)
    py = pxy.sum(axis=0, keepdims=True)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = pxy / (px * py)
        term = np.where(pxy > 0, pxy * np.log2(ratio), 0.0)
    return float(term.sum())


def _stratified_subsample(
    X: np.ndarray[Any, Any], y: np.ndarray[Any, Any], cap: int,
) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any]]:
    if X.shape[0] <= cap:
        return X, y
    rng = np.random.default_rng(PROBE_SEED)
    take: list[np.ndarray[Any, Any]] = []
    remaining = cap
    for cls in (0, 1):
        pool = np.flatnonzero(y == cls)
        n = min(cap // 2 if cls == 0 else remaining, pool.size)
        take.append(rng.choice(pool, size=n, replace=False))
        remaining -= n
    sel = np.concatenate(take)
    rng.shuffle(sel)
    return X[sel], y[sel]


def _standardize(
    Xtr: np.ndarray[Any, Any], X: np.ndarray[Any, Any],
) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any], np.ndarray[Any, Any]]:
    mu = Xtr.mean(axis=0)
    sd = Xtr.std(axis=0)
    sd[sd == 0] = 1.0
    return mu, sd, (X - mu) / sd


def build_index_probe(
    env: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import average_precision_score

    Xtr, ytr = _domain(env, "train")
    Xva, yva = _domain(env, "val")
    dist = pd.DataFrame(
        _dist_rows(Xtr, ytr, "train") + _dist_rows(Xva, yva, "val"))

    Xs, ys = _stratified_subsample(Xtr, ytr, MI_SAMPLE_CAP)
    mu, sd, Xtr_n = _standardize(Xs, Xs)
    _, _, Xva_n = _standardize(Xs, Xva)

    probes = (
        ("ndvi_only", (0,)),
        ("sai_only", (1,)),
        ("ndvi_plus_sai", (0, 1)),
    )
    rows: list[dict[str, Any]] = []
    for name, cols in probes:
        clf = LogisticRegression(max_iter=1000, random_state=PROBE_SEED)
        clf.fit(Xtr_n[:, cols], ys)
        prob = clf.predict_proba(Xva_n[:, cols])
        pos = int(np.flatnonzero(clf.classes_ == 1)[0])
        p = prob[:, pos]
        thr, iou = choose_threshold(
            p, yva, np.ones_like(yva, dtype=bool),
            np.array(THRESHOLD_GRID_DEFAULT))
        rows.append({
            "probe": name, "features": "+".join(
                ("NDVI", "SAI")[c] for c in cols),
            "fit_on": "train_unique_arbitrated_core",
            "eval_on": "val_arbitrated_core",
            "n_train": int(Xs.shape[0]), "n_val": int(Xva.shape[0]),
            "val_positive_fraction": float(yva.mean()),
            "val_auprc": float(average_precision_score(yva, p)),
            "val_best_threshold": float(thr),
            "val_threshold_iou": float(iou),
            "coefficients": [float(c) for c in clf.coef_.ravel()],
            "intercept": float(clf.intercept_[0]),
            "mi_bits_train": float(_mi_hist(
                Xs[:, cols[0]] if len(cols) == 1
                else clf.decision_function(Xtr_n[:, cols]), ys)),
            "pearson_r_train": [
                float(np.corrcoef(Xs[:, c], ys)[0, 1]) for c in cols],
            "interpretation": "DIAGNOSTIC_ASSOCIATION_NOT_CAUSAL",
        })
    return dist, pd.DataFrame(rows)
