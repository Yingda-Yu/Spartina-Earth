#!/usr/bin/env python3
"""R1 Part C: derive footprint indices v0_1 from the W10 cell union.

v0 intersected the *corridor* polygon and the optical fetch carried a
hard server-side bbox (maxx=127 E) that excluded the 23 far-NE cells
(130.4-131.2 E). v0_1 removes every hard-coded path/tile range: WRS-2
frames and MGRS tiles are kept exactly when their polygon intersects
the union of all 3,319 retained W10 cell polygons (the actual domain
units). v0 files are never overwritten; a tracked manifest records both
sets and their differences (v0 remains marked SUPERSEDED_BY_V0_1).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import geopandas as gpd
import mgrs

from spartina.data.national.census_join import load_cells
from spartina.data.national.footprints import (
    L7_EXTENDED_RESUME,
    L7_NOMINAL_END,
    L7_SLC_FAILURE,
    NOMINAL_WINDOWS,
    geometry_fingerprint,
    utc_now_iso,
)


def _git_commit() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    )
    return proc.stdout.strip() if proc.returncode == 0 else "UNKNOWN"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_mgrs_builder(script_path: Path) -> Any:
    spec = importlib.util.spec_from_file_location("build_mgrs_index_v0", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_wrs(
    source_shp: Path,
    cell_union: Any,
    out_dir: Path,
) -> tuple[dict[str, Any], set[str]]:
    frames = gpd.read_file(source_shp, engine="pyogrio")
    hits = gpd.sjoin(
        frames,
        gpd.GeoDataFrame(geometry=[cell_union], crs="EPSG:4326"),
        how="inner",
        predicate="intersects",
    ).drop_duplicates(subset=["PATH", "ROW"]).sort_values(["PATH", "ROW"])

    rows: list[dict[str, Any]] = []
    geoms = []
    for _, record in hits.iterrows():
        path, row = int(record["PATH"]), int(record["ROW"])
        geom = record.geometry
        minx, miny, maxx, maxy = geom.bounds
        item = {
            "frame_id": f"WRS2-D-P{path:03d}-R{row:03d}",
            "path": path,
            "row": row,
            "wrs_mode": "D",
            "wrspr": str(record["WRSPR"]),
            "rings_ok": int(record["RINGS_OK"]),
            "rings_nok": int(record["RINGS_NOK"]),
            "acq_day_l7": None
            if record["ACQDayL7"] is None
            else int(record["ACQDayL7"]),
            "acq_day_l8": None
            if record["ACQDayL8"] is None
            else int(record["ACQDayL8"]),
            "geometry_kind": "NOMINAL_WRS2_DESCENDING_POLYGON",
            "geometry_sha256": geometry_fingerprint(geom),
            "minx": round(minx, 7),
            "miny": round(miny, 7),
            "maxx": round(maxx, 7),
            "maxy": round(maxy, 7),
            "valid_for_sensors": (
                "landsat5,landsat8,landsat9,l7_pre_slc_failure,l7_post_slc_failure"
            ),
            "not_valid_for": "landsat7_extended_science_mission_geometric_drift",
        }
        rows.append(item)
        geoms.append(geom)

    csv_path = out_dir / "wrs2_china_coast_v0_1_index.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    gpkg_path = out_dir / "wrs2_china_coast_v0_1.gpkg"
    gpd.GeoDataFrame(rows, geometry=geoms, crs="EPSG:4326").to_file(
        gpkg_path, driver="GPKG", engine="pyogrio"
    )
    return (
        {
            "index_csv": csv_path.name,
            "index_csv_sha256": _sha256(csv_path),
            "footprint_gpkg": gpkg_path.name,
            "footprint_gpkg_sha256": _sha256(gpkg_path),
            "n_frames": len(rows),
            "paths": sorted({r["path"] for r in rows}),
            "sensor_era_rules": {
                "nominal_windows": {
                    key: {
                        "start": value.start.isoformat(),
                        "end": value.end.isoformat() if value.end else None,
                        "note": value.note,
                    }
                    for key, value in NOMINAL_WINDOWS.items()
                },
                "l7_slc_failure_utc": L7_SLC_FAILURE.isoformat(),
                "l7_nominal_wrs2_end_utc": L7_NOMINAL_END.isoformat(),
                "l7_extended_resume_utc": L7_EXTENDED_RESUME.isoformat(),
            },
        },
        {r["frame_id"] for r in rows},
    )


def build_mgrs(
    cells_csv: Path,
    cell_union: Any,
    out_dir: Path,
    builder_script: Path,
) -> tuple[dict[str, Any], set[str]]:
    builder = _load_mgrs_builder(builder_script)
    m = mgrs.MGRS()
    candidate_tiles: set[str] = set()
    with cells_csv.open(newline="", encoding="utf-8") as handle:
        for record in csv.DictReader(handle):
            lon, lat = float(record["center_lon"]), float(record["center_lat"])
            for dlon, dlat in builder.SAMPLE_OFFSETS:
                candidate_tiles.add(
                    m.toMGRS(lat + dlat, lon + dlon, MGRSPrecision=0)
                )

    rows: list[dict[str, Any]] = []
    geoms = []
    for tile_id in sorted(candidate_tiles):
        geometry, zone, edge_overlap = builder._tile_polygon_4326(m, tile_id)
        if not geometry.intersects(cell_union):
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

    csv_path = out_dir / "mgrs_china_coast_v0_1_index.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    gpkg_path = out_dir / "mgrs_china_coast_v0_1.gpkg"
    gpd.GeoDataFrame(rows, geometry=geoms, crs="EPSG:4326").to_file(
        gpkg_path, driver="GPKG", engine="pyogrio"
    )
    return (
        {
            "index_csv": csv_path.name,
            "index_csv_sha256": _sha256(csv_path),
            "tile_gpkg": gpkg_path.name,
            "tile_gpkg_sha256": _sha256(gpkg_path),
            "n_tiles": len(rows),
            "candidate_tiles_seen": len(candidate_tiles),
            "utm_zones": sorted({r["utm_zone"] for r in rows}),
            "lat_bands": sorted({r["lat_band"] for r in rows}),
            "license_note": builder.MGRS_LICENSE_NOTE,
        },
        {r["mgrs_tile"] for r in rows},
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cells-csv",
        type=Path,
        default=Path("work/national/domain/cells_china_albers_W10000.csv"),
    )
    parser.add_argument(
        "--wrs-source",
        type=Path,
        default=Path("work/national/footprints/source/WRS2_descending.shp"),
    )
    parser.add_argument(
        "--mgrs-builder",
        type=Path,
        default=Path("scripts/data/national/build_mgrs_index.py"),
    )
    parser.add_argument(
        "--v0-wrs-index",
        type=Path,
        default=Path("work/national/footprints/wrs2_china_coast_index.csv"),
    )
    parser.add_argument(
        "--v0-mgrs-index",
        type=Path,
        default=Path("work/national/footprints/mgrs_china_coast_index.csv"),
    )
    parser.add_argument(
        "--out-dir", type=Path, default=Path("work/national/footprints")
    )
    parser.add_argument(
        "--tracked-doc",
        type=Path,
        default=Path("docs/data/national/FOOTPRINT_INDICES_v0_1.json"),
    )
    args = parser.parse_args()

    cells = load_cells(args.cells_csv)
    cell_union = cells.geometry.union_all()

    wrs_info, wrs_v01 = build_wrs(args.wrs_source, cell_union, args.out_dir)
    mgrs_info, mgrs_v01 = build_mgrs(
        args.cells_csv, cell_union, args.out_dir, args.mgrs_builder
    )

    v0_wrs = set(pd_read_col(args.v0_wrs_index, "frame_id"))
    v0_mgrs = set(pd_read_col(args.v0_mgrs_index, "mgrs_tile"))

    manifest = {
        "artifact": "footprint_indices",
        "version": "v0_1",
        "generated_utc": utc_now_iso(),
        "git_commit": _git_commit(),
        "audit": "M2.3b-R1 PART C / PART E",
        "supersedes": {
            "wrs2": "work/national/footprints/wrs2_china_coast_index.csv (v0)",
            "mgrs": "work/national/footprints/mgrs_china_coast_index.csv (v0)",
        },
        "derivation": (
            "frames/tiles kept iff polygon intersects the union of the "
            "3,319 retained W10 cell polygons; no hard-coded path/tile range"
        ),
        "wrs2": {
            **wrs_info,
            "v0_n_frames": len(v0_wrs),
            "frames_added_vs_v0": sorted(wrs_v01 - v0_wrs),
            "frames_dropped_vs_v0": sorted(v0_wrs - wrs_v01),
        },
        "mgrs": {
            **mgrs_info,
            "v0_n_tiles": len(v0_mgrs),
            "tiles_added_vs_v0": sorted(mgrs_v01 - v0_mgrs),
            "tiles_dropped_vs_v0": sorted(v0_mgrs - mgrs_v01),
        },
    }
    args.tracked_doc.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"WRS frames v0={len(v0_wrs)} v0_1={wrs_info['n_frames']} "
        f"added={len(wrs_v01 - v0_wrs)} dropped={len(v0_wrs - wrs_v01)}"
    )
    print(
        f"MGRS tiles v0={len(v0_mgrs)} v0_1={mgrs_info['n_tiles']} "
        f"added={len(mgrs_v01 - v0_mgrs)} dropped={len(v0_mgrs - mgrs_v01)}"
    )
    print(f"manifest -> {args.tracked_doc}")
    return 0


def pd_read_col(path: Path, col: str) -> list[str]:
    with path.open(newline="", encoding="utf-8") as handle:
        return [r[col] for r in csv.DictReader(handle)]


if __name__ == "__main__":
    sys.exit(main())
