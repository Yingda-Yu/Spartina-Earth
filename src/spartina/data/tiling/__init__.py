"""Deterministic tiling for Spartina Earth analysis grids.

Tile identity is a pure function of the analysis grid, pixel offsets and
patch size; it never depends on generation order.
"""

from __future__ import annotations

from spartina.data.tiling.ids import (
    TILE_ID_REGEX,
    parse_tile_id,
    tile_id,
)
from spartina.data.tiling.windows import (
    WindowSpec,
    packed_region_starts,
    window_bounds,
    window_transform,
)

__all__ = [
    "TILE_ID_REGEX",
    "WindowSpec",
    "packed_region_starts",
    "parse_tile_id",
    "tile_id",
    "window_bounds",
    "window_transform",
]
