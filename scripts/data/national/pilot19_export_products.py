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

``--plan-version v2`` runs the owner-approved PILOT_EVENT_SELECTION_V2
recovery: scope is the checksum-gated plan_v2 (187 eligible, not 194);
V1 bytes of replaced slots move to products/manifests_v1_superseded with
an index; retained products get a metadata-only schema v1 bump (raw
bytes/SHA untouched) and S1 products gain the locally derived uint8
``s1_dualpol_valid_v2`` token (finite VV/VH AND > -70 dB; raw dB
preserved per F3); replacement S2/S1 raw exports use r2 request ids so
V1 tasks are never adopted; landed bytes are re-gated at 0.95 actual
coverage against the V2 plan measurement.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
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

PLAN_V1_CSV = REPO_ROOT / "datasets/manifests/national_pilot_event_plan_v1.csv"
PLAN_V1_JSON = REPO_ROOT / "datasets/manifests/national_pilot_event_plan_v1.json"
PLAN_V2_CSV = REPO_ROOT / "datasets/manifests/national_pilot_event_plan_v2.csv"
PLAN_V2_JSON = REPO_ROOT / "datasets/manifests/national_pilot_event_plan_v2.json"
# Backwards-compatible aliases (V1 remains the default behaviour).
PLAN_CSV = PLAN_V1_CSV
PLAN_JSON = PLAN_V1_JSON
PANEL_CSV = REPO_ROOT / "datasets/manifests/national_first_pixel_panel_v1.csv"
CANARY_CSV = REPO_ROOT / "datasets/manifests/national_pilot19_canary_v1.csv"
CANARY_V2_CSV = REPO_ROOT / "datasets/manifests/national_pilot19_canary_v2.csv"
WORK_DIR = REPO_ROOT / "work" / "national" / "pilot19"
PRODUCT_DIR = WORK_DIR / "products"
MANIFEST_DIR = WORK_DIR / "manifests"
#: Issue #19 V2 recovery: V1 bytes/manifests of events that FAIL the actual
#: mask gate (empty S2 datatakes, partial S1 frames) are moved here before
#: their slot is re-exported under r2. Nothing V1 is deleted or overwritten.
PRODUCTS_V1_SUPERSEDED_DIR = WORK_DIR / "products_v1_superseded"
MANIFESTS_V1_SUPERSEDED_DIR = WORK_DIR / "manifests_v1_superseded"
SUPERSESSION_INDEX = WORK_DIR / "v1_v2_product_supersession_index.json"
TASK_STORE = WORK_DIR / "tasks" / "task_store.json"
FAILURES_JSON = WORK_DIR / "failures.json"
PROGRESS_JSON_V1 = WORK_DIR / "export_progress.json"
PROGRESS_JSON_V2 = WORK_DIR / "export_progress_v2.json"
PROGRESS_JSON = PROGRESS_JSON_V1
OUT_V1_CSV = REPO_ROOT / "datasets/manifests/national_pilot19_pixel_export_v1.csv"
OUT_V1_JSON = REPO_ROOT / "datasets/manifests/national_pilot19_pixel_export_v1.json"
OUT_V2_CSV = REPO_ROOT / "datasets/manifests/national_pilot19_pixel_export_v2.csv"
OUT_V2_JSON = REPO_ROOT / "datasets/manifests/national_pilot19_pixel_export_v2.json"
OUT_CSV = OUT_V1_CSV
OUT_JSON = OUT_V1_JSON

GDRIVE_FOLDER = "SpartinaEarthPilot19"
REVISION = "r1"
#: Landsat VALID component revision r2: pilot D1 found QA-clear pixels with
#: per-band SR nodata (interior B1/B2 NaN under clear QA). VALID now
#: also requires every SR band observed. SR/QA_PIXEL stay r1 (same pixels).
LANDSAT_VALID_REVISION = "r2"
#: Sentinel raw components (S2 sr/valid, S1 vvvh) for V2 REPLACED events are
#: re-exported under r2 request ids/prefixes: r1 stays owned by the failed
#: V1 event, so task adoption can never download old-event bytes for a
#: replaced slot. KEPT events keep r1 bytes and r1 request ids untouched.
SENTINEL_V2_REPLACED_REVISION = "r2"

# -- PILOT_EVENT_SELECTION_V2 (owner-approved F1/F3 recovery) -----------
SELECTION_V2 = "PILOT_EVENT_SELECTION_V2"
SELECTION_V1_LANDSAT_INHERITED = "PILOT_EVENT_SELECTION_V1_INHERITED_LANDSAT"
SCHEMA_V0 = "spartina_observation_product_v0"
SCHEMA_V1 = "spartina_observation_product_v1"
STATUS_V2_ELIGIBLE = "V2_ELIGIBLE"
CHANGE_KEPT = "KEPT_SAME_EVENT_PASSES_ACTUAL_MASK"
CHANGE_REPLACED = "REPLACED_V1_EVENT_FAILED_ACTUAL_MASK"
CHANGE_LANDSAT = "V1_INHERITED_LANDSAT"
ACTUAL_MASK_GATE = 0.95
S1_FLOOR_DB = -70.0
#: Locally derived S1 observation-validity token (never a GEE task; derived
#: deterministically from the identity-preserved vvvh raster).
S1_VALID_V2_ROLE = "dualpol_valid_v2"
S1_VALID_V2_REVISION = "v2"
S1_VALID_V2_TOKEN = "s1_dualpol_valid_v2"
#: Live-replay vs byte agreement on the export grid was validated to four
#: decimals (V2 manifest rules); allow a small resampling edge margin on
#: LIVE-evidence rows, require exact agreement for LANDED-bytes rows.
ACTUAL_MASK_LIVE_TOL = 2e-3
ACTUAL_MASK_LANDED_TOL = 1e-6
BASIS_S2_V2 = "V2_SAME_DATATAKE_UNION_ACTUAL_SR_MASK_OVER_EXPORT_GRID"
BASIS_S1_V2 = "V2_DUALPOL_ACTUAL_MASK_INCL_EXTREME_FLOOR_OVER_EXPORT_GRID"
BASIS_LANDSAT_INHERITED = (
    "V1_INHERITED_R2_ALL_SR_BANDS_OBSERVED_POSTEXPORT_BYTE_FRACTION")


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

#: V2-only roles derived LOCALLY from landed bytes (never GEE tasks). The S1
#: token is s1_dualpol_valid_v2: finite(VV) AND finite(VH) AND VV > -70 dB
#: AND VH > -70 dB; raw vvvh stays identity-preserved and is never clipped.
DERIVED_COMPONENTS_V2: dict[str, tuple[str, ...]] = {
    "landsat5": (), "landsat7": (), "landsat8": (),
    "sentinel2": (),
    "sentinel1": (S1_VALID_V2_ROLE,),
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

def plan_paths(plan_version: str = "v1") -> tuple[Path, Path]:
    if plan_version == "v1":
        return PLAN_V1_CSV, PLAN_V1_JSON
    if plan_version == "v2":
        return PLAN_V2_CSV, PLAN_V2_JSON
    raise ValueError(f"unknown plan version {plan_version!r}")


def plan_csv_sha256(plan_version: str = "v1") -> str:
    csv_path, json_path = plan_paths(plan_version)
    plan_doc = json.loads(json_path.read_text(encoding="utf-8"))
    key = ("plan_csv_sha256" if plan_version == "v1"
           else "plan_v2_csv_sha256")
    expected = str(plan_doc["checksums"][key])
    actual = sha256_file(csv_path)
    if actual != expected:
        raise ProvenanceError(
            f"frozen {plan_version} plan CSV checksum mismatch: expected "
            f"{expected}, got {actual}; refusing export")
    return expected


def _v2_eligible(frame: pd.DataFrame) -> pd.DataFrame:
    """V2 production scope: actual-mask-eligible S2/S1 + inherited landsat.

    Landsat rows keep V1 status SELECTED under change
    V1_INHERITED_LANDSAT; S2/S1 rows must be V2_ELIGIBLE. Anything
    NO_ELIGIBLE_EVENT_ACTUAL_MASK / NO_SCENE is excluded honestly.
    """
    is_landsat = frame["sensor"].astype(str).str.startswith("landsat")
    landsat_ok = is_landsat & (frame["status"] == "SELECTED") & (
        frame["v2_change"] == CHANGE_LANDSAT)
    sentinel_ok = (~is_landsat) & (frame["status"] == STATUS_V2_ELIGIBLE)
    return frame[landsat_ok | sentinel_ok].copy()


def load_scope(
    *, canary: bool, only_sensor: str | None,
    products_filter: tuple[str, ...] = (),
    plan_version: str = "v1",
) -> list[dict[str, Any]]:
    """Return the frozen, checksum-gated, eligible product rows to run."""
    csv_path, _json_path = plan_paths(plan_version)
    plan_csv_sha256(plan_version)
    plan = pd.read_csv(csv_path)
    plan = (plan[plan["status"] == "SELECTED"].copy()
            if plan_version == "v1" else _v2_eligible(plan))
    if canary:
        canary_csv = CANARY_CSV if plan_version == "v1" else CANARY_V2_CSV
        if not canary_csv.exists():
            raise FileNotFoundError(f"canary allowlist missing: {canary_csv}")
        allow = set(pd.read_csv(canary_csv)["product_id"].astype(str))
        plan = plan[plan["product_id"].astype(str).isin(allow)]
    if only_sensor:
        plan = plan[plan["sensor"] == only_sensor]
    if products_filter:
        wanted = set(products_filter)
        plan = plan[plan["product_id"].astype(str).isin(wanted)]
        missing = wanted - set(plan["product_id"].astype(str))
        if missing:
            raise ValueError(
                f"--products ids not eligible in frozen {plan_version} "
                f"plan: {sorted(missing)}")
    rows = [{k: _clean(v) for k, v in row.items()}
            for row in plan.to_dict("records")]
    rows.sort(key=lambda r: str(r["product_id"]))
    return rows


def load_panel() -> pd.DataFrame:
    return pd.read_csv(PANEL_CSV).set_index("cell_id")


def event_selection_block(
    row: dict[str, Any], plan_v2_checksum: str,
) -> dict[str, Any]:
    """Manifest provenance block for PILOT_EVENT_SELECTION_V2 products."""
    inherited = str(row["sensor"]).startswith("landsat")
    return {
        "revision": (SELECTION_V1_LANDSAT_INHERITED if inherited
                     else SELECTION_V2),
        "plan_csv": PLAN_V2_CSV.name,
        "plan_csv_sha256": plan_v2_checksum,
        "supersedes_plan_csv": PLAN_V1_CSV.name,
        "eligibility_status": row.get("status"),
        "v2_change": row.get("v2_change"),
        "actual_mask_gate": ACTUAL_MASK_GATE,
        "actual_observed_fraction_planned": (
            row.get("v2_actual_observed_fraction")),
        "candidates_evaluated": row.get("v2_candidates_evaluated"),
        "evidence_source": row.get("v2_evidence_source"),
        "label_independent": True,
        "threshold_relaxation_forbidden": True}


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


def component_revision(
    row: dict[str, Any], role: str, plan_version: str = "v1",
) -> str:
    """Component revision for a plan row.

    V2 replacement S2/S1 events export under r2 so their r1 request ids
    keep pointing at the failed V1 event (idempotent resume can never
    adopt the old task). KEPT events and all Landsat components keep
    their existing r1/r2 revisions; raw bytes are never resubmitted.
    """
    sensor = str(row["sensor"])
    base = role_revision(sensor, role)
    if plan_version != "v2" or sensor.startswith("landsat"):
        return base
    if str(row.get("v2_change")) == CHANGE_REPLACED:
        return SENTINEL_V2_REPLACED_REVISION
    return REVISION


def prefix_for(
    row: dict[str, Any], role: str, *, plan_version: str = "v1",
    revision: str | None = None,
) -> str:
    rev = revision or component_revision(row, role, plan_version)
    return (f"spartina_pilot19_{row['product_id']}_{role}_"
            f"{date_tag(row)}_{rev}")


def request_for(
    row: dict[str, Any], role: str, *, plan_version: str = "v1",
    revision: str | None = None,
) -> str:
    rev = revision or component_revision(row, role, plan_version)
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


def build_bundle(
    ee: Any, row: dict[str, Any], panel: pd.DataFrame, *,
    plan_version: str = "v1",
) -> Bundle:
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
            Component("sr", refl,
                      prefix_for(row, "sr", plan_version=plan_version),
                      request_for(row, "sr", plan_version=plan_version)),
            Component("valid", valid,
                      prefix_for(row, "valid", plan_version=plan_version),
                      request_for(row, "valid", plan_version=plan_version)),
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
            Component("sr", sr_img,
                      prefix_for(row, "sr", plan_version=plan_version),
                      request_for(row, "sr", plan_version=plan_version)),
            Component("valid", valid_img,
                      prefix_for(row, "valid", plan_version=plan_version),
                      request_for(row, "valid", plan_version=plan_version)),
            Component("qapixel", qa_img,
                      prefix_for(row, "qapixel", plan_version=plan_version),
                      request_for(row, "qapixel", plan_version=plan_version)),
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
            Component("vvvh", image,
                      prefix_for(row, "vvvh", plan_version=plan_version),
                      request_for(row, "vvvh", plan_version=plan_version)),
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
) -> tuple[dict[str, Any], dict[str, float | None]]:
    """Finite-robust, VALID-restricted physical audit of landed Landsat SR.

    Observed percentiles may legitimately reach the DN=65535 saturation
    cap (1.6022); the physical [-0.30, 1.30] gate is applied to QA-VALID
    pixels only. Non-finite pixels inside VALID and excessive saturation
    inside VALID are hard failures. Returns (audit, valid-only stats).
    """
    n_bands = len(landsat.sr_bands(sensor))
    with rasterio.open(valid_path) as vd:
        valid = vd.read(1) == 1
    stats: dict[str, float | None] = {}
    detail: dict[str, Any] = {"bands": {}}
    checks: dict[str, bool] = {}
    zero_valid_window = int(valid.sum()) == 0
    warnings: list[str] = []
    if zero_valid_window:
        warnings.append(
            "no QA-valid surface pixels in window (source scene "
            "quality: cloud/QA; export itself faithful)")
    with rasterio.open(sr_path) as sr:
        observed = sr.dataset_mask() > 0
        for i in range(1, n_bands + 1):
            band = f"sr_b{i}"
            arr = sr.read(i).astype("float64")
            finite = np.isfinite(arr)
            of = observed & finite
            vf = of & valid
            n_of = int(of.sum())
            n_vf = int(vf.sum())
            if n_of == 0:
                raise ProvenanceError(
                    f"{sr_path}:{band} fully nodata (export defect)")
            nonfinite_observed = int((observed & ~finite).sum())
            nonfinite_valid = int((valid & ~finite).sum())
            po = np.percentile(arr[of], [0, 1, 50, 99, 100])
            for key, value in zip(
                    ("min", "p01", "p50", "p99", "max"), po, strict=True):
                stats[f"{band}_obs_{key}"] = float(value)
            stats[f"{band}_observed_px"] = n_of
            stats[f"{band}_valid_px"] = n_vf
            sat = np.isclose(arr, SR_SATURATION_CAP, atol=1e-5)
            sat_observed = int((of & sat).sum())
            sat_valid = int((vf & sat).sum())
            sat_frac = sat_valid / max(n_vf, 1)
            if n_vf > 0:
                pv = np.percentile(arr[vf], [0, 1, 50, 99, 100])
                for key, value in zip(
                        ("min", "p01", "p50", "p99", "max"), pv,
                        strict=True):
                    stats[f"{band}_valid_{key}"] = float(value)
                range_ok = bool(pv[1] >= -0.30 and pv[3] <= 1.30)
                ordered_ok = bool(
                    pv[0] <= pv[1] <= pv[2] <= pv[3] <= pv[4])
            else:
                for key in ("min", "p01", "p50", "p99", "max"):
                    stats[f"{band}_valid_{key}"] = None
                range_ok = True  # vacuous: zero-valid is a quality WARN
                ordered_ok = True
            detail["bands"][band] = {
                "nonfinite_observed_pixels": nonfinite_observed,
                "nonfinite_valid_pixels": nonfinite_valid,
                "saturation_cap_value": SR_SATURATION_CAP,
                "saturated_observed_pixels": sat_observed,
                "saturated_valid_pixels": sat_valid,
                "saturated_valid_fraction": sat_frac}
            checks[f"{band}_no_nonfinite_in_valid"] = nonfinite_valid == 0
            checks[f"{band}_valid_physical_range"] = range_ok
            checks[f"{band}_valid_ordered"] = ordered_ok
            checks[f"{band}_saturation_in_valid_below_hard_fraction"] = (
                sat_frac <= SATURATION_IN_VALID_HARD_FRACTION)
    detail["sensor"] = sensor
    detail["n_sr_bands"] = n_bands
    detail["zero_valid_pixels"] = zero_valid_window
    detail["warnings"] = warnings
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


# ---------------------------------------------------------------------------
# PILOT_EVENT_SELECTION_V2 actual-mask checks + s1_dualpol_valid_v2 token
# ---------------------------------------------------------------------------

def s2_sr_actual_mask(sr_path: str) -> dict[str, Any]:
    """All-four-required-band observed fraction over the full export grid.

    Pixel-identical to the V2 selection evidence definition (B2/B3/B4/B8
    finite on the same locked grid).
    """
    with rasterio.open(sr_path) as src:
        total = int(src.width * src.height)
        observed = np.ones((src.height, src.width), dtype=bool)
        per_band: dict[str, float] = {}
        for i in range(1, src.count + 1):
            fin = np.isfinite(src.read(i))
            per_band[str(src.descriptions[i - 1]) or f"band_{i}"] = (
                float(fin.sum()) / total if total else 0.0)
            observed &= fin
        return {"grid_pixels": total,
                "observed_pixels": int(observed.sum()),
                "actual_observed_fraction": (
                    float(observed.mean()) if total else 0.0),
                "per_band_finite_fraction": per_band}


def mask_in_w10_cell_fraction(
    observed: np.ndarray[Any, Any], transform: Any,
    cell_id: str, utm_zone: int, pixel_m: float,
) -> dict[str, Any]:
    """Observed fraction of a boolean mask INSIDE the W10 cell.

    Owner F1 defines production eligibility on actual observed coverage
    over the W10 cell (pixel-centre rule), not on the larger covering
    export grid. The grid fraction is recorded separately as evidence.
    """
    from build_pilot_label_supports_v1 import (  # noqa: PLC0415
        cell_polygon_utm,
        pixel_centres_in_cell,
    )

    h, w = observed.shape
    inside = pixel_centres_in_cell(
        cell_polygon_utm(cell_id, utm_zone), transform, h, w, int(pixel_m))
    n_inside = int(inside.sum())
    n_obs = int((observed & inside).sum())
    return {"cell_pixels": n_inside,
            "observed_in_cell_pixels": n_obs,
            "actual_observed_fraction_in_w10_cell": (
                n_obs / n_inside if n_inside else 0.0)}


def sr_in_w10_cell_fraction(
    sr_path: str, cell_id: str, utm_zone: int, pixel_m: float,
) -> dict[str, Any]:
    """Joint all-required-SR-band observed fraction INSIDE the W10 cell."""
    with rasterio.open(sr_path) as src:
        observed = np.ones((src.height, src.width), dtype=bool)
        for i in range(1, src.count + 1):
            observed &= np.isfinite(src.read(i))
        return mask_in_w10_cell_fraction(
            observed, src.transform, cell_id, utm_zone, pixel_m)


def s1_dualpol_valid_v2_stats(vvvh_path: str) -> dict[str, Any]:
    """Dual-pol validity statistics from identity-preserved VV/VH bytes.

    Definition (owner-approved F3; identical to the V2 plan byte
    evidence): observed iff ``finite(VV) AND finite(VH) AND VV > -70 dB
    AND VH > -70 dB``. Pixels <= -70 dB are
    NON_OBSERVATION_EXTREME_FLOOR. The raw raster is never modified.
    """
    with rasterio.open(vvvh_path) as src:
        total = int(src.width * src.height)
        vv = src.read(1).astype("float64")
        vh = src.read(2).astype("float64")
    fin_vv = np.isfinite(vv)
    fin_vh = np.isfinite(vh)
    dual_finite = fin_vv & fin_vh
    floor_vv = dual_finite & (vv <= S1_FLOOR_DB)
    floor_vh = dual_finite & (vh <= S1_FLOOR_DB)
    floor_any = floor_vv | floor_vh
    valid = dual_finite & ~floor_any
    return {
        "grid_pixels": total,
        "finite_vv_pixels": int(fin_vv.sum()),
        "finite_vh_pixels": int(fin_vh.sum()),
        "dualpol_finite_pixels": int(dual_finite.sum()),
        "dualpol_finite_fraction": (
            float(dual_finite.mean()) if total else 0.0),
        "floor_pixels_vv_le_minus70": int(floor_vv.sum()),
        "floor_pixels_vh_le_minus70": int(floor_vh.sum()),
        "floor_pixels_either_band": int(floor_any.sum()),
        "floor_area_fraction": float(floor_any.mean()) if total else 0.0,
        "valid_pixels": int(valid.sum()),
        "actual_observed_fraction": (
            float(valid.mean()) if total else 0.0),
        "mask": valid}


def write_s1_valid_v2_token(vvvh_path: str, out_path: Path) -> dict[str, Any]:
    """Derive the uint8 s1_dualpol_valid_v2 token next to the raw raster.

    Local-only derivation: no GEE task, no resampling, no change to raw
    bytes. Grid/CRS/transform are copied from the identity vvvh raster.
    """
    stats = s1_dualpol_valid_v2_stats(vvvh_path)
    valid = stats.pop("mask")
    with rasterio.open(vvvh_path) as src:
        profile = src.profile
    profile.update(count=1, dtype="uint8", nodata=None)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(valid.astype("uint8"), 1)
        dst.set_band_description(1, "S1_DUALPOL_VALID_V2")
    stats["token_path"] = str(out_path)
    return stats


def actual_mask_gate_check(
    byte_fraction: float, plan_fraction: float, evidence_source: str,
) -> dict[str, Any]:
    """Gate landed bytes against the 0.95 rule and the V2 plan measurement."""
    evidence = str(evidence_source)
    tol = (ACTUAL_MASK_LANDED_TOL if evidence.startswith("LANDED")
           else ACTUAL_MASK_LIVE_TOL)
    delta = abs(byte_fraction - float(plan_fraction))
    gate_pass = byte_fraction >= ACTUAL_MASK_GATE
    agrees = delta <= tol
    return {
        "gate": f"actual_observed_fraction >= {ACTUAL_MASK_GATE}",
        "gate_pass": gate_pass,
        "byte_fraction": byte_fraction,
        "plan_v2_fraction": float(plan_fraction),
        "plan_evidence_source": evidence,
        "abs_delta": delta,
        "agreement_tolerance": tol,
        "plan_agreement_pass": agrees,
        "pass": gate_pass and agrees}


def landsat_inherited_gate(
    grid_stats: dict[str, Any], cell_stats: dict[str, Any],
) -> dict[str, Any]:
    """Inherited-Landsat V2 gate record.

    Eligibility is the actual joint all-SR-band observed fraction INSIDE
    the W10 cell (owner F1), >= 0.95. The full covering-grid fraction is
    carried as evidence; a grid shortfall with the cell passing is not an
    eligibility failure (the export grid deliberately over-covers the
    cell by ~27%). Inherited rows have no V2 plan fraction to agree with.
    """
    cell_frac = float(
        cell_stats["actual_observed_fraction_in_w10_cell"])
    grid_frac = float(grid_stats["actual_observed_fraction"])
    gate = actual_mask_gate_check(
        cell_frac, ACTUAL_MASK_GATE, "LANDED_BYTES_V1_INHERITED")
    gate["gate"] = (
        "actual_observed_fraction_in_w10_cell >= "
        f"{ACTUAL_MASK_GATE}")
    gate["plan_v2_fraction"] = None
    gate["abs_delta"] = None
    gate["plan_agreement_pass"] = True
    gate["pass"] = gate["gate_pass"]
    gate["grid_byte_fraction"] = grid_frac
    gate["grid_fraction_below_gate"] = grid_frac < ACTUAL_MASK_GATE
    return gate


#: Residual live-proxy vs landed-byte deltas at mosaic/footprint edges are
#: known to exceed the pixel tolerance (fractional edge-mask resampling in
#: reduceRegion; documented for S1 during V2 selection). They are tolerated
#: ONLY while both evidence sides independently pass the 0.95 gate and the
#: event identity is unchanged; a delta that flips the gate is a hard fail.
PROXY_CROSSCHECK_WARN = "LIVE_PROXY_EDGE_RESAMPLING_CROSSCHECK_DELTA"


def v2_replay_actual_mask_gate(
    cell_frac: float, grid_frac: float, plan_frac: Any,
    evidence_source: str,
) -> dict[str, Any]:
    """Gate for S2/S1 slots replayed under PILOT_EVENT_SELECTION_V2.

    Eligibility authority is the ACTUAL landed raster mask measured INSIDE
    the W10 cell (owner F1): ``cell_frac >= 0.95``. The plan-time live
    reduceRegion fraction was measured on the covering grid and stays a
    cross-check on the like-for-like grid byte fraction:

    * bytes and plan on opposite sides of the 0.95 gate => hard failure
      (``gate_status_conflict``), exactly the STOP rule used during V2
      S1 selection;
    * both pass but their fractions differ beyond tolerance because of the
      documented fractional edge-mask proxy artifact => recorded WARN,
      product still eligible (actual bytes, not the proxy, decide);
    * bytes below 0.95 => hard failure regardless of the plan.
    """
    pf = float(plan_frac) if plan_frac not in (None, "") else None
    byte_pass = cell_frac >= ACTUAL_MASK_GATE
    plan_gate = (pf >= ACTUAL_MASK_GATE) if pf is not None else None
    delta = abs(grid_frac - pf) if pf is not None else None
    tol = (ACTUAL_MASK_LANDED_TOL if str(evidence_source).startswith("LANDED")
           else ACTUAL_MASK_LIVE_TOL)
    agrees = bool(delta <= tol) if delta is not None else True
    conflict = plan_gate is not None and (byte_pass != plan_gate)
    warnings: list[dict[str, Any]] = []
    if (delta is not None and not agrees and byte_pass
            and bool(plan_gate)):
        warnings.append({
            "code": PROXY_CROSSCHECK_WARN,
            "abs_delta": float(delta), "tolerance": tol,
            "detail": ("landed bytes and the V2 live reduceRegion proxy "
                       "both pass the 0.95 actual-mask gate; the residual "
                       "delta is the documented fractional edge-mask "
                       "resampling bias at mosaic/footprint edges; the "
                       "actual observed raster over the W10 cell remains "
                       "the eligibility authority (owner F1)")})
    return {
        "gate": (f"actual_observed_fraction_in_w10_cell >= "
                 f"{ACTUAL_MASK_GATE}"),
        "gate_pass": byte_pass,
        "byte_fraction": float(cell_frac),
        "byte_grid_fraction": float(grid_frac),
        "plan_v2_fraction": pf,
        "plan_evidence_source": str(evidence_source),
        "plan_gate_pass": plan_gate,
        "gate_status_conflict": bool(conflict),
        "abs_delta": (float(delta) if delta is not None else None),
        "agreement_tolerance": float(tol),
        "plan_agreement_pass": agrees,
        "crosscheck_warnings": warnings,
        "pass": bool(byte_pass and not conflict)}


#: Bulk-plausibility sigma0 dB envelope inherited from the M2.1b Zhejiang
#: screen. National coastal scenes legitimately contain sparse harbour/ship
#: double-bounce point targets (VV up to ~+37 dB, VH also bright) and calm
#: water speckle nulls (VH below -50 dB); all such pixels in the canary were
#: independently confirmed present in the source GEE scene via the live
#: server identity check, so bulk-envelope exceedance is a fraction gate.
S1_DB_BULK_MIN = -50.0
S1_DB_BULK_MAX = 30.0
#: Upper envelope beyond which pixels cannot be valid S1 GRD dB; catches
#: corruption and double-transform artifacts (which reach hundreds of dB).
#: F3 (owner-approved 2026-10-09): there is NO symmetric lower rejection
#: bound on the RAW raster. The discrete GEE frame-border floor
#: (~-80.031 dB) is an observation-validity matter handled by the derived
#: s1_dualpol_valid_v2 token (<= -70 dB -> NON_OBSERVATION_EXTREME_FLOOR);
#: the raw identity bytes are preserved, never rejected or clipped.
S1_DB_HARD_MAX = 45.0
#: Point-target / dark-water tail must stay below 0.1% of finite pixels.
#: The tail counts physical backscatter only: sparse dark-water nulls
#: strictly between the -70 dB floor rule and the -50 dB bulk edge, plus
#: point targets above +30 dB. Pixels <= -70 dB are non-observation
#: (token-masked), not a physical-tail violation.
S1_TAIL_OUTSIDE_BULK_HARD_FRACTION = 1e-3


def s1_physical_audit(path: str) -> dict[str, Any]:
    """Finite-robust physical audit of a landed identity S1 VV/VH raster.

    Hard failures: pixels above the upper dB envelope, non-monotone
    percentiles, implausible medians, co-pol/cross-pol ordering inverted,
    or >0.1% of finite pixels in the physical sparse tail
    (-70 dB < x < -50 dB or x > +30 dB). Pixels <= -70 dB are NOT a raw
    failure (F3): they are counted per band and removed only in the
    derived ``s1_dualpol_valid_v2`` token. The source-fidelity
    (no 10*log10) guarantee is enforced separately by the live server
    identity comparison in validate_bundle.
    """
    detail: dict[str, Any] = {
        "expected_units": "sigma0 dB (COPERNICUS/S1_GRD pre-converted)",
        "transform_applied": "IDENTITY_SELECT_ONLY_NO_10LOG10",
        "raw_raster_policy": "RAW GEE VALUES PRESERVED EXACTLY (F3)",
        "bulk_envelope_db": [S1_DB_BULK_MIN, S1_DB_BULK_MAX],
        "upper_hard_envelope_db": S1_DB_HARD_MAX,
        "extreme_floor_rule_db": S1_FLOOR_DB,
        "extreme_floor_semantics": (
            "NON_OBSERVATION_EXTREME_FLOOR in the derived "
            "s1_dualpol_valid_v2 token only; observation-validity rule, "
            "not a physical impossibility claim; never a raw-byte reject"),
        "tail_policy": ("physical sparse tail = -70 < x < -50 dB dark-water "
                        "nulls plus x > +30 dB point targets; legitimate "
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
            above_hard = int((vals > S1_DB_HARD_MAX).sum())
            at_floor = int((vals <= S1_FLOOR_DB).sum())
            physical_tail = int(
                ((vals > S1_FLOOR_DB) & (vals < S1_DB_BULK_MIN)
                 | (vals > S1_DB_BULK_MAX)).sum())
            tail_frac = physical_tail / n
            detail["bands"][name] = {
                "finite_pixels": n,
                "grid_pixels": total,
                "finite_fraction": n / total,
                "min": float(pct[0]), "p01": float(pct[1]),
                "p50": float(pct[2]), "p99": float(pct[3]),
                "max": float(pct[4]),
                "above_upper_hard_envelope_pixels": above_hard,
                "at_or_below_extreme_floor_pixels": at_floor,
                "at_or_below_extreme_floor_fraction": at_floor / n,
                "physical_tail_pixels": physical_tail,
                "physical_tail_fraction": tail_frac}
            # Key retained from the pre-F3 audit; semantics are now
            # upper-envelope only (the lower bound moved to the token).
            checks[f"{name}_no_pixels_beyond_hard_envelope"] = (
                above_hard == 0)
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


# ---------------------------------------------------------------------------
# V2 recovery: archive V1 failed-event bytes; enrich retained manifests
# ---------------------------------------------------------------------------

def _tif_date_tag(name: str) -> str | None:
    """Extract the YYYYMMDD tag from a landed component file name."""
    parts = name.removesuffix(".tif").split("_")
    return parts[-2] if len(parts) >= 2 and len(parts[-2]) == 8 else None


def is_old_event_orphan(
    name: str, pid: str, v2_date: str,
) -> bool:
    """A downloaded r1/r2 tif for this slot that is NOT the V2 event.

    V2 raw exports use revision r2 (S2/S1 replaced events) and V1 bytes
    use r1; token files use revision v2. A pre-V2 orphan (downloaded but
    never landed, e.g. a quarantined partial S1 frame) is archived when
    its date differs from the V2 event date.
    """
    prefix = f"spartina_pilot19_{pid}_"
    if not name.startswith(prefix) or not name.endswith(".tif"):
        return False
    revision = name.removesuffix(".tif").split("_")[-1]
    if revision not in (REVISION, SENTINEL_V2_REPLACED_REVISION):
        return False
    tag = _tif_date_tag(name)
    return tag is not None and tag != v2_date


def _move_with_sha(src: Path, dst_dir: Path) -> dict[str, Any]:
    dst_dir.mkdir(parents=True, exist_ok=True)
    digest = sha256_file(src)
    dst = dst_dir / src.name
    if dst.exists():
        if sha256_file(dst) != digest:
            raise ProvenanceError(
                f"V1 supersession archive conflict for {src.name}: "
                "archived copy has a different SHA-256")
        src.unlink()  # identical duplicate already archived
    else:
        shutil.move(str(src), str(dst))
    return {"name": src.name, "sha256": digest,
            "size_bytes": dst.stat().st_size}


def archive_superseded_v1(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Move V1 manifests/bytes of REPLACED slots into supersession archive.

    Idempotent. Nothing V1 is deleted: manifest-referenced files move
    with their recorded SHA-256, plus any downloaded old-event orphan
    rasters (quarantined partial frames). An index records every move.
    """
    MANIFESTS_V1_SUPERSEDED_DIR.mkdir(parents=True, exist_ok=True)
    PRODUCTS_V1_SUPERSEDED_DIR.mkdir(parents=True, exist_ok=True)
    index: dict[str, Any] = {"products": {}}
    if SUPERSESSION_INDEX.exists():
        index = json.loads(
            SUPERSESSION_INDEX.read_text(encoding="utf-8"))
    for row in rows:
        if str(row.get("v2_change")) != CHANGE_REPLACED:
            continue
        pid = str(row["product_id"])
        entry = index["products"].setdefault(pid, {
            "product_id": pid, "sensor": row["sensor"],
            "cell_id": row["cell_id"], "year": int(row["year"]),
            "v2_event_id": row.get("event_id"),
            "v2_event_utc": row.get("event_utc"),
            "archived_manifest": None, "archived_files": []})
        v2_date = date_tag(row)
        mpath = MANIFEST_DIR / f"{pid}.json"
        archived_names = {f["name"] for f in entry["archived_files"]}
        # Only the ORIGINAL V1 manifest (schema v0) is archived. A slot
        # already rebuilt under V2 (schema v1, e.g. after the canary) is
        # left untouched on subsequent runs.
        if mpath.exists():
            doc = json.loads(mpath.read_text(encoding="utf-8"))
            if doc.get("schema") == SCHEMA_V0:
                entry["v1_event_id"] = doc.get("observation_event_id")
                entry["v1_event_utc"] = doc.get("acquisition_utc_planned")
                for frec in doc.get("landed_files", []):
                    src = Path(str(frec["local_uri"]))
                    if src.exists() and src.name not in archived_names:
                        moved = _move_with_sha(
                            src, PRODUCTS_V1_SUPERSEDED_DIR)
                        if moved["sha256"] != frec.get("sha256"):
                            raise ProvenanceError(
                                f"{pid}: archived {src.name} SHA-256 "
                                "disagrees with its V1 manifest; STOP")
                        moved["role"] = frec.get("role")
                        moved["source"] = "v1_manifest_landed_file"
                        entry["archived_files"].append(moved)
                        archived_names.add(src.name)
                amove = _move_with_sha(mpath, MANIFESTS_V1_SUPERSEDED_DIR)
                entry["archived_manifest"] = amove["name"]
        for tif in sorted(PRODUCT_DIR.glob(f"spartina_pilot19_{pid}_*.tif")):
            if (tif.name not in archived_names
                    and is_old_event_orphan(tif.name, pid, v2_date)):
                moved = _move_with_sha(tif, PRODUCTS_V1_SUPERSEDED_DIR)
                moved["source"] = "v1_downloaded_old_event_orphan"
                entry["archived_files"].append(moved)
                archived_names.add(tif.name)
    SUPERSESSION_INDEX.write_text(
        json.dumps(index, indent=2, sort_keys=True, default=str),
        encoding="utf-8")
    return index


def _v2_gate_from_landed(
    sensor: str, doc: dict[str, Any],
    row: dict[str, Any], local_files: dict[str, Path],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Actual-mask block + any new derived file records for a V1 product."""
    new_files: list[dict[str, Any]] = []
    if sensor == "sentinel2":
        sr_path = str(local_files["sr"])
        stats = s2_sr_actual_mask(sr_path)
        cell = sr_in_w10_cell_fraction(
            sr_path, str(doc["cell_id"]), int(doc["utm_zone"]), 10.0)
        gate = v2_replay_actual_mask_gate(
            cell["actual_observed_fraction_in_w10_cell"],
            stats["actual_observed_fraction"],
            row.get("v2_actual_observed_fraction"),
            str(row.get("v2_evidence_source", "")))
        if not gate["pass"]:
            raise ProvenanceError(
                f"{row['product_id']}: retained S2 bytes fail V2 gate "
                f"during enrichment: {gate}")
        return ({"coverage_basis": BASIS_S2_V2, **stats, **cell,
                 "gate": gate}, [])
    if sensor == "sentinel1":
        vvvh = local_files["vvvh"]
        token_path = PRODUCT_DIR / (
            f"{prefix_for(row, S1_VALID_V2_ROLE, revision=S1_VALID_V2_REVISION)}.tif")
        tok = write_s1_valid_v2_token(str(vvvh), token_path)
        info = raster_grid_info(token_path)
        assert_grid_matches(info, doc["grid_spec"])
        if info["count"] != 1 or info["dtypes"] != ["uint8"]:
            raise ProvenanceError(
                f"{row['product_id']}: derived token must be 1x uint8")
        with rasterio.open(token_path) as td:
            tok_mask = td.read(1) == 1
            cell = mask_in_w10_cell_fraction(
                tok_mask, td.transform, str(doc["cell_id"]),
                int(doc["utm_zone"]), 10.0)
        gate = v2_replay_actual_mask_gate(
            cell["actual_observed_fraction_in_w10_cell"],
            float(tok["actual_observed_fraction"]),
            row.get("v2_actual_observed_fraction"),
            str(row.get("v2_evidence_source", "")))
        if not gate["pass"]:
            raise ProvenanceError(
                f"{row['product_id']}: retained S1 token fails V2 gate: "
                f"{gate}")
        source_sha = next(
            f["sha256"] for f in doc["landed_files"] if f["role"] == "vvvh")
        new_files.append({
            "local_uri": str(token_path),
            "size_bytes": int(token_path.stat().st_size),
            "sha256": sha256_file(token_path),
            "role": S1_VALID_V2_ROLE,
            "drive_file_name": None, "drive_folder": None,
            "grid_verified": True,
            "derivation": {
                "token": S1_VALID_V2_TOKEN,
                "derived_locally": True,
                "gee_export_task": None,
                "source_role": "vvvh",
                "source_sha256": source_sha,
                "rule": ("finite(VV) AND finite(VH) AND VV > -70 dB AND "
                         "VH > -70 dB over the identical grid"),
                "floor_rule_db": S1_FLOOR_DB,
                "floor_semantics": "NON_OBSERVATION_EXTREME_FLOOR",
                "raw_values_modified": False,
                "raw_raster_policy": "preserved exactly; no clip"}})
        block = {"coverage_basis": BASIS_S1_V2,
                 "validity_token": S1_VALID_V2_TOKEN,
                 "token_role": S1_VALID_V2_ROLE,
                 "token_file": token_path.name, **tok, **cell, "gate": gate}
        return block, new_files
    # Inherited landsat: metadata-only V2 bump (no new bytes). The joint
    # all-required-SR-band observed fraction is re-measured on the landed
    # bytes; the V1 audit's per-band fractions cannot give the joint
    # intersection (min over bands overstates it when non-finite pixels
    # differ between bands). Eligibility is the owner F1 W10-cell
    # fraction; the full-grid fraction is evidence only.
    sr_path = str(local_files["sr"])
    stats = s2_sr_actual_mask(sr_path)
    cell = sr_in_w10_cell_fraction(
        sr_path, str(doc["cell_id"]), int(doc["utm_zone"]), 30.0)
    frac = cell["actual_observed_fraction_in_w10_cell"]
    gate = landsat_inherited_gate(stats, cell)
    if not gate["pass"]:
        raise ProvenanceError(
            f"{row['product_id']}: inherited Landsat in-W10-cell fraction "
            f"{frac} < {ACTUAL_MASK_GATE}; STOP for owner review")
    return {"coverage_basis": BASIS_LANDSAT_INHERITED, **stats, **cell,
            "gate": gate}, []


def enrich_retained_products_to_v2(
    rows: list[dict[str, Any]], *, plan_checksum: str,
) -> list[str]:
    """Metadata-only V2 upgrade of already-landed retained products.

    Raw r1/r2 bytes and SHA-256 records are untouched. The original V1
    manifest is archived once; S1 products additionally receive the
    locally derived s1_dualpol_valid_v2 token. Idempotent.
    """
    enriched: list[str] = []
    for row in rows:
        pid = str(row["product_id"])
        mpath = MANIFEST_DIR / f"{pid}.json"
        if not mpath.exists():
            continue  # not landed yet -> exported fresh by the scheduler
        doc = json.loads(mpath.read_text(encoding="utf-8"))
        # Records written before the in-W10-cell correction lack the
        # owner-denominator fields; refresh those metadata-only (raw bytes
        # and SHA-256 untouched; the S1 token is rewritten identically).
        block = doc.get("qa", {}).get("actual_mask_v2", {})
        stale_missing_cell = (
            "actual_observed_fraction_in_w10_cell" not in block)
        if (doc.get("schema") == SCHEMA_V1
                and doc.get("event_selection", {}).get("plan_csv_sha256")
                == plan_checksum
                and not stale_missing_cell):
            continue
        for frec in doc["landed_files"]:
            if sha256_file(frec["local_uri"]) != frec["sha256"]:
                raise ProvenanceError(
                    f"{pid}: retained file re-hash mismatch at "
                    f"{frec['local_uri']}; refusing enrichment")
        sensor = str(row["sensor"])
        local_files = {
            str(f["role"]): Path(str(f["local_uri"]))
            for f in doc["landed_files"]}
        block, new_files = _v2_gate_from_landed(
            sensor, doc, row, local_files)
        existing_roles = {str(f["role"]) for f in doc["landed_files"]}
        doc["landed_files"].extend(
            f for f in new_files if f["role"] not in existing_roles)
        doc.setdefault("qa", {})["actual_mask_v2"] = block
        # Archive the V1 manifest exactly once, then rewrite in place.
        archived = MANIFESTS_V1_SUPERSEDED_DIR / f"{pid}.json"
        if not archived.exists():
            shutil.copy2(mpath, archived)
        doc["schema"] = SCHEMA_V1
        doc["event_selection"] = event_selection_block(row, plan_checksum)
        doc["v2_enriched_utc"] = _now()
        doc["n_bytes"] = sum(int(f["size_bytes"])
                             for f in doc["landed_files"])
        mpath.write_text(
            json.dumps(doc, indent=2, sort_keys=True, default=str),
            encoding="utf-8")
        enriched.append(pid)
    return enriched


class ExportScheduler:
    def __init__(
        self, ee: Any, store: TaskStore, panel: pd.DataFrame,
        *, concurrency: int, poll_interval_s: int,
        task_timeout_s: int, hard_stop_on_failure: bool,
        plan_version: str = "v1", plan_checksum: str = "",
    ) -> None:
        self.ee = ee
        self.store = store
        self.panel = panel
        self.plan_version = plan_version
        self.plan_checksum = plan_checksum
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
            bundle = build_bundle(
                self.ee, row, self.panel, plan_version=self.plan_version)
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
        if self.plan_version == "v2":
            qa["actual_mask_v2"] = self._v2_actual_mask_extras(
                row, bundle, landed, files)
        product_bytes = sum(int(f["size_bytes"]) for f in files)
        if self.total_landed_bytes + product_bytes > VOLUME_CAP_BYTES:
            raise ProvenanceError(
                f"pilot volume cap {VOLUME_CAP_BYTES} bytes exceeded; STOP")
        for f in files:
            f["grid_verified"] = True
            if "sha256" not in f:
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
        is_v2 = self.plan_version == "v2"
        manifest = {
            "schema": SCHEMA_V1 if is_v2 else SCHEMA_V0,
            "product_id": pid,
            "issue": "#19 M2.5 national 20-cell pilot",
            **({"event_selection":
                event_selection_block(row, self.plan_checksum)} if is_v2
               else {}),
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

    # -- V2 actual-mask extras + derived s1_dualpol_valid_v2 ---------------
    def _v2_actual_mask_extras(
        self, row: dict[str, Any], bundle: Bundle,
        landed: dict[str, Path], files: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Verify the 0.95 actual-mask gate on landed bytes; derive token.

        S2: all-four-SR-band finite fraction. S1: derive the local
        s1_dualpol_valid_v2 uint8 token from the identity vvvh raster
        (raw bytes untouched), verify its grid, and gate on its coverage.
        Landsat: inherited V1 r2 products; the joint all-SR-band finite
        fraction is re-measured on the landed bytes at landing.
        """
        sensor = str(row["sensor"])
        if sensor == "sentinel2":
            sr_path = str(landed["sr"])
            stats = s2_sr_actual_mask(sr_path)
            cell = sr_in_w10_cell_fraction(
                sr_path, str(row["cell_id"]), int(bundle.zone), 10.0)
            gate = v2_replay_actual_mask_gate(
                cell["actual_observed_fraction_in_w10_cell"],
                stats["actual_observed_fraction"],
                row.get("v2_actual_observed_fraction"),
                str(row.get("v2_evidence_source", "")))
            if not gate["pass"]:
                raise ProvenanceError(
                    f"{row['product_id']}: S2 landed bytes fail V2 actual "
                    f"mask gate: {gate}")
            return {"coverage_basis": BASIS_S2_V2, **stats, **cell,
                    "gate": gate}
        if sensor == "sentinel1":
            vvvh = landed["vvvh"]
            token_prefix = prefix_for(
                row, S1_VALID_V2_ROLE,
                revision=S1_VALID_V2_REVISION)
            token_path = PRODUCT_DIR / f"{token_prefix}.tif"
            tok = write_s1_valid_v2_token(str(vvvh), token_path)
            tok_info = raster_grid_info(token_path)
            assert_grid_matches(tok_info, bundle.grid.to_dict())
            if tok_info["count"] != 1 or tok_info["dtypes"] != ["uint8"]:
                raise ProvenanceError(
                    f"{row['product_id']}: {S1_VALID_V2_TOKEN} must be a "
                    f"single uint8 band, got {tok_info['dtypes']}")
            with rasterio.open(token_path) as td:
                tok_mask = td.read(1) == 1
                cell = mask_in_w10_cell_fraction(
                    tok_mask, td.transform, str(row["cell_id"]),
                    int(bundle.zone), 10.0)
            gate = v2_replay_actual_mask_gate(
                cell["actual_observed_fraction_in_w10_cell"],
                float(tok["actual_observed_fraction"]),
                row.get("v2_actual_observed_fraction"),
                str(row.get("v2_evidence_source", "")))
            if not gate["pass"]:
                raise ProvenanceError(
                    f"{row['product_id']}: S1 token fails V2 actual mask "
                    f"gate: {gate}")
            source_sha = next(
                f["sha256"] for f in files if f["role"] == "vvvh")
            files.append({
                "local_uri": str(token_path),
                "size_bytes": int(token_path.stat().st_size),
                "sha256": sha256_file(token_path),
                "role": S1_VALID_V2_ROLE,
                "drive_file_name": None,
                "drive_folder": None,
                "grid_verified": True,
                "derivation": {
                    "token": S1_VALID_V2_TOKEN,
                    "derived_locally": True,
                    "gee_export_task": None,
                    "source_role": "vvvh",
                    "source_sha256": source_sha,
                    "rule": ("finite(VV) AND finite(VH) AND VV > -70 dB "
                             "AND VH > -70 dB over the identical grid"),
                    "floor_rule_db": S1_FLOOR_DB,
                    "floor_semantics": "NON_OBSERVATION_EXTREME_FLOOR",
                    "raw_values_modified": False,
                    "raw_raster_policy": "preserved exactly; no clip"}})
            return {"coverage_basis": BASIS_S1_V2,
                    "validity_token": S1_VALID_V2_TOKEN,
                    "token_role": S1_VALID_V2_ROLE,
                    "token_file": token_path.name,
                    **tok, **cell, "gate": gate}
        # Inherited landsat: JOINT all-required-SR-band observed
        # fraction measured on the landed bytes; eligibility is the
        # in-W10-cell fraction (owner F1), grid fraction is evidence.
        sr_path = str(landed["sr"])
        stats = s2_sr_actual_mask(sr_path)
        cell = sr_in_w10_cell_fraction(
            sr_path, str(row["cell_id"]), int(bundle.zone), 30.0)
        frac = cell["actual_observed_fraction_in_w10_cell"]
        gate = landsat_inherited_gate(stats, cell)
        if not gate["pass"]:
            raise ProvenanceError(
                f"{row['product_id']}: inherited Landsat in-W10-cell "
                f"fraction {frac} below {ACTUAL_MASK_GATE}; owner review "
                "required")
        return {"coverage_basis": BASIS_LANDSAT_INHERITED, **stats, **cell,
                "gate": gate}

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

    def _n_components(self, sensor: str) -> int:
        n = len(COMPONENTS[sensor])
        if self.plan_version == "v2":
            n += len(DERIVED_COMPONENTS_V2[sensor])
        return n

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
            "n_components": self._n_components(str(row["sensor"])),
            "n_export_tasks": len(COMPONENTS[str(row["sensor"])]),
            "manifest": (
                str(self._manifest_path(str(row["product_id"]))
                    .relative_to(REPO_ROOT))
                if str(row["product_id"]) in self.landed_pids else None)}
            for row in scope]
        progress_path = (PROGRESS_JSON_V2 if self.plan_version == "v2"
                         else PROGRESS_JSON_V1)
        doc = {
            "product": (
                "national_pilot19_pixel_export_progress_v2"
                if self.plan_version == "v2"
                else "national_pilot19_pixel_export_progress_v1"),
            "issue": 19,
            "event_selection_revision": (
                SELECTION_V2 if self.plan_version == "v2"
                else "PILOT_EVENT_SELECTION_V1"),
            "event_plan_csv_sha256": self.plan_checksum,
            "updated_utc": _now(),
            "gdrive_folder": GDRIVE_FOLDER,
            "revision": REVISION,
            "component_revisions": {
                "default": REVISION,
                "landsat:valid": LANDSAT_VALID_REVISION,
                "sentinel_v2_replaced": SENTINEL_V2_REPLACED_REVISION,
                "s1:dualpol_valid_v2": S1_VALID_V2_REVISION},
            "states": summary["states"],
            "total_landed_bytes": self.total_landed_bytes,
            "volume_cap_bytes": VOLUME_CAP_BYTES,
            "hard_stop": self.stop,
            "products": products,
            "failures": self.failures,
            "git": git_context(REPO_ROOT),
            "environment": runtime_environment()}
        progress_path.parent.mkdir(parents=True, exist_ok=True)
        progress_path.write_text(
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
    plan_checksum: str, hard_stop: bool, plan_version: str = "v1",
) -> None:
    rows: list[dict[str, Any]] = []
    total = 0
    for row in scope:
        pid = str(row["product_id"])
        sensor = str(row["sensor"])
        manifest_path = MANIFEST_DIR / f"{pid}.json"
        entry: dict[str, Any] = {
            "product_id": pid, "cell_id": row["cell_id"],
            "sensor": sensor, "year": int(row["year"]),
            "coverage_tier": row.get("coverage_tier"),
            "v2_change": row.get("v2_change"),
            "state": _STATE_SELECTED,
            "n_tasks_planned": len(COMPONENTS[sensor]),
            "n_derived_files_planned": (
                len(DERIVED_COMPONENTS_V2[sensor])
                if plan_version == "v2" else 0),
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
    n_derived = sum(
        len(DERIVED_COMPONENTS_V2[str(r["sensor"])]) for r in scope)
    doc = {
        "manifest_id": (
            "national_pilot19_pixel_export_v2" if plan_version == "v2"
            else "national_pilot19_pixel_export_v1"),
        "issue": 19,
        "event_selection_revision": (
            SELECTION_V2 if plan_version == "v2"
            else "PILOT_EVENT_SELECTION_V1"),
        "created_utc": _now(),
        "scope": (
            f"{'v2_' if plan_version == 'v2' else ''}"
            f"{'canary' if canary else 'frozen_20_cell_pilot'}"),
        "canary": canary,
        "n_products_eligible": len(scope),
        "product_states": state_counts,
        "task_store_counts": store.counts(),
        "n_export_tasks_planned": sum(
            len(COMPONENTS[str(r["sensor"])]) for r in scope),
        "n_derived_files_planned": n_derived,
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
    out_json = OUT_V2_JSON if plan_version == "v2" else OUT_V1_JSON
    out_csv = OUT_V2_CSV if plan_version == "v2" else OUT_V1_CSV
    out_json.write_text(
        json.dumps(doc, indent=2, default=str), encoding="utf-8")
    pd.DataFrame(rows).to_csv(out_csv, index=False)
    print(f"[pilot19] aggregate: {state_counts}; "
          f"{total / 1024**2:.1f} MiB landed", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-version", choices=["v1", "v2"],
                        default="v1",
                        help="event-selection revision (v2 = owner-"
                             "approved PILOT_EVENT_SELECTION_V2 recovery)")
    parser.add_argument("--canary", action="store_true",
                        help="export only the frozen canary allowlist "
                             "(v1: 5 products; v2: 4 recovery cases)")
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
    plan_checksum = plan_csv_sha256(args.plan_version)
    scope = load_scope(
        canary=args.canary, only_sensor=args.only_sensor,
        products_filter=products_filter, plan_version=args.plan_version)
    if not scope:
        raise SystemExit("empty scope after frozen-plan filters; abort")
    n_tasks = sum(len(COMPONENTS[str(r["sensor"])]) for r in scope)
    n_derived = sum(
        len(DERIVED_COMPONENTS_V2[str(r["sensor"])]) for r in scope)
    print(f"[pilot19] scope ({args.plan_version}): {len(scope)} products / "
          f"{n_tasks} export tasks / {n_derived} local derived files "
          f"(canary={args.canary})", flush=True)

    PRODUCT_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    TASK_STORE.parent.mkdir(parents=True, exist_ok=True)
    if args.plan_version == "v2":
        # Repair, not restart: archive V1 bytes of replaced slots, then
        # metadata-only V2 upgrade of every already-landed retained
        # product (raw bytes/SHA-256 untouched; S1 gains derived token).
        archive_superseded_v1(scope)
        enriched = enrich_retained_products_to_v2(
            scope, plan_checksum=plan_checksum)
        print(f"[pilot19] v2 preflight: {len(enriched)} retained products "
              f"enriched; replaced V1 bytes archived", flush=True)
    store = TaskStore(TASK_STORE)
    panel = load_panel()
    scheduler = ExportScheduler(
        ee, store, panel, concurrency=args.concurrency,
        poll_interval_s=args.poll_interval_s,
        task_timeout_s=args.task_timeout_s,
        hard_stop_on_failure=args.canary,
        plan_version=args.plan_version, plan_checksum=plan_checksum)
    scheduler.run(scope)
    write_aggregate(
        scope, store, scheduler.failures, canary=args.canary,
        plan_checksum=plan_checksum, hard_stop=scheduler.stop,
        plan_version=args.plan_version)
    if scheduler.stop:
        print("CANARY_FAIL: systematic canary failure; remaining tasks "
              "NOT submitted", flush=True)
        return 2
    if args.canary:
        print("canary products landed; require V2_RECOVERY_CANARY_PASS "
              "(Phase H/I QA) before any further export", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
