#!/usr/bin/env python3
"""Build the target-independent national coastal domain (Issue #14).

Deterministic construction of the 5/10/20 km coastal corridors and of the
two candidate 10 km lattices (China Albers equal-area vs UTM-zone-aware).
Writes deterministic cell lists (CSV), corridor bytes (GPKG) and a fully
hashed stats JSON into an output directory; no label product is touched.

Usage (M0/M1, offline; requires the geo extra)::

    PYTHONPATH=src python3 scripts/data/national/build_national_domain.py \
        --gshhs-shp work/external/gshhg_2_3_7/extracted/GSHHS_shp/h/GSHHS_h_L1.shp \
        --admin0-shp work/external/naturalearth_10m_admin0/extracted/ne_10m_admin_0_countries.shp \
        --out-dir work/national/domain
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
from pyproj import CRS, Transformer
from shapely.geometry import Point, box
from shapely.geometry.base import BaseGeometry

from spartina.data.national import geometry as nat_geom
from spartina.data.national.coastal_domain import (
    DEFAULT_BBOX_WGS84,
    ZONE_BAND_MARGIN_DEG,
    CellHit,
    build_china_land,
    build_corridor,
    coastal_zone_bands,
    scan_lattice_cells,
    zone_band_bounds,
)
from spartina.data.national.grid import CELL_SIZE_M, GridKind, utm_epsg


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_commit() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    )
    return proc.stdout.strip() if proc.returncode == 0 else "UNKNOWN"


def _write_cells_csv(
    path: Path, hits: list[CellHit], center_lonlat: dict[str, tuple[float, float]]
) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "cell_id",
                "grid_kind",
                "utm_zone",
                "row",
                "col",
                "intersection_area_m2",
                "center_lon",
                "center_lat",
            ]
        )
        for hit in hits:
            lon, lat = center_lonlat[hit.cell_id]
            writer.writerow(
                [
                    hit.cell_id,
                    hit.kind.value,
                    "" if hit.zone is None else hit.zone,
                    hit.row,
                    hit.col,
                    f"{hit.intersection_m2:.3f}",
                    f"{lon:.6f}",
                    f"{lat:.6f}",
                ]
            )


def _cell_polygon_aea(hit: CellHit, crs: CRS) -> BaseGeometry:
    polygon = box(
        hit.col * CELL_SIZE_M,
        hit.row * CELL_SIZE_M,
        (hit.col + 1) * CELL_SIZE_M,
        (hit.row + 1) * CELL_SIZE_M,
    )
    if hit.kind is GridKind.CHINA_ALBERS:
        return polygon
    if hit.zone is None:
        raise ValueError("UTM hit without zone")
    source = CRS.from_epsg(utm_epsg(hit.zone))
    return gpd.GeoSeries([polygon], crs=source).to_crs(crs).iloc[0]


def _seam_overlap(
    left_hits: list[CellHit],
    right_hits: list[CellHit],
    left_zone: int,
    right_zone: int,
    seam_lon: float,
    aea: CRS,
) -> dict[str, Any]:
    """Overlap stats for two UTM lattices across a zone boundary."""
    strip = box(seam_lon - 0.12, 15.0, seam_lon + 0.12, 43.0)

    def near_seam(hits: list[CellHit], zone: int) -> gpd.GeoDataFrame:
        crs = CRS.from_epsg(utm_epsg(zone))
        to_wgs = Transformer.from_crs(crs, 4326, always_xy=True)
        rows: list[dict[str, Any]] = []
        for hit in hits:
            lon, lat = to_wgs.transform(
                (hit.col + 0.5) * CELL_SIZE_M, (hit.row + 0.5) * CELL_SIZE_M
            )
            if strip.contains(Point(lon, lat)):
                rows.append({"cell_id": hit.cell_id, "geometry": _cell_polygon_aea(hit, aea)})
        id_col = "id_l" if zone == left_zone else "id_r"
        if not rows:
            return gpd.GeoDataFrame(
                {id_col: [], "geometry": []}, geometry="geometry", crs=aea
            )
        frame = gpd.GeoDataFrame(rows, geometry="geometry", crs=aea)
        return frame.rename(columns={"cell_id": id_col})

    left = near_seam(left_hits, left_zone)
    right = near_seam(right_hits, right_zone)
    pairs = 0
    overlap_m2 = 0.0
    if len(left) and len(right):
        joined = gpd.sjoin(left, right, how="inner", predicate="intersects")
        for row in joined.itertuples(index=False):
            pairs += 1
            gl = left.loc[left["id_l"] == row.id_l, "geometry"].iloc[0]
            gr = right.loc[right["id_r"] == row.id_r, "geometry"].iloc[0]
            overlap_m2 += float(gl.intersection(gr).area)
    return {
        "seam_longitude": seam_lon,
        "left_zone": left_zone,
        "right_zone": right_zone,
        "left_cells_in_strip": int(len(left)),
        "right_cells_in_strip": int(len(right)),
        "overlapping_cell_pairs": int(pairs),
        "pairwise_overlap_area_m2": round(overlap_m2, 1),
        "note": "two lattices overlap inside the +-0.12 degree seam strip; a single "
        "production grid must deduplicate these cells (Albers strategy has no seams)",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gshhs-shp", type=Path, required=True)
    parser.add_argument("--admin0-shp", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--gshhs-f-shp", type=Path, default=None)
    parser.add_argument("--widths", type=int, nargs="+", default=[5_000, 10_000, 20_000])
    parser.add_argument("--island-near-m", type=int, default=25_000)
    parser.add_argument("--island-max-area-m2", type=int, default=100_000_000)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    aea = nat_geom.CHINA_ALBERS_CRS
    bbox = DEFAULT_BBOX_WGS84

    gshhs = gpd.read_file(args.gshhs_shp, bbox=bbox, engine="pyogrio")
    admin0 = gpd.read_file(args.admin0_shp, bbox=bbox, engine="pyogrio")
    china_land = build_china_land(
        gshhs,
        admin0,
        aea.to_proj4(),
        island_max_area_m2=args.island_max_area_m2,
        island_near_m=args.island_near_m,
    )
    all_land_aea = gshhs.to_crs(aea).union_all()

    # No-island sensitivity baseline (W10 only).
    corridor_no_islands = build_corridor(china_land.mainland, all_land_aea, 10_000)
    aea_no_islands = len(scan_lattice_cells(corridor_no_islands, GridKind.CHINA_ALBERS))

    stats: dict[str, Any] = {
        "artifact": "china_national_coastal_domain",
        "version": "v0",
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "git_commit": _git_commit(),
        "parameters": {
            "bbox_wgs84": list(bbox),
            "cell_size_m": CELL_SIZE_M,
            "widths_m": args.widths,
            "island_near_m": args.island_near_m,
            "island_max_area_m2": args.island_max_area_m2,
            "zone_band_margin_deg": ZONE_BAND_MARGIN_DEG,
            "min_cell_intersection_fraction": 0.01,
            "corridor_definition": (
                "seaward=buffer(china,W)-all_land; "
                "onshore=china intersect buffer(seaward,W); corridor=union"
            ),
        },
        "sources": {
            "gshhs_shp": str(args.gshhs_shp),
            "admin0_shp": str(args.admin0_shp),
            "gshhs_passport": "work/external/gshhg_2_3_7/SOURCE_PASSPORT.json",
            "natural_earth_passport": (
                "work/external/naturalearth_10m_admin0/SOURCE_PASSPORT.json"
            ),
        },
        "china_land_diagnostics": {
            "land_area_km2": round(china_land.land_area_m2 / 1e6, 2),
            "added_island_count": china_land.added_island_count,
            "added_island_area_km2": round(china_land.added_island_area_m2 / 1e6, 2),
        },
        "widths": [],
        "strategy_comparison_at_10000m": {},
        "sensitivity": {
            "aea_cells_without_added_islands": aea_no_islands,
        },
    }

    # Augmented China land (mainland + recovered islands) in WGS84 for
    # banded UTM construction; using only the Natural Earth polygon here
    # would drop all archipelago seas (Zhoushan, Yangtze mouth).
    china_aug_wgs = gpd.GeoSeries([china_land.land], crs=aea).to_crs(4326).iloc[0]

    utm_all_hits: dict[int, list[CellHit]] = {}
    for width in args.widths:
        width_key = f"W{width}"
        corridor_aea = build_corridor(china_land.land, all_land_aea, width)
        aea_hits = scan_lattice_cells(corridor_aea, GridKind.CHINA_ALBERS)

        # Deterministic cell lists.
        aea_xy = Transformer.from_crs(aea, 4326, always_xy=True)
        centers: dict[str, tuple[float, float]] = {}
        for hit in aea_hits:
            centers[hit.cell_id] = aea_xy.transform(
                (hit.col + 0.5) * CELL_SIZE_M, (hit.row + 0.5) * CELL_SIZE_M
            )

        utm_hits_by_zone: dict[int, list[CellHit]] = {}
        for zone in coastal_zone_bands():
            west, _, east, _ = zone_band_bounds(zone)
            band = box(west, bbox[1], east, bbox[3])
            china_band = china_aug_wgs.intersection(band)
            if china_band.is_empty:
                utm_hits_by_zone[zone] = []
                continue
            utm = CRS.from_epsg(utm_epsg(zone))
            china_utm = gpd.GeoSeries([china_band], crs=4326).to_crs(utm).iloc[0]
            all_utm = (
                gpd.GeoSeries([all_land_aea], crs=aea)
                .to_crs(utm)
                .iloc[0]
                .intersection(box(*china_utm.buffer(width + 15_000).bounds))
            )
            corridor_utm = build_corridor(china_utm, all_utm, width)
            zone_hits = scan_lattice_cells(corridor_utm, GridKind.UTM_ZONE_AWARE, zone)
            utm_hits_by_zone[zone] = zone_hits
            xy = Transformer.from_crs(utm, 4326, always_xy=True)
            for hit in zone_hits:
                centers[hit.cell_id] = xy.transform(
                    (hit.col + 0.5) * CELL_SIZE_M, (hit.row + 0.5) * CELL_SIZE_M
                )
            if width == 10_000:
                utm_all_hits[zone] = zone_hits

        utm_hits = [hit for zone in coastal_zone_bands() for hit in utm_hits_by_zone[zone]]
        aea_csv = args.out_dir / f"cells_china_albers_{width_key}.csv"
        utm_csv = args.out_dir / f"cells_utm_zone_aware_{width_key}.csv"
        _write_cells_csv(aea_csv, aea_hits, centers)
        _write_cells_csv(utm_csv, utm_hits, centers)

        # Bytes: corridor geometry (ignored by Git; regenerable).
        gpd.GeoDataFrame(
            {"width_m": [width]}, geometry=[corridor_aea], crs=aea
        ).to_file(args.out_dir / f"corridor_{width_key}.gpkg", driver="GPKG")

        stats["widths"].append(
            {
                "width_m": width,
                "corridor_area_km2": round(corridor_aea.area / 1e6, 2),
                "china_albers_cells": len(aea_hits),
                "utm_zone_aware_cells": len(utm_hits),
                "utm_cells_by_zone": {
                    str(zone): len(utm_hits_by_zone[zone]) for zone in coastal_zone_bands()
                },
                "files": {
                    "albers_cells_csv": aea_csv.name,
                    "albers_cells_csv_sha256": _sha256(aea_csv),
                    "utm_cells_csv": utm_csv.name,
                    "utm_cells_csv_sha256": _sha256(utm_csv),
                    "corridor_gpkg": f"corridor_{width_key}.gpkg",
                },
            }
        )

    # Strategy comparison at W10.
    corridor10 = build_corridor(china_land.land, all_land_aea, 10_000)
    aea10 = scan_lattice_cells(corridor10, GridKind.CHINA_ALBERS)
    aea_union = gpd.GeoSeries(
        [_cell_polygon_aea(hit, aea) for hit in aea10], crs=aea
    ).union_all()
    utm10 = [hit for zone in coastal_zone_bands() for hit in utm_all_hits[zone]]
    utm_union = gpd.GeoSeries(
        [_cell_polygon_aea(hit, aea) for hit in utm10], crs=aea
    ).union_all()
    seams = [
        _seam_overlap(utm_all_hits[49], utm_all_hits[50], 49, 50, 114.0, aea),
        _seam_overlap(utm_all_hits[50], utm_all_hits[51], 50, 51, 120.0, aea),
        _seam_overlap(utm_all_hits[51], utm_all_hits[52], 51, 52, 126.0, aea),
    ]
    stats["strategy_comparison_at_10000m"] = {
        "china_albers": {
            "cells": len(aea10),
            "cell_union_area_km2": round(aea_union.area / 1e6, 2),
        },
        "utm_zone_aware": {
            "cells": len(utm10),
            "cell_union_area_km2": round(utm_union.area / 1e6, 2),
        },
        "grid_ground_intersection_km2": round(aea_union.intersection(utm_union).area / 1e6, 2),
        "grid_ground_symmetric_difference_km2": round(
            aea_union.symmetric_difference(utm_union).area / 1e6, 2
        ),
        "seams": seams,
    }

    if args.gshhs_f_shp is not None:
        gshhs_f = gpd.read_file(args.gshhs_f_shp, bbox=bbox, engine="pyogrio")
        land_f = build_china_land(
            gshhs_f,
            admin0,
            aea.to_proj4(),
            island_max_area_m2=args.island_max_area_m2,
            island_near_m=args.island_near_m,
        )
        all_f = gshhs_f.to_crs(aea).union_all()
        f_counts: dict[str, int] = {}
        for width in args.widths:
            corridor_f = build_corridor(land_f.land, all_f, width)
            f_counts[f"W{width}"] = len(
                scan_lattice_cells(corridor_f, GridKind.CHINA_ALBERS)
            )
        stats["sensitivity"]["full_resolution_aea_cells"] = f_counts

    stats_path = args.out_dir / "domain_stats.json"
    stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n")
    print(f"wrote {stats_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
