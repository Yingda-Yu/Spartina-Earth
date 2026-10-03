"""Deterministic 12-24 cell selection for the first-pixel pilot (DESIGN ONLY).

No pixels are downloaded by this script. It consumes the census/strata
products already built locally and picks a stratified, geometry-edge
balanced set of W10 cells for the pilot, ordered by
``SHA256(seed | cell_id)`` so the choice is reproducible and cannot be
hand-tuned to flattering locations.

Output: docs/data/national/FIRST_PIXEL_PILOT_DESIGN_v0.json,
status SELECTION_DESIGNED_NOT_EXECUTED.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import geopandas as gpd
import pandas as pd

# Fixed seed; changing it changes the panel, so it is pinned here.
PILOT_SEED = "spartina-earth-first-pixel-pilot-v0"
PILOT_YEAR = 2024

# Quotas sum to 20 cells (within the mandated 12-24 range).
QUOTAS: tuple[tuple[str, str, int], ...] = (
    ("stratum", "MULTI_PRODUCT_SILVER_POSITIVE", 3),
    ("stratum", "SILVER_2015_POSITIVE_ONLY", 3),
    ("stratum", "CMSSM_2020_POSITIVE_ONLY", 3),
    ("stratum", "NEAR_SILVER_UNLABELED", 3),
    ("stratum", "UNLABELED_COASTAL", 3),
    ("edge", "ISLAND_ONLY", 2),
    ("edge", "MGRS_GRID_EDGE_TILE", 1),
    ("edge", "MULTI_MGRS_ZONE_CELL", 1),
    ("edge", "MULTI_WRS_FRAME_CELL", 1),
)


def _git_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()


def _rank(cell_id: str) -> str:
    return hashlib.sha256(f"{PILOT_SEED}|{cell_id}".encode()).hexdigest()


def cell_edge_flags(
    cells: gpd.GeoDataFrame,
    frames: gpd.GeoDataFrame,
    tiles: gpd.GeoDataFrame,
    island_classes: pd.DataFrame,
) -> pd.DataFrame:
    frame_join = gpd.sjoin(
        cells[["cell_id", "geometry"]],
        frames[["frame_id", "geometry"]],
        how="left",
        predicate="intersects",
    )
    wrs_counts = frame_join.groupby("cell_id")["frame_id"].nunique()
    tile_join = gpd.sjoin(
        cells[["cell_id", "geometry"]],
        tiles[["mgrs_tile", "utm_zone", "grid_edge_overlap", "geometry"]],
        how="left",
        predicate="intersects",
    )
    tile_counts = tile_join.groupby("cell_id")["mgrs_tile"].nunique()
    zone_counts = tile_join.groupby("cell_id")["utm_zone"].nunique()
    edge_tiles = tile_join[
        cast(pd.Series, tile_join["grid_edge_overlap"]) == 1
    ].groupby("cell_id").size()
    flags = pd.DataFrame({"cell_id": cells["cell_id"]})
    flags = flags.merge(island_classes, on="cell_id", how="left")
    flags["n_wrs_frames"] = flags["cell_id"].map(wrs_counts).fillna(0).astype(int)
    flags["n_mgrs_tiles"] = flags["cell_id"].map(tile_counts).fillna(0).astype(int)
    flags["n_mgrs_zones"] = flags["cell_id"].map(zone_counts).fillna(0).astype(int)
    flags["n_edge_tiles"] = (
        flags["cell_id"].map(edge_tiles).fillna(0).astype(int)
    )
    flags["MULTI_WRS_FRAME_CELL"] = flags["n_wrs_frames"] >= 2
    flags["MULTI_MGRS_ZONE_CELL"] = flags["n_mgrs_zones"] >= 2
    flags["MGRS_GRID_EDGE_TILE"] = flags["n_edge_tiles"] >= 1
    flags["ISLAND_ONLY"] = (
        flags["land_class"].fillna("").eq("ISLAND_ONLY")
    )
    return flags


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--census-dir", type=Path, default=Path("work/national/census"))
    parser.add_argument(
        "--footprint-dir", type=Path, default=Path("work/national/footprints")
    )
    parser.add_argument("--domain-dir", type=Path, default=Path("work/national/domain"))
    parser.add_argument(
        "--strata-csv",
        type=Path,
        default=Path("work/national/strata/strata_china_albers_W10000.csv"),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("docs/data/national/FIRST_PIXEL_PILOT_DESIGN_v0.json"),
    )
    args = parser.parse_args()

    from spartina.data.national.census_join import load_cells

    cells = load_cells(args.domain_dir / "cells_china_albers_W10000.csv")
    frames = cast(
        gpd.GeoDataFrame,
        gpd.read_file(args.footprint_dir / "wrs2_china_coast.gpkg", engine="pyogrio"),
    )
    tiles = cast(
        gpd.GeoDataFrame,
        gpd.read_file(args.footprint_dir / "mgrs_china_coast.gpkg", engine="pyogrio"),
    )
    island_classes = pd.read_csv(
        args.census_dir / "island_cell_classification_W10000.csv"
    )
    strata = pd.read_csv(args.strata_csv)[["cell_id", "exclusive_stratum"]]
    availability = pd.read_csv(
        args.census_dir / "china_eo_availability_v0.csv"
    )
    s2_year = availability[
        (cast(pd.Series, availability["sensor"]) == "sentinel2")
        & (cast(pd.Series, availability["year"]) == PILOT_YEAR)
    ][["cell_id", "n_events"]].rename(columns={"n_events": "s2_events_year"})

    flags = cell_edge_flags(cells, frames, tiles, island_classes)
    table = flags.merge(strata, on="cell_id", how="left").merge(
        s2_year, on="cell_id", how="left"
    )
    table["rank"] = table["cell_id"].map(_rank)
    table = table.sort_values("rank")

    selected: list[dict[str, Any]] = []
    chosen: set[str] = set()
    quota_log: list[dict[str, Any]] = []
    for kind, value, quota in QUOTAS:
        if kind == "stratum":
            pool = cast(pd.DataFrame, table[table["exclusive_stratum"] == value])
        else:
            # Edge pools are boolean membership flags, not string labels.
            pool = cast(
                pd.DataFrame,
                table[cast(pd.Series, table[value]).fillna(False).astype(bool)],
            )
        picked = 0
        for record in pool.itertuples(index=False):
            cell_id = cast(Any, record).cell_id
            if cell_id in chosen:
                continue
            chosen.add(str(cell_id))
            selected.append(
                {
                    "cell_id": str(cell_id),
                    "selected_for": f"{kind}:{value}",
                    "exclusive_stratum": cast(Any, record).exclusive_stratum,
                    "s2_events_pilot_year": int(
                        cast(Any, record).s2_events_year
                    )
                    if not pd.isna(cast(Any, record).s2_events_year)
                    else 0,
                    "n_wrs_frames": int(cast(Any, record).n_wrs_frames),
                    "n_mgrs_tiles": int(cast(Any, record).n_mgrs_tiles),
                    "n_mgrs_zones": int(cast(Any, record).n_mgrs_zones),
                    "n_edge_tiles": int(cast(Any, record).n_edge_tiles),
                    "land_class": cast(Any, record).land_class,
                    "rank": cast(Any, record).rank,
                }
            )
            picked += 1
            if picked == quota:
                break
        quota_log.append(
            {"category": f"{kind}:{value}", "quota": quota, "filled": picked}
        )

    centers = pd.read_csv(args.domain_dir / "cells_china_albers_W10000.csv")[
        ["cell_id", "center_lon", "center_lat"]
    ]
    for record in selected:
        center = centers[centers["cell_id"] == record["cell_id"]].iloc[0]
        record["center_lon"] = float(center["center_lon"])
        record["center_lat"] = float(center["center_lat"])

    result = {
        "product": "first_pixel_pilot_design_v0",
        "status": "SELECTION_DESIGNED_NOT_EXECUTED",
        "git_commit": _git_commit(),
        "seed": PILOT_SEED,
        "ranking": "sha256(seed | cell_id), ascending, pool-quota fill",
        "pilot_first_sensor_year": f"sentinel2:{PILOT_YEAR}",
        "pixel_policy": "metadata only so far; NO pixel download authorized",
        "quota_log": quota_log,
        "n_selected": len(selected),
        "selected_cells": selected,
        "design_notes": [
            "Stage A: Sentinel-2 single year; validate Albers cell export "
            "vs actual MGRS granule geometry, multi-tile and multi-zone "
            "compositing and projection checks.",
            "Stage B (later, separate approval): Landsat C02 L2 and "
            "Sentinel-1 GRD dB (already dB; no second 10log10).",
            "No cell was dropped for zero cloud-free scenes; selection "
            "pre-dates any pixel evidence.",
        ],
    }
    args.out.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(quota_log, indent=2))
    print(f"selected {len(selected)} cells -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
