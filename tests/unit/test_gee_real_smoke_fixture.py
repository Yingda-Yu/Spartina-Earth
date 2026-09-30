"""Offline regression for the frozen real GEE catalog smoke (Issue #6).

The first *real* Earth Engine catalog retrieval over HZB_TECH_SMOKE_V1
(2020-09-01..2020-11-01, target DOY 275) is frozen under
tests/fixtures/gee/real_smoke_catalog_v1.json. This module replays the
deterministic selection code on those 30 candidate rows WITHOUT any network
access or Earth Engine credentials and asserts:

* per-sensor candidate / eligible / selected counts;
* the exact selected scene ids and ranks (S2 T51RUP, S1 ascending orbit 69);
* the Sentinel-1 pass split (15 ascending, 0 descending -- passes ranked
  independently, never merged);
* the zero Landsat-8 eligibility that closes the export gate;
* the recomputed catalog/selection SHA-256 fingerprints match the frozen
  values, so a silent change to the QA counts or ranking rules is detected.

The frozen snapshot is evidence, not a mock: every scene id, UTC timestamp
and count came from a real authenticated retrieval on 2026-09-30.
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
    "real_smoke_catalog_v1.json")
DRIVER_PATH = REPO_ROOT / "scripts" / "data" / "gee" / (
    "real_catalog_smoke.py")

FROZEN_CATALOG_FP = (
    "ddf6f158eff85dbc74b7be5f2780319da44cc2910f3ca930917bbc7df6692f28")
FROZEN_SELECTION_FP = (
    "b659c68b0018b09328b61a5cbaf64ad21a282594e81834173815db7bdc9d4f4e")
SENSORS = ("landsat8", "sentinel1", "sentinel2")

S1_SELECTED = (
    "S1A_IW_GRDH_1SDV_20201002T100300_20201002T100325_034616_0407DA_822F")
S2_SELECTED = "20200905T023549_20200905T024731_T51RUP"


@pytest.fixture(scope="module")
def fixture() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def driver() -> Any:
    """Load the real smoke driver without initializing Earth Engine.

    All ``ee`` imports inside the GEE package are lazy (inside functions),
    so the selection helpers work on environments without earthengine-api.
    """
    spec = importlib.util.spec_from_file_location(
        "real_catalog_smoke_offline_fixture", DRIVER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def replayed(fixture: dict[str, Any], driver: Any) -> dict[str, list[dict[str, Any]]]:
    """Re-run the driver ranking on de-annotated copies of the frozen rows."""
    record = fixture["policy"]
    policy = driver.SingleScenePolicy(
        min_footprint_coverage=record["min_footprint_coverage"],
        min_valid_pixel_fraction=record["min_valid_pixel_fraction"],
        max_cloud_fraction=record["max_cloud_fraction"],
        target_doy=record["target_doy"])
    rows_by_sensor: dict[str, list[dict[str, Any]]] = {
        sensor: [] for sensor in SENSORS}
    for row in fixture["candidate_rows"]:
        clean = dict(row)
        # Reset every annotation the ranking stage derives.
        clean["policy_eligible"] = False
        clean["selected"] = False
        clean["selected_orbit"] = driver.NOT_APPLICABLE
        clean["selection_rank"] = None
        clean["selection_score"] = None
        clean["selection_reason"] = None
        clean["rejection_reasons"] = []
        rows_by_sensor[str(row["sensor"])].append(clean)
    for sensor in ("landsat8", "sentinel2"):
        driver._rank_optical(rows_by_sensor[sensor], policy)
    driver._rank_sar(rows_by_sensor["sentinel1"], policy)
    return rows_by_sensor


def test_fixture_identity_fields(fixture: dict[str, Any]) -> None:
    assert fixture["fixture_version"] == "gee_real_smoke_catalog_v1"
    assert fixture["roi_id"] == "HZB_TECH_SMOKE_V1"
    assert fixture["roi_crs_epsg"] == 4326
    assert fixture["project_id"] == "project-795fc21c-e217-47f3-adb"
    assert fixture["window"] == {
        "start_utc": "2020-09-01T00:00:00Z",
        "end_utc": "2020-11-01T00:00:00Z",
        "target_doy": 275,
    }
    assert fixture["collections"] == {
        "landsat8": "LANDSAT/LC08/C02/T1_L2",
        "sentinel1": "COPERNICUS/S1_GRD",
        "sentinel2": "COPERNICUS/S2_SR_HARMONIZED",
    }
    assert len(fixture["candidate_rows"]) == 30


def test_replayed_counts(
    fixture: dict[str, Any],
    replayed: dict[str, list[dict[str, Any]]],
) -> None:
    expected = {"landsat8": (3, 0, 0),
                "sentinel1": (15, 15, 1),
                "sentinel2": (12, 5, 1)}
    for sensor, (n_cand, n_elig, n_sel) in expected.items():
        rows = replayed[sensor]
        assert len(rows) == n_cand
        assert sum(1 for r in rows if r["policy_eligible"]) == n_elig
        assert sum(1 for r in rows if r["selected"]) == n_sel
    # The frozen summary block must agree with the replay.
    for sensor, (n_cand, n_elig, n_sel) in expected.items():
        assert fixture["counts"][sensor] == {
            "candidate_count": n_cand,
            "eligible_count": n_elig,
            "selected_count": n_sel,
        }


def test_landsat8_zero_eligible_closes_export_gate(
    replayed: dict[str, list[dict[str, Any]]],
) -> None:
    """All three L8 scenes exceed the predeclared 0.30 ROI cloud threshold.

    This is the real 2020 autumn cloud situation, not a code defect: the
    export gate must refuse (NO_ELIGIBLE_LANDSAT8_SCENE) rather than widen
    the window or relax the policy after inspection.
    """
    rows = replayed["landsat8"]
    assert {r["scene_id"] for r in rows} == {
        "LC08_118039_20200901", "LC08_118039_20200917",
        "LC08_118039_20201003"}
    assert not any(r["policy_eligible"] for r in rows)
    assert not any(r["selected"] for r in rows)
    for row in rows:
        assert "high_roi_cloud_fraction" in row["rejection_reasons"]
        assert row["roi_cloud_fraction"] > 0.30
    best = min(rows, key=lambda r: r["roi_cloud_fraction"])
    assert best["scene_id"] == "LC08_118039_20200901"
    assert best["roi_cloud_fraction"] == pytest.approx(0.7832637502, abs=1e-9)


def test_sentinel2_selection(replayed: dict[str, list[dict[str, Any]]]) -> None:
    rows = sorted(
        (r for r in replayed["sentinel2"] if r["policy_eligible"]),
        key=lambda r: r["selection_rank"])
    assert [r["scene_id"] for r in rows] == [
        "20200905T023549_20200905T024731_T51RUP",
        "20201030T023831_20201030T023833_T51RUP",
        "20201010T023631_20201010T024205_T51RUP",
        "20200930T023551_20200930T023909_T51RUP",
        "20200925T023549_20200925T024420_T51RUP",
    ]
    assert [r["selection_rank"] for r in rows] == [1, 2, 3, 4, 5]
    chosen = rows[0]
    assert chosen["selected"] is True
    assert chosen["mgrs_tile"] == "51RUP"
    assert chosen["roi_cloud_fraction"] == 0.0
    assert chosen["cloud_probability_available"] is True
    assert chosen["acquisition_utc"] == "2020-09-05T02:49:21.773000+00:00"
    assert chosen["product_id"] == (
        "S2B_MSIL2A_20200905T023549_N0214_R089_T51RUP_20200905T053156")


def test_sentinel1_passes_ranked_separately(
    fixture: dict[str, Any],
    replayed: dict[str, list[dict[str, Any]]],
) -> None:
    rows = replayed["sentinel1"]
    ascending = [r for r in rows if r["orbit_direction"] == "ASCENDING"]
    descending = [r for r in rows if r["orbit_direction"] == "DESCENDING"]
    assert len(ascending) == 15
    assert len(descending) == 0
    assert all(r["instrument_mode"] == "IW" for r in rows)
    assert all(r["vv_available"] and r["vh_available"] for r in rows)
    picks = [r for r in rows if r["selected"]]
    assert len(picks) == 1
    chosen = picks[0]
    assert chosen["scene_id"] == S1_SELECTED
    assert chosen["selected_orbit"] == "ASCENDING"
    assert chosen["selection_rank"] == 1
    assert chosen["relative_orbit_number"] == 69
    assert chosen["acquisition_utc"] == "2020-10-02T10:03:00+00:00"
    # The ingestion pipeline really returned no productIdentifier.
    assert chosen["product_id"] == "MISSING"
    # Frozen pass breakdown mirrors the replay.
    assert fixture["s1_pass_breakdown"] == {
        "ASCENDING": {
            "candidate_count": 15, "eligible_count": 15,
            "selected_scene_id": S1_SELECTED},
        "DESCENDING": {
            "candidate_count": 0, "eligible_count": 0,
            "selected_scene_id": None},
    }


def test_catalog_fingerprint_reproduces(
    fixture: dict[str, Any],
    driver: Any,
    replayed: dict[str, list[dict[str, Any]]],
) -> None:
    ordered = [row for sensor in SENSORS for row in replayed[sensor]]
    fingerprint = driver.canonical_fingerprint(
        driver._fingerprint_payload(ordered))
    assert fingerprint == fixture["catalog_fingerprint_sha256"]
    assert fingerprint == FROZEN_CATALOG_FP


def test_selection_fingerprint_reproduces(
    fixture: dict[str, Any],
    driver: Any,
    replayed: dict[str, list[dict[str, Any]]],
) -> None:
    record = fixture["policy"]
    policy = driver.SingleScenePolicy(
        min_footprint_coverage=record["min_footprint_coverage"],
        min_valid_pixel_fraction=record["min_valid_pixel_fraction"],
        max_cloud_fraction=record["max_cloud_fraction"],
        target_doy=record["target_doy"])
    fingerprint = driver.canonical_fingerprint(
        driver._selection_payload(replayed, policy))
    assert fingerprint == fixture["selection_fingerprint_sha256"]
    assert fingerprint == FROZEN_SELECTION_FP


def test_roi_geometry_hash(fixture: dict[str, Any], driver: Any) -> None:
    assert driver.canonical_fingerprint(fixture["roi_geometry"]) == (
        fixture["roi_geometry_sha256"])
    assert fixture["roi_geometry_sha256"] == (
        "b72d475976e4ff3e775defb467ec4a62f880a5df1bc42aa0c0a882be7d9da43f")
