#!/usr/bin/env python3
"""Issue #19 Phase D/E -- real GEE pixel export for the FROZEN 20-cell pilot.

Generalised from the Zhejiang M2.1b real-export driver
(``scripts/data/zhejiang/m21b_export_products.py``) to the national
panel. Runs ONLY with ``SPARTINA_PILOT19_EXPORT=1`` and
``SPARTINA_GEE_PROJECT`` set. Scope is hard-locked by checksum to the
frozen event plan (``national_pilot_event_plan_v1.csv``; 280 rows, 194
SELECTED, 402 planned component tasks). No cell, year or product is ever
added by this script.

Per product it:
* re-derives the locked GridSpec from the exact Albers 10 km cell using
  the SAME rule as the Phase F/G label supports (densified UTM bounds +
  ``spartina.data.gee.grid.covering_grid``; native 30 m for Landsat,
  10 m for Sentinel; never upsampled);
* Landsat 5/7/8 Collection 2 Level-2: physical SR float32
  (DN*2.75e-5-0.2; fill pixels masked so DN=0 never exports as -0.2),
  uint8 QA VALID byte, raw uint16 QA_PIXEL. L5/L7 carry six SR bands,
  L8 seven;
* Sentinel-2 SR_HARMONIZED: same-DATATAKE ordered mosaic, B2/B3/B4/B8
  float32 DN/10000, uint8 SCL VALID under s2_scl_qa_v1_1 (SCL {4,5,6};
  water valid; dark/unclassified/snow invalid), intersected with the
  four-band observation mask, contributing granule ids preserved;
* Sentinel-1 GRD: identity select of VV/VH float32 dB (no second
  10*log10), pass and relative orbit verified against the frozen plan;
* lands bytes via Drive, verifies grid/dtype/band-order, computes
  SHA-256, audits scaling/percentiles and S1 server identity, and writes
  a per-product provenance manifest plus an aggregate export ledger.

Deterministic request ids (``{product_id}:{role}:r1``) and a JSON task
store give idempotent resume. Submission is NOT completion: a product is
LANDED only with files + manifest + SHA-256 on disk.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import rasterio  # noqa: E402
from pyproj import CRS, Transformer  # noqa: E402

from spartina.data.gee import driveio, landsat  # noqa: E402
from spartina.data.gee.auth import configured_project, initialize  # noqa: E402
from spartina.data.gee.collections import collection_for  # noqa: E402
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
from spartina.data.gee.tasks import (  # noqa: E402
    STATE_COMPLETED,
    STATE_FAILED,
    STATE_PENDING,
    STATE_RUNNING,
    TaskRecord,
    TaskStore,
)
from spartina.data.national import grid as national_grid  # noqa: E402
from spartina.data.national.grid import (  # noqa: E402
    CHINA_ALBERS_PROJ4,
    GridKind,
    parse_cell_id,
    utm_epsg,
)

PLAN_CSV = REPO_ROOT / "datasets/manifests/national_pilot_event_plan_v1.csv"
PLAN_JSON = REPO_ROOT / "datasets/manifests/national_pilot_event_plan_v1.json"
PANEL_CSV = REPO_ROOT / "datasets/manifests/national_first_pixel_panel_v1.csv"
CANARY_CSV = REPO_ROOT / "datasets/manifests/national_pilot19_canary_v1.csv"
WORK_DIR = REPO_ROOT / "work" / "national" / "pilot19"
PRODUCT_DIR = WORK_DIR / "products"
MANIFEST_DIR = WORK_DIR / "manifests"
TASK_STORE = WORK_DIR / "tasks" / "task_store.json"
FAILURES_JSON = WORK_DIR / "failures.json"
PROGRESS_JSON = WORK_DIR / "export_progress.json"
OUT_CSV = REPO_ROOT / "datasets/manifests/national_pilot19_pixel_export_v1.csv"
OUT_JSON = REPO_ROOT / "datasets/manifests/national_pilot19_pixel_export_v1.json"

GDRIVE_FOLDER = "SpartinaEarthPilot19"
REVISION = "r1"
#: Landsat VALID component revision r2: pilot D1 found QA-clear pixels with
#: per-band SR nodata (interior B1/B2 NaN under clear QA_PIXEL). VALID now
#: also requires every SR band observed. SR/QA_PIXEL stay r1 (same pixels).
LANDSAT_VALID_REVISION = "r2"


def role_revision(sensor: str, role: str) -> str:
    if sensor.startswith("landsat") and role == "valid":
        return LANDSAT_VALID_REVISION
    return REVISION
POLL_INTERVAL_S = 15
TASK_TIMEOUT_S = 5400
DRIVE_PROPAGATION_S = 180
POLL_BATCH = 50
VOLUME_CAP_BYTES = 4 * 1024**3
GEE_FAILED_STATES = frozenset({"FAILED", "CANCELLED"})
TASK_RESULT_KEYS = (
    "state", "description", "task_type", "attempt",
    "creation_timestamp_ms", "start_timestamp_ms",
    "update_timestamp_ms", "additional_info")

#: sensor -> exported component roles (component tasks == planned files).
COMPONENTS: dict[str, tuple[str, ...]] = {
    "landsat5": ("sr", "valid", "qapixel"),
    "landsat7": ("sr", "valid", "qapixel"),
    "landsat8": ("sr", "valid", "qapixel"),
    "sentinel2": ("sr", "valid"),
    "sentinel1": ("vvvh",),
}

#: Points sampled per cell edge when projecting the Albers square to UTM;
#: MUST match build_pilot_label_supports_v1.BOUNDS_DENSIFY_PER_EDGE.
BOUNDS_DENSIFY_PER_EDGE = 21

_STATE_SELECTED = "SELECTED"
_STATE_SUBMITTED = "SUBMITTED"
_STATE_RUNNING = "RUNNING"
_STATE_LANDED = "LANDED"
_STATE_FAILED = "EXPORT_FAILED"

_ALBERS = CRS.from_proj4(CHINA_ALBERS_PROJ4)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()  # noqa: UP017


def _clean(value: Any) -> Any:
    """Normalise pandas round-trip values (NaN/empty string -> None)."""
    if value is None:
        return None
    if isinstance(value, float) and np.isnan(value):
        return None
    if isinstance(value, str):
        return value or None
    return value


# ---------------------------------------------------------------------------
# Frozen scope (plan checksum gate; SELECTED filter)
# ---------------------------------------------------------------------------

def plan_csv_sha256() -> str:
    plan_doc = json.loads(PLAN_JSON.read_text(encoding="utf-8"))
    expected = str(plan_doc["checksums"]["plan_csv_sha256"])
    actual = sha256_file(PLAN_CSV)
    if actual != expected:
        raise ProvenanceError(
            f"frozen plan CSV checksum mismatch: expected {expected}, "
            f"got {actual}; refusing export")
    return expected


def load_scope(
    *, canary: bool, only_sensor: str | None,
    products_filter: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    """Return the frozen, checksum-gated, SELECTED product rows to run."""
    plan_csv_sha256()
    plan = pd.read_csv(PLAN_CSV)
    plan = plan[plan["status"] == "SELECTED"].copy()
    if canary:
        if not CANARY_CSV.exists():
            raise FileNotFoundError(f"canary allowlist missing: {CANARY_CSV}")
        allow = set(pd.read_csv(CANARY_CSV)["product_id"].astype(str))
        plan = plan[plan["product_id"].astype(str).isin(allow)]
    if only_sensor:
        plan = plan[plan["sensor"] == only_sensor]
    if products_filter:
        wanted = set(products_filter)
        plan = plan[plan["product_id"].astype(str).isin(wanted)]
        missing = wanted - set(plan["product_id"].astype(str))
        if missing:
            raise ValueError(
                f"--products ids not SELECTED in frozen plan: {sorted(missing)}")
    rows = [{k: _clean(v) for k, v in row.items()}
            for row in plan.to_dict("records")]
    rows.sort(key=lambda r: str(r["product_id"]))
    return rows


def load_panel() -> pd.DataFrame:
    return pd.read_csv(PANEL_CSV).set_index("cell_id")


# ---------------------------------------------------------------------------
# Grid rule -- identical to build_pilot_label_supports_v1 (densify + cover)
# ---------------------------------------------------------------------------

def cell_zone(panel: pd.DataFrame, cell_id: str) -> int:
    """Native UTM zone of one cell, derived from the frozen WGS centroid."""
    center_lon = float(panel.loc[cell_id, "center_lon"])
    return int(np.floor((center_lon + 180.0) / 6.0) + 1)


def cell_utm_bounds(
    cell_id: str, zone: int,
) -> tuple[int, tuple[float, float, float, float]]:
    """Projected UTM bounding box of one Albers cell (edges densified)."""
    ref = parse_cell_id(cell_id)
    lattice = national_grid.GridSpec(GridKind.CHINA_ALBERS)
    xmin, ymin, xmax, ymax = lattice.cell_bounds_projected(ref.row, ref.col)
    transformer = Transformer.from_crs(
        _ALBERS, CRS.from_epsg(utm_epsg(zone)), always_xy=True)
    edge = np.linspace(0.0, 1.0, BOUNDS_DENSIFY_PER_EDGE)
    pts: list[tuple[float, float]] = []
    for t in edge:
        tv = float(t)
        pts.extend([
            (xmin + tv * (xmax - xmin), ymin),
            (xmin + tv * (xmax - xmin), ymax),
            (xmin, ymin + tv * (ymax - ymin)),
            (xmax, ymin + tv * (ymax - ymin)),
        ])
    px, py = transformer.transform([p[0] for p in pts], [p[1] for p in pts])
    return utm_epsg(zone), (
        float(np.min(px)), float(np.min(py)),
        float(np.max(px)), float(np.max(py)))


def product_grid(
    row: dict[str, Any], panel: pd.DataFrame,
) -> tuple[GridSpec, dict[str, Any], int]:
    """Locked GridSpec + projected-CRS export region for one product."""
    cell_id = str(row["cell_id"])
    sensor = str(row["sensor"])
    zone = cell_zone(panel, cell_id)
    epsg, bounds = cell_utm_bounds(cell_id, zone)
    pixel_m = 30.0 if sensor.startswith("landsat") else 10.0
    grid = covering_grid(bounds, epsg, pixel_m)
    assert_no_forced_upsampling(pixel_m, grid.pixel_x_m)
    # Projected-CRS rectangle, never a WGS84 round-trip (adds a pixel
    # column; M2.1b r3 lesson). Dimensions pinned at task submission.
    region = {"type": "Rectangle", "crs": grid.crs,
              "coordinates": [list(grid.bounds)]}
    return grid, region, zone


# ---------------------------------------------------------------------------
# Deterministic task naming
# ---------------------------------------------------------------------------

def date_tag(row: dict[str, Any]) -> str:
    return str(row["event_utc"])[:10].replace("-", "")


def prefix_for(row: dict[str, Any], role: str) -> str:
    return (f"spartina_pilot19_{row['product_id']}_{role}_"
            f"{date_tag(row)}_{role_revision(str(row['sensor']), role)}")


def request_for(row: dict[str, Any], role: str) -> str:
    rev = role_revision(str(row["sensor"]), role)
    return f"{row['product_id']}:{role}:{rev}"


# ---------------------------------------------------------------------------
# Image builders (all provenance-sensitive decisions live here)
# ---------------------------------------------------------------------------

def _scene_ids(row: dict[str, Any]) -> list[str]:
    raw = row.get("scene_ids")
    if not isinstance(raw, str) or not raw:
        raise ProvenanceError(f"{row['product_id']}: plan row has no scene_ids")
    return raw.split("|")


def build_s2(
    ee: Any, scene_ids: list[str],
) -> tuple[Any, Any, dict[str, Any]]:
    """Same-datatake ordered S2 mosaic (reflectance float + SCL VALID)."""
    col = (ee.ImageCollection(collection_for("sentinel2"))
           .filter(ee.Filter.inList("system:index", scene_ids)))
    n = int(col.size().getInfo())
    if n != len(scene_ids):
        raise ProvenanceError(
            f"S2 catalog returned {n} scenes for {scene_ids}; abort")
    # sort() tie-breaks equal MGRS_TILE values by system:index.
    ordered = col.sort("MGRS_TILE")
    datatakes = sorted(set(col.aggregate_array("DATATAKE_IDENTIFIER").getInfo()))
    dates = sorted({s[:8] for s in scene_ids})
    if len(datatakes) != 1:
        raise ProvenanceError(f"cross-datatake merge forbidden, got {datatakes}")
    if len(dates) != 1:
        raise ProvenanceError(f"cross-date mosaic forbidden, got dates {dates}")
    tiles = sorted(set(col.aggregate_array("MGRS_TILE").getInfo()))
    ordered_indexes = list(ordered.aggregate_array("system:index").getInfo())
    ordered_products = list(ordered.aggregate_array("PRODUCT_ID").getInfo())
    spacecraft = sorted(set(col.aggregate_array("SPACECRAFT_NAME").getInfo()))
    time_starts = list(ordered.aggregate_array("system:time_start").getInfo())

    def _observed4(img: Any) -> Any:
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
    valid = ordered.map(_valid_one).mosaic().unmask(0).rename("VALID")
    config = {
        "collection_id": collection_for("sentinel2"),
        "composite": ("SAME_DATATAKE_ORDERED_MOSAIC"
                      if len(tiles) > 1 else "NONE_SINGLE_SOURCE_SCENE"),
        "tile_order": tiles,
        "scene_order_system_index": ordered_indexes,
        "contributing_source_product_ids": ordered_products,
        "spacecraft": spacecraft,
        "scene_time_start_epoch_ms": time_starts,
        "datatake_identifier": datatakes[0],
        "scene_date": dates[0],
        "reflectance_scale": float(REFLECTANCE_SCALE),
        "reflectance_offset": 0.0,
        "band_order": list(TEN_M_BANDS),
        "resampling": "NONE; native 10 m bands only; 20/60 m excluded",
        "native_resolution_m": 10.0,
        "scl_qa_policy_version": S2_SCL_QA_POLICY_VERSION,
        "scl_qa_policy": S2_SCL_QA_POLICY.to_manifest_dict(),
        "valid_definition": (
            "SCL valid-surface (classes 4/5/6; water valid) AND all four "
            "native 10 m bands observed in the same source tile; masks "
            "evaluated before the same-datatake mosaic; dark(2)/"
            "unclassified(7)/snow(11) invalid"),
    }
    return reflectance, valid, config


_LANDSAT_PROP_KEYS = (
    "WRS_PATH", "WRS_ROW", "LANDSAT_PRODUCT_ID", "SPACECRAFT_ID",
    "CLOUD_COVER", "CLOUD_COVER_LAND", "COLLECTION_CATEGORY",
    "system:time_start",
)


def build_landsat(
    ee: Any, sensor: str, scene_id: str,
) -> tuple[Any, Any, Any, dict[str, Any]]:
    """One C02 L2 scene: physical SR float + QA VALID byte + raw QA uint16."""
    img = (ee.ImageCollection(collection_for(sensor))
           .filter(ee.Filter.eq("system:index", scene_id)).first())
    sr_band_names = list(landsat.sr_bands(sensor))
    qa = img.select("QA_PIXEL")
    # Explicit fill mask: DN=0 fill pixels must never export as the
    # scaled -0.2 intercept.
    fill_mask = qa.bitwiseAnd(1 << landsat.QA_FILL).eq(0)
    sr = (img.select(sr_band_names)
          .multiply(landsat.LANDSAT_C2_SR_MULTIPLY)
          .add(landsat.LANDSAT_C2_SR_ADD).toFloat()
          .updateMask(fill_mask))
    radsat = img.select("QA_RADSAT")
    blocked = [landsat.QA_FILL, landsat.QA_DILATED_CLOUD, landsat.QA_CIRRUS,
               landsat.QA_CLOUD, landsat.QA_CLOUD_SHADOW, landsat.QA_SNOW]
    valid = qa.bitwiseAnd(1 << landsat.QA_CLEAR).neq(0)
    for bit in blocked:
        valid = valid.And(qa.bitwiseAnd(1 << bit).eq(0))
    valid = valid.And(radsat.eq(0))
    # r2: QA_PIXEL clear does not guarantee per-band presence. Pilot D1
    # observed interior B1/B2 nodata pixels under clear QA (R00260 L8 2020);
    # require every SR band observed, matching the S2 contract.
    observed_all_sr = sr.mask().reduce(ee.Reducer.min())
    valid = (valid.And(observed_all_sr.eq(1))
             .toByte().unmask(0).rename("VALID"))
    qa_raw = img.select("QA_PIXEL").toUint16().rename("QA_PIXEL")
    props = img.toDictionary(list(_LANDSAT_PROP_KEYS)).getInfo()
    config = {
        "collection_id": collection_for(sensor),
        "composite": "NONE_SINGLE_SOURCE_SCENE",
        "scene_id": scene_id,
        "source_product_id": props.get("LANDSAT_PRODUCT_ID"),
        "sr_band_order": sr_band_names,
        "sr_scale": landsat.LANDSAT_C2_SR_MULTIPLY,
        "sr_offset": landsat.LANDSAT_C2_SR_ADD,
        "native_resolution_m": 30.0,
        "upsampling": "FORBIDDEN; 30 m product stays on the 30 m grid",
        "qa_contract": {
            "valid": ("r2: QA_PIXEL clear bit6 and none of fill/dilated/"
                      "cirrus/cloud/shadow/snow, plus QA_RADSAT == 0, AND "
                      "every SR band observed (per-band mask min == 1); "
                      "r1 (QA+RADSAT only) superseded after pilot D1 found "
                      "interior per-band nodata under clear QA"),
            "fill_dn0": ("fill bit0 pixels masked BEFORE scaling; DN=0 "
                         "never exported as reflectance -0.2"),
            "raw_qa_exported_separately": True},
        "properties": props,
    }
    return sr, valid, qa_raw, config


#: Frozen-plan pass vocabulary -> GEE orbitProperties_pass values.
PASS_TO_GEE: dict[str, str] = {"ASC": "ASCENDING", "DESC": "DESCENDING"}


_S1_PROP_KEYS = (
    "productIdentifier", "orbitProperties_pass",
    "relativeOrbitNumber_start", "platform_number", "instrumentMode",
    "transmitterReceiverPolarisation", "resolution_meters",
    "system:time_start",
)


def build_s1(ee: Any, scene_id: str) -> tuple[Any, dict[str, Any]]:
    img = (ee.ImageCollection(collection_for("sentinel1"))
           .filter(ee.Filter.eq("system:index", scene_id)).first())
    props = img.toDictionary(list(_S1_PROP_KEYS)).getInfo()
    # Older ingests (observed on a 2015 scene) omit productIdentifier;
    # system:index is then itself the full GRD product filename and is
    # the identifier the frozen plan was built from.
    product_identifier = props.get("productIdentifier")
    source_id = product_identifier or scene_id
    image = img.select(["VV", "VH"], ["VV", "VH"]).toFloat()
    config = {
        "collection_id": collection_for("sentinel1"),
        "composite": "NONE_SINGLE_SOURCE_SCENE",
        "source_product_id": source_id,
        "productIdentifier_property_present": product_identifier is not None,
        "product_id_source_rule": (
            "GEE productIdentifier property when present; system:index "
            "(full GRD filename) when the ingest omits productIdentifier "
            "(observed on older S1 scenes)"),
        "transform": "IDENTITY_SELECT_ONLY",
        "units": "sigma0 dB as ingested by GEE",
        "log10_applied": False,
        "band_order": ["VV", "VH"],
        "native_resolution_m": float(props["resolution_meters"]),
        "pass_kept_separate": True,
        "properties": props,
    }
    return image, config


@dataclass
class Component:
    role: str
    image: Any
    prefix: str
    request_id: str


@dataclass
class Bundle:
    row: dict[str, Any]
    grid: GridSpec
    region: dict[str, Any]
    zone: int
    components: list[Component]
    proc: dict[str, Any]
    native_resolution_m: float
    science_stream: str


def _expect_equal(label: str, actual: Any, expected: Any) -> None:
    if actual != expected:
        raise ProvenanceError(
            f"GEE vs frozen plan cross-check failed for {label}: "
            f"gee={actual!r} plan={expected!r}")


def build_bundle(ee: Any, row: dict[str, Any],
                 panel: pd.DataFrame) -> Bundle:
    sensor = str(row["sensor"])
    scene_ids = _scene_ids(row)
    grid, region, zone = product_grid(row, panel)
    components: list[Component] = []
    proc: dict[str, Any]
    if sensor == "sentinel2":
        refl, valid, proc = build_s2(ee, scene_ids)
        if set(scene_ids) != set(proc["scene_order_system_index"]):
            raise ProvenanceError(
                f"{row['product_id']}: S2 scene id set disagreement with catalog")
        planned_products = row.get("product_ids_source")
        if (isinstance(planned_products, str)
                and "|" not in planned_products
                and planned_products not in proc["contributing_source_product_ids"]):
            raise ProvenanceError(
                f"{row['product_id']}: S2 planned source product "
                f"{planned_products} absent in GEE granule products")
        components = [
            Component("sr", refl, prefix_for(row, "sr"), request_for(row, "sr")),
            Component("valid", valid, prefix_for(row, "valid"),
                      request_for(row, "valid")),
        ]
        native = 10.0
    elif sensor.startswith("landsat"):
        sr_img, valid_img, qa_img, proc = build_landsat(
            ee, sensor, scene_ids[0])
        _expect_equal(
            f"{row['product_id']} LANDSAT_PRODUCT_ID",
            proc["source_product_id"], row.get("product_ids_source"))
        if row.get("wrs_path") is not None:
            _expect_equal(
                f"{row['product_id']} WRS_PATH",
                int(proc["properties"]["WRS_PATH"]),
                int(float(row["wrs_path"])))
            _expect_equal(
                f"{row['product_id']} WRS_ROW",
                int(proc["properties"]["WRS_ROW"]),
                int(float(row["wrs_row"])))
        components = [
            Component("sr", sr_img, prefix_for(row, "sr"), request_for(row, "sr")),
            Component("valid", valid_img, prefix_for(row, "valid"),
                      request_for(row, "valid")),
            Component("qapixel", qa_img, prefix_for(row, "qapixel"),
                      request_for(row, "qapixel")),
        ]
        native = 30.0
    elif sensor == "sentinel1":
        image, proc = build_s1(ee, scene_ids[0])
        _expect_equal(f"{row['product_id']} productIdentifier",
                      proc["source_product_id"], scene_ids[0])
        if row.get("pass") is not None:
            plan_pass = PASS_TO_GEE.get(str(row["pass"]), str(row["pass"]))
            _expect_equal(
                f"{row['product_id']} orbit pass",
                proc["properties"]["orbitProperties_pass"], plan_pass)
        if row.get("relative_orbit") is not None:
            _expect_equal(
                f"{row['product_id']} relative orbit",
                int(proc["properties"]["relativeOrbitNumber_start"]),
                int(float(row["relative_orbit"])))
        components = [
            Component("vvvh", image, prefix_for(row, "vvvh"),
                      request_for(row, "vvvh")),
        ]
        native = float(proc["native_resolution_m"])
    else:
        raise ProvenanceError(f"unsupported sensor {sensor!r}")
    return Bundle(
        row=row, grid=grid, region=region, zone=zone, components=components,
        proc=proc, native_resolution_m=native,
        science_stream=("landsat_30m" if sensor.startswith("landsat")
                        else "sentinel_10m"))


# ---------------------------------------------------------------------------
# Raster statistics / audits (generalised unchanged from M2.1b)
# ---------------------------------------------------------------------------

def band_stats(path: str, bands: list[str], *, is_db: bool = False) -> dict[str, float]:
    with rasterio.open(path) as src:
        out: dict[str, float] = {}
        for i, name in enumerate(bands, start=1):
            arr = src.read(i, masked=True)
            vals = arr.compressed()
            vals = vals[np.isfinite(vals)]
            if vals.size == 0:
                raise ProvenanceError(
                    f"{path}:{name} no finite observed pixels")
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


def landsat_scaling_audit(sensor: str, stats: dict[str, float]) -> dict[str, Any]:
    """Physical SR range + ordered percentiles, 6 bands (L5/7) or 7 (L8)."""
    n_bands = len(landsat.sr_bands(sensor))
    checks: dict[str, bool] = {}
    for i in range(1, n_bands + 1):
        band = f"sr_b{i}"
        lo = stats.get(f"{band}_p01")
        hi = stats.get(f"{band}_p99")
        if lo is None or hi is None:
            continue
        checks[f"{band}_physical_range"] = lo >= -0.30 and hi <= 1.3
        checks[f"{band}_ordered"] = (
            stats[f"{band}_min"] <= lo <= stats[f"{band}_p50"] <= hi
            <= stats[f"{band}_max"])
    return {
        "sensor": sensor,
        "n_sr_bands": n_bands,
        "plausible_physical_sr_range": [-0.30, 1.30],
        "checks": checks, "pass": all(checks.values())}


#: C02 L2 DN=65535 maps exactly to this value; observed values at the
#: cap are radiometric saturation, NOT a scaling error.
SR_SATURATION_CAP = 65535 * landsat.LANDSAT_C2_SR_MULTIPLY     + landsat.LANDSAT_C2_SR_ADD
#: >0.1% saturated pixels inside QA-VALID means RADSAT failed to flag.
SATURATION_IN_VALID_HARD_FRACTION = 1e-3


def landsat_physical_audit(
    sensor: str, sr_path: str, valid_path: str,
) -> tuple[dict[str, Any], dict[str, float]]:
    """Finite-robust, VALID-restricted physical audit of landed Landsat SR.

    Observed percentiles may legitimately reach the DN=65535 saturation
    cap (1.6022); the physical [-0.30, 1.30] gate is applied to QA-VALID
    pixels only. Non-finite pixels inside VALID and excessive saturation
    inside VALID are hard failures. Returns (audit, valid-only stats).
    """
    n_bands = len(landsat.sr_bands(sensor))
    with rasterio.open(valid_path) as vd:
        valid = vd.read(1) == 1
    stats: dict[str, float] = {}
    detail: dict[str, Any] = {"bands": {}}
    checks: dict[str, bool] = {}
    with rasterio.open(sr_path) as sr:
        observed = sr.dataset_mask() > 0
        for i in range(1, n_bands + 1):
            band = f"sr_b{i}"
            arr = sr.read(i).astype("float64")
            finite = np.isfinite(arr)
            of = observed & finite
            vf = of & valid
            if int(vf.sum()) == 0:
                raise ProvenanceError(
                    f"{sr_path}:{band} has no finite VALID pixels")
            nonfinite_observed = int((observed & ~finite).sum())
            nonfinite_valid = int((valid & ~finite).sum())
            po = np.percentile(arr[of], [0, 1, 50, 99, 100])
            pv = np.percentile(arr[vf], [0, 1, 50, 99, 100])
            for key, value in zip(
                    ("min", "p01", "p50", "p99", "max"), po, strict=True):
                stats[f"{band}_obs_{key}"] = float(value)
            for key, value in zip(
                    ("min", "p01", "p50", "p99", "max"), pv, strict=True):
                stats[f"{band}_valid_{key}"] = float(value)
            stats[f"{band}_observed_px"] = int(of.sum())
            stats[f"{band}_valid_px"] = int(vf.sum())
            sat = np.isclose(arr, SR_SATURATION_CAP, atol=1e-5)
            sat_observed = int((of & sat).sum())
            sat_valid = int((vf & sat).sum())
            sat_frac = sat_valid / max(int(vf.sum()), 1)
            detail["bands"][band] = {
                "nonfinite_observed_pixels": nonfinite_observed,
                "nonfinite_valid_pixels": nonfinite_valid,
                "saturation_cap_value": SR_SATURATION_CAP,
                "saturated_observed_pixels": sat_observed,
                "saturated_valid_pixels": sat_valid,
                "saturated_valid_fraction": sat_frac}
            checks[f"{band}_no_nonfinite_in_valid"] = nonfinite_valid == 0
            checks[f"{band}_valid_physical_range"] = (
                pv[1] >= -0.30 and pv[3] <= 1.30)
            checks[f"{band}_valid_ordered"] = (
                pv[0] <= pv[1] <= pv[2] <= pv[3] <= pv[4])
            checks[f"{band}_saturation_in_valid_below_hard_fraction"] = (
                sat_frac <= SATURATION_IN_VALID_HARD_FRACTION)
    detail["sensor"] = sensor
    detail["n_sr_bands"] = n_bands
    detail["valid_pixel_physical_range"] = [-0.30, 1.30]
    detail["saturation_cap"] = SR_SATURATION_CAP
    detail["saturation_policy"] = (
        "observed DN=65535 saturation at 1.6022 is physical and excluded "
        "from VALID via QA_RADSAT; only saturation inside QA-VALID is a "
        "hard failure above 0.1 percent")
    detail["checks"] = checks
    detail["pass"] = all(checks.values())
    return detail, stats


def observed_fractions(path: str) -> dict[str, Any]:
    """Per-band observed-pixel counts against the full export grid."""
    with rasterio.open(path) as src:
        total = int(src.width * src.height)
        mask = src.dataset_mask() > 0
        bands: dict[str, Any] = {}
        for i in range(1, src.count + 1):
            arr = src.read(i)
            observed = int(mask.sum())
            finite = int((mask & np.isfinite(arr)).sum())
            bands[f"band_{i}"] = {
                "name": src.descriptions[i - 1],
                "observed_pixels": observed,
                "finite_pixels": finite,
                "nonfinite_pixels": observed - finite,
                "grid_pixels": total,
                "observed_fraction": observed / total if total else None,
                "finite_fraction": finite / total if total else None}
        return {"nodata": src.nodata, "grid_pixels": total, "bands": bands}


#: Bulk-plausibility sigma0 dB envelope inherited from the M2.1b Zhejiang
#: screen. National coastal scenes legitimately contain sparse harbour/ship
#: double-bounce point targets (VV up to ~+37 dB, VH also bright) and calm
#: water speckle nulls (VH below -50 dB); all such pixels in the canary were
#: independently confirmed present in the source GEE scene via the live
#: server identity check, so bulk-envelope exceedance is a fraction gate.
S1_DB_BULK_MIN = -50.0
S1_DB_BULK_MAX = 30.0
#: Absolute envelope beyond which pixels cannot be valid S1 GRD dB; catches
#: corruption and double-transform artifacts (which reach hundreds of dB).
S1_DB_HARD_MIN = -70.0
S1_DB_HARD_MAX = 45.0
#: Point-target / dark-water tail must stay below 0.1% of finite pixels.
S1_TAIL_OUTSIDE_BULK_HARD_FRACTION = 1e-3


def s1_physical_audit(path: str) -> dict[str, Any]:
    """Finite-robust physical audit of a landed identity S1 VV/VH raster.

    Hard failures: pixels beyond the absolute dB envelope, non-monotone
    percentiles, implausible medians, co-pol/cross-pol ordering inverted,
    or >0.1% of finite pixels outside the bulk [-50, 30] envelope. The
    source-fidelity (no 10*log10) guarantee is enforced separately by the
    live server identity comparison in validate_bundle.
    """
    detail: dict[str, Any] = {
        "expected_units": "sigma0 dB (COPERNICUS/S1_GRD pre-converted)",
        "transform_applied": "IDENTITY_SELECT_ONLY_NO_10LOG10",
        "bulk_envelope_db": [S1_DB_BULK_MIN, S1_DB_BULK_MAX],
        "hard_envelope_db": [S1_DB_HARD_MIN, S1_DB_HARD_MAX],
        "tail_policy": ("pixels outside the bulk envelope are legitimate "
                        "sparse coastal point targets / dark-water nulls "
                        "when the server identity check matches and the "
                        "tail stays below 0.1 percent"),
        "bands": {}}
    checks: dict[str, bool] = {}
    with rasterio.open(path) as src:
        total = int(src.width * src.height)
        mask = src.dataset_mask() > 0
        for i, name in enumerate(("VV", "VH"), start=1):
            if src.descriptions[i - 1] != name:
                raise ProvenanceError(
                    f"{path}: band {i} must be {name}, got "
                    f"{src.descriptions[i - 1]}")
            arr = src.read(i).astype("float64")
            finite = mask & np.isfinite(arr)
            n = int(finite.sum())
            if n == 0:
                raise ProvenanceError(f"{path}:{name} no finite pixels")
            vals = arr[finite]
            pct = np.percentile(vals, [0, 1, 50, 99, 100])
            outside_hard = int(((vals < S1_DB_HARD_MIN)
                                | (vals > S1_DB_HARD_MAX)).sum())
            outside_bulk = int(((vals < S1_DB_BULK_MIN)
                                | (vals > S1_DB_BULK_MAX)).sum())
            tail_frac = outside_bulk / n
            detail["bands"][name] = {
                "finite_pixels": n,
                "grid_pixels": total,
                "finite_fraction": n / total,
                "min": float(pct[0]), "p01": float(pct[1]),
                "p50": float(pct[2]), "p99": float(pct[3]),
                "max": float(pct[4]),
                "outside_hard_envelope_pixels": outside_hard,
                "outside_bulk_envelope_pixels": outside_bulk,
                "outside_bulk_envelope_fraction": tail_frac}
            checks[f"{name}_no_pixels_beyond_hard_envelope"] = (
                outside_hard == 0)
            checks[f"{name}_ordered_percentiles"] = bool(
                pct[0] <= pct[1] <= pct[2] <= pct[3] <= pct[4])
            checks[f"{name}_tail_below_hard_fraction"] = (
                tail_frac <= S1_TAIL_OUTSIDE_BULK_HARD_FRACTION)
        vv50 = detail["bands"]["VV"]["p50"]
        vh50 = detail["bands"]["VH"]["p50"]
        checks["VV_median_plausible"] = -30.0 <= vv50 <= 5.0
        checks["VH_median_plausible"] = -40.0 <= vh50 <= -5.0
        checks["VV_median_above_VH"] = vv50 > vh50
    detail["checks"] = checks
    detail["pass"] = all(checks.values())
    return detail


def server_recompute_stats(
    ee: Any, image: Any, region: dict[str, Any], grid: GridSpec,
    bands: list[str],
) -> dict[str, float]:
    rect = ee.Geometry.Rectangle(region["coordinates"][0], region["crs"], False)
    reducer = (ee.Reducer.minMax()
               .combine(ee.Reducer.percentile([1, 50, 99]), sharedInputs=True))
    raw = (image.select(bands).reduceRegion(
        reducer=reducer, geometry=rect, crs=grid.crs,
        scale=grid.pixel_x_m, bestEffort=False, tileScale=4).getInfo())
    out: dict[str, float] = {}
    for band in bands:
        for src_name, dst in (("min", "min"), ("max", "max"),
                              ("p1", "p01"), ("p50", "p50"), ("p99", "p99")):
            out[f"{band}_{dst}"] = float(raw[f"{band}_{src_name}"])
    return out


def compare_landed_vs_server(
    landed: dict[str, float], server: dict[str, float],
    bands: list[str], *, extrema_tol: float, pct_tol: float,
) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    deltas: dict[str, float] = {}
    for band in bands:
        for stat, tol in (("min", extrema_tol), ("max", extrema_tol),
                          ("p01", pct_tol), ("p50", pct_tol), ("p99", pct_tol)):
            key = f"{band}_{stat}"
            delta = abs(landed[key] - server[key])
            deltas[key] = round(delta, 4)
            checks[key] = delta <= tol
    return {"landed": landed, "server_recompute": server,
            "abs_deltas": deltas,
            "tolerance_db": {"extrema": extrema_tol, "percentiles": pct_tol},
            "checks": checks, "pass": all(checks.values())}


# ---------------------------------------------------------------------------
# Post-landing bundle validation
# ---------------------------------------------------------------------------

def validate_bundle(
    ee: Any, bundle: Bundle, landed: dict[str, Path],
) -> dict[str, Any]:
    """Validate every landed component of one product; raises on failure."""
    grid = bundle.grid
    sensor = str(bundle.row["sensor"])
    qa: dict[str, Any] = {}
    if sensor.startswith("landsat"):
        sr_path = landed["sr"]
        valid_path = landed["valid"]
        qa_path = landed["qapixel"]
        sr_info = raster_grid_info(sr_path)
        vd_info = valid_mask_info(valid_path)
        qa_info = raster_grid_info(qa_path)
        for info in (sr_info, vd_info, qa_info):
            assert_grid_matches(info, grid.to_dict())
        n_bands = len(landsat.sr_bands(sensor))
        names = list(landsat.sr_bands(sensor))
        if sr_info["count"] != n_bands:
            raise ProvenanceError(
                f"{bundle.row['product_id']}: expected {n_bands} SR bands "
                f"for {sensor}, got {sr_info['count']}")
        if sr_info["dtypes"] != ["float32"] * n_bands:
            raise ProvenanceError(
                f"{bundle.row['product_id']}: SR must be {n_bands}x float32, "
                f"got {sr_info['dtypes']}")
        if list(sr_info["band_names"]) != names:
            raise ProvenanceError(
                f"{bundle.row['product_id']}: band order "
                f"{sr_info['band_names']} != {names}")
        if qa_info["dtypes"] != ["uint16"]:
            raise ProvenanceError(
                f"{bundle.row['product_id']}: QA_PIXEL must land uint16")
        physical, valid_stats = landsat_physical_audit(
            sensor, str(sr_path), str(valid_path))
        if not physical["pass"]:
            raise ProvenanceError(
                f"{bundle.row['product_id']}: landsat physical audit fail: "
                f"{[k for k, ok in physical['checks'].items() if not ok]}")
        qa = {
            "physical_audit": physical,
            "valid_band_stats": valid_stats,
            "observed": observed_fractions(str(sr_path)),
            "valid_mask": {k: vd_info[k] for k in
                           ("valid_fraction", "unique_values",
                            "unique_value_counts", "total_pixel_count",
                            "valid_pixel_count")},
            "qa_pixel_dtype": qa_info["dtypes"],
            "qa_pixel_grid": {k: qa_info[k] for k in
                              ("count", "dtypes", "nodata")}}
    elif sensor == "sentinel2":
        sr_path = landed["sr"]
        valid_path = landed["valid"]
        sr_info = raster_grid_info(sr_path)
        vd_info = valid_mask_info(valid_path)
        assert_grid_matches(sr_info, grid.to_dict())
        assert_grid_matches(vd_info, grid.to_dict())
        if sr_info["count"] != 4 or sr_info["dtypes"] != ["float32"] * 4:
            raise ProvenanceError(
                f"{bundle.row['product_id']}: S2 SR must be 4x float32")
        if list(sr_info["band_names"]) != list(TEN_M_BANDS):
            raise ProvenanceError(
                f"{bundle.row['product_id']}: band order "
                f"{sr_info['band_names']}")
        sanity = reflectance_sanity_masked(
            str(sr_path), str(valid_path), list(TEN_M_BANDS))
        if not sanity["scaling_check_pass"]:
            raise ProvenanceError(
                f"{bundle.row['product_id']}: S2 scaling sanity fail")
        qa = {
            "reflectance_sanity": sanity,
            "observed": observed_fractions(str(sr_path)),
            "valid_mask": {k: vd_info[k] for k in
                           ("valid_fraction", "unique_values",
                            "unique_value_counts", "total_pixel_count",
                            "valid_pixel_count")}}
    else:  # sentinel1
        path = landed["vvvh"]
        info = raster_grid_info(path)
        assert_grid_matches(info, grid.to_dict())
        if (info["count"] != 2
                or info["dtypes"] != ["float32", "float32"]
                or list(info["band_names"]) != ["VV", "VH"]):
            raise ProvenanceError(
                f"{bundle.row['product_id']}: S1 must be VV,VH float32")
        physical = s1_physical_audit(str(path))
        s1_image = next(c.image for c in bundle.components if c.role == "vvvh")
        stats = band_stats(str(path), ["VV", "VH"], is_db=True)
        server_stats = server_recompute_stats(
            ee, s1_image, bundle.region, grid, ["VV", "VH"])
        identity = compare_landed_vs_server(
            stats, server_stats, ["VV", "VH"], extrema_tol=1.0, pct_tol=0.6)
        if not physical["pass"] or not identity["pass"]:
            raise ProvenanceError(
                f"{bundle.row['product_id']}: S1 dB/identity audit failed "
                f"(physical={physical['pass']}, "
                f"server_match={identity['pass']})")
        qa = {"physical_audit": physical,
              "server_identity_check": identity,
              "observed": observed_fractions(str(path))}
    return qa


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

@dataclass
class _Job:
    bundle: Bundle
    backend_ids: dict[str, str] = field(default_factory=dict)
    deadlines: dict[str, float] = field(default_factory=dict)
    ready_since: float | None = None


def _safe_result(raw: dict[str, Any]) -> dict[str, Any]:
    return {k: raw.get(k) for k in TASK_RESULT_KEYS if k in raw}


def task_is_adoptable(record: TaskRecord) -> bool:
    """True when a store record already owns a live backend task.

    ENQUEUED/RUNNING/COMPLETED records with a backend id are resumed,
    never duplicated; only PENDING records (failed attempts with
    attempts < max) are submitted again.
    """
    return bool(record.backend_task_id) and record.state != STATE_PENDING


def polled_download(prefix: str, deadline_s: float) -> tuple[str, bytes]:
    while True:
        try:
            return driveio.download_latest(prefix)
        except driveio.DriveDownloadError:
            if time.monotonic() >= deadline_s:
                raise
            time.sleep(10)


class ExportScheduler:
    def __init__(
        self, ee: Any, store: TaskStore, panel: pd.DataFrame,
        *, concurrency: int, poll_interval_s: int,
        task_timeout_s: int, hard_stop_on_failure: bool,
    ) -> None:
        self.ee = ee
        self.store = store
        self.panel = panel
        self.concurrency = max(1, concurrency)
        self.poll_interval_s = poll_interval_s
        self.task_timeout_s = task_timeout_s
        self.hard_stop_on_failure = hard_stop_on_failure
        self.failures: list[dict[str, Any]] = self._load_failures()
        self.landed_pids: set[str] = self._discover_landed()
        self.total_landed_bytes = self._sum_landed_bytes()
        self.active: dict[str, _Job] = {}
        self.queue: list[dict[str, Any]] = []
        self.stop = False

    # -- ledger ------------------------------------------------------------
    def _load_failures(self) -> list[dict[str, Any]]:
        if FAILURES_JSON.exists():
            return list(json.loads(
                FAILURES_JSON.read_text("utf-8")).get("failures", []))
        return []

    def _record_failure(self, row: dict[str, Any], stage: str, detail: str) -> None:
        self.failures.append({
            "utc": _now(), "product_id": row["product_id"],
            "cell_id": row["cell_id"], "sensor": row["sensor"],
            "stage": stage, "detail": detail})
        FAILURES_JSON.parent.mkdir(parents=True, exist_ok=True)
        FAILURES_JSON.write_text(
            json.dumps({"failures": self.failures}, indent=2, default=str),
            encoding="utf-8")

    def _supersede_prior_failures(self, pid: str) -> None:
        """Mark earlier ledger entries for a reactivated product superseded."""
        changed = False
        for entry in self.failures:
            if (entry.get("product_id") == pid
                    and not entry.get("superseded")):
                entry["superseded"] = True
                entry["superseded_utc"] = _now()
                entry["superseded_by"] = "successful_reactivation_run"
                changed = True
        if changed:
            FAILURES_JSON.write_text(
                json.dumps({"failures": self.failures}, indent=2,
                           default=str),
                encoding="utf-8")

    def _manifest_path(self, pid: str) -> Path:
        return MANIFEST_DIR / f"{pid}.json"

    def _discover_landed(self) -> set[str]:
        out: set[str] = set()
        MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
        for path in sorted(MANIFEST_DIR.glob("*.json")):
            doc = json.loads(path.read_text("utf-8"))
            pid = str(doc["product_id"])
            for f in doc["landed_files"]:
                if sha256_file(f["local_uri"]) != f["sha256"]:
                    raise ProvenanceError(
                        f"{pid}: landed file re-hash mismatch at "
                        f"{f['local_uri']}; refusing")
            out.add(pid)
        return out

    def _sum_landed_bytes(self) -> int:
        total = 0
        for pid in self.landed_pids:
            doc = json.loads(self._manifest_path(pid).read_text("utf-8"))
            total += sum(int(f["size_bytes"]) for f in doc["landed_files"])
        return total

    # -- task submission ---------------------------------------------------
    def _region_geometry(self, bundle: Bundle) -> Any:
        coords = bundle.region["coordinates"][0]
        return self.ee.Geometry.Rectangle(coords, bundle.region["crs"], False)

    def _record(self, comp: Component) -> TaskRecord:
        record = self.store.get_by_request_id(comp.request_id)
        if record is None:
            raise ProvenanceError(
                f"task store missing submitted request {comp.request_id}")
        return record

    def _submit_component(self, bundle: Bundle, comp: Component) -> str:
        """Submit, resume-retry, or adopt a task; return its backend id."""
        existing = self.store.get_by_request_id(comp.request_id)
        if existing is not None and task_is_adoptable(existing):
            # Adopt ENQUEUED/RUNNING/COMPLETED tasks left by a previous
            # process; never submit a duplicate. Only PENDING records
            # (after a recorded failed attempt) are resubmitted.
            return str(existing.backend_task_id)
        task = self.ee.batch.Export.image.toDrive(
            image=comp.image, description=comp.prefix,
            folder=GDRIVE_FOLDER, fileNamePrefix=comp.prefix,
            region=self._region_geometry(bundle), crs=bundle.grid.crs,
            crsTransform=list(bundle.grid.transform),
            dimensions=[bundle.grid.width, bundle.grid.height],
            maxPixels=1_000_000_000, fileFormat="GeoTIFF")
        record = (self.store.create(comp.request_id)
                  if existing is None else existing)
        task.start()
        self.store.mark_enqueued(record.task_id, str(task.id))
        self.store.record_poll_state(
            record.task_id, "READY", detail="observed after task.start()")
        return str(task.id)

    def _activate(self, row: dict[str, Any]) -> None:
        pid = str(row["product_id"])
        try:
            bundle = build_bundle(self.ee, row, self.panel)
            job = _Job(bundle=bundle)
            for comp in bundle.components:
                backend_id = self._submit_component(bundle, comp)
                job.backend_ids[comp.role] = backend_id
                job.deadlines[comp.role] = (
                    time.monotonic() + self.task_timeout_s)
            self._supersede_prior_failures(pid)
            self.active[pid] = job
            print(f"[pilot19] {pid} submitted "
                  f"{len(bundle.components)} task(s)", flush=True)
        except Exception as exc:  # provenance/build failure -> ledger
            self._record_failure(
                row, "BUILD_OR_SUBMIT", f"{type(exc).__name__}: {exc}")
            if self.hard_stop_on_failure:
                self.stop = True

    # -- polling -----------------------------------------------------------
    def _poll_cycle(self) -> None:
        pending: list[tuple[str, _Job, str, str]] = []
        for pid, job in self.active.items():
            for comp in job.bundle.components:
                record = self._record(comp)
                if record.state == STATE_COMPLETED:
                    continue
                pending.append(
                    (pid, job, comp.role, job.backend_ids[comp.role]))
        for start in range(0, len(pending), POLL_BATCH):
            chunk = pending[start:start + POLL_BATCH]
            ids = [backend_id for _, _, _, backend_id in chunk]
            statuses = self.ee.data.getTaskStatus(ids)
            for (pid, job, role, _backend), raw in zip(
                    chunk, statuses, strict=True):
                self._handle_status(pid, job, role, dict(raw))

    def _handle_status(
        self, pid: str, job: _Job, role: str, raw: dict[str, Any],
    ) -> None:
        state = str(raw.get("state"))
        comp = next(c for c in job.bundle.components if c.role == role)
        record = self._record(comp)
        if state == STATE_COMPLETED:
            self.store.record_poll_state(record.task_id, state)
            self.store.mark_completed(record.task_id, result=_safe_result(raw))
            return
        if state not in GEE_FAILED_STATES:
            self.store.record_poll_state(record.task_id, state)
            return
        self.store.record_poll_state(record.task_id, state)
        self.store.record_attempt_error(
            record.task_id, f"{state}: {raw.get('error_message')}")
        rec = self.store.get(record.task_id)
        if rec.state == STATE_PENDING and not self.stop:
            backend_id = self._submit_component(job.bundle, comp)
            job.backend_ids[role] = backend_id
            job.deadlines[role] = time.monotonic() + self.task_timeout_s
            print(f"[pilot19] {pid}:{role} resubmitted "
                  f"(attempt {rec.attempts + 1})", flush=True)
            return
        self._record_failure(
            job.bundle.row, f"GEE_TASK_{role}",
            f"{state}: {raw.get('error_message')}")
        if self.hard_stop_on_failure:
            self.stop = True

    def _timeouts(self) -> None:
        for _pid, job in list(self.active.items()):
            for comp in job.bundle.components:
                role = comp.role
                record = self._record(comp)
                if record.state == STATE_COMPLETED:
                    continue
                if time.monotonic() < job.deadlines[role]:
                    continue
                self.store.record_attempt_error(
                    record.task_id,
                    f"client timeout after {self.task_timeout_s}s "
                    f"(last store state {record.state})")
                rec = self.store.get(record.task_id)
                if rec.state == STATE_PENDING and not self.stop:
                    backend_id = self._submit_component(job.bundle, comp)
                    job.backend_ids[role] = backend_id
                    job.deadlines[role] = time.monotonic() + self.task_timeout_s
                    continue
                self._record_failure(
                    job.bundle.row, f"TIMEOUT_{role}",
                    f"task timed out after {self.task_timeout_s}s")
                if self.hard_stop_on_failure:
                    self.stop = True

    # -- completion / landing ---------------------------------------------
    def _product_states(self, job: _Job) -> dict[str, str]:
        return {comp.role: self._record(comp).state
                for comp in job.bundle.components}

    def _try_complete(self, pid: str, job: _Job) -> bool:
        states = self._product_states(job)
        if any(s == STATE_FAILED for s in states.values()):
            return True  # failure ledger already written; drop job
        if not all(s == STATE_COMPLETED for s in states.values()):
            return False
        if job.ready_since is None:
            job.ready_since = time.monotonic()
        try:
            self._land_and_validate(pid, job)
        except driveio.DriveDownloadError as exc:
            if time.monotonic() > job.ready_since + DRIVE_PROPAGATION_S:
                self._record_failure(job.bundle.row, "DRIVE_DOWNLOAD", str(exc))
                if self.hard_stop_on_failure:
                    self.stop = True
                return True
            return False  # wait for Drive propagation
        except Exception as exc:
            self._record_failure(
                job.bundle.row, "LAND_OR_VALIDATE",
                f"{type(exc).__name__}: {exc}")
            if self.hard_stop_on_failure:
                self.stop = True
            return True
        return True

    def _land_and_validate(self, pid: str, job: _Job) -> None:
        bundle = job.bundle
        row = bundle.row
        landed: dict[str, Path] = {}
        files: list[dict[str, Any]] = []
        deadline = time.monotonic() + DRIVE_PROPAGATION_S
        for comp in bundle.components:
            name, data = polled_download(comp.prefix, deadline)
            path = PRODUCT_DIR / f"{comp.prefix}.tif"
            landed_record = land_bytes(path, data)
            landed[comp.role] = path
            files.append({**landed_record, "role": comp.role,
                          "drive_file_name": name,
                          "drive_folder": GDRIVE_FOLDER,
                          "grid_verified": False})
        qa = validate_bundle(self.ee, bundle, landed)
        product_bytes = sum(int(f["size_bytes"]) for f in files)
        if self.total_landed_bytes + product_bytes > VOLUME_CAP_BYTES:
            raise ProvenanceError(
                f"pilot volume cap {VOLUME_CAP_BYTES} bytes exceeded; STOP")
        for f in files:
            f["grid_verified"] = True
            f["sha256"] = sha256_file(f["local_uri"])
        tasks = []
        for comp in bundle.components:
            rec = self._record(comp)
            tasks.append({
                "role": comp.role, "prefix": comp.prefix,
                "request_id": comp.request_id,
                "task_id": rec.backend_task_id,
                "store_task_id": rec.task_id,
                "attempts": rec.attempts,
                "state": rec.state,
                "terminal_result": dict(rec.result),
                "state_history": list(rec.state_history)})
        panel_row = self.panel.loc[str(row["cell_id"])]
        bundle_payload = {
            "product_id": pid, "cell_id": row["cell_id"],
            "sensor": row["sensor"], "grid": bundle.grid.to_dict(),
            "source_scene_ids": _scene_ids(row),
            "files": sorted(
                ({"role": f["role"], "sha256": f["sha256"],
                  "size_bytes": f["size_bytes"]} for f in files),
                key=lambda x: str(x["role"])),
            "processing_config_sha256": canonical_fingerprint(bundle.proc)}
        manifest = {
            "schema": "spartina_observation_product_v0",
            "product_id": pid,
            "issue": "#19 M2.5 national 20-cell pilot",
            "cell_id": row["cell_id"],
            "observation_event_id": row.get("event_id"),
            "sensor": row["sensor"],
            "science_stream": bundle.science_stream,
            "year": int(row["year"]),
            "priority": row.get("priority"),
            "variant": row.get("variant"),
            "region_province": str(panel_row["region_province"]),
            "coastal_segment": str(panel_row["coastal_segment"]),
            "source_scene_ids": _scene_ids(row),
            "source_product_ids_planned": row.get("product_ids_source"),
            "acquisition_utc_planned": row.get("event_utc"),
            "day_of_year": int(row["doy"]),
            "season_tag": row.get("season_tag"),
            "orbit_pass": row.get("pass"),
            "relative_orbit": row.get("relative_orbit"),
            "platform": row.get("platform"),
            "wrs_path": row.get("wrs_path"),
            "wrs_row": row.get("wrs_row"),
            "mgrs_tiles_planned": row.get("mgrs_tiles"),
            "member_scene_count": int(row["member_scene_count"]),
            "native_resolution_m": bundle.native_resolution_m,
            "coverage": row.get("coverage"),
            "coverage_tier": row.get("coverage_tier"),
            "coverage_basis": row.get("coverage_basis"),
            "coverage_fraction_planned": row.get("coverage_fraction"),
            "cloud_fraction_planned": row.get("cloud_fraction"),
            "utm_zone": bundle.zone,
            "grid_spec": bundle.grid.to_dict(),
            "grid_sha256": canonical_fingerprint(bundle.grid.to_dict()),
            "region": bundle.region,
            "build_revision": (
                "pilot19 r1/r2: national generalisation of M2.1b r4/r5; "
                "projected-CRS rectangle + explicit dimensions; Landsat "
                "fill-before-scale DN=0 nodata semantics; L5/L7 six SR "
                "bands; S2 s2_scl_qa_v1_1 x four-band observation mask; "
                "S1 identity dB; landsat VALID r2 intersects all-SR-bands-"
                "observed (r1 VALID superseded after pilot D1 finding)"),
            "processing_config": bundle.proc,
            "qa": qa,
            "export_tasks": tasks,
            "landed_files": files,
            "gdrive_folder": GDRIVE_FOLDER,
            "n_bytes": product_bytes,
            "label_policy": {
                "gold_promoted": False,
                "unlabeled_is_negative": False,
                "label_bytes_modified": False,
                "note": ("label adapters are separate derived supports; "
                         "GOLD = 0; fractions are SILVER occupancy only")},
            "bundle": {"fingerprint_sha256":
                      canonical_fingerprint(bundle_payload),
                      "payload": bundle_payload},
            "git": git_context(REPO_ROOT),
            "environment": runtime_environment(),
            "created_utc": _now()}
        MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
        self._manifest_path(pid).write_text(
            json.dumps(manifest, indent=2, sort_keys=True, default=str),
            encoding="utf-8")
        self.landed_pids.add(pid)
        self.total_landed_bytes += product_bytes
        print(f"[pilot19] {pid} LANDED: {len(files)} file(s), "
              f"{product_bytes / 1e6:.1f} MB", flush=True)

    # -- main loop ---------------------------------------------------------
    def run(self, scope: list[dict[str, Any]]) -> None:
        self.queue = [r for r in scope
                      if str(r["product_id"]) not in self.landed_pids]
        self.write_progress(scope)
        while (self.queue or self.active) and not self.stop:
            while (self.queue and len(self.active) < self.concurrency
                   and not self.stop):
                self._activate(self.queue.pop(0))
            if not self.active:
                break
            self._poll_cycle()
            self._timeouts()
            for pid in list(self.active):
                if self._try_complete(pid, self.active[pid]):
                    del self.active[pid]
            self.write_progress(scope)
            if (self.queue or self.active) and not self.stop:
                time.sleep(self.poll_interval_s)
        self.write_progress(scope)
        if self.stop:
            print("[pilot19] HARD STOP (canary gate failure); no further "
                  "tasks submitted", flush=True)

    # -- progress ledger ---------------------------------------------------
    def _active_state(self, job: _Job) -> str:
        states = set(self._product_states(job).values())
        if STATE_RUNNING in states:
            return _STATE_RUNNING
        return _STATE_SUBMITTED

    def write_progress(self, scope: list[dict[str, Any]]) -> None:
        failed_pids = {f["product_id"] for f in self.failures
             if not f.get("superseded")}
        active_map = {pid: self._active_state(job)
                      for pid, job in self.active.items()}
        summary = summarize_states(
            [str(r["product_id"]) for r in scope],
            self.landed_pids, failed_pids, active_map)
        products = [{
            "product_id": str(row["product_id"]),
            "cell_id": row["cell_id"],
            "sensor": row["sensor"],
            "year": int(row["year"]),
            "state": summary["by_product"][str(row["product_id"])],
            "n_components": len(COMPONENTS[str(row["sensor"])]),
            "manifest": (
                str(self._manifest_path(str(row["product_id"]))
                    .relative_to(REPO_ROOT))
                if str(row["product_id"]) in self.landed_pids else None)}
            for row in scope]
        doc = {
            "product": "national_pilot19_pixel_export_progress_v1",
            "issue": 19,
            "updated_utc": _now(),
            "gdrive_folder": GDRIVE_FOLDER,
            "revision": REVISION,
            "component_revisions": {
                "default": REVISION,
                "landsat:valid": LANDSAT_VALID_REVISION},
            "states": summary["states"],
            "total_landed_bytes": self.total_landed_bytes,
            "volume_cap_bytes": VOLUME_CAP_BYTES,
            "hard_stop": self.stop,
            "products": products,
            "failures": self.failures,
            "git": git_context(REPO_ROOT),
            "environment": runtime_environment()}
        PROGRESS_JSON.parent.mkdir(parents=True, exist_ok=True)
        PROGRESS_JSON.write_text(
            json.dumps(doc, indent=2, default=str), encoding="utf-8")


def summarize_states(
    scope_pids: list[str], landed: set[str], failed: set[str],
    active: dict[str, str],
) -> dict[str, Any]:
    """Pure state rollup (SELECTED/SUBMITTED/RUNNING/LANDED/EXPORT_FAILED)."""
    by_product: dict[str, str] = {}
    for pid in scope_pids:
        if pid in landed:
            by_product[pid] = _STATE_LANDED
        elif pid in active:
            by_product[pid] = active[pid]
        elif pid in failed:
            by_product[pid] = _STATE_FAILED
        else:
            by_product[pid] = _STATE_SELECTED
    states: dict[str, int] = {
        _STATE_SELECTED: 0, _STATE_SUBMITTED: 0, _STATE_RUNNING: 0,
        _STATE_LANDED: 0, _STATE_FAILED: 0}
    for state in by_product.values():
        states[state] += 1
    return {"states": states, "by_product": by_product}


# ---------------------------------------------------------------------------
# Aggregate ledger
# ---------------------------------------------------------------------------

def write_aggregate(
    scope: list[dict[str, Any]], store: TaskStore,
    failures: list[dict[str, Any]], *, canary: bool,
    plan_checksum: str, hard_stop: bool,
) -> None:
    rows: list[dict[str, Any]] = []
    total = 0
    for row in scope:
        pid = str(row["product_id"])
        manifest_path = MANIFEST_DIR / f"{pid}.json"
        entry: dict[str, Any] = {
            "product_id": pid, "cell_id": row["cell_id"],
            "sensor": row["sensor"], "year": int(row["year"]),
            "coverage_tier": row.get("coverage_tier"),
            "state": _STATE_SELECTED,
            "n_tasks_planned": len(COMPONENTS[str(row["sensor"])]),
            "n_files_landed": 0, "bytes": 0,
            "manifest": None, "sha_by_role": None}
        if manifest_path.exists():
            doc = json.loads(manifest_path.read_text("utf-8"))
            entry["state"] = _STATE_LANDED
            entry["n_files_landed"] = len(doc["landed_files"])
            entry["bytes"] = int(doc["n_bytes"])
            entry["manifest"] = str(manifest_path.relative_to(REPO_ROOT))
            entry["sha_by_role"] = json.dumps(
                {f["role"]: f["sha256"] for f in doc["landed_files"]},
                sort_keys=True)
            total += entry["bytes"]
        elif any(f.get("product_id") == pid
                     and not f.get("superseded") for f in failures):
            entry["state"] = _STATE_FAILED
        rows.append(entry)
    state_counts: dict[str, int] = {}
    for entry in rows:
        state_counts[str(entry["state"])] = (
            state_counts.get(str(entry["state"]), 0) + 1)
    doc = {
        "manifest_id": "national_pilot19_pixel_export_v1",
        "issue": 19,
        "created_utc": _now(),
        "scope": "canary_5_products" if canary else "frozen_20_cell_pilot",
        "canary": canary,
        "n_products_selected": len(scope),
        "product_states": state_counts,
        "task_store_counts": store.counts(),
        "n_tasks_planned": sum(
            len(COMPONENTS[str(r["sensor"])]) for r in scope),
        "total_landed_bytes": total,
        "total_landed_gib": round(total / 1024**3, 3),
        "volume_cap_bytes": VOLUME_CAP_BYTES,
        "hard_stop": hard_stop,
        "event_plan_csv_sha256": plan_checksum,
        "gdrive_folder": GDRIVE_FOLDER,
        "products": rows,
        "failures": failures,
        "git": git_context(REPO_ROOT),
        "environment": runtime_environment()}
    OUT_JSON.write_text(
        json.dumps(doc, indent=2, default=str), encoding="utf-8")
    pd.DataFrame(rows).to_csv(OUT_CSV, index=False)
    print(f"[pilot19] aggregate: {state_counts}; "
          f"{total / 1024**2:.1f} MiB landed", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canary", action="store_true",
                        help="export only the frozen 5-product canary")
    parser.add_argument("--only-sensor",
                        choices=["landsat5", "landsat7", "landsat8",
                                 "sentinel1", "sentinel2"])
    parser.add_argument("--products", default="",
                        help="comma-separated product_id allowlist")
    parser.add_argument("--concurrency", type=int, default=7)
    parser.add_argument("--task-timeout-s", type=int, default=TASK_TIMEOUT_S)
    parser.add_argument("--poll-interval-s", type=int, default=POLL_INTERVAL_S)
    args = parser.parse_args()

    if os.environ.get("SPARTINA_PILOT19_EXPORT") != "1":
        raise SystemExit(
            "real pilot export needs SPARTINA_PILOT19_EXPORT=1 (explicit "
            "operator opt-in); scope is the frozen Issue #19 plan only")
    if configured_project() is None:
        raise SystemExit("export SPARTINA_GEE_PROJECT=<project-id> first")
    initialize()
    import ee

    products_filter = tuple(
        p.strip() for p in args.products.split(",") if p.strip())
    scope = load_scope(
        canary=args.canary, only_sensor=args.only_sensor,
        products_filter=products_filter)
    if not scope:
        raise SystemExit("empty scope after frozen-plan filters; abort")
    n_tasks = sum(len(COMPONENTS[str(r["sensor"])]) for r in scope)
    print(f"[pilot19] scope: {len(scope)} products / {n_tasks} component "
          f"tasks (canary={args.canary})", flush=True)

    PRODUCT_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    TASK_STORE.parent.mkdir(parents=True, exist_ok=True)
    store = TaskStore(TASK_STORE)
    panel = load_panel()
    scheduler = ExportScheduler(
        ee, store, panel, concurrency=args.concurrency,
        poll_interval_s=args.poll_interval_s,
        task_timeout_s=args.task_timeout_s,
        hard_stop_on_failure=args.canary)
    scheduler.run(scope)
    write_aggregate(
        scope, store, scheduler.failures, canary=args.canary,
        plan_checksum=plan_csv_sha256(), hard_stop=scheduler.stop)
    if scheduler.stop:
        print("CANARY_FAIL: systematic canary failure; remaining tasks "
              "NOT submitted", flush=True)
        return 2
    if args.canary:
        print("canary products landed; proceed to Phase H/I QA gate "
              "before any further export", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
