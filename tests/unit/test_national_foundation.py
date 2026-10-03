"""Offline unit tests for the Issue #14 national foundation modules."""

from __future__ import annotations

import csv
import json

import geopandas as gpd
import pytest
from shapely.geometry import Polygon, box

from spartina.data.national import census
from spartina.data.national.coastal_domain import (
    build_china_land,
    build_corridor,
    scan_lattice_cells,
    zone_band_bounds,
)
from spartina.data.national.domain import CorridorWidth, DomainDecisionInputs
from spartina.data.national.grid import (
    CHINA_COASTAL_UTM_ZONES,
    GridKind,
    GridSpec,
    encode_cell_id,
    parse_cell_id,
)
from spartina.data.national.passport import PassportFile, SourcePassport
from spartina.data.national.products import REQUIRED_COLUMNS, load_label_products
from spartina.data.national.registry import COLUMNS, load_multimodal_registry
from spartina.data.national.tiers import CostAssumptions, NationalScaleModel

# ---- grid ----------------------------------------------------------------

def test_cell_id_round_trip_albers() -> None:
    cid = encode_cell_id(GridKind.CHINA_ALBERS, 123, 45)
    ref = parse_cell_id(cid)
    assert ref.kind is GridKind.CHINA_ALBERS
    assert ref.zone is None
    assert (ref.row, ref.col) == (123, 45)
    assert cid == "CNA10K-R00123-C00045"


def test_cell_id_round_trip_utm() -> None:
    cid = encode_cell_id(GridKind.UTM_ZONE_AWARE, 4_096, 128, 51)
    ref = parse_cell_id(cid)
    assert ref.kind is GridKind.UTM_ZONE_AWARE
    assert ref.zone == 51
    assert (ref.row, ref.col) == (4_096, 128)
    assert cid == "CNU10K-Z51N-R004096-C000128"


@pytest.mark.parametrize(
    "bad",
    [
        "CNA10K-R01-C01",
        "CNA10K-R1-C01",
        "CNA10K-R00001-X00001",
        "CNU10K-Z53N-R004096-C000128",
        "CNU10K-Z48N-R004096-C000128",
        "T50SMG1234567890",
        "CNA10K-R00001-C00001-extra",
    ],
)
def test_malformed_cell_ids_rejected(bad: str) -> None:
    with pytest.raises(ValueError):
        parse_cell_id(bad)


def test_utm_zone_rejected_for_albers_and_vice_versa() -> None:
    spec = GridSpec(GridKind.CHINA_ALBERS)
    with pytest.raises(ValueError):
        spec.cell_bounds_projected(0, 0, zone=50)
    spec_u = GridSpec(GridKind.UTM_ZONE_AWARE)
    with pytest.raises(ValueError):
        spec_u.cell_bounds_projected(0, 0)
    with pytest.raises(ValueError):
        spec_u.cell_bounds_projected(0, 0, zone=48)


def test_indices_for_bounds_cover() -> None:
    spec = GridSpec(GridKind.CHINA_ALBERS)
    rmin, rmax, cmin, cmax = spec.indices_for_bounds(-15_000, 5_000, 25_000, 10_001)
    assert (rmin, rmax, cmin, cmax) == (0, 1, -2, 2)
    with pytest.raises(ValueError):
        spec.indices_for_bounds(0, 0, 0, 10)


# ---- domain width ---------------------------------------------------------

def test_width_rule_evidence_driven() -> None:
    assert DomainDecisionInputs().recommended_width() is CorridorWidth.W_20KM
    assert (
        DomainDecisionInputs(intertidal_onshore_extent_m_p90=7_000).recommended_width()
        is CorridorWidth.W_10KM
    )
    assert (
        DomainDecisionInputs(shoreline_position_uncertainty_m=15_000).recommended_width()
        is CorridorWidth.W_20KM
    )
    assert (
        DomainDecisionInputs(management_zone_halfwidth_m=2_000).recommended_width()
        is CorridorWidth.W_5KM
    )


# ---- passport -------------------------------------------------------------

def _valid_passport_kwargs() -> dict[str, object]:
    return {
        "dataset_id": "X",
        "source_url": "https://example.org/x.zip",
        "download_utc": "2026-10-03T09:44:37+00:00",
        "license": "CC-BY-4.0",
        "files": (PassportFile("a.shp", 10, "a" * 64),),
        "citation": "Doe, J. (2025) Example.",
    }


def test_passport_accepts_valid() -> None:
    passport = SourcePassport(**_valid_passport_kwargs())  # type: ignore[arg-type]
    passport.validate()
    assert passport.total_size_bytes() == 10


def test_passport_rejects_non_utc_and_bad_hash() -> None:
    kwargs = _valid_passport_kwargs()
    kwargs["download_utc"] = "2026-10-03T17:44:37+08:00"
    with pytest.raises(ValueError):
        SourcePassport(**kwargs).validate()  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        PassportFile("a", 1, "nope").validate()


def test_passport_json_roundtrip(tmp_path: object) -> None:
    from pathlib import Path

    out = Path(str(tmp_path)) / "SOURCE_PASSPORT.json"
    payload = _valid_passport_kwargs()
    payload["files"] = [
        {"name": "a.shp", "size_bytes": 10, "sha256": "a" * 64}
    ]
    out.write_text(json.dumps(payload))
    from spartina.data.national.passport import load_passport

    loaded = load_passport(out)
    assert loaded.dataset_id == "X"


# ---- product + multimodal registries -------------------------------------

def test_label_products_manifest_roundtrip(tmp_path: object) -> None:
    from pathlib import Path

    path = Path(str(tmp_path)) / "labels.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(REQUIRED_COLUMNS))
        writer.writeheader()
        row = {column: "UNKNOWN" for column in REQUIRED_COLUMNS}
        row["product_id"] = "P1"
        row["year"] = "2015"
        writer.writerow(row)
        row2 = dict(row)
        row2["product_id"] = "P2"
        row2["year"] = "2020"
        writer.writerow(row2)
    registry = load_label_products(path)
    assert registry.years() == ["2015", "2020"]
    assert registry.by_id("P1").year_int == 2015


def test_label_products_rejects_extra_column(tmp_path: object) -> None:
    from pathlib import Path

    path = Path(str(tmp_path)) / "bad.csv"
    cols = list(REQUIRED_COLUMNS) + ["surprise"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=cols)
        writer.writeheader()
        writer.writerow({c: "" for c in cols})
    with pytest.raises(ValueError):
        load_label_products(path)


def test_multimodal_registry_roundtrip(tmp_path: object) -> None:
    from pathlib import Path

    path = Path(str(tmp_path)) / "mm.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(COLUMNS))
        writer.writeheader()
        row = {column: "" for column in COLUMNS}
        row.update(
            {
                "dataset_id": "JRC-GSW",
                "family": "surface_water",
                "role": "CORE",
                "access_status": "GEE_ASSET",
                "gee_asset": "JRC/GSW1_4/GlobalSurfaceWater",
            }
        )
        writer.writerow(row)
    registry = load_multimodal_registry(path)
    assert registry.by_id("JRC-GSW").gee_asset.endswith("GlobalSurfaceWater")
    assert registry.by_family()["surface_water"][0].dataset_id == "JRC-GSW"


# ---- census helpers -------------------------------------------------------

def test_summarize_frame_rows() -> None:
    rows = ((2018, "P118R039"), (2018, "P118R039"), (2019, "P119R039"))
    summary = census.summarize_frame_rows(rows)
    assert summary[2018]["total_scenes"] == 2
    assert summary[2018]["distinct_nominal_frames"] == 1
    joined = census.cell_year_sensor_records(
        {"P118R039": {2018: 2}, "P119R039": {2019: 1}}
    )
    assert joined["2018"]["P118R039"] == 2


def test_batch_contract_guards() -> None:
    s1_spec = next(s for s in census.SENSOR_SPECS if s.sensor is census.Sensor.S1)
    census.assert_batch_contract(s1_spec)
    bad = census.SensorSpec(
        census.Sensor.S1,
        "COPERNICUS/S1_GRD",
        2014,
        2026,
        "MGRS",
        "MGRS_TILE",
        (),
        False,
        "broken spec",
    )
    with pytest.raises(ValueError):
        census.assert_batch_contract(bad)


# ---- tiers ----------------------------------------------------------------

def test_tier_model_arithmetic() -> None:
    model = NationalScaleModel(3_320, CostAssumptions(positive_history_cells=482))
    t0 = model.tier0(census_years=5)
    assert t0.cell_years == 3_320 * 5
    assert t0.bytes_total == 3_320 * 5 * 4_096
    t1 = model.tier1()
    assert t1.cells == 482
    assert t1.cell_years == 482
    all_tiers = model.all_tiers(census_years=5)
    assert set(all_tiers) == {
        "TIER0_METADATA_ONLY",
        "TIER1_POSITIVE_HISTORY_NEARBY",
        "TIER2_STANDARD_NATIONAL_MONITORING",
        "TIER3_FULL_COASTAL_ARCHIVE",
    }
    assert all_tiers["TIER3_FULL_COASTAL_ARCHIVE"]["gibibytes"] > 0


def test_tier_model_rejects_bad_inputs() -> None:
    with pytest.raises(ValueError):
        NationalScaleModel(0, CostAssumptions())
    with pytest.raises(ValueError):
        NationalScaleModel(10, CostAssumptions(tier1_cell_fraction=0))


# ---- coastal domain geometry ---------------------------------------------

def test_corridor_excludes_foreign_land_border() -> None:
    china = box(0, 0, 100, 100)
    foreign = box(100, 0, 200, 100)
    all_land = china.union(foreign)
    corridor = build_corridor(china, all_land, 10)
    # Open-water sides are in, the shared land border and foreign land are out.
    assert corridor.covers(box(40, 101, 60, 109))
    assert corridor.covers(box(40, -9, 60, -1))
    assert not corridor.covers(box(91, 40, 99, 60))
    assert not corridor.intersects(box(101, 40, 109, 60))


def test_scan_lattice_deterministic_and_sliver_filtered() -> None:
    china = box(0, 0, 100, 100)
    foreign = box(100, 0, 200, 100)
    corridor = build_corridor(china, china.union(foreign), 10)
    hits = scan_lattice_cells(
        corridor, GridKind.CHINA_ALBERS, cell_size_m=10, min_fraction=0.01
    )
    assert len(hits) > 0
    assert len({h.cell_id for h in hits}) == len(hits)
    # No cells along the interior of the shared foreign border (col 10).
    assert not any(h.row in range(0, 10) and h.col == 10 for h in hits)
    # Every retained cell really overlaps the corridor by >= 1 % (0.01 * 100).
    assert all(h.intersection_m2 >= 1.0 for h in hits)
    assert scan_lattice_cells(china.intersection(box(300, 300, 301, 301)),
                              GridKind.CHINA_ALBERS) == []


def test_build_china_land_recovers_small_nearby_island() -> None:
    # Synthetic 4326 frames near 30 N, 120 E (units ~ degrees).
    china_poly = Polygon([(120.0, 30.0), (120.05, 30.0), (120.05, 30.05),
                          (120.0, 30.05)])
    # Small Chinese-administered island absent from the China polygon,
    # ~3-5 km offshore, not inside any other country polygon.
    island = box(120.055, 30.02, 120.057, 30.022)
    # Foreign mainland across the sea; its own small islet must stay out.
    foreign = Polygon([(120.2, 29.8), (120.4, 29.8), (120.4, 30.2),
                       (120.2, 30.2)])
    foreign_islet = box(120.21, 30.01, 120.212, 30.012)
    gshhs = gpd.GeoDataFrame(
        {"id": [1, 2, 3, 4]},
        geometry=[china_poly, island, foreign, foreign_islet],
        crs=4326,
    )
    admin = gpd.GeoDataFrame(
        {"ADMIN": ["China", "Atlantis"]},
        geometry=[china_poly, foreign],
        crs=4326,
    )
    land = build_china_land(
        gshhs,
        admin,
        "+proj=aea +lat_1=25 +lat_2=47 +lat_0=0 +lon_0=105 +datum=WGS84 +units=m",
    )
    assert land.added_island_count == 1
    assert land.land.covers(
        gpd.GeoSeries([island], crs=4326)
        .to_crs("+proj=aea +lat_1=25 +lat_2=47 +lat_0=0 +lon_0=105 +datum=WGS84 +units=m")
        .iloc[0]
    )
    assert not land.land.intersects(
        gpd.GeoSeries([foreign_islet], crs=4326)
        .to_crs("+proj=aea +lat_1=25 +lat_2=47 +lat_0=0 +lon_0=105 +datum=WGS84 +units=m")
        .iloc[0]
    )


def test_zone_bands_cover_coast_without_gaps() -> None:
    # 49: 108-114, 50: 114-120, 51: 120-126, 52: 126-132 (plus margins).
    assert CHINA_COASTAL_UTM_ZONES == (49, 50, 51, 52)
    west49, _, east49, _ = zone_band_bounds(49)
    west50, _, _, _ = zone_band_bounds(50)
    assert west49 < 108.0 < east49
    assert west50 < 114.0 < east49  # bands overlap at the seam
