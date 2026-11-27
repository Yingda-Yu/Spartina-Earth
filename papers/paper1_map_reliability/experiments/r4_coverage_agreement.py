#!/usr/bin/env python3
"""
R4-02 — Coverage audit and coverage-normalized agreement.

Question
--------
The pair IoU values treat every non-positive pixel of every product as
"absence".  That is only valid where both products actually provide
comparable observations.  This script verifies, from the delivered source
entities, whether each product's valid-observation domain can be
reconstructed, and quantifies what can be quantified.

Verified entity inventories (computed by this script, cached in meta JSON)
---------------------------------------------------------------
GEODATA 2020 raster (30 m, Krasovsky Albers, single band uint8):
  value 1   : 577,657 px (519.89 km^2) = mapped S. alterniflora presence
  value 255 : 3,057,690,143 px        = uniform fill (everything else)
  -> There is NO explicit absence class: "true absence" and "no-data /
     outside mapped coverage" are indistinguishable in the delivered
     entity.  The valid-observation footprint is therefore NOT
     reconstructable.  (All sibling years 1990/2000/2015/2020 are the same
     presence-only encoding; verified for 2020, the comparison year.)

CMSA 2020 shapefile: 8,914 polygons = 8,864 gridcode-2 (S. alterniflora
  presence) + 50 gridcode-0.  Patch-level presence product; the observation
  domain (where CMSA looked and mapped absence) is not shipped.
  -> Valid-observation footprint NOT reconstructable.

CM-SSM 2020 shapefile: 148,072 province-coded patch polygons.
  -> Valid-observation footprint NOT reconstructable.

Consequence
-----------
A strict coverage-normalized IoU (IoU restricted to the intersection of the
two products' valid observation domains) is NOT COMPUTABLE from the
delivered entities for any pair.  Per the R4 brief this is reported as a
limitation; no mask is invented.  The published IoU values therefore carry
an explicit assumption: "not mapped as presence" == "absence" over the
shared analysis domain for all three products.

Computable proxies (clearly labelled as proxies, not observation domains)
-------------------------------------------------------------------------
P1. Coastal-strip co-mapping (0.5-degree latitude strips): per pair, the
    positive pixels of product A that lie in strips where product B maps
    NOTHING, and vice versa.  Such strips indicate segment-level footprint
    gaps (detection or coverage differences, not attributable without
    reference data).
P2. Nearest-positive distance: for each pair and direction, the distance
    from every A-positive pixel to the nearest B-positive pixel.  Small
    distances = boundary-level disagreement; large distances = isolated /
    segment-level disagreement.

Outputs
  results/r4_coverage_normalized_iou.csv   (pair-level verdict + proxies)
  results/r4_coverage_strips.csv           (per-strip co-mapping detail)
  results/r4_coverage_meta.json            (entity inventories, verified)
  figures/fig_r4_coverage_strips.{pdf,png} (latitude-strip footprint chart)
"""
import os, csv, json, time, subprocess, glob
os.environ.setdefault("PROJ_LIB",
    "/data/yingda/software/miniconda3/envs/spartina-earth/share/proj")
os.environ.setdefault("MPLCONFIGDIR", "/data/yingda/Spartina-Earth/work/tmp_mpl")
import numpy as np
import rasterio
from rasterio import warp as rio_warp
from scipy import ndimage
from scipy.spatial import cKDTree
from pyproj import Transformer

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
PAPER = os.path.join(ROOT, "papers", "paper1_map_reliability")
RESULTS = os.path.join(PAPER, "results")
FIGURES = os.path.join(PAPER, "figures")
CACHE = os.path.join(ROOT, "work", "cache", "paper1_100m")
LOG_PATH = os.path.join(CACHE, "r4_coverage.log")

RES_M = 100
REGIONS = ["Bohai_Yellow", "East_China", "South_China"]
PAIRS = [("CMSA_vs_GEODATA", "CMSA", "GEODATA"),
         ("CMSSM_vs_GEODATA", "CMSSM", "GEODATA"),
         ("CMSA_vs_CMSSM", "CMSA", "CMSSM")]
STRIP_DEG = 0.5
PX_KM2 = RES_M ** 2 / 1e6

_T0 = time.time()

def log(msg):
    line = f"[{time.time()-_T0:7.1f}s] {msg}"
    print(line, flush=True)
    with open(LOG_PATH, "a") as f:
        f.write(line + "\n")

def git_commit():
    try:
        return subprocess.check_output(["git", "-C", ROOT, "rev-parse", "HEAD"],
                                       text=True).strip()
    except Exception:
        return "UNKNOWN"

def verify_geodata_entity():
    """Full-res value inventory of the GEODATA 2020 entity."""
    tif = glob.glob(os.path.join(ROOT, "work", "intake", "staging",
        "2020年中国滨海30 m分辨率互花米草空间分布动态数据集-数据实体",
        "*.tif"))[0]
    src = rasterio.open(tif)
    inv = {"path": tif, "crs": str(src.crs), "shape": list(src.shape),
           "res": list(src.res), "nodata": src.nodata,
           "count": src.count, "dtype": src.dtypes[0],
           "value_counts": {}, "verified_full_resolution": True}
    counts = {}
    t = time.time()
    for _, window in src.block_windows(1):
        a = src.read(1, window=window)
        v, c = np.unique(a, return_counts=True)
        for vv, cc in zip(v.tolist(), c.tolist()):
            counts[vv] = counts.get(vv, 0) + int(cc)
    src.close()
    inv["value_counts"] = {str(k): v for k, v in sorted(counts.items())}
    inv["value_counts_check_total"] = int(np.prod(inv["shape"]))
    log(f"GEODATA entity inventory (full-res, {time.time()-t:.1f}s): "
        + ", ".join(f"{k}={v:,}" for k, v in inv["value_counts"].items()))
    return inv

def verify_vector_entities():
    import geopandas as gpd
    out = {}
    c = gpd.read_file(os.path.join(ROOT, "work", "intake", "staging",
        "中国大陆2017-2021互花米草CMSA", "CMSA_2020.shp"))
    out["CMSA"] = {"path": "work/intake/staging/中国大陆2017-2021互花米草CMSA/CMSA_2020.shp",
                   "n_polygons": int(len(c)),
                   "gridcode_counts": {str(k): int(v)
                                       for k, v in c["gridcode"].value_counts().items()}}
    s = gpd.read_file(os.path.join(ROOT, "work", "external",
        "cm_ssm_2020_official", "extracted", "CM-SSM", "CM-SSM.shp"))
    prov = {str(k): int(v) for k, v in s["name"].value_counts().items()}
    out["CMSSM"] = {"path": "work/external/cm_ssm_2020_official/extracted/CM-SSM/CM-SSM.shp",
                    "n_patches": int(len(s)),
                    "province_code_counts": dict(sorted(prov.items()))}
    for k in out:
        log(f"{k} entity: {json.dumps(out[k], ensure_ascii=False)[:180]}")
    return out

def policy_b_masks(direct, union_pos, H, W):
    out = {g: direct[g].copy() for g in REGIONS}
    resid = union_pos & ~np.logical_or.reduce(list(direct.values()))
    n = int(resid.sum())
    if n == 0:
        return out
    ys, xs = np.nonzero(resid)
    query = np.column_stack([ys, xs]).astype(np.float32)
    best_d = np.full(n, np.inf, dtype=np.float32)
    best_k = np.full(n, -1, dtype=np.int8)
    for k, g in enumerate(REGIONS):
        edge = direct[g] & ~ndimage.binary_erosion(
            direct[g], structure=np.ones((3, 3), bool), border_value=0)
        ey, ex = np.nonzero(edge)
        tree = cKDTree(np.column_stack([ey, ex]).astype(np.float32))
        dd, _ = tree.query(query, k=1, workers=-1)
        upd = dd < best_d
        best_d[upd] = dd[upd]
        best_k[upd] = k
    for k, g in enumerate(REGIONS):
        sel = best_k == k
        if sel.any():
            out[g][ys[sel], xs[sel]] = True
    return out

def main():
    open(LOG_PATH, "w").close()
    log("=" * 72)
    log("R4-02 — coverage audit and coverage-normalized agreement")
    log(f"git_commit={git_commit()}")

    # ---------------- entity inventories ----------------
    geo_inv = verify_geodata_entity()
    vec_inv = verify_vector_entities()
    # sanity: 30 m presence px must reproduce the 519.89 km^2 area
    n_pos = geo_inv["value_counts"].get("1", 0)
    geo_inv["presence_area_km2_from_entity"] = round(n_pos * 900 / 1e6, 2)

    # ---------------- analysis grid ----------------
    d = np.load(os.path.join(CACHE, "products_100m_epsg3410.npz"))
    arr = {"CMSA": d["cmsa"].astype(bool), "CMSSM": d["cmssm"].astype(bool),
           "GEODATA": d["geo"].astype(bool)}
    H, W = int(d["H"]), int(d["W"])
    db = [float(v) for v in d["db"]]
    tr = rasterio.Affine(*d["transform"].tolist())
    m = np.load(os.path.join(CACHE, "marine_masks_100m.npz"))
    direct = {g: m[f"{g}__mask"].astype(bool) for g in REGIONS}
    log(f"loaded products {W}x{H}")
    union_pos = arr["CMSA"] | arr["CMSSM"] | arr["GEODATA"]

    # ---------------- latitudes of positive pixels ----------------
    tf = Transformer.from_crs("EPSG:3410", "EPSG:4326", always_xy=True)
    pos = {}
    for p, a in arr.items():
        ys, xs = np.nonzero(a)
        lon, lat = tf.transform(db[0] + (xs + .5) * RES_M,
                                db[3] - (ys + .5) * RES_M)
        pos[p] = {"y": ys, "x": xs, "lat": lat}
        log(f"  {p}: {len(ys):,} positive px, lat "
            f"[{np.min(lat):.2f}, {np.max(lat):.2f}]")

    # ---------------- P1: coastal-strip co-mapping ----------------
    strip_rows = []
    strip_summary = {}
    all_lat = np.concatenate([pos[p]["lat"] for p in arr])
    edges = np.arange(np.floor(np.min(all_lat) / STRIP_DEG) * STRIP_DEG,
                      np.ceil(np.max(all_lat) / STRIP_DEG) * STRIP_DEG + STRIP_DEG,
                      STRIP_DEG)
    strip_idx = {}
    for p in arr:
        strip_idx[p] = np.digitize(pos[p]["lat"], edges) - 1
    n_strips = len(edges) - 1
    strip_counts = {}
    for p in arr:
        cnt = np.bincount(strip_idx[p], minlength=n_strips)
        strip_counts[p] = cnt
    for i in range(n_strips):
        strip_rows.append({
            "lat_lo": round(float(edges[i]), 2),
            "lat_hi": round(float(edges[i + 1]), 2),
            "CMSA_px": int(strip_counts["CMSA"][i]),
            "CMSSM_px": int(strip_counts["CMSSM"][i]),
            "GEODATA_px": int(strip_counts["GEODATA"][i]),
        })
    with open(os.path.join(RESULTS, "r4_coverage_strips.csv"), "w",
              newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(strip_rows[0].keys()))
        w.writeheader()
        w.writerows(strip_rows)
    log(f"coastal strips: {n_strips} x {STRIP_DEG} deg bands written")

    # ---------------- P2: nearest-positive distances ----------------
    dist_stats = {}
    for pair_label, pa, pb in PAIRS:
        for src_name, other_name in [(pa, pb), (pb, pa)]:
            sy, sx = pos[src_name]["y"], pos[src_name]["x"]
            oy, ox = pos[other_name]["y"], pos[other_name]["x"]
            tree = cKDTree(np.column_stack([oy, ox]).astype(np.float32))
            dd, _ = tree.query(np.column_stack([sy, sx]).astype(np.float32),
                               k=1, workers=-1)
            dd_km = dd * RES_M / 1000.0
            key = (pair_label, src_name, other_name)
            dist_stats[str(key)] = {
                "n_src_positive_px": int(len(sy)),
                "median_km": round(float(np.median(dd_km)), 4),
                "p90_km": round(float(np.percentile(dd_km, 90)), 4),
                "share_within_0p1km_pct": round(float((dd_km <= 0.1).mean() * 100), 2),
                "share_within_0p5km_pct": round(float((dd_km <= 0.5).mean() * 100), 2),
                "share_within_1km_pct": round(float((dd_km <= 1.0).mean() * 100), 2),
                "share_beyond_5km_pct": round(float((dd_km > 5.0).mean() * 100), 2),
                "share_beyond_10km_pct": round(float((dd_km > 10.0).mean() * 100), 2),
            }
            log(f"  {pair_label} {src_name}->{other_name}: median "
                f"{dist_stats[str(key)]['median_km']} km, <=1km "
                f"{dist_stats[str(key)]['share_within_1km_pct']}%")

    # ---------------- pair-level verdict rows ----------------
    iou_rows = []
    for pair_label, pa, pb in PAIRS:
        a, b = arr[pa], arr[pb]
        inter = int((a & b).sum())
        union_r = int((a | b).sum())
        iou_orig = inter / union_r
        # strip-gap proxies
        gap_a = 0
        gap_b = 0
        cnt_a, cnt_b = strip_counts[pa], strip_counts[pb]
        for i in range(n_strips):
            if cnt_b[i] == 0:
                gap_a += int(cnt_a[i])
            if cnt_a[i] == 0:
                gap_b += int(cnt_b[i])
        ds_ab = dist_stats[str((pair_label, pa, pb))]
        ds_ba = dist_stats[str((pair_label, pb, pa))]
        iou_rows.append({
            "pair": pair_label,
            "valid_masks_recoverable": "NO",
            "iou_original_full_domain": round(iou_orig, 4),
            "iou_coverage_normalized": "NOT_COMPUTABLE",
            "reason": "Neither product ships a valid-observation domain; "
                      "GEODATA entity is presence-only (1) with uniform 255 "
                      "fill; CMSA/CM-SSM are patch-vector products. "
                      "Restricting IoU to the products' own footprints would "
                      "degenerate to their presence masks.",
            "assumption_behind_original_iou": "not mapped as presence == "
                      "absence over the shared 100 m analysis domain",
            "a_pos_px_in_strips_where_b_maps_nothing": gap_a,
            "b_pos_px_in_strips_where_a_maps_nothing": gap_b,
            "a_pos_km2_in_b_empty_strips": round(gap_a * PX_KM2, 2),
            "b_pos_km2_in_a_empty_strips": round(gap_b * PX_KM2, 2),
            "a_pos_share_in_b_empty_strips_pct": round(gap_a / float(a.sum()) * 100, 2),
            "b_pos_share_in_a_empty_strips_pct": round(gap_b / float(b.sum()) * 100, 2),
            "a_to_b_median_dist_km": ds_ab["median_km"],
            "a_to_b_within_1km_pct": ds_ab["share_within_1km_pct"],
            "a_to_b_beyond_5km_pct": ds_ab["share_beyond_5km_pct"],
            "b_to_a_median_dist_km": ds_ba["median_km"],
            "b_to_a_within_1km_pct": ds_ba["share_within_1km_pct"],
            "b_to_a_beyond_5km_pct": ds_ba["share_beyond_5km_pct"],
        })
        log(f"  {pair_label}: IoU {iou_orig:.4f} (coverage-normalized NOT "
            f"COMPUTABLE); strip-gap A {gap_a:,} px / B {gap_b:,} px")

    with open(os.path.join(RESULTS, "r4_coverage_normalized_iou.csv"), "w",
              newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(iou_rows[0].keys()))
        w.writeheader()
        w.writerows(iou_rows)

    # ---------------- regional strip-gap detail (feeds R4-03) ----------
    regions_b = policy_b_masks(direct, union_pos, H, W)
    reg_rows = []
    for g in REGIONS:
        msk = regions_b[g]
        row = {"region": g}
        for p in arr:
            row[f"{p}_positive_px"] = int((arr[p] & msk).sum())
        for pair_label, pa, pb in PAIRS:
            a_r, b_r = arr[pa] & msk, arr[pb] & msk
            inter = int((a_r & b_r).sum())
            union_r = int((a_r | b_r).sum())
            row[f"{pair_label}_iou"] = round(inter / union_r, 4) if union_r else ""
            row[f"{pair_label}_only_{pa}_km2"] = round((int(a_r.sum()) - inter) * PX_KM2, 2)
            row[f"{pair_label}_only_{pb}_km2"] = round((int(b_r.sum()) - inter) * PX_KM2, 2)
        reg_rows.append(row)
    with open(os.path.join(RESULTS, "r4_coverage_by_region.csv"), "w",
              newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(reg_rows[0].keys()))
        w.writeheader()
        w.writerows(reg_rows)

    # ---------------- figure: latitude-strip footprint chart ----------
    fig, ax = plt.subplots(figsize=(10, 7))
    centers = (edges[:-1] + edges[1:]) / 2
    colors = {"CMSA": "#1b9e77", "CMSSM": "#d95f02", "GEODATA": "#7570b3"}
    disp_names = {"CMSA": "CMSA", "CMSSM": "CM-SSM", "GEODATA": "GEODATA"}
    y = centers
    for off, p in zip([-0.14, 0, 0.14], ["CMSA", "CMSSM", "GEODATA"]):
        km2 = strip_counts[p] * PX_KM2
        ax.barh(y + off, km2, height=0.13, color=colors[p],
                label=disp_names[p])
    ax.set_xlabel("mapped S. alterniflora area per 0.5-deg latitude strip (km²)")
    ax.set_ylabel("latitude band centre (°N)")
    ax.set_yscale("linear")
    ax.legend()
    ax.set_title("R4-02 — product footprints by coastal latitude strip\n"
                 "(empty strips for one product = segment-level footprint gaps; "
                 "proxy, not a valid-observation domain)", fontsize=10)
    fig.tight_layout()
    for ext in ["pdf", "png"]:
        fig.savefig(os.path.join(FIGURES, f"fig_r4_coverage_strips.{ext}"),
                    dpi=300 if ext == "png" else None)
    plt.close(fig)
    log("saved figures/fig_r4_coverage_strips.pdf/.png")

    meta = {
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "git_commit": git_commit(),
        "geodata_entity": geo_inv,
        "vector_entities": vec_inv,
        "verdict": {
            "coverage_normalized_iou_computable": False,
            "reason": "GEODATA entity is presence-only (1) with uniform 255 "
                      "fill, so absence and no-data are indistinguishable; "
                      "CMSA and CM-SSM are patch-vector products without "
                      "observation-domain rasters. No masks were invented.",
        },
        "distance_statistics": dist_stats,
        "outputs": ["results/r4_coverage_normalized_iou.csv",
                    "results/r4_coverage_strips.csv",
                    "results/r4_coverage_by_region.csv",
                    "figures/fig_r4_coverage_strips.pdf"],
        "runtime_s": round(time.time() - _T0, 1),
    }
    with open(os.path.join(RESULTS, "r4_coverage_meta.json"), "w") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    log(f"done in {time.time()-_T0:.1f}s")

if __name__ == "__main__":
    main()
