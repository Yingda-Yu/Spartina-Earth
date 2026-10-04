"""Real GEE integration tests for the M2.3b-R1 national census audit.

Auto-skip unless genuine credentials AND SPARTINA_GEE_PROJECT are present.
Every test is metadata-only (``.size()`` aggregates, no pixels, no
exports) and the national export guard is installed for the whole module:
touching ``ee.batch.Export`` must raise.

Run:

    pytest -m gee_integration -v -k national_census_r1

Assertions (executed evidence, never skip-as-pass):

* frozen 2026 YTD cutoff: L8/L9 non-empty before 2026-10-03, L7 zero
  after imaging-suspension (2024-01-19), L5 not queried (decommissioned);
* S1 pass-distribution diagnosis token + spot-check CSV consistency,
  plus a live two-cell re-confirmation (Bohai DESC abundant vs southern
  rare) with direct ``filterBounds`` aggregates;
* NE chronic-zero INDEX_MISS cell: direct ``filterBounds`` proves scenes
  exist over a v0 chronic-zero cell;
* v0_1 built products (when present) carry PARTIAL_YEAR 2026 rows.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from shapely.geometry import mapping

from spartina.data.gee import auth
from spartina.data.national.census_join import load_cells
from spartina.data.zhejiang.census import ExportAttempted, install_export_guard

PROJECT_READY = bool(auth.configured_project())

pytestmark = [
    pytest.mark.gee_integration,
    pytest.mark.skipif(
        not auth.credentials_available(),
        reason="GEE credentials not configured; integration test skipped.",
    ),
    pytest.mark.skipif(
        not PROJECT_READY,
        reason="SPARTINA_GEE_PROJECT is unset; real Initialize needs a "
        "Cloud project with Earth Engine enabled.",
    ),
]

REPO_ROOT = Path(__file__).resolve().parents[2]
R1_DIR = REPO_ROOT / "work" / "national" / "census_r1"
CUTS_OFF_UTC = "2026-10-03T00:00:00Z"
CUTOFF_DAY = "2026-10-03"
DOMAIN_BBOX = (105.0, 15.0, 132.0, 43.0)

BOHAI_CELL = "CNA10K-R00415-C00131"  # spot check: ASC 324 / DESC 318
SOUTHERN_CELL = "CNA10K-R00312-C00156"  # Zhejiang-Fujian: ASC 990 / DESC 6
NE_INDEX_MISS_CELL = "CNA10K-R00485-C00204"

S1_TOKEN = "DESCENDING_REGIONALLY_AND_TEMPORALLY_IMBALANCED"


@pytest.fixture(scope="module")
def ee_module():
    auth.initialize()
    import ee  # imported after Initialize path is proven available

    restore = install_export_guard(ee)
    yield ee
    restore()


def _cell_geometry(ee_module, cell_id: str):
    cells_csv = REPO_ROOT / "work" / "national" / "domain" / (
        "cells_china_albers_W10000.csv"
    )
    cells = load_cells(cells_csv)
    selected = cells[cells["cell_id"] == cell_id]
    assert len(selected) == 1, f"cell not found: {cell_id}"
    return ee_module.Geometry(mapping(selected.geometry.iloc[0]))


# --- Part F: export guard ------------------------------------------------


def test_export_guard_blocks_batch_export(ee_module) -> None:
    with pytest.raises(ExportAttempted):
        _ = ee_module.batch.Export.image.toDrive


# --- Part A: 2026 YTD frozen cutoff --------------------------------------


def test_2026_ytd_optical_cutoff(ee_module) -> None:
    bbox = ee_module.Geometry.Rectangle(list(DOMAIN_BBOX), "EPSG:4326", False)

    n_l8 = (
        ee_module.ImageCollection("LANDSAT/LC08/C02/T1_L2")
        .filterBounds(bbox)
        .filterDate("2026-01-01", CUTOFF_DAY)
        .size()
        .getInfo()
    )
    n_l9 = (
        ee_module.ImageCollection("LANDSAT/LC09/C02/T1_L2")
        .filterBounds(bbox)
        .filterDate("2026-01-01", CUTOFF_DAY)
        .size()
        .getInfo()
    )
    assert int(n_l8) > 0
    assert int(n_l9) > 0

    # L7 imaging suspended 2024-01-19: nothing after in T1_L2.
    n_l7_post_suspension = (
        ee_module.ImageCollection("LANDSAT/LE07/C02/T1_L2")
        .filterBounds(bbox)
        .filterDate("2024-01-20", CUTOFF_DAY)
        .size()
        .getInfo()
    )
    assert int(n_l7_post_suspension) == 0

    # L5 decommissioned 2013-06-05: the 2026 query is not even issued.
    n_l5_2026 = (
        ee_module.ImageCollection("LANDSAT/LT05/C02/T1_L2")
        .filterBounds(bbox)
        .filterDate("2026-01-01", CUTOFF_DAY)
        .size()
        .getInfo()
    )
    assert int(n_l5_2026) == 0
    status_path = R1_DIR / "landsat5_2026_status.json"
    assert status_path.exists()
    assert json.loads(status_path.read_text(encoding="utf-8"))["status"] == (
        "SENSOR_NOT_OPERATIONAL"
    )


# --- Part B: S1 pass distribution token + live re-confirmation -----------


def test_s1_audit_token_and_spot_check_files() -> None:
    token_doc = REPO_ROOT / "docs" / "data" / "national" / (
        "S1_PASS_DISTRIBUTION_AUDIT_v0_1.json"
    )
    assert token_doc.exists()
    doc = json.loads(token_doc.read_text(encoding="utf-8"))
    assert doc["diagnosis_token"] == S1_TOKEN

    spots = pd.read_csv(R1_DIR / "s1_spot_checks_v0_1.csv")
    assert len(spots) == 10
    regions = set(spots["region"].astype(str))
    assert regions == {
        "BOHAI",
        "YANGTZE",
        "ZHEJIANG_FUJIAN",
        "PEARL_DELTA",
        "HAINAN",
    }
    bohai = spots[spots["region"] == "BOHAI"]
    southern = spots[spots["region"].isin(
        ["YANGTZE", "ZHEJIANG_FUJIAN", "PEARL_DELTA", "HAINAN"]
    )]
    # Bohai: DESC abundant (~50% share); southern regions: DESC < 5%.
    bohai_desc_share = (bohai["DESC"].sum()
                        / bohai[["ASC", "DESC"]].sum().sum())
    southern_desc_share = (
        southern["DESC"].sum() / southern[["ASC", "DESC"]].sum().sum()
    )
    assert bohai_desc_share > 0.30
    assert southern_desc_share < 0.05

    # Complete-era pass summary: 2014 partial era + 2015-2025 full years
    # + 2026 YTD (PARTIAL_YEAR), per Issue #16 completeness note.
    assert "funnel_totals_2014_partial" in doc
    assert "funnel_totals_2015_2025" in doc
    assert "funnel_totals_2026_ytd" in doc
    era = doc["era_summary"]
    assert era["2014_partial"]["label"].startswith("PARTIAL_ERA")
    assert era["2014_partial"]["raw_bbox_DESC"] > 0
    assert era["2014_partial"]["d_level_scenes"] == 0
    assert era["2015_2025_full"]["d_level_DESC"] > 0
    assert era["2026_ytd"]["label"] == "PARTIAL_YEAR"
    assert era["2026_ytd"]["annualized"] is False
    # National DESC demonstrably exists; the token must not claim absence.
    d_level = doc["funnel_totals_2015_2025"]["D_CELL_IW_VVVH"]
    assert d_level["DESC"] > 1000
    assert "ABSENT" not in doc["diagnosis_token"]


def test_s1_pass_region_structure_live(ee_module) -> None:
    """Direct filterBounds re-confirmation at one Bohai + one southern cell."""
    bohai = _cell_geometry(ee_module, BOHAI_CELL)
    south = _cell_geometry(ee_module, SOUTHERN_CELL)

    def counts(geom) -> tuple[int, int]:
        base = (
            ee_module.ImageCollection("COPERNICUS/S1_GRD")
            .filterBounds(geom)
            .filter(ee_module.Filter.eq("instrumentMode", "IW"))
            .filter(ee_module.Filter.listContains(
                "transmitterReceiverPolarisation", "VV"))
            .filterDate("2014-10-01", CUTOFF_DAY)
        )
        asc = base.filter(
            ee_module.Filter.eq("orbitProperties_pass", "ASCENDING")
        ).size().getInfo()
        desc = base.filter(
            ee_module.Filter.eq("orbitProperties_pass", "DESCENDING")
        ).size().getInfo()
        return int(asc), int(desc)

    b_asc, b_desc = counts(bohai)
    s_asc, s_desc = counts(south)
    assert b_desc > 100
    assert b_desc / max(b_asc + b_desc, 1) > 0.30
    assert s_asc > 100
    assert s_desc / max(s_asc + s_desc, 1) < 0.05


# --- Part C: NE chronic-zero INDEX_MISS live evidence --------------------


def test_ne_index_miss_cell_live(ee_module) -> None:
    audit_csv = REPO_ROOT / "datasets" / "manifests" / (
        "china_ne_chronic_zero_audit_v0.csv"
    )
    audit = pd.read_csv(audit_csv)
    row = audit[audit["cell_id"] == NE_INDEX_MISS_CELL]
    assert len(row) == 1
    assert str(row.iloc[0]["classification"]) == "INDEX_MISS"

    geom = _cell_geometry(ee_module, NE_INDEX_MISS_CELL)
    n_l8 = (
        ee_module.ImageCollection("LANDSAT/LC08/C02/T1_L2")
        .filterBounds(geom)
        .filterDate("2015-01-01", "2026-01-01")
        .size()
        .getInfo()
    )
    n_s2 = (
        ee_module.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(geom)
        .filterDate("2015-01-01", "2026-01-01")
        .size()
        .getInfo()
    )
    assert int(n_l8) > 0
    assert int(n_s2) > 0


# --- Part E: built v0_1 products -----------------------------------------


@pytest.mark.skipif(
    not (R1_DIR / "products" / "china_eo_availability_v0_1.csv").exists(),
    reason="v0_1 products not built locally; run build_cell_event_census_v0_1.py",
)
def test_v01_products_partial_year_semantics() -> None:
    products = R1_DIR / "products"
    availability = pd.read_csv(
        products / "china_eo_availability_v0_1.csv", low_memory=False
    )
    rows_2026 = availability[availability["year"] == 2026]
    assert (rows_2026["year_status"] == "PARTIAL_YEAR").all()
    assert set(rows_2026["census_cutoff_utc"].dropna()) == {CUTS_OFF_UTC}
    l5_2026 = rows_2026[rows_2026["sensor"] == "landsat5"]
    assert (l5_2026["status"] == "SENSOR_NOT_OPERATIONAL").all()
    l8_2026 = rows_2026[rows_2026["sensor"] == "landsat8"]
    assert (l8_2026["n_events"] > 0).any()

    gaps = pd.read_csv(products / "china_eo_data_gap_matrix_v0_1.csv")
    assert "2026" not in " ".join(gaps["zero_event_years"].fillna("").astype(str))

    scenes = pd.read_parquet(products / "china_eo_scene_census_v0_1.parquet")
    assert {"mission_phase", "default_production_eligible"} <= set(scenes.columns)
    l7 = scenes[scenes["sensor"] == "landsat7"]
    assert not l7[
        l7["mission_phase"] == "OFF_NOMINAL_EXTENDED_MISSION"
    ]["default_production_eligible"].any()
    # 2022 orbit-lowering standby rows are preserved metadata but
    # must also stay out of the default production pool.
    assert not l7[
        l7["mission_phase"] == "STANDBY_ORBIT_LOWERING"
    ]["default_production_eligible"].any()
    assert len(l7) >= 20187  # all v0 L7 rows preserved

    report = json.loads(
        (products / "china_eo_census_report_v0_1.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["s1_pass_audit_token"] == S1_TOKEN
    assert report["census_cutoff_utc"] == CUTS_OFF_UTC
    # Only nominal-repeat-orbit L7 scenes are default-production eligible:
    # neither the 6,156 extended-mission rows nor the 9 standby rows count.
    assert (
        report["default_production_eligible_counts"]["landsat7"]
        == report["l7_extended_mission"]["phase_scene_counts"][
            "NOMINAL_REPEAT_ORBIT"
        ]
        == 21132
    )
