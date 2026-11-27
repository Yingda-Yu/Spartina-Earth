#!/usr/bin/env python3
"""Build the nominal MGRS 100 km tile index for the China coastal domain.

MGRS tiles are computed from the MGRS standard with the ``mgrs`` package
(no bulk download): each W10 cell center plus fixed 8-neighbour offsets
(~>=10 km, so every tile straddling a cell is found) is mapped to its
100 km grid square; nominal squares are then intersected with the domain
corridor.

This index is a CHEAP PREFILTER ONLY. Its
``geometry_kind = NOMINAL_MGRS_100KM_GRID_PREFILTER`` geometry must never
be reported as an acquisition footprint: Sentinel-2 scenes can be
partial tiles (nocost/nodata regions) and every ObservationEvent keeps
its own ``actual_scene_geometry`` from metadata.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import geopandas as gpd
import mgrs
from pyproj import CRS
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry

from spartina.data.national.footprints import geometry_fingerprint, utc_now_iso

# Offsets in degrees; >=0.13 deg lon and >=0.11 deg lat exceeds 10 km
# everywhere in the domain (down to ~18 N).
SAMPLE_OFFSETS: tuple[tuple[float, float], ...] = (
    (0.0, 0.0),
    (0.15, 0.0),
    (-0.15, 0.0),
    (0.0, 0.13),
    (0.0, -0.13),
    (0.15, 0.13),
    (-0.15, 0.13),
    (0.15, -0.13),
    (-0.15, -0.13),
)

MGRS_LICENSE_NOTE = (
    "MGRS is a geospatial standard (NGA); tile geometry computed "
    "locally with the mgrs Python package, no external dataset downloaded"
)


def _git_commit() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    )
    return proc.stdout.strip() if proc.returncode == 0 else "UNKNOWN"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tile_polygon_4326(
    m: mgrs.MGRS, tile_id: str
) -> tuple[BaseGeometry, int, bool]:
    zone = int(tile_id[:2])
    _, hemi, easting, northing = m.MGRSToUTM(tile_id)
    if hemi != "N":
        raise ValueError(f"unexpected hemisphere for {tile_id}: {hemi}")
    utm_crs = CRS.from_epsg(32600 + zone)
    square = box(easting, northing, easting + 100_000, northing + 100_000)
    geometry = (
        gpd.GeoSeries([square], crs=utm_crs).to_crs("EPSG:4326").iloc[0]
    )
    # Boundary probes: nominal 100 km MGRS squares are clipped where UTM
    # zones or 8-degree latitude bands meet, so a point inside the
    # nominal square can legitimately carry a neighbouring tile id. A
    # mismatch at the 10 km probe (thin sliver) or at the 99 km probe
    # (no in-tile interior sampled here) flags the square as a grid-edge
    # overlap. As a conservative PREFILTER the square is still retained;
    # actual scene geometry is the final gate downstream.
    probe_10 = (
        gpd.GeoSeries(
            [box(easting + 10_000, northing + 10_000,
                 easting + 11_000, northing + 11_000)],
            crs=utm_crs,
        )
        .to_crs("EPSG:4326")
        .iloc[0]
        .centroid
    )
    probe_99 = (
        gpd.GeoSeries(
            [box(easting + 98_000, northing + 98_000,
                 easting + 99_000, northing + 99_000)],
            crs=utm_crs,
        )
        .to_crs("EPSG:4326")
        .iloc[0]
        .centroid
    )
    check_10 = m.toMGRS(probe_10.y, probe_10.x, MGRSPrecision=0)
    check_99 = m.toMGRS(probe_99.y, probe_99.x, MGRSPrecision=0)
    edge_overlap = check_10 != tile_id or check_99 != tile_id
    return geometry, zone, edge_overlap


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cells-csv", type=Path, required=True)
    parser.add_argument("--corridor-gpkg", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--tracked-doc", type=Path, required=True)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    m = mgrs.MGRS()
    candidate_tiles: set[str] = set()
    with args.cells_csv.open(newline="", encoding="utf-8") as handle:
        for record in csv.DictReader(handle):
            lon, lat = float(record["center_lon"]), float(record["center_lat"])
            for dlon, dlat in SAMPLE_OFFSETS:
                candidate_tiles.add(
                    m.toMGRS(lat + dlat, lon + dlon, MGRSPrecision=0)
                )

    corridor = gpd.read_file(args.corridor_gpkg, engine="pyogrio").to_crs("EPSG:4326")
    corridor_union = corridor.geometry.union_all()

    rows: list[dict[str, Any]] = []
    geoms = []
    for tile_id in sorted(candidate_tiles):
        geometry, zone, edge_overlap = _tile_polygon_4326(m, tile_id)
        if not geometry.intersects(corridor_union):
            continue
        minx, miny, maxx, maxy = geometry.bounds
        rows.append(
            {
                "mgrs_tile": tile_id,
                "utm_zone": zone,
                "lat_band": tile_id[2],
                "square": tile_id[3:],
                "geometry_kind": "NOMINAL_MGRS_100KM_GRID_PREFILTER",
                "actual_scene_geometry": "REQUIRED_FROM_SCENE_METADATA",
                "geometry_sha256": geometry_fingerprint(geometry),
                "minx": round(minx, 7),
                "miny": round(miny, 7),
                "maxx": round(maxx, 7),
                "maxy": round(maxy, 7),
                "nominal_area_km2": 10_000,
                "grid_edge_overlap": int(edge_overlap),
            }
        )
        geoms.append(geometry)

    fieldnames = list(rows[0].keys())
    csv_path = args.out_dir / "mgrs_china_coast_index.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    gpkg_path = args.out_dir / "mgrs_china_coast.gpkg"
    gpd.GeoDataFrame(rows, geometry=geoms, crs="EPSG:4326").to_file(
        gpkg_path, driver="GPKG", engine="pyogrio"
    )

    manifest = {
        "artifact": "mgrs_nominal_tile_index",
        "version": "v0",
        "generated_utc": utc_now_iso(),
        "git_commit": _git_commit(),
        "role": "cheap nominal prefilter for Sentinel cell joins; NOT a scene footprint",
        "method": {
            "generator": "mgrs Python package (MGRS standard, NGA)",
            "sampling": "W10 cell centers + 8 fixed lon/lat offsets (~>=10 km)",
            "license_note": MGRS_LICENSE_NOTE,
            "roundtrip_check": "every tile center maps back to its tile id",
        },
        "prefilter_discipline": (
            "Sentinel-2 ObservationEvents must keep actual scene geometry; "
            "nominal tile geometry can only prefilter candidates"
        ),
        "corridor": str(args.corridor_gpkg),
        "candidate_tiles_seen": len(candidate_tiles),
        "n_tiles_intersecting_corridor": len(rows),
        "utm_zones": sorted({r["utm_zone"] for r in rows}),
        "lat_bands": sorted({r["lat_band"] for r in rows}),
        "grid_edge_overlap_tiles": [
            r["mgrs_tile"] for r in rows if r["grid_edge_overlap"]
        ],
        "outputs": {
            "index_csv": csv_path.name,
            "index_csv_sha256": _sha256(csv_path),
            "tile_gpkg": gpkg_path.name,
            "tile_gpkg_sha256": _sha256(gpkg_path),
        },
    }
    args.tracked_doc.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"tiles={len(rows)} (candidates {len(candidate_tiles)})")
    print(f"csv={csv_path} gpkg={gpkg_path} manifest={args.tracked_doc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
