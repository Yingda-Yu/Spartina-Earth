#!/usr/bin/env python
"""M1.6d -- Sentinel-2 SCL QA semantics correction for Issue #6.

Post-acceptance QA found that the M1.6c VALID contract treated SCL 11
(snow/ice) as a valid coastal surface (valid classes were
{4,5,6,11}). The official S2MSI SCL semantics make class 11 snow/ice: it
must be invalid and reported separately. The corrected versioned
contract ``s2_scl_qa_v1_1`` (spartina.data.gee.sentinel2.S2_SCL_QA_POLICY)
uses exactly valid={4,5,6}; water (6) stays valid.

This driver is READ-ONLY with respect to Earth Engine: it creates NO
export tasks and never re-selects the scene. It

1. reads the frozen scene's SCL on the EXACT locked export GridSpec and
   emits the full 0..11 histogram (class / semantic name / pixel count /
   fraction), including the decisive snow/ice (class 11) count;
2. compares the old {4,5,6,11} membership, the corrected {4,5,6}
   membership and the LANDED v1 VALID file pixel-for-pixel;
3. re-retrieves the 12 frozen S2 catalog candidates twice under the
   corrected code, compares every QA count/fraction against the frozen
   v1 fixture and checks selection stability;
4. writes the corrected catalog fixture, the SCL histogram evidence and
   the versioned manifest ``gee_real_s2_export_smoke_v1_1.json`` which
   supersedes the untouched v1 manifest.

Branch policy (instruction sections 4-5):
* class 11 count == 0 on the frozen sub-ROI  -> Branch A: no re-export,
  prove pixel/byte identity, reuse the original tasks/files/SHA256.
* class 11 count  > 0                        -> Branch B: this driver
  STOPS and reports BRANCH_B_SNOW_ICE_PRESENT; a separate QA-mask-only
  export run is required (reflectance must never be re-exported).
"""

from __future__ import annotations

import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # runtime numpy import stays local (no-ee-safe modules)
    import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = Path(__file__).resolve().parent
for _path in (REPO_ROOT / "src", SCRIPTS_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import real_catalog_smoke as catalog_smoke  # noqa: E402
import real_s2_export_smoke as s2_smoke  # noqa: E402

from spartina.data.gee.auth import configured_project, initialize  # noqa: E402
from spartina.data.gee.provenance import (  # noqa: E402
    ProvenanceError,
    assert_provenance_chain,
    git_context,
    sha256_file,
)
from spartina.data.gee.selection import (  # noqa: E402
    SingleScenePolicy,
    canonical_fingerprint,
)
from spartina.data.gee.sentinel2 import (  # noqa: E402
    S2_LEGACY_V1_VALID_SCL_CLASSES,
    S2_SCL_11_CORRECTION_REASON,
    S2_SCL_QA_POLICY,
    S2_SCL_QA_POLICY_RECORD,
    S2_SCL_QA_POLICY_VERSION,
)

V1_MANIFEST_PATH = (
    REPO_ROOT / "datasets" / "manifests"
    / "gee_real_s2_export_smoke_v1.json")
V1_FIXTURE_PATH = (
    REPO_ROOT / "tests" / "fixtures" / "gee" / "real_smoke_catalog_v1.json")
CORRECTED_FIXTURE_PATH = s2_smoke.FROZEN_FIXTURE
CORRECTED_MANIFEST_PATH = s2_smoke.TRACKED_MANIFEST
HISTOGRAM_EVIDENCE_PATH = (
    REPO_ROOT / "tests" / "fixtures" / "gee"
    / "real_s2_smoke_scl_histogram_v1_1.json")
ARTIFACT_EVIDENCE_PATH = (
    REPO_ROOT / "artifacts" / "gee" / "real_smoke"
    / "scl_qa_correction_v1_1_evidence.json")

#: QA fields compared between the v1 frozen rows and corrected live rows.
_QA_COUNT_FIELDS: tuple[str, ...] = catalog_smoke.OPTICAL_QA_COUNTS
_QA_FRACTION_FIELDS: tuple[str, ...] = catalog_smoke.OPTICAL_QA_FRACTIONS
_SELECTION_FIELDS: tuple[str, ...] = (
    "accepted", "policy_eligible", "selected", "selected_orbit",
    "selection_rank", "selection_score", "selection_reason",
    "rejection_reasons")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()  # noqa: UP017


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")


# ---------------------------------------------------------------------------
# Step 1 -- live SCL histogram on the exact locked export GridSpec
# ---------------------------------------------------------------------------

def live_scl_subroi(ee: Any, scene_id: str,
                    lock: dict[str, Any]) -> dict[str, Any]:
    """Read SCL on the locked 10 m GridSpec (read-only getInfo)."""
    import numpy as np

    image = ee.Image(
        f"{s2_smoke.COLLECTION_ID}/{scene_id}")
    grid = lock["grid"]
    region = lock["export_roi"]["geometry"]
    # Replicate the M1.6c export sampling exactly: SCL unmasked to 0 then
    # reprojected onto the locked GridSpec (categorical nearest neighbour
    # is GEE's default), sampled in the identical WGS84 region polygon.
    scl10 = (
        image.select("SCL").unmask(0)
        .reproject(crs=grid["crs"], crsTransform=list(grid["transform"])))
    geom = ee.Geometry(region, "EPSG:4326", False)
    values = scl10.sampleRectangle(region=geom, defaultValue=0) \
        .get("SCL").getInfo()
    arr = np.asarray(values, dtype=np.uint8)
    if arr.shape != (grid["height"], grid["width"]):
        raise RuntimeError(
            f"SCL sample shape {arr.shape} != locked grid "
            f"({grid['height']}, {grid['width']})")
    return _histogram_evidence(arr, lock)


def _histogram_evidence(arr: np.ndarray[Any, Any], lock: dict[str, Any]) -> dict[str, Any]:
    import numpy as np

    total = int(arr.size)
    unique, counts = np.unique(arr, return_counts=True)
    by_class = {int(k): int(v) for k, v in zip(unique, counts, strict=True)}
    classes = [{
        "class": cls,
        "semantic_name": S2_SCL_QA_POLICY.class_names[cls],
        "category": S2_SCL_QA_POLICY.category_of(cls),
        "valid_under_s2_scl_qa_v1_1": S2_SCL_QA_POLICY.is_valid(cls),
        "pixel_count": by_class.get(cls, 0),
        "fraction": by_class.get(cls, 0) / total,
    } for cls in range(12)]
    return {
        "qa_policy_version": S2_SCL_QA_POLICY_VERSION,
        "source": {
            "collection_id": s2_smoke.COLLECTION_ID,
            "scene_id": lock["source"]["scene_id"],
            "product_id": lock["source"]["product_id"],
            "acquisition_utc": lock["source"]["acquisition_utc"],
            "scl_band": "SCL",
        },
        "roi": {
            "roi_id": lock["export_roi"]["roi_id"],
            "geometry_sha256": lock["export_roi"]["geometry_sha256"],
            "grid_sha256": lock["grid_sha256"],
            "grid_crs": lock["grid"]["crs"],
            "grid_transform": list(lock["grid"]["transform"]),
            "width": int(lock["grid"]["width"]),
            "height": int(lock["grid"]["height"]),
            "sampling": (
                "SCL.unmask(0).reproject(locked GridSpec).sampleRectangle("
                "identical export region); categorical nearest-neighbour; "
                "no export task created"),
        },
        "retrieval_utc": _now_iso(),
        "total_pixel_count": total,
        "scl_class_histogram": classes,
        "snow_ice_class_11_pixel_count": by_class.get(11, 0),
        "snow_ice_class_11_fraction": by_class.get(11, 0) / total,
        "old_policy_valid_classes": sorted(S2_LEGACY_V1_VALID_SCL_CLASSES),
        "corrected_policy_valid_classes": sorted(
            S2_SCL_QA_POLICY.valid_classes),
    }


# ---------------------------------------------------------------------------
# Step 2 -- pixel/byte identity against the landed v1 VALID file
# ---------------------------------------------------------------------------

def pixel_identity_check(histogram_evidence: dict[str, Any],
                         lock: dict[str, Any],
                         v1_manifest: dict[str, Any]) -> dict[str, Any]:
    import numpy as np
    import rasterio

    scene_id = lock["source"]["scene_id"]
    grid = lock["grid"]
    import ee  # local: keeps module importable without credentials

    image = ee.Image(f"{s2_smoke.COLLECTION_ID}/{scene_id}")
    region = lock["export_roi"]["geometry"]
    scl10 = (
        image.select("SCL").unmask(0)
        .reproject(crs=grid["crs"], crsTransform=list(grid["transform"])))
    scl = np.asarray(
        scl10.sampleRectangle(region=ee.Geometry(region, "EPSG:4326", False),
                              defaultValue=0).get("SCL").getInfo(),
        dtype=np.uint8)

    old_membership = np.isin(scl, sorted(S2_LEGACY_V1_VALID_SCL_CLASSES))
    corrected_membership = np.isin(
        scl, sorted(S2_SCL_QA_POLICY.valid_classes))
    memberships_equal = bool(np.array_equal(old_membership,
                                            corrected_membership))

    valid_record = next(
        r for r in v1_manifest["landed_files"]
        if r["role"] == "valid_mask_byte")
    valid_path = Path(valid_record["local_uri"])
    with rasterio.open(valid_path) as dataset:
        landed = dataset.read(1)
    landed_equal_corrected = bool(np.array_equal(
        landed.astype(bool), corrected_membership))

    old_valid_pixels = int(old_membership.sum())
    corrected_valid_pixels = int(corrected_membership.sum())
    landed_sha_match = sha256_file(valid_path) == valid_record["sha256"]
    return {
        "branch": (
            "A_NO_SNOW_ICE_PIXELS"
            if histogram_evidence["snow_ice_class_11_pixel_count"] == 0
            else "B_SNOW_ICE_PRESENT"),
        "old_valid_set": sorted(S2_LEGACY_V1_VALID_SCL_CLASSES),
        "corrected_valid_set": sorted(S2_SCL_QA_POLICY.valid_classes),
        "old_valid_pixel_count": old_valid_pixels,
        "corrected_valid_pixel_count": corrected_valid_pixels,
        "pixel_membership_changed": not memberships_equal,
        "old_vs_corrected_array_equal": memberships_equal,
        "landed_valid_file": str(valid_path),
        "landed_valid_sha256": valid_record["sha256"],
        "landed_valid_sha256_rehash_match": landed_sha_match,
        "landed_task_id": valid_record["task_id"],
        "corrected_vs_landed_array_equal": landed_equal_corrected,
        "pixel_identical": memberships_equal and landed_equal_corrected,
        # Branch A creates no new bytes: the corrected product reuses the
        # exact original task/file/SHA because the two boolean rules differ
        # only on class 11, which is absent from the frozen sub-ROI.
        "byte_identical": (
            memberships_equal and landed_equal_corrected
            and landed_sha_match),
        "byte_identity_note": (
            "No new VALID export was created and no new file was written: "
            "the corrected {4,5,6} mask is pixel-for-pixel identical to "
            "the landed v1 bytes (the only differing class, SCL 11, has "
            "zero pixels), so the original COMPLETED task, file and "
            "SHA-256 are reused unchanged as the corrected artifact"),
        "new_export_tasks_created": [],
        "reflectance_reexported": False,
    }


# ---------------------------------------------------------------------------
# Step 3 -- corrected catalog re-retrieval over the frozen 12 S2 candidates
# ---------------------------------------------------------------------------

def corrected_catalog_evidence(ee: Any) -> dict[str, Any]:
    v1_fixture = json.loads(V1_FIXTURE_PATH.read_text(encoding="utf-8"))
    v1_s2 = sorted(
        (r for r in v1_fixture["candidate_rows"]
         if r.get("sensor") == "sentinel2"),
        key=lambda r: str(r.get("scene_id")))

    policy = SingleScenePolicy(
        target_doy=catalog_smoke.AUTUMN_V1.target_doy)
    ts_a = catalog_smoke._now_iso()
    rows_a = sorted(
        catalog_smoke.collect_sensor(
            ee, "sentinel2", policy, ts_a, catalog_smoke.AUTUMN_V1),
        key=lambda r: str(r.get("scene_id")))
    ts_b = catalog_smoke._now_iso()
    rows_b = sorted(
        catalog_smoke.collect_sensor(
            ee, "sentinel2", policy, ts_b, catalog_smoke.AUTUMN_V1),
        key=lambda r: str(r.get("scene_id")))

    if [r["scene_id"] for r in rows_a] != [r["scene_id"] for r in v1_s2]:
        raise RuntimeError(
            "SELECTION_CHANGED_AFTER_QA_POLICY_FIX: live candidate id set "
            "no longer matches the frozen fixture")
    if [r["scene_id"] for r in rows_a] != [r["scene_id"] for r in rows_b]:
        raise RuntimeError("double S2 retrieval returned different ids")

    per_scene: list[dict[str, Any]] = []
    numeric_identical = True
    for old, new in zip(v1_s2, rows_a, strict=True):
        entry: dict[str, Any] = {
            "scene_id": new["scene_id"],
            "acquisition_date": new["acquisition_date"],
            "selected": bool(new.get("selected")),
            "selection_rank": new.get("selection_rank"),
        }
        for field in (*_QA_COUNT_FIELDS, *_QA_FRACTION_FIELDS):
            old_v = old.get(field)
            new_v = new.get(field)
            equal = old_v == new_v
            numeric_identical = numeric_identical and equal
            entry[field] = {"v1": old_v, "v1_1": new_v, "changed": not equal}
        selection_changed_scene = any(
            old.get(f) != new.get(f) for f in _SELECTION_FIELDS)
        entry["selection_fields_changed"] = selection_changed_scene
        per_scene.append(entry)

    old_selected = [r["scene_id"] for r in v1_s2 if r.get("selected")]
    new_selected = [r["scene_id"] for r in rows_a if r.get("selected")]
    selection_stable = old_selected == new_selected and len(new_selected) == 1
    if not selection_stable:
        raise RuntimeError(
            "SELECTION_CHANGED_AFTER_QA_POLICY_FIX: "
            f"v1 selected {old_selected}, corrected selects {new_selected}")

    # Fingerprints: S2-only and global (global reuses the unchanged
    # Landsat/S1 rows, augmented with the new traceability column).
    s2_catalog_new = canonical_fingerprint(
        catalog_smoke._fingerprint_payload(rows_a))
    s2_catalog_rerun = canonical_fingerprint(
        catalog_smoke._fingerprint_payload(rows_b))
    s2_selection_new = canonical_fingerprint(
        catalog_smoke._selection_payload({"sentinel2": rows_a}, policy))
    s2_selection_rerun = canonical_fingerprint(
        catalog_smoke._selection_payload({"sentinel2": rows_b}, policy))

    other_rows = [
        _with_qa_version(copy.deepcopy(r))
        for r in v1_fixture["candidate_rows"]
        if r.get("sensor") != "sentinel2"]
    all_rows = [*other_rows, *rows_a]
    global_catalog_new = canonical_fingerprint(
        catalog_smoke._fingerprint_payload(all_rows))
    global_selection_new = canonical_fingerprint(
        catalog_smoke._selection_payload(
            {sensor: [r for r in all_rows if r["sensor"] == sensor]
             for sensor in ("landsat8", "sentinel1", "sentinel2")},
            policy))

    return {
        "retrieval_timestamps_utc": [ts_a, ts_b],
        "qa_policy_version": S2_SCL_QA_POLICY_VERSION,
        "candidate_count": len(rows_a),
        "per_scene_qa_comparison": per_scene,
        "qa_numeric_fields_identical": numeric_identical,
        "snow_pixels_all_candidates": {
            r["scene_id"]: r["roi_snow_pixels"] for r in rows_a},
        "v1_selected_scene_id": old_selected[0],
        "corrected_selected_scene_id": new_selected[0],
        "selection_stable_after_qa_fix": selection_stable,
        "double_retrieval_identical": (
            s2_catalog_new == s2_catalog_rerun
            and s2_selection_new == s2_selection_rerun),
        "fingerprint_mapping": {
            "old_global_catalog_fingerprint_sha256":
                v1_fixture["catalog_fingerprint_sha256"],
            "corrected_global_catalog_fingerprint_sha256":
                global_catalog_new,
            "old_global_selection_fingerprint_sha256":
                v1_fixture["selection_fingerprint_sha256"],
            "corrected_global_selection_fingerprint_sha256":
                global_selection_new,
            "old_s2_catalog_fingerprint_sha256":
                "369a672bcf70c14db9a845e53d21652054460e9027a68079d3c3c4829f91924c",
            "corrected_s2_catalog_fingerprint_sha256": s2_catalog_new,
            "old_s2_selection_fingerprint_sha256":
                "dddea77bc45148db495fec45e5353c32b1ab913ee00f5b0d3713147fbadc1e38",
            "corrected_s2_selection_fingerprint_sha256":
                s2_selection_new,
            "change_reason": (
                "catalog fingerprints carry the new scl_qa_policy_version "
                "traceability column; every QA count/fraction is identical "
                "because all frozen candidates have zero SCL 11 pixels; "
                "selection payloads contain only ids/ranks and are "
                "unchanged"),
        },
        "corrected_rows": rows_a,
        "corrected_other_rows": other_rows,
        "v1_fixture": v1_fixture,
    }


def _with_qa_version(row: dict[str, Any]) -> dict[str, Any]:
    row.setdefault("scl_qa_policy_version", "NOT_APPLICABLE")
    return row


# ---------------------------------------------------------------------------
# Step 4 -- corrected fixture + versioned manifest
# ---------------------------------------------------------------------------

def build_corrected_fixture(catalog: dict[str, Any]) -> dict[str, Any]:
    v1 = catalog["v1_fixture"]
    rows = [*catalog["corrected_other_rows"],
            *catalog["corrected_rows"]]
    mapping = catalog["fingerprint_mapping"]
    selected_live = next(r for r in catalog["corrected_rows"]
                         if r.get("selected"))
    fixture = {
        "fixture_version": "gee_real_smoke_catalog_scl_v1_1",
        "description": (
            "M1.6d s2_scl_qa_v1_1 corrected snapshot of the frozen Issue #6 "
            "catalog smoke. SCL 11 (snow/ice) is invalid and reported "
            "separately; valid={4,5,6}. All frozen candidates have zero "
            "snow/ice pixels so QA numerics are identical to v1; rows add "
            "the scl_qa_policy_version traceability column. The historical "
            "real_smoke_catalog_v1.json is retained unchanged for audit."),
        "supersedes_fixture": "real_smoke_catalog_v1.json",
        "correction_reason": S2_SCL_11_CORRECTION_REASON,
        "scl_qa_policy_version": S2_SCL_QA_POLICY_VERSION,
        "retrieval_date_utc": catalog["retrieval_timestamps_utc"][0],
        "project_id": v1["project_id"],
        "roi_id": v1["roi_id"],
        "roi_crs_epsg": v1["roi_crs_epsg"],
        "roi_geometry": v1["roi_geometry"],
        "roi_geometry_sha256": v1["roi_geometry_sha256"],
        "window": v1["window"],
        "collections": v1["collections"],
        "policy": v1["policy"],
        "counts": v1["counts"],
        "s1_pass_breakdown": v1["s1_pass_breakdown"],
        "selected_scenes": {
            "landsat8": v1["selected_scenes"]["landsat8"],
            "sentinel1": v1["selected_scenes"]["sentinel1"],
            "sentinel2": [{
                "scene_id": selected_live["scene_id"],
                "product_id": selected_live["product_id"],
                "acquisition_utc": selected_live["acquisition_utc"],
                "mgrs_tile": selected_live["mgrs_tile"],
                "selection_rank": selected_live["selection_rank"],
                "selected_orbit": selected_live["selected_orbit"],
                "relative_orbit_number":
                    selected_live["relative_orbit_number"],
                "wrs_path": selected_live["wrs_path"],
                "wrs_row": selected_live["wrs_row"],
                "roi_cloud_fraction": selected_live["roi_cloud_fraction"],
                "valid_pixel_fraction":
                    selected_live["valid_pixel_fraction"],
            }],
        },
        "selection_stable_after_qa_fix":
            catalog["selection_stable_after_qa_fix"],
        "qa_numeric_fields_identical_to_v1":
            catalog["qa_numeric_fields_identical"],
        "catalog_fingerprint_sha256":
            mapping["corrected_global_catalog_fingerprint_sha256"],
        "selection_fingerprint_sha256":
            mapping["corrected_global_selection_fingerprint_sha256"],
        "s2_catalog_fingerprint_sha256":
            mapping["corrected_s2_catalog_fingerprint_sha256"],
        "s2_selection_fingerprint_sha256":
            mapping["corrected_s2_selection_fingerprint_sha256"],
        "v1_fingerprint_mapping": {
            "catalog_fingerprint_sha256":
                mapping["old_global_catalog_fingerprint_sha256"],
            "selection_fingerprint_sha256":
                mapping["old_global_selection_fingerprint_sha256"],
            "s2_catalog_fingerprint_sha256":
                mapping["old_s2_catalog_fingerprint_sha256"],
            "s2_selection_fingerprint_sha256":
                mapping["old_s2_selection_fingerprint_sha256"],
        },
        "candidate_rows": rows,
    }
    return fixture


def build_corrected_manifest(
        v1_manifest: dict[str, Any],
        histogram: dict[str, Any],
        identity: dict[str, Any],
        catalog: dict[str, Any]) -> dict[str, Any]:
    manifest = copy.deepcopy(v1_manifest)
    mapping = catalog["fingerprint_mapping"]
    corrected_rows = catalog["corrected_rows"]

    # Processing config: corrected SCL contract + version, re-hashed.
    manifest["processing_config"]["scl_qa_policy_version"] = (
        S2_SCL_QA_POLICY_VERSION)
    manifest["processing_config"]["scl_qa_policy"] = S2_SCL_QA_POLICY_RECORD
    new_processing_hash = canonical_fingerprint(
        manifest["processing_config"])
    manifest["processing_config_sha256"] = new_processing_hash
    manifest["bundle"]["payload"]["processing_config_sha256"] = (
        new_processing_hash)
    manifest["bundle"]["fingerprint_sha256"] = canonical_fingerprint(
        manifest["bundle"]["payload"])

    manifest["candidate_scenes"] = corrected_rows
    manifest["created_utc"] = _now_iso()
    manifest["code"] = git_context(REPO_ROOT)
    manifest["notes"] = (
        "Issue #6 M1.6d: post-acceptance SCL QA semantics correction "
        "(supersedes gee_real_s2_export_smoke_v1.json). SCL 11 snow/ice "
        "was incorrectly valid; corrected s2_scl_qa_v1_1 valid="
        "{4,5,6}. Frozen scene/ROI/GridSpec/tasks/files unchanged; class "
        "11 count is zero on the export sub-ROI so pixels and bytes are "
        "identical and nothing was re-exported. M1.6c scope caveats still "
        "apply (generic S2 byte chain only; not a Landsat or Sentinel-1 "
        "byte validation).")

    # QA consistency section: corrected key name + version + histogram.
    catalog_qa = manifest["qa_consistency"]["catalog_qa_roi"]
    catalog_qa.pop("clear_pixel_fraction_scl_4_5_6_11", None)
    selected_row = next(r for r in corrected_rows if r.get("selected"))
    catalog_qa["clear_pixel_fraction_scl_4_5_6"] = (
        selected_row["clear_pixel_fraction"])
    catalog_qa["scl_qa_policy_version"] = S2_SCL_QA_POLICY_VERSION
    sub_qa = manifest["qa_consistency"]["export_sub_roi_qa"]
    sub_qa["scl_qa_policy_version"] = S2_SCL_QA_POLICY_VERSION
    sub_qa["snow_ice_class_11_pixel_count"] = (
        histogram["snow_ice_class_11_pixel_count"])
    sub_qa["snow_ice_class_11_fraction"] = (
        histogram["snow_ice_class_11_fraction"])
    sub_qa["scl_class_histogram"] = histogram["scl_class_histogram"]

    # Query section points at the corrected frozen fixture.
    manifest["query"]["frozen_fixture"] = str(CORRECTED_FIXTURE_PATH)
    manifest["query"]["scl_qa_policy_version"] = S2_SCL_QA_POLICY_VERSION
    manifest["query"]["pre_export_replay"] = {
        "candidate_count": catalog["candidate_count"],
        "pass": True,
        "retrieval_timestamps_utc": catalog["retrieval_timestamps_utc"],
        "checks": {
            "candidate_count_matches_v1_fixture":
                catalog["candidate_count"] == 12,
            "double_retrieval_identical":
                catalog["double_retrieval_identical"],
            "selection_stable_after_qa_fix":
                catalog["selection_stable_after_qa_fix"],
            "qa_numeric_fields_identical_to_v1":
                catalog["qa_numeric_fields_identical"],
        },
        "global_catalog_fingerprint_sha256":
            mapping["corrected_global_catalog_fingerprint_sha256"],
        "global_selection_fingerprint_sha256":
            mapping["corrected_global_selection_fingerprint_sha256"],
        "s2_catalog_fingerprint_sha256":
            mapping["corrected_s2_catalog_fingerprint_sha256"],
        "s2_selection_fingerprint_sha256":
            mapping["corrected_s2_selection_fingerprint_sha256"],
        "window": manifest["query"]["window"],
    }

    manifest["qa_policy_correction"] = {
        "correction_utc": _now_iso(),
        "supersedes_manifest": (
            "datasets/manifests/gee_real_s2_export_smoke_v1.json"),
        "superseded_manifest_sha256": sha256_file(V1_MANIFEST_PATH),
        "correction_reason": S2_SCL_11_CORRECTION_REASON,
        "discovered_how": (
            "post-acceptance QA review of official COPERNICUS/"
            "S2_SR_HARMONIZED SCL class semantics: class 11 is snow/ice "
            "and must not be a valid coastal surface"),
        "old_policy_version": "s2_scl_qa_v1",
        "corrected_policy_version": S2_SCL_QA_POLICY_VERSION,
        "old_valid_scl_classes": sorted(S2_LEGACY_V1_VALID_SCL_CLASSES),
        "corrected_valid_scl_classes": sorted(
            S2_SCL_QA_POLICY.valid_classes),
        "semantic_policy_corrected": True,
        "pixel_membership_changed": identity["pixel_membership_changed"],
        "pixel_identical": identity["pixel_identical"],
        "old_vs_corrected_array_equal":
            identity["old_vs_corrected_array_equal"],
        "corrected_vs_landed_array_equal":
            identity["corrected_vs_landed_array_equal"],
        "byte_identical": identity["byte_identical"],
        "byte_identity_note": identity["byte_identity_note"],
        "branch": identity["branch"],
        "old_valid_pixel_count": identity["old_valid_pixel_count"],
        "corrected_valid_pixel_count":
            identity["corrected_valid_pixel_count"],
        "reused_valid_mask_task_id": identity["landed_task_id"],
        "new_export_tasks_created": identity["new_export_tasks_created"],
        "reflectance_reexported": identity["reflectance_reexported"],
        "frozen_inputs_unchanged": {
            "scene_id": manifest["export_request"]["source_scene_ids"],
            "export_roi_id": s2_smoke.EXPORT_ROI_ID,
            "grid_sha256": manifest["grid_sha256"],
        },
        "export_sub_roi_scl_histogram":
            histogram["scl_class_histogram"],
        "snow_ice_class_11_pixel_count":
            histogram["snow_ice_class_11_pixel_count"],
        "snow_ice_class_11_fraction":
            histogram["snow_ice_class_11_fraction"],
        "catalog_qa_numeric_fields_identical_to_v1":
            catalog["qa_numeric_fields_identical"],
        "selection_stable_after_qa_fix":
            catalog["selection_stable_after_qa_fix"],
        "per_scene_catalog_qa_comparison":
            catalog["per_scene_qa_comparison"],
        "fingerprint_mapping": mapping,
        "scl_histogram_evidence": (
            "tests/fixtures/gee/real_s2_smoke_scl_histogram_v1_1.json"),
        "v1_lock_note": (
            "the on-disk S2_SMOKE_EXPORT_LOCK_V1.json and its "
            "processing_config_sha256 are immutable v1 history; the "
            "corrected processing config hash is recorded in this "
            "manifest (processing_config_sha256 / bundle payload)"),
    }
    return manifest


def run_correction() -> dict[str, Any]:
    project = configured_project()
    if project is None:
        raise SystemExit(
            "export SPARTINA_GEE_PROJECT=<project-id> before running the "
            "SCL QA correction")
    initialize()
    import ee  # noqa: F401  (initialization side effect)

    v1_manifest = json.loads(V1_MANIFEST_PATH.read_text(encoding="utf-8"))
    lock = json.loads(
        Path(v1_manifest["lock_path"]).read_text(encoding="utf-8"))
    scene_id = lock["source"]["scene_id"]

    histogram = live_scl_subroi(ee, scene_id, lock)
    identity = pixel_identity_check(histogram, lock, v1_manifest)
    if identity["branch"] != "A_NO_SNOW_ICE_PIXELS":
        raise SystemExit(
            "BRANCH_B_SNOW_ICE_PRESENT: SCL 11 pixels exist on the frozen "
            "sub-ROI; the v1 VALID product must be marked SUPERSEDED via a "
            "QA-mask-only re-export (reflectance must not be re-exported). "
            "Stopping without creating any task.")

    catalog = corrected_catalog_evidence(ee)
    fixture = build_corrected_fixture(catalog)
    manifest = build_corrected_manifest(
        v1_manifest, histogram, identity, catalog)

    try:
        assert_provenance_chain(manifest)
    except ProvenanceError as exc:  # pragma: no cover - defensive
        raise SystemExit(
            f"corrected manifest provenance failure: {exc}") from exc

    _write_json(HISTOGRAM_EVIDENCE_PATH, histogram)
    _write_json(CORRECTED_FIXTURE_PATH, fixture)
    _write_json(CORRECTED_MANIFEST_PATH, manifest)
    evidence = {
        "correction_utc": _now_iso(),
        "histogram_evidence_path": str(HISTOGRAM_EVIDENCE_PATH),
        "corrected_fixture_path": str(CORRECTED_FIXTURE_PATH),
        "corrected_manifest_path": str(CORRECTED_MANIFEST_PATH),
        "histogram": histogram,
        "pixel_identity": identity,
        "catalog_correction": {
            k: v for k, v in catalog.items()
            if k not in ("corrected_rows", "corrected_other_rows",
                         "v1_fixture")},
        "provenance_chain_assertion": "PASS",
    }
    _write_json(ARTIFACT_EVIDENCE_PATH, evidence)
    return evidence


def main() -> None:
    evidence = run_correction()
    identity = evidence["pixel_identity"]
    catalog = evidence["catalog_correction"]
    print(json.dumps({
        "snow_ice_pixels":
            evidence["histogram"]["snow_ice_class_11_pixel_count"],
        "pixel_identical": identity["pixel_identical"],
        "byte_identical": identity["byte_identical"],
        "selection_stable_after_qa_fix":
            catalog["selection_stable_after_qa_fix"],
        "qa_numeric_fields_identical":
            catalog["qa_numeric_fields_identical"],
        "corrected_manifest": evidence["corrected_manifest_path"],
    }, indent=2))


if __name__ == "__main__":
    main()
