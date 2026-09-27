"""Spatial probability mosaic with Hann overlap blending.

Windows overlap (stride 48 < patch 96); headline metrics must be
computed on one stitched probability raster, never as an average of
per-window IoUs. Blending accumulates ``p * w`` and ``w`` with a fixed
2-D Hann center weight, which is order independent.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import numpy as np


def hann2d(patch: int) -> np.ndarray[Any, Any]:
    w = np.hanning(patch).astype(np.float64)
    return (w[:, None] * w[None, :]) + 1e-8


class ProbabilityMosaic:
    def __init__(self, height: int, width: int, patch: int) -> None:
        self.numer = np.zeros((height, width), dtype=np.float64)
        self.weight = np.zeros((height, width), dtype=np.float64)
        self.coverage = np.zeros((height, width), dtype=bool)
        self.patch = patch

    def add_window(
        self, row_off: int, col_off: int, prob: np.ndarray[Any, Any],
    ) -> None:
        p = self.patch
        if prob.shape != (p, p):
            raise ValueError(f"expected ({p},{p}) window, got {prob.shape}")
        win = (slice(row_off, row_off + p), slice(col_off, col_off + p))
        w = hann2d(p)
        self.numer[win] += prob.astype(np.float64) * w
        self.weight[win] += w
        self.coverage[win] = True

    def add_windows(
        self, items: Iterable[tuple[int, int, np.ndarray[Any, Any]]],
    ) -> None:
        for row_off, col_off, prob in items:
            self.add_window(row_off, col_off, prob)

    def raster(self) -> np.ndarray[Any, Any]:
        """Blended probabilities; NaN where no window covered a pixel."""
        out = np.full_like(self.numer, np.nan, dtype=np.float64)
        covered = self.weight > 0
        out[covered] = self.numer[covered] / self.weight[covered]
        return out
