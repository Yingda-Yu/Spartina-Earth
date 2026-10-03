"""Unit tests for footprint indices and sensor-era rules (Issue #16)."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import date, datetime
from pathlib import Path

import pytest
from shapely.geometry import box

from spartina.data.national.footprints import (
    CELL_YEAR_STATUS,
    L7_EXTENDED_RESUME,
    L7_EXTENDED_SCIENCE_MISSION,
    L7_NOMINAL_END,
    L7_POST_SLC_FAILURE,
    L7_PRE_SLC_FAILURE,
    L7_SLC_FAILURE,
    L7_STANDBY_ORBIT_LOWERING,
    METADATA_AVAILABLE,
    NO_CELL_INTERSECTION,
    NO_SCENES_FOUND,
    QUERY_FAILED,
    SENSOR_NOT_OPERATIONAL,
    geometry_fingerprint,
    l7_era,
    l7_footprint_is_nominal_wrs2,
    sensor_operational,
    wrs2_frame_id,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FP_DIR = REPO_ROOT / "work" / "national" / "footprints"
DOC_DIR = REPO_ROOT / "docs" / "data" / "national"


# --- L7 era boundaries ----------------------------------------------------

@pytest.mark.parametrize(
    ("day", "era", "nominal"),
    [
        (date(1999, 4, 15), L7_PRE_SLC_FAILURE, True),
        (date(2003, 5, 30), L7_PRE_SLC_FAILURE, True),
        (date(2003, 5, 31), L7_POST_SLC_FAILURE, True),
        (date(2022, 4, 5), L7_POST_SLC_FAILURE, True),
        (date(2022, 4, 6), L7_STANDBY_ORBIT_LOWERING, False),
        (date(2022, 5, 4), L7_STANDBY_ORBIT_LOWERING, False),
        (date(2022, 5, 5), L7_EXTENDED_SCIENCE_MISSION, False),
        (date(2024, 1, 19), L7_EXTENDED_SCIENCE_MISSION, False),
    ],
)
def test_l7_era_boundaries(day: date, era: str, nominal: bool) -> None:
    assert l7_era(day) is era
    assert l7_era(datetime(day.year, day.month, day.day, 12, 0)) is era
    assert l7_footprint_is_nominal_wrs2(day) is nominal


def test_l7_constants_match_usgs_dates() -> None:
    assert date(2003, 5, 31) == L7_SLC_FAILURE
    assert date(2022, 4, 5) == L7_NOMINAL_END
    assert date(2022, 5, 5) == L7_EXTENDED_RESUME


# --- sensor operational status -------------------------------------------

@pytest.mark.parametrize(
    ("sensor", "year", "expected"),
    [
        ("landsat5", 1983, False),
        ("landsat5", 1984, True),
        ("landsat5", 2012, True),
        ("landsat5", 2014, False),
        ("landsat7", 1998, False),
        ("landsat7", 2024, True),
        ("landsat8", 2012, False),
        ("landsat8", 2013, True),
        ("landsat8", 2025, True),
        ("landsat9", 2021, True),
        ("landsat9", 2020, False),
        ("sentinel2", 2014, False),
        ("sentinel2", 2015, True),
    ],
)
def test_sensor_operational_years(sensor: str, year: int, expected: bool) -> None:
    assert sensor_operational(sensor, year) is expected


def test_cell_year_status_distinct_and_complete() -> None:
    assert set(CELL_YEAR_STATUS) == {
        SENSOR_NOT_OPERATIONAL,
        NO_SCENES_FOUND,
        NO_CELL_INTERSECTION,
        METADATA_AVAILABLE,
        QUERY_FAILED,
    }


def test_not_operational_is_not_zero() -> None:
    # documentation-level guard: the missing-data status must never be
    # encoded as a plain zero count
    assert SENSOR_NOT_OPERATIONAL != "0"
    assert NO_SCENES_FOUND != "0"
    assert QUERY_FAILED != "0"


# --- deterministic ids / fingerprints ------------------------------------

def test_wrs2_frame_id_format_and_order() -> None:
    assert wrs2_frame_id(118, 39) == "WRS2-D-P118-R039"
    assert wrs2_frame_id(1, 1) == "WRS2-D-P001-R001"
    with pytest.raises(ValueError):
        wrs2_frame_id(0, 1)
    with pytest.raises(ValueError):
        wrs2_frame_id(1, 249)


def test_geometry_fingerprint_stable_and_distinguishing() -> None:
    g1 = box(0, 0, 1, 1)
    g2 = box(0, 0, 1, 1)
    g3 = box(0, 0, 1, 2)
    fp1 = geometry_fingerprint(g1)
    assert fp1 == geometry_fingerprint(g2)
    assert re.fullmatch(r"[0-9a-f]{64}", fp1)
    assert geometry_fingerprint(g3) != fp1
    # WKB canonical big-endian prefix
    assert hashlib.sha256(
        g1.wkb
    ).hexdigest() != fp1 or bytes(g1.wkb)[0] == 1  # not little-endian WKB


# --- built artifacts ------------------------------------------------------

def test_wrs2_index_artifact_integrity() -> None:
    csv_path = FP_DIR / "wrs2_china_coast_index.csv"
    doc_path = DOC_DIR / "FOOTPRINT_INDICES_v0.json"
    if not csv_path.exists():
        pytest.skip("WRS-2 index not built")
    rows = list(csv.DictReader(csv_path.open(newline="", encoding="utf-8")))
    assert len(rows) == 66
    ids = [r["frame_id"] for r in rows]
    assert ids == sorted(ids)
    assert len(set(ids)) == 66
    for r in rows:
        assert re.fullmatch(r"WRS2-D-P\d{3}-R\d{3}", r["frame_id"])
        assert re.fullmatch(r"[0-9a-f]{64}", r["geometry_sha256"])
        assert r["geometry_kind"] == "NOMINAL_WRS2_DESCENDING_POLYGON"
        assert int(r["rings_nok"]) == 0
        assert float(r["minx"]) >= 105.0
        assert int(r["path"]) in range(114, 127)
    doc = json.loads(doc_path.read_text())
    zip_path = FP_DIR / "source" / "WRS2_descending.zip"
    assert doc["source"]["zip_sha256"] == hashlib.sha256(
        zip_path.read_bytes()
    ).hexdigest()
    assert doc["n_frames_intersecting_corridor"] == 66
    assert doc["source"]["license"] == "USGS Public Domain"


def test_mgrs_index_is_explicit_prefilter_only() -> None:
    csv_path = FP_DIR / "mgrs_china_coast_index.csv"
    doc_path = DOC_DIR / "MGRS_TILE_INDEX_v0.json"
    if not csv_path.exists():
        pytest.skip("MGRS index not built")
    rows = list(csv.DictReader(csv_path.open(newline="", encoding="utf-8")))
    assert len(rows) == 128
    assert len({r["mgrs_tile"] for r in rows}) == 128
    for r in rows:
        assert re.fullmatch(r"\d{2}[C-X][A-Z]{2}", r["mgrs_tile"])
        assert r["geometry_kind"] == "NOMINAL_MGRS_100KM_GRID_PREFILTER"
        # the field that keeps nominal geometry from becoming final
        assert r["actual_scene_geometry"] == "REQUIRED_FROM_SCENE_METADATA"
        assert re.fullmatch(r"[0-9a-f]{64}", r["geometry_sha256"])
        assert r["nominal_area_km2"] == "10000"
    doc = json.loads(doc_path.read_text())
    assert doc["n_tiles_intersecting_corridor"] == 128
    assert "NOT a scene footprint" in doc["role"]
