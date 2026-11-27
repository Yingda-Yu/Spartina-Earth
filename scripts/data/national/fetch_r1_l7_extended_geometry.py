#!/usr/bin/env python3
"""R1 Part D: fetch actual Landsat 7 Extended Science Mission footprints.

From 2022-05-05 Landsat 7 acquired from a lower (697 km) orbit off the
WRS-2 ground track, so nominal WRS-2 polygons must not gate those
scenes. The v0 census preserved the metadata rows but excluded them from
the cell join. This script retrieves their actual per-scene geometry
(metadata + geometry only; export guard installed), WITHOUT a
``WRS_PATH`` ``inList`` prefilter and with the full national-domain
bbox, so drifted paths are not silently dropped.

Window: 2022-05-05 .. 2026-01-01 (imaging was suspended 2024-01-19; the
tail is queried anyway so the absence of later scenes is an observed
fact, not an assumption). Year -> H1/H2 -> quarter splitting is applied
on getInfo failure; raw payloads are cached per scope.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import geopandas as gpd
import pandas as pd
from pyproj import CRS
from shapely.geometry import shape
from shapely.prepared import PreparedGeometry, prep

from spartina.data.gee.auth import initialize
from spartina.data.national.census_join import load_cells
from spartina.data.national.census_ledger import ResourceLedger
from spartina.data.national.footprints import (
    L7_EXTENDED_RESUME,
    geometry_fingerprint,
)
from spartina.data.national.grid import CHINA_ALBERS_PROJ4
from spartina.data.zhejiang.census import install_export_guard

L7_COLLECTION = "LANDSAT/LE07/C02/T1_L2"
DOMAIN_BBOX = (105.0, 15.0, 132.0, 43.0)
START_DATE = L7_EXTENDED_RESUME.isoformat()  # 2022-05-05
END_DATE = "2026-01-01"
GEOMETRY_SCALE_M = 1000.0
L7_KEYS = (
    "system:index",
    "LANDSAT_SCENE_ID",
    "LANDSAT_PRODUCT_ID",
    "SCENE_CENTER_TIME",
    "DATE_ACQUIRED",
    "WRS_PATH",
    "WRS_ROW",
    "CLOUD_COVER",
    "CLOUD_COVER_LAND",
)


def _git_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def load_corridor(path: Path) -> PreparedGeometry:
    gdf = gpd.read_file(path, engine="pyogrio")
    gdf = gdf.set_crs(CRS.from_proj4(CHINA_ALBERS_PROJ4), allow_override=True)
    gdf = gdf.to_crs("EPSG:4326")
    return prep(gdf.geometry.union_all())


def load_w10_union(cells_csv: Path) -> PreparedGeometry:
    cells = load_cells(cells_csv)
    return prep(cells.geometry.union_all())


def fetch_period(
    ee: Any, start_date: str, end_date: str, geom_scale: float
) -> dict[str, Any]:
    roi = ee.Geometry.Rectangle(list(DOMAIN_BBOX), "EPSG:4326", False)
    keys = list(L7_KEYS)
    collection = (
        ee.ImageCollection(L7_COLLECTION)
        .filterBounds(roi)
        .filterDate(start_date, end_date)
    )

    def _as_feature(image: Any) -> Any:
        return ee.Feature(image.geometry(geom_scale, "EPSG:4326"), image.toDictionary(keys))

    return cast(dict[str, Any], collection.map(_as_feature).getInfo())


def parse_features(
    features: list[dict[str, Any]],
    corridor: PreparedGeometry,
    w10: PreparedGeometry,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for feature in features:
        geojson = feature.get("geometry")
        props = feature.get("properties", {})
        if not isinstance(geojson, dict) or not isinstance(props, dict):
            continue
        if not isinstance(props.get("system:index"), str):
            feature_id = feature.get("id")
            if isinstance(feature_id, str) and feature_id:
                props["system:index"] = feature_id
        scene_id = props.get("LANDSAT_SCENE_ID") or props.get("system:index")
        if not isinstance(scene_id, str) or not scene_id:
            continue
        center = props.get("SCENE_CENTER_TIME")
        date_only = props.get("DATE_ACQUIRED")
        when: datetime | None = None
        if isinstance(center, str) and center:
            try:
                when = datetime.fromisoformat(center.replace("Z", "+00:00"))
            except ValueError:
                when = None
        if when is None and isinstance(date_only, str) and len(date_only) >= 10:
            when = datetime.fromisoformat(date_only[:10]).replace(tzinfo=UTC)
        if when is None or when.date() < L7_EXTENDED_RESUME:
            continue
        try:
            geom = shape(geojson)
        except (ValueError, TypeError):
            continue
        path = props.get("WRS_PATH")
        row = props.get("WRS_ROW")
        cloud = props.get("CLOUD_COVER")
        bounds = geom.bounds
        rows.append(
            {
                "scene_id": scene_id,
                "product_id": props.get("LANDSAT_PRODUCT_ID")
                if isinstance(props.get("LANDSAT_PRODUCT_ID"), str)
                else None,
                "utc": when.isoformat(),
                "year": when.year,
                "doy": when.timetuple().tm_yday,
                "wrs_path": int(path) if isinstance(path, int) else None,
                "wrs_row": int(row) if isinstance(row, int) else None,
                "cloud_cover": float(cloud)
                if isinstance(cloud, int | float)
                else None,
                "mission_phase": "OFF_NOMINAL_EXTENDED_MISSION",
                "default_production_eligible": False,
                "intersects_corridor_w10": bool(corridor.intersects(geom)),
                "intersects_w10_cells": bool(w10.intersects(geom)),
                "footprint_sha256": geometry_fingerprint(geom),
                "min_lon": round(bounds[0], 6),
                "min_lat": round(bounds[1], 6),
                "max_lon": round(bounds[2], 6),
                "max_lat": round(bounds[3], 6),
                "geometry_wkt": geom.wkt,
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=Path("work/national/census_r1"))
    parser.add_argument(
        "--corridor-gpkg",
        type=Path,
        default=Path("work/national/domain/corridor_W10000.gpkg"),
    )
    parser.add_argument(
        "--cells-csv",
        type=Path,
        default=Path("work/national/domain/cells_china_albers_W10000.csv"),
    )
    parser.add_argument("--attempts", type=int, default=4)
    parser.add_argument("--geom-scale", type=float, default=GEOMETRY_SCALE_M)
    args = parser.parse_args()

    initialize()
    import ee

    install_export_guard(ee)

    raw_dir = args.out_dir / "raw_l7_extended"
    raw_dir.mkdir(parents=True, exist_ok=True)

    ledger = ResourceLedger(
        run_id="l7extgeom-" + datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ"),
        git_commit=_git_commit(),
    )
    ledger.note("R1 PART D: L7 Extended Science Mission actual footprints")
    ledger.note(f"window={START_DATE}..{END_DATE} (exclusive end)")
    ledger.note(f"server bbox={DOMAIN_BBOX}; NO WRS_PATH inList prefilter")
    ledger.note("mission_phase=OFF_NOMINAL_EXTENDED_MISSION; not default-production eligible")

    corridor = load_corridor(args.corridor_gpkg)
    w10 = load_w10_union(args.cells_csv)

    def run_batch(scope: str, start_date: str, end_date: str) -> list[dict[str, Any]]:
        cache_path = raw_dir / f"{scope}.json"
        if cache_path.exists():
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            cached = payload.get("features", [])
            features = (
                [cast(dict[str, Any], f) for f in cached if isinstance(f, dict)]
                if isinstance(cached, list)
                else []
            )
            ledger.record_call(
                sensor="landsat7",
                call_kind="geometry_batch.cache",
                scope=scope,
                n_results=len(features),
                payload_bytes=len(cache_path.read_bytes()),
                duration_s=0.0,
                retries=0,
                ok=True,
            )
            return features
        attempt = 0
        while True:
            attempt += 1
            started = time.perf_counter()
            try:
                payload = fetch_period(ee, start_date, end_date, args.geom_scale)
                raw_features = payload.get("features", [])
                features = (
                    [
                        cast(dict[str, Any], f)
                        for f in raw_features
                        if isinstance(f, dict)
                    ]
                    if isinstance(raw_features, list)
                    else []
                )
                ledger.record_call(
                    sensor="landsat7",
                    call_kind="geometry_batch.getInfo",
                    scope=scope,
                    n_results=len(features),
                    payload_bytes=len(json.dumps(payload).encode("utf-8")),
                    duration_s=round(time.perf_counter() - started, 3),
                    retries=attempt - 1,
                    ok=True,
                )
                cache_path.write_text(
                    json.dumps(payload, ensure_ascii=False), encoding="utf-8"
                )
                return features
            except Exception as exc:  # noqa: BLE001 - logged, not swallowed
                if attempt >= args.attempts:
                    ledger.record_call(
                        sensor="landsat7",
                        call_kind="geometry_batch.getInfo",
                        scope=scope,
                        n_results=0,
                        payload_bytes=0,
                        duration_s=0.0,
                        retries=attempt - 1,
                        ok=False,
                        error=f"{type(exc).__name__}: {exc}"[:500],
                    )
                    raise
                time.sleep(2**attempt)

    def month_bounds(start_date: str, end_date: str) -> list[tuple[str, str]]:
        """First-of-month chunks covering [start_date, end_date)."""
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=UTC)
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=UTC)
        bounds: list[tuple[str, str]] = []
        cursor = start_dt.replace(day=1)
        while cursor < end_dt:
            nxt_year = cursor.year + (1 if cursor.month == 12 else 0)
            nxt_month = 1 if cursor.month == 12 else cursor.month + 1
            nxt = cursor.replace(month=nxt_month, year=nxt_year)
            chunk_start = max(cursor, start_dt)
            chunk_end = min(nxt, end_dt)
            bounds.append(
                (chunk_start.strftime("%Y-%m-%d"), chunk_end.strftime("%Y-%m-%d"))
            )
            cursor = nxt
        return bounds

    # Fixed small window; imaging suspended 2024-01-19, tail probed to 2026.
    periods = (
        ("2022ext", "2022-05-05", "2023-01-01"),
        ("2023H1", "2023-01-01", "2023-07-01"),
        ("2023H2", "2023-07-01", "2024-01-01"),
        ("2024H1", "2024-01-01", "2024-07-01"),
        ("2024H2", "2024-07-01", "2025-01-01"),
        ("2025", "2025-01-01", "2026-01-01"),
    )
    all_features: list[dict[str, Any]] = []
    for scope, start, end in periods:
        try:
            features = run_batch(scope, start, end)
        except Exception:
            ledger.note(f"BATCH_FAILED_SPLIT {scope} -> months")
            features = []
            for idx, (m_start, m_end) in enumerate(month_bounds(start, end)):
                features.extend(
                    run_batch(f"{scope}M{idx:02d}", m_start, m_end)
                )
        all_features.extend(features)
        print(f"{scope}: returned={len(features)}", flush=True)

    rows = parse_features(all_features, corridor, w10)
    deduped: dict[str, dict[str, Any]] = {}
    for row in rows:
        deduped.setdefault(str(row["scene_id"]), row)
    rows = list(deduped.values())

    args.out_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = args.out_dir / "l7_extended_geometry_v0_1.parquet"
    if rows:
        attributes = pd.DataFrame(rows).drop(columns=["geometry_wkt"])
        geom = gpd.GeoSeries.from_wkt(
            [str(r["geometry_wkt"]) for r in rows], crs="EPSG:4326"
        )
        gdf = gpd.GeoDataFrame(attributes, geometry=geom)
    else:
        gdf = gpd.GeoDataFrame(
            columns=["scene_id", "utc", "mission_phase", "geometry"],
            geometry=gpd.GeoSeries(crs="EPSG:4326"),
        )
    gdf.to_parquet(parquet_path, engine="pyarrow")
    ledger.note(f"unique_extended_scenes={len(rows)}")
    ledger.record_cache_file(parquet_path)
    ledger.write(args.out_dir / "resource_ledger_l7_extended_r1.json")
    print(f"l7 extended: rows={len(rows)} -> {parquet_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
