#!/usr/bin/env python3
"""R1 Parts C/E: fetch ONLY the v0 prefilter-affected historical ranges.

The v0 optical census used server bbox (105,15,127,43) plus a v0 frame
``inList``; two domain regions were therefore never observed:

1. the 23 far-NE cells (130.4-131.2 E) -- direct filterBounds evidence in
   ``NE_CHRONIC_ZERO_AUDIT_v0``;
2. cells served by the 5 WRS-2 frames and 13 MGRS tiles added in
   ``FOOTPRINT_INDICES_v0_1`` (new rows on already-queried paths/tiles
   were dropped by the v0 local frame filter).

This script retrieves exactly those ranges over each sensor's nominal
operational years through 2025 (2026 comes from the YTD fetcher; L7
extended scenes from the geometry fetcher) and keeps only NEW scene ids
absent from the v0 caches, filtered through the v0_1 frame/tile index.
Metadata-only; export guard installed; raw per-year JSON is cached.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd
from shapely.geometry import mapping

from spartina.data.gee.auth import initialize
from spartina.data.national.census_join import load_cells
from spartina.data.national.census_ledger import ResourceLedger
from spartina.data.national.footprints import (
    L7_EXTENDED_RESUME,
    NOMINAL_WINDOWS,
)
from spartina.data.national.scene_events import (
    landsat_scene_from_props,
    s2_granule_from_props,
)
from spartina.data.zhejiang.census import install_export_guard

DOMAIN_BBOX = (105.0, 15.0, 132.0, 43.0)

OPTICAL_COLLECTIONS: dict[str, str] = {
    "landsat5": "LANDSAT/LT05/C02/T1_L2",
    "landsat7": "LANDSAT/LE07/C02/T1_L2",
    "landsat8": "LANDSAT/LC08/C02/T1_L2",
    "landsat9": "LANDSAT/LC09/C02/T1_L2",
    "sentinel2": "COPERNICUS/S2_SR_HARMONIZED",
}
LANDSAT_PROPS = (
    "LANDSAT_SCENE_ID",
    "LANDSAT_PRODUCT_ID",
    "SCENE_CENTER_TIME",
    "DATE_ACQUIRED",
    "WRS_PATH",
    "WRS_ROW",
    "CLOUD_COVER",
    "CLOUD_COVER_LAND",
)
S2_PROPS = (
    "system:index",
    "PRODUCT_ID",
    "DATATAKE_IDENTIFIER",
    "MGRS_TILE",
    "SPACECRAFT_NAME",
    "system:time_start",
    "CLOUDY_PIXEL_PERCENTAGE",
    "CLOUDY_PIXEL_OVER_LAND_PERCENTAGE",
)


def _git_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--r1-dir", type=Path, default=Path("work/national/census_r1")
    )
    parser.add_argument(
        "--v0-dir", type=Path, default=Path("work/national/census")
    )
    parser.add_argument(
        "--cells-csv",
        type=Path,
        default=Path("work/national/domain/cells_china_albers_W10000.csv"),
    )
    parser.add_argument(
        "--ne-cells-csv",
        type=Path,
        default=Path("datasets/manifests/china_ne_chronic_zero_audit_v0.csv"),
    )
    parser.add_argument(
        "--wrs-v01-index",
        type=Path,
        default=Path("work/national/footprints/wrs2_china_coast_v0_1_index.csv"),
    )
    parser.add_argument(
        "--wrs-v0-index",
        type=Path,
        default=Path("work/national/footprints/wrs2_china_coast_index.csv"),
    )
    parser.add_argument(
        "--mgrs-v01-index",
        type=Path,
        default=Path("work/national/footprints/mgrs_china_coast_v0_1_index.csv"),
    )
    parser.add_argument(
        "--mgrs-v0-index",
        type=Path,
        default=Path("work/national/footprints/mgrs_china_coast_index.csv"),
    )
    parser.add_argument("--attempts", type=int, default=4)
    args = parser.parse_args()

    out_dir = args.r1_dir / "incremental"
    raw_dir = out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    with args.wrs_v01_index.open(newline="", encoding="utf-8") as handle:
        wrs_v01 = {
            (int(r["path"]), int(r["row"])) for r in csv.DictReader(handle)
        }
    with args.wrs_v0_index.open(newline="", encoding="utf-8") as handle:
        wrs_v0 = {
            (int(r["path"]), int(r["row"])) for r in csv.DictReader(handle)
        }
    added_frames = wrs_v01 - wrs_v0
    added_paths = sorted({p for p, _ in added_frames})
    with args.mgrs_v01_index.open(newline="", encoding="utf-8") as handle:
        mgrs_v01 = {r["mgrs_tile"] for r in csv.DictReader(handle)}
    with args.mgrs_v0_index.open(newline="", encoding="utf-8") as handle:
        mgrs_v0 = {r["mgrs_tile"] for r in csv.DictReader(handle)}
    added_tiles = sorted(mgrs_v01 - mgrs_v0)

    ne_ids = set(pd.read_csv(args.ne_cells_csv)["cell_id"].astype(str))
    cells = load_cells(args.cells_csv)
    ne_union = (
        cells[cells["cell_id"].isin(ne_ids)].geometry.union_all()
    )

    initialize()
    import ee

    install_export_guard(ee)
    roi_bbox = ee.Geometry.Rectangle(list(DOMAIN_BBOX), "EPSG:4326", False)
    ne_geom = ee.Geometry(mapping(ne_union))

    ledger = ResourceLedger(
        run_id="affected-ranges-r1", git_commit=_git_commit()
    )
    ledger.note("R1 PARTS C/E: incremental metadata for v0-affected ranges")
    ledger.note(f"NE cells={len(ne_ids)}; added WRS frames={sorted(added_frames)}")
    ledger.note(f"added MGRS tiles={added_tiles}")
    ledger.note("server OR filter: bounds(NE union) OR inList(added paths/tiles)")

    for sensor, collection_id in OPTICAL_COLLECTIONS.items():
        v0_path = args.v0_dir / f"scene_census_{sensor}_v0.parquet"
        v0_ids: set[str] = set()
        if v0_path.exists():
            old = pd.read_parquet(v0_path)
            id_col = "system_index" if sensor == "sentinel2" else "scene_id"
            v0_ids = set(old[id_col].astype(str))
        props = S2_PROPS if sensor == "sentinel2" else LANDSAT_PROPS
        window = NOMINAL_WINDOWS[sensor]
        year_start = window.start.year
        year_end = min(2025, window.end.year if window.end else 2025)
        if sensor == "landsat7":
            year_end = 2022  # nominal only; extended handled by geometry fetch
        new_rows: list[dict[str, Any]] = []
        for year in range(year_start, year_end + 1):
            scope = f"{sensor}:{year}"
            cache_path = raw_dir / f"{scope.replace(':', '_')}.json"
            if cache_path.exists():
                payload = json.loads(cache_path.read_text(encoding="utf-8"))
            else:
                collection = (
                    ee.ImageCollection(collection_id)
                    .filterBounds(roi_bbox)
                    .filterDate(f"{year}-01-01", f"{year + 1}-01-01")
                )
                if sensor == "sentinel2":
                    scope_filter = ee.Filter.Or(
                        ee.Filter.bounds(ne_geom),
                        ee.Filter.inList("MGRS_TILE", added_tiles),
                    )
                else:
                    scope_filter = ee.Filter.Or(
                        ee.Filter.bounds(ne_geom),
                        ee.Filter.inList("WRS_PATH", added_paths),
                    )
                collection = collection.filter(scope_filter)
                payload = None
                for attempt in range(1, args.attempts + 1):
                    started = time.perf_counter()
                    try:
                        columns = [
                            collection.aggregate_array(q) for q in props
                        ]
                        payload = ee.Dictionary.fromLists(
                            list(props), columns
                        ).getInfo()
                        ledger.record_call(
                            sensor=sensor,
                            call_kind="aggregate_arrays.getInfo",
                            scope=scope,
                            n_results=len(payload.get(props[0], [])),
                            payload_bytes=len(
                                json.dumps(payload, default=str).encode()
                            ),
                            duration_s=round(time.perf_counter() - started, 3),
                            retries=attempt - 1,
                        )
                        break
                    except Exception as exc:  # noqa: BLE001
                        if attempt == args.attempts:
                            ledger.record_call(
                                sensor=sensor,
                                call_kind="aggregate_arrays.getInfo",
                                scope=scope,
                                n_results=0,
                                payload_bytes=0,
                                duration_s=0.0,
                                retries=attempt - 1,
                                ok=False,
                                error=f"{type(exc).__name__}: {exc}"[:300],
                            )
                            raise
                        time.sleep(min(2**attempt, 30))
                cache_path.write_text(
                    json.dumps(payload, default=str, ensure_ascii=False),
                    encoding="utf-8",
                )
            prop_columns = {p: list(payload.get(p, [])) for p in props}
            n = len(prop_columns[props[0]])
            kept = 0
            for i in range(n):
                scene_props = {
                    p: prop_columns[p][i]
                    if i < len(prop_columns[p])
                    else None
                    for p in props
                }
                if sensor == "sentinel2":
                    granule = s2_granule_from_props(scene_props)
                    if granule is None or granule.mgrs_tile not in mgrs_v01:
                        continue
                    if granule.system_index in v0_ids:
                        continue
                    row = granule.to_row()
                else:
                    scene = landsat_scene_from_props(sensor, scene_props)
                    if scene is None or (scene.path, scene.row) not in wrs_v01:
                        continue
                    if sensor == "landsat7" and scene.utc.date() >= L7_EXTENDED_RESUME:
                        continue  # nominal query; extended uses native geometry
                    if scene.scene_id in v0_ids:
                        continue
                    row = scene.to_row()
                row["year_status"] = "FULL_YEAR"
                row["census_cutoff_utc"] = None
                new_rows.append(row)
                kept += 1
            print(f"{scope}: returned={n} kept_new={kept}", flush=True)

        frame = pd.DataFrame(new_rows)
        out_path = out_dir / f"scene_census_{sensor}_incremental_v0_1.parquet"
        frame.to_parquet(out_path, index=False)
        ledger.record_cache_file(out_path)
        ledger.note(f"{sensor}: new_scenes={len(frame)}")

    ledger.write(out_dir / "resource_ledger_incremental_r1.json")
    print(f"-> {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
