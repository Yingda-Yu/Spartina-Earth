"""Stable tile IDs derived from grid geometry.

ID contract (Issue #4): the ID is uniquely determined by the analysis
grid id, the pixel *offset* of the window on that grid and the patch
side length. Re-running with the same grid + config must produce the
same ID; names like ``tile_00001`` that depend on generation order are
forbidden.

Format::

    HB2015_R0000_C0384_P128

``R`` is the row offset (top), ``C`` the column offset (left), ``P``
the square patch side in pixels. Fields are zero padded to keep lexical
and numeric ordering aligned over the supported grid (< 10 000 px).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

TILE_ID_REGEX = re.compile(
    r"^(?P<grid>[A-Za-z0-9]+)_R(?P<row>\d{4})_C(?P<col>\d{4})_P(?P<patch>\d{3})$"
)


@dataclass(frozen=True)
class TileAddress:
    """Triple that uniquely identifies a window on an analysis grid."""

    grid_id: str
    row_off: int
    col_off: int
    patch: int

    def __post_init__(self) -> None:
        if not self.grid_id or not self.grid_id.replace("_", "").isalnum():
            raise ValueError(f"invalid grid_id: {self.grid_id!r}")
        if self.row_off < 0 or self.col_off < 0:
            raise ValueError("tile offsets must be non-negative")
        if not 1 <= self.patch <= 999:
            raise ValueError("patch side must be in [1, 999] px")


def tile_id(grid_id: str, row_off: int, col_off: int, patch: int) -> str:
    """Return the deterministic ID for a window on an analysis grid."""
    addr = TileAddress(grid_id, row_off, col_off, patch)
    return (
        f"{addr.grid_id}_R{addr.row_off:04d}_C{addr.col_off:04d}"
        f"_P{addr.patch:03d}"
    )


def parse_tile_id(tid: str) -> TileAddress:
    """Parse a tile ID; raises ``ValueError`` on malformed IDs."""
    m = TILE_ID_REGEX.match(tid)
    if m is None:
        raise ValueError(f"malformed tile_id: {tid!r}")
    return TileAddress(
        grid_id=m.group("grid"),
        row_off=int(m.group("row")),
        col_off=int(m.group("col")),
        patch=int(m.group("patch")),
    )
