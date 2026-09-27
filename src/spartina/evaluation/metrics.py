"""Pilot-0 evaluation metrics on stitched mosaics.

Pixel (IoU/Dice/Precision/Recall/AUPRC), boundary F1 (@30/@60 m),
8-connected one-to-one patch matching (IoU>=0.25 primary, >=0.50 supp),
small-patch recall, area error, calibration (Brier, ECE-15).
"""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy import ndimage, optimize

THRESHOLD_GRID_DEFAULT = np.round(np.arange(0.05, 0.9501, 0.01), 2)


def confusion(
    prob: np.ndarray[Any, Any], y: np.ndarray[Any, Any],
    valid: np.ndarray[Any, Any], threshold: float,
) -> dict[str, int]:
    p = (prob[valid] >= threshold)
    t = y[valid].astype(bool)
    tp = int(np.count_nonzero(p & t))
    fp = int(np.count_nonzero(p & ~t))
    fn = int(np.count_nonzero(~p & t))
    tn = int(np.count_nonzero(~p & ~t))
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn}


def pixel_rates(c: dict[str, int]) -> dict[str, float | None]:
    tp, fp, fn = c["tp"], c["fp"], c["fn"]
    denom_iou = tp + fp + fn
    denom_p = tp + fp
    denom_r = tp + fn
    iou = tp / denom_iou if denom_iou else None
    prec = tp / denom_p if denom_p else None
    rec = tp / denom_r if denom_r else None
    f1 = (2 * tp / (2 * tp + fp + fn)) if (2 * tp + fp + fn) else None
    return {"iou": iou, "precision": prec, "recall": rec, "f1": f1}


def choose_threshold(
    prob: np.ndarray[Any, Any], y: np.ndarray[Any, Any],
    valid: np.ndarray[Any, Any],
    grid: np.ndarray[Any, Any] = THRESHOLD_GRID_DEFAULT,
) -> tuple[float, float]:
    """Maximize IoU; tie-break: closest to 0.5, then lower threshold."""
    best: tuple[tuple[float, float, float], float, float] | None = None
    for t in grid:
        rates = pixel_rates(confusion(prob, y, valid, float(t)))
        iou = rates["iou"]
        if iou is None:
            continue
        key = (-float(iou), abs(float(t) - 0.5), float(t))
        if best is None or key < best[0]:
            best = (key, float(t), float(iou))
    if best is None:
        raise RuntimeError("no valid threshold produced a metric")
    return best[1], best[2]


def auprc(
    prob: np.ndarray[Any, Any], y: np.ndarray[Any, Any],
    valid: np.ndarray[Any, Any],
) -> float | None:
    from sklearn.metrics import average_precision_score
    pv, yv = prob[valid], y[valid].astype(np.int8)
    if yv.sum() == 0 or yv.sum() == yv.size:
        return None
    return float(average_precision_score(yv, pv))


def calibration(
    prob: np.ndarray[Any, Any], y: np.ndarray[Any, Any],
    valid: np.ndarray[Any, Any], n_bins: int = 15,
) -> dict[str, float]:
    pv, yv = prob[valid], y[valid].astype(np.float64)
    brier = float(np.mean((pv - yv) ** 2))
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    n = pv.size
    for i in range(n_bins):
        lo, hi = bins[i], bins[i + 1]
        sel = (pv >= lo) & (pv < hi if i < n_bins - 1 else pv <= hi)
        if sel.sum() == 0:
            continue
        ece += (sel.sum() / n) * abs(pv[sel].mean() - yv[sel].mean())
    return {"brier": brier, "ece": float(ece)}


def _boundary(mask: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
    eroded = ndimage.binary_erosion(mask, border_value=0)
    return np.asarray(mask & ~eroded, dtype=bool)


def boundary_f1(
    pred: np.ndarray[Any, Any], ref: np.ndarray[Any, Any],
    tolerance_px: int,
) -> float | None:
    bp, br = _boundary(pred), _boundary(ref)
    if not bp.any() and not br.any():
        return None
    if not bp.any() or not br.any():
        return 0.0
    dist_to_ref = ndimage.distance_transform_edt(~br)
    dist_to_pred = ndimage.distance_transform_edt(~bp)
    precision = float(np.mean(dist_to_ref[bp] <= tolerance_px))
    recall = float(np.mean(dist_to_pred[br] <= tolerance_px))
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def patch_matching(
    pred: np.ndarray[Any, Any], ref: np.ndarray[Any, Any],
    min_iou: float,
) -> dict[str, Any]:
    """One-to-one 8-connected component matching via Hungarian assignment."""
    struct = np.ones((3, 3), dtype="uint8")
    rlab, nr = ndimage.label(ref, structure=struct)
    plab, np_ = ndimage.label(pred, structure=struct)
    matches: list[tuple[int, int, float]] = []
    small_ref = {i: int(np.count_nonzero(rlab == i)) < 10
                 for i in range(1, nr + 1)}
    if nr and np_:
        rsizes = np.bincount(rlab.ravel())
        psizes = np.bincount(plab.ravel())
        # candidate pairs limited to overlapping bounding regions
        ious = np.zeros((nr, np_), dtype=np.float64)
        overlap = plab[rlab > 0]
        rids = rlab[rlab > 0]
        pairs = np.unique(np.stack([rids, overlap]), axis=1)
        for ri, pi in zip(pairs[0], pairs[1], strict=True):
            inter = int(np.count_nonzero((rlab == ri) & (plab == pi)))
            union = int(rsizes[ri] + psizes[pi] - inter)
            ious[ri - 1, pi - 1] = inter / union if union else 0.0
        if ious.size:
            r_ind, p_ind = optimize.linear_sum_assignment(-ious)
            for ri, pi in zip(r_ind, p_ind, strict=True):
                if ious[ri, pi] >= min_iou:
                    matches.append((ri + 1, pi + 1, float(ious[ri, pi])))
    matched_ref = {m[0] for m in matches}
    small_ids = {i for i, s in small_ref.items() if s}
    small_matched = len(small_ids & matched_ref)
    return {
        "n_ref": int(nr),
        "n_pred": int(np_),
        "n_matches": len(matches),
        "patch_precision": (len(matches) / np_) if np_ else None,
        "patch_recall": (len(matches) / nr) if nr else None,
        "small_ref_count": len(small_ids),
        "small_patch_recall": (small_matched / len(small_ids)
                               if small_ids else None),
        "matches": matches,
    }


def area_metrics(
    pred: np.ndarray[Any, Any], ref: np.ndarray[Any, Any],
    pixel_area_m2: float = 900.0,
) -> dict[str, float | None]:
    pa, ra = int(pred.sum()), int(ref.sum())
    diff = pa - ra
    return {
        "pred_area_ha": pa * pixel_area_m2 / 1e4,
        "ref_area_ha": ra * pixel_area_m2 / 1e4,
        "abs_area_error_ha": abs(diff) * pixel_area_m2 / 1e4,
        "rel_area_error": (abs(diff) / ra) if ra else None,
        "signed_area_bias": (diff / ra) if ra else None,
    }


def evaluate_view(
    prob: np.ndarray[Any, Any], y: np.ndarray[Any, Any],
    valid: np.ndarray[Any, Any], threshold: float,
    pixel_area_m2: float = 900.0, ece_bins: int = 15,
) -> dict[str, Any]:
    """Full metric bundle for one label view on a stitched mosaic."""
    c = confusion(prob, y, valid, threshold)
    rates = pixel_rates(c)
    pred = (prob >= threshold) & valid
    ref = y & valid
    out: dict[str, Any] = {
        "threshold": threshold,
        "n_valid_pixels": int(valid.sum()),
        "n_positive_pixels": int(ref.sum()),
        **rates,
        "auprc": auprc(prob, y, valid),
        "bf1_30m": boundary_f1(pred, ref, 1),
        "bf1_60m": boundary_f1(pred, ref, 2),
        "patch_025": {k: v for k, v in patch_matching(pred, ref, 0.25)
                      .items() if k != "matches"},
        "patch_050": {k: v for k, v in patch_matching(pred, ref, 0.50)
                      .items() if k != "matches"},
        **area_metrics(pred, ref, pixel_area_m2),
    }
    out.update(calibration(prob, y, valid, ece_bins))
    return out
