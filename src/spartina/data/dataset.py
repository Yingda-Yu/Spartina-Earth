"""Torch datasets and label-view masks for Pilot-0 baseline runs.

Three label views (Issue #5 execution spec section 3):

* ``arbitrated_core`` (PRIMARY): IGNORE, invalid-input and
  WEAK-positive/SILVER-negative disagreement pixels are excluded; target
  is SILVER. WEAK-only pixels are NEVER silently trained as background.
* ``silver_strict`` (SECONDARY): SILVER product outside IGNORE; WEAK-only
  locations are background. Interpretation: SILVER-product reproduction.
* ``weak_only``: diagnostic mask; never an accuracy denominator.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import torch
from torch.utils.data import Dataset

from spartina.data.normalization import BandStats, apply_normalization
from spartina.data.pilot0 import (
    VARIANT_BANDS,
    Pilot0Sources,
    windows_for_split,
)
from spartina.experiments.embargo import EmbargoGate

PATCH_DEFAULT = 96


@dataclass(frozen=True)
class PreparedGrid:
    """Normalized 11-band grid plus per-band finite-validity masks."""

    norm: np.ndarray[Any, Any]            # (11, H, W) float32
    valid: np.ndarray[Any, Any]           # (11, H, W) bool
    stats: list[BandStats]


def prepare_grid(
    sources: Pilot0Sources, stats: list[BandStats],
) -> PreparedGrid:
    norm = apply_normalization(sources.stack, stats)
    valid = np.isfinite(sources.stack)
    return PreparedGrid(norm=norm, valid=valid, stats=stats)


def view_masks(
    valid_inputs: np.ndarray[Any, Any],
    silver: np.ndarray[Any, Any],
    weak: np.ndarray[Any, Any],
    ignore: np.ndarray[Any, Any],
    weak_only: np.ndarray[Any, Any],
) -> dict[str, np.ndarray[Any, Any]]:
    """Return core/strict validity masks over a window or full grid."""
    not_ignore = ~ignore
    core_valid = not_ignore & valid_inputs & ~(weak & ~silver)
    strict_valid = not_ignore & valid_inputs
    weak_candidate = weak_only & valid_inputs
    return {"arbitrated_core": core_valid, "silver_strict": strict_valid,
            "weak_only": weak_candidate}


def geometric_transform(
    x: np.ndarray[Any, Any], masks: dict[str, np.ndarray[Any, Any]],
    kind: int,
) -> tuple[np.ndarray[Any, Any], dict[str, np.ndarray[Any, Any]]]:
    """Deterministic geometric transform shared by x and every mask.

    kind: 0 identity, 1 hflip, 2 vflip, 3 rot90, 4 rot180, 5 rot270.
    Rotations are k * 90 deg CCW on the (row, col) plane.
    """
    if kind == 0:
        return x, masks
    if kind == 1:
        xt = x[:, :, ::-1]
        mt = {k: v[:, ::-1] for k, v in masks.items()}
        return np.ascontiguousarray(xt), {k: np.ascontiguousarray(v)
                                          for k, v in mt.items()}
    if kind == 2:
        xt = x[:, ::-1, :]
        mt = {k: v[::-1, :] for k, v in masks.items()}
        return np.ascontiguousarray(xt), {k: np.ascontiguousarray(v)
                                          for k, v in mt.items()}
    k = {3: 1, 4: 2, 5: 3}[kind]
    xt = np.rot90(x, k=k, axes=(1, 2))
    mt = {kk: np.ascontiguousarray(np.rot90(v, k=k))
          for kk, v in masks.items()}
    return np.ascontiguousarray(xt), mt


class Pilot0WindowDataset(Dataset[dict[str, Any]]):
    """Windows of one split for one input variant."""

    KINDS = (0, 1, 2, 3, 4, 5)

    def __init__(
        self,
        sources: Pilot0Sources,
        grid: PreparedGrid,
        variant: str,
        split: str,
        gate: EmbargoGate,
        patch: int = PATCH_DEFAULT,
        train: bool = False,
        base_seed: int = 0,
        epoch: int = 0,
    ) -> None:
        gate.request_split(split)
        if variant not in VARIANT_BANDS:
            raise ValueError(f"unknown variant: {variant!r}")
        self.sources = sources
        self.grid = grid
        self.variant = variant
        self.bands = VARIANT_BANDS[variant]
        self.split = split
        self.patch = patch
        self.train = train
        self.base_seed = int(base_seed)
        self.epoch = int(epoch)
        self.rows = windows_for_split(sources.windows, split)

    def set_epoch(self, epoch: int) -> None:
        self.epoch = int(epoch)

    def __len__(self) -> int:
        return len(self.rows)

    def _kind_for(self, index: int) -> int:
        if not self.train:
            return 0
        rng = np.random.default_rng(
            (self.base_seed * 1_000_003 + self.epoch * 91_765 + index)
            % (2**32))
        return int(rng.integers(0, len(self.KINDS)))

    def __getitem__(self, index: int) -> dict[str, Any]:
        row = self.rows.iloc[index]
        r0, c0 = int(row["row_off"]), int(row["col_off"])
        p = self.patch
        win = (slice(r0, r0 + p), slice(c0, c0 + p))
        x = self.grid.norm[self.bands][:, r0:r0 + p, c0:c0 + p].copy()
        valid_inputs = np.all(
            self.grid.valid[self.bands][:, r0:r0 + p, c0:c0 + p], axis=0)
        masks = {
            "silver": self.sources.silver[win],
            "weak": self.sources.weak[win],
            "ignore": self.sources.ignore[win],
            "weak_only": self.sources.weak_only[win],
            "valid_inputs": valid_inputs,
        }
        kind = self._kind_for(index)
        x, masks = geometric_transform(x, masks, kind)
        views = view_masks(
            masks["valid_inputs"], masks["silver"], masks["weak"],
            masks["ignore"], masks["weak_only"])
        return {
            "x": torch.from_numpy(x.astype(np.float32)),
            "y": torch.from_numpy(
                masks["silver"].astype(np.float32)),
            "core_valid": torch.from_numpy(
                views["arbitrated_core"].astype(bool)),
            "strict_valid": torch.from_numpy(
                views["silver_strict"].astype(bool)),
            "weak_only_mask": torch.from_numpy(
                views["weak_only"].astype(bool)),
            "valid_inputs": torch.from_numpy(
                masks["valid_inputs"].astype(bool)),
            "tile_id": row["tile_id"],
            "row_off": r0,
            "col_off": c0,
            "aug_kind": kind,
        }


def grid_view_masks(
    sources: Pilot0Sources, grid: PreparedGrid, variant: str,
) -> dict[str, np.ndarray[Any, Any]]:
    """Whole-grid label views; intersect with mosaic coverage at eval."""
    valid_inputs = np.all(grid.valid[VARIANT_BANDS[variant]], axis=0)
    return view_masks(
        valid_inputs, sources.silver, sources.weak, sources.ignore,
        sources.weak_only)
