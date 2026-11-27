#!/usr/bin/env python3
"""
E4 EXTENDED — robustness experiments.

Tests controlled processing effects that are separable from
differences embedded in the original source products:

1. Grid origin/alignment — shift common grid by +RES_M/2
2. Rasterization rule — all_touched=True vs False
3. Grid resolution — 30m, 50m, 100m (already done in e3, reference here)
4. Coastal mask — CMSA-bounded domain vs full domain

Does NOT alter source product data. Quantifies processing sensitivity.
"""

import os, sys, time, numpy as np, csv
import geopandas as gpd, rasterio
from rasterio import features as rio_features
from rasterio.warp import reproject, Resampling

os.environ.setdefault("PROJ_LIB",
    "/data/yingda/software/miniconda3/envs/spartina-earth/share/proj")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
RESULTS = os.path.join(ROOT, "papers", "paper1_map_reliability", "results")
TARGET_CRS = "EPSG:3410"
DOMAIN_BUFFER = 10_000

DATA_PATHS = {
    "CMSA": os.path.join(ROOT, "work", "intake", "staging",
        "中国大陆2017-2021互花米草CMSA", "CMSA_2020.shp"),
    "CMSSM": os.path.join(ROOT, "work", "external", "cm_ssm_2020_official",
        "extracted", "CM-SSM", "CM-SSM.shp"),
    "GEODATA": os.path.join(ROOT, "work", "intake", "staging",
        "2020年中国滨海30 m分辨率互花米草空间分布动态数据集-数据实体",
        "2020年中国滨海30 m分辨率互花米草空间分布动态数据集-数据实体.tif"),
}


def build_grid(domain_buf, res_m, origin_shift=0.0):
    """Build common grid with optional origin shift (metres)."""
    shifted_origin = domain_buf[0] - origin_shift
    shifted_max = domain_buf[2] - origin_shift
    width = int((shifted_max - shifted_origin) / res_m)
    height = int((domain_buf[3] - domain_buf[1]) / res_m)
    transform = rasterio.transform.from_bounds(
        shifted_origin, domain_buf[1],
        shifted_origin + width * res_m,
        domain_buf[1] + height * res_m,
        width, height)
    return width, height, transform


def rasterize_vector(gdf, width, height, transform, all_touched=False):
    shapes = [(g, 1) for g in gdf.geometry if g is not None and not g.is_empty]
    return rio_features.rasterize(
        shapes=shapes, out_shape=(height, width), transform=transform,
        fill=0, dtype="uint8", all_touched=all_touched)


def warp_geodata(width, height, transform, res_paths):
    import pyproj
    dst = np.zeros((height, width), dtype="uint8")
    with rasterio.open(res_paths["GEODATA"]) as src:
        reproject(source=rasterio.band(src, 1), destination=dst,
            src_crs=src.crs, dst_crs=pyproj.CRS.from_user_input(TARGET_CRS),
            src_transform=src.transform, dst_transform=transform,
            resampling=Resampling.nearest, src_nodata=255, dst_nodata=0)
    return (dst == 1).astype("uint8")


def run_once(res_m, origin_shift=0.0, all_touched=False,
             dom_buffer=DOMAIN_BUFFER, label=""):
    t0 = time.time()
    # Resolve ROOT path correctly
    HERE = os.path.dirname(os.path.abspath(__file__))
    ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
    res_paths = {
        "CMSA": os.path.join(ROOT, "work", "intake", "staging",
            "中国大陆2017-2021互花米草CMSA", "CMSA_2020.shp"),
        "CMSSM": os.path.join(ROOT, "work", "external", "cm_ssm_2020_official",
            "extracted", "CM-SSM", "CM-SSM.shp"),
        "GEODATA": os.path.join(ROOT, "work", "intake", "staging",
            "2020年中国滨海30 m分辨率互花米草空间分布动态数据集-数据实体",
            "2020年中国滨海30 m分辨率互花米草空间分布动态数据集-数据实体.tif"),
    }
    # Load
    cmsa = gpd.read_file(res_paths["CMSA"])
    cmsa = cmsa[cmsa["gridcode"] == 2].copy().to_crs(TARGET_CRS)
    cmssm = gpd.read_file(res_paths["CMSSM"]).to_crs(TARGET_CRS)

    # Domain
    domain = cmsa.total_bounds
    d_buf = np.array([domain[0]-dom_buffer, domain[1]-dom_buffer,
                      domain[2]+dom_buffer, domain[3]+dom_buffer])
    width, height, transform = build_grid(d_buf, res_m, origin_shift)

    # Rasterize
    arr_cmsa = rasterize_vector(cmsa, width, height, transform, all_touched)
    arr_cmssm = rasterize_vector(cmssm, width, height, transform, all_touched)
    arr_geodata = warp_geodata(width, height, transform, res_paths)

    # Pair metrics
    px_km2 = res_m**2 / 1e6
    results = []
    for name_a, arr_a, name_b, arr_b in [
        ("CMSA", arr_cmsa, "CMSSM", arr_cmssm),
        ("CMSA", arr_cmsa, "GEODATA", arr_geodata),
        ("CMSSM", arr_cmssm, "GEODATA", arr_geodata),
    ]:
        inter = int((arr_a & arr_b).sum())
        union = int((arr_a | arr_b).sum())
        iou = inter / union if union > 0 else np.nan
        dice = 2*inter / (arr_a.sum()+arr_b.sum()) if (arr_a.sum()+arr_b.sum()) > 0 else np.nan
        results.append({
            "pair": f"{name_a}_vs_{name_b}",
            "iou": round(iou, 4), "dice": round(dice, 4),
            "area_a_km2": round(arr_a.sum()*px_km2, 2),
            "area_b_km2": round(arr_b.sum()*px_km2, 2),
            "intersection_km2": round(inter*px_km2, 2),
            "union_km2": round(union*px_km2, 2),
            "res_m": res_m, "origin_shift_m": origin_shift,
            "all_touched": str(all_touched), "dom_buffer_m": dom_buffer,
            "label": label,
        })
    elapsed = time.time() - t0
    print(f"  [{label}] {res_m}m shift={origin_shift}m at={all_touched} buf={dom_buffer}m — {elapsed:.0f}s")
    return results


def main():
    print("=" * 60)
    print("E4 EXTENDED — processing robustness experiments")
    print("=" * 60)

    all_rows = []
    RESOLUTION = 100  # Fast: 100m for all robustness tests

    # Baseline
    print("\n=== BASELINE ===")
    all_rows += run_once(RESOLUTION, 0.0, False, DOMAIN_BUFFER, "baseline")

    # 1. Grid origin alignment
    print("\n=== GRID ALIGNMENT ===")
    for shift in [RESOLUTION/2, RESOLUTION, -RESOLUTION]:
        all_rows += run_once(RESOLUTION, shift, False, DOMAIN_BUFFER, f"shift_{shift}m")

    # 2. Rasterization rule
    print("\n=== RASTERIZATION ===")
    all_rows += run_once(RESOLUTION, 0.0, True, DOMAIN_BUFFER, "all_touched_true")

    # 3. Buffer sensitivity
    print("\n=== BUFFER SENSITIVITY ===")
    for buf in [0, 5000, 50000]:
        all_rows += run_once(RESOLUTION, 0.0, False, buf, f"buffer_{buf}m")

    # Save CSV
    out = os.path.join(RESULTS, "robustness_2020.csv")
    with open(out, "w", newline="") as f:
        keys = list(all_rows[0].keys())
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"\nSaved: {out}")

    # Summary table
    print("\n=== ROBUSTNESS SUMMARY ===")
    pairs = ["CMSA_vs_CMSSM", "CMSA_vs_GEODATA", "CMSSM_vs_GEODATA"]
    for pair in pairs:
        pr = [r for r in all_rows if r["pair"] == pair]
        base = [r for r in pr if r["label"] == "baseline"][0]["iou"]
        print(f"\n{pair} (baseline IoU={base:.4f}):")
        for r in pr:
            delta = r["iou"] - base
            print(f"  {r['label']:25s} IoU={r['iou']:.4f}  Δ={delta:+.4f}  "
                  f"({delta/base*100:+.2f}%)")


if __name__ == "__main__":
    main()
