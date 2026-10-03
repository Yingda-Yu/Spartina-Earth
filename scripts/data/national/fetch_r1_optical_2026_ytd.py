#!/usr/bin/env python3
"""R1 Part A: fetch 2026 year-to-date optical metadata with a frozen cutoff.

Only year 2026 is queried, for Landsat 7/8/9 and Sentinel-2, over the
national-domain bbox (105,15,132,43). The server-side date window ends
at the frozen audit cutoff 2026-10-03T00:00:00Z (exclusive), and every
parsed row is locally asserted to be strictly before the cutoff.

To make the audit independent of the v0 frame prefilter (Part C tests
whether that index misses the NE cells), NO ``WRS_PATH`` / ``MGRS_TILE``
``inList`` server filter is applied: all bbox-intersecting scenes are
cached with an ``in_v0_index`` flag. The v0_1 build selects production
scenes through the (possibly extended) v0_1 footprint indices.

Landsat 5 is NOT queried: it is marked SENSOR_NOT_OPERATIONAL in the
ledger and a marker file, which is semantically distinct from "zero
scenes in 2026". Metadata-only; export guard installed.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pandas as pd

from spartina.data.gee.auth import initialize
from spartina.data.national.census_ledger import ResourceLedger
from spartina.data.national.scene_events import (
    landsat_scene_from_props,
    s2_granule_from_props,
)
from spartina.data.zhejiang.census import install_export_guard

DOMAIN_BBOX = (105.0, 15.0, 132.0, 43.0)
YEAR = 2026
CUTOFF_UTC = "2026-10-03T00:00:00Z"
CUTOFF_DT = datetime(2026, 10, 3, tzinfo=UTC)

OPTICAL_COLLECTIONS: dict[str, str] = {
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=Path("work/national/census_r1"))
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
        ledger = ResourceLedger(
            run_id="optical-2026ytd-r1", git_commit=_git_commit()
        )
        ledger.note(f"R1 PART A: optical metadata {YEAR} YTD only")
        ledger.note(f"frozen cutoff={CUTOFF_UTC} (exclusive server end)")
        ledger.note(f"server bbox={DOMAIN_BBOX}; NO frame inList prefilter")
        ledger.note("in_v0_index flag preserved; v0_1 build applies v0_1 index")

        # Landsat 5: operational 1984-03..2013-06; never queried for 2026.
        ledger.record_call(
            sensor="landsat5",
            call_kind="not_queried_sensor_not_operational",
            scope="landsat5:2026",
            n_results=0,
            payload_bytes=0,
            duration_s=0.0,
            retries=0,
            ok=True,
        )
        (args.out_dir / "landsat5_2026_status.json").write_text(
            json.dumps(
                {
                    "sensor": "landsat5",
                    "year": YEAR,
                    "status": "SENSOR_NOT_OPERATIONAL",
                    "queried": False,
                    "note": "Landsat 5 mission ended 2013-06-05; not zero scenes",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        with args.wrs_index.open(newline="", encoding="utf-8") as handle:
            v0_frames = {
                (int(r["path"]), int(r["row"])) for r in csv.DictReader(handle)
            }
        with args.mgrs_index.open(newline="", encoding="utf-8") as handle:
            v0_tiles = {r["mgrs_tile"] for r in csv.DictReader(handle)}

        roi = ee.Geometry.Rectangle(list(DOMAIN_BBOX), "EPSG:4326", False)

        for sensor, collection_id in OPTICAL_COLLECTIONS.items():
            props = S2_PROPS if sensor == "sentinel2" else LANDSAT_PROPS
            scope = f"{sensor}:{YEAR}"
            payload: dict[str, Any] | None = None
            for attempt in range(1, args.attempts + 1):
                started = time.perf_counter()
                try:
                    collection = (
                        ee.ImageCollection(collection_id)
                        .filterBounds(roi)
                        .filterDate(f"{YEAR}-01-01", "2026-10-03")
                    )
                    columns = [collection.aggregate_array(q) for q in props]
                    payload = cast(
                        dict[str, Any],
                        ee.Dictionary.fromLists(
                            list(props), columns
                        ).getInfo(),
                    )
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
                    break
                except Exception as exc:  # noqa: BLE001 - logged, not swallowed
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
            assert payload is not None

            # Raw cache for full traceability / future index extraction.
            (args.out_dir / f"raw_optical_{sensor}_2026ytd.json").write_text(
                json.dumps(payload, default=str, ensure_ascii=False),
                encoding="utf-8",
            )

            prop_columns = {p: list(payload.get(p, [])) for p in props}
            n = len(prop_columns[props[0]])
            rows: list[dict[str, Any]] = []
            n_after_cutoff = 0
            for i in range(n):
                scene_props = {
                    p: prop_columns[p][i]
                    if i < len(prop_columns[p])
                    else None
                    for p in props
                }
                if sensor == "sentinel2":
                    granule = s2_granule_from_props(scene_props)
                    if granule is None:
                        continue
                    if granule.utc >= CUTOFF_DT:
                        n_after_cutoff += 1
                        continue
                    row = granule.to_row()
                    row["in_v0_index"] = granule.mgrs_tile in v0_tiles
                else:
                    scene = landsat_scene_from_props(sensor, scene_props)
                    if scene is None:
                        continue
                    if scene.utc >= CUTOFF_DT:
                        n_after_cutoff += 1
                        continue
                    row = scene.to_row()
                    row["in_v0_index"] = (scene.path, scene.row) in v0_frames
                row["year_status"] = "PARTIAL_YEAR"
                row["census_cutoff_utc"] = CUTOFF_UTC
                rows.append(row)

            frame = pd.DataFrame(rows)
            out_path = (
                args.out_dir / f"scene_census_{sensor}_2026ytd_v0_1.parquet"
            )
            frame.to_parquet(out_path, index=False)
            ledger.record_cache_file(out_path)
            in_index = int(frame["in_v0_index"].sum()) if len(frame) else 0
            ledger.note(
                f"{sensor}: bbox_rows={len(frame)} in_v0_index={in_index} "
                f"after_cutoff_dropped={n_after_cutoff}"
            )
            print(
                f"{sensor}: bbox_rows={len(frame)} in_v0_index={in_index} "
                f"dropped_ge_cutoff={n_after_cutoff}",
                flush=True,
            )

        ledger_path = args.out_dir / "resource_ledger_optical_2026ytd_r1.json"
        ledger.write(ledger_path)
        print(f"ledger: {ledger_path}")
        print(json.dumps(ledger.totals(), indent=2))
    finally:
        restore()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
