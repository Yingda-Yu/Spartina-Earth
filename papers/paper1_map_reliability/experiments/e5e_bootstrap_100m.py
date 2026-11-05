#!/usr/bin/env python3
"""
E5e — Spatial block bootstrap at a single estimand resolution (100 m).

Why this script exists
----------------------
The R2 experiment `e5c_bootstrap_iou.py` produced a point estimate of IoU at
the 30 m harmonized raster but bootstrap CIs from a 100 m block resampling of
the 100 m raster, and it stratified by EPSG:3410 longitude bands that were
labelled as sea regions although they are pure meridian slices.  Both the
resolution pairing and the regionalization are invalid.  This script replaces
it.

Design decisions (documented per R3.1 Task 4)
--------------------------------------------
1. PRIMARY RESOLUTION = 100 m.  Reason: E4 shows global IoU changes by <=0.4 %
   between 30 m and 100 m, so 100 m is a faithful estimand while making the
   regional masks (Natural Earth province polygons) defensible; more
   importantly, the point estimate and the bootstrap CI are computed on the
   *same* 100 m grid, so they refer to the same estimand.
2. RESAMPLING UNIT = square spatial block (1, 2, 5, 10 km).  This is the
   cluster-level bootstrap appropriate for spatially autocorrelated map
   disagreement; per-pixel resampling would destroy the dependence structure
   and produce absurdly narrow CIs.
3. ESTIMAND = IoU of the totals over the region (ratio of sums), not the mean
   of block IoUs.  Resampling blocks and re-summing intersection and union is
   therefore consistent with the estimand.
4. EMPTY BLOCKS (union == 0) are excluded from resampling but reported
   (N_total, N_empty, N_informative).  Including them would add units that
   contribute identically zero and would narrow the CI artificially.
5. REGIONAL CONTRASTS (difference and ratio) are bootstrapped *directly* from
   independent block resampling inside each disjoint region.  Significance is
   read from the contrast distribution, never from overlapping/ non-
   overlapping individual CIs.
6. SPATIAL DEPENDENCE is quantified with Moran's I on block-level IoU using a
   k-nearest-neighbour (k=8) row-standardised weight matrix and a 999-permutation
   null.
7. MONTE CARLO UNCERTAINTY of the CI endpoints is estimated by repeating the
   whole bootstrap under 5 independent seeds; the spread between seed-specific
   CI bounds is reported.

Inputs (cached by e5d_geographic_regions.py)
  work/cache/paper1_100m/products_100m_epsg3410.npz
  work/cache/paper1_100m/region_masks_100m.npz

Outputs
  results/e5e_bootstrap_100m.csv
  results/e5e_region_contrasts_100m.csv
  results/e5e_moran_100m.csv
  results/e5e_bootstrap_meta.json
"""
import os, csv, json, time, resource
os.environ.setdefault("PROJ_LIB",
    "/data/yingda/software/miniconda3/envs/spartina-earth/share/proj")
import numpy as np
from scipy.spatial import cKDTree
from scipy import sparse
import rasterio
from rasterio import features as rio_features

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
PAPER = os.path.join(ROOT, "papers", "paper1_map_reliability")
RESULTS = os.path.join(PAPER, "results")
CACHE = os.path.join(ROOT, "work", "cache", "paper1_100m")
LOG_PATH = os.path.join(CACHE, "e5e_bootstrap.log")

RES_M = 100            # primary estimand resolution (DE)
BLOCK_SIZES_KM = [1, 2, 5, 10]
N_BOOT = 1000
SEEDS = [202601, 202602, 202603, 202604, 202605]
MORAN_K = 8
MORAN_PERM = 999

REGION_ORDER = ["Bohai_Yellow", "East_China", "South_China"]
PAIRS = ["CMSA_vs_CMSSM", "CMSA_vs_GEODATA", "CMSSM_vs_GEODATA"]

CONTRACTS_NPZ = os.path.join(CACHE, "products_100m_epsg3410.npz")
MASKS_NPZ = os.path.join(CACHE, "marine_masks_100m.npz")

_T0 = time.time()


def log(msg):
    line = f"[{time.time()-_T0:8.1f}s {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1e6:6.2f}GB] {msg}"
    print(line, flush=True)
    with open(LOG_PATH, "a") as f:
        f.write(line + "\n")


def load_inputs():
    d = np.load(CONTRACTS_NPZ)
    arr = {"CMSA": d["cmsa"], "CMSSM": d["cmssm"], "GEODATA": d["geo"]}
    H, W = int(d["H"]), int(d["W"])
    db = d["db"]
    tr = rasterio.Affine(*d["transform"].tolist())
    m = np.load(MASKS_NPZ)
    masks = {k[:-6]: m[k].astype(bool) for k in m.files
             if k.endswith("__mask") and not k.startswith("poly_")}
    province_rows = json.loads(str(m["per_poly"])) if "per_poly" in m.files else []
    return arr, masks, province_rows, H, W, db, tr


def region_masks_with_offshore(masks, arr, H, W):
    """Re-create the offshore nearest-region assignment used by E5d."""
    union_pos = np.zeros((H, W), dtype=bool)
    for a in arr.values():
        union_pos |= a.astype(bool)
    residual = union_pos & ~np.logical_or.reduce(list(masks.values()))
    n_resid = int(residual.sum())
    if n_resid == 0:
        return masks, {}, 0
    from scipy import ndimage
    ys, xs = np.nonzero(residual)
    query = np.column_stack([ys, xs]).astype(np.float32)
    names = [g for g, mm in masks.items() if int(mm.sum()) > 0]
    trees = {}
    for gname in names:
        edge = masks[gname] & ~ndimage.binary_erosion(
            masks[gname], structure=np.ones((3, 3), bool), border_value=0)
        ey, ex = np.nonzero(edge)
        trees[gname] = cKDTree(np.column_stack([ey, ex]).astype(np.float32))
    best_d = np.full(n_resid, np.inf, dtype=np.float32)
    best_k = np.full(n_resid, -1, dtype=np.int8)
    for k, gname in enumerate(names):
        dd, _ = trees[gname].query(query, k=1, workers=-1)
        upd = dd < best_d
        best_d[upd] = dd[upd]
        best_k[upd] = k
    assigned = {g: 0 for g in names}
    flat_idx = ys.astype(np.int64) * W + xs.astype(np.int64)
    buf = np.zeros(H * W, dtype=bool)
    for k, gname in enumerate(names):
        sel = (best_k == k)
        assigned[gname] = int(sel.sum())
        if assigned[gname]:
            buf[:] = False
            buf[flat_idx[sel]] = True
            masks[gname] = masks[gname] | buf.reshape(H, W)
    return masks, assigned, n_resid


def pair_pixels(arr_a, arr_b):
    """Return (y, x) coordinate arrays of positive pixels for each product."""
    ya, xa = np.nonzero(arr_a)
    yb, xb = np.nonzero(arr_b)
    return ya, xa, yb, xb


def block_counts(ya, xa, yb, xb, region_mask, H, W, block_px):
    """Per-block intersection / union / area counts restricted to a region.

    Works on the sparse set of positive pixels (only ~5e4 pixels nationally),
    so cost is O(n log n) in positive pixels, not O(H*W).
    """
    nbw = int(np.ceil(W / block_px))
    nbh = int(np.ceil(H / block_px))
    n_total = nbh * nbw

    keep_a = region_mask[ya, xa]
    keep_b = region_mask[yb, xb]
    ay, ax = ya[keep_a], xa[keep_a]
    by_, bx_ = yb[keep_b], xb[keep_b]

    flat_a = ay.astype(np.int64) * W + ax
    flat_b = by_.astype(np.int64) * W + bx_
    flat_i = np.intersect1d(flat_a, flat_b, assume_unique=True)
    flat_u = np.union1d(flat_a, flat_b)

    def blocks(y, x):
        return (y // block_px).astype(np.int64) * nbw + (x // block_px)

    ca = np.bincount(blocks(ay, ax), minlength=n_total)
    cb = np.bincount(blocks(by_, bx_), minlength=n_total)
    iy, ix = np.divmod(flat_i, W)
    uy, ux = np.divmod(flat_u, W)
    ci = np.bincount(blocks(iy, ix), minlength=n_total)
    cu = np.bincount(blocks(uy, ux), minlength=n_total)

    # block centres for Moran's I
    cy = (np.arange(nbh) * block_px + block_px / 2)
    cx = (np.arange(nbw) * block_px + block_px / 2)
    return ca, cb, ci, cu, nbh, nbw, cy, cx


def boot_iou(inter, union, n_boot, rng):
    n = len(inter)
    out = np.empty(n_boot, dtype=np.float64)
    for b in range(n_boot):
        k = rng.integers(0, n, n)
        isum = inter[k].sum()
        usum = union[k].sum()
        out[b] = isum / usum if usum > 0 else np.nan
    return out


def summarise(samples):
    s = samples[~np.isnan(samples)]
    return {
        "boot_mean": float(np.mean(s)),
        "boot_sd": float(np.std(s, ddof=1)),
        "ci_lo": float(np.percentile(s, 2.5)),
        "ci_hi": float(np.percentile(s, 97.5)),
        "n_eff": int(len(s)),
    }


def morans_i(coords, values, k=MORAN_K, n_perm=MORAN_PERM, seed=7):
    n = len(values)
    if n <= k + 2:
        return {"I": None, "p_perm": None, "n": n}
    tree = cKDTree(coords)
    _, nb = tree.query(coords, k=k + 1)
    rows = np.repeat(np.arange(n), k)
    cols = nb[:, 1:].ravel()
    Wsp = sparse.csr_matrix((np.full(n * k, 1.0 / k), (rows, cols)), shape=(n, n))

    def compute(v):
        z = v - v.mean()
        denom = float(z @ z)
        if denom == 0:
            return np.nan
        return float(z @ (Wsp @ z)) / denom

    obs = compute(values)
    rng = np.random.default_rng(seed)
    perm = np.empty(n_perm)
    for i in range(n_perm):
        perm[i] = compute(rng.permutation(values))
    p = (1 + np.sum(np.abs(perm) >= abs(obs))) / (n_perm + 1)
    return {"I": obs, "p_perm": float(p), "n": n,
            "perm_mean": float(np.mean(perm)), "perm_sd": float(np.std(perm))}


def main():
    open(LOG_PATH, "w").close()
    log("= " * 28)
    log("E5e — same-resolution (100 m) spatial block bootstrap")
    log("= " * 28)

    arr, masks, province_rows, H, W, db, tr = load_inputs()
    log(f"loaded products: grid {W}x{H} = {W*H:,} px")
    masks, assigned, n_resid = region_masks_with_offshore(masks, arr, H, W)
    log(f"offshore residual px: {n_resid:,}; assigned: {assigned}")

    pairs = {"CMSA_vs_CMSSM": (arr["CMSA"], arr["CMSSM"]),
             "CMSA_vs_GEODATA": (arr["CMSA"], arr["GEODATA"]),
             "CMSSM_vs_GEODATA": (arr["CMSSM"], arr["GEODATA"])}

    rows, contrast_rows, moran_rows = [], [], []
    detail = {}

    for pair_label in PAIRS:
        a, b = pairs[pair_label]
        ya, xa, yb, xb = pair_pixels(a, b)

        # ---------------- national (whole domain) ----------------
        whole = np.ones((H, W), dtype=bool)
        for bs_km in BLOCK_SIZES_KM:
            bp = int(bs_km * 1000 / RES_M)
            t = time.time()
            ca, cb, ci, cu, nbh, nbw, cy, cx = block_counts(
                ya, xa, yb, xb, whole, H, W, bp)
            n_total = nbh * nbw
            informative = cu > 0
            n_inf = int(informative.sum())
            n_empty = n_total - n_inf
            n_pos = int(((ca > 0) & (cb > 0) & informative).sum())
            exact = float(ci.sum() / cu.sum())
            i_arr, u_arr = ci[informative], cu[informative]

            seed_summaries = []
            for sd in SEEDS:
                samples = boot_iou(i_arr, u_arr, N_BOOT,
                                   np.random.default_rng(sd))
                seed_summaries.append(summarise(samples))
            prim = seed_summaries[0]
            ci_lo_spread = float(np.std([s["ci_lo"] for s in seed_summaries], ddof=1))
            ci_hi_spread = float(np.std([s["ci_hi"] for s in seed_summaries], ddof=1))
            mean_spread = float(np.std([s["boot_mean"] for s in seed_summaries], ddof=1))

            # --- Moran's I on informative block IoU (block size >= 2 km) ---
            if bs_km >= 2 and n_inf > 50:
                yy, xx = np.divmod(np.nonzero(informative)[0], nbw)
                coords = np.column_stack([yy * bp, xx * bp]).astype(np.float64)
                vals = ci[informative] / cu[informative]
                mi = morans_i(coords, vals)
                moran_rows.append({
                    "pair": pair_label, "scale": "National", "block_km": bs_km,
                    "n_blocks": n_inf, "morans_I": round(mi["I"], 4) if mi["I"] is not None else None,
                    "perm_p": round(mi["p_perm"], 4) if mi["p_perm"] is not None else None,
                })
                log(f"  Moran I {pair_label} {bs_km}km: I={mi['I']:.3f} p={mi['p_perm']:.3f} (n={n_inf})")

            rows.append({
                "pair": pair_label, "scale": "National", "block_km": bs_km,
                "resolution_m": RES_M, "exact_iou": round(exact, 4),
                "boot_mean": round(prim["boot_mean"], 4),
                "boot_sd": round(prim["boot_sd"], 4),
                "ci_lo": round(prim["ci_lo"], 4), "ci_hi": round(prim["ci_hi"], 4),
                "n_blocks_total": n_total, "n_blocks_empty": n_empty,
                "n_blocks_informative": n_inf, "n_blocks_both_positive": n_pos,
                "n_boot": N_BOOT, "seed": SEEDS[0],
                "mc_seed_ci_lo_std": round(ci_lo_spread, 6),
                "mc_seed_ci_hi_std": round(ci_hi_spread, 6),
                "mc_seed_mean_std": round(mean_spread, 6),
            })
            log(f"  National {pair_label} {bs_km}km: IoU={exact:.4f} "
                f"CI=[{prim['ci_lo']:.4f},{prim['ci_hi']:.4f}] "
                f"N_inf={n_inf:,}/{n_total:,} ({time.time()-t:.1f}s)")

        # ---------------- per region ----------------
        for gname in REGION_ORDER:
            mask = masks[gname]
            if int(mask.sum()) == 0:
                log(f"  region {gname}: empty mask, skipped")
                continue
            for bs_km in BLOCK_SIZES_KM:
                bp = int(bs_km * 1000 / RES_M)
                t = time.time()
                ca, cb, ci, cu, nbh, nbw, cy, cx = block_counts(
                    ya, xa, yb, xb, mask, H, W, bp)
                n_total = nbh * nbw
                informative = cu > 0
                n_inf = int(informative.sum())
                if n_inf < 10:
                    log(f"  region {gname} {pair_label} {bs_km}km: only "
                        f"{n_inf} informative blocks, skipped")
                    continue
                n_empty = n_total - n_inf
                n_pos = int(((ca > 0) & (cb > 0) & informative).sum())
                exact = float(ci.sum() / cu.sum())
                i_arr, u_arr = ci[informative], cu[informative]

                seed_summaries = []
                for sd in SEEDS:
                    samples = boot_iou(i_arr, u_arr, N_BOOT,
                                       np.random.default_rng(sd))
                    seed_summaries.append(summarise(samples))
                prim = seed_summaries[0]
                ci_lo_spread = float(np.std([s["ci_lo"] for s in seed_summaries], ddof=1))
                ci_hi_spread = float(np.std([s["ci_hi"] for s in seed_summaries], ddof=1))
                mean_spread = float(np.std([s["boot_mean"] for s in seed_summaries], ddof=1))

                if bs_km >= 2 and n_inf > 50:
                    yy, xx = np.divmod(np.nonzero(informative)[0], nbw)
                    coords = np.column_stack([yy * bp, xx * bp]).astype(np.float64)
                    vals = ci[informative] / cu[informative]
                    mi = morans_i(coords, vals)
                    moran_rows.append({
                        "pair": pair_label, "scale": gname, "block_km": bs_km,
                        "n_blocks": n_inf,
                        "morans_I": round(mi["I"], 4) if mi["I"] is not None else None,
                        "perm_p": round(mi["p_perm"], 4) if mi["p_perm"] is not None else None,
                    })

                rows.append({
                    "pair": pair_label, "scale": gname, "block_km": bs_km,
                    "resolution_m": RES_M, "exact_iou": round(exact, 4),
                    "boot_mean": round(prim["boot_mean"], 4),
                    "boot_sd": round(prim["boot_sd"], 4),
                    "ci_lo": round(prim["ci_lo"], 4), "ci_hi": round(prim["ci_hi"], 4),
                    "n_blocks_total": n_total, "n_blocks_empty": n_empty,
                    "n_blocks_informative": n_inf, "n_blocks_both_positive": n_pos,
                    "n_boot": N_BOOT, "seed": SEEDS[0],
                    "mc_seed_ci_lo_std": round(ci_lo_spread, 6),
                    "mc_seed_ci_hi_std": round(ci_hi_spread, 6),
                    "mc_seed_mean_std": round(mean_spread, 6),
                })
                detail.setdefault(pair_label, {}).setdefault(gname, {})[bs_km] = {
                    "inter": i_arr, "union": u_arr, "exact": exact}
                log(f"  {gname:14s} {pair_label:17s} {bs_km:2d}km: "
                    f"IoU={exact:.4f} CI=[{prim['ci_lo']:.4f},{prim['ci_hi']:.4f}] "
                    f"N_inf={n_inf:,}/{n_total:,} ({time.time()-t:.1f}s)")

    # ---------------- direct regional contrasts ----------------
    # Two regions at a time, independent block resampling inside each region.
    CONTRAST_BS_KM = 2   # primary resampling scale for contrasts
    for pair_label in PAIRS:
        dd = detail.get(pair_label, {})
        regs = [g for g in REGION_ORDER
                if g in dd and CONTRAST_BS_KM in dd[g]
                and len(dd[g][CONTRAST_BS_KM]["inter"]) >= 10]
        if len(regs) < 2:
            continue
        for i in range(len(regs)):
            for j in range(i + 1, len(regs)):
                gi, gj = regs[i], regs[j]
                di = dd[gi][CONTRAST_BS_KM]
                dj = dd[gj][CONTRAST_BS_KM]
                for sd in SEEDS:
                    rng = np.random.default_rng(sd)
                    si = boot_iou(di["inter"], di["union"], N_BOOT, rng)
                    sj = boot_iou(dj["inter"], dj["union"], N_BOOT, rng)
                    diff = si - sj
                    with np.errstate(divide="ignore", invalid="ignore"):
                        ratio = np.where(sj != 0, si / sj, np.nan)
                    if sd == SEEDS[0]:
                        p_two = 2.0 * min(float(np.mean(diff <= 0)),
                                          float(np.mean(diff >= 0)))
                        p_two = min(p_two, 1.0)
                        contrast_rows.append({
                            "pair": pair_label, "region_high": gi, "region_low": gj,
                            "block_km": CONTRAST_BS_KM,
                            "iou_high": round(di["exact"], 4),
                            "iou_low": round(dj["exact"], 4),
                            "diff": round(float(di["exact"] - dj["exact"]), 4),
                            "diff_ci_lo": round(float(np.percentile(diff, 2.5)), 4),
                            "diff_ci_hi": round(float(np.percentile(diff, 97.5)), 4),
                            "ratio": round(float(di["exact"] / dj["exact"]), 3),
                            "ratio_ci_lo": round(float(np.nanpercentile(ratio, 2.5)), 3),
                            "ratio_ci_hi": round(float(np.nanpercentile(ratio, 97.5)), 3),
                            "p_two_side": round(p_two, 4),
                            "n_boot": N_BOOT, "seed": sd,
                            "n_blocks_high": len(di["inter"]),
                            "n_blocks_low": len(dj["inter"]),
                        })
                log(f"  contrast {pair_label} {gi} vs {gj}: "
                    f"diff={di['exact']-dj['exact']:+.4f} ratio={di['exact']/dj['exact']:.2f}")

    # ---------------- write outputs ----------------
    out1 = os.path.join(RESULTS, "e5e_bootstrap_100m.csv")
    with open(out1, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    out2 = os.path.join(RESULTS, "e5e_region_contrasts_100m.csv")
    with open(out2, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(contrast_rows[0].keys()))
        w.writeheader(); w.writerows(contrast_rows)
    out3 = os.path.join(RESULTS, "e5e_moran_100m.csv")
    with open(out3, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["pair", "scale", "block_km",
                                          "n_blocks", "morans_I", "perm_p"])
        w.writeheader(); w.writerows(moran_rows)

    meta = {
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "git_commit": _git(),
        "primary_resolution_m": RES_M,
        "primary_resolution_rationale":
            "30->100 m global IoU change <=0.4% (E4); point estimate and CI "
            "are both computed on the 100 m grid so they refer to one estimand",
        "block_sizes_km": BLOCK_SIZES_KM,
        "n_bootstrap_per_seed": N_BOOT,
        "seeds": SEEDS,
        "estimand": "IoU of regional totals = sum(intersection_blocks)/sum(union_blocks)",
        "resampling_unit": "square spatial block; blocks with union==0 excluded",
        "contrast_method": "independent block resampling within each disjoint region; "
                           "difference and ratio distributions; p from sign of distribution",
        "morans": {"k": MORAN_K, "n_perm": MORAN_PERM, "weights": "row-standardised kNN"},
        "monte_carlo_uncertainty": "std of CI endpoints across the 5 independent seeds",
        "runtime_s": round(time.time() - _T0, 1),
        "max_rss_gb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6, 2),
        "supersedes": "results/superseded_e5_longitude_bands/e5c_iou_bootstrap.csv",
    }
    with open(os.path.join(RESULTS, "e5e_bootstrap_meta.json"), "w") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    log(f"saved: {out1}")
    log(f"saved: {out2}")
    log(f"saved: {out3}")
    log(f"runtime: {time.time()-_T0:.1f}s  maxrss="
        f"{resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1e6:.2f}GB")


def _git():
    import subprocess
    try:
        return subprocess.check_output(["git", "-C", ROOT, "rev-parse", "HEAD"],
                                       text=True).strip()
    except Exception:
        return "UNKNOWN"


if __name__ == "__main__":
    main()
