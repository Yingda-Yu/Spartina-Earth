"""Geometry assembly for national grids (thin shapely/pyproj layer).

The pure lattice arithmetic lives in :mod:`grid`; this module only turns
indices into polygons and provides one vectorised polygon/grid index
helper used by the domain build scripts.
"""

from __future__ import annotations

from typing import Final

from pyproj import CRS, Transformer
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry
from shapely.prepared import prep

from .grid import CHINA_ALBERS_PROJ4, GridKind, GridSpec, utm_epsg

CHINA_ALBERS_CRS: Final[CRS] = CRS.from_proj4(CHINA_ALBERS_PROJ4)
WGS84_CRS: Final[CRS] = CRS.from_epsg(4326)


def crs_for(kind: GridKind, zone: int | None = None) -> CRS:
    """The projected CRS backing a lattice strategy."""
    if kind is GridKind.CHINA_ALBERS:
        return CHINA_ALBERS_CRS
    if kind is GridKind.UTM_ZONE_AWARE:
        if zone is None:
            raise ValueError("UTM lattice needs a zone")
        return CRS.from_epsg(utm_epsg(zone))
    raise ValueError(f"unknown grid kind: {kind!r}")


def cell_polygon_wgs84(
    spec: GridSpec, row: int, col: int, zone: int | None = None
) -> BaseGeometry:
    """Construct a cell square and transform it to WGS84."""
    xmin, ymin, xmax, ymax = spec.cell_bounds_projected(row, col, zone)
    source = crs_for(spec.kind, zone)
    transformer = Transformer.from_crs(source, WGS84_CRS, always_xy=True)
    corners_wgs = [
        transformer.transform(x, y)
        for x, y in (
            (xmin, ymin),
            (xmax, ymin),
            (xmax, ymax),
            (xmin, ymax),
        )
    ]
    xs = [p[0] for p in corners_wgs]
    ys = [p[1] for p in corners_wgs]
    return box(min(xs), min(ys), max(xs), max(ys))


def lattice_cell_ids_covering(
    spec: GridSpec,
    polygon_projected: BaseGeometry,
    zone: int | None,
) -> list[tuple[int, int]]:
    """Return ``(row, col)`` lattice cells intersecting a projected polygon.

    Candidates come from the polygon bounds (deterministic range); exact
    intersection is tested geometrically.  Prepared polygons keep this
    tractable for national lattices.
    """
    xmin, ymin, xmax, ymax = polygon_projected.bounds
    row_min, row_max, col_min, col_max = spec.indices_for_bounds(
        xmin, ymin, xmax, ymax
    )
    prepared = prep(polygon_projected)
    keep: list[tuple[int, int]] = []
    size = spec.cell_size_m
    for row in range(row_min, row_max + 1):
        for col in range(col_min, col_max + 1):
            square = box(col * size, row * size, (col + 1) * size, (row + 1) * size)
            if prepared.intersects(square):
                keep.append((row, col))
    return keep
