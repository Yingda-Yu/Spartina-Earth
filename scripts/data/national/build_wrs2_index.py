#!/usr/bin/env python3
"""Build the WRS-2 descending footprint index for the China coastal domain.

Source: USGS WRS-2 descending path/row shapefile (public domain),
downloaded manually (metadata-only external fetch, not a GEE export):
https://d9-wret.s3.us-west-2.amazonaws.com/assets/palladium/production/s3fs-public/atoms/files/WRS2_descending_0.zip

Outputs (geometry bytes stay in ignored ``work/``; the tracked manifest
holds identifiers, bounds, fingerprints and checksums):

* ``work/national/footprints/wrs2_china_coast.gpkg`` - polygons clipped
  spatially to frames intersecting the domain corridor (Issue #16);
* ``work/national/footprints/wrs2_china_coast_index.csv`` - one row per
  path/row with geometry fingerprint and WGS84 bounds;
* tracked manifest passed via ``--tracked-doc``.

The index is a cheap *nominal* prefilter. It is valid for Landsat 5/8/9
and for Landsat 7 before the Extended Science Mission; L7 scenes after
2022-05-05 drift off WRS-2 and require actual scene geometry.
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

from spartina.data.national.footprints import (
    L7_EXTENDED_RESUME,
    L7_NOMINAL_END,
    L7_SLC_FAILURE,
    NOMINAL_WINDOWS,
    geometry_fingerprint,
    utc_now_iso,
    wrs2_frame_id,
)

USGS_WRS2_URL = (
    "https://d9-wret.s3.us-west-2.amazonaws.com/assets/"
    "palladium/production/s3fs-public/atoms/files/WRS2_descending_0.zip"
)


def _git_commit() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    )
    return proc.stdout.strip() if proc.returncode == 0 else "UNKNOWN"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-zip", type=Path, required=True)
    parser.add_argument("--corridor-gpkg", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--tracked-doc", type=Path, required=True)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    args.tracked_doc.parent.mkdir(parents=True, exist_ok=True)

    shp = args.source_zip.with_name("WRS2_descending.shp")
    if not shp.exists():
        raise SystemExit(
            f"extract {args.source_zip} next to itself first; missing {shp}"
        )

    frames = gpd.read_file(shp, engine="pyogrio")
    if str(frames.crs) != "EPSG:4326":
        raise ValueError(f"WRS source must be EPSG:4326, got {frames.crs}")
    corridor = gpd.read_file(args.corridor_gpkg, engine="pyogrio").to_crs("EPSG:4326")
    corridor_union = corridor.geometry.union_all()

    hits = gpd.sjoin(
        frames,
        gpd.GeoDataFrame(geometry=[corridor_union], crs="EPSG:4326"),
        how="inner",
        predicate="intersects",
    ).drop(columns=[c for c in ("index_right",) if c in frames.columns])
    hits = hits.drop_duplicates(subset=["PATH", "ROW"]).sort_values(["PATH", "ROW"])

    rows: list[dict[str, Any]] = []
    geoms = []
    for _, record in hits.iterrows():
        path, row = int(record["PATH"]), int(record["ROW"])
        geom = record.geometry
        bounds = geom.bounds  # (minx, miny, maxx, maxy)
        frame = {
            "frame_id": wrs2_frame_id(path, row),
            "path": path,
            "row": row,
            "wrs_mode": "D",
            "wrspr": str(record["WRSPR"]),
            "rings_ok": int(record["RINGS_OK"]),
            "rings_nok": int(record["RINGS_NOK"]),
            "acq_day_l7": None if record["ACQDayL7"] is None else int(record["ACQDayL7"]),
            "acq_day_l8": None if record["ACQDayL8"] is None else int(record["ACQDayL8"]),
            "geometry_kind": "NOMINAL_WRS2_DESCENDING_POLYGON",
            "geometry_sha256": geometry_fingerprint(geom),
            "minx": round(bounds[0], 7),
            "miny": round(bounds[1], 7),
            "maxx": round(bounds[2], 7),
            "maxy": round(bounds[3], 7),
            "valid_for_sensors": (
                "landsat5,landsat8,landsat9,"
                "l7_pre_slc_failure,l7_post_slc_failure"
            ),
            "not_valid_for": "landsat7_extended_science_mission_geometric_drift",
        }
        rows.append(frame)
        geoms.append(geom)

    fieldnames = list(rows[0].keys()) if rows else []
    csv_path = args.out_dir / "wrs2_china_coast_index.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    gpkg_path = args.out_dir / "wrs2_china_coast.gpkg"
    out = gpd.GeoDataFrame(rows, geometry=geoms, crs="EPSG:4326")
    out.drop(columns=[]).to_file(gpkg_path, driver="GPKG", engine="pyogrio")

    manifest = {
        "artifact": "wrs2_descending_footprint_index",
        "version": "v0",
        "generated_utc": utc_now_iso(),
        "git_commit": _git_commit(),
        "role": "nominal cheap spatial prefilter for Landsat cell joins",
        "source": {
            "publisher": "U.S. Geological Survey (USGS) Landsat Missions",
            "page": "https://www.usgs.gov/landsat-missions/landsat-shapefiles-and-kml-files",
            "download_url": USGS_WRS2_URL,
            "file": "WRS2_descending.zip",
            "zip_sha256": _sha256(args.source_zip),
            "license": "USGS Public Domain",
        },
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
            "l7_extended_science_mission_resume_utc": L7_EXTENDED_RESUME.isoformat(),
            "l7_extended_note": (
                "from 2022-05-05 L7 acquired at 697 km off the WRS-2 "
                "ground track; nominal polygons must not gate those scenes"
            ),
        },
        "corridor": str(args.corridor_gpkg),
        "n_frames_intersecting_corridor": len(rows),
        "paths": sorted({r["path"] for r in rows}),
        "rings_nok_frames": [r["frame_id"] for r in rows if r["rings_nok"] != 0],
        "outputs": {
            "index_csv": csv_path.name,
            "index_csv_sha256": _sha256(csv_path),
            "footprint_gpkg": gpkg_path.name,
            "footprint_gpkg_sha256": _sha256(gpkg_path),
        },
    }
    args.tracked_doc.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"frames={len(rows)} csv={csv_path} gpkg={gpkg_path}")
    print(f"manifest={args.tracked_doc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
