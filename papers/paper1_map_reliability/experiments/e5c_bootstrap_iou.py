#!/usr/bin/env python3
"""
E5c — Patch-level bootstrap for IoU uncertainty (fast version).

Strategy: Precompute intersection and union counts per 2km block, then
bootstrap from those block-level values. Much faster than recomputing
mask operations each bootstrap iteration.

SUPERSEDED (2026-11-05). The regions in this script are EPSG:3410 meridian
bands, not sea regions, and the labels were inverted. Outputs are archived in
results/superseded_e5_longitude_bands/e5c_iou_bootstrap.csv and are not cited.
The replacement, which computes point estimates and block-bootstrap CIs at the
same 100 m resolution with IHO-derived regions and direct contrast
distributions, is experiments/e5e_bootstrap_100m.py.
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
BLOCK_KM = 2
BLOCK_PX = int(BLOCK_KM * 1000 / RES_M)  # 20 px
N_BOOT = 1000

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
    return arr_cmsa, arr_cmssm, arr_geo, height, width, domain_buf


def block_intersection_union(arr_a, arr_b, height, width):
    """Precompute intersection and union counts per block. Returns 1D arrays."""
    bh, bw = BLOCK_PX, BLOCK_PX
    nbh = height // bh
    nbw = width // bw
    n_blocks = nbh * nbw
    inter_counts = np.zeros(n_blocks, dtype=np.int64)
    union_counts = np.zeros(n_blocks, dtype=np.int64)
    idx = 0
    for hi in range(nbh):
        for wi in range(nbw):
            h0, h1 = hi * bh, (hi + 1) * bh
            w0, w1 = wi * bw, (wi + 1) * bw
            a_block = arr_a[h0:h1, w0:w1]
            b_block = arr_b[h0:h1, w0:w1]
            inter_counts[idx] = (a_block & b_block).sum()
            union_counts[idx] = (a_block | b_block).sum()
            idx += 1
    return inter_counts, union_counts


def bootstrap_iou_fast(inter_counts, union_counts, n_boot=N_BOOT, seed=42):
    """Bootstrap IoU from precomputed block-level intersection/union."""
    rng = np.random.RandomState(seed)
    n = len(inter_counts)
    ious = np.zeros(n_boot)
    for b in range(n_boot):
        idx = rng.randint(0, n, size=n)
        isum = inter_counts[idx].sum()
        usum = union_counts[idx].sum()
        ious[b] = isum / usum if usum > 0 else np.nan
    return ious[~np.isnan(ious)]


def boot_for_subregion(arr_a, arr_b, height, width, w_start, w_end,
                       n_boot=N_BOOT, seed=42):
    """Block-bootstrap IoU for a column-range subregion."""
    sub_w = w_end - w_start
    if sub_w < BLOCK_PX * 2:
        return None
    a_sub = arr_a[:, w_start:w_end]
    b_sub = arr_b[:, w_start:w_end]
    if a_sub.sum() == 0 and b_sub.sum() == 0:
        return None
    ic, uc = block_intersection_union(a_sub, b_sub, height, sub_w)
    ious = bootstrap_iou_fast(ic, uc, n_boot, seed)
    return ious


def main():
    print("=" * 60)
    print(f"E5c — Block Bootstrap IoU ({BLOCK_KM}km blocks, N={N_BOOT})")
    print("=" * 60)
    t0 = time.time()
    np.random.seed(42)
    arr_cmsa, arr_cmssm, arr_geo, height, width, domain_buf = load_all()
    print(f"Loaded in {time.time()-t0:.1f}s, grid {width}x{height}")

    pairs = [
        ("CMSA_vs_CMSSM", arr_cmsa, arr_cmssm),
        ("CMSA_vs_GEODATA", arr_cmsa, arr_geo),
        ("CMSSM_vs_GEODATA", arr_cmssm, arr_geo),
    ]

    rows = []
    for label, a, b in pairs:
        t0 = time.time()
        ic, uc = block_intersection_union(a, b, height, width)
        ious = bootstrap_iou_fast(ic, uc, N_BOOT)
        mean_iou = np.mean(ious)
        std_iou = np.std(ious, ddof=1)
        lo = np.percentile(ious, 2.5)
        hi = np.percentile(ious, 97.5)
        # Exact IoU for reference (full data, no bootstrap)
        exact_iou = ic.sum() / uc.sum()
        print(f"\n{label}:")
        print(f"  Exact IoU (full data): {exact_iou:.4f}")
        print(f"  Bootstrap: mean={mean_iou:.4f}  std={std_iou:.4f}  "
              f"95% CI=[{lo:.4f}, {hi:.4f}]")
        print(f"  Block count: {len(ic)}, zeros: {(uc==0).sum()}")
        print(f"  Time: {time.time()-t0:.1f}s")
        rows.append({
            "pair": label, "scale": "global",
            "exact_iou": round(exact_iou, 4),
            "iou_mean": round(mean_iou, 4), "iou_std": round(std_iou, 4),
            "ci_lo": round(lo, 4), "ci_hi": round(hi, 4),
            "n_bootstrap": len(ious), "block_km": BLOCK_KM,
            "grid_res_m": RES_M, "effective_note": "block bootstrap",
        })

    # Per-region for CMSA_vs_GEODATA
    print("\n=== Per-region bootstrap (CMSA_vs_GEODATA) ===")
    minx = domain_buf[0]
    x_bohai_end = int((11_000_000 - minx) / RES_M)
    x_east_end = int((11_500_000 - minx) / RES_M)
    regions = [
        ("Bohai_Yellow", 0, x_bohai_end),
        ("East_China", x_bohai_end, x_east_end),
        ("South_China", x_east_end, width),
    ]
    for reg_name, ws, we in regions:
        result = boot_for_subregion(arr_cmsa, arr_geo, height, width, ws, we, N_BOOT, 42)
        if result is None or len(result) < 10:
            print(f"  {reg_name}: SKIP (no data or too few blocks)")
            continue
        m, s, lo, hi = np.mean(result), np.std(result, ddof=1), \
                       np.percentile(result, 2.5), np.percentile(result, 97.5)
        # Exact for subregion
        a_sub = arr_cmsa[:, ws:we]
        b_sub = arr_geo[:, ws:we]
        exact = (a_sub & b_sub).sum() / (a_sub | b_sub).sum()
        print(f"  {reg_name}: exact_IoU={exact:.4f}  "
              f"boot mean={m:.4f} ±{s:.4f}  CI=[{lo:.4f}, {hi:.4f}]")
        rows.append({
            "pair": "CMSA_vs_GEODATA", "scale": reg_name,
            "exact_iou": round(exact, 4),
            "iou_mean": round(m, 4), "iou_std": round(s, 4),
            "ci_lo": round(lo, 4), "ci_hi": round(hi, 4),
            "n_bootstrap": len(result), "block_km": BLOCK_KM,
            "grid_res_m": RES_M, "effective_note": "block bootstrap",
        })

    # Save
    out = os.path.join(RESULTS, "e5c_iou_bootstrap.csv")
    with open(out, "w", newline="") as f:
        fieldnames = list(rows[0].keys())
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()
