"""Target-independent coastal-China domain construction (Issue #14).

The domain is built from two passported external sources:

* GSHHS L1 polygons provide the detailed coastline / land-sea mask.
* Natural Earth 1:10m admin-0 polygons provide *ownership*: which land is
  administered by China.  GSHHG itself carries no country attribution.

Coastline-specific corridor (never a generic boundary ring):

* ``seaward = china.buffer(W) - all_land`` (open water only, so foreign
  land borders can never enter the domain);
* ``onshore  = china & seaward.buffer(W)`` (land within W of that water);
* ``corridor = seaward | onshore``.

Small Chinese-administered islands that are missing from the generalized
Natural Earth polygon (the Zhoushan, Miaodao, Changshan and Wanshan
archipelagos carry thousands of such polygons in GSHHS) are recovered by
an explicit, documented rule: area <= ``island_max_area_m2``,
representative point within ``island_near_m`` of the China polygon, and
the point outside every other admin-0 polygon.  All rule parameters are
fixed a priori; nothing is fitted to Spartina labels.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

import geopandas as gpd
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry
from shapely.prepared import prep

from .grid import CELL_SIZE_M, CHINA_COASTAL_UTM_ZONES, GridKind, encode_cell_id

# Fixed a-priori domain rule parameters (Issue #14 sections 24-28).
DEFAULT_BBOX_WGS84: Final[tuple[float, float, float, float]] = (105.0, 15.0, 132.0, 43.0)
ISLAND_MAX_AREA_M2: Final[int] = 100_000_000  # 100 km^2
ISLAND_NEAR_M: Final[int] = 25_000
# A cell enters the domain only if >=1 % of its area intersects the
# corridor.  Removes zero-width projection/border slivers (observed at the
# Tumen triple-border) without dropping genuinely narrow estuarine cells.
MIN_CELL_INTERSECTION_FRACTION: Final[float] = 0.01
# Half-width of the per-zone construction band (degrees).  Every Chinese
# coastal point is covered by exactly one zone band; the overlap with the
# adjacent band is only used to quantify seam double-coverage.
ZONE_BAND_MARGIN_DEG: Final[float] = 0.25

CHINA_ADMIN_NAME: Final[str] = "China"


@dataclass(frozen=True)
class ChinaLand:
    """China-administered land used for corridor construction."""

    land: BaseGeometry
    """Union of clipped mainland and recovered islands."""

    mainland: BaseGeometry
    """GSHHS polygons clipped to the Natural Earth China polygon."""

    added_island_count: int
    added_island_area_m2: float

    @property
    def land_area_m2(self) -> float:
        return float(self.land.area)


@dataclass(frozen=True)
class CellHit:
    """One lattice cell retained for the domain."""

    cell_id: str
    kind: GridKind
    zone: int | None
    row: int
    col: int
    intersection_m2: float


def select_admin_polygon(
    admin0_wgs84: gpd.GeoDataFrame, admin_name: str = CHINA_ADMIN_NAME
) -> BaseGeometry:
    """Return the single WGS84 admin-0 polygon union for ``admin_name``."""
    rows = admin0_wgs84[admin0_wgs84["ADMIN"] == admin_name]
    if len(rows) != 1:
        raise ValueError(
            f"expected exactly one admin-0 row named {admin_name!r}, got {len(rows)}"
        )
    return rows.to_crs(4326).union_all()


def build_china_land(
    gshhs_wgs84: gpd.GeoDataFrame,
    admin0_wgs84: gpd.GeoDataFrame,
    target_crs: str,
    island_max_area_m2: int = ISLAND_MAX_AREA_M2,
    island_near_m: int = ISLAND_NEAR_M,
) -> ChinaLand:
    """Clip detailed land to China ownership and recover small islands.

    Inputs are WGS84 GeoDataFrames; all geometric work happens in
    ``target_crs`` (an equal-area CRS for area reporting).
    """
    china_wgs = select_admin_polygon(admin0_wgs84)
    china = gpd.GeoSeries([china_wgs], crs=4326).to_crs(target_crs).iloc[0]
    other_admin = admin0_wgs84[admin0_wgs84["ADMIN"] != CHINA_ADMIN_NAME]
    other = other_admin.to_crs(target_crs).union_all()

    land = gshhs_wgs84.to_crs(target_crs)
    mainland = gpd.clip(land, gpd.GeoSeries([china], crs=target_crs)).union_all()

    small = land[land.area <= island_max_area_m2]
    rep_points = gpd.GeoSeries(
        small.geometry.map(lambda geom: geom.representative_point()), crs=target_crs
    )
    near_china = rep_points.distance(china) <= island_near_m
    in_china = rep_points.map(lambda point: point.within(china))
    in_other_country = rep_points.map(lambda point: point.within(other))
    islands = small[near_china & ~in_other_country & ~in_china]
    island_union = islands.union_all()

    return ChinaLand(
        land=mainland.union(island_union),
        mainland=mainland,
        added_island_count=int(len(islands)),
        added_island_area_m2=float(islands.area.sum()),
    )


def build_corridor(china_land: BaseGeometry, all_land: BaseGeometry, width_m: int) -> BaseGeometry:
    """Coastline-specific symmetric corridor of half-width ``width_m``.

    The outward half is restricted to open water (not foreign land), and
    the inward half is land reached from that water, so inland
    international borders (e.g. the Tumen, Yalu or Vietnam land borders)
    never enter the domain.
    """
    seaward = china_land.buffer(width_m).difference(all_land)
    onshore = china_land.intersection(seaward.buffer(width_m))
    return seaward.union(onshore)


def _floor_div(value: float, size: int) -> int:
    return math.floor(value / size)


def _ceil_div(value: float, size: int) -> int:
    return math.ceil(value / size)


def scan_lattice_cells(
    corridor: BaseGeometry,
    kind: GridKind,
    zone: int | None = None,
    cell_size_m: int = CELL_SIZE_M,
    min_fraction: float = MIN_CELL_INTERSECTION_FRACTION,
) -> list[CellHit]:
    """Scan one fixed lattice for cells intersecting the corridor.

    Lattices anchor at projected (0, 0), matching :mod:`grid` encoding.
    """
    if kind is GridKind.UTM_ZONE_AWARE and zone is None:
        raise ValueError("UTM lattice scan requires a zone")
    if corridor.is_empty:
        return []
    min_area_m2 = min_fraction * cell_size_m * cell_size_m
    minx, miny, maxx, maxy = corridor.bounds
    r0 = _floor_div(miny, cell_size_m)
    r1 = _ceil_div(maxy, cell_size_m)
    c0 = _floor_div(minx, cell_size_m)
    c1 = _ceil_div(maxx, cell_size_m)
    prepared = prep(corridor)
    hits: list[CellHit] = []
    for row in range(r0, r1):
        y0 = row * cell_size_m
        y1 = y0 + cell_size_m
        for col in range(c0, c1):
            x0 = col * cell_size_m
            x1 = x0 + cell_size_m
            cell = box(x0, y0, x1, y1)
            if not prepared.intersects(cell):
                continue
            intersection = cell.intersection(corridor)
            if intersection.area < min_area_m2:
                continue
            hits.append(
                CellHit(
                    cell_id=encode_cell_id(
                        kind, row, col, zone, cell_size_m=cell_size_m
                    ),
                    kind=kind,
                    zone=zone,
                    row=row,
                    col=col,
                    intersection_m2=float(intersection.area),
                )
            )
    return hits


def zone_band_bounds(
    zone: int, margin_deg: float = ZONE_BAND_MARGIN_DEG
) -> tuple[float, float, float, float]:
    """Western/eastern longitude bounds (with margin) of a UTM zone band."""
    west = 6 * zone - 186 - margin_deg
    east = 6 * zone - 180 + margin_deg
    return (west, -90.0, east, 90.0)


def coastal_zone_bands() -> tuple[int, ...]:
    """UTM zones that intersect the Chinese coastline."""
    return CHINA_COASTAL_UTM_ZONES
