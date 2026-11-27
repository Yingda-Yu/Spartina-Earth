"""Build the four national census products from local caches (no GEE).

Inputs (ignored ``work/`` tree):
* ``scene_census_<sensor>_v0.parquet`` from the two fetch scripts;
* ``resource_ledger_optical_v0.json`` / ``resource_ledger_s1_v0.json``;
* WRS-2 and MGRS index geopackages and the W10 cell list.

Outputs:
* ``china_eo_scene_census_v0.parquet`` -- one row per scene/granule;
* ``china_cell_event_census_v0.parquet`` -- cell x ObservationEvent pairs;
* ``china_eo_availability_v0.csv`` -- cell x year x sensor status/counts;
* ``china_eo_data_gap_matrix_v0.csv`` -- zero-event years + chronic flags;
* ``china_eo_census_report_v0.json`` -- aggregate evidence summary.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import cast

import geopandas as gpd
import numpy as np
import pandas as pd

from spartina.data.national.census_join import (
    build_availability,
    cell_events_union,
    chronic_gap_flags,
    join_landsat_family,
    join_s1_scenes,
    join_s2_granules,
    load_cells,
)

LANDSAT_SENSORS = ("landsat5", "landsat7", "landsat8", "landsat9")
OPTICAL_SENSORS = (*LANDSAT_SENSORS, "sentinel2")


def _git_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _failed_scopes(census_dir: Path) -> tuple[set[str], set[str]]:
    """Return (optical failed sensor:year, s1 fully-failed years)."""
    optical_failed: set[str] = set()
    ledger_path = census_dir / "resource_ledger_optical_v0.json"
    if ledger_path.exists():
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        scopes: dict[str, set[str]] = {}
        for call in ledger["calls"]:
            bucket = scopes.setdefault(call["scope"], set())
            bucket.add("ok" if call["ok"] else "fail")
        for scope, states in scopes.items():
            if states == {"fail"}:
                optical_failed.add(scope)
    s1_failed_years: set[str] = set()
    s1_ledger_path = census_dir / "resource_ledger_s1_v0.json"
    if s1_ledger_path.exists():
        ledger = json.loads(s1_ledger_path.read_text(encoding="utf-8"))
        per_year: dict[str, set[str]] = {}
        for call in ledger["calls"]:
            period, pass_name = call["scope"].split("-", 1)
            year = period[:4] if period[:4].isdigit() else period
            bucket = per_year.setdefault(year, set())
            # Half-year fallback scopes (2019H1/H2) mark the year rescued:
            # a failed yearly batch plus successful halves is NOT a gap.
            bucket.add(f"{pass_name}:{'ok' if call['ok'] else 'fail'}")
        for year, states in per_year.items():
            if states == {"ASC:fail", "DESC:fail"}:
                s1_failed_years.add(year)
    return optical_failed, s1_failed_years


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--census-dir", type=Path, default=Path("work/national/census"))
    parser.add_argument(
        "--footprint-dir", type=Path, default=Path("work/national/footprints")
    )
    parser.add_argument(
        "--cells-csv",
        type=Path,
        default=Path("work/national/domain/cells_china_albers_W10000.csv"),
    )
    parser.add_argument("--year-start", type=int, default=1984)
    parser.add_argument("--year-end", type=int, default=2025)
    args = parser.parse_args()

    cells = load_cells(args.cells_csv)
    frames = cast(
        gpd.GeoDataFrame,
        gpd.read_file(args.footprint_dir / "wrs2_china_coast.gpkg", engine="pyogrio"),
    )
    tiles = cast(
        gpd.GeoDataFrame,
        gpd.read_file(args.footprint_dir / "mgrs_china_coast.gpkg", engine="pyogrio"),
    )

    scene_frames: list[pd.DataFrame] = []
    pair_frames: list[pd.DataFrame] = []
    sensor_scene_counts: dict[str, int] = {}
    extended_l7 = 0

    for sensor in LANDSAT_SENSORS:
        path = args.census_dir / f"scene_census_{sensor}_v0.parquet"
        if not path.exists():
            print(f"MISSING {path}", flush=True)
            continue
        scenes = pd.read_parquet(path)
        sensor_scene_counts[sensor] = len(scenes)
        scene_frames.append(
            cast(pd.DataFrame, scenes)
        )
        pairs, extended = join_landsat_family(scenes, frames, cells)
        extended_l7 += extended
        pair_frames.append(pairs)

    s2_path = args.census_dir / "scene_census_sentinel2_v0.parquet"
    if s2_path.exists():
        s2_scenes = pd.read_parquet(s2_path)
        sensor_scene_counts["sentinel2"] = len(s2_scenes)
        scene_frames.append(cast(pd.DataFrame, s2_scenes))
        pair_frames.append(join_s2_granules(s2_scenes, tiles, cells))

    s1_path = args.census_dir / "scene_census_sentinel1_v0.parquet"
    s1_scenes: gpd.GeoDataFrame | None = None
    if s1_path.exists():
        s1_scenes = cast(gpd.GeoDataFrame, gpd.read_parquet(s1_path))
        sensor_scene_counts["sentinel1"] = len(s1_scenes)
        s1_attrs = pd.DataFrame(s1_scenes.drop(columns="geometry"))
        scene_frames.append(s1_attrs)
        pair_frames.append(join_s1_scenes(s1_scenes, cells))

    cell_events = cell_events_union(pair_frames)
    optical_failed, s1_failed_years = _failed_scopes(args.census_dir)
    failed_scopes = set(optical_failed)
    failed_scopes.update(f"sentinel1:{year}" for year in s1_failed_years)

    availability = build_availability(
        cell_events,
        cast("pd.Series[str]", cells["cell_id"]),
        args.year_start,
        args.year_end,
        failed_scopes,
    )
    gaps = chronic_gap_flags(availability)

    scene_census = pd.concat(scene_frames, ignore_index=True, sort=True)

    out = args.census_dir
    scene_census.to_parquet(out / "china_eo_scene_census_v0.parquet", engine="pyarrow")
    cell_events.to_parquet(
        out / "china_cell_event_census_v0.parquet", engine="pyarrow"
    )
    availability.to_csv(out / "china_eo_availability_v0.csv", index=False)
    gaps.to_csv(out / "china_eo_data_gap_matrix_v0.csv", index=False)

    # Aggregate evidence report (no invented numbers: bytes only).
    events_per_cell_year = (
        cell_events.groupby(["cell_id", "year", "sensor"])["event_id"]
        .nunique()
        .rename("n")
        .reset_index()
    )
    quantiles = [0.05, 0.5, 0.95]
    per_sensor_quantiles: dict[str, dict[str, float]] = {}
    for sensor, group in events_per_cell_year.groupby("sensor"):
        values = cast(pd.Series, group["n"]).to_numpy(dtype=float)
        per_sensor_quantiles[str(sensor)] = {
            f"p{int(q * 100):02d}": float(np.quantile(values, q))
            for q in quantiles
        }
    chronic_counts = {
        str(sensor): int(
            (
                cast(pd.Series, sub["gap_class"]) == "CHRONIC_ZERO_COMMON_ERA"
            ).sum()
        )
        for sensor, sub in gaps.groupby("sensor")
    }
    report = {
        "product": "china_eo_census_v0",
        "git_commit": _git_commit(),
        "grid": "mainland China coastal domain v0 / W10000 Albers (3319 cells)",
        "scene_counts": sensor_scene_counts,
        "unique_scenes_total": int(scene_census["event_id"].nunique())
        if "event_id" in scene_census.columns
        else 0,
        "cell_event_pairs": len(cell_events),
        "l7_extended_excluded_scenes": extended_l7,
        "failed_scopes": sorted(failed_scopes),
        "events_per_cell_year_quantiles": per_sensor_quantiles,
        "chronic_zero_cells_common_era": chronic_counts,
        "availability_rows": len(availability),
        "gap_rows": len(gaps),
        "s1_note": (
            "GEE S1_GRD over the domain is overwhelmingly ASCENDING; "
            "DESCENDING count verified 2023 at three sites"
        ),
    }
    (out / "china_eo_census_report_v0.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
