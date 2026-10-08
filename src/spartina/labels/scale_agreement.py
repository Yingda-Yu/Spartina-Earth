"""Pure helpers for the 2020 multi-resolution external-label scale audit.

Issue #18. No I/O lives here so every aggregation step is unit testable.
All quantities describe *agreement / disagreement between external
reference products*; no function in this module estimates accuracy.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

import numpy as np
from scipy import ndimage

# Pre-registered fractional-cover bins for coarse pixels.
COVER_BIN_EDGES: tuple[float, ...] = (0.0, 0.25, 0.5, 0.75, 1.0000001)
COVER_BIN_LABELS: tuple[str, ...] = (
    "0", "(0,0.25]", "(0.25,0.5]", "(0.5,0.75]", "(0.75,1]",
)

# Signed boundary-distance bands (metres), shared by both supports.
DISTANCE_BIN_EDGES: tuple[float, ...] = (0.0, 30.0, 60.0, 120.0, 300.0)
DISTANCE_BIN_LABELS: tuple[str, ...] = (
    "0-30m", "30-60m", "60-120m", "120-300m", ">=300m",
)

# Fine-patch area bins (m^2); 900 m^2 = one 30 m pixel.
PATCH_BIN_EDGES: tuple[float, ...] = (
    0.0, 100.0, 900.0, 2_500.0, 10_000.0, 100_000.0, float("inf"),
)
PATCH_BIN_LABELS: tuple[str, ...] = (
    "<100m2(sliver)", "100-900m2", "900-2500m2", "2500-1e4m2",
    "1e4-1e5m2", ">=1e5m2",
)

def signed_distance(mask: np.ndarray[Any, Any], pixel_m: float) -> np.ndarray[Any, Any]:
    """Signed distance (m) to the mask boundary.

    Positive inside the mask (one raster cell immediately inside the
    edge reads ``+pixel_m``) and negative outside.
    ``ndimage.distance_transform_edt`` returns, for every NONZERO
    element, its distance to the nearest zero element (zero elements
    themselves receive 0); therefore the inside branch is ``edt(mask)``
    and the outside branch is ``-edt(~mask)``. Swapping them yields an
    all-zero field, which silently turns a distance band into the whole
    array.
    """
    return np.where(
        mask,
        ndimage.distance_transform_edt(mask),
        -ndimage.distance_transform_edt(~mask),
    ) * pixel_m


PROVINCE_CODES: dict[str, str] = {
    "LN": "Liaoning", "HB": "Hebei", "TJ": "Tianjin", "SD": "Shandong",
    "JS": "Jiangsu", "SH": "Shanghai", "ZJ": "Zhejiang", "FJ": "Fujian",
    "GD": "Guangdong", "GX": "Guangxi",
}
PROVINCE_ORDER: tuple[str, ...] = (
    "Liaoning", "Hebei", "Tianjin", "Shandong", "Jiangsu", "Shanghai",
    "Zhejiang", "Fujian", "Guangdong", "Guangxi", "UNATTRIBUTED",
)

# Issue #18 R1, Part B: W10 domain-membership sensitivity variants.
# Owner-signed KEEP statuses define the primary KEEP_ONLY universe;
# PROVISIONAL cells (Issue #17 sign-off pending) enter only the
# KEEP_PLUS_PROVISIONAL sensitivity variant.
KEEP_DOMAIN_STATUSES: tuple[str, ...] = (
    "KEEP_MAINLAND_COASTAL", "KEEP_ISLAND_COASTAL",
)
PROVISIONAL_DOMAIN_STATUS: str = "PROVISIONAL_UNRESOLVED"


def domain_variant_mask(
    membership_statuses: Any, include_provisional: bool
) -> np.ndarray[Any, Any]:
    """Boolean membership mask for the two pre-registered domain variants.

    ``KEEP_ONLY`` (``include_provisional=False``) selects exactly the two
    owner-defined KEEP statuses; ``KEEP_PLUS_PROVISIONAL`` (``True``)
    additionally selects ``PROVISIONAL_UNRESOLVED`` cells. Any other
    status (EXCLUDE_DOMAIN_ARTIFACT, missing) is always excluded.
    """
    statuses = np.asarray(membership_statuses)
    keep = np.isin(statuses, list(KEEP_DOMAIN_STATUSES))
    if include_provisional:
        keep = keep | (statuses == PROVISIONAL_DOMAIN_STATUS)
    return keep


def assign_bin(value: float, edges: tuple[float, ...],
               labels: tuple[str, ...]) -> str:
    """Assign ``value`` to left-closed/right-open bins; last edge inclusive."""
    for idx in range(len(edges) - 1):
        upper = edges[idx + 1]
        if idx == len(edges) - 2:
            if edges[idx] <= value <= upper:
                return labels[idx]
        elif edges[idx] <= value < upper:
            return labels[idx]
    return labels[-1]


def jaccard(intersection: float, area_a: float, area_b: float) -> float:
    """Jaccard index from areas on one comparison support."""
    union = area_a + area_b - intersection
    return float(intersection / union) if union > 0 else float("nan")


def dice(intersection: float, area_a: float, area_b: float) -> float:
    """Sorensen-Dice coefficient (F1 on areas) from areas on one support."""
    denom = area_a + area_b
    return float(2.0 * intersection / denom) if denom > 0 else float("nan")


def area_bias(area_a: float, area_b: float) -> float:
    """Signed relative area bias (A - B) / B; B is the named reference."""
    return float((area_a - area_b) / area_b) if area_b > 0 else float("nan")


def omission_commission(
    area_a: float, area_b: float, intersection: float
) -> tuple[float, float]:
    """Return (omission, commission) areas of A relative to named ref B."""
    return max(0.0, area_b - intersection), max(0.0, area_a - intersection)


class Tally:
    """Keyed area/count accumulator (dict-backed; order independent)."""

    def __init__(self) -> None:
        self._counts: Counter[tuple[Any, ...]] = Counter()
        self._areas: dict[tuple[Any, ...], float] = {}

    def add(self, key: tuple[Any, ...], count: int, area: float) -> None:
        self._counts[key] += int(count)
        self._areas[key] = self._areas.get(key, 0.0) + float(area)

    def add_many(
        self,
        key_parts: list[tuple[Any, ...]],
        counts: np.ndarray[Any, Any],
        areas: np.ndarray[Any, Any],
    ) -> None:
        for parts, count, area in zip(key_parts, counts, areas, strict=True):
            if count:
                self._counts[parts] += int(count)
                self._areas[parts] = self._areas.get(parts, 0.0) + float(area)

    def rows(self, key_names: tuple[str, ...]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for key, count in self._counts.most_common():
            row = dict(zip(key_names, key, strict=True))
            row["pixel_count"] = count
            row["area_km2"] = round(self._areas[key] / 1e6, 6)
            out.append(row)
        return out

    def __len__(self) -> int:
        return len(self._counts)


def block_bootstrap_ci(
    values: np.ndarray[Any, Any],
    weights: np.ndarray[Any, Any] | None = None,
    n_boot: int = 500,
    seed: int = 20201018,
    alpha: float = 0.05,
) -> tuple[float, float]:
    """Percentile CI by spatially blocking: rows are blocks (e.g. W10 cells).

    Never bootstrap individual pixels; callers pass one row per spatial
    block. Weighted blocks keep their weight in every resample.
    """
    rng = np.random.default_rng(seed)
    n = values.shape[0]
    if n == 0:
        return float("nan"), float("nan")
    means = np.empty(n_boot, dtype=np.float64)
    if weights is None:
        for i in range(n_boot):
            idx = rng.integers(0, n, n)
            means[i] = float(np.mean(values[idx]))
    else:
        w = weights / weights.sum()
        for i in range(n_boot):
            idx = rng.integers(0, n, n)
            means[i] = float(
                np.sum(values[idx] * w[idx]) / np.sum(w[idx])
            )
    lo = float(np.quantile(means, alpha / 2.0))
    hi = float(np.quantile(means, 1.0 - alpha / 2.0))
    return lo, hi


def fine_coverage_bins(
    cover: np.ndarray[Any, Any], bin_edges: tuple[float, ...] = COVER_BIN_EDGES
) -> np.ndarray[Any, Any]:
    """Vectorised fractional-cover bin index for an N-D array.

    Bin 0 is exact zero; positive cover is right-edge inclusive
    against ``bin_edges[1:-1]`` (matching the pre-registered
    ``(0,0.25]`` notation): 0 | (0,0.25] | (0.25,0.5] | (0.5,0.75]
    | (0.75,1].
    """
    idx = np.zeros(cover.shape, dtype=np.int8)
    pos = cover > bin_edges[0]
    idx[pos] = (
        np.digitize(cover[pos], bin_edges[1:-1], right=True) + 1
    )
    return idx


def mixed_pixel_split(
    g_positive: np.ndarray[Any, Any],
    fine_cover: np.ndarray[Any, Any],
    pure_lo: float = 0.1,
    pure_hi: float = 0.9,
) -> dict[str, int]:
    """Counts for H6: binary coarse call vs mixed fine occupancy.

    Categories use pre-registered fine-occupancy thresholds:
    near-empty <= ``pure_lo``, mixed strictly inside (lo, hi),
    near-full >= ``pure_hi``.
    """
    g = g_positive.astype(bool)
    near_empty = fine_cover <= pure_lo
    near_full = fine_cover >= pure_hi
    mixed = ~near_empty & ~near_full
    return {
        "g0_fine_empty": int((~g & near_empty).sum()),
        "g0_fine_mixed": int((~g & mixed).sum()),
        "g0_fine_full": int((~g & near_full).sum()),
        "g1_fine_empty": int((g & near_empty).sum()),
        "g1_fine_mixed": int((g & mixed).sum()),
        "g1_fine_full": int((g & near_full).sum()),
    }
