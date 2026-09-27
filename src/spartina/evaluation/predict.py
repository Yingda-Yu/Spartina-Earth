"""Mosaic inference for a frozen (or training) model on one split."""

from __future__ import annotations

from typing import Any

import numpy as np
import torch

from spartina.data.dataset import PreparedGrid
from spartina.data.pilot0 import (
    VARIANT_BANDS,
    Pilot0Sources,
    windows_for_split,
)
from spartina.evaluation.mosaic import ProbabilityMosaic

DROP_SAR = {9, 10}
DROP_INDICES = {7, 8}


def dropped_source_bands(drop: str | None) -> set[int]:
    if drop is None:
        return set()
    if drop == "sar":
        return set(DROP_SAR)
    if drop == "indices":
        return set(DROP_INDICES)
    if drop == "sar_indices":
        return set(DROP_SAR) | set(DROP_INDICES)
    raise ValueError(f"unknown drop mode: {drop!r}")


@torch.no_grad()
def predict_mosaic(
    model: torch.nn.Module,
    sources: Pilot0Sources,
    grid: PreparedGrid,
    variant: str,
    split: str,
    device: torch.device,
    patch: int = 96,
    batch_size: int = 32,
    drop: str | None = None,
) -> np.ndarray[Any, Any]:
    """Stitched probability raster (NaN outside window coverage)."""
    model.eval()
    bands = VARIANT_BANDS[variant]
    drop_local = {bands.index(b) for b in dropped_source_bands(drop)
                  if b in bands}
    rows = windows_for_split(sources.windows, split)
    mosaic = ProbabilityMosaic(sources.height, sources.width, patch)
    batch_x: list[torch.Tensor] = []
    batch_meta: list[tuple[int, int]] = []

    def flush() -> None:
        if not batch_x:
            return
        x = torch.stack(batch_x).to(device)
        logits = model(x)
        prob = torch.sigmoid(logits.float()).cpu().numpy()[:, 0]
        for (r0, c0), p in zip(batch_meta, prob, strict=True):
            mosaic.add_window(r0, c0, p)
        batch_x.clear()
        batch_meta.clear()

    for row in rows.itertuples(index=False):
        r0, c0 = int(row.row_off), int(row.col_off)
        x = grid.norm[bands][:, r0:r0 + patch, c0:c0 + patch]
        if drop_local:
            for li in drop_local:
                x[li] = 0.0
        batch_x.append(torch.from_numpy(np.ascontiguousarray(x,
                                                             np.float32)))
        batch_meta.append((r0, c0))
        if len(batch_x) >= batch_size:
            flush()
    flush()
    return mosaic.raster()
