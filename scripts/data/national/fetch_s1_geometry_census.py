"""Fetch Sentinel-1 GRD *actual* scene footprints for the national census.

Metadata-only, no pixel data and no ``ee.batch.Export`` (the export guard is
installed unconditionally). Unlike the optical collection census (one
``aggregate_array`` reduce per sensor-year), S1 cell coverage cannot be
judged from nominal frames alone: S1_GRD scenes carry individual
geocoded footprints. We therefore retrieve one geometry per scene, but in
batches: exactly one ``getInfo`` per (year, pass) chunk over the corridor
bbox server prefilter. ASCENDING and DESCENDING passes are always queried
in separate calls.

Outputs (all under the ignored ``work/`` tree; tracked companions are
checksums + run metadata, never the bytes):

* ``scene_census_sentinel1_v0.parquet`` -- one row per kept scene, with
  geometry, bounds, metadata and geometry SHA-256;
* ``resource_ledger_s1_v0.json`` -- every API call, retries, failures,
  payload bytes and wall time.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
from pyproj import CRS
from shapely.geometry import shape
from shapely.prepared import prep

from spartina.data.gee.auth import initialize
from spartina.data.national.census_ledger import ResourceLedger
from spartina.data.national.footprints import geometry_fingerprint
from spartina.data.national.grid import CHINA_ALBERS_PROJ4
from spartina.data.national.scene_events import s1_scene_from_props
from spartina.data.zhejiang.census import install_export_guard

S1_COLLECTION = "COPERNICUS/S1_GRD"
CORRIDOR_BBOX = (105.0, 15.0, 127.0, 43.0)
GEOMETRY_SCALE_M = 1000.0
PASS_FILTERS = (("ASC", "ASCENDING"), ("DESC", "DESCENDING"))
S1_KEYS = (
    "system:index",
    "system:time_start",
    "relativeOrbitNumber_start",
    "orbitNumber_start",
    "orbitProperties_pass",
    "platform_number",
    "instrumentMode",
    "transmitterReceiverPolarisation",
)


def _git_commit() -> str:
    import subprocess

    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def load_corridor(path: Path) -> Any:
    """Dissolved, prepared corridor union for local precision intersection."""
    gdf = gpd.read_file(path, engine="pyogrio")
    # The work-tree gpkg stores an unnamed Albers WKT that some GDAL builds
    # mis-parse as geographic; pin the canonical projection explicitly.
    gdf = gdf.set_crs(CRS.from_proj4(CHINA_ALBERS_PROJ4), allow_override=True)
    gdf = gdf.to_crs("EPSG:4326")
    return prep(gdf.geometry.union_all())


def fetch_period_pass(
    ee: Any,
    start_date: str,
    end_date: str,
    pass_value: str,
    geom_scale: float,
) -> dict[str, Any]:
    """One batched getInfo: every S1 scene in the bbox for period and pass."""
    roi = ee.Geometry.Rectangle(list(CORRIDOR_BBOX), "EPSG:4326", False)
    keys = list(S1_KEYS)
    collection = (
        ee.ImageCollection(S1_COLLECTION)
        .filterBounds(roi)
        .filterDate(start_date, end_date)
        .filter(ee.Filter.eq("orbitProperties_pass", pass_value))
    )

    def _as_feature(image: Any) -> Any:
        return ee.Feature(image.geometry(geom_scale), image.toDictionary(keys))

    result: dict[str, Any] = collection.map(_as_feature).getInfo()
    return result


def parse_features(
    features: list[dict[str, Any]], corridor: Any
) -> tuple[list[dict[str, Any]], int]:
    """Return (kept rows, parse failures) for one batch."""
    rows: list[dict[str, Any]] = []
    parse_failures = 0
    for feature in features:
        geojson = feature.get("geometry")
        props = feature.get("properties", {})
        if not isinstance(geojson, dict) or not isinstance(props, dict):
            parse_failures += 1
            continue
        # ee.Feature(geom, toDictionary(keys)) hoists system:index out of
        # properties and exposes it as the feature id.
        if not isinstance(props.get("system:index"), str):
            feature_id = feature.get("id")
            if isinstance(feature_id, str) and feature_id:
                props["system:index"] = feature_id
        try:
            geom = shape(geojson)
        except (ValueError, TypeError):
            parse_failures += 1
            continue
        if not corridor.intersects(geom):
            continue
        digest = geometry_fingerprint(geom)
        scene = s1_scene_from_props(props, digest)
        if scene is None:
            parse_failures += 1
            continue
        row = scene.to_manifest_row()
        minx, miny, maxx, maxy = geom.bounds
        row.update(
            {
                "min_lon": round(minx, 6),
                "min_lat": round(miny, 6),
                "max_lon": round(maxx, 6),
                "max_lat": round(maxy, 6),
                "geometry_wkt": geom.wkt,
            }
        )
        rows.append(row)
    return rows, parse_failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=Path("work/national/census"))
    parser.add_argument(
        "--corridor-gpkg",
        type=Path,
        default=Path("work/national/domain/corridor_W10000.gpkg"),
    )
    parser.add_argument("--year-start", type=int, default=2014)
    parser.add_argument("--year-end", type=int, default=2025)
    parser.add_argument("--attempts", type=int, default=4)
    parser.add_argument("--geom-scale", type=float, default=GEOMETRY_SCALE_M)
    args = parser.parse_args()

    import ee

    initialize()
    install_export_guard(ee)

    run_id = "s1geom-" + datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    ledger = ResourceLedger(run_id=run_id, git_commit=_git_commit())
    ledger.note("S1_GRD actual scene footprints, metadata+geometry only")
    ledger.note("server prefilter=corridor bbox; one getInfo per year x pass")
    ledger.note("ASC and DESC always separate calls")
    ledger.note(f"geometry(scale={args.geom_scale} m); local corridor intersect")

    corridor = load_corridor(args.corridor_gpkg)
    all_rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    total_parse_failures = 0

    def run_batch(
        scope: str, start_date: str, end_date: str, pass_value: str
    ) -> list[dict[str, Any]] | None:
        attempt = 0
        while attempt < args.attempts:
            attempt += 1
            try:
                started = time.perf_counter()
                payload = fetch_period_pass(
                    ee, start_date, end_date, pass_value, args.geom_scale
                )
                raw_features = payload.get("features", [])
                if not isinstance(raw_features, list):
                    raw_features = []
                features: list[dict[str, Any]] = [
                    f for f in raw_features if isinstance(f, dict)
                ]
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
                return features
            except Exception as exc:  # noqa: BLE001 - logged, not swallowed
                if attempt == args.attempts:
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
                    ledger.note(f"QUERY_FAILED {scope}: {type(exc).__name__}")
                    return None
                time.sleep(2**attempt)
        return None

    for year in range(args.year_start, args.year_end + 1):
        for pass_name, pass_value in PASS_FILTERS:
            scope = f"{year}-{pass_name}"
            features = run_batch(
                scope, f"{year}-01-01", f"{year + 1}-01-01", pass_value
            )
            # Peak S1A+S1B years can exceed the yearly getInfo limit:
            # retry the failed year as two half-year batches.
            if features is None:
                ledger.note(f"YEAR_BATCH_FAILED_SPLIT {scope} -> H1/H2")
                halves = (
                    (f"{year}H1-{pass_name}", f"{year}-01-01", f"{year}-07-01"),
                    (f"{year}H2-{pass_name}", f"{year}-07-01", f"{year + 1}-01-01"),
                )
                combined: list[dict[str, Any]] = []
                for half_scope, half_start, half_end in halves:
                    half_features = run_batch(
                        half_scope, half_start, half_end, pass_value
                    )
                    if half_features is None:
                        combined = []
                        break
                    combined.extend(half_features)
                features = combined
            if not features and any(
                c.scope.startswith(f"{year}") and not c.ok
                for c in ledger.calls
            ):
                continue
            rows, parse_failures = parse_features(features, corridor)
            added = 0
            for row in rows:
                scene_id = str(row["scene_id"])
                if scene_id in seen:
                    continue
                seen.add(scene_id)
                all_rows.append(row)
                added += 1
            total_parse_failures += parse_failures
            ledger.note(
                f"{scope}: returned={len(features)} kept_new={added} "
                f"parse_failures={parse_failures}"
            )
            print(f"{scope}: returned={len(features)} kept_new={added}", flush=True)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = args.out_dir / "scene_census_sentinel1_v0.parquet"
    if all_rows:
        attributes = pd.DataFrame(all_rows).drop(columns=["geometry_wkt"])
        geom = gpd.GeoSeries.from_wkt(
            [str(r["geometry_wkt"]) for r in all_rows], crs="EPSG:4326"
        )
        gdf = gpd.GeoDataFrame(attributes, geometry=geom)
    else:
        ledger.note("NO_SCENES_KEPT: parquet not written")
        gdf = gpd.GeoDataFrame(
            columns=[
                "event_id", "sensor", "scene_id", "utc", "year", "doy",
                "season_tag", "pass", "relative_orbit", "orbit_start",
                "platform", "polarization", "instrument_mode",
                "footprint_sha256", "min_lon", "min_lat", "max_lon",
                "max_lat", "geometry",
            ],
            geometry=gpd.GeoSeries(crs="EPSG:4326"),
        )
    gdf.to_parquet(parquet_path, engine="pyarrow")
    ledger.note(f"parse_failures_total={total_parse_failures}")
    ledger.note(f"unique_scenes={len(seen)}")
    ledger.record_cache_file(parquet_path)
    ledger_path = args.out_dir / "resource_ledger_s1_v0.json"
    ledger.write(ledger_path)
    print(f"sentinel1: rows={len(all_rows)} -> {parquet_path}")
    print(f"ledger: {ledger_path}")
    print(json.dumps(ledger.totals(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
