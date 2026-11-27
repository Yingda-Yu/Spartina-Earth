"""Issue #21, Phase A — frozen SpartinaShift v0.2 support requirements.

This module is frozen BEFORE any new-cell selection and before any pixel
is exported. It declares:

* the support goals for the v0.2 benchmark expansion (never forced; if
  the data cannot meet a goal, the maximum attainable support is
  reported honestly);
* the hard Phase H scope caps;
* the legal and forbidden inputs to deterministic cell selection
  (no model output may ever enter);
* the acquisition rules for Phases D-G (multi-date Sentinel-2,
  multi-date Landsat, the two predeclared data views, near-synchronous
  Sentinel-1 pairing);
* the development-only status of the original 20-cell Stage-1 panel and
  the hard exclusion of its inspected test/witness cells from the
  pristine primary v0.2 test.

Nothing in this module is derived from model performance.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Final

from spartina.data.national.pilot_events import (
    AUTUMN_DOY_END,
    AUTUMN_DOY_START,
    AUTUMN_TAG,
    OPTICAL_CLOUD_MAX,
    POSTEXPORT_GEOMETRIC_VALID_MIN,
    TARGET_DOY,
)

REQUIREMENTS_NAME: Final[str] = "SPARTINASHIFT_V0_2_SUPPORT_REQUIREMENTS"
REQUIREMENTS_VERSION: Final[str] = "v0.2-requirements-frozen"
ISSUE: Final[int] = 21
PHASE: Final[str] = "A"
STATUS: Final[str] = "FROZEN_PRE_SELECTION"

# ---------------------------------------------------------------------
# Corrected scientific interpretation carried over from the Issue #20
# owner review. Stage 1 is a support/instrumentation diagnostic only.
# ---------------------------------------------------------------------
STAGE1_PANEL_STATUS: Final[str] = "DEVELOPMENT_INSTRUMENTATION_ONLY"
STAGE1_INTERPRETATION: Final[str] = (
    "Within-scene separability exists, but the current benchmark "
    "support is too weak to attribute cross-scene/temporal collapse "
    "to model capacity.")
FORBIDDEN_CLAIM: Final[str] = (
    "Issue #20 / Stage 1 must not be stated to prove that model "
    "capacity is sufficient.")

# ---------------------------------------------------------------------
# Phase H hard scope caps (an owner-review STOP is triggered if the
# projected scope exceeds ANY of these).
# ---------------------------------------------------------------------
MAX_NEW_CELLS: Final[int] = 96
MAX_LANDED_EO_GIB: Final[int] = 40
MAX_GEE_COMPONENT_TASKS: Final[int] = 10_000

# ---------------------------------------------------------------------
# Frozen selection universe.
# ---------------------------------------------------------------------
DOMAIN_TOKEN: Final[str] = "W10_DOMAIN_V1_CORE_FROZEN"
DOMAIN_KEEP_CELLS: Final[int] = 3016
DOMAIN_EXCLUDED_CELLS: Final[int] = 298
DOMAIN_PROVISIONAL_CELLS: Final[int] = 5
PRODUCTION_ELIGIBLE_REQUIRED: Final[bool] = True
SELECTION_UNIT: Final[str] = "W10 cell (China Albers equal-area, 10 km)"
SELECTION_NAMESPACE: Final[str] = "SPARTINASHIFT_V0_2_CELL_SELECTION"
CELL_ID_TIE_BREAK: Final[str] = "cell_id ascending"

# ---------------------------------------------------------------------
# Phase A support goals. Targets are goals, never forced: when the
# frozen inputs cannot reach a target, the maximum attainable support
# is reported and the shortfall is recorded, not hidden.
# ---------------------------------------------------------------------
ATTAINABILITY_POLICY: Final[str] = (
    "Goals are never forced. If a requirement cannot be met from the "
    "frozen inputs, the maximum attainable support and the shortfall "
    "are reported honestly; no threshold is relaxed after seeing "
    "imagery or model outputs.")

GEODATA_TEMPORAL_GOALS: Final[dict[str, Any]] = {
    "label_family": "GEODATA",
    "anchor_years": [2015, 2020],
    "positive_cells_usable_both_years_min": 12,
    "regions_min": 3,
    "background_cells_min": 12,
    "positive_definition": (
        "named GEODATA Spartina presence/area in BOTH 2015 and 2020 "
        "for the same W10 cell (national 30 m product; fractional "
        "area support, no synthetic upsampling)"),
}

CMSA_TEMPORAL_GOALS: Final[dict[str, Any]] = {
    "label_family": "CMSA",
    "anchor_years": [2020, 2021],
    "positive_cells_usable_both_years_min": 24,
    "regions_min": 4,
    "background_cells_min": 24,
    "background_comparability_note": (
        "'comparable background/control support' is predeclared to "
        "mean at least the same cell count as the positive target"),
    "positive_definition": (
        "gridcode=2 CMSA polygon presence/area in BOTH 2020 and 2021 "
        "for the same W10 cell; gridcode=0 polygons are UNKNOWN and "
        "never count as positive or background evidence"),
}

CROSS_REGION_GOALS: Final[dict[str, Any]] = {
    "defensible_region_holdouts_min": 4,
    "held_region_cells_min": 4,
    "held_region_positive_cells_min": 2,
    "outside_pool_cells_min": 12,
    "outside_pool_positive_cells_min": 4,
    "region_definition": (
        "target-independent province attribution (Natural Earth 10 m "
        "admin-1 v5.1.1; centroid-in-province, else unique nearest "
        "province within 25 km with a >300 m second-province margin, "
        "else UNKNOWN); UNKNOWN cannot anchor a holdout"),
}

NEAR_SYNCHRONOUS_GOALS: Final[dict[str, Any]] = {
    "paired_cells_min": 24,
    "paired_positive_cells_min": 12,
    "primary_pairing_gap_days_max": 7,
    "gap_semantics": "absolute |S2 date - S1 date| in calendar days",
    "simultaneous_rule": (
        "a pair is called 'simultaneous' only when the gap is exactly "
        "0 days; otherwise the numeric gap is reported"),
}

# ---------------------------------------------------------------------
# Phase B legal vs forbidden selection inputs.
# ---------------------------------------------------------------------
LEGAL_SELECTION_INPUTS: Final[tuple[str, ...]] = (
    "frozen W10 geography and registry "
    "(W10_DOMAIN_V1_CORE_FROZEN, production_eligible=true)",
    "target-independent region/province groups and coastal-segment "
    "attribution",
    "mainland/island operational class",
    "named label-source presence/area: GEODATA 1990/2000/2015/2020, "
    "CMSA 2017-2021 (gridcode=2 positive), CM-SSM 2020 "
    "(external-reference only, never a training/tuning label)",
    "Issue #18 pre-model agreement/disagreement strata "
    "(exclusive_stratum / agreement categories)",
    "patch/area class derived from named label products",
    "EO availability and QA metadata from the metadata-only national "
    "census (event counts, coverage basis, cloud metadata); no pixels",
)

FORBIDDEN_SELECTION_INPUTS: Final[tuple[str, ...]] = (
    "any model prediction or model-derived feature",
    "Stage-1 failure maps, error maps, or per-cell errors",
    "model uncertainty, confidence, or calibration outputs",
    "Stage-1 test/evaluation performance of any kind",
    "label appearance or content visible in downloaded imagery",
    "any redesign of the panel after seeing imagery or pixels",
)

# ---------------------------------------------------------------------
# Phases D-G acquisition rules.
# ---------------------------------------------------------------------
PHENOLOGY: Final[dict[str, Any]] = {
    "autumn_doy_start": AUTUMN_DOY_START,
    "autumn_doy_end": AUTUMN_DOY_END,
    "target_doy": TARGET_DOY,
    "season_tag": AUTUMN_TAG,
    "window_note": (
        "identical to the frozen Issue #19 V2 predeclared autumn "
        "window; target DOY is a tie-break only"),
}

S2_RULES: Final[dict[str, Any]] = {
    "cell_years": [2020, 2021],
    "max_datatakes_per_cell_year": 3,
    "qa_policy": "s2_scl_qa_v1_1",
    "scene_cloud_fraction_max": OPTICAL_CLOUD_MAX,
    "postexport_actual_mask_valid_min": POSTEXPORT_GEOMETRIC_VALID_MIN,
    "coverage_basis": "SAME_DATATAKE_MEMBER_TILE_UNION_COVERS_CELL",
    "spread_rule": (
        "selected datatakes must be spread across the predeclared "
        "window; near-duplicate dates are forbidden; ranking is "
        "deterministic (cloud asc, |doy-target| asc, event_id asc) "
        "after a predeclared date-spacing partition of the window"),
    "label_use": "label appearance is never used",
}

LANDSAT_RULES: Final[dict[str, Any]] = {
    "cell_years": [2015, 2020],
    "observations_per_cell_year_desired": [2, 3],
    "collection": "Collection 2 Level-2 science products",
    "qa_band": "QA_PIXEL",
    "postexport_actual_mask_valid_min": POSTEXPORT_GEOMETRIC_VALID_MIN,
    "nominal_frame_tier": "WRS2_NOMINAL_FRAME_NEAR_FULL_TOLERANCE_V1",
    "preserve": [
        "source sensor identity (L5/L7/L8/L9)",
        "QA_PIXEL semantics",
        "physical scaling (Collection 2 L2 reflectance/temperature)",
        "actual-mask eligibility",
    ],
    "harmonization": (
        "no silent spectral harmonization across sensors; if fewer "
        "valid dates exist than desired, record the deficit honestly"),
}

VIEW_SINGLE_EVENT_CANONICAL: Final[str] = "SINGLE_EVENT_CANONICAL"
VIEW_MULTI_DATE_SEASONAL: Final[str] = "MULTI_DATE_SEASONAL"
VIEW_CONTRACT: Final[dict[str, Any]] = {
    "views": [VIEW_SINGLE_EVENT_CANONICAL, VIEW_MULTI_DATE_SEASONAL],
    "multi_date_representation_freeze": (
        "The deterministic MULTI_DATE_SEASONAL representation (date "
        "ordering, missingness, QA propagation, aggregation rule, "
        "band semantics) is frozen in Phase F BEFORE any training; "
        "candidate forms are temporal stack, robust median/medoid, "
        "and fixed-date-slot stack with missing masks. The choice is "
        "made on data semantics only, never on model performance."),
}

S1_RULES: Final[dict[str, Any]] = {
    "instrument_mode": "IW",
    "polarizations": ["VV", "VH"],
    "validity_token": "s1_dualpol_valid_v2",
    "validity_definition": (
        "finite VV AND finite VH AND both values > -70 dB on the "
        "landed grid"),
    "preserve": ["ASC/DESC pass direction", "relative orbit number"],
    "primary_pairing_gap_days_max": 7,
    "ranking": [
        "minimum absolute S2-S1 date gap",
        "existing s1_dualpol_valid_v2 / actual-mask quality rule",
        "deterministic source ID tie-break",
    ],
    "unpaired_optical_rule": (
        "if no <=7 day pair exists, preserve the optical sample and "
        "mark the modality slot UNAVAILABLE; the optical sample is "
        "never dropped"),
    "threshold_widen_rule": (
        "the primary 7-day threshold is not widened after seeing "
        "support; any wider sensitivity tier must be frozen before "
        "training as a separate tier"),
    "full_ledger_required": True,
}

#: Phase C freshness rule for the primary v0.2 test reserve.
FRESH_TEST_RESERVE_RULES: Final[dict[str, Any]] = {
    "name": "V0_2_FRESH_NEW_CELL_TEST_RESERVE",
    "membership": "new cells only (not Stage-1 panel cells)",
    "old_test_witness_eligible_as_primary_test": False,
    "model_output_influence": False,
    "final_roles_assigned_now": False,
    "strata_represented": ["region", "positive/background"],
    "note": (
        "final train/val/test roles are frozen by the future v0.2 "
        "protocol after acquisition QA completes, without revisiting "
        "Stage-1 performance"),
}

# Input artifact references; the emitter fills the SHA-256 values at
# freeze time and fails if any artifact is missing or altered.
INPUT_ARTIFACTS: Final[tuple[str, ...]] = (
    "datasets/manifests/china_coastal_cells_v1_1_core_frozen.csv",
    "work/national/strata/strata_china_albers_W10000.csv",
    "work/issue18/derived/s30_cells.csv",
    "work/issue18/derived/s10_cells.csv",
    "work/national/census_r1/products/china_cell_event_census_v0_1.parquet",
    "datasets/manifests/national_first_pixel_panel_v1.json",
    "benchmarks/spartinashift/silver_v0_1/SPARTINASHIFT_SILVER_V0_1_PROTOCOL.json",
    "benchmarks/spartinashift/silver_v0_1/splits_v0_1.json",
)


def selection_hash_rank(namespace: str, cell_id: str) -> str:
    """Deterministic SHA-256 rank for a cell under a named namespace."""
    return hashlib.sha256(
        f"{REQUIREMENTS_NAME}|{namespace}|{cell_id}".encode()).hexdigest()


def requirements_checksum(document: dict[str, Any]) -> str:
    """SHA-256 over the frozen content, excluding bookkeeping fields.

    Mirrors the canonical v0.1 protocol-checksum convention.
    """
    body = {k: v for k, v in document.items()
            if k not in {"checksum", "document_checksum",
                         "git_commit", "generated_utc"}}
    canonical = json.dumps(
        body, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def validate_requirements(document: dict[str, Any]) -> None:
    """Validate a frozen requirements document.

    Raises ``ValueError`` listing every structural violation; the
    embedded checksum is verified against the recomputed one.
    """
    problems: list[str] = []

    def need(cond: bool, message: str) -> None:
        if not cond:
            problems.append(message)

    need(document.get("requirements_name") == REQUIREMENTS_NAME,
         "requirements_name mismatch")
    need(document.get("requirements_version") == REQUIREMENTS_VERSION,
         "requirements_version mismatch")
    need(document.get("issue") == ISSUE, "issue must be 21")
    need(document.get("phase") == PHASE, "phase must be A")
    need(document.get("status") == STATUS, "status must be FROZEN_PRE_SELECTION")

    scope = document.get("hard_scope_caps", {})
    need(scope.get("max_new_cells") == MAX_NEW_CELLS, "new-cell cap")
    need(scope.get("max_landed_eo_gib") == MAX_LANDED_EO_GIB, "GiB cap")
    need(scope.get("max_gee_component_tasks") == MAX_GEE_COMPONENT_TASKS,
         "GEE task cap")

    goals = document.get("support_goals", {})
    geo, cmsa = goals.get("geodata_temporal", {}), goals.get("cmsa_temporal", {})
    xr, pair = goals.get("cross_region", {}), goals.get("near_synchronous", {})
    need(geo.get("positive_cells_usable_both_years_min") == 12,
         "GEODATA positive goal must be 12")
    need(geo.get("regions_min") == 3, "GEODATA region goal must be 3")
    need(geo.get("background_cells_min") == 12,
         "GEODATA background goal must be 12")
    need(cmsa.get("positive_cells_usable_both_years_min") == 24,
         "CMSA positive goal must be 24")
    need(cmsa.get("regions_min") == 4, "CMSA region goal must be 4")
    need(cmsa.get("background_cells_min") == 24,
         "CMSA background goal must be 24 (predeclared comparability)")
    need(xr.get("defensible_region_holdouts_min") == 4,
         "need >=4 region holdouts")
    need(xr.get("held_region_cells_min") == 4, "held region >=4 cells")
    need(xr.get("held_region_positive_cells_min") == 2,
         "held region >=2 positive")
    need(xr.get("outside_pool_cells_min") == 12, "outside pool >=12")
    need(xr.get("outside_pool_positive_cells_min") == 4,
         "outside pool >=4 positive")
    need(pair.get("paired_cells_min") == 24, "paired cells goal 24")
    need(pair.get("paired_positive_cells_min") == 12,
         "paired positive goal 12")
    need(pair.get("primary_pairing_gap_days_max") == 7, "pairing gap 7 days")

    s2, l8, s1 = (document.get("acquisition_rules", {}).get(k, {})
                  for k in ("sentinel2", "landsat", "sentinel1"))
    need(s2.get("max_datatakes_per_cell_year") == 3, "S2 <=3 datatakes")
    need(s2.get("qa_policy") == "s2_scl_qa_v1_1", "S2 QA policy token")
    need(s2.get("postexport_actual_mask_valid_min") == 0.95,
         "S2 actual-mask 0.95")
    need(l8.get("collection") == "Collection 2 Level-2 science products",
         "Landsat C2 L2")
    need(l8.get("qa_band") == "QA_PIXEL", "Landsat QA_PIXEL")
    need(s1.get("instrument_mode") == "IW", "S1 IW")
    need(s1.get("validity_token") == "s1_dualpol_valid_v2", "S1 validity token")
    need(s1.get("primary_pairing_gap_days_max") == 7, "S1 pairing 7 days")

    legal = set(document.get("selection_inputs", {}).get("legal", []))
    forbidden = set(document.get("selection_inputs", {}).get("forbidden", []))
    need(len(legal) == len(LEGAL_SELECTION_INPUTS), "legal input list altered")
    need(len(forbidden) == len(FORBIDDEN_SELECTION_INPUTS),
         "forbidden input list altered")
    need(not (legal & forbidden), "legal and forbidden inputs overlap")

    stage1 = document.get("stage1_panel", {})
    need(stage1.get("status") == STAGE1_PANEL_STATUS,
         "Stage-1 panel must be DEVELOPMENT_INSTRUMENTATION_ONLY")
    panel = stage1.get("cell_ids", [])
    need(len(panel) == 20, "Stage-1 panel must list 20 cells")
    need(len(set(panel)) == 20, "Stage-1 panel ids must be unique")
    inspected = set(stage1.get("inspected_test_witness_cell_ids", []))
    need(len(inspected) >= 1, "inspected test/witness list missing")
    need(inspected <= set(panel), "inspected cells must be panel members")
    need(not stage1.get("eligible_as_primary_v02_test", True),
         "Stage-1 cells must be ineligible as primary v0.2 test")

    inputs = document.get("input_artifacts", [])
    need(len(inputs) == len(INPUT_ARTIFACTS), "input artifact list altered")
    for entry in inputs:
        need(len(entry.get("sha256", "")) == 64,
             f"missing checksum for {entry.get('path', '?')}")

    embedded = document.get("checksum")
    need(isinstance(embedded, str) and len(embedded) == 64,
         "embedded checksum missing")
    if isinstance(embedded, str) and len(embedded) == 64:
        recomputed = requirements_checksum(document)
        need(recomputed == embedded,
             f"checksum mismatch: embedded={embedded[:12]} "
             f"recomputed={recomputed[:12]}")

    if problems:
        raise ValueError("requirements document invalid: " + "; ".join(problems))
