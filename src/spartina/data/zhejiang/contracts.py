"""Shared contracts for the Zhejiang three-bay M2.1a sampling frame.

Only vocabulary, enums and column names live here -- no I/O, no Earth
Engine import. Keeping the vocabulary in one place lets the census code,
manifest writers and schema tests agree exactly on the strings that
implement Issue #7 anti-fabrication rules:

* pre-operational years say ``SENSOR_NOT_OPERATIONAL`` (never "0 scenes");
* label tiers and allowed-use categories are closed sets (no GOLD is
  allowed to be *produced* at this stage; GOLD can only be cross-linked as
  candidate evidence owned by Issue #11);
* QA levels distinguish cheap scene metadata from ROI pixel QA.
"""

from __future__ import annotations

from typing import Final

# --- Provenance / geometry ------------------------------------------------
PROVENANCE_TIER_A: Final[str] = "A_OFFICIAL_VECTOR"
PROVENANCE_TIER_B: Final[str] = "B_PUBLISHED_DATASET"
PROVENANCE_TIER_C: Final[str] = "C_DERIVED"
PROVENANCE_TIERS: Final[tuple[str, ...]] = (
    PROVENANCE_TIER_A,
    PROVENANCE_TIER_B,
    PROVENANCE_TIER_C,
)

EVIDENCE_VERIFIED: Final[str] = "VERIFIED"
EVIDENCE_PROVISIONAL: Final[str] = "PROVISIONAL"
EVIDENCE_REJECTED: Final[str] = "REJECTED"
EVIDENCE_UNKNOWN: Final[str] = "UNKNOWN"
EVIDENCE_STATUSES: Final[tuple[str, ...]] = (
    EVIDENCE_VERIFIED,
    EVIDENCE_PROVISIONAL,
    EVIDENCE_REJECTED,
    EVIDENCE_UNKNOWN,
)

ANCHOR_SECTION_POINT: Final[str] = "SECTION_POINT"
ANCHOR_CONSTRUCTION_CORNER: Final[str] = "CONSTRUCTION_CORNER"
ANCHOR_KINDS: Final[tuple[str, ...]] = (
    ANCHOR_SECTION_POINT,
    ANCHOR_CONSTRUCTION_CORNER,
)

# --- Labels ---------------------------------------------------------------
LABEL_GOLD: Final[str] = "GOLD"
LABEL_SILVER: Final[str] = "SILVER"
LABEL_WEAK: Final[str] = "WEAK"
LABEL_UNLABELED: Final[str] = "UNLABELED"
LABEL_TIERS: Final[tuple[str, ...]] = (
    LABEL_GOLD,
    LABEL_SILVER,
    LABEL_WEAK,
    LABEL_UNLABELED,
)

USE_TRAIN: Final[str] = "TRAIN"
USE_VALIDATION_REFERENCE: Final[str] = "VALIDATION_REFERENCE"
USE_DIAGNOSTIC_ONLY: Final[str] = "DIAGNOSTIC_ONLY"
USE_DESCRIPTIVE_ONLY: Final[str] = "DESCRIPTIVE_ONLY"
USE_DO_NOT_USE: Final[str] = "DO_NOT_USE"
ALLOWED_USES: Final[tuple[str, ...]] = (
    USE_TRAIN,
    USE_VALIDATION_REFERENCE,
    USE_DIAGNOSTIC_ONLY,
    USE_DESCRIPTIVE_ONLY,
    USE_DO_NOT_USE,
)

#: Sentinel used when an inventory row can only point at potential GOLD
#: evidence; promotion itself belongs to Issue #11.
GOLD_CANDIDATE_ONLY: Final[str] = "GOLD_CANDIDATE_EVIDENCE"

# --- EO census ------------------------------------------------------------
QA_SCENE_METADATA: Final[str] = "SCENE_METADATA"
QA_ROI_PIXEL: Final[str] = "ROI_PIXEL_QA"
QA_LEVELS: Final[tuple[str, ...]] = (QA_SCENE_METADATA, QA_ROI_PIXEL)

GAP_NOT_OPERATIONAL: Final[str] = "SENSOR_NOT_OPERATIONAL"
GAP_NO_SCENES: Final[str] = "NO_SCENES_FOUND"
GAP_NO_QUALITY: Final[str] = "NO_QUALITY_SCENES"
GAP_QUERY_NOT_RUN: Final[str] = "QUERY_NOT_RUN"
GAP_UNKNOWN: Final[str] = "UNKNOWN"
#: Not a gap: at least one usable scene exists this year.
GAP_NONE: Final[str] = "NONE"
GAP_STATUSES: Final[tuple[str, ...]] = (
    GAP_NOT_OPERATIONAL,
    GAP_NO_SCENES,
    GAP_NO_QUALITY,
    GAP_QUERY_NOT_RUN,
    GAP_UNKNOWN,
    GAP_NONE,
)

SLC_PRE_FAILURE: Final[str] = "PRE_SLC_FAILURE"
SLC_POST_FAILURE: Final[str] = "POST_SLC_FAILURE"
SLC_NA: Final[str] = "NOT_APPLICABLE"

ORBIT_ASCENDING: Final[str] = "ASCENDING"
ORBIT_DESCENDING: Final[str] = "DESCENDING"

#: Sensors actually censused at M2.1a, in fixed display/processing order.
SENSORS: Final[tuple[str, ...]] = (
    "landsat5",
    "landsat7",
    "landsat8",
    "landsat9",
    "sentinel1",
    "sentinel2",
)

OPTICAL_SENSORS: Final[tuple[str, ...]] = (
    "landsat5",
    "landsat7",
    "landsat8",
    "landsat9",
    "sentinel2",
)

BAY_IDS: Final[tuple[str, ...]] = ("ZJ-HZB", "ZJ-SMB", "ZJ-YQB")

# --- Manifest column schemas (single source of truth) --------------------
ROI_REGISTRY_COLUMNS: Final[tuple[str, ...]] = (
    "roi_id",
    "name_zh",
    "name_en",
    "geometry_status",
    "provenance_tier",
    "derivation_method",
    "base_coastline_id",
    "base_coastline_sha256",
    "source_crs",
    "analysis_crs",
    "envelope_area_km2",
    "water_area_km2",
    "onshore_belt_area_km2",
    "roi_area_km2",
    "published_area_km2",
    "published_area_delta_pct",
    "bbox_west_east_south_north",
    "max_anchor_snap_m",
    "geometry_is_valid",
    "geometry_fingerprint",
    "logical_fingerprint",
    "source_ids",
    "notes",
)

ROI_SOURCE_COLUMNS: Final[tuple[str, ...]] = (
    "source_id",
    "applies_to",
    "publisher",
    "title",
    "url",
    "doi",
    "publication_date",
    "access_date",
    "geometry_type",
    "crs",
    "boundary_meaning",
    "license",
    "status",
    "notes",
)

LABEL_INVENTORY_COLUMNS: Final[tuple[str, ...]] = (
    "asset_id",
    "asset_name",
    "asset_kind",
    "nominal_year",
    "verified_acquisition_date",
    "source_owner",
    "method",
    "resolution_m",
    "crs",
    "geometry_kind",
    "overlap_zj_hzb",
    "overlap_zj_smb",
    "overlap_zj_yqb",
    "overlap_units",
    "overlap_area_km2",
    "label_tier",
    "license",
    "redistributable",
    "known_problems",
    "allowed_use",
    "allowed_use_reason",
    "gold_candidate_issue",
    "local_path",
    "logical_fingerprint",
    "notes",
)

CENSUS_SCENE_COLUMNS: Final[tuple[str, ...]] = (
    "roi_id",
    "year",
    "sensor",
    "collection_id",
    "scene_id",
    "acquisition_utc",
    "day_of_year",
    "tile_ref",
    "orbit_direction",
    "relative_orbit_number",
    "instrument_mode",
    "polarizations",
    "spacecraft",
    "processing_baseline",
    "slc_status",
    "scene_cloud_fraction",
    "footprint_coverage_fraction",
    "metadata_retrieval_timestamp",
)

CENSUS_SUMMARY_COLUMNS: Final[tuple[str, ...]] = (
    "roi_id",
    "year",
    "sensor",
    "collection_id",
    "operational",
    "slc_status",
    "qa_level",
    "total_scenes",
    "distinct_acquisition_dates",
    "scenes_ascending",
    "scenes_descending",
    "tile_refs",
    "spacecraft_names",
    "processing_baselines",
    "scene_cloud_eligible_scenes",
    "footprint_coverage_eligible_scenes",
    "season_candidate_scenes",
    "season_candidate_window_ids",
    "quality_candidate_scenes",
    "best_footprint_coverage",
    "gap_status",
    "query_status",
    "metadata_retrieval_timestamp",
    "summary_fingerprint",
)

AVAILABILITY_COLUMNS: Final[tuple[str, ...]] = (
    "year",
    "roi_id",
    "landsat5_status",
    "landsat5_scenes",
    "landsat7_status",
    "landsat7_scenes",
    "landsat8_status",
    "landsat8_scenes",
    "landsat9_status",
    "landsat9_scenes",
    "sentinel1_status",
    "sentinel1_scenes",
    "sentinel2_status",
    "sentinel2_scenes",
    "label_available",
    "field_uav_available",
    "management_event_known",
    "tide_metadata",
    "status",
)
