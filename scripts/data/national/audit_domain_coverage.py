"""Island-cell audit and W5/W10/W20 coverage diagnostic (local, no GEE).

Outputs:
* work CSV with the W10 island/mainland cell classification;
* tracked JSON summary under docs/data/national/DOMAIN_COVERAGE_AUDIT_v0.json
  (counts only; no bytes).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box

from spartina.data.national.census_join import (
    FULL_COVER,
    join_landsat_family,
    join_s1_scenes,
    join_s2_granules,
    load_cells,
)
from spartina.data.national.coastal_domain import build_china_land
from spartina.data.national.grid import CHINA_ALBERS_PROJ4

WIDTHS = (5000, 10000, 20000)
LANDSAT_SENSORS = ("landsat5", "landsat7", "landsat8", "landsat9")


def _git_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()


def classify_island_cells(
    cells: gpd.GeoDataFrame,
    gshhs_path: Path,
    admin_path: Path,
) -> pd.DataFrame:
    # Pre-clip source layers to the regional bbox in WGS84: unioning the
    # whole world in Albers triggers GEOS topology errors at projection
    # edges, and only near-China polygons affect island attribution.
    bbox = (100.0, 5.0, 135.0, 50.0)
    region = box(*bbox)
    gshhs = gpd.read_file(gshhs_path, engine="pyogrio", bbox=bbox)
    admin = gpd.read_file(admin_path, engine="pyogrio", bbox=bbox)
    # Clip geometries themselves to the region so projected coordinates
    # never approach the Albers anti-meridian edge.
    gshhs = gshhs.set_geometry(gshhs.geometry.intersection(region))
    admin = admin.set_geometry(admin.geometry.intersection(region))
    china = build_china_land(gshhs, admin, CHINA_ALBERS_PROJ4)
    cells_albers = cast(gpd.GeoDataFrame, cells.to_crs(CHINA_ALBERS_PROJ4))
    geoms = cast(gpd.GeoSeries, cells_albers.geometry)
    on_mainland = geoms.intersects(china.mainland).to_numpy()
    on_island = geoms.intersects(china.land.difference(china.mainland)).to_numpy()
    classes = np.where(
        on_mainland & on_island,
        "MAINLAND_AND_ISLAND",
        np.where(on_mainland, "MAINLAND", "ISLAND_ONLY"),
    )
    return pd.DataFrame(
        {"cell_id": cells["cell_id"], "land_class": classes}
    )


def width_diagnostic(
    width: int,
    census_dir: Path,
    footprint_dir: Path,
    domain_dir: Path,
) -> dict[str, Any]:
    cells = load_cells(domain_dir / f"cells_china_albers_W{width}.csv", width_m=width)
    frames = cast(
        gpd.GeoDataFrame,
        gpd.read_file(footprint_dir / "wrs2_china_coast.gpkg", engine="pyogrio"),
    )
    tiles = cast(
        gpd.GeoDataFrame,
        gpd.read_file(footprint_dir / "mgrs_china_coast.gpkg", engine="pyogrio"),
    )
    landsat = pd.concat(
        [
            pd.read_parquet(census_dir / f"scene_census_{sensor}_v0.parquet")
            for sensor in LANDSAT_SENSORS
        ],
        ignore_index=True,
    )
    l_pairs, extended = join_landsat_family(landsat, frames, cells)
    s2_pairs = join_s2_granules(
        pd.read_parquet(census_dir / "scene_census_sentinel2_v0.parquet"),
        tiles,
        cells,
    )
    s1_scenes = cast(
        gpd.GeoDataFrame,
        gpd.read_parquet(census_dir / "scene_census_sentinel1_v0.parquet"),
    )
    s1_pairs = join_s1_scenes(s1_scenes, cells)
    pairs = pd.concat(
        [cast(pd.DataFrame, l_pairs), s2_pairs, s1_pairs], ignore_index=True
    )

    per_sensor: dict[str, dict[str, Any]] = {}
    for sensor in ("landsat8", "sentinel2", "sentinel1"):
        sub = pairs[cast(pd.Series, pairs["sensor"]) == sensor]
        counts = (
            sub.groupby(["cell_id", "year"])["event_id"]
            .nunique()
            .rename("n")
            .reset_index()
        )
        values = cast(pd.Series, counts["n"]).to_numpy(dtype=float)
        per_sensor[sensor] = {
            "cell_event_pairs": int(len(sub)),
            "cells_ever_observed": int(sub["cell_id"].nunique()),
            "events_per_cell_year_p50": float(np.median(values))
            if len(values)
            else 0.0,
            "full_cover_pair_fraction": round(
                float((sub["coverage"] == FULL_COVER).mean()), 4
            )
            if len(sub)
            else 0.0,
        }
    observed = pairs[pairs["year"].between(2015, 2025)]["cell_id"].nunique()
    return {
        "width_m": width,
        "n_cells": int(len(cells)),
        "l7_extended_excluded_scenes": extended,
        "cells_with_any_event_2015_2025": int(observed),
        "cells_never_observed_2015_2025": int(len(cells) - observed),
        "per_sensor": per_sensor,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--census-dir", type=Path, default=Path("work/national/census"))
    parser.add_argument(
        "--footprint-dir", type=Path, default=Path("work/national/footprints")
    )
    parser.add_argument("--domain-dir", type=Path, default=Path("work/national/domain"))
    parser.add_argument(
        "--gshhs",
        type=Path,
        default=Path(
            "work/external/gshhg_2_3_7/extracted/GSHHS_shp/h/GSHHS_h_L1.shp"
        ),
    )
    parser.add_argument(
        "--admin0",
        type=Path,
        default=Path(
            "work/external/naturalearth_10m_admin0/extracted/"
            "ne_10m_admin_0_countries.shp"
        ),
    )
    parser.add_argument(
        "--out-json",
        type=Path,
        default=Path("docs/data/national/DOMAIN_COVERAGE_AUDIT_v0.json"),
    )
    args = parser.parse_args()

    cells_w10 = load_cells(args.domain_dir / "cells_china_albers_W10000.csv")
    classes = classify_island_cells(cells_w10, args.gshhs, args.admin0)
    classes_path = args.census_dir / "island_cell_classification_W10000.csv"
    classes.to_csv(classes_path, index=False)

    cell_events = pd.read_parquet(
        args.census_dir / "china_cell_event_census_v0.parquet"
    )
    common = cell_events[cast(pd.Series, cell_events["year"]).between(2015, 2025)]
    observed_cells = set(common["cell_id"].unique())
    classes["observed_2015_2025"] = classes["cell_id"].isin(observed_cells)
    island_table: dict[str, dict[str, Any]] = {}
    for name, group in classes.groupby("land_class"):
        island_table[str(name)] = {
            "n_cells": int(len(group)),
            "n_observed_2015_2025": int(group["observed_2015_2025"].sum()),
            "fraction_observed": round(
                float(group["observed_2015_2025"].mean()), 4
            ),
        }

    never_ids = sorted(set(cells_w10["cell_id"]) - observed_cells)
    centers = pd.read_csv(args.domain_dir / "cells_china_albers_W10000.csv")
    never_detail = centers[centers["cell_id"].isin(never_ids)][
        ["cell_id", "center_lon", "center_lat", "intersection_area_m2"]
    ]

    width_tables = [
        width_diagnostic(width, args.census_dir, args.footprint_dir, args.domain_dir)
        for width in WIDTHS
    ]

    result = {
        "product": "domain_coverage_audit_v0",
        "git_commit": _git_commit(),
        "domain_term": "mainland China coastal domain v0",
        "island_rule": (
            "cell intersects added islands (GSHHS within 25 km of China, "
            "area <= 100 km2, not in another admin polygon); MAINLAND vs "
            "ISLAND_ONLY vs mixed"
        ),
        "w10_land_classes": island_table,
        "never_observed_w10_cells": {
            "n": len(never_ids),
            "cell_ids": never_ids,
            "centers": never_detail.to_dict("records"),
        },
        "width_diagnostics": width_tables,
        "classification_csv": str(classes_path),
    }
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
