"""Local spatial joins for the national EO census.

No GEE calls happen here. Inputs are the cached scene/granule metadata
parquets (``work/national/census``) plus the static WRS-2 and MGRS index
geometries. Joins are strictly local, deterministic and repeatable.

Coverage semantics (per cell-event pair):

* ``FULL_CELL_COVERED``    -- the nominal frame / MGRS tile / actual S1
                              footprint geometrically covers the complete
                              10 km cell polygon;
* ``PARTIAL_CELL_OVERLAP`` -- the geometries intersect but the cell is not
                              fully contained.

Sentinel-2 granules are grouped into ObservationEvents **only** by
``(datatake identifier, UTC calendar date)``: multi-tile members of the
same datatake on the same day merge, granules from different dates never
merge. Landsat 7 Extended Science Mission scenes (>= 2022-05-05) are not
on the nominal WRS-2 grid and are excluded from the nominal join; the
caller reports their count.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import geopandas as gpd
import pandas as pd
from shapely.geometry import box

from spartina.data.national.footprints import (
    METADATA_AVAILABLE,
    NO_SCENES_FOUND,
    NOMINAL_WINDOWS,
    SENSOR_NOT_OPERATIONAL,
    l7_footprint_is_nominal_wrs2,
    sensor_operational,
)
from spartina.data.national.grid import CHINA_ALBERS_PROJ4, GridKind, GridSpec
from spartina.data.national.scene_events import event_id

WRS2_BASIS = "WRS2_NOMINAL_FRAME"
MGRS_BASIS = "MGRS_NOMINAL_100KM_TILE"
S1_BASIS = "S1_GRD_ACTUAL_GEE_FOOTPRINT"
FULL_COVER = "FULL_CELL_COVERED"
PARTIAL_COVER = "PARTIAL_CELL_OVERLAP"
EXTENDED_L7 = "L7_EXTENDED_EXCLUDED_NO_NATIVE_GEOMETRY"

CELL_EVENT_COLUMNS = (
    "cell_id",
    "sensor",
    "event_id",
    "utc",
    "year",
    "doy",
    "season_tag",
    "coverage",
    "geometry_basis",
    "member_scene_count",
)

def load_cells(cells_csv: Path, width_m: int = 10000) -> gpd.GeoDataFrame:
    """Build Albers cell polygons (EPSG:4326) from a domain cell list."""
    grid = GridSpec(GridKind.CHINA_ALBERS, cell_size_m=width_m)
    frame = pd.read_csv(cells_csv)
    geometries: list[Any] = []
    for row in frame.itertuples(index=False):
        xmin, ymin, xmax, ymax = grid.cell_bounds_projected(
            int(cast(Any, row).row), int(cast(Any, row).col)
        )
        geometries.append(box(xmin, ymin, xmax, ymax))
    gdf = gpd.GeoDataFrame(
        frame[["cell_id"]].copy(), geometry=geometries, crs=CHINA_ALBERS_PROJ4
    )
    return cast(gpd.GeoDataFrame, gdf.to_crs("EPSG:4326"))


def _pairwise_join(
    scenes: gpd.GeoDataFrame,
    cells: gpd.GeoDataFrame,
) -> pd.DataFrame:
    """Intersect-join scene polygons to cells, then test full coverage."""
    joined = gpd.sjoin(
        scenes[["event_id", "geometry"]],
        cells[["cell_id", "geometry"]],
        how="inner",
        predicate="intersects",
    )
    scene_geoms = cast(gpd.GeoSeries, scenes.geometry).loc[
        cast(pd.Series, joined.index)
    ]
    cell_lookup = cells.set_index("cell_id")
    cell_geoms = cast(gpd.GeoSeries, cell_lookup.geometry).loc[
        cast(pd.Series, joined["cell_id"]).to_numpy()
    ]
    covers = cast(gpd.GeoSeries, scene_geoms).covers(
        cast(gpd.GeoSeries, cell_geoms.set_axis(cast(pd.Series, joined.index)))
    )
    coverage = pd.Series(
        [FULL_COVER if flag else PARTIAL_COVER for flag in covers],
        index=joined.index,
        name="coverage",
    )
    result = pd.DataFrame(
        {
            "event_id": cast(pd.Series, joined["event_id"]).to_numpy(),
            "cell_id": cast(pd.Series, joined["cell_id"]).to_numpy(),
            "coverage": coverage.to_numpy(),
        }
    )
    return result


def join_landsat_family(
    scenes: pd.DataFrame,
    frames: gpd.GeoDataFrame,
    cells: gpd.GeoDataFrame,
) -> tuple[pd.DataFrame, int]:
    """Join Landsat scenes via nominal WRS-2 frame polygons.

    Returns the cell-event pairs and the number of L7 extended-mission
    scenes excluded (their native geometry was not fetched).
    """
    frame_lookup = cast(
        pd.DataFrame, frames[["path", "row", "geometry"]].copy()
    )
    scenes = scenes.rename(columns={"wrs_path": "path", "wrs_row": "row"})
    scenes = scenes.copy()
    extended = 0
    if "landsat7" in set(cast(pd.Series, scenes["sensor"]).astype(str)):
        utc = pd.to_datetime(cast(pd.Series, scenes["utc"]), utc=True, format="ISO8601")
        is_l7 = cast(pd.Series, scenes["sensor"]) == "landsat7"
        nominal = cast(pd.Series, utc.map(lambda t: l7_footprint_is_nominal_wrs2(t)))
        extended = int((is_l7 & ~nominal).sum())
        scenes = scenes[~(is_l7 & ~nominal)].copy()
    merged = scenes.merge(frame_lookup, on=["path", "row"], how="inner")
    scene_gdf = gpd.GeoDataFrame(
        merged.drop(columns=["geometry_y"], errors="ignore"),
        geometry=cast(Any, merged["geometry"]),
        crs="EPSG:4326",
    )
    pairs = _pairwise_join(cast(gpd.GeoDataFrame, scene_gdf), cells)
    enriched = pairs.merge(
        scenes[
            [
                "event_id",
                "sensor",
                "utc",
                "year",
                "doy",
                "season_tag",
                "frame_id",
            ]
        ],
        on="event_id",
        how="left",
    )
    enriched["geometry_basis"] = WRS2_BASIS
    enriched["member_scene_count"] = 1
    return enriched, extended


def s2_event_group_id(datatake_identifier: str, utc_day: str) -> str:
    """Deterministic S2 ObservationEvent id (datatake + UTC day)."""
    return event_id("sentinel2", f"{datatake_identifier}:{utc_day}")


def join_s2_granules(
    granules: pd.DataFrame,
    tiles: gpd.GeoDataFrame,
    cells: gpd.GeoDataFrame,
) -> pd.DataFrame:
    """Join S2 granules via nominal MGRS tile polygons; group to events."""
    granules = granules.copy()
    utc = pd.to_datetime(cast(pd.Series, granules["utc"]), utc=True, format="ISO8601")
    granules["utc_day"] = cast(pd.Series, utc.dt.date.astype(str))
    granules["s2_event_id"] = [
        s2_event_group_id(str(d), str(day))
        for d, day in zip(
            cast(pd.Series, granules["datatake_identifier"]),
            cast(pd.Series, granules["utc_day"]), strict=False,
        )
    ]
    tile_lookup = cast(pd.DataFrame, tiles[["mgrs_tile", "geometry"]].copy())
    merged = granules.merge(tile_lookup, on="mgrs_tile", how="inner")
    granule_gdf = gpd.GeoDataFrame(
        merged.drop(columns=["geometry_y"], errors="ignore"),
        geometry=cast(Any, merged["geometry"]),
        crs="EPSG:4326",
    )
    pairs = _pairwise_join(cast(gpd.GeoDataFrame, granule_gdf), cells)
    # Granule -> event columns; different dates never share an event.
    granule_keys = cast(
        pd.DataFrame,
        granules[
            ["event_id", "s2_event_id", "utc_day", "utc", "year", "doy",
             "season_tag"]
        ],
    )
    enriched = pairs.merge(granule_keys, on="event_id", how="left")
    event_level = (
        enriched.groupby(["cell_id", "s2_event_id"], as_index=False)
        .agg(
            coverage=(
                "coverage",
                lambda values: FULL_COVER
                if FULL_COVER in set(values)
                else PARTIAL_COVER,
            ),
            member_scene_count=("event_id", "nunique"),
            utc=("utc", "min"),
            year=("year", "min"),
            doy=("doy", "min"),
            season_tag=("season_tag", "first"),
        )
    )
    event_level = event_level.rename(columns={"s2_event_id": "event_id"})
    event_level["sensor"] = "sentinel2"
    event_level["geometry_basis"] = MGRS_BASIS
    return cast(pd.DataFrame, event_level[list(CELL_EVENT_COLUMNS)])


def join_s1_scenes(
    scenes: gpd.GeoDataFrame, cells: gpd.GeoDataFrame
) -> pd.DataFrame:
    """Join actual S1 GRD footprints to cells (one scene == one event)."""
    scene_gdf = cast(gpd.GeoDataFrame, scenes.to_crs("EPSG:4326"))
    pairs = _pairwise_join(scene_gdf, cells)
    attrs = cast(
        pd.DataFrame,
        scene_gdf[
            ["event_id", "sensor", "utc", "year", "doy", "season_tag"]
        ],
    )
    enriched = pairs.merge(attrs, on="event_id", how="left")
    enriched["geometry_basis"] = S1_BASIS
    enriched["member_scene_count"] = 1
    return cast(pd.DataFrame, enriched[list(CELL_EVENT_COLUMNS)])


def build_availability(
    cell_events: pd.DataFrame,
    cell_ids: pd.Series[str],
    year_start: int,
    year_end: int,
    failed_scopes: set[str],
) -> pd.DataFrame:
    """Cell x year x sensor availability over each sensor's operational span."""
    sensors = sorted(NOMINAL_WINDOWS)
    records: list[dict[str, Any]] = []
    events = cast(pd.DataFrame, cell_events).copy()
    events["utc"] = pd.to_datetime(cast(pd.Series, events["utc"]), utc=True, format="ISO8601")
    grouped = events.groupby(
        ["cell_id", "year", "sensor"], as_index=False
    ).agg(
        n_events=("event_id", "nunique"),
        n_full_cover=("coverage", lambda s: int((s == FULL_COVER).sum())),
        n_autumn=("season_tag", lambda s: int((s == "AUTUMN_PRIMARY_V1_CANDIDATE").sum())),
        first_utc=("utc", "min"),
        last_utc=("utc", "max"),
    )
    lookup = {
        (r.cell_id, r.year, r.sensor): r
        for r in grouped.itertuples(index=False)
    }
    cells_list = list(cell_ids)
    for sensor in sensors:
        for year in range(year_start, year_end + 1):
            scope = f"{sensor}:{year}"
            if not sensor_operational(sensor, year):
                status = SENSOR_NOT_OPERATIONAL
            elif scope in failed_scopes:
                status = "QUERY_FAILED"
            else:
                status = None
            if status == SENSOR_NOT_OPERATIONAL:
                continue
            for cell_id in cells_list:
                record = lookup.get((cell_id, year, sensor))
                if record is None:
                    records.append(
                        {
                            "cell_id": cell_id,
                            "year": year,
                            "sensor": sensor,
                            "status": status or NO_SCENES_FOUND,
                            "n_events": 0,
                            "n_full_cover": 0,
                            "n_autumn_events": 0,
                            "first_utc": None,
                            "last_utc": None,
                        }
                    )
                else:
                    records.append(
                        {
                            "cell_id": cell_id,
                            "year": year,
                            "sensor": sensor,
                            "status": "QUERY_FAILED"
                            if scope in failed_scopes
                            else METADATA_AVAILABLE,
                            "n_events": int(cast(Any, record).n_events),
                            "n_full_cover": int(cast(Any, record).n_full_cover),
                            "n_autumn_events": int(cast(Any, record).n_autumn),
                            "first_utc": cast(Any, record).first_utc.isoformat(),
                            "last_utc": cast(Any, record).last_utc.isoformat(),
                        }
                    )
    return pd.DataFrame.from_records(records)


def chronic_gap_flags(
    availability: pd.DataFrame, common_start: int = 2015, common_end: int = 2025
) -> pd.DataFrame:
    """Per cell x sensor: zero-event years, longest dry run, chronic flag."""
    rows: list[dict[str, Any]] = []
    for (cell_id, sensor), group in availability.groupby(["cell_id", "sensor"]):
        years = cast(pd.Series, group["year"]).tolist()
        zero_years = [
            int(y)
            for y, n in zip(years, cast(pd.Series, group["n_events"]).tolist(), strict=False)
            if int(n) == 0
        ]
        longest = 0
        run = 0
        previous: int | None = None
        for year in zero_years:
            run = run + 1 if previous is not None and year == previous + 1 else 1
            longest = max(longest, run)
            previous = year
        common = group[
            (cast(pd.Series, group["year"]) >= common_start)
            & (cast(pd.Series, group["year"]) <= common_end)
        ]
        common_years = len(common)
        common_zero = int((cast(pd.Series, common["n_events"]) == 0).sum())
        if common_years == 0:
            chronic = "NOT_APPLICABLE"
        elif common_zero == common_years:
            chronic = "CHRONIC_ZERO_COMMON_ERA"
        elif longest >= 3:
            chronic = "MULTI_YEAR_GAP"
        else:
            chronic = "NO_CHRONIC_GAP"
        rows.append(
            {
                "cell_id": cell_id,
                "sensor": sensor,
                "zero_event_years": "|".join(str(y) for y in zero_years),
                "max_consecutive_zero_years": longest,
                "common_era_years": common_years,
                "common_era_zero_years": common_zero,
                "gap_class": chronic,
            }
        )
    return pd.DataFrame.from_records(rows)


def cell_events_union(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Concat family join outputs and de-duplicate cell x event pairs.

    If an event covers a cell fully through any family geometry, FULL wins.
    """
    if not frames:
        return pd.DataFrame(columns=list(CELL_EVENT_COLUMNS))
    merged = pd.concat(frames, ignore_index=True, sort=False)
    merged["coverage_rank"] = (
        cast(pd.Series, merged["coverage"]).map({FULL_COVER: 0, PARTIAL_COVER: 1})
    )
    merged = merged.sort_values(["cell_id", "event_id", "coverage_rank"])
    merged = merged.drop_duplicates(["cell_id", "event_id"], keep="first")
    merged = merged.drop(columns=["coverage_rank"])
    return cast(pd.DataFrame, merged[list(CELL_EVENT_COLUMNS)].reset_index(drop=True))
