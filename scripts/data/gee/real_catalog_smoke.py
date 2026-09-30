#!/usr/bin/env python
"""Real Earth Engine catalog smoke for one small Hangzhou Bay ROI.

Issue #6 integration gate (metadata only -- this script never exports
pixels). It runs real L8 / S1 / S2 queries over a narrow, data-rich
seasonal window, computes ROI-level raster quality fractions inside EE,
retains EVERY candidate scene (selected scene is explicit), and writes:

    artifacts/gee/candidate_scenes_<UTC>.parquet
    artifacts/gee/candidate_scenes_<UTC>.json
    artifacts/gee/selected_scenes_<UTC>.json

Run with real credentials and a project:

    export SPARTINA_GEE_PROJECT=<your-gcp-project-with-ee-enabled>
    earthengine authenticate
    python scripts/data/gee/real_catalog_smoke.py

The tiny box is a *technical smoke ROI*, not an authoritative Hangzhou
Bay boundary (see docs/data/ZHEJIANG_DATA_PREPARATION_V0.md).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

from spartina.data.gee import pixelqa  # noqa: E402
from spartina.data.gee.auth import PROJECT_ENV_VAR, configured_project, initialize  # noqa: E402
from spartina.data.gee.catalog import (  # noqa: E402
    EarthEngineCatalogClient,
    Region,
    SceneQuery,
)
from spartina.data.gee.quality import (  # noqa: E402
    CloudCoverFilter,
    apply_filters,
    build_candidate_table,
    candidate_records,
)
from spartina.data.gee.selection import (  # noqa: E402
    SingleScenePolicy,
    best_single_scene,
    rejection_reasons,
)

# 0.02-degree technical smoke box on the northern Hangzhou Bay coast
# (EPSG:4326); UTM 51N for fixed grids. NOT a bay boundary.
HZ_SMOKE_BOX: Region = Region(
    geometry={
        "type": "Polygon",
        "coordinates": [[
            [121.10, 30.30], [121.12, 30.30], [121.12, 30.32],
            [121.10, 30.32], [121.10, 30.30]]],
    },
    crs_epsg=4326,
)

# Sensor -> (native pixel m, science stream grid name)
SENSOR_GRID: dict[str, tuple[float, str]] = {
    "landsat8": (30.0, "landsat_30m"),
    "sentinel2": (10.0, "sentinel_10m"),
    "sentinel1": (10.0, "sentinel_10m"),
}

# Column order required by the Issue #6 candidate-scene table contract.
CANDIDATE_COLUMNS: tuple[str, ...] = (
    "scene_id", "product_id", "sensor", "acquisition_utc",
    "wrs_path", "wrs_row", "mgrs_tile",
    "orbit_direction", "relative_orbit_number", "polarizations",
    "cloud_cover_fraction", "roi_cloud_fraction",
    "valid_pixel_fraction", "clear_pixel_fraction",
    "footprint_coverage_fraction",
    "native_resolution_m", "grid",
    "accepted", "policy_eligible", "selected",
    "rejection_reasons",
)

DEFAULT_START = "2020-09-01"
DEFAULT_END = "2020-10-31"
DEFAULT_TARGET_DOY = 275  # 1 October, autumn Spartina window (planning v0)
DEFAULT_MAX_CATALOG_CLOUD = 0.80


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")  # noqa: UP017


def _ee_geometry(ee: Any, region: Region) -> Any:
    return ee.Geometry(region.geometry, f"EPSG:{region.crs_epsg}", False)


def _raw_collection(ee: Any, sensor: str, roi: Any,
                    start: str, end: str) -> Any:
    if sensor == "landsat8":
        from spartina.data.gee import landsat
        return landsat.load_collection(
            ee, "landsat8", roi, start, end,
            max_cloud_cover=DEFAULT_MAX_CATALOG_CLOUD)
    if sensor == "sentinel2":
        from spartina.data.gee import sentinel2
        return sentinel2.load_collection(
            ee, roi, start, end,
            max_cloud_cover=DEFAULT_MAX_CATALOG_CLOUD)
    if sensor == "sentinel1":
        from spartina.data.gee import sentinel1
        return sentinel1.load_collection(ee, roi, start, end)
    raise KeyError(f"unsupported smoke sensor {sensor!r}")


def _pixel_quality(ee: Any, sensor: str, collection: Any,
                   roi: Any) -> dict[str, dict[str, object]]:
    if sensor == "landsat8":
        fractions = pixelqa.evaluate_landsat(ee, collection, roi)
    elif sensor == "sentinel2":
        fractions = pixelqa.evaluate_sentinel2(ee, collection, roi)
    elif sensor == "sentinel1":
        fractions = pixelqa.evaluate_sentinel1(ee, collection, roi)
    else:
        raise KeyError(sensor)
    return {sid: dict(values) for sid, values in fractions.items()}


def _ordered_row(record: dict[str, object], sensor: str) -> dict[str, object]:
    extras = record.get("quality_extras")
    extras = dict(extras) if isinstance(extras, dict) else {}
    raw_reasons = record.get("rejection_reasons")
    native_m, grid_name = SENSOR_GRID[sensor]
    row: dict[str, object] = {
        "scene_id": record.get("scene_id"),
        "product_id": record.get("product_id"),
        "sensor": sensor,
        "acquisition_utc": record.get("acquisition_utc"),
        "wrs_path": record.get("wrs_path"),
        "wrs_row": record.get("wrs_row"),
        "mgrs_tile": record.get("mgrs_tile"),
        "orbit_direction": record.get("orbit_direction"),
        "relative_orbit_number": record.get("relative_orbit_number"),
        "polarizations": record.get("polarizations"),
        "cloud_cover_fraction": record.get("cloud_cover_fraction"),
        "roi_cloud_fraction": extras.get("roi_cloud_fraction"),
        "valid_pixel_fraction": record.get("valid_pixel_fraction"),
        "clear_pixel_fraction": extras.get("clear_pixel_fraction"),
        "footprint_coverage_fraction": record.get(
            "footprint_coverage_fraction"),
        "native_resolution_m": native_m,
        "grid": grid_name,
        "accepted": bool(record.get("accepted")),
        "selected": bool(record.get("selected")),
        "rejection_reasons": (
            list(raw_reasons) if isinstance(raw_reasons, list) else []),
    }
    return row


def run_smoke(
    sensors: tuple[str, ...], start: str, end: str,
    out_dir: Path, target_doy: int,
) -> dict[str, Any]:
    """Execute the real metadata-only smoke; return the run summary."""
    project = configured_project()
    if project is None:
        raise SystemExit(
            f"export {PROJECT_ENV_VAR}=<project-id> before the real smoke")
    initialize()
    import ee

    client = EarthEngineCatalogClient()
    ee_roi = _ee_geometry(ee, HZ_SMOKE_BOX)
    policy = SingleScenePolicy(target_doy=target_doy)
    ordered_rows: list[dict[str, object]] = []
    selected: dict[str, object] = {}

    for sensor in sensors:
        scenes = client.query(SceneQuery(
            sensor_name=sensor, start_date=start, end_date=end,
            region=HZ_SMOKE_BOX, max_cloud_cover=1.0))
        if not scenes:
            raise RuntimeError(
                f"ZERO real scenes for {sensor} {start}..{end}; "
                "cannot run a provenance smoke on an empty catalog")
        raw = _raw_collection(ee, sensor, ee_roi, start, end)
        pixel_quality = _pixel_quality(ee, sensor, raw, ee_roi)
        if sensor in ("landsat8", "sentinel2"):
            accepted = apply_filters(
                scenes, [CloudCoverFilter(DEFAULT_MAX_CATALOG_CLOUD)])
        else:
            accepted = list(scenes)
        table = build_candidate_table(
            scenes,
            frozenset(s.scene_id for s in accepted),
            pixel_quality_by_scene=pixel_quality,
        )
        records = candidate_records(table)
        chosen = best_single_scene(records, policy)
        chosen_id = (chosen.get("scene_id") if chosen else None)
        for record in records:
            row = _ordered_row(record, sensor)
            policy_reasons = rejection_reasons(record, policy)
            existing_reasons = (
                list(row["rejection_reasons"])
                if isinstance(row["rejection_reasons"], list) else [])
            row["policy_eligible"] = not policy_reasons and row["accepted"]
            if policy_reasons:
                row["rejection_reasons"] = sorted(
                    {*existing_reasons, *policy_reasons})
            row["selected"] = row["scene_id"] == chosen_id
            ordered_rows.append(row)
        if chosen is not None:
            selected[sensor] = {
                "scene_id": chosen_id,
                "acquisition_utc": chosen.get("acquisition_utc"),
                "product_id": chosen.get("product_id"),
            }
        else:
            selected[sensor] = None

    stamp = _now_stamp()
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"candidate_scenes_{stamp}.json"
    parquet_path = out_dir / f"candidate_scenes_{stamp}.parquet"
    json_path.write_text(
        json.dumps(ordered_rows, indent=2, sort_keys=True),
        encoding="utf-8")
    try:
        import pandas as pd
    except ImportError as exc:
        raise SystemExit("pandas/pyarrow are required to write the parquet") from exc
    frame = pd.DataFrame(ordered_rows, columns=list(CANDIDATE_COLUMNS))
    frame.to_parquet(parquet_path, index=False)
    summary = {
        "run_utc": stamp,
        "project_env_var": PROJECT_ENV_VAR,
        "project_id_set": project is not None,
        "roi": {"name": "HZ_SMOKE_BOX_TECHNICAL", "crs_epsg": 4326,
                "geometry": HZ_SMOKE_BOX.geometry,
                "note": "technical smoke box, not an authoritative boundary"},
        "window": {"start": start, "end": end, "target_doy": target_doy},
        "sensors": list(sensors),
        "candidate_counts": {
            sensor: sum(1 for r in ordered_rows if r["sensor"] == sensor)
            for sensor in sensors},
        "selected_scenes": selected,
        "candidate_parquet": str(parquet_path),
        "candidate_json": str(json_path),
        "policy": {
            "min_footprint_coverage": policy.min_footprint_coverage,
            "min_valid_pixel_fraction": policy.min_valid_pixel_fraction,
            "max_cloud_fraction": policy.max_cloud_fraction,
        },
    }
    summary_path = out_dir / f"selected_scenes_{stamp}.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--target-doy", type=int, default=DEFAULT_TARGET_DOY)
    parser.add_argument("--sensors", nargs="+",
                        default=["landsat8", "sentinel1", "sentinel2"])
    parser.add_argument("--out-dir", default="artifacts/gee")
    args = parser.parse_args()
    summary = run_smoke(
        tuple(args.sensors), args.start, args.end,
        Path(args.out_dir), args.target_doy)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
