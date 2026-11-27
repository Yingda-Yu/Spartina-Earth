"""Unit tests for the Issue #19 deterministic event-selection policy."""

from __future__ import annotations

import pandas as pd
import pytest

from spartina.data.national.pilot_events import (
    AUTUMN_TAG,
    FULL_COVER,
    NEAR_FULL_NOMINAL_MIN,
    OPTICAL_CLOUD_MAX,
    PARTIAL_COVER,
    TIER_NEAR_FULL,
    TIER_STRICT,
    SelectionError,
    optical_candidates,
    select_optical,
    select_s1_pass,
)

COLS = ["event_id", "season_tag", "coverage", "doy", "cloud_fraction",
        "coverage_fraction", "geometry_basis"]


def optical_row(event_id: str, *, doy: int, cloud: float,
                coverage: str = FULL_COVER, fraction: float | None = 1.0,
                basis: str = "WRS2_NOMINAL_FRAME",
                season: str = AUTUMN_TAG) -> dict[str, object]:
    return {"event_id": event_id, "season_tag": season, "coverage": coverage,
            "doy": doy, "cloud_fraction": cloud,
            "coverage_fraction": fraction, "geometry_basis": basis}


def test_empty_and_no_scene() -> None:
    status, detail = select_optical(pd.DataFrame(columns=COLS))
    assert status.value == "NO_SCENE"
    assert "no intersecting scene" in detail["reason"]


def test_summer_only_is_no_eligible_event() -> None:
    frame = pd.DataFrame([
        optical_row("E1", doy=200, cloud=0.01, season="SUMMER")])
    status, detail = select_optical(frame)
    assert status.value == "NO_ELIGIBLE_EVENT"
    assert detail["n_intersecting_events"] == 1


def test_strict_full_clear_wins_and_ranks_by_cloud_then_doy() -> None:
    frame = pd.DataFrame([
        optical_row("CLOUDY", doy=290, cloud=0.29),
        optical_row("CLEAR_LATE", doy=310, cloud=0.05),
        optical_row("CLEAR_NEAR", doy=295, cloud=0.05)])
    status, detail = select_optical(frame)
    assert status.name == "SELECTED"
    assert detail["event"]["event_id"] == "CLEAR_NEAR"
    assert detail["coverage_tier"] == TIER_STRICT


def test_cloud_ceiling_gate_is_inclusive_at_threshold() -> None:
    frame = pd.DataFrame([
        optical_row("AT", doy=290, cloud=OPTICAL_CLOUD_MAX)])
    status, _ = select_optical(frame)
    assert status.name == "SELECTED"


def test_all_cloudy_full_events_fail_with_min_cloud() -> None:
    frame = pd.DataFrame([
        optical_row("C1", doy=290, cloud=0.5),
        optical_row("C2", doy=300, cloud=0.8)])
    status, detail = select_optical(frame)
    assert status.value == "NO_ELIGIBLE_EVENT"
    assert detail["n_full_cover_autumn_events"] == 2
    assert detail["min_autumn_cloud_fraction"] == pytest.approx(0.5)
    assert "0.500" in detail["reason"]


def test_near_full_used_when_no_strict_clear() -> None:
    frame = pd.DataFrame([
        optical_row("FULL_CLOUDY", doy=290, cloud=0.9),
        optical_row("EDGE_CLEAR", doy=302, cloud=0.27,
                    coverage=PARTIAL_COVER, fraction=0.9427)])
    status, detail = select_optical(frame)
    assert status.name == "SELECTED"
    assert detail["event"]["event_id"] == "EDGE_CLEAR"
    assert detail["coverage_tier"] == TIER_NEAR_FULL
    assert detail["nominal_coverage_fraction"] == pytest.approx(0.9427)
    gate = detail["post_export_gate"]
    assert gate["min_required"] >= NEAR_FULL_NOMINAL_MIN
    assert gate["phase"] == "H"


def test_strict_preferred_over_near_full_even_if_near_cloud_lower() -> None:
    frame = pd.DataFrame([
        optical_row("STRICT_OK", doy=320, cloud=0.29),
        optical_row("EDGE", doy=290, cloud=0.01,
                    coverage=PARTIAL_COVER, fraction=0.97)])
    status, detail = select_optical(frame)
    assert status.name == "SELECTED"
    assert detail["event"]["event_id"] == "STRICT_OK"
    assert detail["coverage_tier"] == TIER_STRICT


def test_partial_below_threshold_rejected_with_best_fraction() -> None:
    frame = pd.DataFrame([
        optical_row("FULL_CLOUDY", doy=290, cloud=0.9),
        optical_row("SMALL_EDGE", doy=290, cloud=0.05,
                    coverage=PARTIAL_COVER, fraction=0.166)])
    status, detail = select_optical(frame)
    assert status.value == "NO_ELIGIBLE_EVENT"
    assert detail["n_near_full_autumn_events"] == 0
    assert "0.1660" in detail["reason"]


def test_near_full_requires_wrs_nominal_basis() -> None:
    # Actual-footprint / non-WRS PARTIAL rows never enter the tolerance.
    frame = pd.DataFrame([
        optical_row("EXT", doy=290, cloud=0.05, coverage=PARTIAL_COVER,
                    fraction=0.95, basis="L7_EXTENDED_ACTUAL_FOOTPRINT")])
    status, detail = select_optical(frame)
    assert status.value == "NO_ELIGIBLE_EVENT"
    assert detail["n_near_full_autumn_events"] == 0


def test_near_full_cloudy_is_rejected_with_near_min_cloud() -> None:
    frame = pd.DataFrame([
        optical_row("EDGE_CLOUDY", doy=290, cloud=0.42,
                    coverage=PARTIAL_COVER, fraction=0.9427)])
    status, detail = select_optical(frame)
    assert status.value == "NO_ELIGIBLE_EVENT"
    assert detail["n_near_full_autumn_events"] == 1
    assert "near-full events all cloudy" in detail["reason"]


def test_missing_columns_raise() -> None:
    with pytest.raises(SelectionError, match="missing columns"):
        optical_candidates(pd.DataFrame({"season_tag": [AUTUMN_TAG]}))


S1_COLS = ["event_id", "season_tag", "doy", "pass", "instrument_mode",
           "polarization"]


def s1_row(event_id: str, *, doy: int, pass_dir: str,
           pol: str = "VV|VH", mode: str = "IW") -> dict[str, object]:
    return {"event_id": event_id, "season_tag": AUTUMN_TAG, "doy": doy,
            "pass": pass_dir, "instrument_mode": mode,
            "polarization": pol}


def test_s1_empty_no_scene() -> None:
    status, detail = select_s1_pass(pd.DataFrame(columns=S1_COLS), "ASC")
    assert status.value == "NO_SCENE"
    assert "ASC" in detail["reason"]


def test_s1_pass_and_dualpol_filters() -> None:
    frame = pd.DataFrame([
        s1_row("ASC_OK", doy=290, pass_dir="ASC"),
        s1_row("DESC_OK", doy=280, pass_dir="DESC"),
        s1_row("ASC_EW", doy=290, pass_dir="ASC", mode="EW"),
        s1_row("ASC_HH", doy=290, pass_dir="ASC", pol="HH")])
    status, detail = select_s1_pass(frame, "ASC")
    assert status.name == "SELECTED"
    assert detail["event"]["event_id"] == "ASC_OK"
    status2, _ = select_s1_pass(frame, "DESC")
    assert status2.name == "SELECTED"


def test_s1_accepts_both_dual_pol_tokens() -> None:
    frame = pd.DataFrame([s1_row("V0", doy=290, pass_dir="DESC",
                                 pol="VH|VV")])
    status, detail = select_s1_pass(frame, "DESC")
    assert status.name == "SELECTED"
    assert detail["event"]["event_id"] == "V0"


def test_s1_ranks_by_doy_and_never_fuses() -> None:
    frame = pd.DataFrame([
        s1_row("FAR", doy=320, pass_dir="ASC"),
        s1_row("NEAR", doy=295, pass_dir="ASC")])
    status, detail = select_s1_pass(frame, "ASC")
    assert status.name == "SELECTED"
    assert detail["event"]["event_id"] == "NEAR"
    missing = pd.DataFrame([s1_row("D1", doy=290, pass_dir="DESC")])
    status2, detail2 = select_s1_pass(missing, "ASC")
    assert status2.value == "NO_ELIGIBLE_EVENT"
    assert "passes never fused" not in detail2["reason"]
    assert detail2["n_intersecting_scenes"] == 1


def test_s1_missing_columns_raise() -> None:
    with pytest.raises(SelectionError, match="missing columns"):
        select_s1_pass(pd.DataFrame({"doy": [1]}), "ASC")
