"""Macro spatial blocks for contiguous, leakage-free splits.

Model windows are small; split *units* are much larger contiguous
stripes assigned to exactly one split. A guard zone of ``patch/2`` on
both sides of every split boundary is excluded from window placement,
which geometrically prevents any model input window from sharing
source pixels across splits (a window fully inside one side and
``patch/2`` away from the line can never reach across it).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

SPLIT_TARGETS = {"train": 0.60, "val": 0.20, "test": 0.20}
SPLIT_ORDER = ("train", "val", "test")


@dataclass(frozen=True)
class SplitRegion:
    """One contiguous stripe owned by a split (column ranges)."""

    name: str
    owner_start: int  # inclusive, ownership of pixels
    owner_end: int  # exclusive
    usable_start: int  # inclusive, window-placement interior
    usable_end: int  # exclusive

    def contains_window_columns(self, col_off: int, width: int) -> bool:
        return col_off >= self.usable_start and col_off + width <= self.usable_end


def make_regions(
    width: int, b1: int, b2: int, guard: int
) -> dict[str, SplitRegion]:
    """Build train [0,b1), val [b1,b2), test [b2,width) with guards."""
    if not guard <= b1 < b2 <= width - guard:
        raise ValueError("boundaries do not leave guarded regions")
    return {
        "train": SplitRegion("train", 0, b1, 0, b1 - guard),
        "val": SplitRegion("val", b1, b2, b1 + guard, b2 - guard),
        "test": SplitRegion("test", b2, width, b2 + guard, width),
    }


def component_crossings(
    col_min: np.ndarray[Any, Any], col_max: np.ndarray[Any, Any],
    boundary: int,
) -> np.ndarray[Any, Any]:
    """Boolean array: component spans (strictly) both sides of line."""
    return (col_min < boundary) & (col_max >= boundary)


def choose_stripe_boundaries(
    width: int,
    col_silver: np.ndarray[Any, Any],
    col_valid: np.ndarray[Any, Any],
    silver_min_col: np.ndarray[Any, Any],
    silver_max_col: np.ndarray[Any, Any],
    weak_min_col: np.ndarray[Any, Any],
    weak_max_col: np.ndarray[Any, Any],
    patch: int,
    guard: int,
    region_window_stats: Any,
    min_column_tracks: int = 2,
    min_eval_windows: int = 5,
) -> tuple[int, int, dict[str, object]]:
    """Deterministic exhaustive search over stripe boundaries.

    ``region_window_stats(lo, hi, blocked_silver_ids, blocked_weak_ids)``
    returns ``(tracks, viable_windows, silver_eval_windows)`` for a usable
    column range; blocked ids are components cut by the candidate
    boundaries (quarantined). It is deterministic and based on
    geometry/coverage only, never on model results.

    Feasibility: at least ``min_column_tracks`` window tracks, SILVER in
    every region and >= ``min_eval_windows`` SILVER-eval windows in each
    evaluation region. Objective is lexicographic, never random:

    1. max deviation of SILVER area shares from 60/20/20,
    2. max deviation of viable-window-count shares from 60/20/20,
    3. number of split SILVER components cut,
    4. number of material WEAK-only components cut,
    5. max deviation of valid-area shares from 60/20/20,
    6. earliest ``b1`` then earliest ``b2``.
    """
    best: tuple[tuple[Any, ...], int, int] | None = None
    diag: dict[str, object] = {}
    cs_total = col_silver.sum()
    vd_total = col_valid.sum()
    for b1 in range(patch, width - 2 * patch - 2 * guard + 1):
        for b2 in range(b1 + 2 * guard + patch,
                        width - guard - patch + 1):
            interiors = [(0, b1 - guard),
                         (b1 + guard, b2 - guard),
                         (b2 + guard, width)]
            sv = np.array([col_silver[a:b].sum() for a, b in interiors],
                          dtype=float)
            vv = np.array([col_valid[a:b].sum() for a, b in interiors],
                          dtype=float)
            if sv.min() <= 0:
                continue
            q_s = (set(np.where(component_crossings(
                        silver_min_col, silver_max_col, b1))[0] + 1)
                   | set(np.where(component_crossings(
                        silver_min_col, silver_max_col, b2))[0] + 1))
            q_w = (set(np.where(component_crossings(
                        weak_min_col, weak_max_col, b1))[0] + 1)
                   | set(np.where(component_crossings(
                        weak_min_col, weak_max_col, b2))[0] + 1))
            stats = [region_window_stats(a, b, q_s, q_w)
                     for a, b in interiors]
            tracks = np.array([s[0] for s in stats], dtype=float)
            viable = np.array([s[1] for s in stats], dtype=float)
            silver_w = np.array([s[2] for s in stats], dtype=float)
            if tracks.min() < min_column_tracks:
                continue
            if silver_w[1] < min_eval_windows or silver_w[2] < min_eval_windows:
                continue
            # shares normalized over usable interiors (guard-band pixels
            # are owned by no split; their fraction is reported separately)
            sp = sv / sv.sum()
            vp = vv / vv.sum()
            wp = viable / viable.sum()
            cross_s = int(
                component_crossings(silver_min_col, silver_max_col, b1).sum()
                + component_crossings(silver_min_col, silver_max_col, b2).sum()
            )
            cross_w = int(
                component_crossings(weak_min_col, weak_max_col, b1).sum()
                + component_crossings(weak_min_col, weak_max_col, b2).sum()
            )
            target = np.array([SPLIT_TARGETS[n] for n in SPLIT_ORDER])
            key = (
                round(float(np.abs(sp - target).max()), 6),
                round(float(np.abs(wp - target).max()), 6),
                cross_s,
                cross_w,
                round(float(np.abs(vp - target).max()), 6),
                b1,
                b2,
            )
            if best is None or key < best[0]:
                best = (key, b1, b2)
                diag = {
                    "silver_area_shares": [float(x) for x in sp],
                    "viable_window_shares": [float(x) for x in wp],
                    "valid_area_shares": [float(x) for x in vp],
                    "silver_in_guard_fraction": float(1 - sv.sum()
                                                     / cs_total),
                    "valid_in_guard_fraction": float(1 - vv.sum()
                                                    / vd_total),
                    "window_tracks": [int(x) for x in tracks],
                    "viable_windows": [int(x) for x in viable],
                    "silver_eval_windows": [int(x) for x in silver_w],
                    "silver_components_cut": cross_s,
                    "weak_components_cut": cross_w,
                }
    if best is None:
        raise RuntimeError("no feasible stripe boundary found")
    diag["search_objective"] = list(best[0])
    return best[1], best[2], diag
