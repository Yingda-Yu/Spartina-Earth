"""Fixed analysis grids for the GEE EO Data Factory.

Every export is reprojected/gridded onto an explicit :class:`GridSpec`
(crs, affine transform, width, height, pixel size, bounds). Two science
streams are kept strictly separate:

* **Landsat era — 30 m science stream.** 30 m native pixels land on a
  30 m grid.
* **Sentinel era — 10 m science stream.** 10 m native pixels land on a
  10 m grid.

The factory refuses to put a coarser native product onto a finer grid
(:func:`assert_no_forced_upsampling`); upsampling 30 m Landsat and
presenting the result as a true 10 m historical product is prohibited
(AGENTS.md integrity rule 7).

Standard library only; no ``ee`` import here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

#: (west, south, east, north)

Bounds = tuple[float, float, float, float]

LANDSAT_PIXEL_M: Final[float] = 30.0
SENTINEL_PIXEL_M: Final[float] = 10.0
_TOL: Final[float] = 1e-9


class GridError(ValueError):
    """Invalid grid specification or forbidden resampling request."""


@dataclass(frozen=True)
class GridSpec:
    """A fixed pixel grid in one projected CRS.

    ``transform`` uses the GDAL/OGR affine convention
    ``x = a*col + b*row + c``, ``y = d*col + e*row + f``. North-up grids
    have ``b = d = 0``, ``a > 0``, ``e < 0``.
    """

    crs: str
    transform: tuple[float, float, float, float, float, float]
    width: int
    height: int

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise GridError("width/height must be positive")
        a, b, _c, d, e, _f = self.transform
        if abs(b) > _TOL or abs(d) > _TOL:
            raise GridError("only north-up axis-aligned grids are supported")
        if a <= 0 or e >= 0:
            raise GridError("transform must be north-up (a>0, e<0)")

    @property
    def pixel_x_m(self) -> float:
        return self.transform[0]

    @property
    def pixel_y_m(self) -> float:
        return -self.transform[4]

    @property
    def west(self) -> float:
        return self.transform[2]

    @property
    def north(self) -> float:
        return self.transform[5]

    @property
    def east(self) -> float:
        return self.west + self.pixel_x_m * self.width

    @property
    def south(self) -> float:
        return self.north - self.pixel_y_m * self.height

    @property
    def bounds(self) -> Bounds:
        return (self.west, self.south, self.east, self.north)

    @property
    def crs_epsg(self) -> int:
        return int(self.crs.split(":")[1])

    def to_dict(self) -> dict[str, object]:
        """JSON-serializable grid description."""
        return {
            "crs": self.crs,
            "transform": list(self.transform),
            "width": self.width,
            "height": self.height,
            "pixel_size_m": [self.pixel_x_m, self.pixel_y_m],
            "bounds": list(self.bounds),
        }


def from_origin(
    west: float, north: float, pixel_m: float, width: int, height: int,
    crs_epsg: int,
) -> GridSpec:
    """Build a north-up grid from an explicit upper-left origin."""
    if pixel_m <= 0:
        raise GridError("pixel_m must be positive")
    return GridSpec(
        crs=f"EPSG:{crs_epsg}",
        transform=(pixel_m, 0.0, west, 0.0, -pixel_m, north),
        width=int(width), height=int(height))


def covering_grid(
    bounds: Bounds, crs_epsg: int, pixel_m: float,
) -> GridSpec:
    """Build the smallest pixel-aligned grid that fully covers ``bounds``.

    The grid origin is placed at a multiple of ``pixel_m`` (in projected
    coordinates) so independently built grids on nearby ROIs share the
    same lattice and nest without sub-pixel shifts.
    """
    west, south, east, north = bounds
    if not (east > west and north > south):
        raise GridError(f"invalid bounds {bounds}")
    if pixel_m <= 0:
        raise GridError("pixel_m must be positive")
    origin_west = math.floor(west / pixel_m) * pixel_m
    origin_north = math.ceil(north / pixel_m) * pixel_m
    width = int(math.ceil((east - origin_west) / pixel_m - _TOL))
    height = int(math.ceil((origin_north - south) / pixel_m - _TOL))
    return from_origin(origin_west, origin_north, pixel_m, width, height,
                       crs_epsg)


def landsat_30m_grid(bounds: Bounds, crs_epsg: int) -> GridSpec:
    """30 m science stream grid for Landsat-era products."""
    return covering_grid(bounds, crs_epsg, LANDSAT_PIXEL_M)


def sentinel_10m_grid(bounds: Bounds, crs_epsg: int) -> GridSpec:
    """10 m science stream grid for Sentinel-era products."""
    return covering_grid(bounds, crs_epsg, SENTINEL_PIXEL_M)


def assert_no_forced_upsampling(
    source_native_m: float, grid_pixel_m: float,
) -> None:
    """Reject placing a coarse native product on a finer grid.

    A coarser *grid* (downsampling) is allowed; an equal-size grid is the
    normal case. A finer grid than the native source resolution is
    forbidden because it would fabricate pixels.
    """
    if grid_pixel_m + _TOL < source_native_m:
        raise GridError(
            f"refusing to place {source_native_m:g} m native data on a "
            f"{grid_pixel_m:g} m grid: forced upsampling cannot create "
            "real resolution (30 m Landsat must not be sold as 10 m)")


def grid_for_stream(
    stream: str, bounds: Bounds, crs_epsg: int,
) -> GridSpec:
    """Return the fixed grid for a named science stream."""
    if stream == "landsat_30m":
        return landsat_30m_grid(bounds, crs_epsg)
    if stream == "sentinel_10m":
        return sentinel_10m_grid(bounds, crs_epsg)
    raise GridError(f"unknown science stream {stream!r}; expected "
                    "'landsat_30m' or 'sentinel_10m'")


__all__ = [
    "Bounds",
    "GridError",
    "GridSpec",
    "LANDSAT_PIXEL_M",
    "SENTINEL_PIXEL_M",
    "assert_no_forced_upsampling",
    "covering_grid",
    "from_origin",
    "grid_for_stream",
    "landsat_30m_grid",
    "sentinel_10m_grid",
]
