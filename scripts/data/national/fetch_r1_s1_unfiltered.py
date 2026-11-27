"""R1 audit fetch: Sentinel-1 GRD scenes WITHOUT the orbit-pass filter.

M2.3b-R1 Part B evidence engine. The v0 census queried ASCENDING and
DESCENDING in separate calls over bbox (105,15,127,43) and the cached
rows are 100% ASCENDING; this audit fetch removes the pass filter, uses
the full national-domain bbox (105,15,132,43 -- the same domain extent
used when the W10 corridor was built), retrieves every scene footprint
with its pass property, and preserves non-IW modes and non-VV|VH
polarizations so the raw funnel A->F can be counted without loss.

Metadata + geometry only; no pixel data and no ``ee.batch.Export`` (the
export guard is installed unconditionally).

Years 2014..2026 are fetched. 2026 is a PARTIAL_YEAR bounded by the
frozen cutoff 2026-10-03T00:00:00Z: the server-side filterDate end is the
cutoff itself. Raw batch payloads are cached per scope under
``raw_s1_unfiltered/`` so reruns of the audit never re-query GEE.
"""

from __future__ import annotations

import argparse
import json
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
from spartina.data.national.footprints import geometry_fingerprint
from spartina.data.national.grid import CHINA_ALBERS_PROJ4
from spartina.data.zhejiang.census import install_export_guard

S1_COLLECTION = "COPERNICUS/S1_GRD"
DOMAIN_BBOX = (105.0, 15.0, 132.0, 43.0)
CUTOFF_UTC = "2026-10-03T00:00:00Z"
GEOMETRY_SCALE_M = 1000.0
S1_KEYS = (
    "system:index",
    "system:time_start",
    "relativeOrbitNumber_start",
    "orbitNumber_start",
    "orbitProperties_pass",
    "platform_number",
    "instrumentMode",
    "transmitterReceiverPolarisation",
    "resolution_meters",
    "productType",
)


def _git_commit() -> str:
    import subprocess

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
    """One batched getInfo: every S1 scene (both passes) in the bbox."""
    roi = ee.Geometry.Rectangle(list(DOMAIN_BBOX), "EPSG:4326", False)
    keys = list(S1_KEYS)
    collection = (
        ee.ImageCollection(S1_COLLECTION)
        .filterBounds(roi)
        .filterDate(start_date, end_date)
    )

    def _as_feature(image: Any) -> Any:
        return ee.Feature(image.geometry(geom_scale), image.toDictionary(keys))

    return cast(dict[str, Any], collection.map(_as_feature).getInfo())


def parse_features(
    features: list[dict[str, Any]],
    corridor: PreparedGeometry,
    w10: PreparedGeometry,
) -> list[dict[str, Any]]:
    """Permissive parse: keep every mode/pass/pol so funnel A is complete."""
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
        scene_id = props.get("system:index")
        ts = props.get("system:time_start")
        if not isinstance(scene_id, str) or not isinstance(ts, int | float):
            continue
        try:
            geom = shape(geojson)
        except (ValueError, TypeError):
            continue
        when = datetime.fromtimestamp(float(ts) / 1000.0, tz=UTC)
        if when > datetime(2026, 10, 3, tzinfo=UTC):
            # Defense in depth: server filterDate already bounds this.
            continue
        pass_value = props.get("orbitProperties_pass")
        pass_name = (
            "ASC" if pass_value == "ASCENDING"
            else "DESC" if pass_value == "DESCENDING"
            else "UNKNOWN"
        )
        platform_number = props.get("platform_number")
        pol = props.get("transmitterReceiverPolarisation")
        rel_orbit = props.get("relativeOrbitNumber_start")
        orbit = props.get("orbitNumber_start")
        resolution = props.get("resolution_meters")
        centroid = geom.centroid
        bounds = geom.bounds
        rows.append(
            {
                "scene_id": scene_id,
                "utc": when.isoformat(),
                "year": when.year,
                "doy": when.timetuple().tm_yday,
                "pass": pass_name,
                "platform_number": (
                    platform_number
                    if isinstance(platform_number, str)
                    else "UNKNOWN"
                ),
                "instrument_mode": (
                    props["instrumentMode"]
                    if isinstance(props.get("instrumentMode"), str)
                    else "UNKNOWN"
                ),
                "polarization": "|".join(pol)
                if isinstance(pol, list) and all(isinstance(v, str) for v in pol)
                else "UNKNOWN",
                "relative_orbit": int(rel_orbit)
                if isinstance(rel_orbit, int) and not isinstance(rel_orbit, bool)
                else None,
                "orbit_start": int(orbit)
                if isinstance(orbit, int) and not isinstance(orbit, bool)
                else None,
                "resolution_m": float(resolution)
                if isinstance(resolution, int | float)
                and not isinstance(resolution, bool)
                else None,
                "product_type": props.get("productType")
                if isinstance(props.get("productType"), str)
                else None,
                "intersects_corridor_w10": bool(corridor.intersects(geom)),
                "intersects_w10_cells": bool(w10.intersects(geom)),
                "footprint_sha256": geometry_fingerprint(geom),
                "centroid_lon": round(centroid.x, 6),
                "centroid_lat": round(centroid.y, 6),
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
    parser.add_argument("--year-start", type=int, default=2014)
    parser.add_argument("--year-end", type=int, default=2026)
    parser.add_argument("--attempts", type=int, default=4)
    parser.add_argument("--geom-scale", type=float, default=GEOMETRY_SCALE_M)
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="re-query scopes even when a raw JSON cache exists",
    )
    args = parser.parse_args()

    import ee

    initialize()
    install_export_guard(ee)

    raw_dir = args.out_dir / "raw_s1_unfiltered"
    raw_dir.mkdir(parents=True, exist_ok=True)

    run_id = "s1r1unf-" + datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    ledger = ResourceLedger(run_id=run_id, git_commit=_git_commit())
    ledger.note("R1 PART B: S1_GRD UNFILTERED pass audit (no pass eq filter)")
    ledger.note(f"server bbox={DOMAIN_BBOX} (national domain extent)")
    ledger.note(f"2026 PARTIAL_YEAR cutoff={CUTOFF_UTC}")
    ledger.note("year->H1/H2->quarter split on getInfo failure")
    ledger.note("raw payload cached per scope; permissive parse keeps all modes/pols")

    corridor = load_corridor(args.corridor_gpkg)
    w10 = load_w10_union(args.cells_csv)

    def run_batch(scope: str, start_date: str, end_date: str) -> list[dict[str, Any]]:
        cache_path = raw_dir / f"{scope}.json"
        if cache_path.exists() and not args.refresh:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            cached = payload.get("features", [])
            features = (
                [cast(dict[str, Any], f) for f in cached if isinstance(f, dict)]
                if isinstance(cached, list)
                else []
            )
            ledger.record_call(
                sensor="sentinel1",
                call_kind="geometry_batch.cache",
                scope=scope,
                n_results=len(features),
                payload_bytes=len(cache_path.read_bytes()),
                duration_s=0.0,
                retries=0,
                ok=True,
            )
            return [f for f in features if isinstance(f, dict)]
        attempt = 0
        while True:
            attempt += 1
            try:
                started = time.perf_counter()
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
                    sensor="sentinel1",
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
                        sensor="sentinel1",
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

    def quarter_scopes(year: int, half: str, year_end: str) -> list[tuple[str, str, str]]:
        if half == "H1":
            quarters = (
                ("Q1", "-01-01", "-04-01"),
                ("Q2", "-04-01", "-07-01"),
            )
        else:
            quarters = (
                ("Q3", "-07-01", "-10-01"),
                ("Q4", "-10-01", "-01-01"),
            )
        result: list[tuple[str, str, str]] = []
        for quarter, m_start, m_end in quarters:
            q_end = year_end if half == "H2" and quarter == "Q4" else f"{year}{m_end}"
            result.append((f"{year}{quarter}", f"{year}{m_start}", q_end))
        return result

    all_features: list[dict[str, Any]] = []
    for year in range(args.year_start, args.year_end + 1):
        year_end = "2026-10-03" if year == args.year_end else f"{year + 1}-01-01"
        scope, start, end = str(year), f"{year}-01-01", year_end
        try:
            features = run_batch(scope, start, end)
        except Exception:
            ledger.note(f"YEAR_BATCH_FAILED_SPLIT {scope} -> H1/H2")
            halves = (
                ("H1", f"{year}-01-01", f"{year}-07-01"),
                ("H2", f"{year}-07-01", year_end),
            )
            features = []
            for half, half_start, half_end in halves:
                half_scope = f"{year}{half}"
                try:
                    features.extend(run_batch(half_scope, half_start, half_end))
                except Exception:
                    ledger.note(
                        f"HALF_BATCH_FAILED_SPLIT {half_scope} -> quarters"
                    )
                    for q_scope, q_start, q_end in quarter_scopes(
                        year, half, year_end
                    ):
                        features.extend(run_batch(q_scope, q_start, q_end))
        all_features.extend(features)
        print(f"{year}: returned={len(features)}", flush=True)

    rows = parse_features(all_features, corridor, w10)
    # De-duplicate by scene_id (split batches can overlap on date boundaries).
    deduped: dict[str, dict[str, Any]] = {}
    for row in rows:
        deduped.setdefault(str(row["scene_id"]), row)
    rows = list(deduped.values())

    args.out_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = args.out_dir / "s1_grd_unfiltered_v0_1.parquet"
    if rows:
        attributes = pd.DataFrame(rows).drop(columns=["geometry_wkt"])
        geom = gpd.GeoSeries.from_wkt(
            [str(r["geometry_wkt"]) for r in rows], crs="EPSG:4326"
        )
        gdf = gpd.GeoDataFrame(attributes, geometry=geom)
    else:
        gdf = gpd.GeoDataFrame(
            columns=["scene_id", "utc", "year", "pass", "geometry"],
            geometry=gpd.GeoSeries(crs="EPSG:4326"),
        )
    gdf.to_parquet(parquet_path, engine="pyarrow")
    ledger.note(f"unique_scenes={len(rows)}")
    ledger.record_cache_file(parquet_path)
    ledger_path = args.out_dir / "resource_ledger_s1_r1_unfiltered.json"
    ledger.write(ledger_path)
    print(f"sentinel1 unfiltered: rows={len(rows)} -> {parquet_path}")
    print(f"ledger: {ledger_path}")
    print(json.dumps(ledger.totals(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
