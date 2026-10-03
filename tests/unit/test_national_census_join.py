"""Unit tests for local national census joins (no GEE, no pixels)."""

from __future__ import annotations

import geopandas as gpd
import pandas as pd
from shapely.geometry import box

from spartina.data.national.census_join import (
    FULL_COVER,
    PARTIAL_COVER,
    build_availability,
    cell_events_union,
    chronic_gap_flags,
    join_landsat_family,
    join_s2_granules,
    s2_event_group_id,
)
from spartina.data.national.scene_events import event_id

CELL = gpd.GeoDataFrame(
    {"cell_id": ["cell-a", "cell-b"]},
    geometry=[box(0.0, 0.0, 0.1, 0.1), box(2.0, 2.0, 2.1, 2.1)],
    crs="EPSG:4326",
)


def _frame(path: int, row: int, geom: object) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {"path": [path], "row": [row]}, geometry=[geom], crs="EPSG:4326"
    )


def _landsat_scene(sensor: str, path: int, row: int, utc: str) -> pd.DataFrame:
    scene_id = f"{sensor}_{path}_{row}_{utc}"
    ts = pd.Timestamp(utc, tz="UTC")
    return pd.DataFrame(
        [
            {
                "event_id": event_id(sensor, scene_id),
                "sensor": sensor,
                "scene_id": scene_id,
                "utc": ts.isoformat(),
                "year": ts.year,
                "doy": ts.dayofyear,
                "season_tag": "OTHER_SEASON_FULL_YEAR",
                "frame_id": f"WRS2-D-P{path:03d}-R{row:03d}",
                "wrs_path": path,
                "wrs_row": row,
            }
        ]
    )


def test_landsat_full_and_partial_coverage() -> None:
    frames = pd.concat(
        [
            _frame(118, 39, box(-0.2, -0.2, 0.3, 0.3)),  # contains cell-a
            _frame(119, 40, box(0.05, 0.05, 0.5, 0.5)),  # partial cell-a
        ],
        ignore_index=True,
    )
    frames = gpd.GeoDataFrame(frames, geometry="geometry", crs="EPSG:4326")
    scenes = pd.concat(
        [
            _landsat_scene("landsat8", 118, 39, "2020-06-01T02:00:00+00:00"),
            _landsat_scene("landsat8", 119, 40, "2020-06-17T02:00:00+00:00"),
        ],
        ignore_index=True,
    )
    pairs, extended = join_landsat_family(scenes, frames, CELL)
    assert extended == 0
    by_event = pairs.set_index("event_id")["coverage"].to_dict()
    assert list(by_event.values()) == [FULL_COVER, PARTIAL_COVER]
    assert set(pairs["cell_id"]) == {"cell-a"}


def test_l7_extended_mission_scenes_excluded_without_native_geometry() -> None:
    frames = _frame(118, 39, box(-0.2, -0.2, 0.3, 0.3))
    nominal = _landsat_scene("landsat7", 118, 39, "2022-03-01T02:00:00+00:00")
    extended = _landsat_scene("landsat7", 118, 39, "2022-06-01T02:00:00+00:00")
    scenes = pd.concat([nominal, extended], ignore_index=True)
    pairs, excluded = join_landsat_family(scenes, frames, CELL)
    assert excluded == 1
    assert len(pairs) == 1


def test_s2_same_datatake_same_day_merges_different_days_never_merge() -> None:
    tiles = gpd.GeoDataFrame(
        {"mgrs_tile": ["51TBT", "51TBU"]},
        geometry=[
            box(-0.2, -0.2, 0.3, 0.3),
            box(-0.1, -0.2, 0.4, 0.3),
        ],
        crs="EPSG:4326",
    )
    base = {
        "sensor": "sentinel2",
        "year": 2020,
        "doy": 245,
        "season_tag": "AUTUMN_PRIMARY_V1_CANDIDATE",
    }
    rows = [
        {
            **base,
            "event_id": event_id("sentinel2", "g1-tile1"),
            "scene_id": "g1-tile1",
            "datatake_identifier": "GS2A_DT1",
            "mgrs_tile": "51TBT",
            "utc": "2020-09-01T02:30:00+00:00",
        },
        {
            **base,
            "event_id": event_id("sentinel2", "g1-tile2"),
            "scene_id": "g1-tile2",
            "datatake_identifier": "GS2A_DT1",
            "mgrs_tile": "51TBU",
            "utc": "2020-09-01T02:30:10+00:00",
        },
        {
            **base,
            "event_id": event_id("sentinel2", "g2-tile1"),
            "scene_id": "g2-tile1",
            "datatake_identifier": "GS2A_DT1",
            "mgrs_tile": "51TBT",
            "utc": "2020-09-06T02:30:00+00:00",
            "doy": 250,
        },
    ]
    events = join_s2_granules(pd.DataFrame(rows), tiles, CELL)
    assert len(events) == 2
    dt1 = events[events["member_scene_count"] == 2]
    assert len(dt1) == 1
    assert dt1.iloc[0]["coverage"] == FULL_COVER
    assert s2_event_group_id("GS2A_DT1", "2020-09-01") == dt1.iloc[0]["event_id"]
    assert set(events["geometry_basis"]) == {"MGRS_NOMINAL_100KM_TILE"}


def test_cell_events_union_full_cover_wins_and_dedupes() -> None:
    columns = [
        "cell_id", "sensor", "event_id", "utc", "year", "doy",
        "season_tag", "coverage", "geometry_basis", "member_scene_count",
    ]
    partial = dict(
        cell_id="c", sensor="sentinel1", event_id="e", utc="2020-01-01T00:00:00+00:00",
        year=2020, doy=1, season_tag="OTHER_SEASON_FULL_YEAR",
        coverage=PARTIAL_COVER, geometry_basis="B", member_scene_count=1,
    )
    full = {**partial, "coverage": FULL_COVER}
    merged = cell_events_union(
        [pd.DataFrame([partial, full])[columns]]
    )
    assert len(merged) == 1
    assert merged.iloc[0]["coverage"] == FULL_COVER


def test_availability_statuses_and_chronic_gap_classes() -> None:
    events = pd.DataFrame(
        [
            {
                "cell_id": "cell-a", "sensor": "sentinel2",
                "event_id": "x", "utc": "2020-09-01T02:30:00+00:00",
                "year": 2020, "doy": 245,
                "season_tag": "AUTUMN_PRIMARY_V1_CANDIDATE",
                "coverage": FULL_COVER,
            }
        ]
    )
    availability = build_availability(
        events,
        pd.Series(["cell-a"], name="cell_id"),
        year_start=2019,
        year_end=2021,
        failed_scopes=set(),
    )
    s2 = availability[availability["sensor"] == "sentinel2"]
    statuses = dict(zip(s2["year"], s2["status"], strict=False))
    assert statuses == {
        2019: "NO_SCENES_FOUND",
        2020: "METADATA_AVAILABLE",
        2021: "NO_SCENES_FOUND",
    }
    # Landsat 5 not operational in 2019-2021 -> no rows at all.
    assert not (availability["sensor"] == "landsat5").any()
    failed = build_availability(
        events, pd.Series(["cell-a"], name="cell_id"), 2020, 2020,
        failed_scopes={"sentinel2:2020"},
    )
    assert (
        failed[failed["sensor"] == "sentinel2"]["status"] == "QUERY_FAILED"
    ).all()
    gaps = chronic_gap_flags(availability)
    s2_gap = gaps[gaps["sensor"] == "sentinel2"].iloc[0]
    assert s2_gap["max_consecutive_zero_years"] >= 1
    assert s2_gap["gap_class"] in {
        "CHRONIC_ZERO_COMMON_ERA", "MULTI_YEAR_GAP", "NO_CHRONIC_GAP",
    }
