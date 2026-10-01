#!/usr/bin/env python
"""M1.6c -- first REAL Sentinel-2 byte-pipeline closure for Issue #6.

Purpose (owner authorization, GitHub comment 2026-10-01): validate the
GENERIC real Earth Engine byte transport chain

    ee.batch.Export.image.toDrive -> bounded poll (full state history)
    -> Google Drive -> atomic local landing -> rasterio validation
    -> SHA-256 -> GridSpec match -> complete provenance manifest

using the ALREADY SELECTED, ALREADY FROZEN autumn Sentinel-2 scene from
the first real catalog smoke. This driver MUST NOT re-select a scene:
a pre-export double metadata retrieval must reproduce the frozen
selection exactly, otherwise it STOPS before creating any task.

Scope caveat (must accompany every report of this product):
* VERIFIES the generic real byte/export/provenance infrastructure on S2;
* does NOT verify Landsat C2 L2 byte scaling/export (both predeclared
  2020 L8 windows yielded zero eligible scenes:
  L8_REAL_EXPORT_NOT_OBSERVED_UNDER_PREDECLARED_WINDOWS);
* does NOT verify Sentinel-1 real byte export.

Product: S2_REAL_BYTE_SMOKE_V1 -- a technical smoke product only. It is
not the Zhejiang dataset, not a science stack, not training data.

Single source scene only -- never median/mean/mosaic/qualityMosaic.
Native 10 m bands only (B2/B3/B4/B8) as float32 reflectance = DN/10000;
B11/B12 (native 20 m) are excluded and never resampled to 10 m. VALID
lands as a separate uint8 0/1 file driven by the versioned SCL QA
contract in spartina.data.gee.sentinel2 (s2_scl_qa_v1_1: valid classes
{4,5,6}; water stays valid; SCL 11 snow/ice is invalid and is counted
separately; the post-acceptance M1.6d correction superseded the original
{4,5,6,11} rule).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = Path(__file__).resolve().parent
for _path in (REPO_ROOT / "src", SCRIPTS_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import real_catalog_smoke as catalog_smoke  # noqa: E402

from spartina.data.gee import driveio  # noqa: E402
from spartina.data.gee.auth import configured_project, initialize  # noqa: E402
from spartina.data.gee.collections import COLLECTIONS  # noqa: E402
from spartina.data.gee.export import ExportRequest, ExportTask, land_bytes  # noqa: E402
from spartina.data.gee.grid import (  # noqa: E402
    GridSpec,
    assert_no_forced_upsampling,
    covering_grid,
)
from spartina.data.gee.manifest import build_data_factory_manifest  # noqa: E402
from spartina.data.gee.provenance import (  # noqa: E402
    ProvenanceError,
    assert_grid_matches,
    assert_provenance_chain,
    git_context,
    raster_grid_info,
    reflectance_sanity_masked,
    runtime_environment,
    sha256_file,
    valid_mask_info,
)
from spartina.data.gee.selection import (  # noqa: E402
    SingleScenePolicy,
    canonical_fingerprint,
)
from spartina.data.gee.sentinel2 import (  # noqa: E402
    REFLECTANCE_SCALE,
    S2_SCL_QA_POLICY,
    S2_SCL_QA_POLICY_VERSION,
    TEN_M_BANDS,
)
from spartina.data.gee.tasks import STATE_COMPLETED, STATE_RUNNING, TaskStore  # noqa: E402

PRODUCT_ID = "S2_REAL_BYTE_SMOKE_V1"
LOCK_ID = "S2_SMOKE_EXPORT_LOCK_V1"
COLLECTION_ID = COLLECTIONS["sentinel2"]
UTM_EPSG = 32651  # UTM zone 51N (Zhejiang coast)
EXPORT_ROI_ID = "HZB_TECH_SMOKE_EXPORT_V1"
EXPORT_METRIC_HALF_WIDTH_M = 250.0  # fixed metric width: 500 m nominal
GDRIVE_FOLDER = "SpartinaEarthSmoke"
POLL_INTERVAL_S = 10
POLL_TIMEOUT_S = 1800
DRIVE_PROPAGATION_S = 90
GEE_DONE = "COMPLETED"
GEE_FAILED = {"FAILED", "CANCELLED", "CANCEL_REQUESTED"}

#: Frozen catalog fixture under the corrected s2_scl_qa_v1_1 policy.
#: The historical s2_scl_qa_v1 fixture (real_smoke_catalog_v1.json) is
#: retained unchanged for audit; its snow_pixel counts were zero for all
#: S2 candidates, so the corrected rows differ only by the recorded QA
#: policy version.
FROZEN_FIXTURE = (
    REPO_ROOT / "tests" / "fixtures" / "gee"
    / "real_smoke_catalog_scl_v1_1.json")
DEFAULT_OUT_DIR = REPO_ROOT / "work" / "gee" / "real_smoke" / "s2"
DEFAULT_TASKS = DEFAULT_OUT_DIR / "tasks" / "task_store.json"
TRACKED_MANIFEST = (
    REPO_ROOT / "datasets" / "manifests"
    / "gee_real_s2_export_smoke_v1_1.json")

#: SCL VALID contract record, identical to
#: pixelqa.sentinel2_qa_count_bands CLEAR_PIXELS used at catalog time.
#: Single source of truth: spartina.data.gee.sentinel2.S2_SCL_QA_POLICY.
SCL_QA_POLICY: dict[str, Any] = S2_SCL_QA_POLICY.to_manifest_dict()

#: White-listed task-status keys persisted from the live GEE status payload
#: (the status object contains no credentials; we still whitelist).
_TASK_RESULT_KEYS = (
    "state", "description", "task_type", "attempt",
    "creation_timestamp_ms", "start_timestamp_ms",
    "update_timestamp_ms", "additional_info")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()  # noqa: UP017


# ---------------------------------------------------------------------------
# Deterministic export ROI (technical ROI projected centroid + fixed metric
# width; never moved after looking at imagery)
# ---------------------------------------------------------------------------

def _bbox_centroid_lonlat(geometry: dict[str, Any]) -> tuple[float, float]:
    ring = geometry["coordinates"][0]
    lons = [float(p[0]) for p in ring]
    lats = [float(p[1]) for p in ring]
    return (min(lons) + max(lons)) / 2.0, (min(lats) + max(lats)) / 2.0


def build_export_roi() -> tuple[GridSpec, dict[str, Any], dict[str, Any]]:
    """Return (grid, region_geojson_wgs84, construction_rule).

    Deterministic rule: bbox centroid of HZB_TECH_SMOKE_V1 in EPSG:4326
    -> project to UTM 51N -> fixed +/-250 m metric box -> covering_grid
    snaps outward to the 10 m lattice -> export region is that exact grid
    footprint back-transformed to WGS84. Region never overrides the grid:
    crsTransform + fileDimensions are the single source of truth.
    """
    from pyproj import Transformer

    to_utm = Transformer.from_crs(4326, UTM_EPSG, always_xy=True)
    to_wgs = Transformer.from_crs(UTM_EPSG, 4326, always_xy=True)
    lon0, lat0 = _bbox_centroid_lonlat(catalog_smoke.ROI_GEOMETRY)
    cx, cy = to_utm.transform(lon0, lat0)
    metric_bounds = (
        cx - EXPORT_METRIC_HALF_WIDTH_M, cy - EXPORT_METRIC_HALF_WIDTH_M,
        cx + EXPORT_METRIC_HALF_WIDTH_M, cy + EXPORT_METRIC_HALF_WIDTH_M)
    grid = covering_grid(metric_bounds, UTM_EPSG, 10.0)
    assert_no_forced_upsampling(10.0, grid.pixel_x_m)
    west, south, east, north = grid.bounds
    lons, lats = to_wgs.transform(
        [west, east, east, west, west],
        [south, south, north, north, south])
    region = {"type": "Polygon", "coordinates": [[
        [float(lo), float(la)]
        for lo, la in zip(lons, lats, strict=True)]]}
    rule = {
        "construction": (
            "bbox centroid of HZB_TECH_SMOKE_V1 (EPSG:4326) -> project to "
            "EPSG:32651 -> fixed +/-250 m metric box (500 m nominal) -> "
            "covering_grid outward snap to the 10 m lattice -> region is "
            "the grid footprint back-transformed to WGS84; ROI is never "
            "moved after inspecting imagery"),
        "technical_roi_centroid_lonlat": [lon0, lat0],
        "centroid_utm51n_m": [cx, cy],
        "metric_half_width_m": EXPORT_METRIC_HALF_WIDTH_M,
        "metric_nominal_width_m": 2.0 * EXPORT_METRIC_HALF_WIDTH_M,
        "metric_box_bounds_utm51n_m": list(metric_bounds),
        "grid_bounds_utm51n_m": list(grid.bounds),
        "grid_width_m": east - west,
        "grid_height_m": north - south,
        "snap_note": (
            "covering_grid snaps outward to the 10 m lattice; the landed "
            "footprint is exactly 500-520 m per side, never hand-edited"),
    }
    return grid, region, rule


# ---------------------------------------------------------------------------
# Pre-export deterministic replay gate (frozen fixture is the reference)
# ---------------------------------------------------------------------------

def replay_s2_selection(ee: Any, fixture: dict[str, Any]) -> dict[str, Any]:
    """Double real S2 retrieval; must reproduce the frozen selection.

    Returns an evidence block; raises on any drift (STOP rule: the export
    must not start after a replay mismatch).
    """
    fixture_s2 = [r for r in fixture["candidate_rows"]
                  if r.get("sensor") == "sentinel2"]
    fixture_selected = [r for r in fixture_s2 if r.get("selected")]
    if len(fixture_selected) != 1:
        raise RuntimeError(
            f"frozen fixture must contain exactly 1 selected S2 scene, "
            f"got {len(fixture_selected)}")
    expected = fixture_selected[0]
    policy = SingleScenePolicy(
        target_doy=catalog_smoke.AUTUMN_V1.target_doy)
    ts_a = catalog_smoke._now_iso()
    rows_a = catalog_smoke.collect_sensor(
        ee, "sentinel2", policy, ts_a, catalog_smoke.AUTUMN_V1)
    ts_b = catalog_smoke._now_iso()
    rows_b = catalog_smoke.collect_sensor(
        ee, "sentinel2", policy, ts_b, catalog_smoke.AUTUMN_V1)

    ids_a = sorted(r["scene_id"] for r in rows_a)
    ids_b = sorted(r["scene_id"] for r in rows_b)
    ids_fx = sorted(r["scene_id"] for r in fixture_s2)
    live_selected = [r for r in rows_a if r.get("selected")]
    live = live_selected[0] if len(live_selected) == 1 else None

    s2_fp_a = canonical_fingerprint(
        catalog_smoke._fingerprint_payload(rows_a))
    s2_fp_b = canonical_fingerprint(
        catalog_smoke._fingerprint_payload(rows_b))
    s2_fp_fx = canonical_fingerprint(
        catalog_smoke._fingerprint_payload(fixture_s2))
    sel_fp_a = canonical_fingerprint(
        catalog_smoke._selection_payload({"sentinel2": rows_a}, policy))
    sel_fp_b = canonical_fingerprint(
        catalog_smoke._selection_payload({"sentinel2": rows_b}, policy))
    sel_fp_fx = canonical_fingerprint(
        catalog_smoke._selection_payload(
            {"sentinel2": fixture_s2}, policy))

    checks = {
        "candidate_count_matches_fixture":
            len(rows_a) == len(fixture_s2),
        "double_retrieval_ids_identical": ids_a == ids_b,
        "live_ids_match_fixture": ids_a == ids_fx,
        "exactly_one_selected": live is not None,
        "selected_scene_id_matches": (
            live is not None
            and live["scene_id"] == expected["scene_id"]),
        "selected_product_id_matches": (
            live is not None
            and live.get("product_id") == expected.get("product_id")),
        "selected_utc_matches": (
            live is not None
            and live.get("acquisition_utc") == expected.get("acquisition_utc")),
        "selected_mgrs_matches": (
            live is not None
            and live.get("mgrs_tile") == "51RUP"
            == expected.get("mgrs_tile")),
        "s2_catalog_fingerprint_rerun": s2_fp_a == s2_fp_b,
        "s2_catalog_fingerprint_matches_fixture": s2_fp_a == s2_fp_fx,
        "s2_selection_fingerprint_rerun": sel_fp_a == sel_fp_b,
        "s2_selection_fingerprint_matches_fixture": sel_fp_a == sel_fp_fx,
        # s2_scl_qa_v1_1 corrected frozen fixture; historical v1 values
        # (ddf6f158... / b659c68b...) are retained in the correction
        # manifest fingerprint mapping and must never be overwritten.
        "global_catalog_fingerprint_matches_fixture":
            fixture["catalog_fingerprint_sha256"]
            == "db9d29bb735e3a6cfb6852b239d30e525c82672a991e741d56a5fefb13c3b55b",
        "global_selection_fingerprint_matches_fixture":
            fixture["selection_fingerprint_sha256"]
            == "b659c68b0018b09328b61a5cbaf64ad21a282594e81834173815db7bdc9d4f4e",
    }
    evidence = {
        "window": {
            "name": catalog_smoke.AUTUMN_V1.name,
            "start_utc": catalog_smoke.AUTUMN_V1.start_utc,
            "end_utc": catalog_smoke.AUTUMN_V1.end_utc,
            "target_doy": catalog_smoke.AUTUMN_V1.target_doy,
        },
        "retrieval_timestamps_utc": [ts_a, ts_b],
        "candidate_count": len(rows_a),
        "checks": checks,
        "pass": all(checks.values()),
        "global_catalog_fingerprint_sha256":
            fixture["catalog_fingerprint_sha256"],
        "global_selection_fingerprint_sha256":
            fixture["selection_fingerprint_sha256"],
        "s2_catalog_fingerprint_sha256": s2_fp_a,
        "s2_selection_fingerprint_sha256": sel_fp_a,
    }
    if not evidence["pass"]:
        raise RuntimeError(
            "PRE_EXPORT_REPLAY_MISMATCH_STOP: live S2 selection does not "
            f"reproduce the frozen fixture: {json.dumps(checks, indent=2)}")
    return evidence


# ---------------------------------------------------------------------------
# Source images (single scene; native 10 m bands only)
# ---------------------------------------------------------------------------

def load_s2_images(ee: Any, scene_id: str) -> tuple[Any, Any]:
    """Single S2 scene -> (float32 B2/B3/B4/B8 /1e4, byte VALID)."""
    image = (
        ee.ImageCollection(COLLECTION_ID)
        .filter(ee.Filter.eq("system:index", scene_id))
        .first())
    scl = image.select("SCL")
    observed = scl.mask()
    reflectance = (
        image.select(list(TEN_M_BANDS), list(TEN_M_BANDS))
        .divide(float(REFLECTANCE_SCALE))
        .toFloat()
        .updateMask(observed))
    valid = (
        S2_SCL_QA_POLICY.ee_valid_surface(ee, scl)
        .unmask(0).toByte().rename("VALID"))
    return reflectance, valid


def _processing_config(grid: GridSpec,
                       prefixes: dict[str, str]) -> dict[str, Any]:
    return {
        "collection_id": COLLECTION_ID,
        "composite": "NONE_SINGLE_SOURCE_SCENE",
        "reflectance_scale": 1e-4,
        "reflectance_offset": 0.0,
        "masking": (
            "B2/B3/B4/B8 scaled integer SR divided by 10000 -> float32; "
            "reflectance keeps the S2 scene mask (fill stays masked, "
            "never a fake 0); the separate uint8 VALID file carries the "
            "SCL clear decision"),
        "band_order": list(TEN_M_BANDS),
        "excluded_native_20m_bands": ["B11", "B12"],
        "resampling": (
            "NONE; native 10 m bands only; 20 m bands are excluded and "
            "never resampled to 10 m"),
        "native_resolution_m": 10.0,
        "scl_qa_policy_version": S2_SCL_QA_POLICY_VERSION,
        "scl_qa_policy": SCL_QA_POLICY,
        "valid_mask_band_order": ["VALID"],
        "valid_mask_unmasked_to": 0,
        "reflectance_dtype": "float32",
        "valid_mask_dtype": "uint8",
        "crs_transform": list(grid.transform),
        "expected_dimensions_px": [grid.width, grid.height],
        "dimensions_source": (
            "derived by GEE from the region polygon + crsTransform; "
            "fileDimensions omitted because GEE requires multiples of "
            "the shard size (256); landed raster must equal the locked "
            "GridSpec dimensions"),
        "gdrive_folder": GDRIVE_FOLDER,
        "drive_file_prefixes": dict(prefixes),
    }


def build_lock(
    selected: dict[str, Any], grid: GridSpec, region: dict[str, Any],
    rule: dict[str, Any], replay: dict[str, Any],
    config: dict[str, Any], prefixes: dict[str, str],
) -> dict[str, Any]:
    """Freeze every export input BEFORE any EE task is created."""
    tech_hash = canonical_fingerprint(catalog_smoke.ROI_GEOMETRY)
    export_hash = canonical_fingerprint(region)
    grid_hash = canonical_fingerprint(grid.to_dict())
    return {
        "lock_id": LOCK_ID,
        "lock_version": 1,
        "product_id": PRODUCT_ID,
        "created_utc": _now_iso(),
        "collection_id": COLLECTION_ID,
        "composite": "NONE_SINGLE_SOURCE_SCENE",
        "source": {
            "scene_id": selected["scene_id"],
            "product_id": selected.get("product_id"),
            "acquisition_utc": selected.get("acquisition_utc"),
            "mgrs_tile": selected.get("mgrs_tile"),
        },
        "technical_roi": {
            "roi_id": catalog_smoke.ROI_ID,
            "crs_epsg": catalog_smoke.ROI_CRS_EPSG,
            "geometry": catalog_smoke.ROI_GEOMETRY,
            "geometry_sha256": tech_hash,
        },
        "export_roi": {
            "roi_id": EXPORT_ROI_ID,
            "crs_epsg": 4326,
            "grid_crs_epsg": UTM_EPSG,
            "geometry": region,
            "geometry_sha256": export_hash,
            "construction_rule": rule,
        },
        "band_order": list(TEN_M_BANDS),
        "reflectance_scale": 1e-4,
        "scl_qa_policy_version": S2_SCL_QA_POLICY_VERSION,
        "scl_qa_policy": SCL_QA_POLICY,
        "grid": grid.to_dict(),
        "grid_sha256": grid_hash,
        "processing_config_sha256": canonical_fingerprint(config),
        "catalog_fingerprint_sha256":
            replay["global_catalog_fingerprint_sha256"],
        "selection_fingerprint_sha256":
            replay["global_selection_fingerprint_sha256"],
        "s2_catalog_fingerprint_sha256":
            replay["s2_catalog_fingerprint_sha256"],
        "s2_selection_fingerprint_sha256":
            replay["s2_selection_fingerprint_sha256"],
        "gdrive_folder": GDRIVE_FOLDER,
        "drive_file_prefixes": dict(prefixes),
        "freeze_rule": (
            "once written, scene / ROIs / bands / grid are immutable for "
            "this session; a failed task is recorded, never bypassed by a "
            "scene swap"),
    }


# ---------------------------------------------------------------------------
# Real EE batch tasks with full per-poll state history
# ---------------------------------------------------------------------------

def _safe_task_result(raw: dict[str, Any]) -> dict[str, Any]:
    return {key: raw.get(key) for key in _TASK_RESULT_KEYS if key in raw}


def run_task(
    ee: Any, image: Any, region: dict[str, Any], grid: GridSpec,
    prefix: str, store: TaskStore, request_id: str,
) -> dict[str, Any]:
    """Start + bounded-poll ONE real Drive task; persist every poll."""
    # ee 1.7.x batch config rejects a raw GeoJSON dict; pass an explicit
    # EPSG:4326 non-geodesic Geometry (same construction the catalog
    # queries use). The dict stays the hashed/locked geometry; only the
    # API wrapper changes.
    region_geometry = ee.Geometry(region, "EPSG:4326", False)
    task = ee.batch.Export.image.toDrive(
        image=image,
        description=prefix,
        folder=GDRIVE_FOLDER,
        fileNamePrefix=prefix,
        region=region_geometry,
        crs=grid.crs,
        crsTransform=list(grid.transform),
        # fileDimensions is intentionally NOT set: GEE requires it to be a
        # multiple of the shard size (256). Output dimensions are derived
        # from the region polygon + crsTransform, and the landed raster is
        # hard-checked against the locked GridSpec (51x51 at 10 m).
        maxPixels=1_000_000_000,
        fileFormat="GeoTIFF",
    )
    record = store.create(request_id)
    task.start()
    store.mark_enqueued(record.task_id, str(task.id))
    # GEE is READY immediately after start; record it before the first
    # status fetch as the first history observation.
    store.record_poll_state(
        record.task_id, "READY",
        detail="observed immediately after task.start()")
    deadline = time.monotonic() + POLL_TIMEOUT_S
    while time.monotonic() < deadline:
        statuses = ee.data.getTaskStatus(str(task.id))
        raw = dict(statuses[0])
        state = str(raw.get("state"))
        store.record_poll_state(record.task_id, state)
        if state == GEE_DONE:
            store.mark_completed(
                record.task_id, result=_safe_task_result(raw))
            completed = store.get(record.task_id)
            return {
                "request_id": request_id,
                "task_id": completed.backend_task_id,
                "description": prefix,
                "state": STATE_COMPLETED,
                "creation_utc": completed.created_utc,
                "completion_utc": completed.updated_utc,
                "state_history": list(completed.state_history),
                "terminal_result": dict(completed.result),
            }
        if state in GEE_FAILED:
            error = str(raw.get("error_message") or "task failed")
            store.record_attempt_error(
                record.task_id, f"{state}: {error}")
            raise RuntimeError(
                f"GEE export task {task.id} {state}: {error}")
        if state == "RUNNING":
            current = store.get(record.task_id)
            if current.state != STATE_RUNNING:
                store.mark_running(record.task_id)
        time.sleep(POLL_INTERVAL_S)
    raise TimeoutError(
        f"GEE export task {task.id} did not finish within "
        f"{POLL_TIMEOUT_S}s")


def submit_or_resume(
    ee: Any, image: Any, region: dict[str, Any], grid: GridSpec,
    prefix: str, store: TaskStore, request_id: str,
) -> dict[str, Any]:
    """Submit a fresh task, or resume against a stored COMPLETED one.

    Resume is the only idempotent path: if a previous process died AFTER
    the backend task COMPLETED (e.g. during the Drive download), we must
    not create a duplicate export. We re-verify the terminal state with
    GEE, require the Drive artefact to be present, append one resume
    poll to the persisted history, and return the ORIGINAL task id.
    Any other stored state aborts loudly - no silent retries.
    """
    existing = store.get_by_request_id(request_id)
    if existing is None:
        return run_task(ee, image, region, grid, prefix, store, request_id)
    if existing.state != STATE_COMPLETED or not existing.backend_task_id:
        raise SystemExit(
            f"task store already contains {request_id!r} in state "
            f"{existing.state!r}; refusing to create a duplicate export. "
            "Investigate the stored task before re-running.")
    statuses = ee.data.getTaskStatus(str(existing.backend_task_id))
    raw = dict(statuses[0])
    state = str(raw.get("state"))
    if state != GEE_DONE:
        raise SystemExit(
            f"stored COMPLETED task {existing.backend_task_id} now reports "
            f"{state!r}; refusing to proceed")
    driveio.find_latest_file(prefix)  # raises if the output is absent
    store.record_poll_state(
        existing.task_id, GEE_DONE,
        detail="resume verification poll after post-completion crash")
    rec = store.get(existing.task_id)
    print(f"[s2-smoke] RESUMING completed task {rec.backend_task_id} "
          f"for {request_id} (no new export created)")
    return {
        "request_id": request_id,
        "task_id": rec.backend_task_id,
        "description": prefix,
        "state": STATE_COMPLETED,
        "creation_utc": rec.created_utc,
        "completion_utc": rec.updated_utc,
        "state_history": list(rec.state_history),
        "terminal_result": dict(rec.result),
        "resumed": True,
    }


def polled_download(prefix: str) -> tuple[str, bytes]:
    """Wait for Drive propagation, then download the finished GeoTIFF."""
    deadline = time.monotonic() + DRIVE_PROPAGATION_S
    while True:
        try:
            return driveio.download_latest(prefix)
        except driveio.DriveDownloadError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(5)


# ---------------------------------------------------------------------------
# Bundle / provenance checks specific to the two-file S2 product
# ---------------------------------------------------------------------------

def assert_s2_bundle_chain(manifest: dict[str, Any],
                           lock: dict[str, Any]) -> None:
    """Each landed GeoTIFF must map 1:1 to exactly one COMPLETED task."""
    errors: list[str] = []
    tasks = {t["role"]: t for t in manifest.get("export_tasks", [])}
    files = {f["role"]: f for f in manifest.get("landed_files", [])}
    if set(tasks) != {"surface_reflectance_float32", "valid_mask_byte"}:
        errors.append(f"export_tasks roles wrong: {sorted(tasks)}")
    if set(files) != set(tasks):
        errors.append("landed file roles do not match task roles")
    task_ids = [t.get("task_id") for t in tasks.values()]
    if len([i for i in task_ids if i]) != len(set(task_ids)):
        errors.append("task ids missing or duplicated")
    for role, task in tasks.items():
        if task.get("state") != STATE_COMPLETED:
            errors.append(f"{role}: task state {task.get('state')}")
        history = [h.get("state") for h in task.get("state_history", [])]
        if not history or history[0] != "READY" \
                or history[-1] != "COMPLETED":
            errors.append(f"{role}: bad state history {history}")
        if role not in files:
            continue
        if files[role].get("task_id") != task.get("task_id"):
            errors.append(f"{role}: file task_id does not match its task")
        if files[role].get("sha256") != sha256_file(
                files[role]["local_uri"]):
            errors.append(f"{role}: file re-hash differs from manifest")
    source = lock.get("source", {})
    if manifest.get("selected_scene_ids") != [source.get("scene_id")]:
        errors.append("lock scene != manifest selected scene")
    if manifest.get("grid_sha256") != lock.get("grid_sha256"):
        errors.append("grid hash drifted after lock")
    if manifest.get("processing_config_sha256") != \
            lock.get("processing_config_sha256"):
        errors.append("processing config hash drifted after lock")
    if manifest.get("lock_sha256") != canonical_fingerprint(lock):
        errors.append("lock hash does not reproduce")
    if errors:
        raise ProvenanceError(
            "S2 bundle chain broken: " + "; ".join(errors))


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

def run_pipeline(
    *,
    out_dir: Path = DEFAULT_OUT_DIR,
    tasks_path: Path = DEFAULT_TASKS,
    tracked_manifest: Path = TRACKED_MANIFEST,
    fixture_path: Path = FROZEN_FIXTURE,
) -> dict[str, Any]:
    """Execute the whole real S2 byte-pipeline closure; return manifest."""
    if os.environ.get("SPARTINA_GEE_SMOKE_EXPORT") != "1":
        raise SystemExit(
            "real S2 byte export needs SPARTINA_GEE_SMOKE_EXPORT=1 "
            "(explicit operator opt-in; CI default must never export)")
    if configured_project() is None:
        raise SystemExit("export SPARTINA_GEE_PROJECT=<project-id> first")
    initialize()
    import ee

    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    replay = replay_s2_selection(ee, fixture)
    selected = next(
        r for r in fixture["candidate_rows"]
        if r.get("sensor") == "sentinel2" and r.get("selected"))
    scene_id = str(selected["scene_id"])
    scene_date = str(selected["acquisition_date"])
    mgrs = str(selected["mgrs_tile"])

    grid, region, roi_rule = build_export_roi()
    tech_hash = canonical_fingerprint(catalog_smoke.ROI_GEOMETRY)
    export_roi_hash = canonical_fingerprint(region)
    grid_hash = canonical_fingerprint(grid.to_dict())

    date_tag = scene_date.replace("-", "")
    prefixes = {
        "reflectance":
            f"spartina_s2_smoke_{date_tag}_{mgrs}_reflectance",
        "validmask":
            f"spartina_s2_smoke_{date_tag}_{mgrs}_validmask",
    }
    config = _processing_config(grid, prefixes)
    config_hash = canonical_fingerprint(config)

    out_dir.mkdir(parents=True, exist_ok=True)
    lock = build_lock(selected, grid, region, roi_rule, replay,
                      config, prefixes)
    lock_path = out_dir / f"{LOCK_ID}.json"
    lock_path.write_text(
        json.dumps(lock, indent=2, sort_keys=True), encoding="utf-8")
    lock_hash = canonical_fingerprint(lock)

    reflectance_image, valid_image = load_s2_images(ee, scene_id)
    store = TaskStore(tasks_path)
    refl_task = submit_or_resume(
        ee, reflectance_image, region, grid, prefixes["reflectance"],
        store, f"smoke-s2-reflectance-{scene_date}-{mgrs}")
    valid_task = submit_or_resume(
        ee, valid_image, region, grid, prefixes["validmask"],
        store, f"smoke-s2-validmask-{scene_date}-{mgrs}")

    refl_name, refl_bytes = polled_download(prefixes["reflectance"])
    valid_name, valid_bytes = polled_download(prefixes["validmask"])
    refl_path = out_dir / f"{prefixes['reflectance']}.tif"
    valid_path = out_dir / f"{prefixes['validmask']}.tif"
    refl_landed = land_bytes(refl_path, refl_bytes)
    valid_landed = land_bytes(valid_path, valid_bytes)

    # -- raster contract --------------------------------------------------
    refl_info = raster_grid_info(refl_path)
    valid_info = valid_mask_info(valid_path)  # FAILS unless uint8 {0,1}
    assert_grid_matches(refl_info, grid.to_dict())
    assert_grid_matches(valid_info, grid.to_dict())
    for key in ("crs_epsg", "transform", "bounds", "width", "height"):
        if refl_info[key] != valid_info[key]:
            raise ProvenanceError(
                f"VALID grid differs from reflectance grid on {key}: "
                f"{refl_info[key]} vs {valid_info[key]}")
    if refl_info["count"] != 4 or any(
            t != "float32" for t in refl_info["dtypes"]):
        raise ProvenanceError(
            f"reflectance must be 4x float32: {refl_info}")
    if list(refl_info["band_names"]) != list(TEN_M_BANDS):
        raise ProvenanceError(
            f"reflectance band order/descriptions must be "
            f"{list(TEN_M_BANDS)}, got {refl_info['band_names']}")
    sanity = reflectance_sanity_masked(refl_path, valid_path, TEN_M_BANDS)

    qa_consistency = {
        "catalog_qa_roi": {
            "roi_id": catalog_smoke.ROI_ID,
            "crs_epsg": catalog_smoke.ROI_CRS_EPSG,
            "geometry": catalog_smoke.ROI_GEOMETRY,
            "geometry_sha256": tech_hash,
            "roi_total_pixels": selected.get("roi_total_pixels"),
            "roi_cloud_fraction": selected.get("roi_cloud_fraction"),
            "roi_cirrus_fraction": selected.get("roi_cirrus_fraction"),
            "roi_shadow_fraction": selected.get("roi_shadow_fraction"),
            "roi_snow_fraction": selected.get("roi_snow_fraction"),
            "roi_saturated_fraction":
                selected.get("roi_saturated_fraction"),
            "valid_pixel_fraction_observed":
                selected.get("valid_pixel_fraction"),
            "clear_pixel_fraction_scl_4_5_6":
                selected.get("clear_pixel_fraction"),
            "scl_qa_policy_version": S2_SCL_QA_POLICY_VERSION,
            "roi_coverage_fraction": selected.get("roi_coverage_fraction"),
        },
        "export_sub_roi_qa": {
            "roi_id": EXPORT_ROI_ID,
            "crs_epsg": 4326,
            "grid_crs_epsg": UTM_EPSG,
            "geometry": region,
            "geometry_sha256": export_roi_hash,
            "total_pixel_count": valid_info["total_pixel_count"],
            "valid_pixel_count": valid_info["valid_pixel_count"],
            "valid_fraction": valid_info["valid_fraction"],
            "unique_values": valid_info["unique_values"],
            "unique_value_counts": valid_info["unique_value_counts"],
        },
        "equality_test": (
            "NOT_PERFORMED: catalog QA ROI (0.02 deg box) and the export "
            "sub-ROI (deterministic ~500 m grid footprint) are different "
            "geometries; per-scene fractions are never compared with an "
            "equality test"),
        "logical_check": (
            "catalog scene ROI cloud_fraction == 0 (clear 0.8627); a "
            "fully-zero VALID mask in the sub-ROI would contradict the "
            "cloud-free scene; valid_pixel_count must be > 0"),
        "logical_check_pass": valid_info["valid_pixel_count"] > 0,
    }
    if not qa_consistency["logical_check_pass"]:
        raise ProvenanceError("catalog vs landed QA logic inconsistent")

    export_tasks = []
    for role, task, name in (
            ("surface_reflectance_float32", refl_task, refl_name),
            ("valid_mask_byte", valid_task, valid_name)):
        export_tasks.append({
            "role": role,
            "drive_file_name": name,
            "drive_folder": GDRIVE_FOLDER,
            "task_id": task["task_id"],
            "request_id": task["request_id"],
            "description": task["description"],
            "state": task["state"],
            "creation_utc": task["creation_utc"],
            "completion_utc": task["completion_utc"],
            "state_history": task["state_history"],
            "terminal_result": task["terminal_result"],
        })

    landed_files = [
        {**refl_landed, "role": "surface_reflectance_float32",
         "band_order": list(TEN_M_BANDS), "format": "GeoTIFF",
         "grid_verified": True, "drive_file_name": refl_name,
         "drive_folder": GDRIVE_FOLDER, "task_id": refl_task["task_id"]},
        {**valid_landed, "role": "valid_mask_byte",
         "band_order": ["VALID"], "format": "GeoTIFF",
         "grid_verified": True, "drive_file_name": valid_name,
         "drive_folder": GDRIVE_FOLDER, "task_id": valid_task["task_id"]},
    ]

    bundle_payload = {
        "product_id": PRODUCT_ID,
        "scene_id": scene_id,
        "product_id_scene": selected.get("product_id"),
        "acquisition_utc": selected.get("acquisition_utc"),
        "processing_config_sha256": config_hash,
        "grid": grid.to_dict(),
        "files": sorted(
            ({"role": f["role"], "drive_file_name": f["drive_file_name"],
              "sha256": f["sha256"], "size_bytes": f["size_bytes"]}
             for f in landed_files),
            key=lambda item: item["role"]),
    }
    bundle_fingerprint = canonical_fingerprint(bundle_payload)

    request = ExportRequest(
        request_id=f"smoke-s2-{scene_date}-{mgrs}",
        sensor_name="sentinel2",
        tile_id=EXPORT_ROI_ID,
        start_date=catalog_smoke.AUTUMN_V1.start_utc,
        end_date=catalog_smoke.AUTUMN_V1.end_utc,
        destination_uri=(
            f"gdrive://{GDRIVE_FOLDER}/{prefixes['reflectance']}"),
        bands=TEN_M_BANDS,
        crs_epsg=grid.crs_epsg,
        resolution_m=10.0,
        grid_spec=grid.to_dict(),
        source_scene_ids=(scene_id,),
        science_stream="sentinel_10m",
    )
    task_handle = ExportTask(
        task_id=str(refl_task["task_id"]),
        request_id=request.request_id,
        state=STATE_COMPLETED,
        messages=(
            f"ee.batch.Export.image.toDrive reflectance -> {GDRIVE_FOLDER} "
            f"(task {refl_task['task_id']})",
            f"ee.batch.Export.image.toDrive validmask -> {GDRIVE_FOLDER} "
            f"(task {valid_task['task_id']})",
        ))
    candidate_scenes = [
        dict(r) for r in fixture["candidate_rows"]
        if r.get("sensor") == "sentinel2"]
    manifest = build_data_factory_manifest(
        request, task_handle,
        candidate_scenes=candidate_scenes,
        selected_scene_ids=[scene_id],
        grid_spec=grid.to_dict(),
        processing_config=config,
        landed_files=landed_files,
        roi={
            "technical_roi": {
                "roi_id": catalog_smoke.ROI_ID,
                "crs_epsg": catalog_smoke.ROI_CRS_EPSG,
                "geometry": catalog_smoke.ROI_GEOMETRY,
                "geometry_sha256": tech_hash,
            },
            "export_roi": {
                "roi_id": EXPORT_ROI_ID,
                "crs_epsg": 4326,
                "geometry": region,
                "geometry_sha256": export_roi_hash,
                "construction_rule": roi_rule,
            },
        },
        notes=(
            "Issue #6 M1.6c: first REAL Sentinel-2 byte pipeline (generic "
            "EE transport/provenance validation). Single previously-selected "
            "scene, native 10 m B2/B3/B4/B8 float32 /10000 + byte SCL "
            "VALID, ~500 m deterministic export ROI. NOT a Landsat byte "
            "validation (L8_REAL_EXPORT_NOT_OBSERVED_UNDER_PREDECLARED_"
            "WINDOWS) and NOT a Sentinel-1 byte validation."))

    manifest["export_task"] = {
        "task_id": refl_task["task_id"],
        "state": STATE_COMPLETED,
        "messages": list(task_handle.messages),
        "creation_utc": refl_task["creation_utc"],
        "completion_utc": valid_task["completion_utc"],
        "task_id_valid_mask": valid_task["task_id"],
        "per_file_tasks": "see export_tasks for full state histories",
    }
    manifest["export_tasks"] = export_tasks
    manifest["query"] = {
        "frozen_fixture": str(fixture_path),
        "window": replay["window"],
        "pre_export_replay": replay,
    }
    manifest["source_product"] = {
        "scene_id": scene_id,
        "product_id": selected.get("product_id"),
        "acquisition_utc": selected.get("acquisition_utc"),
        "acquisition_date": scene_date,
        "mgrs_tile": mgrs,
        "spacecraft": selected.get("spacecraft"),
        "processing_baseline": selected.get("processing_baseline"),
        "relative_orbit_number": selected.get("relative_orbit_number"),
        "selection_metrics": {
            "roi_cloud_fraction": selected.get("roi_cloud_fraction"),
            "clear_pixel_fraction": selected.get("clear_pixel_fraction"),
            "valid_pixel_fraction": selected.get("valid_pixel_fraction"),
            "roi_coverage_fraction":
                selected.get("roi_coverage_fraction"),
            "selection_rank": selected.get("selection_rank"),
            "selection_score": selected.get("selection_score"),
            "selection_reason": selected.get("selection_reason"),
        },
    }
    manifest["scl_qa_policy"] = SCL_QA_POLICY
    manifest["raster_verification"] = {
        "reflectance": refl_info,
        "valid_mask": valid_info,
    }
    manifest["reflectance_sanity"] = sanity
    manifest["qa_consistency"] = qa_consistency
    manifest["lock_path"] = str(lock_path)
    manifest["lock_sha256"] = lock_hash
    manifest["lock"] = lock
    manifest["grid_sha256"] = grid_hash
    manifest["processing_config_sha256"] = config_hash
    manifest["bundle"] = {
        "fingerprint_sha256": bundle_fingerprint,
        "payload": bundle_payload,
    }
    manifest["product_scope"] = {
        "product_id": PRODUCT_ID,
        "purpose": (
            "generic real EE batch export / Drive landing / raster / "
            "checksum / provenance infrastructure validation"),
        "not_for": [
            "final Zhejiang dataset", "Sentinel science stack",
            "training data", "benchmark sample",
            "Landsat byte/scaling/availability validation",
            "Sentinel-1 byte validation"],
        "landsat_real_byte_status":
            "L8_REAL_EXPORT_NOT_OBSERVED_UNDER_PREDECLARED_WINDOWS",
        "sentinel1_real_byte_status": "NOT_YET_VERIFIED",
    }
    manifest["project_id"] = configured_project()
    manifest["code"] = git_context(REPO_ROOT)
    manifest["environment"] = runtime_environment()

    assert_s2_bundle_chain(manifest, lock)
    assert_provenance_chain(manifest)

    work_manifest = out_dir / "gee_real_s2_export_smoke_v1.manifest.json"
    work_manifest.write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    tracked_manifest.parent.mkdir(parents=True, exist_ok=True)
    tracked_manifest.write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    summary = {
        "product_id": PRODUCT_ID,
        "scene_id": scene_id,
        "product_id_scene": selected.get("product_id"),
        "acquisition_utc": selected.get("acquisition_utc"),
        "mgrs_tile": mgrs,
        "global_catalog_fingerprint":
            replay["global_catalog_fingerprint_sha256"],
        "global_selection_fingerprint":
            replay["global_selection_fingerprint_sha256"],
        "s2_catalog_fingerprint":
            replay["s2_catalog_fingerprint_sha256"],
        "s2_selection_fingerprint":
            replay["s2_selection_fingerprint_sha256"],
        "export_roi_hash": export_roi_hash,
        "grid": grid.to_dict(),
        "tasks": {
            "reflectance": refl_task["task_id"],
            "validmask": valid_task["task_id"]},
        "task_states": {
            "reflectance": [
                h["state"] for h in refl_task["state_history"]],
            "validmask": [
                h["state"] for h in valid_task["state_history"]]},
        "landed": {
            "reflectance": {
                "path": str(refl_path), "name": refl_name,
                **refl_landed},
            "validmask": {
                "path": str(valid_path), "name": valid_name,
                **valid_landed}},
        "bundle_fingerprint_sha256": bundle_fingerprint,
        "lock_path": str(lock_path),
        "lock_sha256": lock_hash,
        "reflectance_raster": {
            "crs_epsg": refl_info["crs_epsg"],
            "transform": refl_info["transform"],
            "width": refl_info["width"], "height": refl_info["height"],
            "dtypes": refl_info["dtypes"],
            "band_names": refl_info["band_names"],
            "nodata": refl_info["nodata"]},
        "valid_fraction": valid_info["valid_fraction"],
        "valid_unique_values": valid_info["unique_values"],
        "reflectance_scaling_check_pass":
            sanity["scaling_check_pass"],
        "qa_logical_check_pass": qa_consistency["logical_check_pass"],
        "provenance_chain": "PASS",
        "manifest_work": str(work_manifest),
        "manifest_tracked": str(tracked_manifest),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--tasks", default=str(DEFAULT_TASKS))
    parser.add_argument("--tracked-manifest", default=str(TRACKED_MANIFEST))
    parser.add_argument("--fixture", default=str(FROZEN_FIXTURE))
    args = parser.parse_args()
    run_pipeline(
        out_dir=Path(args.out_dir),
        tasks_path=Path(args.tasks),
        tracked_manifest=Path(args.tracked_manifest),
        fixture_path=Path(args.fixture))


if __name__ == "__main__":
    main()
