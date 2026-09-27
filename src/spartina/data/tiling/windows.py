"""Window geometry on a fixed raster grid.

A *model window* is a square pixel window addressed by its top-left
offset. Window placement is deterministic: global half-patch lattice
plus, inside a split region, boundary-aligned edge windows so that a
narrow region still gets full windows without straddling a split line.
"""

from __future__ import annotations

from dataclasses import dataclass

from rasterio.transform import Affine


@dataclass(frozen=True)
class WindowSpec:
    """A square pixel window on the analysis grid."""

    row_off: int
    col_off: int
    height: int
    width: int

    def __post_init__(self) -> None:
        if self.row_off < 0 or self.col_off < 0:
            raise ValueError("offsets must be non-negative")
        if self.height <= 0 or self.width <= 0:
            raise ValueError("window extent must be positive")

    @property
    def row_end(self) -> int:
        return self.row_off + self.height

    @property
    def col_end(self) -> int:
        return self.col_off + self.width

    def shares_pixels(self, other: WindowSpec) -> bool:
        """True iff the two windows share at least one source pixel."""
        return not (
            self.col_end <= other.col_off
            or other.col_end <= self.col_off
            or self.row_end <= other.row_off
            or other.row_end <= self.row_off
        )

    def pixel_gap(self, other: WindowSpec) -> int:
        """Minimum axis-aligned pixel gap (0 if they touch or overlap)."""
        gap_x = max(0, max(self.col_off, other.col_off)
                    - min(self.col_end, other.col_end))
        gap_y = max(0, max(self.row_off, other.row_off)
                    - min(self.row_end, other.row_end))
        return max(gap_x, gap_y)


def packed_region_starts(
    extent: int,
    patch: int,
    stride: int,
    region_lo: int,
    region_hi: int,
) -> list[int]:
    """Deterministic window start offsets fully inside one region.

    Candidates are the global ``stride`` lattice clipped to the region,
    the region's left edge and the right-edge aligned position (plus one
    stride inward). Sorted and deduplicated. Every returned window lies
    fully inside ``[region_lo, region_hi)``; if the region is narrower
    than ``patch`` the list is empty.
    """
    if extent < patch:
        raise ValueError("region extent smaller than patch")
    if region_hi - region_lo < patch:
        return []
    starts = {
        s
        for s in range(0, extent - patch + 1, stride)
        if s >= region_lo and s + patch <= region_hi
    }
    starts.add(region_lo)
    last = region_hi - patch
    starts.add(last)
    if last - stride >= region_lo:
        starts.add(last - stride)
    return sorted(starts)


def window_transform(grid_transform: Affine, win: WindowSpec) -> Affine:
    """Rasterio Affine of a window relative to the grid origin."""
    return Affine(
        grid_transform.a,
        grid_transform.b,
        grid_transform.c + win.col_off * grid_transform.a,
        grid_transform.d,
        grid_transform.e,
        grid_transform.f + win.row_off * grid_transform.e,
    )


def window_bounds(
    grid_transform: Affine, win: WindowSpec
) -> tuple[float, float, float, float]:
    """Projected bounds ``(west, south, east, north)`` of a window."""
    west = grid_transform.c + win.col_off * grid_transform.a
    north = grid_transform.f + win.row_off * grid_transform.e
    east = west + win.width * grid_transform.a
    south = north + win.height * grid_transform.e
    return west, south, east, north
