#!/usr/bin/env python3
"""M2.1b Issue #13 -- controlled REAL pixel exports for the pilot plan.

Runs ONLY with SPARTINA_M21B_EXPORT=1 and SPARTINA_GEE_PROJECT set.
Scope is hard-locked to datasets/manifests/zhejiang_m21b_pilot_event_plan_v0.json:
13 planned products (~0.2 GB), 8 fixed 10 km cells, 2022 autumn window.

Per product it:
* re-derives the locked GridSpec from the fixed cell geometry (10 m for
  S2/S1, native 30 m for Landsat; never upsampled);
* exports same-DATATAKE multi-tile S2 events with one ordered
  ee.ImageCollection.mosaic (no cross-date merge), B2/B3/B4/B8 float32
  DN/10000 plus a uint8 SCL VALID file (classes 4/5/6 valid, 11 invalid);
* exports the first eligible L8/L9 scene as physical C2 L2 SR float32
  (scale 2.75e-5, offset -0.2), uint8 QA VALID, and raw uint16 QA_PIXEL;
* exports S1 IW VV+VH float32 with the identity transform (already dB;
  a second 10*log10 is forbidden), ASC/DESC never mixed;
* lands bytes via Drive, validates grid/dtype/bounds, computes SHA-256,
  audits S2 reflectance, Landsat physical scaling, and S1 dB ranges;
* writes per-product manifests and the aggregate pilot manifest with
  tide statuses (observed MISSING; modeled NOT_DEPLOYED), label status,
  rights, and full provenance. Resume is idempotent via the task store.
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
sys.path.insert(0, str(REPO_ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import rasterio  # noqa: E402

from spartina.data.gee import driveio, landsat  # noqa: E402
from spartina.data.gee.auth import configured_project, initialize  # noqa: E402
from spartina.data.gee.export import land_bytes  # noqa: E402
from spartina.data.gee.grid import (  # noqa: E402
    GridSpec,
    assert_no_forced_upsampling,
    covering_grid,
)
from spartina.data.gee.provenance import (  # noqa: E402
    ProvenanceError,
    assert_grid_matches,
    git_context,
    raster_grid_info,
    reflectance_sanity_masked,
    runtime_environment,
    sha256_file,
    valid_mask_info,
)
from spartina.data.gee.selection import canonical_fingerprint  # noqa: E402
from spartina.data.gee.sentinel2 import (  # noqa: E402
    REFLECTANCE_SCALE,
    S2_SCL_QA_POLICY,
    S2_SCL_QA_POLICY_VERSION,
    TEN_M_BANDS,
)
from spartina.data.gee.tasks import STATE_COMPLETED, TaskStore  # noqa: E402
from spartina.data.zhejiang.m21b_pilot import s1_db_audit  # noqa: E402

PLAN_JSON = REPO_ROOT / "datasets/manifests/zhejiang_m21b_pilot_event_plan_v0.json"
CELL_REGISTRY = REPO_ROOT / "datasets/manifests/zhejiang_analysis_cells_v0.csv"
OVERLAP_CSV = REPO_ROOT / "datasets/manifests/zhejiang_label_cell_overlap_v0_1.csv"
RIGHTS_CSV = REPO_ROOT / "datasets/manifests/zhejiang_label_rights_v0.csv"
WORK_DIR = REPO_ROOT / "work" / "m21b"
PRODUCT_DIR = WORK_DIR / "products"
MANIFEST_DIR = WORK_DIR / "manifests"
TASK_STORE = WORK_DIR / "tasks" / "task_store.json"
OUT_CSV = REPO_ROOT / "datasets/manifests/zhejiang_m21b_pilot_v0.csv"
OUT_JSON = REPO_ROOT / "datasets/manifests/zhejiang_m21b_pilot_v0.json"

GDRIVE_FOLDER = "SpartinaEarthM21b"
CRS_EPSG = 32651
POLL_INTERVAL_S = 10
POLL_TIMEOUT_S = 2400
DRIVE_PROPAGATION_S = 90
GEE_DONE = "COMPLETED"
GEE_FAILED = {"FAILED", "CANCELLED", "CANCEL_REQUESTED"}
TASK_RESULT_KEYS = (
    "state", "description", "task_type", "attempt",
    "creation_timestamp_ms", "start_timestamp_ms",
    "update_timestamp_ms", "additional_info")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()  # noqa: UP017


# ---------------------------------------------------------------------------
# Grids / regions
# ---------------------------------------------------------------------------

def cell_bounds(cell_id: str) -> tuple[float, float, float, float]:
    reg = pd.read_csv(CELL_REGISTRY)
    row = reg[(reg["cell_id"] == cell_id)
              & (reg["cell_size_m"] == 10000)].iloc[0]
    return (float(row["westx_easting_m"]),
            float(row["southy_northing_m"]),
            float(row["eastx_easting_m"]),
            float(row["northy_northing_m"]))


def grid_and_region(
    bounds: tuple[float, float, float, float], pixel_m: float,
) -> tuple[GridSpec, dict[str, Any]]:
    grid = covering_grid(bounds, CRS_EPSG, pixel_m)
    assert_no_forced_upsampling(pixel_m, grid.pixel_x_m)
    # Export region is expressed in the PROJECTED CRS, never round-tripped
    # through WGS84: a 10 km WGS polygon reprojects back ~10 m too wide and
    # creates an extra pixel column.
    region = {"type": "Rectangle", "crs": grid.crs,
              "coordinates": [list(grid.bounds)]}
    return grid, region


# ---------------------------------------------------------------------------
# Image builders (all provenance-sensitive decisions live here)
# ---------------------------------------------------------------------------

def build_s2_images(ee: Any, scene_ids: list[str]) -> tuple[Any, Any, dict[str, Any]]:
    col = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
           .filter(ee.Filter.inList("system:index", scene_ids)))
    n = int(col.size().getInfo())
    if n != len(scene_ids):
        raise ProvenanceError(
            f"S2 catalog returned {n} scenes for {scene_ids}; abort")
    # Deterministic MGRS-tile ordering, identical for reflectance and QA.
    ordered = col.sort("MGRS_TILE")
    datatakes = sorted(set(
        col.aggregate_array("DATATAKE_IDENTIFIER").getInfo()))
    dates = sorted({s[:8] for s in scene_ids})
    if len(datatakes) != 1:
        raise ProvenanceError(
            f"cross-datatake merge forbidden, got {datatakes}")
    if len(dates) != 1:
        raise ProvenanceError(
            f"cross-date mosaic forbidden, got dates {dates}")
    tiles = sorted(
        set(col.aggregate_array("MGRS_TILE").getInfo()))

    def _observed4(img: Any) -> Any:
        # All FOUR native 10 m bands must carry a value; SCL alone can be
        # present at a granule edge where B2/B3/B4/B8 are missing.
        observed = img.select("B2").mask()
        for band in ("B3", "B4", "B8"):
            observed = observed.And(img.select(band).mask())
        return observed

    def _refl_one(img: Any) -> Any:
        return (img.select(list(TEN_M_BANDS), list(TEN_M_BANDS))
                .divide(float(REFLECTANCE_SCALE)).toFloat()
                .updateMask(_observed4(img)))

    def _valid_one(img: Any) -> Any:
        return (S2_SCL_QA_POLICY.ee_valid_surface(ee, img.select("SCL"))
                .toByte().updateMask(_observed4(img)))

    reflectance = ordered.map(_refl_one).mosaic()
    valid_ordered = ordered.map(_valid_one)
    # Mosaic while outside-footprint stays masked; fill only at the end.
    valid = valid_ordered.mosaic().unmask(0).rename("VALID")
    config = {
        "collection_id": "COPERNICUS/S2_SR_HARMONIZED",
        "composite": "SAME_DATATAKE_ORDERED_MOSAIC" if len(tiles) > 1
                     else "NONE_SINGLE_SOURCE_SCENE",
        "tile_order": tiles,
        "datatake_identifier": datatakes[0],
        "scene_date": dates[0],
        "reflectance_scale": float(REFLECTANCE_SCALE),
        "reflectance_offset": 0.0,
        "band_order": list(TEN_M_BANDS),
        "resampling": "NONE; native 10 m bands only; 20 m bands excluded",
        "native_resolution_m": 10.0,
        "scl_qa_policy_version": S2_SCL_QA_POLICY_VERSION,
        "scl_qa_policy": S2_SCL_QA_POLICY.to_manifest_dict(),
        "valid_definition": (
            "SCL valid-surface (classes 4/5/6) AND all four native 10 m "
            "bands observed in the same source tile; masks are evaluated "
            "before the same-datatake mosaic"),
    }
    return reflectance, valid, config


def build_landsat_images(
    ee: Any, sensor: str, scene_id: str,
) -> tuple[Any, Any, Any, dict[str, Any]]:
    img = (ee.ImageCollection(f"LANDSAT/LC0{'8' if sensor == 'landsat8' else '9'}/C02/T1_L2")
           .filter(ee.Filter.eq("system:index", scene_id)).first())
    sr_bands = list(landsat.sr_bands(sensor))
    qa = img.select("QA_PIXEL")
    fill_mask = qa.bitwiseAnd(1 << landsat.QA_FILL).eq(0)
    sr = (img.select(sr_bands).multiply(landsat.LANDSAT_C2_SR_MULTIPLY)
          .add(landsat.LANDSAT_C2_SR_ADD).toFloat().updateMask(fill_mask))
    valid = _landsat_valid(img)
    qa_raw = img.select("QA_PIXEL").toUint16().rename("QA_PIXEL")
    props = {
        "wrs_path": img.get("WRS_PATH").getInfo(),
        "wrs_row": img.get("WRS_ROW").getInfo(),
        "landsat_product_id": img.get("LANDSAT_PRODUCT_ID").getInfo(),
        "spacecraft_id": img.get("SPACECRAFT_ID").getInfo(),
        "cloud_cover": img.get("CLOUD_COVER").getInfo(),
        "cloud_cover_land": img.get("CLOUD_COVER_LAND").getInfo(),
        "collection_category": img.get("COLLECTION_CATEGORY").getInfo(),
    }
    config = {
        "collection_id": f"LANDSAT/LC0{'8' if sensor == 'landsat8' else '9'}/C02/T1_L2",
        "composite": "NONE_SINGLE_SOURCE_SCENE",
        "scene_id": scene_id,
        "sr_band_order": sr_bands,
        "sr_scale": landsat.LANDSAT_C2_SR_MULTIPLY,
        "sr_offset": landsat.LANDSAT_C2_SR_ADD,
        "native_resolution_m": 30.0,
        "upsampling": "FORBIDDEN; 30 m product stays on the 30 m grid",
        "qa_contract": {
            "valid": "QA_PIXEL clear bit6 and none of fill/dilated/cirrus/"
                     "cloud/shadow/snow, plus QA_RADSAT == 0",
            "raw_qa_exported_separately": True},
        "properties": props,
    }
    return sr, valid, qa_raw, config


def _landsat_valid(img: Any) -> Any:
    qa = img.select("QA_PIXEL")
    radsat = img.select("QA_RADSAT")
    blocked = [landsat.QA_FILL, landsat.QA_DILATED_CLOUD, landsat.QA_CIRRUS,
               landsat.QA_CLOUD, landsat.QA_CLOUD_SHADOW, landsat.QA_SNOW]
    mask = qa.bitwiseAnd(1 << landsat.QA_CLEAR).neq(0)
    for bit in blocked:
        mask = mask.And(qa.bitwiseAnd(1 << bit).eq(0))
    mask = mask.And(radsat.eq(0))
    return mask.toByte().unmask(0).rename("VALID")


def build_s1_image(ee: Any, scene_id: str) -> tuple[Any, dict[str, Any]]:
    img = (ee.ImageCollection("COPERNICUS/S1_GRD")
           .filter(ee.Filter.eq("system:index", scene_id)).first())
    props = {
        "product_identifier": img.get("productIdentifier").getInfo(),
        "orbit_direction": img.get("orbitProperties_pass").getInfo(),
        "relative_orbit": img.get("relativeOrbitNumber_start").getInfo(),
        "platform": img.get("platform_number").getInfo(),
        "instrument_mode": img.get("instrumentMode").getInfo(),
        "polarisations": img.get("transmitterReceiverPolarisation").getInfo(),
        "resolution_meters": img.get("resolution_meters").getInfo(),
    }
    image = img.select(["VV", "VH"], ["VV", "VH"]).toFloat()
    config = {
        "collection_id": "COPERNICUS/S1_GRD",
        "composite": "NONE_SINGLE_SOURCE_SCENE",
        "transform": "IDENTITY_SELECT_ONLY",
        "units": "sigma0 dB as ingested by GEE",
        "log10_applied": False,
        "band_order": ["VV", "VH"],
        "native_resolution_m": float(props["resolution_meters"]),
        "pass_kept_separate": True,
        "properties": props,
    }
    return image, config


# ---------------------------------------------------------------------------
# Task lifecycle (same proven pattern as the S2 smoke; product-local store)
# ---------------------------------------------------------------------------

def _safe_result(raw: dict[str, Any]) -> dict[str, Any]:
    return {k: raw.get(k) for k in TASK_RESULT_KEYS if k in raw}


def submit_or_resume(
    ee: Any, image: Any, region: dict[str, Any], grid: GridSpec,
    prefix: str, store: TaskStore, request_id: str,
) -> dict[str, Any]:
    existing = store.get_by_request_id(request_id)
    # Projected-CRS rectangle: exact cell square, no WGS84 round-trip.
    coords = region["coordinates"][0]
    region_geometry = ee.Geometry.Rectangle(coords, region["crs"], False)
    if existing is not None:
        if existing.state != STATE_COMPLETED or not existing.backend_task_id:
            raise SystemExit(
                f"task store has {request_id!r} in state "
                f"{existing.state!r}; investigate, no duplicate export")
        statuses = ee.data.getTaskStatus(str(existing.backend_task_id))
        if str(statuses[0].get("state")) != GEE_DONE:
            raise SystemExit(
                f"stored COMPLETED task {existing.backend_task_id} now "
                f"{statuses[0].get('state')!r}")
        driveio.find_latest_file(prefix)
        store.record_poll_state(
            existing.task_id, GEE_DONE, detail="resume verification poll")
        rec = store.get(existing.task_id)
        return {"task_id": rec.backend_task_id,
                "state": STATE_COMPLETED,
                "state_history": list(rec.state_history),
                "terminal_result": dict(rec.result), "resumed": True}

    task = ee.batch.Export.image.toDrive(
        image=image, description=prefix, folder=GDRIVE_FOLDER,
        fileNamePrefix=prefix, region=region_geometry, crs=grid.crs,
        crsTransform=list(grid.transform),
        # dimensions pins width/height: otherwise GEE derives the origin
        # from the region polygon (server-side geographic round-trip adds
        # one pixel column for 10 km cells) and ignores transform c/f.
        dimensions=[grid.width, grid.height],
        maxPixels=1_000_000_000, fileFormat="GeoTIFF")
    record = store.create(request_id)
    task.start()
    store.mark_enqueued(record.task_id, str(task.id))
    store.record_poll_state(record.task_id, "READY",
                           detail="observed after task.start()")
    deadline = time.monotonic() + POLL_TIMEOUT_S
    while time.monotonic() < deadline:
        raw = dict(ee.data.getTaskStatus(str(task.id))[0])
        state = str(raw.get("state"))
        store.record_poll_state(record.task_id, state)
        if state == GEE_DONE:
            store.mark_completed(record.task_id, result=_safe_result(raw))
            rec = store.get(record.task_id)
            return {"task_id": rec.backend_task_id,
                    "state": STATE_COMPLETED,
                    "state_history": list(rec.state_history),
                    "terminal_result": dict(rec.result), "resumed": False}
        if state in GEE_FAILED:
            store.record_attempt_error(
                record.task_id, f"{state}: {raw.get('error_message')}")
            raise RuntimeError(
                f"GEE task {task.id} {state}: {raw.get('error_message')}")
        time.sleep(POLL_INTERVAL_S)
    raise TimeoutError(f"task {task.id} timed out after {POLL_TIMEOUT_S}s")


def polled_download(prefix: str) -> tuple[str, bytes]:
    deadline = time.monotonic() + DRIVE_PROPAGATION_S
    while True:
        try:
            return driveio.download_latest(prefix)
        except driveio.DriveDownloadError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(5)


def server_recompute_stats(
    ee: Any, image: Any, region: dict[str, Any], grid: GridSpec,
    bands: list[str],
) -> dict[str, float]:
    """Independently recompute min/max/percentiles server-side.

    The exported GeoTIFF is byte-identical in value to the source image
    only if these numbers match the landed-raster statistics; a missed
    rescale or a second 10*log10 cannot survive this comparison.
    """
    rect = ee.Geometry.Rectangle(region["coordinates"][0],
                                 region["crs"], False)
    reducer = (ee.Reducer.minMax()
               .combine(ee.Reducer.percentile([1, 50, 99]),
                        sharedInputs=True))
    raw = (image.select(bands).reduceRegion(
        reducer=reducer, geometry=rect, crs=grid.crs,
        scale=grid.pixel_x_m, bestEffort=False, tileScale=4)
        .getInfo())
    out: dict[str, float] = {}
    for band in bands:
        for src, dst in (("min", "min"), ("max", "max"),
                         ("p1", "p01"), ("p50", "p50"),
                         ("p99", "p99")):
            out[f"{band}_{dst}"] = float(raw[f"{band}_{src}"])
    return out


def compare_landed_vs_server(
    landed: dict[str, float], server: dict[str, float], bands: list[str],
    *, extrema_tol: float, pct_tol: float,
) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    deltas: dict[str, float] = {}
    for band in bands:
        for stat, tol in (("min", extrema_tol), ("max", extrema_tol),
                          ("p01", pct_tol), ("p50", pct_tol),
                          ("p99", pct_tol)):
            key = f"{band}_{stat}"
            delta = abs(landed[key] - server[key])
            deltas[key] = round(delta, 4)
            checks[key] = delta <= tol
    return {"landed": landed, "server_recompute": server,
            "abs_deltas": deltas, "tolerance_db":
            {"extrema": extrema_tol, "percentiles": pct_tol},
            "checks": checks, "pass": all(checks.values())}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def band_stats(path: str, bands: list[str], *, is_db: bool = False) -> dict[str, float]:
    with rasterio.open(path) as src:
        out: dict[str, float] = {}
        for i, name in enumerate(bands, start=1):
            arr = src.read(i, masked=True)
            vals = arr.compressed()
            if vals.size == 0:
                raise ProvenanceError(f"{path}:{name} no observed pixels")
            pct = np.percentile(vals, [0, 1, 50, 99, 100])
            prefix = name.lower() if not is_db else name
            out.update({
                f"{prefix}_min": float(pct[0]),
                f"{prefix}_p01": float(pct[1]),
                f"{prefix}_p50": float(pct[2]),
                f"{prefix}_p99": float(pct[3]),
                f"{prefix}_max": float(pct[4]),
                f"{prefix}_valid_px": int(vals.size)})
        return out


def landsat_scaling_audit(stats: dict[str, float]) -> dict[str, Any]:
    # Physical C2 L2 SR lives roughly in [-0.2, 1.2]; extrema beyond that
    # indicate a missing scale/offset application or corrupt bytes.
    checks: dict[str, bool] = {}
    for band in ("sr_b1", "sr_b2", "sr_b3", "sr_b4", "sr_b5", "sr_b6",
                 "sr_b7"):
        lo = stats.get(f"{band}_p01")
        hi = stats.get(f"{band}_p99")
        if lo is None or hi is None:
            continue
        checks[f"{band}_physical_range"] = (lo >= -0.30 and hi <= 1.3)
        checks[f"{band}_ordered"] = (
            stats[f"{band}_min"] <= lo <= stats[f"{band}_p50"] <= hi
            <= stats[f"{band}_max"])
    return {"plausible_physical_sr_range": [-0.30, 1.30],
            "checks": checks, "pass": all(checks.values())}


# ---------------------------------------------------------------------------
# Per-product orchestration
# ---------------------------------------------------------------------------

def label_and_rights(cell_id: str) -> dict[str, Any]:
    ov = pd.read_csv(OVERLAP_CSV)
    rights = pd.read_csv(RIGHTS_CSV).set_index("asset_id")
    rows = ov[(ov["cell_id"] == cell_id) & (ov["cell_size_m"] == 10000)]
    label: dict[str, Any] = {"cell_id": cell_id, "tiers": [],
                            "label_bytes_copied": False}
    for _, r in rows.iterrows():
        rid = str(r["asset_id"])
        right = rights.loc[rid] if rid in rights.index else None
        label["tiers"].append({
            "asset_id": rid, "label_tier": r["label_tier"],
            "status_bay_scoped": r["cell_label_status_bay_scoped"],
            "positive_area_km2_bay_clip":
                float(r["positive_area_km2_bay_clip"]),
            "redistribution": (str(right["public_redistribution_allowed"])
                               if right is not None else "UNKNOWN"),
            "scientific_analysis": (str(right["scientific_analysis_allowed"])
                                    if right is not None else "UNKNOWN"),
            "internal_training": (str(right["internal_training_allowed"])
                                  if right is not None else "UNKNOWN"),
        })
    return label


def tide_block() -> dict[str, Any]:
    return {
        "observed_tide_status": "MISSING",
        "modeled_tide_status": "NOT_DEPLOYED",
        "modeled_tide_selection": "FES2022b_SELECTED_NOT_DEPLOYED",
        "inundation_proxy_status": "MISSING",
        "water_fraction_proxy_status": "MISSING",
        "no_fabricated_tide": True,
    }


def export_one(
    ee: Any, product: dict[str, Any], store: TaskStore,
) -> dict[str, Any]:
    pid = str(product["product_id"])
    cid = str(product["cell_id"])
    sensor = str(product["sensor"])
    scene_ids = str(product["scene_ids"]).split("|")
    bounds = cell_bounds(cid)
    per_product_manifest = MANIFEST_DIR / f"{pid}.json"
    if per_product_manifest.exists():
        cached = json.loads(per_product_manifest.read_text())
        for f in cached["landed_files"]:
            if sha256_file(f["local_uri"]) != f["sha256"]:
                raise ProvenanceError(
                    f"{pid}: cached file re-hash mismatch; refusing")
        print(f"[m21b] {pid} already landed and verified; skipping")
        return dict(cached)

    pixel_m = 30.0 if sensor.startswith("landsat") else 10.0
    grid, region = grid_and_region(bounds, pixel_m)
    date_tag = str(product["event_utc"])[:10].replace("-", "")
    # r1/r2 region; r3 pinned dimensions; r4 fixed the Landsat VALID byte;
    # r5 intersects S2 VALID with the four-band observation mask (a multi-
    # tile seam had 10 px SCL-valid but surface-band-missing).
    rev = "r5" if sensor == "sentinel2" else "r4"
    files: list[dict[str, Any]] = []
    tasks: list[dict[str, Any]] = []
    raster_checks: dict[str, Any] = {}

    def _land(prefix: str, task_info: dict[str, Any], role: str) -> None:
        name, data = polled_download(prefix)
        path = PRODUCT_DIR / f"{prefix}.tif"
        landed = land_bytes(path, data)
        files.append({**landed, "role": role, "drive_file_name": name,
                      "drive_folder": GDRIVE_FOLDER,
                      "task_id": task_info["task_id"],
                      "local_uri": str(path), "grid_verified": False})
        tasks.append({"role": role, "prefix": prefix, **task_info})

    if sensor == "sentinel2":
        refl_img, valid_img, proc = build_s2_images(ee, scene_ids)
        p1 = f"spartina_m21b_{pid}_sr_{date_tag}_{rev}"
        p2 = f"spartina_m21b_{pid}_valid_{date_tag}_{rev}"
        _land(p1, submit_or_resume(ee, refl_img, region, grid, p1, store,
                                   f"{pid}:reflectance:{rev}"), "sr_float32")
        _land(p2, submit_or_resume(ee, valid_img, region, grid, p2, store,
                                   f"{pid}:valid:{rev}"), "valid_byte")
        sr_info = raster_grid_info(files[-2]["local_uri"])
        vd_info = valid_mask_info(files[-1]["local_uri"])
        assert_grid_matches(sr_info, grid.to_dict())
        assert_grid_matches(vd_info, grid.to_dict())
        if sr_info["count"] != 4 or sr_info["dtypes"] != ["float32"] * 4:
            raise ProvenanceError(f"{pid}: SR must be 4x float32")
        if list(sr_info["band_names"]) != list(TEN_M_BANDS):
            raise ProvenanceError(f"{pid}: band order {sr_info['band_names']}")
        sanity = reflectance_sanity_masked(
            files[-2]["local_uri"], files[-1]["local_uri"], TEN_M_BANDS)
        raster_checks = {"reflectance_sanity": sanity,
                         "valid_mask": {k: vd_info[k] for k in
                                        ("valid_fraction", "unique_values",
                                         "unique_value_counts",
                                         "total_pixel_count",
                                         "valid_pixel_count")}}
        if not sanity["scaling_check_pass"]:
            raise ProvenanceError(f"{pid}: reflectance scaling sanity fail")
        native_resolution = 10.0
        stream = "sentinel_10m"

    elif sensor.startswith("landsat"):
        sr_img, valid_img, qa_img, proc = build_landsat_images(
            ee, sensor, scene_ids[0])
        p1 = f"spartina_m21b_{pid}_sr_{date_tag}_{rev}"
        p2 = f"spartina_m21b_{pid}_valid_{date_tag}_{rev}"
        p3 = f"spartina_m21b_{pid}_qapixel_{date_tag}_{rev}"
        _land(p1, submit_or_resume(ee, sr_img, region, grid, p1, store,
                                   f"{pid}:sr:{rev}"), "sr_float32")
        _land(p2, submit_or_resume(ee, valid_img, region, grid, p2, store,
                                   f"{pid}:valid:{rev}"), "valid_byte")
        _land(p3, submit_or_resume(ee, qa_img, region, grid, p3, store,
                                   f"{pid}:qapixel:{rev}"), "qa_pixel_uint16")
        sr_info = raster_grid_info(files[-3]["local_uri"])
        vd_info = valid_mask_info(files[-2]["local_uri"])
        qa_info = raster_grid_info(files[-1]["local_uri"])
        for info in (sr_info, vd_info, qa_info):
            assert_grid_matches(info, grid.to_dict())
        if sr_info["count"] != 7 or sr_info["dtypes"] != ["float32"] * 7:
            raise ProvenanceError(f"{pid}: L8/9 SR must be 7x float32")
        if qa_info["dtypes"] != ["uint16"]:
            raise ProvenanceError(f"{pid}: QA_PIXEL must land uint16")
        stats = band_stats(
            files[-3]["local_uri"],
            [f"SR_B{i}" for i in range(1, 8)])
        # band_stats lowercases names; remap keys to sr_bN
        remapped = {}
        for i in range(1, 8):
            for suffix in ("min", "p01", "p50", "p99", "max", "valid_px"):
                remapped[f"sr_b{i}_{suffix}"] = stats[f"sr_b{i}_{suffix}"]
        scale_audit = landsat_scaling_audit(remapped)
        if not scale_audit["pass"]:
            raise ProvenanceError(f"{pid}: landsat scaling audit fail")
        raster_checks = {"scaling_audit": scale_audit,
                         "band_stats": remapped,
                         "valid_mask": {k: vd_info[k] for k in
                                        ("valid_fraction", "unique_values",
                                         "total_pixel_count",
                                         "valid_pixel_count")},
                         "qa_pixel_dtype": qa_info["dtypes"]}
        native_resolution = 30.0
        stream = "landsat_30m"

    else:  # sentinel1
        image, proc = build_s1_image(ee, scene_ids[0])
        p1 = f"spartina_m21b_{pid}_vvvh_{date_tag}_{rev}"
        _land(p1, submit_or_resume(ee, image, region, grid, p1, store,
                                   f"{pid}:vvvh:{rev}"), "vv_vh_float32_db")
        info = raster_grid_info(files[-1]["local_uri"])
        assert_grid_matches(info, grid.to_dict())
        if info["count"] != 2 or info["dtypes"] != ["float32", "float32"] \
                or list(info["band_names"]) != ["VV", "VH"]:
            raise ProvenanceError(f"{pid}: S1 must be VV,VH float32")
        stats = band_stats(files[-1]["local_uri"], ["VV", "VH"], is_db=True)
        db_audit = s1_db_audit(stats)
        server_stats = server_recompute_stats(
            ee, image, region, grid, ["VV", "VH"])
        identity_check = compare_landed_vs_server(
            stats, server_stats, ["VV", "VH"],
            extrema_tol=1.0, pct_tol=0.6)
        if not db_audit["pass"] or not identity_check["pass"]:
            raise ProvenanceError(
                f"{pid}: S1 dB/identity audit failed "
                f"(envelope={db_audit['pass']}, "
                f"server_match={identity_check['pass']})")
        raster_checks = {"db_audit": db_audit,
                         "server_identity_check": identity_check}
        native_resolution = float(proc["native_resolution_m"])
        stream = "sentinel_10m"

    for f in files:
        f["grid_verified"] = True
        f["sha256"] = sha256_file(f["local_uri"])

    bundle_payload = {
        "product_id": pid, "cell_id": cid, "sensor": sensor,
        "grid": grid.to_dict(),
        "source_scene_ids": scene_ids,
        "files": sorted(({"role": f["role"], "sha256": f["sha256"],
                          "size_bytes": f["size_bytes"]} for f in files),
                         key=lambda x: x["role"]),
        "processing_config_sha256": canonical_fingerprint(proc),
    }
    manifest = {
        "schema": "spartina_observation_product_v0",
        "product_id": pid,
        "issue": "#13 M2.1b",
        "bay_id": "ZJ-HZB",
        "cell_id": cid,
        "observation_event_id": product["event_key"],
        "product_role": product["role"],
        "sensor": sensor,
        "science_stream": stream,
        "source_scene_ids": scene_ids,
        "source_tiles": str(product["tiles"]).split("|")
        if product["tiles"] else [],
        "acquisition_utc": product["event_utc"],
        "day_of_year": int(product["doy"]),
        "orbit_pass": product["pass_direction"] or None,
        "relative_orbit": product["relative_orbit"] or None,
        "native_resolution_m": native_resolution,
        "coverage_fraction": float(product["coverage_fraction"]),
        "contributing_cloud_max": product["contributing_cloud_max"],
        "multi_tile_same_datatake": bool(product["multi_tile"]),
        "grid_spec": grid.to_dict(),
        "grid_sha256": canonical_fingerprint(grid.to_dict()),
        "region": region,
        "build_revision": (
            "region: r3 projected-CRS rectangle + explicit dimensions "
            "(r1 WGS84 polygon and r2 projected rectangle were rejected "
            "by the grid assert); Landsat VALID byte fixed in r4; S2 r5 "
            "intersects SCL-valid with the four-band observation mask "
            "after a multi-tile seam exposed 10 inconsistent pixels"),
        "processing_config": proc,
        "qa": raster_checks,
        "tide": tide_block(),
        "label_availability": label_and_rights(cid),
        "rights_note": (
            "label bytes are NOT part of this product; SILVER L1 "
            "redistribution=NO; rights are per-asset in the manifest"),
        "export_tasks": tasks,
        "landed_files": files,
        "gdrive_folder": GDRIVE_FOLDER,
        "bundle": {"fingerprint_sha256":
                   canonical_fingerprint(bundle_payload),
                   "payload": bundle_payload},
        "git": git_context(REPO_ROOT),
        "environment": runtime_environment(),
        "created_utc": _now(),
    }
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    per_product_manifest.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, default=str),
        encoding="utf-8")
    print(f"[m21b] {pid} landed: {len(files)} file(s), "
          f"{sum(f['size_bytes'] for f in files) / 1e6:.1f} MB")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only-sensor", choices=["sentinel2", "landsat",
                                                  "sentinel1"])
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    if os.environ.get("SPARTINA_M21B_EXPORT") != "1":
        raise SystemExit(
            "real pilot export needs SPARTINA_M21B_EXPORT=1 (explicit "
            "operator opt-in) and is limited to the frozen event plan")
    if configured_project() is None:
        raise SystemExit("export SPARTINA_GEE_PROJECT=<project-id> first")
    initialize()
    import ee

    plan = json.loads(PLAN_JSON.read_text())
    products = list(plan["products"])
    if args.only_sensor:
        wanted = ({"sentinel2": {"sentinel2"},
                  "landsat": {"landsat8", "landsat9"},
                  "sentinel1": {"sentinel1"}}[args.only_sensor])
        products = [p for p in products if p["sensor"] in wanted]
    if args.limit:
        products = products[: args.limit]

    PRODUCT_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    TASK_STORE.parent.mkdir(parents=True, exist_ok=True)
    store = TaskStore(TASK_STORE)

    manifests = []
    failures = list(plan.get("failure_ledger", []))
    for product in products:
        try:
            manifests.append(export_one(ee, product, store))
        except Exception as exc:  # record, never silently substitute
            failures.append({"product_id": product["product_id"],
                             "cell_id": product["cell_id"],
                             "sensor": product["sensor"],
                             "code": "EXPORT_OR_VALIDATION_FAILURE",
                             "detail": f"{type(exc).__name__}: {exc}"})
            raise

    rows = []
    total = 0
    for m in manifests:
        for f in m["landed_files"]:
            total += int(f["size_bytes"])
        rows.append({
            "product_id": m["product_id"], "cell_id": m["cell_id"],
            "sensor": m["sensor"], "event_utc": m["acquisition_utc"],
            "n_files": len(m["landed_files"]),
            "bytes": sum(int(f["size_bytes"]) for f in m["landed_files"]),
            "sha_by_role": json.dumps(
                {f["role"]: f["sha256"] for f in m["landed_files"]},
                sort_keys=True),
            "bundle_fingerprint_sha256":
                m["bundle"]["fingerprint_sha256"],
            "tide_observed": m["tide"]["observed_tide_status"],
            "tide_modeled": m["tide"]["modeled_tide_status"],
            "product_manifest":
                str((MANIFEST_DIR / f"{m['product_id']}.json").relative_to(
                    REPO_ROOT)),
        })
    pd.DataFrame(rows).to_csv(OUT_CSV, index=False)

    aggregate = {
        "manifest_id": "zhejiang_m21b_pilot_v0",
        "issue": "#13",
        "created_utc": _now(),
        "n_products_landed": len(manifests),
        "n_products_planned": plan["n_products"],
        "total_bytes": total,
        "total_gib": round(total / 1024**3, 3),
        "volume_cap_bytes": 10 * 1024**3,
        "products": rows,
        "failure_ledger": failures,
        "simulation_discrepancies": plan.get("simulation_discrepancies", []),
        "event_plan_fingerprint_sha256": plan["fingerprint_sha256"],
        "tide_policy": tide_block(),
        "label_policy": {
            "gold_promoted": False,
            "unlabeled_is_negative": False,
            "label_bytes_copied": False,
        },
        "git": git_context(REPO_ROOT),
        "environment": runtime_environment(),
    }
    if total > 10 * 1024**3:
        raise SystemExit("pilot exceeded 10 GB; STOP")
    OUT_JSON.write_text(
        json.dumps(aggregate, indent=2, sort_keys=True, default=str),
        encoding="utf-8")
    print(f"[m21b] {len(manifests)} products, {total / 1024**2:.1f} MiB; "
          f"wrote {OUT_JSON.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
