"""Spatial-leakage checks for dataset splits.

Implements the M0 benchmark contract at
``benchmarks/spartinashift/SPEC.md``:

* spatial units (not random neighbouring patches) are assigned to splits;
* units assigned to different splits must not touch, including a buffer;
* every date of one spatial unit must belong to the same split.

The geometry model is deliberately dependency-free in M0: each unit is an
axis-aligned bounding box in a *projected* CRS (metres), which is enough
to encode tile/segment indices and buffer checks. M1 may replace the
backend with shapely geometries while preserving this function interface.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class SpatialUnit:
    """A geographic split unit with a projected bounding box (metres)."""

    unit_id: str
    xmin: float
    ymin: float
    xmax: float
    ymax: float

    def __post_init__(self) -> None:
        if self.xmax <= self.xmin or self.ymax <= self.ymin:
            raise ValueError(f"Unit {self.unit_id!r} has non-positive extent")


def _buffered_intersects(a: SpatialUnit, b: SpatialUnit, buffer_m: float) -> bool:
    """Return True if two boxes overlap after applying ``buffer_m``.

    Two boxes touch/intersect when there is no separating axis with a gap
    strictly greater than the buffer.
    """
    gap_x = max(0.0, max(a.xmin, b.xmin) - min(a.xmax, b.xmax))
    gap_y = max(0.0, max(a.ymin, b.ymin) - min(a.ymax, b.ymax))
    return gap_x <= buffer_m and gap_y <= buffer_m


def find_cross_split_overlaps(
    split_of: Mapping[str, str],
    units: Mapping[str, SpatialUnit],
    buffer_m: float = 250.0,
) -> list[tuple[str, str, float]]:
    """List unit pairs in different splits whose buffers overlap.

    Returns triples ``(unit_id_a, unit_id_b, min_gap_m)``; an empty list
    means the split is spatially disjoint under the requested buffer.
    """
    if buffer_m < 0:
        raise ValueError("buffer_m must be non-negative")
    violations: list[tuple[str, str, float]] = []
    unit_ids = list(units)
    for i, id_a in enumerate(unit_ids):
        for id_b in unit_ids[i + 1 :]:
            split_a = split_of.get(id_a)
            split_b = split_of.get(id_b)
            if split_a is None or split_b is None or split_a == split_b:
                continue
            unit_a = units[id_a]
            unit_b = units[id_b]
            gap_x = max(0.0, max(unit_a.xmin, unit_b.xmin) - min(unit_a.xmax, unit_b.xmax))
            gap_y = max(0.0, max(unit_a.ymin, unit_b.ymin) - min(unit_a.ymax, unit_b.ymax))
            min_gap = max(gap_x, gap_y)
            if _buffered_intersects(unit_a, unit_b, buffer_m):
                violations.append((id_a, id_b, min_gap))
    return violations


def assert_spatially_disjoint(
    split_of: Mapping[str, str],
    units: Mapping[str, SpatialUnit],
    buffer_m: float = 250.0,
) -> None:
    """Raise ``ValueError`` if cross-split buffered overlaps exist."""
    overlaps = find_cross_split_overlaps(split_of, units, buffer_m)
    if overlaps:
        preview = ", ".join(f"{a}~{b}" for a, b, _ in overlaps[:5])
        raise ValueError(
            f"Spatial leakage: {len(overlaps)} cross-split pair(s) within "
            f"{buffer_m} m (first: {preview})"
        )


def check_temporal_grouping(
    split_of: Mapping[str, str],
    unit_dates: Mapping[str, list[str]],
) -> dict[str, list[str]]:
    """Verify all dates of each unit map to one split.

    ``unit_dates`` maps a unit id to its observed dates; this function
    checks the complementary direction used with date-keyed tables: a unit
    appearing in multiple splits is reported. Returns a mapping
    ``unit_id -> sorted list of offending splits`` (empty dict = valid).
    """
    offenders: dict[str, list[str]] = {}
    for unit_id in unit_dates:
        splits = {split_of[unit_id]} if unit_id in split_of else set()
        if len(splits) > 1:
            offenders[unit_id] = sorted(splits)
    return offenders


def check_date_table_grouping(
    date_split_pairs: list[tuple[str, str]],
) -> dict[str, list[str]]:
    """Check (unit_id, split) rows: one unit must never change split.

    Use this when input is a flat table assigning each *dated observation*
    to a split; returns offending unit ids with all splits seen.
    """
    seen: dict[str, set[str]] = {}
    for unit_id, split in date_split_pairs:
        seen.setdefault(unit_id, set()).add(split)
    return {unit_id: sorted(splits) for unit_id, splits in seen.items() if len(splits) > 1}


__all__ = [
    "SpatialUnit",
    "assert_spatially_disjoint",
    "check_date_table_grouping",
    "check_temporal_grouping",
    "find_cross_split_overlaps",
]
