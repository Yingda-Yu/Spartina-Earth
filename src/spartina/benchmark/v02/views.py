"""SpartinaShift v0.2 deterministic view contracts (Issue #21 Phase F).

Two data views are frozen BEFORE any model training. They are chosen on
data semantics only -- never tuned on model performance:

* SINGLE_EVENT_CANONICAL: one optical event per cell-year, chosen by a
  fixed tertile precedence, with its paired S1 (or an explicit missing
  modality mask).
* MULTI_DATE_SEASONAL: a fixed EARLY/MID/LATE date-slot stack per
  cell-year with per-slot missing masks, plus a deterministic robust
  median composite accompanied by a valid-date count. Sensors are never
  merged and Landsat identities are never harmonized.
"""

from __future__ import annotations

from typing import Any, Final

from spartina.benchmark.v02.acquisition import (
    ACTUAL_MASK_GATE,
    LANDSAT_TARGET_PER_CELL_YEAR,
    MAX_DATATAKES_PER_CELL_YEAR,
    MAX_LANDSAT_PER_CELL_YEAR,
    OPTICAL_CLOUD_MAX,
    S1_PRIMARY_GAP_DAYS,
    S1_SENSITIVITY_GAP_DAYS,
    STATUS_PAIRED,
    TERTILE_ORDER,
    TERTILES,
    document_checksum,
)
from spartina.data.gee.sentinel2 import S2_SCL_QA_POLICY_VERSION
from spartina.data.national.pilot_events import (
    AUTUMN_DOY_END,
    AUTUMN_DOY_START,
)

VIEWS_NAME: Final[str] = "V0_2_VIEW_CONTRACTS"
VIEW_SINGLE_EVENT: Final[str] = "SINGLE_EVENT_CANONICAL"
VIEW_MULTI_DATE: Final[str] = "MULTI_DATE_SEASONAL"

#: Canonical event precedence within a cell-year (deterministic; the MID
#: slot is closest to the predeclared target DOY 290).
CANONICAL_TERTILE_PRECEDENCE: Final[tuple[str, ...]] = ("MID", "EARLY",
                                                        "LATE")

S2_SR_BANDS: Final[tuple[str, ...]] = ("B2", "B3", "B4", "B8")
S1_BANDS: Final[tuple[str, ...]] = ("VV", "VH")
LANDSAT_BANDS_L8: Final[tuple[str, ...]] = (
    "SR_B1", "SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B6", "SR_B7")
LANDSAT_BANDS_L57: Final[tuple[str, ...]] = (
    "SR_B1", "SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B7")


def build_view_contracts(requirements_checksum: str) -> dict[str, Any]:
    """Assemble the frozen view-contract document."""
    doc: dict[str, Any] = {
        "product": VIEWS_NAME,
        "issue": 21,
        "requirements_checksum": requirements_checksum,
        "status": "FROZEN_BEFORE_TRAINING; data-semantics choices only; "
                  "never tuned on model performance",
        "shared_rules": {
            "phenology_window_doy": [AUTUMN_DOY_START, AUTUMN_DOY_END],
            "tertiles": [
                {"name": name, "doy_min": lo, "doy_max": hi,
                 "preferred_center_doy": center}
                for name, lo, hi, center in TERTILES],
            "tertile_slot_order": list(TERTILE_ORDER),
            "actual_mask_gate": ACTUAL_MASK_GATE,
            "optical_cloud_max": OPTICAL_CLOUD_MAX,
            "date_convention": "UTC calendar date, identical to the "
                               "frozen acquisition plan and census v0_1",
            "grid_rule": "native W10 native-UTM locked export grids; "
                         "10 m S2/S1 and 30 m Landsat never resampled to "
                         "a common resolution inside a view",
            "missingness": "every view carries explicit per-band and "
                           "per-date observation/VALID masks; absence is "
                           "never encoded as a numeric value",
        },
        "views": {
            VIEW_SINGLE_EVENT: {
                "definition": (
                    "Exactly one optical event per (cell, year); paired "
                    "S1 optional but explicit."),
                "optical_event_precedence": list(
                    CANONICAL_TERTILE_PRECEDENCE),
                "optical_event_rule": (
                    "first V02_ELIGIBLE S2 datatake in precedence "
                    "MID > EARLY > LATE; cell-years with no eligible S2 "
                    "event have NO canonical optical sample (never "
                    "substituted from another year or sensor)"),
                "s2_band_order": list(S2_SR_BANDS),
                "s2_qa_policy": S2_SCL_QA_POLICY_VERSION,
                "s2_qa_semantics": (
                    "per-pixel VALID surface mask from the frozen "
                    "s2_scl_qa_v1_1 SCL policy accompanies the SR bands; "
                    "observed-mask gate and SCL VALID are both propagated"),
                "s1_pair_rule": {
                    "primary_gap_days_max": S1_PRIMARY_GAP_DAYS,
                    "pair_status_required": STATUS_PAIRED,
                    "s1_band_order": list(S1_BANDS),
                    "pass_preserved": True,
                    "relative_orbit_preserved": True,
                    "missing_modality": (
                        "when no <= 7 d gate-passing pair exists the S1 "
                        "bands are emitted as an explicit missing-modality "
                        "mask; the optical sample is preserved; the 14 d "
                        "sensitivity tier is NOT used in this view")},
                "landsat_rule": {
                    "anchor_years": [2015, 2020],
                    "event_precedence": list(CANONICAL_TERTILE_PRECEDENCE),
                    "band_sets_preserved_per_sensor": {
                        "landsat8": list(LANDSAT_BANDS_L8),
                        "landsat7": list(LANDSAT_BANDS_L57),
                        "landsat5": list(LANDSAT_BANDS_L57)},
                    "components": ["physical SR float32", "VALID r2 byte",
                                   "raw QA_PIXEL uint16"],
                    "scaling": "C2 L2 scale 0.0000275 add -0.2 applied at "
                               "export; recorded per product",
                    "harmonization": "NONE; no cross-sensor compositing or "
                                     "spectral adjustment"}},
            VIEW_MULTI_DATE: {
                "definition": (
                    "Fixed date-slot seasonal stack, one slot per tertile, "
                    "with deterministic robust aggregation and full "
                    "missingness propagation."),
                "slot_ordering": list(TERTILE_ORDER),
                "slot_assignment": (
                    "each acquired V02_ELIGIBLE event occupies exactly "
                    "its acquisition tertile slot; at most one S2 event "
                    f"and one Landsat observation per sensor per slot; "
                    f"max {MAX_DATATAKES_PER_CELL_YEAR} S2 datatakes and "
                    f"{MAX_LANDSAT_PER_CELL_YEAR} Landsat observations per "
                    "cell-year; empty slots are explicit masks"),
                "stack_contents": [
                    "per-slot SR bands in fixed band order",
                    "per-slot observed-mask (actual geometric coverage)",
                    "per-slot QA VALID mask (s2_scl_qa_v1_1 / Landsat "
                    "VALID r2)",
                    "per-slot acquisition doy and event id",
                    "per-slot S1 pair block (VV/VH + pair gap + pass + "
                    "orbit or missing-modality mask)"],
                "aggregation": {
                    "rule": "per-pixel robust median across the available "
                            "in-window dates, computed only over pixels "
                            "VALID under the frozen per-sensor QA policy "
                            "AND actually observed",
                    "minimum_dates": 1,
                    "companion_bands": [
                        "valid_date_count (number of dates entering each "
                        "pixel's median)",
                        "date_slot_present mask per tertile"],
                    "tie_break": (
                        "even-count medians use the mean of the two "
                        "central values; deterministic float32 reduction "
                        "in fixed EARLY, MID, LATE order"),
                    "no_medoid": (
                        "medoid rejected at freeze time: it requires a "
                        "distance choice that would encode a modeling "
                        "decision; robust median needs none")},
                "landsat_seasonal_rule": {
                    "target_observations": LANDSAT_TARGET_PER_CELL_YEAR,
                    "max_observations": MAX_LANDSAT_PER_CELL_YEAR,
                    "sensor_identity": (
                        "each slot records landsat5/7/8 identity; "
                        "aggregation runs WITHIN sensor identity only; "
                        "L7 and L8 pixels are never jointly medianed and "
                        "no harmonization is applied"),
                    "qa_components": [
                        "per-date physical SR", "per-date VALID r2",
                        "per-date raw QA_PIXEL (kept, never summarized "
                        "away)"]},
                "s1_seasonal_rule": (
                    "S1 remains paired per optical event; no S1 temporal "
                    "fusion across passes or dates; ASC/DESC never merged"),
                "sensitivity_tier": {
                    "gap_days": S1_SENSITIVITY_GAP_DAYS,
                    "usage": (
                        "frozen for later sensitivity analysis ONLY; "
                        "never back-fills the primary view; threshold "
                        "cannot be widened after seeing support without a "
                        "new frozen contract")},
            },
        },
    }
    doc["document_checksum"] = document_checksum(doc)
    return doc


def validate_view_contracts(document: dict[str, Any]) -> None:
    """Raise ValueError on any contract inconsistency."""
    errors: list[str] = []
    if document.get("product") != VIEWS_NAME:
        errors.append("product name mismatch")
    embedded = document.get("document_checksum")
    if embedded != document_checksum(document):
        errors.append("embedded checksum mismatch")
    views = document.get("views", {})
    for name in (VIEW_SINGLE_EVENT, VIEW_MULTI_DATE):
        if name not in views:
            errors.append(f"missing view {name}")
    single = views.get(VIEW_SINGLE_EVENT, {})
    if list(single.get("optical_event_precedence", [])) != list(
            CANONICAL_TERTILE_PRECEDENCE):
        errors.append("canonical tertile precedence altered")
    if single.get("s2_qa_policy") != S2_SCL_QA_POLICY_VERSION:
        errors.append("S2 QA policy token drift")
    multi = views.get(VIEW_MULTI_DATE, {})
    if list(multi.get("slot_ordering", [])) != list(TERTILE_ORDER):
        errors.append("seasonal slot ordering drift")
    agg = multi.get("aggregation", {})
    if agg.get("minimum_dates") != 1:
        errors.append("aggregation minimum_dates drift")
    if errors:
        raise ValueError("; ".join(errors))
