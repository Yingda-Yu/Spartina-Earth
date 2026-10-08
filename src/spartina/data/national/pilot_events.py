"""Deterministic pilot event-selection policy (Issue #19, Phase C).

The policy is fixed BEFORE any pixel is read and uses only defensible EO
criteria: actual/nominal footprint coverage, acquisition date inside the
predeclared autumn phenology window (DOY 260-320,
``AUTUMN_PRIMARY_V1_CANDIDATE``), scene-level cloud metadata, and S1
orbit-pass semantics. Label overlap and any future model performance are
never inputs. No cross-date optical mosaics; S2 keeps the same-datatake
group; S1 ASC/DESC stay separate.

Pure pandas helpers; the builder script supplies the frozen census tables.
"""

from __future__ import annotations

from typing import Final

import pandas as pd

from spartina.data.national.pilot_panel import SensorYearStatus

#: Predeclared phenological window (identical to the national census tag).
AUTUMN_DOY_START: Final[int] = 260
AUTUMN_DOY_END: Final[int] = 320
AUTUMN_TAG: Final[str] = "AUTUMN_PRIMARY_V1_CANDIDATE"
TARGET_DOY: Final[int] = 290  # Oct 17: window centre, tie-break only

#: Scene-level cloud ceiling for optical selection. Predeclared at the
#: same 0.30 value used by the Zhejiang M2.1b pilot (no tuning after
#: looking at pilot pixels). Pixel-valid fractions are recorded at export
#: time from QA_PIXEL / SCL; they are never used for selection.
OPTICAL_CLOUD_MAX: Final[float] = 0.30

FULL_COVER: Final[str] = "FULL_CELL_COVERED"
PARTIAL_COVER: Final[str] = "PARTIAL_CELL_OVERLAP"

#: Landsat-only second coverage tier. When no strictly full-cover
#: cloud-eligible autumn scene exists, a scene on a nominal WRS-2 frame
#: covering at least this fraction of the cell polygon may be selected.
#: The threshold is predeclared before any pixel is read; the exact
#: fraction and frame are recorded on the plan row; acceptance at Phase H
#: additionally requires ``POSTEXPORT_GEOMETRIC_VALID_MIN`` of the landed
#: export grid to carry non-fill pixels. S1 (actual footprint) and S2
#: (same-datatake tile union) never use this tolerance.
NEAR_FULL_NOMINAL_MIN: Final[float] = 0.90

#: Phase H post-export gate for near-full products: minimum geometric
#: valid fraction (QA_PIXEL fill bit clear) across the exported grid.
POSTEXPORT_GEOMETRIC_VALID_MIN: Final[float] = 0.95

#: Coverage-basis tokens carried into product provenance.
BASIS_LANDSAT_FULL: Final[str] = "WRS2_NOMINAL_FRAME_FULL"
BASIS_LANDSAT_NEAR_FULL: Final[str] = (
    "WRS2_NOMINAL_FRAME_NEAR_FULL_TOLERANCE_V1")
BASIS_S2_UNION: Final[str] = "SAME_DATATAKE_MEMBER_TILE_UNION_COVERS_CELL"

S1_IW: Final[str] = "IW"
#: Canonical dual-pol token; the v0 census stored "VH|VV" and the rebuilt
#: v0_1 funnel stores "VV|VH" -- both denote the same IW VV+VH product and
#: are accepted identically.
S1_DUAL_POL: Final[str] = "VV|VH"
S1_DUAL_POL_TOKENS: Final[frozenset[str]] = frozenset({"VV|VH", "VH|VV"})
PASSES: Final[tuple[str, str]] = ("ASC", "DESC")

TIER_STRICT: Final[str] = "STRICT_FULL"
TIER_NEAR_FULL: Final[str] = "NEAR_FULL_NOMINAL_TOLERANCE"


class SelectionError(ValueError):
    """Raised when candidate rows violate the event contract."""


def optical_candidates(events: pd.DataFrame) -> pd.DataFrame:
    """Restrict cell-event rows to autumn events (any coverage token).

    ``events`` needs columns: season_tag, coverage, doy, cloud_fraction.
    """
    if events.empty:
        return events
    need = {"season_tag", "coverage", "doy", "cloud_fraction"}
    missing = need - set(events.columns)
    if missing:
        raise SelectionError(f"optical events missing columns: {sorted(missing)}")
    return events[events["season_tag"] == AUTUMN_TAG].copy()


def _cloud_eligible(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[
        frame["cloud_fraction"].astype(float) <= OPTICAL_CLOUD_MAX].copy()


def _rank(frame: pd.DataFrame, *, by_cloud: bool) -> pd.DataFrame:
    keys = (["cloud_fraction"] if by_cloud else []) + [
        "doy_dist", "event_id"]
    return frame.assign(
        doy_dist=(frame["doy"].astype(int) - TARGET_DOY).__abs__()
    ).sort_values(keys, ascending=True).reset_index(drop=True)


def _near_full_pool(candidates: pd.DataFrame) -> pd.DataFrame:
    """Autumn PARTIAL events on nominal WRS frames covering >= threshold."""
    if "coverage_fraction" not in candidates.columns:
        return candidates.iloc[0:0]
    pool = candidates[
        (candidates["coverage"] != FULL_COVER)
        & candidates["coverage_fraction"].notna()
        & (candidates["coverage_fraction"].astype(float)
           >= NEAR_FULL_NOMINAL_MIN)].copy()
    basis = pool.get("geometry_basis")
    if basis is not None and not pool.empty:
        pool = pool[basis.astype(str).str.startswith("WRS2")]
    return pool


def _pick(
    ranked: pd.DataFrame, tier: str, detail_reason: str,
    n_intersecting: int, n_autumn: int, pool_size: int,
) -> tuple[SensorYearStatus, dict[str, object]]:
    pick = ranked.iloc[0]
    detail: dict[str, object] = {
        "reason": detail_reason,
        "coverage_tier": tier,
        "selection_rank_of_pool": f"1 of {len(ranked)} eligible",
        "n_intersecting_events": int(n_intersecting),
        "n_autumn_events": int(n_autumn),
        "n_eligible_after_gates": int(len(ranked)),
        "n_pool_for_tier": int(pool_size),
    }
    if tier == TIER_NEAR_FULL:
        detail["nominal_coverage_fraction"] = float(
            pick["coverage_fraction"])
        detail["post_export_gate"] = {
            "phase": "H",
            "measure": "geometric valid fraction (QA_PIXEL fill bit clear) "
                       "over the landed export grid",
            "min_required": POSTEXPORT_GEOMETRIC_VALID_MIN,
            "on_fail": "product marked GEOMETRY_FAIL and excluded",
        }
    return SensorYearStatus.SELECTED, {"event": _event_dict(pick), **detail}


def select_optical(
    events: pd.DataFrame,
) -> tuple[SensorYearStatus, dict[str, object]]:
    """Select one optical event under the predeclared two-tier policy.

    Tier 1 (strict): FULL_CELL_COVERED autumn events with scene cloud
    <= 0.30. Tier 2 (near-full, Landsat only): autumn PARTIAL events whose
    nominal WRS-2 frame covers >= ``NEAR_FULL_NOMINAL_MIN`` of the cell,
    same cloud gate; the choice is flagged and gated at Phase H. Rank key
    in both tiers: cloud fraction asc, |doy - 290| asc, event_id asc.
    """
    if events.empty:
        return (SensorYearStatus.NO_SCENE,
                {"reason": "no intersecting scene in the frozen census"})
    candidates = optical_candidates(events)
    n_intersecting = len(events)
    if candidates.empty:
        return (SensorYearStatus.NO_ELIGIBLE_EVENT,
                {"reason": (
                    "no event inside the predeclared autumn window DOY "
                    f"{AUTUMN_DOY_START}-{AUTUMN_DOY_END}"),
                 "n_intersecting_events": int(n_intersecting)})
    strict = candidates[candidates["coverage"] == FULL_COVER]
    strict_ok = _cloud_eligible(strict)
    if not strict_ok.empty:
        return _pick(
            _rank(strict_ok, by_cloud=True), TIER_STRICT,
            "predeclared policy: FULL_CELL_COVERED + autumn DOY "
            f"{AUTUMN_DOY_START}-{AUTUMN_DOY_END} + scene cloud <= "
            f"{OPTICAL_CLOUD_MAX:.2f}; rank = (cloud asc, |doy-290| asc, "
            "event_id asc)",
            n_intersecting, len(candidates), len(strict))
    near = _near_full_pool(candidates)
    near_ok = _cloud_eligible(near)
    if not near_ok.empty:
        return _pick(
            _rank(near_ok, by_cloud=True), TIER_NEAR_FULL,
            "no strict-full cloud-eligible autumn scene; predeclared "
            f"near-full tolerance (nominal WRS-2 frame cover >= "
            f"{NEAR_FULL_NOMINAL_MIN:.2f}) + autumn DOY "
            f"{AUTUMN_DOY_START}-{AUTUMN_DOY_END} + scene cloud <= "
            f"{OPTICAL_CLOUD_MAX:.2f}; rank = (cloud asc, |doy-290| asc, "
            "event_id asc); Phase H geometric gate applies",
            n_intersecting, len(candidates), len(near))
    # Honest, specific failure reason.
    reason_bits = [
        f"no eligible event after gates: {len(strict)} full-cover and "
        f"{len(near)} near-full (>={NEAR_FULL_NOMINAL_MIN:.2f}) autumn "
        f"events; scene cloud ceiling {OPTICAL_CLOUD_MAX:.2f}"]
    if not near.empty:
        reason_bits.append(
            f"near-full events all cloudy; min cloud "
            f"{float(near['cloud_fraction'].astype(float).min()):.3f}")
    else:
        partials = candidates[
            (candidates["coverage"] != FULL_COVER)
            & candidates["coverage_fraction"].notna()]
        if not partials.empty:
            reason_bits.append(
                "best nominal frame cover for a PARTIAL autumn event "
                f"{float(partials['coverage_fraction'].astype(float).max()):.4f} < "
                f"{NEAR_FULL_NOMINAL_MIN:.2f}")
    if not strict.empty:
        reason_bits.append(
            "full-cover events all cloudy; min cloud "
            f"{float(strict['cloud_fraction'].astype(float).min()):.3f}")
    return (SensorYearStatus.NO_ELIGIBLE_EVENT,
            {"reason": "; ".join(reason_bits),
             "n_intersecting_events": int(n_intersecting),
             "n_autumn_events": int(len(candidates)),
             "n_full_cover_autumn_events": int(len(strict)),
             "n_near_full_autumn_events": int(len(near)),
             "min_autumn_cloud_fraction":
                 float(candidates["cloud_fraction"].astype(float).min())})


def select_s1_pass(
    scenes: pd.DataFrame, pass_direction: str,
) -> tuple[SensorYearStatus, dict[str, object]]:
    """Select one S1 IW dual-pol scene for a fixed pass within autumn.

    Rank key: |doy - 290| asc, event_id asc. ASC/DESC are never mixed.
    """
    if scenes.empty:
        return (SensorYearStatus.NO_SCENE,
                {"reason": f"no {pass_direction} S1 scene in the census"})
    need = {"season_tag", "pass", "instrument_mode", "polarization",
            "doy", "event_id"}
    missing = need - set(scenes.columns)
    if missing:
        raise SelectionError(f"s1 scenes missing columns: {sorted(missing)}")
    pool = scenes[
        (scenes["pass"] == pass_direction)
        & (scenes["season_tag"] == AUTUMN_TAG)
        & (scenes["instrument_mode"] == S1_IW)
        & (scenes["polarization"].isin(S1_DUAL_POL_TOKENS))].copy()
    if pool.empty:
        return (SensorYearStatus.NO_ELIGIBLE_EVENT,
                {"reason": (
                    f"no {pass_direction} IW VV+VH scene in the autumn "
                    f"window DOY {AUTUMN_DOY_START}-{AUTUMN_DOY_END}"),
                 "n_intersecting_scenes": int(len(scenes))})
    ranked = _rank(pool, by_cloud=False)
    pick = ranked.iloc[0]
    detail = {
        "reason": (
            f"predeclared policy: {pass_direction} IW GRD VV+VH, autumn "
            f"DOY {AUTUMN_DOY_START}-{AUTUMN_DOY_END}; rank = (|doy-290| "
            "asc, event_id asc); passes never fused"),
        "coverage_tier": "S1_ACTUAL_FOOTPRINT",
        "selection_rank_of_pool": f"1 of {len(ranked)} eligible",
        "n_intersecting_scenes": int(len(scenes)),
        "n_eligible_after_gates": int(len(ranked)),
    }
    return SensorYearStatus.SELECTED, {"event": _event_dict(pick), **detail}


def _event_dict(row: pd.Series) -> dict[str, object]:
    out: dict[str, object] = {}
    for key in (
        "event_id", "sensor", "utc", "doy", "season_tag", "coverage",
        "coverage_tier", "coverage_basis", "coverage_fraction",
        "cloud_fraction", "pass", "relative_orbit",
        "platform", "instrument_mode", "polarization", "scene_ids",
        "product_ids", "mgrs_tiles", "member_scene_count", "wrs_path",
        "wrs_row", "l7_era", "spacecraft"):
        if key in row.index:
            value = row[key]
            if pd.isna(value):
                value = None
            elif hasattr(value, "item"):
                value = value.item()
            out[key] = value
    return out


POLICY_DOC: Final[dict[str, object]] = {
    "policy": "PILOT_EVENT_SELECTION_V1",
    "phenology_window": {
        "tag": AUTUMN_TAG,
        "doy_start": AUTUMN_DOY_START,
        "doy_end": AUTUMN_DOY_END,
        "target_doy": TARGET_DOY},
    "optical": {
        "cloud_metadata_field": (
            "Landsat CLOUD_COVER / S2 max member-granule cloudy_pixel_percent"),
        "cloud_ceiling": OPTICAL_CLOUD_MAX,
        "rank": ["cloud_fraction asc", "|doy-290| asc", "event_id asc"],
        "cross_date_mosaic": "FORBIDDEN",
        "s2_composite": "same-datatake ordered tile mosaic only",
        "landsat_composite": "single source scene; path/row retained",
        "coverage_tiers": {
            TIER_STRICT: {
                "coverage_required": FULL_COVER,
                "coverage_basis": BASIS_LANDSAT_FULL},
            TIER_NEAR_FULL: {
                "applies_to": "landsat single-scene slots only",
                "trigger": (
                    "only when no strict-full cloud-eligible autumn scene "
                    "exists for the cell/sensor/year"),
                "min_nominal_frame_cover_fraction": NEAR_FULL_NOMINAL_MIN,
                "fraction_basis": (
                    "intersection_area / cell_polygon_area (EPSG:4326) "
                    "against wrs2_china_coast_v0_1 nominal WRS-2 frames"),
                "coverage_basis_token": BASIS_LANDSAT_NEAR_FULL,
                "post_export_gate": {
                    "phase": "H",
                    "geometric_valid_fraction_min":
                        POSTEXPORT_GEOMETRIC_VALID_MIN,
                    "measure": (
                        "share of landed export-grid pixels with QA_PIXEL "
                        "fill bit clear"),
                    "on_fail": (
                        "product marked GEOMETRY_FAIL and excluded from "
                        "registered cell products")},
            }},
        "tier_preference": "strict before near-full; never mixed",
    },
    "sentinel2_coverage": {
        "basis": BASIS_S2_UNION,
        "near_full_tolerance": "NOT_APPLIED",
        "rule": (
            "an event qualifies only when the union of its same-datatake "
            "member MGRS tile polygons covers the cell; different dates "
            "are never merged")},
    "sentinel1": {
        "mode": "IW", "polarization": "VV+VH",
        "polarization_tokens_accepted": sorted(S1_DUAL_POL_TOKENS),
        "coverage_basis": "S1_GRD_ACTUAL_GEE_FOOTPRINT",
        "passes": list(PASSES), "pass_fusion": "FORBIDDEN",
        "log_transform": "identity (GEE S1_GRD is already sigma0 dB)",
        "rank": ["|doy-290| asc", "event_id asc"]},
    "label_independent": (
        "selection never uses label overlap, label presence, or model "
        "performance of any kind"),
}

__all__ = [
    "AUTUMN_DOY_END",
    "AUTUMN_DOY_START",
    "AUTUMN_TAG",
    "BASIS_LANDSAT_FULL",
    "BASIS_LANDSAT_NEAR_FULL",
    "BASIS_S2_UNION",
    "FULL_COVER",
    "NEAR_FULL_NOMINAL_MIN",
    "OPTICAL_CLOUD_MAX",
    "PASSES",
    "POLICY_DOC",
    "PARTIAL_COVER",
    "POSTEXPORT_GEOMETRIC_VALID_MIN",
    "S1_DUAL_POL",
    "S1_DUAL_POL_TOKENS",
    "S1_IW",
    "TIER_NEAR_FULL",
    "TIER_STRICT",
    "SelectionError",
    "TARGET_DOY",
    "optical_candidates",
    "select_optical",
    "select_s1_pass",
]
