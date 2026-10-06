#!/usr/bin/env python3
"""Lightweight spatial consistency checks for newly accessioned labels.

Phase L of the external-label intake audit (see
docs/audit/CHINA_EXTERNAL_LABEL_INTAKE_AUDIT_V1.md). This is *not* an
accuracy assessment and not a change analysis: it allocates each
product's mapped area onto the immutable W10 coastal-cell grid, rolled
up by v1 membership token, and builds a cell-level three-product 2020
co-occurrence table.

Inputs live in the gitignored staging area (work/intake/staging) and the
pre-existing ``old datasets/`` directory; bytes are never copied into
Git. Outputs:

* work/intake/10_domain_allocation.json   (full, gitignored)
* datasets/manifests/china_label_domain_overlap_v1.csv (compact, tracked)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from shapely.geometry import box

from spartina.data.national.geometry import CHINA_ALBERS_CRS

REPO_ROOT = Path(__file__).resolve().parents[3]
STAGING = REPO_ROOT / "work/intake/staging"
WORK_OUT = REPO_ROOT / "work/intake/10_domain_allocation.json"
MANIFEST_OUT = REPO_ROOT / "datasets/manifests/china_label_domain_overlap_v1.csv"
GRID_CSV = REPO_ROOT / "work/national/domain/cells_china_albers_W10000.csv"
MEMBER_CSV = REPO_ROOT / "datasets/manifests/china_coastal_cells_v1_candidate.csv"
CM_SSM_SHP = (
    REPO_ROOT
    / "old datasets/30mSpartinaChina/2020/CM-SSM/CM-SSM.shp"
)
CMSA_DIR = STAGING / "中国大陆2017-2021互花米草CMSA"
GEODATA = {
    "GEODATA_1990": STAGING
    / "1990年中国滨海30 m分辨率互花米草空间分布动态数据集-数据实体"
    / "1990年中国滨海30 m分辨率互花米草空间分布动态数据集-数据实体.tif",
    "GEODATA_2000": STAGING
    / "2000年中国滨海30 m分辨率互花米草空间分布动态数据集-数据实体"
    / "2000年中国滨海30 m分辨率互花米草空间分布动态数据集-数据实体.tif",
    "GEODATA_2015": STAGING
    / "30m分辨率中国互花米草空间分布数据集(2015年)-数据实体"
    / "30m中国互花米草空间分布数据集(2015年)-数据实体.tif",
    "GEODATA_2020": STAGING
    / "2020年中国滨海30 m分辨率互花米草空间分布动态数据集-数据实体"
    / "2020年中国滨海30 m分辨率互花米草空间分布动态数据集-数据实体.tif",
}

# Native pixel area is treated as exactly 30 m x 30 m. The three Albers
# rasters are equal-area; the 2015 UTM raster pixel area is nominal and
# its totals are flagged in the audit doc.
NATIVE_PIXEL_M2 = 900.0


def load_cells() -> gpd.GeoDataFrame:
    frame = pd.read_csv(GRID_CSV)
    width = 10_000
    geometries = [
        box(int(r.col) * width, int(r.row) * width,
            (int(r.col) + 1) * width, (int(r.row) + 1) * width)
        for r in frame.itertuples(index=False)
    ]
    cells = gpd.GeoDataFrame(frame[["cell_id"]], geometry=geometries,
                             crs=CHINA_ALBERS_CRS)
    membership = pd.read_csv(MEMBER_CSV)[
        ["cell_id", "membership_v1_candidate"]
    ]
    merged = cells.merge(membership, on="cell_id", validate="one_to_one")
    return gpd.GeoDataFrame(merged, geometry="geometry", crs=CHINA_ALBERS_CRS)


def raster_positive_points(tif_path: Path) -> gpd.GeoDataFrame:
    """Centres of positive (value == 1) pixels, transformed to grid CRS."""
    xs: list[float] = []
    ys: list[float] = []
    with rasterio.open(tif_path) as ds:
        # Cell-centre coordinates in native CRS.
        for _, window in ds.block_windows(1):
            arr = ds.read(1, window=window)
            rows, cols = np.nonzero(arr == 1)
            if rows.size == 0:
                continue
            x = ds.transform.c + (
                window.col_off + cols.astype(np.float64) + 0.5
            ) * ds.transform.a
            y = ds.transform.f + (
                window.row_off + rows.astype(np.float64) + 0.5
            ) * ds.transform.e
            xs.extend(x.tolist())
            ys.extend(y.tolist())
        pts = gpd.GeoDataFrame(
            {"positive_pixels": np.ones(len(xs), dtype=np.int8)},
            geometry=gpd.points_from_xy(xs, ys),
            crs=ds.crs,
        )
    return pts.to_crs(CHINA_ALBERS_CRS)


def raster_allocation(
    cells: gpd.GeoDataFrame, tif_path: Path
) -> tuple[dict[str, int], pd.DataFrame, dict[str, object]]:
    pts = raster_positive_points(tif_path)
    joined = gpd.sjoin(
        pts[["geometry"]],
        cells[["cell_id", "membership_v1_candidate", "geometry"]],
        how="left", predicate="within",
    )
    per_cell = (
        joined.groupby("cell_id", dropna=True)
        .size()
        .rename("positive_pixels")
        .reset_index()
    )
    per_cell["mapped_area_m2"] = per_cell["positive_pixels"] * NATIVE_PIXEL_M2
    counts = {
        "KEEP": int(joined["membership_v1_candidate"]
                    .str.startswith("KEEP").sum()),
        "EXCLUDE": int(joined["membership_v1_candidate"]
                       .str.startswith("EXCLUDE").sum()),
        "PROVISIONAL": int(joined["membership_v1_candidate"]
                           .str.startswith("PROVISIONAL").sum()),
        "OUTSIDE_GRID": int(joined["cell_id"].isna().sum()),
    }
    diag = outside_diag_points(pts, cells.geometry.union_all())
    return counts, per_cell, diag


def outside_diag_points(
    pts: gpd.GeoDataFrame, union_cells: object
) -> dict[str, object]:
    """Characterise mapped elements falling outside the W10 corridor."""
    outside = pts.loc[~pts.within(union_cells)]
    if len(outside) == 0:
        return {"n_outside": 0}
    dist_km = outside.distance(union_cells) / 1000.0
    ll = outside.to_crs(4326)
    return {
        "n_outside": int(len(outside)),
        "lat_range": [round(float(ll.geometry.y.min()), 3),
                      round(float(ll.geometry.y.max()), 3)],
        "lon_range": [round(float(ll.geometry.x.min()), 3),
                      round(float(ll.geometry.x.max()), 3)],
        "distance_km_p50": round(float(dist_km.median()), 2),
        "distance_km_p95": round(float(dist_km.quantile(0.95)), 2),
        "distance_km_max": round(float(dist_km.max()), 2),
    }


def outside_diag_polygons(
    gdf: gpd.GeoDataFrame, union_cells: object
) -> dict[str, object]:
    outside = gdf.loc[~gdf.within(union_cells)]
    if len(outside) == 0:
        return {"n_outside": 0}
    dist_km = outside.distance(union_cells) / 1000.0
    ll = outside.representative_point().to_crs(4326)
    return {
        "n_outside": int(len(outside)),
        "lat_range": [round(float(ll.geometry.y.min()), 3),
                      round(float(ll.geometry.y.max()), 3)],
        "lon_range": [round(float(ll.geometry.x.min()), 3),
                      round(float(ll.geometry.x.max()), 3)],
        "distance_km_p95": round(float(dist_km.quantile(0.95)), 2),
        "distance_km_max": round(float(dist_km.max()), 2),
    }


def vector_allocation(
    cells: gpd.GeoDataFrame, gdf: gpd.GeoDataFrame, use_gridcode: int | None
) -> tuple[dict[str, float], pd.DataFrame, dict[str, object]]:
    """Exact (unprojected-after-transform) polygon-in-cell areas."""
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()
    if use_gridcode is not None and "gridcode" in gdf.columns:
        gdf = gdf[gdf["gridcode"] == use_gridcode].copy()
    gdf = gdf.to_crs(CHINA_ALBERS_CRS)
    joined = gpd.sjoin(
        gdf[["geometry"]],
        cells[["cell_id", "membership_v1_candidate", "geometry"]],
        how="left", predicate="intersects",
    )
    cell_geom = cells.set_index("cell_id")["geometry"]
    rows = []
    for cell_id, sub in joined.groupby("cell_id", dropna=True):
        poly = cell_geom.loc[cell_id]
        area = float(sub.geometry.intersection(poly).area.sum())
        rows.append((cell_id, area))
    per_cell = pd.DataFrame(rows, columns=["cell_id", "mapped_area_m2"])
    total_inside = float(per_cell["mapped_area_m2"].sum())
    total = float(gdf.geometry.area.sum())
    # Roll up by membership.
    roll = per_cell.merge(
        cells[["cell_id", "membership_v1_candidate"]], on="cell_id"
    )
    out = {
        "KEEP": float(
            roll.loc[roll.membership_v1_candidate.str.startswith("KEEP"),
                     "mapped_area_m2"].sum()
        ),
        "EXCLUDE": float(
            roll.loc[roll.membership_v1_candidate.str.startswith("EXCLUDE"),
                     "mapped_area_m2"].sum()
        ),
        "PROVISIONAL": float(
            roll.loc[
                roll.membership_v1_candidate.str.startswith("PROVISIONAL"),
                "mapped_area_m2",
            ].sum()
        ),
        "OUTSIDE_GRID": max(total - total_inside, 0.0),
    }
    diag = outside_diag_polygons(gdf, cells.geometry.union_all())
    return out, per_cell, diag


def main() -> None:
    cells = load_cells()
    result: dict[str, dict[str, Any]] = {}
    cell_areas: dict[str, pd.Series] = {}

    for name, tif in GEODATA.items():
        counts, per_cell, diag = raster_allocation(cells, tif)
        result[name] = {
            "unit": "positive_30m_pixels",
            "total": sum(counts.values()),
            "allocation": counts,
            "allocated_area_km2": {
                k: round(v * NATIVE_PIXEL_M2 / 1e6, 3)
                for k, v in counts.items()
            },
            "outside_grid_diagnostic": diag,
        }
        cell_areas[name] = per_cell.set_index("cell_id")["mapped_area_m2"]
        print(name, counts)

    for year in range(2017, 2022):
        shp = CMSA_DIR / f"CMSA_{year}.shp"
        gdf = gpd.read_file(shp)
        alloc, per_cell, diag = vector_allocation(cells, gdf, use_gridcode=2)
        result[f"CMSA_{year}"] = {
            "unit": "polygon_m2_gridcode2",
            "total_area_km2": round(
                alloc["KEEP"] + alloc["EXCLUDE"]
                + alloc["PROVISIONAL"] + alloc["OUTSIDE_GRID"], 3
            ),
            "allocated_area_km2": {
                k: round(v / 1e6, 3) for k, v in alloc.items()
            },
            "outside_grid_diagnostic": diag,
        }
        cell_areas[f"CMSA_{year}"] = per_cell.set_index(
            "cell_id"
        )["mapped_area_m2"]
        print(f"CMSA_{year}", result[f"CMSA_{year}"]["allocated_area_km2"])

    if CM_SSM_SHP.exists():
        gdf = gpd.read_file(CM_SSM_SHP)
        alloc, per_cell, diag = vector_allocation(cells, gdf, use_gridcode=None)
        result["CM_SSM_2020"] = {
            "unit": "polygon_m2",
            "total_area_km2": round(
                alloc["KEEP"] + alloc["EXCLUDE"]
                + alloc["PROVISIONAL"] + alloc["OUTSIDE_GRID"], 3
            ),
            "allocated_area_km2": {
                k: round(v / 1e6, 3) for k, v in alloc.items()
            },
            "outside_grid_diagnostic": diag,
        }
        cell_areas["CM_SSM_2020"] = per_cell.set_index(
            "cell_id"
        )["mapped_area_m2"]
        print("CM_SSM_2020", result["CM_SSM_2020"]["allocated_area_km2"])

    WORK_OUT.parent.mkdir(parents=True, exist_ok=True)

    # Compact tracked manifest: one row per product x bucket.
    rows = []
    for product, payload in result.items():
        if "allocated_area_km2" not in payload:
            continue
        for bucket, area_km2 in payload["allocated_area_km2"].items():
            rows.append({
                "product": product,
                "membership_bucket": bucket,
                "mapped_area_km2": area_km2,
                "basis": payload["unit"],
            })
    pd.DataFrame(rows).to_csv(MANIFEST_OUT, index=False)

    # Cell-level three-product 2020 co-occurrence (presence flags).
    grid_ids = pd.Index(cells["cell_id"])
    co = pd.DataFrame(
        {c: cell_areas[c].reindex(grid_ids).fillna(0.0)
         for c in ("GEODATA_2020", "CMSA_2020", "CM_SSM_2020")}
    )
    tbl = co.gt(0)
    combo = tbl.sum(axis=1).value_counts().sort_index()
    pattern = {
        f"n_products_present={int(k)}": int(v) for k, v in combo.items()
    }
    asymmetry = {}
    for n in (1, 2):
        sub = tbl.loc[tbl.sum(axis=1) == n]
        asymmetry[f"cells_with_exactly_{n}_products"] = {
            "n_cells": int(len(sub)),
            "by_product": {p: int(sub[p].sum()) for p in tbl.columns},
        }
    spearman = co.corr(method="spearman").round(3).to_dict()
    result["_2020_CROSS_PRODUCT"] = {
        "basis": "W10 cell presence/area in China Albers; diagnostic only",
        "co_occurrence": pattern,
        "asymmetry": asymmetry,
        "spearman_cell_area": spearman,
        "allocated_area_km2_in_grid": {
            c: round(float(co[c].sum()) / 1e6, 3) for c in co.columns
        },
    }
    print("2020 cell co-occurrence:", pattern)
    full = (
        co.join(cells.set_index("cell_id")["membership_v1_candidate"])
    )
    full.to_csv(REPO_ROOT / "work/intake/11_2020_cell_cooccurrence.csv")

    WORK_OUT.write_text(json.dumps(result, indent=1), encoding="utf-8")
    print("wrote", MANIFEST_OUT.relative_to(REPO_ROOT))


if __name__ == "__main__":
    main()
