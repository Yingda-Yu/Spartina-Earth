"""Vocabulary/schema contract tests for the Zhejiang M2.1a manifests."""

from __future__ import annotations

from spartina.data.zhejiang.contracts import (
    ALLOWED_USES,
    CENSUS_SCENE_COLUMNS,
    CENSUS_SUMMARY_COLUMNS,
    EVIDENCE_STATUSES,
    GAP_STATUSES,
    LABEL_INVENTORY_COLUMNS,
    LABEL_TIERS,
    PROVENANCE_TIERS,
    ROI_REGISTRY_COLUMNS,
    SENSORS,
)


def test_column_sets_unique_and_nonempty():
    for cols in (ROI_REGISTRY_COLUMNS, LABEL_INVENTORY_COLUMNS,
                 CENSUS_SCENE_COLUMNS, CENSUS_SUMMARY_COLUMNS):
        assert len(cols) == len(set(cols))
        assert len(cols) > 5


def test_closed_vocabularies():
    assert set(PROVENANCE_TIERS) == {"A_OFFICIAL_VECTOR", "B_PUBLISHED_DATASET",
                                      "C_DERIVED"}
    assert "VERIFIED" in EVIDENCE_STATUSES and "UNKNOWN" in EVIDENCE_STATUSES
    assert set(LABEL_TIERS) == {"GOLD", "SILVER", "WEAK", "UNLABELED"}
    assert "TRAIN" in ALLOWED_USES and "DO_NOT_USE" in ALLOWED_USES
    # pre-era must be distinguishable from a queried zero
    assert "SENSOR_NOT_OPERATIONAL" in GAP_STATUSES
    assert "NO_SCENES_FOUND" in GAP_STATUSES
    assert "QUERY_NOT_RUN" in GAP_STATUSES
    assert "UNKNOWN" in GAP_STATUSES


def test_sensor_order_is_six_pinned_collections_domain():
    assert SENSORS == ("landsat5", "landsat7", "landsat8",
                       "landsat9", "sentinel1", "sentinel2")


def test_scene_columns_carry_provenance_and_slc():
    assert {"scene_id", "acquisition_utc", "slc_status", "spacecraft",
            "processing_baseline", "footprint_coverage_fraction",
            "scene_cloud_fraction"} <= set(CENSUS_SCENE_COLUMNS)
    assert {"quality_candidate_scenes", "qa_level", "gap_status",
            "summary_fingerprint"} <= set(CENSUS_SUMMARY_COLUMNS)
