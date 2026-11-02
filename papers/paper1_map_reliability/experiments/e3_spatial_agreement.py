#!/usr/bin/env python3
"""
E3 — Spatial Agreement: all 3 pairs @ 30m EPSG:3410 (fast run).
E4 — Resolution sensitivity: also test 50m, 100m.
"""
from __future__ import annotations
import json, time, os
from pathlib import Path

import numpy as np
import geopandas as gpd
import rasterio
from rasterio import features as rio_features, warp as rio_warp
from rasterio.transform import from_bounds

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "work"
OUT = ROOT / "papers/paper1_map_reliability/results"
OUT.mkdir(parents=True, exist_ok=True)

TARGET_CRS = "EPSG:3410"
RESOLUTIONS = [30.0, 50.0, 100.0]  # meters for sensitivity test
DOMAIN_BUFFER = 10000  # 10 km around CMSA bounds

# ====== Load data ======
print("Loading source data ...")
t0 = time.time()

cmsa = gpd.read_file(SRC / "intake/staging/中国大陆2017-2021互花米草CMSA/CMSA_2020.shp")
cmsa_pos = cmsa[cmsa["gridcode"] == 2].to_crs(TARGET_CRS)
print(f"  CMSA 2020: {len(cmsa_pos)} polygons")

cmssm = gpd.read_file(SRC / "external/cm_ssm_2020_official/extracted/CM-SSM/CM-SSM.shp").to_crs(TARGET_CRS)
print(f"  CM-SSM 2020: {len(cmssm)} polygons")

geodata_tif = list((SRC / "intake/staging/2020年中国滨海30 m分辨率互花米草空间分布动态数据集-数据实体").glob("*.tif"))[0]

# Domain = CMSA bounds + buffer (covers all three products well)
b = cmsa_pos.total_bounds
bbox = (b[0]-DOMAIN_BUFFER, b[1]-DOMAIN_BUFFER, b[2]+DOMAIN_BUFFER, b[3]+DOMAIN_BUFFER)
print(f"  Domain bbox @ EPSG:3410: {bbox}")

# ====== Rasterize at multiple resolutions ======
all_results = []

for RES in RESOLUTIONS:
    print(f"\n{'='*60}")
    print(f"Resolution: {RES} m")
    print(f"{'='*60}")
    t_res = time.time()

    w = int((bbox[2]-bbox[0]) / RES)
    h = int((bbox[3]-bbox[1]) / RES)
    aff = from_bounds(*bbox, w, h)
    px_area_km2 = RES**2 / 1e6

    print(f"  Grid: {w}x{h} px = {w*h*px_area_km2:.0f} km² domain")

    # CMSA
    t1 = time.time()
    arr_cmsa = rio_features.rasterize(
        [(g,1) for g in cmsa_pos.geometry if g is not None and not g.is_empty],
        out_shape=(h,w), transform=aff, dtype="uint8", fill=0, all_touched=False)
    print(f"  CMSA rasterize: {time.time()-t1:.1f}s, area={arr_cmsa.sum()*px_area_km2:.2f} km²")

    # CM-SSM
    t1 = time.time()
    arr_cmssm = rio_features.rasterize(
        [(g,1) for g in cmssm.geometry if g is not None and not g.is_empty],
        out_shape=(h,w), transform=aff, dtype="uint8", fill=0, all_touched=False)
    print(f"  CM-SSM rasterize: {time.time()-t1:.1f}s, area={arr_cmssm.sum()*px_area_km2:.2f} km²")

    # GEODATA (warp + threshold to 1)
    t1 = time.time()
    arr_geo = np.zeros((h,w), dtype="uint8")
    with rasterio.open(geodata_tif) as src:
        rio_warp.reproject(
            source=rasterio.band(src, 1), destination=arr_geo,
            src_transform=src.transform, src_crs=src.crs, src_nodata=src.nodata,
            dst_transform=aff, dst_crs=TARGET_CRS, dst_nodata=0,
            resampling=rio_warp.Resampling.nearest)
    arr_geo = (arr_geo == 1).astype("uint8")
    print(f"  GEODATA warp:     {time.time()-t1:.1f}s, area={arr_geo.sum()*px_area_km2:.2f} km²")

    # Pairs
    pairs = {
        "CMSA_vs_CMSSM": (arr_cmsa, arr_cmssm),
        "CMSA_vs_GEODATA": (arr_cmsa, arr_geo),
        "CMSSM_vs_GEODATA": (arr_cmssm, arr_geo),
    }

    print(f"\n  IoU / Dice @ {RES} m:")
    for label, (a, b) in pairs.items():
        a_px, b_px = int(a.sum()), int(b.sum())
        inter, union = int((a & b).sum()), int((a | b).sum())
        iou = inter / union if union > 0 else 0.0
        dice = 2 * inter / (a_px + b_px) if (a_px + b_px) > 0 else 0.0
        only_a = int((a & (1-b)).sum())
        only_b = int((b & (1-a)).sum())

        print(f"    {label:20s} IoU={iou:.4f}  Dice={dice:.4f}  "
              f"A={a_px*px_area_km2:.1f}km² B={b_px*px_area_km2:.1f}km²  "
              f"onlyA={only_a*px_area_km2:.1f}km² onlyB={only_b*px_area_km2:.1f}km²")

        all_results.append({
            "resolution_m": RES, "pair": label,
            "IoU": round(iou, 4), "Dice": round(dice, 4),
            "A_km2": round(a_px * px_area_km2, 2),
            "B_km2": round(b_px * px_area_km2, 2),
            "intersection_km2": round(inter * px_area_km2, 2),
            "union_km2": round(union * px_area_km2, 2),
            "only_A_km2": round(only_a * px_area_km2, 2),
            "only_B_km2": round(only_b * px_area_km2, 2),
            "A_over_B_area_ratio": round(a_px / (b_px + 1e-9), 3),
        })

    print(f"  Resolution done in {time.time()-t_res:.1f}s")

# ====== Save ======
import pandas as pd
df = pd.DataFrame(all_results)
df.to_csv(OUT / "iou_dice_2020_multi_res.csv", index=False)

summary = {
    "experiment": "E3_E4_spatial_agreement_multi_res",
    "target_crs": TARGET_CRS,
    "domain_buffer_m": DOMAIN_BUFFER,
    "pairs": df.to_dict(orient="records"),
}
json.dump(summary, open(OUT / "agreement_summary.json","w"), indent=2)

# Print summary table
print(f"\n{'='*60}")
print("SUMMARY TABLE")
print(f"{'='*60}")
for pair in ["CMSA_vs_CMSSM", "CMSA_vs_GEODATA", "CMSSM_vs_GEODATA"]:
    print(f"\n{pair}:")
    sub = df[df["pair"]==pair]
    for _, r in sub.iterrows():
        print(f"  {r['resolution_m']:>6.0f}m: IoU={r['IoU']:.4f} Dice={r['Dice']:.4f}")
    # Sensitivity: IoU at 100m vs 30m
    iou_30 = sub[sub["resolution_m"]==30]["IoU"].values[0]
    iou_100 = sub[sub["resolution_m"]==100]["IoU"].values[0]
    print(f"  Sensitivity (100m IoU vs 30m): {iou_100:.4f} vs {iou_30:.4f} "
          f"= {(iou_100-iou_30)/iou_30*100:+.1f}%")

print(f"\nAll results saved. Total time: {time.time()-t0:.1f}s")
