"""Offline regression for the frozen M1.6b backup-window smoke (Issue #6).

The PREDECLARED seasonal fallback retrieval (Landsat 8 only,
2020-06-01..2020-08-01 end-exclusive, target DOY 182) over
HZB_TECH_SMOKE_V1 is frozen under
tests/fixtures/gee/real_smoke_backup_catalog_v1.json. This module replays
the unchanged deterministic selection code on those 2 candidate rows
WITHOUT network access or Earth Engine credentials and asserts:

* the window is exactly the predeclared backup window (DOY 152-212
  seasonal policy), and the policy thresholds are identical to v1
  (coverage >= 0.99, valid >= 0.95, ROI cloud <= 0.30);
* exactly two L8 scenes were returned (2020-06-13, 2020-07-31, WRS
  118/39), both fully cloudy over the ROI and rejected solely by
  ``high_roi_cloud_fraction``;
* zero policy-eligible / selected scenes -- the export gate therefore
  stays CLOSED with
  ``L8_REAL_EXPORT_NOT_OBSERVED_UNDER_PREDECLARED_WINDOWS``; no third
  window search, threshold relaxation or sensor substitution may follow;
* catalog/selection SHA-256 fingerprints reproduce from the frozen rows,
  so a silent change to QA counts or ranking rules is detected.

The frozen snapshot is evidence, not a mock: every scene id, UTC
timestamp and count came from a real authenticated L8-only double
retrieval on 2026-09-30 (both runs identical).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "gee" / (
    "real_smoke_backup_catalog_v1.json")
DRIVER_PATH = REPO_ROOT / "scripts" / "data" / "gee" / (
    "real_catalog_smoke.py")

FROZEN_CATALOG_FP = (
    "f9a9c0b4241fc0932535c21b408872db8054e62bf2bd4d7ce4de31ac63423109")
FROZEN_SELECTION_FP = (
    "8c2d37cab34a6252b1edfe97cda5552a1a133abb21b1c5ba2990b8e0d8fac14b")
SENSOR = "landsat8"


@pytest.fixture(scope="module")
def fixture() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def driver() -> Any:
    """Load the catalog driver without initializing Earth Engine."""
    spec = importlib.util.spec_from_file_location(
        "real_catalog_smoke_backup_offline_fixture", DRIVER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def replayed(fixture: dict[str, Any], driver: Any) -> list[dict[str, Any]]:
    """Re-run the driver optical ranking on de-annotated frozen rows."""
    record = fixture["policy"]
    policy = driver.SingleScenePolicy(
        min_footprint_coverage=record["min_footprint_coverage"],
        min_valid_pixel_fraction=record["min_valid_pixel_fraction"],
        max_cloud_fraction=record["max_cloud_fraction"],
        target_doy=record["target_doy"])
    rows: list[dict[str, Any]] = []
    for row in fixture["candidate_rows"]:
        clean = dict(row)
        clean["policy_eligible"] = False
        clean["selected"] = False
        clean["selected_orbit"] = driver.NOT_APPLICABLE
        clean["selection_rank"] = None
        clean["selection_score"] = None
        clean["selection_reason"] = None
        clean["rejection_reasons"] = []
        rows.append(clean)
    driver._rank_optical(rows, policy)
    return rows


def test_fixture_identity_and_predeclared_window(
    fixture: dict[str, Any],
) -> None:
    assert fixture["fixture_version"] == "gee_real_smoke_backup_catalog_v1"
    assert fixture["roi_id"] == "HZB_TECH_SMOKE_V1"
    assert fixture["roi_crs_epsg"] == 4326
    assert fixture["project_id"] == "project-795fc21c-e217-47f3-adb"
    assert fixture["sensors"] == ["landsat8"]
    assert fixture["collections"] == {
        "landsat8": "LANDSAT/LC08/C02/T1_L2"}
    # Exactly the predeclared M1.6b fallback window; end is exclusive.
    assert fixture["window"] == {
        "start_utc": "2020-06-01T00:00:00Z",
        "end_utc": "2020-08-01T00:00:00Z",
        "target_doy": 182,
    }
    assert fixture["window_profile"] == "backup_v1"
    # Thresholds identical to autumn v1 -- no relaxation after results.
    assert fixture["policy"] == {
        "min_footprint_coverage": 0.99,
        "min_valid_pixel_fraction": 0.95,
        "max_cloud_fraction": 0.3,
        "target_doy": 182,
    }
    assert fixture["gate_outcome"] == (
        "L8_REAL_EXPORT_NOT_OBSERVED_UNDER_PREDECLARED_WINDOWS")
    assert fixture["rerun_identical"] is True
    assert fixture["rerun_scene_id_sets_equal"] is True
    assert len(fixture["candidate_rows"]) == 2


def test_backup_candidates_both_rejected_for_roi_cloud(
    replayed: list[dict[str, Any]],
) -> None:
    by_id = {str(r["scene_id"]): r for r in replayed}
    assert set(by_id) == {
        "LC08_118039_20200613", "LC08_118039_20200731"}
    june = by_id["LC08_118039_20200613"]
    july = by_id["LC08_118039_20200731"]
    assert june["product_id"] == (
        "LC08_L2SP_118039_20200613_20200824_02_T1")
    assert july["product_id"] == (
        "LC08_L2SP_118039_20200731_20200908_02_T1")
    assert june["acquisition_utc"] == "2020-06-13T02:25:01.898000+00:00"
    assert july["acquisition_utc"] == "2020-07-31T02:25:20.994000+00:00"
    assert (june["wrs_path"], june["wrs_row"]) == (118, 39)
    assert (july["wrs_path"], july["wrs_row"]) == (118, 39)
    for row in (june, july):
        # Full ROI coverage and observation are present; cloud is the
        # only gate that fails.
        assert row["roi_coverage_fraction"] == 1.0
        assert row["valid_pixel_fraction"] == 1.0
        assert row["roi_cloud_fraction"] == 1.0
        assert row["clear_pixel_fraction"] == 0.0
        assert row["policy_eligible"] is False
        assert row["selected"] is False
        assert row["rejection_reasons"] == ["high_roi_cloud_fraction"]


def test_backup_gate_counts_and_empty_selection(
    fixture: dict[str, Any], replayed: list[dict[str, Any]],
) -> None:
    assert fixture["counts"][SENSOR] == {
        "candidate_count": 2, "eligible_count": 0, "selected_count": 0}
    assert len(replayed) == 2
    assert not any(r["policy_eligible"] for r in replayed)
    assert not any(r["selected"] for r in replayed)
    assert fixture["selected_scenes"] == {"landsat8": []}


def test_backup_catalog_fingerprint_reproduces(
    fixture: dict[str, Any], driver: Any, replayed: list[dict[str, Any]],
) -> None:
    # Historical backup fixture predates scl_qa_policy_version: reproduce
    # its fingerprint with the frozen v1 fingerprint field set.
    fingerprint = driver.canonical_fingerprint(
        driver._fingerprint_payload(
            replayed, fields=driver.FINGERPRINT_FIELDS_V1))
    assert fingerprint == fixture["catalog_fingerprint_sha256"]
    assert fingerprint == FROZEN_CATALOG_FP


def test_backup_selection_fingerprint_reproduces(
    fixture: dict[str, Any], driver: Any, replayed: list[dict[str, Any]],
) -> None:
    record = fixture["policy"]
    policy = driver.SingleScenePolicy(
        min_footprint_coverage=record["min_footprint_coverage"],
        min_valid_pixel_fraction=record["min_valid_pixel_fraction"],
        max_cloud_fraction=record["max_cloud_fraction"],
        target_doy=record["target_doy"])
    fingerprint = driver.canonical_fingerprint(
        driver._selection_payload({SENSOR: replayed}, policy))
    assert fingerprint == fixture["selection_fingerprint_sha256"]
    assert fingerprint == FROZEN_SELECTION_FP


def test_backup_roi_geometry_hash_unchanged(
    fixture: dict[str, Any], driver: Any,
) -> None:
    """The backup query reuses HZB_TECH_SMOKE_V1 exactly (same hash)."""
    assert driver.canonical_fingerprint(fixture["roi_geometry"]) == (
        fixture["roi_geometry_sha256"])
    assert fixture["roi_geometry_sha256"] == (
        "b72d475976e4ff3e775defb467ec4a62f880a5df1bc42aa0c0a882be7d9da43f")
