"""Deterministic single-index rule baselines (SAI primary, NDVI diag)."""

from __future__ import annotations

from typing import Any

import numpy as np

NDVI_BAND = 7
SAI_BAND = 8


def fit_index_threshold(
    values: np.ndarray[Any, Any], y: np.ndarray[Any, Any],
    valid: np.ndarray[Any, Any], lo: float = -1.0, hi: float = 1.0,
    step: float = 0.005,
) -> tuple[float, float]:
    """Best IoU for rule ``value >= t``; tie -> lower threshold."""
    v = values[valid]
    yy = y[valid].astype(bool)
    grid = np.round(np.arange(lo, hi + step / 2, step), 6)
    n_pos = int(yy.sum())
    best_t, best_iou = float(lo), -1.0
    for t in grid:
        pred = v >= t
        tp = int(np.count_nonzero(pred & yy))
        fp = int(np.count_nonzero(pred & ~yy))
        fn = n_pos - tp
        union = tp + fp + fn
        iou = tp / union if union else -1.0
        if iou > best_iou:
            best_t, best_iou = float(t), iou
    return best_t, best_iou


def apply_rule(
    values: np.ndarray[Any, Any], threshold: float,
) -> np.ndarray[Any, Any]:
    return (values >= threshold).astype(np.float32)
