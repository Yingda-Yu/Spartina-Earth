"""Deterministic fixed analysis-cell grid for Zhejiang (M2.1a2, Issue #12).

Spatial model (four strictly separated concepts):

    BayEnvelope      - stable regional identity / benchmark grouping
        v
    AnalysisCell     - fixed projected sample unit, NEVER date-dependent
        v
    CoastalState     - date-specific land/water/inundation metadata

The grid is one Zhejiang-wide fixed UTM grid (EPSG:32651) anchored at the
zone origin (0 m easting, 0 m northing). Cell indices are floor(E/size),
floor(N/size), so every cell_id is fully reconstructible from grid
coordinates -- no random UUIDs, no per-bay origins.

This module is pure geometry over explicit inputs; no Earth Engine, no
pixels, no labels (coastal relevance must be target-independent).
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from shapely.geometry import box
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as shp_transform
from shapely.prepared import prep

from spartina.data.gee.selection import canonical_fingerprint
from spartina.data.zhejiang.rois import geometry_fingerprint

GRID_ID: str = "ZJ_U51_FIXED_V0"
GRID_CRS: str = "EPSG:32651"
ANCHOR_EASTING_M: int = 0
ANCHOR_NORTHING_M: int = 0

CANDIDATE_CELL_SIZES_M: tuple[int, int, int] = (5_000, 10_000, 20_000)

SIZE_TAG: dict[int, str] = {5_000: "5K", 10_000: "10K", 20_000: "20K"}

#: target-independent coastal relevance categories
RELEVANT: str = "COASTAL_RELEVANT"
NOT_RELEVANT_INLAND: str = "NOT_RELEVANT_INLAND"
NOT_RELEVANT_OPEN_WATER: str = "NOT_RELEVANT_OPEN_WATER"
COASTAL_RELEVANCE_STATUSES: tuple[str, ...] = (
    RELEVANT,
    NOT_RELEVANT_INLAND,
    NOT_RELEVANT_OPEN_WATER,
)

COASTLINE_EVIDENCE: str = "GSHHG_v2.3.7_L1_MEAN_SHORELINE"
GEOMETRY_STATUS: str = "FIXED_CELL_GRID_OVER_PROVISIONAL_ENVELOPE_V0"


@dataclass(frozen=True)
class GridSpec:
    grid_id: str
    crs: str
    anchor_easting_m: int
    anchor_northing_m: int
    cell_size_m: int

    def size_tag(self) -> str:
        return SIZE_TAG[self.cell_size_m]

    def fingerprint(self) -> str:
        return canonical_fingerprint({
            "grid_id": self.grid_id,
            "crs": self.crs,
            "anchor_easting_m": self.anchor_easting_m,
            "anchor_northing_m": self.anchor_northing_m,
            "cell_size_m": self.cell_size_m,
            "cell_id_template": (
                "ZJ_U51_{5K|10K|20K}_E{index_east:03d}_N{index_north:03d}"
            ),
        })


def grid_spec(cell_size_m: int) -> GridSpec:
    if cell_size_m not in CANDIDATE_CELL_SIZES_M:
        raise ValueError(f"unsupported cell size {cell_size_m}")
    return GridSpec(
        grid_id=GRID_ID,
        crs=GRID_CRS,
        anchor_easting_m=ANCHOR_EASTING_M,
        anchor_northing_m=ANCHOR_NORTHING_M,
        cell_size_m=cell_size_m,
    )


def cell_id(spec: GridSpec, index_east: int, index_north: int) -> str:
    return (
        f"ZJ_U51_{spec.size_tag()}_E{index_east:03d}_N{index_north:03d}"
    )


def parse_cell_id(value: str) -> tuple[int, int, int]:
    """Inverse of :func:`cell_id`; raises on malformed ids."""
    parts = value.split("_")
    if (len(parts) != 5 or parts[0] != "ZJ" or parts[1] != "U51"
            or not parts[3].startswith("E") or not parts[4].startswith("N")):
        raise ValueError(f"malformed cell_id: {value}")
    tag_to_size = {v: k for k, v in SIZE_TAG.items()}
    if parts[2] not in tag_to_size:
        raise ValueError(f"unknown grid tag {parts[2]} in {value}")
    return tag_to_size[parts[2]], int(parts[3][1:]), int(parts[4][1:])


def cell_bounds(spec: GridSpec, index_east: int,
                index_north: int) -> tuple[float, float, float, float]:
    x0 = spec.anchor_easting_m + index_east * spec.cell_size_m
    y0 = spec.anchor_northing_m + index_north * spec.cell_size_m
    return x0, y0, x0 + spec.cell_size_m, y0 + spec.cell_size_m


def cell_polygon(spec: GridSpec, index_east: int,
                 index_north: int) -> BaseGeometry:
    return box(*cell_bounds(spec, index_east, index_north))


@dataclass
class CellRecord:
    cell_id: str
    grid_id: str
    cell_size_m: int
    crs: str
    index_east: int
    index_north: int
    westx_easting_m: float
    southy_northing_m: float
    eastx_easting_m: float
    northy_northing_m: float
    cell_area_km2: float
    bay_id: str
    envelope_intersect_fraction: float
    land_fraction_gshhg: float
    water_fraction_gshhg: float
    min_coastline_distance_m: float
    coastline_crossing: bool
    coastal_relevance: str
    coastal_evidence: str
    geometry_status: str
    geometry_fingerprint: str
    row_fingerprint: str = ""

    def as_row(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in ANALYSIS_CELL_COLUMNS}


ANALYSIS_CELL_COLUMNS: tuple[str, ...] = (
    "cell_id",
    "grid_id",
    "cell_size_m",
    "crs",
    "index_east",
    "index_north",
    "westx_easting_m",
    "southy_northing_m",
    "eastx_easting_m",
    "northy_northing_m",
    "cell_area_km2",
    "bay_id",
    "envelope_intersect_fraction",
    "land_fraction_gshhg",
    "water_fraction_gshhg",
    "min_coastline_distance_m",
    "coastline_crossing",
    "coastal_relevance",
    "coastal_evidence",
    "geometry_status",
    "geometry_fingerprint",
    "row_fingerprint",
)


def _bay_assignment(
    polygon: BaseGeometry,
    envelopes: dict[str, BaseGeometry],
) -> tuple[str, float]:
    """Deterministic max-intersection-area assignment.

    Envelopes are spatially disjoint for the three Zhejiang bays; a tie on
    area (including double-zero) raises instead of silently choosing.
    """
    best_id = ""
    best_area = -1.0
    for bay_id in sorted(envelopes):
        area = float(polygon.intersection(envelopes[bay_id]).area)
        if area == best_area and area > 0.0:
            raise ValueError(
                f"equal positive intersection tie for bays {best_id} "
                f"and {bay_id}")
        if area > best_area:
            best_area = area
            best_id = bay_id
    if best_area <= 0.0:
        raise ValueError("cell intersects no envelope")
    return best_id, best_area


def build_cells(
    spec: GridSpec,
    envelopes_projected: dict[str, BaseGeometry],
    land_projected: BaseGeometry,
    coastline_projected: BaseGeometry,
    *,
    coastal_belt_m: float,
) -> list[CellRecord]:
    """Enumerate fixed cells intersecting any bay envelope.

    Parameters
    ----------
    envelopes_projected:
        bay_id -> envelope polygon in EPSG:32651 (regional identity).
    land_projected:
        GSHHG land polygons (mean shoreline approximation), projected.
    coastline_projected:
        land/ocean boundary lines, projected.
    coastal_belt_m:
        target-independent half-width of the coastline-interface zone.
        A cell is COASTAL_RELEVANT iff it meets this zone.
    """
    if not envelopes_projected:
        raise ValueError("at least one envelope required")
    size = spec.cell_size_m
    ordered_ids = sorted(envelopes_projected)
    union_env = envelopes_projected[ordered_ids[0]]
    for bay_id in ordered_ids[1:]:
        union_env = union_env.union(envelopes_projected[bay_id])
    minx, miny, maxx, maxy = union_env.bounds
    ix0 = math.floor((minx - spec.anchor_easting_m) / size)
    iy0 = math.floor((miny - spec.anchor_northing_m) / size)
    ix1 = math.floor((maxx - spec.anchor_easting_m) / size)
    iy1 = math.floor((maxy - spec.anchor_northing_m) / size)

    land_prep = prep(land_projected)
    coastal_zone = coastline_projected.buffer(coastal_belt_m, join_style=2)
    coastal_prep = prep(coastal_zone)

    records: list[CellRecord] = []
    for iy in range(iy0, iy1 + 1):
        for ix in range(ix0, ix1 + 1):
            poly = cell_polygon(spec, ix, iy)
            if not poly.intersects(union_env):
                continue
            bay_id, env_area = _bay_assignment(poly, envelopes_projected)
            land_area = (
                float(poly.intersection(land_projected).area)
                if land_prep.intersects(poly) else 0.0
            )
            cell_area = float(poly.area)
            land_frac = round(land_area / cell_area, 6)
            water_frac = round(1.0 - land_frac, 6)
            crossing = bool(coastline_projected.crosses(poly)
                            or coastline_projected.intersects(poly)
                            and coastline_projected.intersection(poly).geom_type
                            in ("LineString", "MultiLineString"))
            if coastline_projected.intersects(poly):
                coast_dist = 0.0
            else:
                coast_dist = round(
                    float(poly.distance(coastline_projected)), 3)
            relevant = bool(coastal_prep.intersects(poly))
            if relevant:
                relevance = RELEVANT
            elif land_frac >= 0.5:
                relevance = NOT_RELEVANT_INLAND
            else:
                relevance = NOT_RELEVANT_OPEN_WATER
            cid = cell_id(spec, ix, iy)
            rec = CellRecord(
                cell_id=cid,
                grid_id=spec.grid_id,
                cell_size_m=size,
                crs=spec.crs,
                index_east=ix,
                index_north=iy,
                westx_easting_m=float(spec.anchor_easting_m + ix * size),
                southy_northing_m=float(spec.anchor_northing_m + iy * size),
                eastx_easting_m=float(spec.anchor_easting_m + (ix + 1) * size),
                northy_northing_m=float(
                    spec.anchor_northing_m + (iy + 1) * size),
                cell_area_km2=round(cell_area / 1_000_000.0, 6),
                bay_id=bay_id,
                envelope_intersect_fraction=round(env_area / cell_area, 6),
                land_fraction_gshhg=land_frac,
                water_fraction_gshhg=water_frac,
                min_coastline_distance_m=coast_dist,
                coastline_crossing=crossing,
                coastal_relevance=relevance,
                coastal_evidence=COASTLINE_EVIDENCE,
                geometry_status=GEOMETRY_STATUS,
                geometry_fingerprint=geometry_fingerprint(poly),
            )
            rec.row_fingerprint = canonical_fingerprint(
                {k: v for k, v in rec.as_row().items()
                 if k != "row_fingerprint"}
            )
            records.append(rec)
    records.sort(key=lambda r: (r.bay_id, r.index_north, r.index_east))
    return records


def registry_fingerprint(records: Iterable[CellRecord]) -> str:
    """Whole-registry hash over deterministically ordered rows."""
    rows = sorted(records, key=lambda r: (r.cell_size_m, r.cell_id))
    return canonical_fingerprint([
        {k: v for k, v in r.as_row().items()
         if k not in ("row_fingerprint",)}
        for r in rows
    ])


def cells_are_interior_disjoint(records: Iterable[CellRecord]) -> bool:
    """Test invariant: cells touch only along exact boundaries."""
    geoms = [
        cell_polygon(grid_spec(r.cell_size_m), r.index_east, r.index_north)
        for r in records
    ]
    for i, a in enumerate(geoms):
        for b in geoms[i + 1:]:
            if a.relate_pattern(b, "T********"):  # interior intersects
                return False
    return True


def project_geometries(
    geoms: Iterable[BaseGeometry], source_crs: str, target_crs: str
) -> list[BaseGeometry]:
    import pyproj

    projector = pyproj.Transformer.from_crs(
        source_crs, target_crs, always_xy=True
    ).transform
    return [shp_transform(projector, g) for g in geoms]
