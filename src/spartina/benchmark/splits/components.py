"""Connected-component registries for split isolation.

Separate registries are built for the SILVER evaluation layer and the
material WEAK-only candidate layer (Issue #4 Step 7/9). Components use
8-connectivity on the 30 m grid.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy import ndimage

PIXEL_AREA_M2 = 30.0 * 30.0


@dataclass(frozen=True)
class ComponentInfo:
    """One connected component in a label layer."""

    component_id: str  # e.g. silver-0007 / weakcand-0003
    label_index: int  # 1-based ndimage label
    pixel_count: int
    area_ha: float
    bbox_top: int
    bbox_left: int
    bbox_bottom: int  # exclusive
    bbox_right: int  # exclusive
    bbox_width_px: int
    bbox_height_px: int
    centroid_row: float
    centroid_col: float
    assigned_split: str | None = None
    quarantined: bool = False
    usable_in_windows: bool = False
    notes: str = ""
    window_tile_ids: list[str] = field(default_factory=list)


def label_components(
    mask: np.ndarray[Any, Any], prefix: str
) -> tuple[np.ndarray[Any, Any], dict[int, ComponentInfo]]:
    """8-connected CC labels + registry keyed by 1-based label index."""
    labels, n = ndimage.label(mask, structure=np.ones((3, 3), dtype="uint8"))
    if n == 0:
        return labels.astype("int32"), {}
    sizes = np.bincount(labels.ravel())
    objs = ndimage.find_objects(labels)
    cy, cx = ndi_centroids(labels, n)
    registry: dict[int, ComponentInfo] = {}
    for i in range(1, n + 1):
        sl = objs[i - 1]
        top, bottom = int(sl[0].start), int(sl[0].stop)
        left, right = int(sl[1].start), int(sl[1].stop)
        registry[i] = ComponentInfo(
            component_id=f"{prefix}-{i - 1:04d}",
            label_index=i,
            pixel_count=int(sizes[i]),
            area_ha=float(sizes[i]) * PIXEL_AREA_M2 / 1e4,
            bbox_top=top,
            bbox_left=left,
            bbox_bottom=bottom,
            bbox_right=right,
            bbox_width_px=right - left,
            bbox_height_px=bottom - top,
            centroid_row=float(cy[i]),
            centroid_col=float(cx[i]),
        )
    return labels.astype("int32"), registry


def ndi_centroids(
    labels: np.ndarray[Any, Any], n: int
) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any]]:
    """Centroids per label index (0 = background), finite defaults."""
    cy = np.zeros(n + 1)
    cx = np.zeros(n + 1)
    rows, cols = np.indices(labels.shape)
    counts = np.bincount(labels.ravel(), minlength=n + 1)
    np.divide(np.bincount(labels.ravel(), weights=rows.ravel(),
                          minlength=n + 1),
              counts, out=cy, where=counts > 0)
    np.divide(np.bincount(labels.ravel(), weights=cols.ravel(),
                          minlength=n + 1),
              counts, out=cx, where=counts > 0)
    return cy, cx


def crossing_component_ids(
    labels: np.ndarray[Any, Any], boundary_col: int
) -> set[int]:
    """Label indices with positive pixels on both sides of a column line."""
    right = (np.indices(labels.shape)[1] >= boundary_col).ravel()
    on_right = np.bincount(labels.ravel(), weights=right.astype(float),
                           minlength=labels.max() + 1)
    totals = np.bincount(labels.ravel(), minlength=labels.max() + 1)
    ids = np.where((on_right > 0) & (on_right < totals))[0]
    return {int(i) for i in ids if i > 0}
