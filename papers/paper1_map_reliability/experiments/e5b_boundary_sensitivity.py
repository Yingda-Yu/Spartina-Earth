#!/usr/bin/env python3
"""
E5b — Subregion boundary sensitivity test.

Shifts the East/South China boundary (x=11,000,000 m in EPSG:3410) by
±250,000 m and ±500,000 m and re-records per-region IoU.

Purpose: Verify the 3× IoU range finding is robust to boundary placement.
Reuses rasterization logic from e5_regional_heterogeneity.py.
"""
import os, csv, time, numpy as np
os.environ.setdefault("PROJ_LIB",
    "/data/yingda/software/miniconda3/envs/spartina-earth/share/proj")
import geopandas as gpd, rasterio, pyproj
from rasterio import features as rio_features
from rasterio.warp import reproject, Resampling

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
RESULTS = os.path.join(ROOT, "papers", "paper1_map_reliability", "results")
RES_M = 100
TARGET_CRS = "EPSG:3410"
DOMAIN_BUFFER_M = 10_000

DATA_PATHS = {
    "CMSA": os.path.join(ROOT, "work", "intake", "staging",
        "中国大陆2017-2021互花米草CMSA", "CMSA_2020.shp"),
    "CMSSM": os.path.join(ROOT, "work", "external", "cm_ssm_2020_official",
        "extracted", "CM-SSM", "CM-SSM.shp"),
    "GEODATA": os.path.join(ROOT, "work", "intake", "staging",
        "2020年中国滨海30 m分辨率互花米草空间分布动态数据集-数据实体",
        "2020年中国滨海30 m分辨率互花米草空间分布动态数据集-数据实体.tif"),
}


def load_all():
    t0 = time.time()
    cmsa = gpd.read_file(DATA_PATHS["CMSA"])
    cmsa = cmsa[cmsa["gridcode"] == 2].copy().to_crs(TARGET_CRS)
    cmssm = gpd.read_file(DATA_PATHS["CMSSM"]).to_crs(TARGET_CRS)
    domain = cmsa.total_bounds
    domain_buf = np.array([
        domain[0]-DOMAIN_BUFFER_M, domain[1]-DOMAIN_BUFFER_M,
        domain[2]+DOMAIN_BUFFER_M, domain[3]+DOMAIN_BUFFER_M])
    width = int((domain_buf[2]-domain_buf[0])/RES_M)
    height = int((domain_buf[3]-domain_buf[1])/RES_M)
    transform = rasterio.transform.from_bounds(
        domain_buf[0], domain_buf[1], domain_buf[2], domain_buf[3], width, height)

    shapes = [(g, 1) for g in cmsa.geometry if g is not None and not g.is_empty]
    arr_cmsa = rio_features.rasterize(shapes=shapes, out_shape=(height, width),
        transform=transform, fill=0, dtype="uint8", all_touched=False)
    shapes = [(g, 1) for g in cmssm.geometry if g is not None and not g.is_empty]
    arr_cmssm = rio_features.rasterize(shapes=shapes, out_shape=(height, width),
        transform=transform, fill=0, dtype="uint8", all_touched=False)
    dst = np.zeros((height, width), dtype="uint8")
    with rasterio.open(DATA_PATHS["GEODATA"]) as src:
        reproject(source=rasterio.band(src, 1), destination=dst,
            src_crs=src.crs, dst_crs=pyproj.CRS.from_user_input(TARGET_CRS),
            src_transform=src.transform, dst_transform=transform,
            resampling=Resampling.nearest, src_nodata=255, dst_nodata=0)
    arr_geo = (dst == 1).astype("uint8")
    print(f"Loaded in {time.time()-t0:.1f}s, grid {width}x{height}")
    return arr_cmsa, arr_cmssm, arr_geo, domain_buf


def split_by_boundary(arr_cmsa, arr_cmssm, arr_geo, domain_buf, boundary_x):
    """Split domain at boundary_x (metres EPSG:3410), return per-region IoU."""
    minx, miny, maxx, maxy = domain_buf
    res_m = RES_M
    w = arr_cmsa.shape[1]
    h = arr_cmsa.shape[0]
    bx = int((boundary_x - minx) / res_m)  # pixel column of boundary

    pairs = [
        ("CMSA_vs_CMSSM", arr_cmsa, arr_cmssm),
        ("CMSA_vs_GEODATA", arr_cmsa, arr_geo),
        ("CMSSM_vs_GEODATA", arr_cmssm, arr_geo),
    ]

    results = []
    regions = {
        "North_of_boundary": slice(0, bx),
        "South_of_boundary": slice(bx, w),
    }
    for rname, rslice in regions.items():
        for label, a, b in pairs:
            a_reg = a[:, rslice]
            b_reg = b[:, rslice]
            ap = a_reg.sum()
            bp = b_reg.sum()
            inter = (a_reg & b_reg).sum()
            union = (a_reg | b_reg).sum()
            iou = inter / union if union > 0 else np.nan
            dice = 2 * inter / (ap + bp) if (ap + bp) > 0 else np.nan
            results.append({
                "boundary_x_m": boundary_x,
                "shift_m": boundary_x - 11_000_000,
                "region": rname,
                "pair": label,
                "iou": round(iou, 4) if not np.isnan(iou) else None,
                "dice": round(dice, 4) if not np.isnan(dice) else None,
                "area_a_km2": round(float(ap) * res_m**2 / 1e6, 2),
                "area_b_km2": round(float(bp) * res_m**2 / 1e6, 2),
                "intersection_km2": round(float(inter) * res_m**2 / 1e6, 2),
            })
    return results


def main():
    print("=" * 60)
    print("E5b — Subregion Boundary Sensitivity")
    print("=" * 60)
    arr_cmsa, arr_cmssm, arr_geo, domain_buf = load_all()

    all_rows = []
    boundaries = [10_500_000, 10_750_000, 11_000_000, 11_250_000, 11_500_000]

    for bx in boundaries:
        rows = split_by_boundary(arr_cmsa, arr_cmssm, arr_geo, domain_buf, bx)
        all_rows.extend(rows)
        shift = bx - 11_000_000
        print(f"\nBoundary @ x={bx:,}m (shift {shift:+,}m):")
        for r in rows:
            if r["iou"] is not None:
                print(f"  {r['region']:20s} {r['pair']:20s} IoU={r['iou']:.4f} "
                      f"A={r['area_a_km2']:6.1f} B={r['area_b_km2']:6.1f}")

    out = os.path.join(RESULTS, "e5b_boundary_sensitivity.csv")
    with open(out, "w", newline="") as f:
        fieldnames = list(all_rows[0].keys())
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"\nSaved: {out}")

    # Summary: check IoU range stability across boundaries
    print("\n=== IoU RANGE STABILITY CHECK ===")
    for pair in ["CMSA_vs_CMSSM", "CMSA_vs_GEODATA", "CMSSM_vs_GEODATA"]:
        pair_rows = [r for r in all_rows if r["pair"] == pair and r["iou"] is not None]
        # Group by boundary shift, take the NORTH (which was Bohai/Yellow/East China) and SOUTH
        # Original: x<11M = North, x>=11M = South
        # The 3× ratio was between lowest and highest region IoU
        ious_by_boundary = {}
        for r in pair_rows:
            key = r["boundary_x_m"]
            ious_by_boundary.setdefault(key, {}); ious_by_boundary[key][r["region"]] = r["iou"]
        print(f"\n{pair}:")
        for bx, regs in sorted(ious_by_boundary.items()):
            north_iou = regs.get("North_of_boundary", np.nan)
            south_iou = regs.get("South_of_boundary", np.nan)
            if not np.isnan(north_iou) and not np.isnan(south_iou) and north_iou > 0:
                ratio = south_iou / north_iou  # South/North ratio
                print(f"  Boundary {bx/1e6:.2f}M m: N IoU={north_iou:.4f}  S IoU={south_iou:.4f}  "
                      f"Ratio S/N={ratio:.2f}x")


if __name__ == "__main__":
    main()
