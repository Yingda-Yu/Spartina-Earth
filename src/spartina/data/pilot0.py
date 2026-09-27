"""Pilot-0 source access for M1.5 baseline experiments.

Loads the frozen Issue #3 stack / label rasters and the frozen Issue #4
window manifest. Everything is read from the accepted v1 artifacts; no
chip export, no split modification.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import rasterio

VARIANT_BANDS: dict[str, list[int]] = {
    "optical": [0, 1, 2, 3, 4, 5, 6],
    "optical_indices": [0, 1, 2, 3, 4, 5, 6, 7, 8],
    "optical_sar": [0, 1, 2, 3, 4, 5, 6, 9, 10],
    "full": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
}
SPLITS = ("train", "val", "test")


@dataclass(frozen=True)
class Pilot0Sources:
    """In-memory source arrays for the whole 1292 x 501 analysis grid."""

    stack: np.ndarray[Any, Any]          # (11, H, W) float32, NaN = invalid
    weak: np.ndarray[Any, Any]           # bool (H, W)
    silver: np.ndarray[Any, Any]         # bool
    ignore: np.ndarray[Any, Any]         # bool
    weak_only: np.ndarray[Any, Any]      # bool: weak+ / silver- / non-ignore
    windows: pd.DataFrame
    crs: str
    transform: tuple[float, ...]
    stack_checksum: str
    root: Path

    @property
    def height(self) -> int:
        return int(self.stack.shape[1])

    @property
    def width(self) -> int:
        return int(self.stack.shape[2])


def load_sources(root: Path, common_cfg: dict[str, Any]) -> Pilot0Sources:
    paths = common_cfg["paths"]
    with rasterio.open(root / paths["stack"]) as ds:
        stack = ds.read().astype(np.float32)
        crs = str(ds.crs)
        gt = ds.transform
        transform = (gt.a, gt.b, gt.c, gt.d, gt.e, gt.f)
    with rasterio.open(root / paths["labels"]) as ds:
        labels = ds.read()
        weak = labels[0].astype(bool)
        silver = labels[1].astype(bool)
        ignore = labels[2].astype(bool)
    weak_only = weak & ~silver & ~ignore
    windows = pd.read_parquet(root / paths["tiles_manifest"])
    # checksum is identical on every row by construction
    stack_checksum = str(windows["source_stack_checksum"].iloc[0])
    return Pilot0Sources(
        stack=stack, weak=weak, silver=silver, ignore=ignore,
        weak_only=weak_only, windows=windows, crs=crs,
        transform=transform, stack_checksum=stack_checksum, root=root,
    )


def windows_for_split(windows: pd.DataFrame, split: str) -> pd.DataFrame:
    """Active (eligible, non-blocked) windows assigned to one split."""
    if split not in SPLITS:
        raise ValueError(f"unknown split: {split!r}")
    out = windows[windows["split"] == split].copy()
    if out.empty:
        raise RuntimeError(f"no active windows for split {split!r}")
    return out.sort_values(["row_off", "col_off"]).reset_index(drop=True)


def window_array(
    sources: Pilot0Sources, row_off: int, col_off: int, patch: int,
) -> np.ndarray[Any, Any]:
    return sources.stack[:, row_off:row_off + patch,
                         col_off:col_off + patch]


def train_unique_pixel_mask(sources: Pilot0Sources) -> np.ndarray[Any, Any]:
    """Union coverage of active TRAIN windows = unique train source px.

    Overlapping windows (stride 48 < patch 96) are de-duplicated by
    rasterizing onto one grid mask.
    """
    patch = int(sources.windows["height"].iloc[0])
    rows = windows_for_split(sources.windows, "train")
    mask = np.zeros((sources.height, sources.width), dtype=bool)
    for r in rows.itertuples(index=False):
        mask[r.row_off:r.row_off + patch, r.col_off:r.col_off + patch] = True
    return mask


def split_coverage_mask(
    sources: Pilot0Sources, split: str,
) -> np.ndarray[Any, Any]:
    """Union pixel coverage of the active windows of one split."""
    patch = int(sources.windows["height"].iloc[0])
    rows = windows_for_split(sources.windows, split)
    mask = np.zeros((sources.height, sources.width), dtype=bool)
    for r in rows.itertuples(index=False):
        mask[r.row_off:r.row_off + patch, r.col_off:r.col_off + patch] = True
    return mask
