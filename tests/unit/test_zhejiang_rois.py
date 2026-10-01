"""Tests for the deterministic Tier-C ROI derivation (pure geometry)."""

from __future__ import annotations

import pytest
from shapely.geometry import box

from spartina.data.zhejiang.rois import (
    Anchor,
    BaySpec,
    construct_bay,
    geometry_fingerprint,
    haversine_m,
    parse_bay_specs,
    polygon_rings,
    snap_to_coastline,
)

PROJECTION = "EPSG:32651"


def _synthetic_world():
    # mainland block with a bay notch opening east, plus two mouth islands
    land = box(0, 0, 10, 10).difference(box(8, 3, 14, 7))
    # mouth-headland rocks whose corner vertices coincide with the envelope
    # mouth points (13.9, 2.9) and (13.9, 6.9)
    land = land.union(box(13.8, 2.8, 14.0, 3.0))
    land = land.union(box(13.8, 6.8, 14.0, 7.0))
    rings = polygon_rings([land])
    return land, rings


def test_haversine_known_degree():
    d = haversine_m(0, 0, 0, 1)
    assert 110_500 < d < 111_700


def test_snap_nearest_vertex_deterministic_tiebreak():
    land, rings = _synthetic_world()
    a = Anchor("mouth_n", "SECTION_POINT", 8.0, 7.0, 500.0, "n")
    rec = snap_to_coastline(a, rings)
    assert rec.snapped_lon == pytest.approx(8.0, abs=1e-9)
    assert rec.snapped_lat == pytest.approx(7.0, abs=1e-9)
    assert rec.snap_distance_m < 500.0


def test_snap_outside_radius_fails_loudly():
    _, rings = _synthetic_world()
    a = Anchor("far", "SECTION_POINT", 20.0, 20.0, 100.0, "far")
    with pytest.raises(ValueError, match="snap radius"):
        snap_to_coastline(a, rings)


def _spec() -> BaySpec:
    anchors = (
        Anchor("head_n", "SECTION_POINT", 8.0, 7.0, 500.0, "hn"),
        Anchor("head_s", "SECTION_POINT", 8.0, 3.0, 500.0, "hs"),
        Anchor("mouth_island_s", "SECTION_POINT", 14.0, 3.0, 100.0, "mis"),
        Anchor("mouth_island_n", "SECTION_POINT", 14.0, 7.0, 100.0, "min"),
    )
    return BaySpec(
        roi_id="TEST-BAY", name_zh="测试湾", name_en="Test Bay",
        envelope_order=("head_n", "head_s", "mouth_island_s",
                        "mouth_island_n"),
        anchors=anchors, onshore_belt_m=2000.0,
        published_area_km2=None)


def test_construct_bay_water_and_belt_valid():
    land, rings = _synthetic_world()
    geom = construct_bay(_spec(), land, rings, PROJECTION)
    assert geom.roi_geometry.is_valid
    # notch corridor (6 deg x 4 deg minus islands) is water
    assert geom.water.area > geom.belt.area
    fp1 = geometry_fingerprint(geom.roi_geometry)
    geom2 = construct_bay(_spec(), land, rings, PROJECTION)
    assert geometry_fingerprint(geom2.roi_geometry) == fp1
    assert geom.snap_records and all(r.snap_distance_m <= 500
                                     for r in geom.snap_records)


def test_construction_corner_must_be_on_land():
    land, rings = _synthetic_world()
    anchors = (_spec().anchors[:2]
               + (Anchor("sea_corner", "CONSTRUCTION_CORNER",
                         12.0, 5.0, 0.0, "x"),)
               + _spec().anchors[2:])
    spec = BaySpec(
        roi_id="TEST-BAY2", name_zh="x", name_en="x",
        envelope_order=("head_n", "head_s", "sea_corner",
                        "mouth_island_s", "mouth_island_n"),
        anchors=tuple(anchors), onshore_belt_m=2000.0,
        published_area_km2=None)
    with pytest.raises(ValueError, match="not on mapped land"):
        construct_bay(spec, land, rings, PROJECTION)


def test_parse_bay_specs_minimal_config():
    cfg = {"rois": [{
        "roi_id": "ZJ-X", "name_zh": "湾", "name_en": "X",
        "onshore_belt_m": 2000,
        "envelope_order": ["a", "b"],
        "anchors": [
            {"id": "a", "kind": "CONSTRUCTION_CORNER", "lon": 1.0,
             "lat": 2.0, "snap_radius_m": 0},
            {"id": "b", "kind": "SECTION_POINT", "lon": 1.1,
             "lat": 2.1, "snap_radius_m": 1000,
             "source_id": "src_x", "place_zh": "p"},
        ],
        "published_area_km2": 12.5,
    }]}
    spec = parse_bay_specs(cfg)[0]
    assert spec.roi_id == "ZJ-X"
    assert spec.anchor("b").source_id == "src_x"
    assert spec.published_area_km2 == 12.5
