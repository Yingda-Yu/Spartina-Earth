#!/usr/bin/env python
"""One real, tiny Landsat 8 export for the Issue #6 acceptance gate.

Metadata queries run first (``real_catalog_smoke.py``). This driver only
starts when ALL of the following hold:

1. metadata smoke passed and a candidate table exists;
2. exactly one LANDSAT-8 scene is *policy-eligible* (the predeclared
   selection policy must not be edited after looking at the results);
3. the operator explicitly exports SPARTINA_GEE_SMOKE_EXPORT=1.

When the fixed 2020 window yields zero policy-eligible L8 scenes (a real
autumn-cloud possibility on a 0.02-degree box), this driver refuses with
NO_ELIGIBLE_LANDSAT8_SCENE instead of widening the window, relaxing the
policy, or exporting a cloudy scene and calling it selected.

Products (single source scene -- NEVER a composite):

* ``..._sr.tif``    SR_B1..SR_B7 float32, DN*2.75e-5-0.2, fill pixels
                    masked (nodata semantics preserved -- never a fake 0);
* ``..._valid.tif`` one byte VALID band (the documented QA_PIXEL clear
                    decision including QA_RADSAT; water remains valid),
                    exported separately so the reflectance file stays a
                    pure float32 7-band raster.

Chain: ee.batch.Export.image.toDrive (folder SpartinaEarthSmoke) -> bounded
poll -> Drive download to work/gee/real_smoke (atomic .part landing) ->
rasterio GridSpec verification -> reflectance sanity -> SHA-256 ->
GEE_DATA_FACTORY_V1 manifest (work copy + datasets/manifests tracked copy)
-> provenance-chain assertion.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

from spartina.data.gee import driveio, landsat  # noqa: E402
from spartina.data.gee.auth import configured_project, initialize  # noqa: E402
from spartina.data.gee.export import ExportRequest, ExportTask, land_bytes  # noqa: E402
from spartina.data.gee.grid import (  # noqa: E402
    GridSpec,
    assert_no_forced_upsampling,
    covering_grid,
)
from spartina.data.gee.manifest import build_data_factory_manifest  # noqa: E402
from spartina.data.gee.provenance import (  # noqa: E402
    assert_grid_matches,
    assert_provenance_chain,
    git_context,
    raster_grid_info,
    reflectance_sanity,
    runtime_environment,
)
from spartina.data.gee.tasks import (  # noqa: E402
    STATE_COMPLETED,
    TaskRecord,
    TaskStore,
)
from spartina.data.gee.tide import no_tide_metadata  # noqa: E402

UTM_EPSG = 32651  # UTM zone 51N (Zhejiang coast 120E-126E)
EXPORT_ROI_ID = "SMOKE_EXPORT_ROI_V1"
EXPORT_HALF_DEG = 0.0025  # ~470-550 m half-width at this latitude
EXPORT_CENTER = (121.110, 30.310)  # fixed centre INSIDE HZB_TECH_SMOKE_V1
GDRIVE_FOLDER = "SpartinaEarthSmoke"
POLL_INTERVAL_S = 10
POLL_TIMEOUT_S = 1800
DRIVE_PROPAGATION_S = 90

GEE_DONE = "COMPLETED"
GEE_FAILED = {"FAILED", "CANCELLED", "CANCEL_REQUESTED"}
SR_BANDS: tuple[str, ...] = (
    "SR_B1", "SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B6", "SR_B7")

DEFAULT_CANDIDATES = (
    REPO_ROOT / "artifacts" / "gee" / "real_smoke"
    / "candidate_scenes_real_smoke_v1.json")
BACKUP_CANDIDATES = (
    REPO_ROOT / "artifacts" / "gee" / "real_smoke"
    / "candidate_scenes_real_smoke_backup_v1.json")
DEFAULT_OUT_DIR = REPO_ROOT / "work" / "gee" / "real_smoke"
DEFAULT_TASKS = DEFAULT_OUT_DIR / "tasks" / "task_store.json"
TRACKED_MANIFEST = (
    REPO_ROOT / "datasets" / "manifests" / "gee_real_smoke_v1.json")
WINDOW = ("2020-09-01T00:00:00Z", "2020-11-01T00:00:00Z")
BACKUP_WINDOW = ("2020-06-01T00:00:00Z", "2020-08-01T00:00:00Z")
BACKUP_TARGET_DOY = 182


@dataclass(frozen=True)
class GateProfile:
    """Predeclared query profile behind the export gate.

    The profile selects ONLY the candidate table / window used by the
    eligibility gate. It changes no threshold and no ranking rule; under
    both fixed 2020 windows the real L8 gate is closed (zero eligible),
    so the export code below the gate never executes for these profiles.
    """

    name: str
    default_candidates: Path
    window: tuple[str, str]
    target_doy: int


AUTUMN_PROFILE = GateProfile(
    name="autumn_v1", default_candidates=DEFAULT_CANDIDATES,
    window=WINDOW, target_doy=275)
BACKUP_PROFILE = GateProfile(
    name="backup_v1", default_candidates=BACKUP_CANDIDATES,
    window=BACKUP_WINDOW, target_doy=BACKUP_TARGET_DOY)
GATE_PROFILES: dict[str, GateProfile] = {
    AUTUMN_PROFILE.name: AUTUMN_PROFILE,
    BACKUP_PROFILE.name: BACKUP_PROFILE}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()  # noqa: UP017


def export_box_geojson() -> dict[str, Any]:
    lon, lat = EXPORT_CENTER
    w, e = lon - EXPORT_HALF_DEG, lon + EXPORT_HALF_DEG
    s, n = lat - EXPORT_HALF_DEG, lat + EXPORT_HALF_DEG
    return {"type": "Polygon", "coordinates": [[
        [w, s], [e, s], [e, n], [w, n], [w, s]]]}


def build_grid(box: dict[str, Any]) -> GridSpec:
    """Reproject the tiny WGS84 box to UTM 51N and snap a 30 m grid."""
    from pyproj import Transformer

    coords = box["coordinates"][0]
    lons = [p[0] for p in coords]
    lats = [p[1] for p in coords]
    xs, ys = Transformer.from_crs(
        4326, UTM_EPSG, always_xy=True).transform(lons, lats)
    grid = covering_grid((min(xs), min(ys), max(xs), max(ys)),
                         UTM_EPSG, 30.0)
    assert_no_forced_upsampling(30.0, grid.pixel_x_m)
    return grid


def _load_source_image(ee: Any, scene_id: str) -> Any:
    """Real single-scene L8 image: float32 scaled SR + byte VALID mask."""
    collection = ee.ImageCollection("LANDSAT/LC08/C02/T1_L2")
    raw = collection.filter(
        ee.Filter.eq("system:index", scene_id)).first()
    qa = raw.select("QA_PIXEL")
    observed = qa.bitwiseAnd(1 << landsat.QA_FILL).eq(0)
    sr = (landsat.scale_to_physical(ee, raw, "landsat8")
          .select(list(SR_BANDS), list(SR_BANDS))
          .toFloat()
          .updateMask(observed))
    clear = (
        observed
        .And(qa.bitwiseAnd(1 << landsat.QA_DILATED_CLOUD).eq(0))
        .And(qa.bitwiseAnd(1 << landsat.QA_CIRRUS).eq(0))
        .And(qa.bitwiseAnd(1 << landsat.QA_CLOUD).eq(0))
        .And(qa.bitwiseAnd(1 << landsat.QA_CLOUD_SHADOW).eq(0))
        .And(qa.bitwiseAnd(1 << landsat.QA_SNOW).eq(0))
        .And(qa.bitwiseAnd(1 << landsat.QA_CLEAR).neq(0))
        .And(raw.select("QA_RADSAT").eq(0))
    )
    valid = clear.rename("VALID").toByte()
    return sr, valid


def run_task(
    ee: Any, image: Any, box: dict[str, Any], grid: GridSpec,
    prefix: str, store: TaskStore, request_id: str,
) -> TaskRecord:
    """Start + bounded-poll a real Drive batch task; return the record."""
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
            return store.get(record.task_id)
        if state in GEE_FAILED:
            error = str(statuses[0].get("error_message") or "task failed")
            store.record_attempt_error(record.task_id, error)
            raise RuntimeError(
                f"GEE export task {task.id} {state}: {error}")
        if state == "RUNNING":
            current = store.get(record.task_id)
            from spartina.data.gee.tasks import STATE_RUNNING
            if current.state != STATE_RUNNING:
                store.mark_running(record.task_id)
        time.sleep(POLL_INTERVAL_S)
    raise TimeoutError(
        f"GEE export task {task.id} did not finish within {POLL_TIMEOUT_S}s")


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


def _cloud_sort_key(row: dict[str, Any]) -> float:
    """Order rejected L8 scenes for the diagnostic message only."""
    value = row.get("roi_cloud_fraction")
    return float(value) if isinstance(value, int | float) else 9.0


def _gate_selected_scene(candidates: list[dict[str, Any]]
                         ) -> dict[str, Any]:
    rows = [r for r in candidates if r.get("sensor") == "landsat8"]
    if not rows:
        raise SystemExit("NO_LANDSAT8_CANDIDATES: candidate table has no L8")
    selected = [r for r in rows if r.get("selected")]
    if len(selected) == 1:
        return dict(selected[0])
    best = sorted(rows, key=_cloud_sort_key)[0]
    raise SystemExit(
        "NO_ELIGIBLE_LANDSAT8_SCENE: the predeclared single-scene policy "
        f"rejected all {len(rows)} L8 candidates, so the export gate is "
        "CLOSED. The date window and policy must not be edited after "
        "inspection. Best-available (NOT exported): "
        f"{best.get('scene_id')} ROI_cloud="
        f"{best.get('roi_cloud_fraction')} clear="
        f"{best.get('clear_pixel_fraction')} reasons="
        f"{best.get('rejection_reasons')}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--window-profile", choices=sorted(GATE_PROFILES),
        default=AUTUMN_PROFILE.name,
        help="predeclared gate profile (autumn_v1 primary window; "
             "backup_v1 is the Issue #6 M1.6b predeclared seasonal "
             "fallback -- threshold/ranking identical)")
    parser.add_argument("--candidates", default=None)
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--tasks", default=str(DEFAULT_TASKS))
    args = parser.parse_args()
    profile = GATE_PROFILES[str(args.window_profile)]

    if __import__("os").environ.get("SPARTINA_GEE_SMOKE_EXPORT") != "1":
        raise SystemExit(
            "real export needs SPARTINA_GEE_SMOKE_EXPORT=1 "
            "(metadata smoke + eligible-scene gate must pass first)")
    if configured_project() is None:
        raise SystemExit("export SPARTINA_GEE_PROJECT=<project-id> first")
    initialize()
    import ee

    candidates_path = (
        Path(args.candidates) if args.candidates
        else profile.default_candidates)
    candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
    chosen = _gate_selected_scene(candidates)
    scene_id = str(chosen["scene_id"])
    scene_date = str(chosen["acquisition_date"])
    short_id = scene_id.replace("/", "_")
    prefix_sr = f"spartina_gee_smoke_l8_{scene_date}_{short_id}_sr"
    prefix_valid = f"spartina_gee_smoke_l8_{scene_date}_{short_id}_valid"

    box = export_box_geojson()
    grid = build_grid(box)
    sr_image, valid_image = _load_source_image(ee, scene_id)
    out_dir = Path(args.out_dir)
    store = TaskStore(args.tasks)
    creation_utc = _now_iso()

    sr_record = run_task(
        ee, sr_image, box, grid, prefix_sr, store,
        f"smoke-l8-sr-{scene_date}-{short_id}")
    valid_record = run_task(
        ee, valid_image, box, grid, prefix_valid, store,
        f"smoke-l8-valid-{scene_date}-{short_id}")
    completion_utc = _now_iso()

    sr_bytes = polled_download(prefix_sr)
    valid_bytes = polled_download(prefix_valid)
    sr_path = out_dir / f"{prefix_sr}.tif"
    valid_path = out_dir / f"{prefix_valid}.tif"
    sr_landed = land_bytes(sr_path, sr_bytes)
    valid_landed = land_bytes(valid_path, valid_bytes)

    sr_info = raster_grid_info(sr_path)
    valid_info = raster_grid_info(valid_path)
    assert_grid_matches(sr_info, grid.to_dict())
    assert_grid_matches(valid_info, grid.to_dict())
    if sr_info["count"] != 7 or any(t != "float32" for t in sr_info["dtypes"]):
        raise SystemExit(f"SR raster dtype/band failure: {sr_info}")
    if valid_info["count"] != 1 or valid_info["dtypes"][0] != "uint8":
        raise SystemExit(f"VALID raster dtype/band failure: {valid_info}")
    sanity = reflectance_sanity(sr_path, band_count=7)

    request = ExportRequest(
        request_id=f"smoke-l8-{scene_date}-{short_id}",
        sensor_name="landsat8",
        tile_id=EXPORT_ROI_ID,
        start_date=profile.window[0], end_date=profile.window[1],
        destination_uri=f"gdrive://{GDRIVE_FOLDER}/{prefix_sr}",
        bands=SR_BANDS,
        crs_epsg=grid.crs_epsg,
        resolution_m=30.0,
        grid_spec=grid.to_dict(),
        source_scene_ids=(scene_id,),
        science_stream="landsat_30m",
    )
    task = ExportTask(
        task_id=sr_record.backend_task_id or f"drive:{prefix_sr}",
        request_id=request.request_id,
        state=STATE_COMPLETED,
        messages=(
            f"ee.batch.Export.image.toDrive SR -> {GDRIVE_FOLDER} "
            f"(task {sr_record.backend_task_id})",
            f"ee.batch.Export.image.toDrive VALID -> {GDRIVE_FOLDER} "
            f"(task {valid_record.backend_task_id})",
        ))
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
            "masking": "SR masked at QA_PIXEL fill (nodata); cloudy pixels "
                       "kept as observed radiance; separate byte VALID band "
                       "= QA_PIXEL clear (dilated/cirrus/cloud/shadow/snow "
                       "absent, Clear bit set) AND QA_RADSAT==0; water valid",
            "band_order": list(SR_BANDS),
            "valid_mask_band_order": ["VALID"],
            "crs_transform": list(grid.transform),
            "file_dimensions": [grid.width, grid.height],
            "gdrive_folder": GDRIVE_FOLDER,
            "native_resolution_m": 30.0,
            "resampling": "NONE; native 30 m pixels on a 30 m grid",
            "raster_verification": {"sr": sr_info, "valid": valid_info},
            "reflectance_sanity": sanity,
        },
        landed_files=[
            {**sr_landed, "role": "surface_reflectance_float32",
             "band_order": list(SR_BANDS), "format": "GeoTIFF",
             "grid_verified": True},
            {**valid_landed, "role": "valid_mask_byte",
             "band_order": ["VALID"], "format": "GeoTIFF",
             "grid_verified": True},
        ],
        tide_records=[{
            **no_tide_metadata(
                scene_id,
                acquisition_utc=str(chosen.get("acquisition_utc"))
                if chosen.get("acquisition_utc") else None,
            ).to_record(),
            "proxy_basis": "none_available",
            "notes": "tide/inundation not assessed for the technical "
                     "export smoke; PROXY field only, never observed tide",
        }],
        roi={
            "roi_id": "HZB_TECH_SMOKE_V1", "crs_epsg": 4326,
            "geometry": box,
            "export_roi_id": EXPORT_ROI_ID,
            "export_roi_center_lonlat": list(EXPORT_CENTER),
            "export_roi_half_width_deg": EXPORT_HALF_DEG,
            "note": "fixed ~500 m sub-box of HZB_TECH_SMOKE_V1; technical "
                    "plumbing verification, not an authoritative boundary",
        },
        notes="Issue #6 first real export: single L8 scene, ~500 m ROI, "
              "7-band float32 SR + byte VALID, Drive roundtrip.")
    manifest["query"] = {
        "window_profile": profile.name,
        "window_start_utc": profile.window[0],
        "window_end_utc": profile.window[1],
        "target_doy": profile.target_doy,
        "candidate_table": str(candidates_path),
    }
    manifest["source_product"] = {
        "scene_id": scene_id,
        "product_id": chosen.get("product_id"),
        "acquisition_utc": chosen.get("acquisition_utc"),
        "wrs_path": chosen.get("wrs_path"),
        "wrs_row": chosen.get("wrs_row"),
        "selection_metrics": {
            "roi_cloud_fraction": chosen.get("roi_cloud_fraction"),
            "roi_shadow_fraction": chosen.get("roi_shadow_fraction"),
            "valid_pixel_fraction": chosen.get("valid_pixel_fraction"),
            "clear_pixel_fraction": chosen.get("clear_pixel_fraction"),
            "roi_coverage_fraction": chosen.get("roi_coverage_fraction"),
            "selection_rank": chosen.get("selection_rank"),
            "selection_score": chosen.get("selection_score"),
        },
    }
    manifest["export_task"]["task_id_valid_mask"] = (
        valid_record.backend_task_id)
    manifest["export_task"]["creation_utc"] = creation_utc
    manifest["export_task"]["completion_utc"] = completion_utc
    manifest["project_id"] = configured_project()
    manifest["code"] = git_context(REPO_ROOT)
    manifest["environment"] = runtime_environment()

    work_manifest = out_dir / "gee_real_smoke_v1.manifest.json"
    work_manifest.write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    TRACKED_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    TRACKED_MANIFEST.write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    assert_provenance_chain(manifest)
    print(json.dumps({
        "scene_id": scene_id,
        "product_id": chosen.get("product_id"),
        "tasks": {"sr": sr_record.backend_task_id,
                  "valid": valid_record.backend_task_id},
        "sr_tif": str(sr_path), "valid_tif": str(valid_path),
        "sr_sha256": sr_landed["sha256"],
        "valid_sha256": valid_landed["sha256"],
        "sizes_bytes": {"sr": sr_landed["size_bytes"],
                        "valid": valid_landed["size_bytes"]},
        "grid": grid.to_dict(),
        "manifest_work": str(work_manifest),
        "manifest_tracked": str(TRACKED_MANIFEST),
        "provenance_chain": "PASS",
        "reflectance_scaling_check": sanity["scaling_check_pass"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
