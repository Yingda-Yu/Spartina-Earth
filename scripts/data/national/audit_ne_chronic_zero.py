#!/usr/bin/env python3
"""R1 Part C: direct-evidence audit of the 23 NE chronic-zero W10 cells.

The v0 gap matrix flags exactly 23 cells (130.4-131.2 E, 41.9-42.7 N,
Tumen tripoint / Sea of Japan area) as CHRONIC_ZERO_COMMON_ERA for all
five modern sensors. This script bypasses every local prefilter index
and queries GEE DIRECTLY per cell (``filterBounds(cell_geometry)``) for
Landsat 7/8/9, Sentinel-2 and Sentinel-1 (pass split) over 2015-2025,
plus the Murray et al. intertidal mask. Local GIS evidence covers
admin-0 intersection (Natural Earth), GSHHS land/coastline, the island
class table, and candidate WRS-2 / MGRS frames from the raw sources.

Each cell is classified as exactly one of:
INDEX_MISS | VALID_COASTAL_ZERO | DOMAIN_EDGE_ARTIFACT |
MIXED_ADMIN_COAST_ARTIFACT | UNRESOLVED.

Metadata-only; export guard installed. Output: tracked manifest CSV
``datasets/manifests/china_ne_chronic_zero_audit_v0.csv`` plus a JSON
companion with run metadata and per-sensor union evidence.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import mgrs
import pandas as pd
from shapely.geometry import box, mapping
from shapely.ops import unary_union

from spartina.data.gee.auth import initialize
from spartina.data.national.census_join import load_cells
from spartina.data.zhejiang.census import install_export_guard

INTERTIDAL_ASSET = "UQ/murray/Intertidal/v1_1/global_intertidal"
WORLD_CLIP = box(100.0, 5.0, 135.0, 50.0)
YEARS_START, YEARS_END = "2015-01-01", "2026-01-01"
OPTICAL_COLLECTIONS = {
    "landsat7": "LANDSAT/LE07/C02/T1_L2",
    "landsat8": "LANDSAT/LC08/C02/T1_L2",
    "landsat9": "LANDSAT/LC09/C02/T1_L2",
    "sentinel2": "COPERNICUS/S2_SR_HARMONIZED",
}
S1_COLLECTION = "COPERNICUS/S1_GRD"

# Sample offsets (degrees) for MGRS tile enumeration around a cell.
MGRS_OFFSETS = (
    (0.0, 0.0),
    (0.15, 0.0),
    (-0.15, 0.0),
    (0.0, 0.13),
    (0.0, -0.13),
    (0.15, 0.13),
    (-0.15, 0.13),
    (0.15, -0.13),
    (-0.15, -0.13),
)


def _git_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def local_gis_evidence(
    cells: gpd.GeoDataFrame,
    admin_path: Path,
    gshhs_path: Path,
    wrs_path: Path,
    v0_wrs: set[str],
    v0_mgrs: set[str],
    island_classes: dict[str, str],
) -> list[dict[str, Any]]:
    admin = gpd.read_file(admin_path, engine="pyogrio")
    admin = admin.clip(WORLD_CLIP)
    land = gpd.read_file(gshhs_path, engine="pyogrio").clip(WORLD_CLIP)
    wrs = gpd.read_file(wrs_path, engine="pyogrio")
    m = mgrs.MGRS()
    rows: list[dict[str, Any]] = []
    for _, cell in cells.iterrows():
        geom = cell.geometry
        cell_area = geom.area
        # Admin intersection.
        hits = gpd.sjoin(
            admin[["ADMIN", "ISO_A3", "geometry"]],
            gpd.GeoDataFrame(geometry=[geom], crs="EPSG:4326"),
            how="inner",
            predicate="intersects",
        )
        countries = sorted(set(hits["ADMIN"].astype(str)))
        china_area = 0.0
        foreign: dict[str, float] = {}
        china_rows = admin[admin["ADMIN"] == "China"]
        if not china_rows.empty:
            inter_cn = unary_union(list(china_rows.geometry)).intersection(geom)
            china_area = inter_cn.area
        for _, row in hits.iterrows():
            name = str(row["ADMIN"])
            if name == "China":
                continue
            other = admin[admin["ADMIN"] == name]
            inter = unary_union(list(other.geometry)).intersection(geom)
            foreign[name] = round(inter.area, 9)
        # GSHHS land / coastline evidence.
        land_hits = gpd.sjoin(
            land,
            gpd.GeoDataFrame(geometry=[geom], crs="EPSG:4326"),
            how="inner",
            predicate="intersects",
        )
        land_area = 0.0
        if not land_hits.empty:
            land_union = unary_union(list(land_hits.geometry)).intersection(geom)
            land_area = land_union.area
        coast_dist_km = float(land.distance(geom).min()) * 111.0
        # WRS-2 frames actually intersecting the cell.
        frame_hits = gpd.sjoin(
            wrs[["PATH", "ROW", "WRSPR", "geometry"]],
            gpd.GeoDataFrame(geometry=[geom], crs="EPSG:4326"),
            how="inner",
            predicate="intersects",
        )
        frames = sorted(
            f"WRS2-D-P{int(p):03d}-R{int(r):03d}"
            for p, r in zip(frame_hits["PATH"], frame_hits["ROW"], strict=True)
        )
        # MGRS tiles: enumerate by sampled points in/around the cell.
        lon0, lat0 = geom.centroid.x, geom.centroid.y
        tiles: set[str] = set()
        for dl, da in MGRS_OFFSETS:
            tile = m.toMGRS(lat0 + da, lon0 + dl, MGRSPrecision=0)[:5]
            tiles.add(tile)
        rows.append(
            {
                "cell_id": cell["cell_id"],
                "centroid_lon": round(lon0, 6),
                "centroid_lat": round(lat0, 6),
                "china_admin_area_frac": round(china_area / cell_area, 4),
                "admin_countries": "|".join(countries),
                "foreign_admin_area_frac": {
                    k: round(v / cell_area, 4) for k, v in foreign.items()
                },
                "land_area_frac": round(land_area / cell_area, 4),
                "coastline_min_distance_km": round(coast_dist_km, 2),
                "island_class": island_classes.get(str(cell["cell_id"]), "UNKNOWN"),
                "wrs_candidate_frames": "|".join(frames),
                "wrs_candidates_not_in_v0": "|".join(
                    f for f in frames if f not in v0_wrs
                ),
                "mgrs_candidate_tiles": "|".join(sorted(tiles)),
                "mgrs_candidates_not_in_v0": "|".join(
                    sorted(t for t in tiles if t not in v0_mgrs)
                ),
            }
        )
    return rows


def direct_gee_counts(ee: Any, geom: Any) -> dict[str, int]:
    """One .size() per sensor, bypassing all indices; S1 pass split."""
    out: dict[str, int] = {}
    for name, collection_id in OPTICAL_COLLECTIONS.items():
        count = (
            ee.ImageCollection(collection_id)
            .filterBounds(geom)
            .filterDate(YEARS_START, YEARS_END)
            .size()
            .getInfo()
        )
        out[name] = int(count)
    s1 = (
        ee.ImageCollection(S1_COLLECTION)
        .filterBounds(geom)
        .filterDate(YEARS_START, YEARS_END)
    )
    out["s1"] = int(s1.size().getInfo())
    out["s1_asc"] = int(
        s1.filter(ee.Filter.eq("orbitProperties_pass", "ASCENDING"))
        .size()
        .getInfo()
    )
    out["s1_desc"] = int(
        s1.filter(ee.Filter.eq("orbitProperties_pass", "DESCENDING"))
        .size()
        .getInfo()
    )
    return out


def intertidal_evidence(ee: Any, geom: Any) -> dict[str, Any]:
    """Murray v1.1 intertidal mask is published as a tiled ImageCollection."""
    try:
        collection = ee.ImageCollection(INTERTIDAL_ASSET)
        n_tiles = int(collection.size().getInfo())
        image = collection.mosaic()
        result = image.reduceRegion(
            reducer=ee.Reducer.count(),
            geometry=geom,
            scale=30000,
            bestEffort=True,
        ).getInfo()
        counts = {k: int(v) for k, v in result.items() if isinstance(v, int | float)}
        return {
            "tiles_in_asset": n_tiles,
            "bands": list(counts),
            "max_count": max(counts.values(), default=0),
        }
    except Exception as exc:  # noqa: BLE001 - UNKNOWN is a valid audit result
        return {"error": f"{type(exc).__name__}: {str(exc)[:160]}"}


def classify(row: dict[str, Any]) -> tuple[str, str]:
    n_optical = sum(int(row.get(s) or 0) for s in OPTICAL_COLLECTIONS)
    n_s1 = int(row.get("s1") or 0)
    china_frac = float(row["china_admin_area_frac"])
    land_frac = float(row["land_area_frac"])
    foreign = row["admin_countries"]
    foreign_names = [c for c in str(foreign).split("|") if c and c != "China"]
    if n_optical + n_s1 == 0 and china_frac > 0:
        return (
            "VALID_COASTAL_ZERO",
            "no direct sensor scenes yet cell intersects China admin; true void",
        )
    if n_optical + n_s1 > 0 and china_frac > 0:
        return (
            "INDEX_MISS",
            "direct GEE scenes exist and cell intersects China admin; "
            "nominal frames/tiles already present in v0 index -- root cause "
            "is the v0 fetch bbox (maxx=127 E) vs domain extent (132 E); "
            "v0_1 re-queries the affected range with cell-union prefilter",
        )
    if n_optical + n_s1 > 0 and china_frac == 0.0 and foreign_names:
        return (
            "MIXED_ADMIN_COAST_ARTIFACT",
            f"scenes exist but land/admin is foreign ({foreign_names}); "
            "cell entered domain via tripoint seaward/onshore buffer",
        )
    if china_frac == 0.0 and not foreign_names and land_frac < 0.05:
        return (
            "DOMAIN_EDGE_ARTIFACT",
            "no admin-0 land intersection (open Sea of Japan edge cell); "
            "sensor scenes still cover the water, which is why a query-bbox "
            "fix alone would not make it a valid China domain cell",
        )
    return ("UNRESOLVED", "conflicting/insufficient GIS and query evidence")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cells-csv",
        type=Path,
        default=Path("work/national/domain/cells_china_albers_W10000.csv"),
    )
    parser.add_argument(
        "--gap-matrix",
        type=Path,
        default=Path("work/national/census/china_eo_data_gap_matrix_v0.csv"),
    )
    parser.add_argument(
        "--pairs",
        type=Path,
        default=Path("work/national/census/china_cell_event_census_v0.parquet"),
    )
    parser.add_argument(
        "--admin",
        type=Path,
        default=Path(
            "work/external/naturalearth_10m_admin0/extracted/"
            "ne_10m_admin_0_countries.shp"
        ),
    )
    parser.add_argument(
        "--gshhs",
        type=Path,
        default=Path("work/sources/GSHHS_shp/h/GSHHS_h_L1.shp"),
    )
    parser.add_argument(
        "--wrs",
        type=Path,
        default=Path("work/national/footprints/source/WRS2_descending.shp"),
    )
    parser.add_argument(
        "--v0-wrs-index",
        type=Path,
        default=Path("work/national/footprints/wrs2_china_coast_index.csv"),
    )
    parser.add_argument(
        "--v0-mgrs-index",
        type=Path,
        default=Path("work/national/footprints/mgrs_china_coast_index.csv"),
    )
    parser.add_argument(
        "--island-class",
        type=Path,
        default=Path(
            "work/national/census/island_cell_classification_W10000.csv"
        ),
    )
    parser.add_argument(
        "--out-csv",
        type=Path,
        default=Path("datasets/manifests/china_ne_chronic_zero_audit_v0.csv"),
    )
    parser.add_argument(
        "--out-json",
        type=Path,
        default=Path("docs/data/national/NE_CHRONIC_ZERO_AUDIT_v0.json"),
    )
    parser.add_argument(
        "--work-json",
        type=Path,
        default=Path("work/national/census_r1/ne_chronic_zero_audit_v0.json"),
    )
    parser.add_argument("--no-gee", action="store_true")
    args = parser.parse_args()

    chronic_ids = sorted(
        set(
            pd.read_csv(args.gap_matrix)
            .query("gap_class == 'CHRONIC_ZERO_COMMON_ERA'")["cell_id"]
            .astype(str)
        )
    )
    assert len(chronic_ids) == 23, f"expected 23 cells, got {len(chronic_ids)}"
    cells = load_cells(args.cells_csv)
    cells = cells[cells["cell_id"].isin(chronic_ids)].copy()
    assert len(cells) == 23

    v0_wrs = set(pd.read_csv(args.v0_wrs_index)["frame_id"].astype(str))
    v0_mgrs = set(pd.read_csv(args.v0_mgrs_index)["mgrs_tile"].astype(str))
    island_df = pd.read_csv(args.island_class)
    class_col = next(
        c for c in island_df.columns if "class" in c.lower() or "stratum" in c.lower()
    )
    island_classes = dict(
        zip(island_df["cell_id"].astype(str), island_df[class_col].astype(str), strict=True)
    )

    rows = local_gis_evidence(
        cells, args.admin, args.gshhs, args.wrs, v0_wrs, v0_mgrs, island_classes
    )

    pairs = pd.read_parquet(args.pairs)
    pair_counts = (
        pairs[pairs["cell_id"].isin(chronic_ids)
        & pairs["year"].between(2015, 2025)]
        .groupby("cell_id")["event_id"]
        .nunique()
        .to_dict()
    )

    by_id = cells.set_index("cell_id")
    if args.no_gee:
        for row in rows:
            row.update(
                {s: None for s in [*OPTICAL_COLLECTIONS, "s1", "s1_asc", "s1_desc"]}
            )
            row["intertidal"] = None
    else:
        initialize()
        import ee

        install_export_guard(ee)

        for row in rows:
            cell_id = str(row["cell_id"])
            geom = ee.Geometry(mapping(by_id.loc[cell_id].geometry))
            started = time.perf_counter()
            row.update(direct_gee_counts(ee, geom))
            row["intertidal"] = intertidal_evidence(ee, geom)
            row["gee_query_s"] = round(time.perf_counter() - started, 2)
            print(
                f"{cell_id}: L8={row['landsat8']} S2={row['sentinel2']} "
                f"S1={row['s1']} (A{row['s1_asc']}/D{row['s1_desc']})",
                flush=True,
            )

    for row in rows:
        cell_id = str(row["cell_id"])
        row["v0_event_pairs_2015_2025"] = int(pair_counts.get(cell_id, 0))

    # Union-level evidence: which frames/tiles do the direct scenes use?
    union_info: dict[str, Any] = {}
    if not args.no_gee:
        union_geom = ee.Geometry(mapping(by_id.geometry.unary_union))
        for name, collection_id in OPTICAL_COLLECTIONS.items():
            coll = (
                ee.ImageCollection(collection_id)
                .filterBounds(union_geom)
                .filterDate(YEARS_START, YEARS_END)
            )
            key = "MGRS_TILE" if name == "sentinel2" else "WRS_PATH"
            values = coll.aggregate_array(key).getInfo()
            counts = (
                pd.Series(values, dtype="object").value_counts().head(30).to_dict()
            )
            union_info[name] = {str(k): int(v) for k, v in counts.items()}
        s1_orbits = (
            ee.ImageCollection(S1_COLLECTION)
            .filterBounds(union_geom)
            .filterDate(YEARS_START, YEARS_END)
            .aggregate_array("relativeOrbitNumber_start")
            .getInfo()
        )
        union_info["s1_relative_orbits"] = {
            str(k): int(v)
            for k, v in pd.Series(s1_orbits)
            .value_counts()
            .head(30)
            .items()
        }

    for row in rows:
        token, note = classify(row)
        row["classification"] = token
        row["classification_note"] = note

    # Geometry WKT column for the tracked manifest (23 small polygons).
    wkt_by_id = {cid: by_id.loc[cid].geometry.wkt for cid in chronic_ids}
    for row in rows:
        row["geometry_wkt"] = wkt_by_id[str(row["cell_id"])]
        inter = row.get("intertidal")
        row["intertidal_evidence"] = json.dumps(inter, ensure_ascii=False)
        row["foreign_admin_area_frac"] = json.dumps(
            row["foreign_admin_area_frac"], ensure_ascii=False
        )
        row.pop("intertidal", None)

    df = pd.DataFrame(rows)
    front = ["cell_id", "classification", "classification_note"]
    columns = front + [c for c in df.columns if c not in front]
    df = df[columns]
    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out_csv, index=False)

    summary = {
        "artifact": "ne_chronic_zero_cell_audit",
        "version": "v0",
        "generated_utc": datetime.now(tz=UTC).isoformat(),
        "git_commit": _git_commit(),
        "audit": "M2.3b-R1 PART C (Issue #16 blocker 3)",
        "n_cells": len(df),
        "class_counts": df["classification"].value_counts().to_dict(),
        "cells": df["cell_id"].tolist(),
        "direct_query_window": f"{YEARS_START}..{YEARS_END} (exclusive end)",
        "intertidal_asset": INTERTIDAL_ASSET,
        "intertidal_license": "Murray et al., CC BY 4.0",
        "union_footprint_evidence": union_info,
        "out_csv": str(args.out_csv),
    }
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.work_json.parent.mkdir(parents=True, exist_ok=True)
    args.work_json.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary["class_counts"], indent=2))
    print(f"-> {args.out_csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
