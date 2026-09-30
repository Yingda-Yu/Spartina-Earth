#!/usr/bin/env python
"""One real, tiny Earth Engine export for the Issue #6 acceptance gate.

Metadata queries come first (see ``real_catalog_smoke.py``). Only after
they succeed should an operator enable this explicitly:

    export SPARTINA_GEE_SMOKE_EXPORT=1
    export SPARTINA_GEE_PROJECT=<project-id>
    python scripts/data/gee/real_export_smoke.py \\
        --candidates artifacts/gee/candidate_scenes_<stamp>.json

It exports the SELECTED single Landsat 8 scene (never a composite) over a
~500 m technical box to Google Drive via a real pollable ee.batch task,
downloads the finished GeoTIFF, verifies it against the fixed 30 m
GridSpec, lands it with SHA-256, and writes GEE_DATA_FACTORY_V1
provenance. Default mode is ``batch`` (Drive). ``--mode direct`` uses
getDownloadURL and is labelled a direct download, not a batch task.

This is intentionally tiny: one scene, ~18x18 px, seven bands.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

from spartina.data.gee import driveio  # noqa: E402
from spartina.data.gee.auth import configured_project, initialize  # noqa: E402
from spartina.data.gee.export import ExportRequest, ExportTask, land_bytes  # noqa: E402
from spartina.data.gee.grid import (  # noqa: E402
    GridSpec,
    assert_no_forced_upsampling,
    covering_grid,
)
from spartina.data.gee.manifest import build_data_factory_manifest, write_json  # noqa: E402
from spartina.data.gee.tasks import (  # noqa: E402
    STATE_COMPLETED,
    STATE_FAILED,
    STATE_RUNNING,
    TaskRecord,
    TaskStore,
)
from spartina.data.gee.tide import no_tide_metadata  # noqa: E402

UTM_EPSG = 32651  # UTM zone 51N (Zhejiang coast 120E-126E)
SMOKE_HALF_DEG = 0.0025  # ~470-550 m half-width in this latitude
SMOKE_CENTER = (121.110, 30.310)
GDRIVE_FOLDER = "spartina_earth_gee_smoke"
POLL_INTERVAL_S = 10
POLL_TIMEOUT_S = 1800
DRIVE_PROPAGATION_S = 90

GEE_DONE = "COMPLETED"
GEE_FAILED = {"FAILED", "CANCELLED", "CANCEL_REQUESTED"}


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")  # noqa: UP017


def smoke_box_geojson() -> dict[str, Any]:
    lon, lat = SMOKE_CENTER
    w, e = lon - SMOKE_HALF_DEG, lon + SMOKE_HALF_DEG
    s, n = lat - SMOKE_HALF_DEG, lat + SMOKE_HALF_DEG
    return {
        "type": "Polygon",
        "coordinates": [[
            [w, s], [e, s], [e, n], [w, n], [w, s]]],
    }


def build_grid(box: dict[str, Any]) -> GridSpec:
    """Reproject the tiny WGS84 box to UTM 51N and snap a 30 m grid."""
    from pyproj import Transformer

    coords = box["coordinates"][0]
    lons = [p[0] for p in coords]
    lats = [p[1] for p in coords]
    transformer = Transformer.from_crs(
        4326, UTM_EPSG, always_xy=True)
    xs, ys = transformer.transform(lons, lats)
    grid = covering_grid((min(xs), min(ys), max(xs), max(ys)),
                         UTM_EPSG, 30.0)
    assert_no_forced_upsampling(30.0, grid.pixel_x_m)
    return grid


def _selected_scene(candidates: list[dict[str, Any]],
                    sensor: str) -> dict[str, Any]:
    rows = [r for r in candidates if r.get("sensor") == sensor]
    if not rows:
        raise SystemExit(f"no {sensor} rows in the candidate file")
    chosen = [r for r in rows if r.get("selected")]
    if len(chosen) != 1:
        raise SystemExit(
            f"expected exactly one selected {sensor} scene, "
            f"found {len(chosen)}")
    return dict(chosen[0])


def _load_image(ee: Any, scene_id: str, bands: tuple[str, ...]) -> Any:
    from spartina.data.gee import landsat

    collection = ee.ImageCollection("LANDSAT/LC08/C02/T1_L2")
    image = collection.filter(
        ee.Filter.eq("system:index", scene_id)).first()
    scaled = landsat.scale_to_physical(ee, image, "landsat8")
    return scaled.select(list(bands))


def run_batch(
    ee: Any, image: Any, box: dict[str, Any], grid: GridSpec,
    prefix: str, store: TaskStore, request_id: str,
) -> tuple[str, TaskRecord]:
    """Start + poll the real ee.batch Drive task; return (file prefix, rec)."""
    task = ee.batch.Export.image.toDrive(
        image=image,
        description=prefix,
        folder=GDRIVE_FOLDER,
        fileNamePrefix=prefix,
        region=box,
        crs=grid.crs,
        crsTransform=list(grid.transform),
        fileDimensions=[grid.width, grid.height],
        maxPixels=1_000_000_000,
        fileFormat="GeoTIFF",
    )
    record = store.create(request_id)
    task.start()
    store.mark_enqueued(record.task_id, str(task.id))
    deadline = time.monotonic() + POLL_TIMEOUT_S
    while time.monotonic() < deadline:
        statuses = ee.data.getTaskStatus(str(task.id))
        state = str(statuses[0].get("state"))
        if state == GEE_DONE:
            store.mark_completed(record.task_id, result=statuses[0])
            return prefix, store.get(record.task_id)
        if state in GEE_FAILED:
            error = str(statuses[0].get("error_message") or "task failed")
            store.record_attempt_error(record.task_id, error)
            raise RuntimeError(f"GEE export task {task.id} {state}: {error}")
        if state == "RUNNING":
            current = store.get(record.task_id)
            if current.state != STATE_RUNNING:
                store.mark_running(record.task_id)
        time.sleep(POLL_INTERVAL_S)
    raise TimeoutError(f"GEE export task {task.id} did not finish in time")


def polled_download(prefix: str) -> bytes:
    """Wait for Drive propagation, then download the finished GeoTIFF."""
    deadline = time.monotonic() + DRIVE_PROPAGATION_S
    while True:
        try:
            _name, data = driveio.download_latest(prefix)
            return data
        except driveio.DriveDownloadError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(5)


def verify_geotiff(
    path: Path, grid: GridSpec, bands: tuple[str, ...],
) -> dict[str, Any]:
    """Verify the landed raster really matches the fixed export grid."""
    import rasterio
    from rasterio.transform import Affine

    with rasterio.open(path) as dataset:
        info = {
            "driver": dataset.driver,
            "width": dataset.width,
            "height": dataset.height,
            "count": dataset.count,
            "crs_epsg": dataset.crs.to_epsg(),
            "dtypes": list(dataset.dtypes),
            "band_names": list(dataset.descriptions),
            "transform": list(dataset.transform)[:6],
        }
    expected = Affine(*grid.transform)
    actual = Affine(*info["transform"])
    if (info["width"] != grid.width or info["height"] != grid.height
            or info["count"] != len(bands)
            or info["crs_epsg"] != grid.crs_epsg):
        raise ValueError(f"landed GeoTIFF disagrees with the GridSpec: {info}")
    if not expected.almost_equals(actual, precision=6):
        raise ValueError(
            f"transform mismatch: expected {tuple(expected)[:6]}, "
            f"got {tuple(actual)[:6]}")
    return info


def run_direct(ee: Any, image: Any, box: dict[str, Any],
               grid: GridSpec, bands: tuple[str, ...],
               prefix: str) -> tuple[bytes, str]:
    """Fallback path: synchronous getDownloadURL GeoTIFF (no batch task)."""
    import urllib.request

    url = image.getDownloadURL({
        "name": prefix,
        "fileFormat": "GEO_TIFF",
        "region": box,
        "crs": grid.crs,
        "crsTransform": list(grid.transform),
        "dimensions": [grid.width, grid.height],
    })
    with urllib.request.urlopen(url, timeout=300) as response:  # noqa: S310
        data = response.read()
    task_id = f"direct:getDownloadURL:{prefix}"
    return data, task_id


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", required=True,
                        help="candidate_scenes_<stamp>.json from the catalog smoke")
    parser.add_argument("--sensor", default="landsat8")
    parser.add_argument("--mode", choices=("batch", "direct"),
                        default="batch")
    parser.add_argument("--out-dir", default="artifacts/gee")
    parser.add_argument("--tasks", default="artifacts/gee/tasks/task_store.json")
    args = parser.parse_args()

    if args.mode == "batch":
        import os
        if os.environ.get("SPARTINA_GEE_SMOKE_EXPORT") != "1":
            raise SystemExit(
                "real batch export needs SPARTINA_GEE_SMOKE_EXPORT=1 "
                "(metadata smoke must pass first)")
    if configured_project() is None:
        raise SystemExit("export SPARTINA_GEE_PROJECT=<project-id> first")
    initialize()
    import ee

    candidates = json.loads(Path(args.candidates).read_text(encoding="utf-8"))
    chosen = _selected_scene(candidates, args.sensor)
    scene_id = str(chosen["scene_id"])
    from spartina.data.gee import landsat

    bands = landsat.export_bands("landsat8")
    box = smoke_box_geojson()
    grid = build_grid(box)
    image = _load_image(ee, scene_id, bands)
    stamp = _now_stamp()
    prefix = f"spartina_l8_smoke_{stamp}"
    request_id = f"smoke-landsat8-{stamp}"
    out_dir = Path(args.out_dir)
    store = TaskStore(args.tasks)

    backend_state = "COMPLETED"
    messages: list[str] = []
    if args.mode == "batch":
        prefix, task_record = run_batch(
            ee, image, box, grid, prefix, store, request_id)
        data = polled_download(prefix)
        task_id = task_record.backend_task_id or f"drive:{prefix}"
        messages.append(f"ee.batch.Export.image.toDrive -> {GDRIVE_FOLDER}")
        if task_record.state in (STATE_FAILED,):
            raise RuntimeError("task store reports failure after export")
    else:
        data, task_id = run_direct(ee, image, box, grid, bands, prefix)
        messages.append("direct getDownloadURL (no Earth Engine batch task)")

    tif_path = out_dir / f"{prefix}.tif"
    landed = land_bytes(tif_path, data)
    raster_info = verify_geotiff(tif_path, grid, bands)
    request = ExportRequest(
        request_id=request_id,
        sensor_name="landsat8",
        tile_id="HZ_SMOKE_BOX_TECHNICAL",
        start_date="2020-09-01", end_date="2020-10-31",
        destination_uri=f"gdrive://{GDRIVE_FOLDER}/{prefix}",
        bands=bands,
        crs_epsg=grid.crs_epsg,
        resolution_m=30.0,
        grid_spec=grid.to_dict(),
        source_scene_ids=(scene_id,),
        science_stream="landsat_30m",
    )
    task = ExportTask(
        task_id=task_id, request_id=request_id,
        state=STATE_COMPLETED if backend_state == "COMPLETED" else backend_state,
        messages=tuple(messages))
    manifest = build_data_factory_manifest(
        request, task,
        candidate_scenes=list(candidates),
        selected_scene_ids=[scene_id],
        grid_spec=grid.to_dict(),
        processing_config={
            "collection_id": "LANDSAT/LC08/C02/T1_L2",
            "composite": "NONE_BEST_SINGLE_SCENE",
            "reflectance_scale": 2.75e-5,
            "reflectance_offset": -0.2,
            "qa_policy": "QA_PIXEL clear decision documented in pixelqa.py; "
                        "export keeps observed pixels without masking",
            "crs_transform": list(grid.transform),
            "file_dimensions": [grid.width, grid.height],
            "gdrive_folder": GDRIVE_FOLDER,
            "export_mode": args.mode,
            "raster_verification": raster_info,
            "native_resolution_m": 30.0,
            "resampling": "NONE; native 30 m pixels on a 30 m grid",
        },
        landed_files=[{**landed, "band_order": list(bands),
                       "format": "GeoTIFF"}],
        tide_records=[{
            **no_tide_metadata(
                scene_id,
                acquisition_utc=str(chosen["acquisition_utc"])
                if chosen.get("acquisition_utc") else None,
            ).to_record(),
            "proxy_basis": "none_available",
            "notes": "tide/inundation not assessed for the technical "
                     "export smoke; PROXY field only, never observed tide",
        }],
        roi={"name": "HZ_SMOKE_BOX_TECHNICAL", "crs_epsg": 4326,
             "geometry": box,
             "note": "technical smoke box, not an authoritative boundary"},
        notes="Issue #6 first real export smoke: single L8 scene, ~500 m ROI.")
    manifest_path = write_json(out_dir / f"manifest_{stamp}.json", manifest)
    print(json.dumps({
        "scene_id": scene_id,
        "task_id": task_id,
        "mode": args.mode,
        "tif": str(tif_path),
        "sha256": landed["sha256"],
        "size_bytes": landed["size_bytes"],
        "grid": grid.to_dict(),
        "manifest": str(manifest_path),
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
