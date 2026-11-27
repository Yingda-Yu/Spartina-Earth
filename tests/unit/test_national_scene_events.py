"""Unit tests for deterministic scene/event row parsing (Issue #16)."""

from __future__ import annotations

from typing import cast

from spartina.data.national.scene_events import (
    event_id,
    landsat_scene_from_props,
    s1_scene_from_props,
    s2_granule_from_props,
    utc_from_epoch_ms,
    utc_from_scene_center,
)


def test_event_ids_deterministic_and_namespaced() -> None:
    assert event_id("landsat8", "LC8") == event_id("landsat8", "LC8")
    assert event_id("landsat8", "LC8") != event_id("landsat9", "LC8")
    assert event_id("sentinel2", "x").startswith("EVT-S2-")
    assert event_id("sentinel1", "x").startswith("EVT-S1-")
    assert event_id("landsat5", "x").startswith("EVT-L-")


def test_utc_parsers_are_always_aware() -> None:
    dt = utc_from_epoch_ms(1686218108000)
    assert dt is not None and dt.tzinfo is not None
    center = utc_from_scene_center("02:24:20.7480600Z", "2023-06-14")
    assert center is None or center.tzinfo is not None
    day_fallback = utc_from_scene_center(None, "2023-06-14")
    assert day_fallback is not None and day_fallback.tzinfo is not None
    assert utc_from_epoch_ms(None) is None
    assert utc_from_epoch_ms(True) is None
    assert utc_from_epoch_ms("not-a-number") is None


def test_s1_parser_requires_complete_metadata() -> None:
    props = {
        "system:index": "S1A_IW_GRDH_1SDV_20230608T095508_x",
        "system:time_start": 1686218108000,
        "relativeOrbitNumber_start": 171,
        "orbitNumber_start": 48893,
        "orbitProperties_pass": "ASCENDING",
        "platform_number": "A",
        "instrumentMode": "IW",
        "transmitterReceiverPolarisation": ["VH", "VV"],
    }
    scene = s1_scene_from_props(props, "hash")
    assert scene is not None
    row = scene.to_manifest_row()
    assert row["pass"] == "ASC"
    assert row["platform"] == "Sentinel-1A"
    assert row["polarization"] == "VH|VV"  # lexical sort
    assert row["footprint_sha256"] == "hash"
    assert cast(str, row["event_id"]).startswith("EVT-S1-")
    assert cast(str, row["utc"]).endswith("+00:00")

    bad = {**props, "orbitProperties_pass": "DESCENDING", "platform_number": "Z"}
    assert s1_scene_from_props(bad, "h") is None
    bad2 = {**props, "transmitterReceiverPolarisation": ["VV", 3]}
    assert s1_scene_from_props(bad2, "h") is None
    bad3 = {**props, "system:time_start": None}
    assert s1_scene_from_props(bad3, "h") is None


def test_landsat_and_s2_parsers_smoke() -> None:
    landsat = landsat_scene_from_props(
        "landsat8",
        {
            "LANDSAT_SCENE_ID": "LC81180382020001LGN00",
            "LANDSAT_PRODUCT_ID": "LC08_L2SP_118038_20200101",
            "SCENE_CENTER_TIME": "02:24:20.7480600Z",
            "DATE_ACQUIRED": "2020-01-01",
            "WRS_PATH": 118,
            "WRS_ROW": 38,
            "CLOUD_COVER": 12.5,
            "CLOUD_COVER_LAND": 3.0,
        },
    )
    assert landsat is not None
    assert landsat.to_row()["wrs_path"] == 118
    s2 = s2_granule_from_props(
        {
            "system:index": "20200901T023021_20200901T023523_T51TBT",
            "PRODUCT_ID": "L2A_T51TBT_20200901T023021",
            "DATATAKE_IDENTIFIER": "GS2A_DT0001",
            "MGRS_TILE": "51TBT",
            "SPACECRAFT_NAME": "Sentinel-2A",
            "system:time_start": 1598938800000,
            "CLOUDY_PIXEL_PERCENTAGE": 5.0,
            "CLOUDY_PIXEL_OVER_LAND_PERCENTAGE": 2.0,
        }
    )
    assert s2 is not None
    row2 = s2.to_row()
    assert row2["mgrs_tile"] == "51TBT"
    assert cast(str, row2["utc"]).endswith("+00:00")
    assert row2["datatake_identifier"] == "GS2A_DT0001"
