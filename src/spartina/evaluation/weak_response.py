"""WEAK-only candidate response diagnostic (NOT accuracy/recall)."""

from __future__ import annotations

from typing import Any

import numpy as np

from spartina.benchmark.splits.components import label_components


def material_weak_labels(
    weak_only: np.ndarray[Any, Any], min_pixels: int = 10,
) -> tuple[np.ndarray[Any, Any], dict[int, Any]]:
    labels, registry = label_components(weak_only, "weakcand")
    material = {i: c for i, c in registry.items()
                if c.pixel_count >= min_pixels}
    keep = np.isin(labels, list(material.keys()))
    labels = np.where(keep, labels, 0).astype("int32")
    return labels, material


def component_responses(
    prob: np.ndarray[Any, Any],
    weak_labels: np.ndarray[Any, Any],
    components: dict[int, Any], threshold: float,
    domain: np.ndarray[Any, Any],
) -> list[dict[str, Any]]:
    """Mean/median prob, above-threshold fraction per material component."""
    rows: list[dict[str, Any]] = []
    finite = ~np.isnan(prob)
    for i, info in sorted(components.items()):
        pix = (weak_labels == i) & domain & finite
        n_covered = int(pix.sum())
        if n_covered == 0:
            continue
        vals = prob[pix]
        above = vals >= threshold
        frac = float(above.mean())
        rows.append({
            "component_id": info.component_id,
            "label_index": i,
            "component_pixels": info.pixel_count,
            "covered_pixels": n_covered,
            "area_ha": info.area_ha,
            "mean_prob": float(vals.mean()),
            "median_prob": float(np.median(vals)),
            "above_threshold_fraction": frac,
            "component_response": int(frac >= 0.5),
        })
    return rows
