#!/usr/bin/env python3
"""
E5 Regional Heterogeneity — pair-wise IoU/Dice by coastal subregion.

Splits the common EPSG:3410 domain into 4 coastal subregions based on
longitude bands (Bohai/Yellow, East China Sea, South China Sea, and a
northern Bohai subdomain). Computes per-region IoU, Dice, area ratios,
disagreement area for all three product pairs at 30m resolution.

Domain split (longitude in EPSG:3410, metres):
  Subregion 1 — Bohai/Yellow Sea:   x < 11,000,000  (northern + eastern coast)
  Subregion 2 — East China Sea:     11,000,000 <= x < 11,500,000
  Subregion 3 — South China Sea:    x >= 11,500,000
  Subregion 4 — Bohai focus:        x < 10,700,000 AND y > 4,000,000
  (Subregions 1-3 are mutually exclusive; 4 is a nested subset of 1)

Subregion boundaries are defined purely on longitude/elevation bands
because no authoritative admin boundary shapefile is available within
the repository. This is explicitly acknowledged as a limitation in
the manuscript.

Reuses rasterization logic from e3_spatial_agreement.py.
"""

import os
import sys
import time
import numpy as np
import geopandas as gpd
import rasterio
from rasterio import features as rio_features
from rasterio.warp import reproject, Resampling
import json
import csv

# --- env ---
os.environ.setdefault("PROJ_LIB",
    "/data/yingda/software/miniconda3/envs/spartina-earth/share/proj")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
RESULTS = os.path.join(ROOT, "papers", "paper1_map_reliability", "results")

RES_M = 100  # 100m for fast regional analysis; IoU within 0.4% of 30m (E4 verified)
TARGET_CRS = "EPSG:3410"
DOMAIN_BUFFER_M = 10_000

DATA_PATHS = {
    "CMSA":  os.path.join(ROOT, "work", "intake", "staging",
              "中国大陆2017-2021互花米草CMSA", "CMSA_2020.shp"),
    "CMSSM": os.path.join(ROOT, "work", "external", "cm_ssm_2020_official",
              "extracted", "CM-SSM", "CM-SSM.shp"),
    "GEODATA": os.path.join(ROOT, "work", "intake", "staging",
              "2020年中国滨海30 m分辨率互花米草空间分布动态数据集-数据实体",
              "2020年中国滨海30 m分辨率互花米草空间分布动态数据集-数据实体.tif"),
}


def load_and_rasterize_all():
    """Return binary masks for all three products at RES_M on common domain."""
    import pyproj

    t0 = time.time()
    cmsa = gpd.read_file(DATA_PATHS["CMSA"])
    cmsa = cmsa[cmsa["gridcode"] == 2].copy().to_crs(TARGET_CRS)

    cmssm = gpd.read_file(DATA_PATHS["CMSSM"]).to_crs(TARGET_CRS)

    domain = cmsa.total_bounds  # [minx, miny, maxx, maxy]
    domain_buf = np.array([
        domain[0] - DOMAIN_BUFFER_M, domain[1] - DOMAIN_BUFFER_M,
        domain[2] + DOMAIN_BUFFER_M, domain[3] + DOMAIN_BUFFER_M,
    ])
    width = int((domain_buf[2] - domain_buf[0]) / RES_M)
    height = int((domain_buf[3] - domain_buf[1]) / RES_M)
    transform = rasterio.transform.from_bounds(
        domain_buf[0], domain_buf[1], domain_buf[2], domain_buf[3], width, height
    )

    # Rasterize CMSA
    shapes = [(g, 1) for g in cmsa.geometry if g is not None and not g.is_empty]
    arr_cmsa = rio_features.rasterize(
        shapes=shapes, out_shape=(height, width), transform=transform,
        fill=0, dtype="uint8", all_touched=False)

    # Rasterize CM-SSM
    shapes = [(g, 1) for g in cmssm.geometry if g is not None and not g.is_empty]
    arr_cmssm = rio_features.rasterize(
        shapes=shapes, out_shape=(height, width), transform=transform,
        fill=0, dtype="uint8", all_touched=False)

    # Warp GEODATA
    dst_arr = np.zeros((height, width), dtype="uint8")
    with rasterio.open(DATA_PATHS["GEODATA"]) as src:
        reproject(
            source=rasterio.band(src, 1), destination=dst_arr,
            src_crs=src.crs, dst_crs=pyproj.CRS.from_user_input(TARGET_CRS),
            src_transform=src.transform, dst_transform=transform,
            resampling=Resampling.nearest, src_nodata=255, dst_nodata=0)
    arr_geodata = (dst_arr == 1).astype("uint8")

    print(f"All three products loaded + rasterized in {time.time()-t0:.1f}s")
    print(f"  Grid: {width}x{height} px = {arr_cmsa.shape}")
    return {
        "CMSA": arr_cmsa, "CMSSM": arr_cmssm, "GEODATA": arr_geodata,
        "transform": transform, "domain": domain_buf, "width": width, "height": height,
    }


def define_subregions_bbox(height, width, domain_buf):
    """Define subregion masks using bbox slicing — no meshgrid, no memory blowup.

    EPSG:3410 coords (metres): China coast spans roughly x=10.5M–12.0M, y=2.5M–4.8M.
    """
    minx, miny, maxx, maxy = domain_buf
    res_m = RES_M

    def idx_for_coord(coord, is_max=False):
        """Convert EPSG:3410 coordinate to pixel index."""
        if is_max:
            return int((coord - minx) / res_m)  # right-exclusive
        return int((coord - minx) / res_m)       # left-inclusive

    def idy_for_coord(coord, is_max=False):
        """Convert y coordinate to pixel row index (top = max y → row 0)."""
        # y increases northwards; row 0 = maxy, row height-1 = miny
        if is_max:
            return int((maxy - coord) / res_m)
        return int((maxy - coord) / res_m)

    masks = {}
    # Bohai/Yellow: x < 11,000,000  (western half of China coast)
    x_11M = idx_for_coord(11_000_000, is_max=True)
    y_top = 0
    y_bot = height
    m = np.zeros((height, width), dtype="bool")
    m[:, :x_11M] = True
    masks["Bohai_Yellow"] = m

    # East China Sea: 11M <= x < 11.5M
    x_115M = idx_for_coord(11_500_000, is_max=True)
    m = np.zeros((height, width), dtype="bool")
    m[:, x_11M:x_115M] = True
    masks["East_China"] = m

    # South China Sea: x >= 11.5M
    m = np.zeros((height, width), dtype="bool")
    m[:, x_115M:] = True
    masks["South_China"] = m

    # Bohai focus: x < 10,700,000 AND y > 4,000,000
    x_107M = idx_for_coord(10_700_000, is_max=True)
    y_4M_top = idy_for_coord(4_000_000, is_max=False)
    y_top = 0
    m = np.zeros((height, width), dtype="bool")
    m[y_top:y_4M_top, :x_107M] = True
    masks["Bohai_focus"] = m

    return masks


def compute_pair_metrics(a, b, mask, px_area_km2):
    """IoU/Dice/areas for pair (a, b) within region mask."""
    ma = a[mask].astype("bool")
    mb = b[mask].astype("bool")
    pos_a = ma.sum()
    pos_b = mb.sum()
    inter = (ma & mb).sum()
    union = (ma | mb).sum()
    iou = inter / union if union > 0 else np.nan
    dice = 2 * inter / (pos_a + pos_b) if (pos_a + pos_b) > 0 else np.nan
    return {
        "area_a_km2": round(pos_a * px_area_km2, 2),
        "area_b_km2": round(pos_b * px_area_km2, 2),
        "intersection_km2": round(inter * px_area_km2, 2),
        "union_km2": round(union * px_area_km2, 2),
        "only_a_km2": round((pos_a - inter) * px_area_km2, 2),
        "only_b_km2": round((pos_b - inter) * px_area_km2, 2),
        "disagree_km2": round((pos_a + pos_b - 2 * inter) * px_area_km2, 2),
        "iou": round(iou, 4),
        "dice": round(dice, 4),
        "a_over_b_ratio": round(pos_a / pos_b, 3) if pos_b > 0 else None,
        "region_area_km2": round(mask.sum() * px_area_km2, 1),
        "a_coverage_pct": round(100 * pos_a / mask.sum(), 3) if mask.sum() > 0 else None,
        "b_coverage_pct": round(100 * pos_b / mask.sum(), 3) if mask.sum() > 0 else None,
    }


def main():
    print("=" * 60)
    print("E5 REGIONAL HETEROGENEITY")
    print(f"Resolution: {RES_M}m, CRS: {TARGET_CRS}")
    print("=" * 60)

    data = load_and_rasterize_all()
    arr_cmsa = data["CMSA"]
    arr_cmssm = data["CMSSM"]
    arr_geodata = data["GEODATA"]
    height, width = arr_cmsa.shape

    # Subregions
    subregions = define_subregions_bbox(height, width, data["domain"])
    print(f"\nDefined {len(subregions)} subregions:")
    for name, mask in subregions.items():
        print(f"  {name}: {mask.sum():,} px = {mask.sum() * RES_M**2 / 1e6:.0f} km²")

    px_area_km2 = RES_M ** 2 / 1e6

    pairs = [
        ("CMSA", arr_cmsa, "CMSSM", arr_cmssm),
        ("CMSA", arr_cmsa, "GEODATA", arr_geodata),
        ("CMSSM", arr_cmssm, "GEODATA", arr_geodata),
    ]

    rows = []
    for sr_name, mask in subregions.items():
        print(f"\nSubregion: {sr_name}")
        for name_a, arr_a, name_b, arr_b in pairs:
            # Skip pairs where both have zero coverage in this region
            if arr_a[mask].sum() == 0 and arr_b[mask].sum() == 0:
                print(f"  {name_a} vs {name_b}: SKIP (no positive pixels)")
                continue
            m = compute_pair_metrics(arr_a, arr_b, mask, px_area_km2)
            print(f"  {name_a} vs {name_b}: IoU={m['iou']}, "
                  f"{m['area_a_km2']} vs {m['area_b_km2']} km²")
            rows.append({
                "subregion": sr_name, "pair": f"{name_a}_vs_{name_b}",
                "resolution_m": RES_M, **m,
            })

    # Save CSV
    out_csv = os.path.join(RESULTS, "regional_agreement_2020.csv")
    fieldnames = list(rows[0].keys())
    with open(out_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nSaved: {out_csv}")
    print(f"Total rows: {len(rows)}")

    # Print summary table
    print("\n=== PER-REGION IoU SUMMARY ===")
    for sr_name in subregions:
        sr_rows = [r for r in rows if r["subregion"] == sr_name]
        if not sr_rows:
            continue
        print(f"\n{sr_name}:")
        for r in sr_rows:
            print(f"  {r['pair']:18s} IoU={r['iou']:.4f}  "
                  f"Dice={r['dice']:.4f}  "
                  f"A={r['area_a_km2']:6.1f}  "
                  f"B={r['area_b_km2']:6.1f}  "
                  f"disagree={r['disagree_km2']:6.1f} km²")


if __name__ == "__main__":
    main()
