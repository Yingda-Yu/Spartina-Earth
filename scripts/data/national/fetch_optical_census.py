#!/usr/bin/env python3
"""Fetch national Landsat + Sentinel-2 scene metadata (Issue #16).

Architecture (forbidden: 3,319 x scenes getInfo):

* one batched ``reduceColumns(...).getInfo()`` per sensor x year over the
  corridor *bounding box* (tiny request geometry);
* precision is achieved entirely by the local static frame indices
  (66 WRS-2 frames, 128 MGRS tiles) and the cell polygons;
* full years are retrieved (no autumn-only query); season tags are
  applied locally;
* Landsat 7 scenes are tagged with the mission era (SLC failure and the
  2022 off-WRS-2 Extended Science Mission);
* Sentinel-2 rows are granules; no cross-date grouping happens here.

Outputs (ignored work cache): parquet scene tables; a resource ledger
records every call, payload size, retry, failure, runtime and peak RAM.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import time
from pathlib import Path
from typing import Any

import pandas as pd

from spartina.data.gee.auth import initialize
from spartina.data.national.census_ledger import ResourceLedger
from spartina.data.national.footprints import NOMINAL_WINDOWS
from spartina.data.national.scene_events import (
    landsat_scene_from_props,
    s2_granule_from_props,
)
from spartina.data.zhejiang.census import install_export_guard

# Bounding box used only as the server-side prefilter; final eligibility
# is the local frame/cell join. Generous around the mainland coast.
CORRIDOR_BBOX = (105.0, 15.0, 127.0, 43.0)  # minx, miny, maxx, maxy

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
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    )
    return proc.stdout.strip() if proc.returncode == 0 else "UNKNOWN"


def _reduce_year(
    ee: Any,
    collection_id: str,
    year: int,
    props: tuple[str, ...],
    frame_filter: tuple[str, tuple[object, ...]] | None,
) -> dict[str, list[Any]]:
    roi = ee.Geometry.Rectangle(list(CORRIDOR_BBOX), "EPSG:4326", False)
    collection = (
        ee.ImageCollection(collection_id)
        .filterBounds(roi)
        .filterDate(f"{year}-01-01", f"{year + 1}-01-01")
    )
    if frame_filter is not None:
        key, values = frame_filter
        collection = collection.filter(ee.Filter.inList(key, list(values)))
    columns = [collection.aggregate_array(q) for q in props]
    result: dict[str, list[Any]] = ee.Dictionary.fromLists(
        list(props), columns
    ).getInfo()
    return result


def _reduce_year_with_retry(
    ee: Any,
    ledger: ResourceLedger,
    sensor: str,
    collection_id: str,
    year: int,
    props: tuple[str, ...],
    attempts: int,
    frame_filter: tuple[str, tuple[object, ...]] | None,
) -> dict[str, list[Any]] | None:
    scope = f"{sensor}:{year}"
    for attempt in range(1, attempts + 1):
        started = time.perf_counter()
        try:
            payload = _reduce_year(
                ee, collection_id, year, props, frame_filter
            )
        except Exception as exc:  # noqa: BLE001 - logged as QUERY_FAILED
            duration = time.perf_counter() - started
            if attempt == attempts:
                ledger.record_call(
                    sensor=sensor,
                    call_kind="aggregate_arrays.getInfo",
                    scope=scope,
                    n_results=0,
                    payload_bytes=0,
                    duration_s=round(duration, 3),
                    retries=attempt - 1,
                    ok=False,
                    error=f"{type(exc).__name__}: {exc}"[:300],
                )
                return None
            time.sleep(min(2 ** attempt, 30))
            continue
        raw = json.dumps(payload, default=str).encode("utf-8")
        ledger.record_call(
            sensor=sensor,
            call_kind="aggregate_arrays.getInfo",
            scope=scope,
            n_results=len(payload.get(props[0], [])),
            payload_bytes=len(raw),
            duration_s=round(time.perf_counter() - started, 3),
            retries=attempt - 1,
        )
        return payload
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--sensors", nargs="*", default=list(OPTICAL_COLLECTIONS))
    parser.add_argument("--year-start", type=int, default=1984)
    parser.add_argument("--year-end", type=int, default=2025)
    parser.add_argument("--attempts", type=int, default=4)
    parser.add_argument(
        "--wrs-index",
        type=Path,
        default=Path("work/national/footprints/wrs2_china_coast_index.csv"),
    )
    parser.add_argument(
        "--mgrs-index",
        type=Path,
        default=Path("work/national/footprints/mgrs_china_coast_index.csv"),
    )
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    initialize()
    import ee

    restore = install_export_guard(ee)
    try:
        run_id = f"optical-census-{args.year_start}-{args.year_end}"
        ledger = ResourceLedger(run_id=run_id, git_commit=_git_commit())
        ledger.note("server prefilter=corridor bbox; precision via local frame index")
        ledger.note("full years retrieved; season tags applied locally")

        for sensor in args.sensors:
            if sensor not in OPTICAL_COLLECTIONS:
                raise ValueError(f"unknown sensor {sensor}")
            window = NOMINAL_WINDOWS[sensor]
            years = range(
                max(args.year_start, window.start.year),
                min(args.year_end, (window.end.year if window.end else args.year_end)) + 1,
            )
            props = S2_PROPS if sensor == "sentinel2" else LANDSAT_PROPS
            frame_filter: tuple[str, tuple[object, ...]] | None
            if sensor == "sentinel2":
                with args.mgrs_index.open(newline="", encoding="utf-8") as handle:
                    tiles = tuple(r["mgrs_tile"] for r in csv.DictReader(handle))
                frame_filter = ("MGRS_TILE", tuple(tiles))
            else:
                # C02 T1_L2 exposes no WRSPR property; restrict to the 12
                # WRS paths server-side, exact (path,row) enforced locally.
                with args.wrs_index.open(newline="", encoding="utf-8") as handle:
                    paths = sorted({int(r["path"]) for r in csv.DictReader(handle)})
                frame_filter = ("WRS_PATH", tuple(int(v) for v in paths))
            rows: list[dict[str, Any]] = []
            failures: list[str] = []
            if sensor == "sentinel2":
                with args.mgrs_index.open(newline="", encoding="utf-8") as handle:
                    allowed_tiles = {r["mgrs_tile"] for r in csv.DictReader(handle)}
            else:
                with args.wrs_index.open(newline="", encoding="utf-8") as handle:
                    allowed_frames = {
                        (int(r["path"]), int(r["row"]))
                        for r in csv.DictReader(handle)
                    }
            for year in years:
                payload = _reduce_year_with_retry(
                    ee, ledger, sensor, OPTICAL_COLLECTIONS[sensor], year,
                    props, args.attempts, frame_filter,
                )
                if payload is None:
                    failures.append(str(year))
                    continue
                columns = {p: list(payload.get(p, [])) for p in props}
                n = len(columns[props[0]])
                for i in range(n):
                    scene_props = {p: columns[p][i] if i < len(columns[p]) else None for p in props}
                    if sensor == "sentinel2":
                        granule = s2_granule_from_props(scene_props)
                        if granule is not None and granule.mgrs_tile in allowed_tiles:
                            rows.append(granule.to_row())
                    else:
                        scene = landsat_scene_from_props(sensor, scene_props)
                        if scene is not None and (scene.path, scene.row) in allowed_frames:
                            rows.append(scene.to_row())
            if failures:
                ledger.note(f"{sensor}: QUERY_FAILED years {failures}")
            frame = pd.DataFrame(rows)
            out_path = args.out_dir / f"scene_census_{sensor}_v0.parquet"
            frame.to_parquet(out_path, index=False)
            ledger.record_cache_file(out_path)
            print(f"{sensor}: rows={len(frame)} -> {out_path}")

        ledger_path = args.out_dir / "resource_ledger_optical_v0.json"
        ledger.write(ledger_path)
        print(f"ledger: {ledger_path}")
        print(json.dumps(ledger.totals(), indent=2))
    finally:
        restore()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
