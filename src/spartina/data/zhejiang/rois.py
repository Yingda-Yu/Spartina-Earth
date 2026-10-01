"""Deterministic Tier-C derivation of the three Zhejiang bay ROIs.

No official, redistributable bay polygon was found for any of the three
bays (see docs/data/ZHEJIANG_ROI_PROVENANCE.md). The v0 study regions are
therefore built deterministically from:

1. named closing-section anchors (headlands / bay-mouth islands), each
   snapped to the *nearest vertex* of the pinned GSHHG v2.3.7 shoreline
   within an explicit, per-anchor radius;
2. onshore CONSTRUCTION_CORNER points that close the envelope across the
   bay head (asserted to lie on land);
3. ``water = envelope - land`` and an onshore inclusion belt of fixed
   width (2 km in v0), so the region covers the intertidal habitat zone.

Everything here is pure geometry over explicit inputs; the driver
``scripts/data/zhejiang/build_roi_registry.py`` owns file I/O and GEE-free.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from shapely.geometry import Point, Polygon, mapping
from shapely.ops import transform as shp_transform
from shapely.ops import unary_union
from shapely.validation import make_valid

from spartina.data.gee.selection import canonical_fingerprint

EARTH_RADIUS_M: float = 6_371_008.8
COORDINATE_DECIMALS: int = 6


@dataclass(frozen=True)
class Anchor:
    anchor_id: str
    kind: str
    lon: float
    lat: float
    snap_radius_m: float
    place_zh: str
    source_id: str | None = None


@dataclass(frozen=True)
class BaySpec:
    roi_id: str
    name_zh: str
    name_en: str
    envelope_order: tuple[str, ...]
    anchors: tuple[Anchor, ...]
    onshore_belt_m: float
    published_area_km2: float | None
    published_area_note: str = ""

    def anchor(self, anchor_id: str) -> Anchor:
        for a in self.anchors:
            if a.anchor_id == anchor_id:
                return a
        raise KeyError(f"{self.roi_id}: anchor {anchor_id!r} not in spec")


@dataclass(frozen=True)
class SnapRecord:
    anchor_id: str
    kind: str
    requested_lon: float
    requested_lat: float
    snapped_lon: float
    snapped_lat: float
    snap_distance_m: float


@dataclass
class BayGeometry:
    roi_id: str
    roi_geometry: Any
    envelope: Any
    water: Any
    belt: Any
    snap_records: list[SnapRecord] = field(default_factory=list)
    repaired: bool = False


# --------------------------------------------------------------------------
# Config parsing
# --------------------------------------------------------------------------
def parse_bay_specs(config: dict[str, Any]) -> list[BaySpec]:
    specs: list[BaySpec] = []
    for bay in config["rois"]:
        anchors = tuple(
            Anchor(
                anchor_id=a["id"],
                kind=a["kind"],
                lon=float(a["lon"]),
                lat=float(a["lat"]),
                snap_radius_m=float(a.get("snap_radius_m", 0.0)),
                place_zh=a.get("place_zh", ""),
                source_id=a.get("source_id"),
            )
            for a in bay["anchors"]
        )
        specs.append(
            BaySpec(
                roi_id=bay["roi_id"],
                name_zh=bay["name_zh"],
                name_en=bay["name_en"],
                envelope_order=tuple(bay["envelope_order"]),
                anchors=anchors,
                onshore_belt_m=float(bay["onshore_belt_m"]),
                published_area_km2=(
                    float(bay["published_area_km2"])
                    if bay.get("published_area_km2") is not None else None
                ),
                published_area_note=bay.get("published_area_note", ""),
            )
        )
    return specs


# --------------------------------------------------------------------------
# Geometry helpers
# --------------------------------------------------------------------------
def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    h = (math.sin(dphi / 2.0) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2.0) ** 2)
    return 2.0 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def polygon_rings(geometries: Iterable[Any]) -> list[list[tuple[float, float]]]:
    """Extract deterministic exterior coordinate rings from shapely geoms."""
    rings: list[list[tuple[float, float]]] = []
    for geom in geometries:
        if geom is None or geom.is_empty:
            continue
        polys = list(geom.geoms) if hasattr(geom, "geoms") else [geom]
        for poly in polys:
            if poly.geom_type not in ("Polygon", "MultiPolygon"):
                continue
            target = [poly] if poly.geom_type == "Polygon" else list(poly.geoms)
            for part in target:
                rings.append([(float(x), float(y))
                              for x, y in part.exterior.coords])
    return rings


def snap_to_coastline(
    anchor: Anchor,
    rings: list[list[tuple[float, float]]],
) -> SnapRecord:
    """Nearest coastline vertex by great-circle distance.

    Deterministic tie-break: earlier polygon ring, then earlier vertex.
    SECTION_POINT anchors must fall inside ``snap_radius_m``; a failure
    raises rather than silently moving the section.
    """
    best: tuple[float, int, int, tuple[float, float]] | None = None
    for pi, ring in enumerate(rings):
        for vi, (x, y) in enumerate(ring):
            d = haversine_m(anchor.lon, anchor.lat, x, y)
            if best is None or d < best[0]:
                best = (d, pi, vi, (x, y))
    if best is None:
        raise ValueError(f"{anchor.anchor_id}: coastline has no vertices")
    dist_m, _, _, (sx, sy) = best
    if anchor.kind == "SECTION_POINT" and dist_m > anchor.snap_radius_m:
        raise ValueError(
            f"{anchor.anchor_id}: nearest coastline vertex is {dist_m:.1f} m "
            f"away but snap radius is {anchor.snap_radius_m:.1f} m"
        )
    return SnapRecord(
        anchor_id=anchor.anchor_id,
        kind=anchor.kind,
        requested_lon=anchor.lon,
        requested_lat=anchor.lat,
        snapped_lon=sx,
        snapped_lat=sy,
        snap_distance_m=round(dist_m, 3),
    )


def _as_valid(geometry: Any) -> tuple[Any, bool]:
    if geometry.is_valid:
        return geometry, False
    repaired = make_valid(geometry)
    return repaired, True


def construct_bay(
    spec: BaySpec,
    land_union: Any,
    rings: list[list[tuple[float, float]]],
    projection: str,
) -> BayGeometry:
    """Build envelope/water/belt/ROI for one bay; never mutates inputs."""
    import pyproj

    snaps: dict[str, SnapRecord] = {}
    ordered: list[tuple[float, float]] = []
    for anchor_id in spec.envelope_order:
        anchor = spec.anchor(anchor_id)
        if anchor.kind == "SECTION_POINT":
            rec = snap_to_coastline(anchor, rings)
            snaps[anchor_id] = rec
            ordered.append((rec.snapped_lon, rec.snapped_lat))
        elif anchor.kind == "CONSTRUCTION_CORNER":
            point = Point(anchor.lon, anchor.lat)
            if not land_union.covers(point):
                raise ValueError(
                    f"{anchor.anchor_id}: construction corner "
                    f"({anchor.lon},{anchor.lat}) is not on mapped land"
                )
            ordered.append((anchor.lon, anchor.lat))
        else:  # pragma: no cover - guarded by schema tests on config load
            raise ValueError(f"{anchor.anchor_id}: unknown kind {anchor.kind}")

    envelope = Polygon(ordered)
    if not envelope.is_valid:
        raise ValueError(f"{spec.roi_id}: envelope ring is not valid")

    water_raw = envelope.difference(land_union)
    water, water_repaired = _as_valid(water_raw)

    to_projected = pyproj.Transformer.from_crs(
        4326, projection, always_xy=True
    ).transform
    to_geographic = pyproj.Transformer.from_crs(
        projection, 4326, always_xy=True
    ).transform

    water_p = shp_transform(to_projected, water)
    land_in_env_p = shp_transform(
        to_projected, land_union.intersection(envelope)
    )
    buffered = water_p.buffer(spec.onshore_belt_m, join_style=2)
    belt_p = land_in_env_p.intersection(buffered.difference(water_p))
    belt = shp_transform(to_geographic, belt_p)
    roi_raw = unary_union([water, belt])
    roi, roi_repaired = _as_valid(roi_raw)

    return BayGeometry(
        roi_id=spec.roi_id,
        roi_geometry=roi,
        envelope=envelope,
        water=water,
        belt=belt,
        snap_records=list(snaps.values()),
        repaired=water_repaired or roi_repaired,
    )


# --------------------------------------------------------------------------
# QA + fingerprints
# --------------------------------------------------------------------------
def area_km2_projected(geometry: Any, projection: str) -> float:
    import pyproj

    project = pyproj.Transformer.from_crs(
        4326, projection, always_xy=True
    ).transform
    return float(shp_transform(project, geometry).area / 1_000_000.0)


def bbox_wesn(geometry: Any) -> tuple[float, float, float, float]:
    minx, miny, maxx, maxy = geometry.bounds
    return (
        round(minx, COORDINATE_DECIMALS),
        round(maxx, COORDINATE_DECIMALS),
        round(miny, COORDINATE_DECIMALS),
        round(maxy, COORDINATE_DECIMALS),
    )


def _round_recursive(obj: Any) -> Any:
    if isinstance(obj, float):
        return round(obj, COORDINATE_DECIMALS)
    if isinstance(obj, dict):
        return {k: _round_recursive(obj[k]) for k in sorted(obj)}
    if isinstance(obj, list | tuple):
        return [_round_recursive(v) for v in obj]
    return obj


def geometry_fingerprint(geometry: Any) -> str:
    payload = _round_recursive(mapping(geometry))
    return canonical_fingerprint(payload)


def registry_row(
    spec: BaySpec,
    geom: BayGeometry,
    *,
    base_coastline_id: str,
    base_coastline_sha256: str,
    projection: str,
    source_ids: list[str],
) -> dict[str, Any]:
    water_km2 = area_km2_projected(geom.water, projection)
    belt_km2 = area_km2_projected(geom.belt, projection)
    roi_km2 = area_km2_projected(geom.roi_geometry, projection)
    env_km2 = area_km2_projected(geom.envelope, projection)
    published = spec.published_area_km2
    delta_pct = (
        round(100.0 * (water_km2 - published) / published, 2)
        if published else None
    )
    max_snap = max(
        (r.snap_distance_m for r in geom.snap_records), default=0.0
    )
    row = {
        "roi_id": spec.roi_id,
        "name_zh": spec.name_zh,
        "name_en": spec.name_en,
        "geometry_status": "PROVISIONAL_TIER_C_DERIVED",
        "provenance_tier": "C_DERIVED",
        "derivation_method": (
            "gshhg237_snapped_sections+water=env-land+onshore_belt"
        ),
        "base_coastline_id": base_coastline_id,
        "base_coastline_sha256": base_coastline_sha256,
        "source_crs": "EPSG:4326",
        "analysis_crs": projection,
        "envelope_area_km2": round(env_km2, 3),
        "water_area_km2": round(water_km2, 3),
        "onshore_belt_area_km2": round(belt_km2, 3),
        "roi_area_km2": round(roi_km2, 3),
        "published_area_km2": published,
        "published_area_delta_pct": delta_pct,
        "bbox_west_east_south_north": "|".join(
            str(v) for v in bbox_wesn(geom.roi_geometry)
        ),
        "max_anchor_snap_m": round(max_snap, 3),
        "geometry_is_valid": bool(geom.roi_geometry.is_valid),
        "geometry_fingerprint": geometry_fingerprint(geom.roi_geometry),
        "logical_fingerprint": "",
        "source_ids": "|".join(source_ids),
        "notes": (
            "non-official derivation; mean shoreline; "
            + ("make_valid applied; " if geom.repaired else "")
            + "published area is chart/datum-unknown sanity check"
        ),
    }
    row["logical_fingerprint"] = canonical_fingerprint(
        {k: v for k, v in row.items() if k != "logical_fingerprint"}
    )
    return row


def geojson_feature(
    spec: BaySpec,
    geom: BayGeometry,
    row: dict[str, Any],
) -> dict[str, Any]:
    return {
        "type": "Feature",
        "geometry": _round_recursive(mapping(geom.roi_geometry)),
        "properties": {
            "roi_id": spec.roi_id,
            "name_zh": spec.name_zh,
            "name_en": spec.name_en,
            "status": "PROVISIONAL_TIER_C_DERIVED",
            "provenance_tier": "C_DERIVED",
            "onshore_belt_m": spec.onshore_belt_m,
            "geometry_fingerprint": row["geometry_fingerprint"],
            "logical_fingerprint": row["logical_fingerprint"],
            "base_coastline": "GSHHG v2.3.7 (c) UH/NOAA, LGPL-3.0-or-later; "
                              "Wessel & Smith 1996, DOI 10.1029/96JB00104",
            "derived_for": "Spartina Earth M2.1a sampling frame; not an "
                           "official government boundary",
        },
    }
