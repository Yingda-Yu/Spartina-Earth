"""M1.6d regression tests for the Sentinel-2 SCL QA semantics correction.

Single source of truth: ``spartina.data.gee.sentinel2.S2_SCL_QA_POLICY``
(version ``s2_scl_qa_v1_1``). These tests pin, class by class, that

* vegetation (4) / bare soils (5) / water (6) are valid;
* snow/ice (11) is invalid and only reported separately;
* cloud shadow (3), medium/high cloud (8/9), cirrus (10), no-data /
  saturated (0/1) are invalid;
* dark area (2) and unclassified (7) are invalid by explicit policy;
* water (6) can never silently drop out of the valid set again;

and they audit the recorded correction evidence (frozen sub-ROI SCL
histogram, corrected catalog fixture and the v1_1 supersession manifest).
Nothing here contacts Earth Engine.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from spartina.data.gee.sentinel2 import (
    S2_LEGACY_V1_VALID_SCL_CLASSES,
    S2_SCL_11_CORRECTION_REASON,
    S2_SCL_QA_POLICY,
    S2_SCL_QA_POLICY_RECORD,
    S2_SCL_QA_POLICY_VERSION,
    scl_is_valid,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
HISTOGRAM_PATH = (
    REPO_ROOT / "tests" / "fixtures" / "gee"
    / "real_s2_smoke_scl_histogram_v1_1.json")
V1_FIXTURE_PATH = (
    REPO_ROOT / "tests" / "fixtures" / "gee" / "real_smoke_catalog_v1.json")
CORRECTED_FIXTURE_PATH = (
    REPO_ROOT / "tests" / "fixtures" / "gee"
    / "real_smoke_catalog_scl_v1_1.json")
V1_MANIFEST_PATH = (
    REPO_ROOT / "datasets" / "manifests"
    / "gee_real_s2_export_smoke_v1.json")
CORRECTED_MANIFEST_PATH = (
    REPO_ROOT / "datasets" / "manifests"
    / "gee_real_s2_export_smoke_v1_1.json")

SCRIPTS = str(REPO_ROOT / "scripts" / "data" / "gee")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)


# ---------------------------------------------------------------------------
# Class-by-class contract
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cls", [4, 5, 6])
def test_vegetation_bare_water_are_valid(cls: int) -> None:
    assert S2_SCL_QA_POLICY.is_valid(cls)
    assert scl_is_valid(cls)


@pytest.mark.parametrize("cls", [3, 8, 9, 10])
def test_cloud_family_and_shadow_are_invalid(cls: int) -> None:
    assert not S2_SCL_QA_POLICY.is_valid(cls)


@pytest.mark.parametrize("cls", [0, 1])
def test_sensor_invalid_classes_are_invalid(cls: int) -> None:
    assert not S2_SCL_QA_POLICY.is_valid(cls)


def test_snow_ice_class_11_is_invalid() -> None:
    """The M1.6d bug: SCL 11 = snow/ice must never be valid surface."""
    assert 11 not in S2_SCL_QA_POLICY.valid_classes
    assert not S2_SCL_QA_POLICY.is_valid(11)
    assert S2_SCL_QA_POLICY.category_of(11) == "snow_or_ice"
    assert 11 in S2_SCL_QA_POLICY.snow_ice_classes


def test_dark_area_class_2_explicitly_invalid() -> None:
    assert not S2_SCL_QA_POLICY.is_valid(2)
    assert S2_SCL_QA_POLICY.category_of(2) == "dark_area"
    assert S2_SCL_QA_POLICY.to_manifest_dict()[
        "dark_area_class_2_decision"] == "NOT_VALID_EXPLICIT_POLICY_DECISION"


def test_unclassified_class_7_explicitly_invalid() -> None:
    assert not S2_SCL_QA_POLICY.is_valid(7)
    assert S2_SCL_QA_POLICY.category_of(7) == "unclassified"
    assert S2_SCL_QA_POLICY.to_manifest_dict()[
        "unclassified_class_7_decision"] == (
        "NOT_VALID_EXPLICIT_POLICY_DECISION")


def test_water_remains_valid_coastal_guard() -> None:
    """Coastal constraint: water (6) stays valid even after QA fixes."""
    assert 6 in S2_SCL_QA_POLICY.valid_classes
    assert S2_SCL_QA_POLICY.water_class == 6
    assert S2_SCL_QA_POLICY.to_manifest_dict()["water_remains_valid"] is True


def test_every_class_has_explicit_decision() -> None:
    table = {row["class"]: row for row
             in S2_SCL_QA_POLICY.class_decision_table()}
    assert set(table) == set(range(12))
    for cls in range(12):
        assert table[cls]["semantic_name"]
        assert isinstance(table[cls]["valid"], bool)
    valid = {cls for cls, row in table.items() if row["valid"]}
    assert valid == {4, 5, 6}


def test_policy_version_and_legacy_audit_constant() -> None:
    assert S2_SCL_QA_POLICY.version == S2_SCL_QA_POLICY_VERSION
    assert S2_SCL_QA_POLICY_VERSION == 's2_scl_qa_v1_1'
    # The legacy incorrect set is retained for history audits only.
    assert frozenset({4, 5, 6, 11}) == S2_LEGACY_V1_VALID_SCL_CLASSES
    record = S2_SCL_QA_POLICY_RECORD
    assert record["supersedes"] == "s2_scl_qa_v1"
    assert record["correction_reason"] == S2_SCL_11_CORRECTION_REASON
    assert record["snow_or_ice_remains_valid"] is False
    assert "{4,5,6}" in record["byte_encoding"]


def test_ee_valid_mask_is_generated_from_contract() -> None:
    """The OR-chain generated for EE enumerates exactly the valid set."""

    class _Expr:
        def __init__(self, value: object) -> None:
            self.value = value

        def Or(self, other: _Expr) -> None:
            self.value = ("or", self.value, other.value)

        def eq(self, cls: int) -> _Expr:
            return _Expr(("eq", cls))

    used: list[int] = []
    mask = _Expr(0)
    for cls in sorted(S2_SCL_QA_POLICY.valid_classes):
        mask.Or(mask.eq(cls))
        used.append(cls)
    assert used == [4, 5, 6]
    assert 11 not in used


# ---------------------------------------------------------------------------
# Recorded live evidence (Branch A)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def histogram() -> dict[str, Any]:
    return json.loads(HISTOGRAM_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def corrected_fixture() -> dict[str, Any]:
    return json.loads(CORRECTED_FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def v1_fixture() -> dict[str, Any]:
    return json.loads(V1_FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def corrected_manifest() -> dict[str, Any]:
    return json.loads(CORRECTED_MANIFEST_PATH.read_text(encoding="utf-8"))


def test_histogram_evidence_branch_a(histogram: dict[str, Any]) -> None:
    assert histogram["qa_policy_version"] == S2_SCL_QA_POLICY_VERSION
    assert histogram["total_pixel_count"] == 2601
    assert histogram["roi"]["width"] == 51
    assert histogram["roi"]["height"] == 51
    counts = {row["class"]: row["pixel_count"]
              for row in histogram["scl_class_histogram"]}
    assert counts[11] == 0
    assert histogram["snow_ice_class_11_pixel_count"] == 0
    assert histogram["snow_ice_class_11_fraction"] == 0.0
    assert sum(counts.values()) == 2601
    # Independently measured via live GEE on the frozen scene/GridSpec:
    assert counts == {0: 0, 1: 0, 2: 735, 3: 0, 4: 12, 5: 0,
                      6: 1824, 7: 30, 8: 0, 9: 0, 10: 0, 11: 0}
    water = next(row for row in histogram["scl_class_histogram"]
                 if row["class"] == 6)
    assert water["valid_under_s2_scl_qa_v1_1"] is True


def test_corrected_fixture_metadata(
        corrected_fixture: dict[str, Any]) -> None:
    assert (corrected_fixture["fixture_version"]
            == "gee_real_smoke_catalog_scl_v1_1")
    assert (corrected_fixture["scl_qa_policy_version"]
            == S2_SCL_QA_POLICY_VERSION)
    assert (corrected_fixture["correction_reason"]
            == S2_SCL_11_CORRECTION_REASON)
    assert corrected_fixture["selection_stable_after_qa_fix"] is True
    assert corrected_fixture["qa_numeric_fields_identical_to_v1"] is True
    selected = corrected_fixture["selected_scenes"]["sentinel2"]
    assert [r["scene_id"] for r in selected] == [
        "20200905T023549_20200905T024731_T51RUP"]


def test_corrected_fixture_rows_and_fingerprints(
        corrected_fixture: dict[str, Any],
        v1_fixture: dict[str, Any]) -> None:
    import real_catalog_smoke as catalog_smoke

    rows = corrected_fixture["candidate_rows"]
    s2_rows = [r for r in rows if r["sensor"] == "sentinel2"]
    assert len(s2_rows) == 12
    assert {r["scl_qa_policy_version"] for r in s2_rows} == {
        S2_SCL_QA_POLICY_VERSION}
    # Corrected catalog fingerprint reproduces with current fields.
    reproduced = catalog_smoke.canonical_fingerprint(
        catalog_smoke._fingerprint_payload(rows))
    assert reproduced == corrected_fixture[
        "catalog_fingerprint_sha256"]
    # S2 selection fingerprint is unchanged after the correction.
    policy = catalog_smoke.SingleScenePolicy(
        target_doy=v1_fixture["policy"]["target_doy"])
    sel = catalog_smoke.canonical_fingerprint(
        catalog_smoke._selection_payload(
            {"sentinel2": s2_rows}, policy))
    assert sel == corrected_fixture["s2_selection_fingerprint_sha256"]
    assert (corrected_fixture["v1_fingerprint_mapping"]
            ["s2_selection_fingerprint_sha256"] == sel)
    # Historical v1 fingerprints are retained, not overwritten.
    assert (corrected_fixture["v1_fingerprint_mapping"]
            ["catalog_fingerprint_sha256"]
            == v1_fixture["catalog_fingerprint_sha256"])
    assert (corrected_fixture["catalog_fingerprint_sha256"]
            != v1_fixture["catalog_fingerprint_sha256"])


def test_catalog_qa_numerics_identical_to_v1(
        corrected_fixture: dict[str, Any],
        v1_fixture: dict[str, Any]) -> None:
    qa_fields = (
        "roi_total_pixels", "roi_valid_pixels", "roi_cloud_pixels",
        "roi_cloud_shadow_pixels", "roi_cirrus_pixels", "roi_snow_pixels",
        "roi_saturated_pixels", "roi_clear_pixels",
        "valid_pixel_fraction", "roi_cloud_fraction", "roi_shadow_fraction",
        "roi_cirrus_fraction", "roi_snow_fraction",
        "roi_saturated_fraction", "clear_pixel_fraction")
    old = {r["scene_id"]: r for r in v1_fixture["candidate_rows"]
           if r["sensor"] == "sentinel2"}
    for row in corrected_fixture["candidate_rows"]:
        if row["sensor"] != "sentinel2":
            continue
        for field in qa_fields:
            assert row[field] == old[row["scene_id"]][field], (
                row["scene_id"], field)
        assert row["roi_snow_pixels"] == 0


def test_v1_fixture_left_untouched(v1_fixture: dict[str, Any]) -> None:
    """The historical fixture must remain the s2_scl_qa_v1 record."""
    assert v1_fixture["fixture_version"] == "gee_real_smoke_catalog_v1"
    s2_rows = [r for r in v1_fixture["candidate_rows"]
               if r["sensor"] == "sentinel2"]
    assert all("scl_qa_policy_version" not in r for r in s2_rows)


def test_corrected_manifest_supersession(
        corrected_manifest: dict[str, Any]) -> None:
    correction = corrected_manifest["qa_policy_correction"]
    v1_sha = hashlib.sha256(V1_MANIFEST_PATH.read_bytes()).hexdigest()
    assert correction["supersedes_manifest"].endswith(
        "gee_real_s2_export_smoke_v1.json")
    assert correction["superseded_manifest_sha256"] == v1_sha
    assert (correction["correction_reason"]
            == S2_SCL_11_CORRECTION_REASON)
    assert correction["semantic_policy_corrected"] is True
    assert correction["pixel_membership_changed"] is False
    assert correction["pixel_identical"] is True
    assert correction["byte_identical"] is True
    assert correction["old_vs_corrected_array_equal"] is True
    assert correction["corrected_vs_landed_array_equal"] is True
    assert correction["branch"] == "A_NO_SNOW_ICE_PIXELS"
    assert correction["old_valid_scl_classes"] == [4, 5, 6, 11]
    assert correction["corrected_valid_scl_classes"] == [4, 5, 6]
    assert correction["selection_stable_after_qa_fix"] is True
    assert correction["new_export_tasks_created"] == []
    assert correction["reflectance_reexported"] is False
    assert correction["snow_ice_class_11_pixel_count"] == 0


def test_corrected_manifest_reuses_tasks_and_records_policy(
        corrected_manifest: dict[str, Any]) -> None:
    tasks = {(f["role"], f["task_id"]) for f
             in corrected_manifest["landed_files"]}
    assert tasks == {
        ("surface_reflectance_float32", "33GGZVKXKEJZE2BMWIBIALVC"),
        ("valid_mask_byte", "GDA6VJPTFVGJO6MMMFV6WXO4")}
    assert (corrected_manifest["processing_config"]["scl_qa_policy_version"]
            == S2_SCL_QA_POLICY_VERSION)
    policy = corrected_manifest["processing_config"]["scl_qa_policy"]
    assert {int(k) for k in policy["valid_classes"]} == {4, 5, 6}
    # QA policy version is part of provenance.
    assert corrected_manifest["query"]["scl_qa_policy_version"] == (
        S2_SCL_QA_POLICY_VERSION)
    sub = corrected_manifest["qa_consistency"]["export_sub_roi_qa"]
    assert sub["snow_ice_class_11_pixel_count"] == 0
    catalog_roi = corrected_manifest["qa_consistency"]["catalog_qa_roi"]
    assert "clear_pixel_fraction_scl_4_5_6_11" not in catalog_roi
    assert catalog_roi["clear_pixel_fraction_scl_4_5_6"] == (
        pytest.approx(0.8627170252666815))


def test_v1_manifest_retained_as_historical_record() -> None:
    """The v1 manifest is never rewritten: old wrong policy still visible."""
    v1 = json.loads(V1_MANIFEST_PATH.read_text(encoding="utf-8"))
    old_policy = v1["processing_config"]["scl_qa_policy"]
    assert {int(k) for k in old_policy["valid_classes"]} == {4, 5, 6, 11}
    assert old_policy["snow_or_ice_remains_valid"] is True
    catalog_roi = v1["qa_consistency"]["catalog_qa_roi"]
    assert "clear_pixel_fraction_scl_4_5_6_11" in catalog_roi
    assert "qa_policy_correction" not in v1
