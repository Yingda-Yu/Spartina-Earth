#!/usr/bin/env python3
"""
R4-04 — Statistical robustness of the regional contrasts under the R4-01
attribution policies.

Principle (R4 brief): recalculate direct regional contrasts ONLY where R4
changes the analysis domain or regional assignment.  The national-scale
results and the policy-B regional results are unchanged (E5e, seed 202601,
5 seeds, 1000 reps) and are NOT rerun.  What changes is regional
attribution:

  - policy A (direct marine-polygon membership only): the regional domain
    loses the 34.42% assigned pixels -> regional IoU and contrasts change;
  - policy C (nearest assignment with a distance cap): pixels beyond the
    cap are unassigned -> regional domains change;
  - policy B (no cap) was the E5e setting.

This script reuses the verified E5e framework verbatim (same estimand
IoU of regional totals at 100 m, same square-block resampling, same seeds,
same direct two-region contrast method) and applies it to policies A and
C with caps 5/10/20 km.  Contrasts use the E5e primary block size 2 km;
block-size sensitivity for regional IoU is reported at 1/2/5/10 km.

Outputs
  results/r4_bootstrap_regional.csv     (regional IoU + CI per policy/block)
  results/r4_region_contrasts_policy.csv (direct diff/ratio contrasts)
  results/r4_bootstrap_meta.json
"""
import os, csv, json, time, resource, subprocess, sys
os.environ.setdefault("PROJ_LIB",
    "/data/yingda/software/miniconda3/envs/spartina-earth/share/proj")
import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
PAPER = os.path.join(ROOT, "papers", "paper1_map_reliability")
RESULTS = os.path.join(PAPER, "results")
CACHE = os.path.join(ROOT, "work", "cache", "paper1_100m")
LOG_PATH = os.path.join(CACHE, "r4_bootstrap.log")

sys.path.insert(0, HERE)
import e5e_bootstrap_100m as e5e   # verified R3.1 framework

RES_M = 100
REGIONS = ["Bohai_Yellow", "East_China", "South_China"]
PAIRS = ["CMSA_vs_CMSSM", "CMSA_vs_GEODATA", "CMSSM_vs_GEODATA"]
BLOCK_SIZES_KM = [1, 2, 5, 10]
CONTRAST_BS_KM = 2
POLICIES = ["A", "C_5km", "C_10km", "C_20km"]

_T0 = time.time()

def log(msg):
    line = (f"[{time.time()-_T0:8.1f}s "
            f"{resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1e6:5.2f}GB] {msg}")
    print(line, flush=True)
    with open(LOG_PATH, "a") as f:
        f.write(line + "\n")

def _git():
    try:
        return subprocess.check_output(["git", "-C", ROOT, "rev-parse", "HEAD"],
                                       text=True).strip()
    except Exception:
        return "UNKNOWN"

def build_policy_masks(direct, arr, H, W, policy, cap_km=None):
    """Region masks + per-residual assignment state, per R4-01 definitions."""
    union_pos = np.zeros((H, W), dtype=bool)
    for a in arr.values():
        union_pos |= a.astype(bool)
    any_direct = np.logical_or.reduce([direct[g] for g in REGIONS])
    resid = union_pos & ~any_direct
    out = {g: direct[g].copy() for g in REGIONS}
    n_resid = int(resid.sum())
    if n_resid == 0 or policy == "A":
        return out, resid, None, None
    ys, xs = np.nonzero(resid)
    query = np.column_stack([ys, xs]).astype(np.float32)
    best_d = np.full(n_resid, np.inf, dtype=np.float32)
    best_k = np.full(n_resid, -1, dtype=np.int8)
    for k, g in enumerate(REGIONS):
        edge = direct[g] & ~ndimage.binary_erosion(
            direct[g], structure=np.ones((3, 3), bool), border_value=0)
        ey, ex = np.nonzero(edge)
        tree = cKDTree(np.column_stack([ey, ex]).astype(np.float32))
        dd, _ = tree.query(query, k=1, workers=-1)
        upd = dd < best_d
        best_d[upd] = dd[upd]
        best_k[upd] = k
    ok = np.ones(n_resid, dtype=bool)
    if policy.startswith("C"):
        ok = best_d * RES_M / 1000.0 <= cap_km
    for k, g in enumerate(REGIONS):
        sel = (best_k == k) & ok
        if sel.any():
            out[g][ys[sel], xs[sel]] = True
    return out, resid, best_k, best_d

def main():
    open(LOG_PATH, "w").close()
    log("=" * 72)
    log("R4-04 — bootstrap under attribution policies A / C (B = E5e, not rerun)")
    log(f"git_commit={_git()}")

    d = np.load(os.path.join(CACHE, "products_100m_epsg3410.npz"))
    arr = {"CMSA": d["cmsa"].astype(bool), "CMSSM": d["cmssm"].astype(bool),
           "GEODATA": d["geo"].astype(bool)}
    H, W = int(d["H"]), int(d["W"])
    m = np.load(os.path.join(CACHE, "marine_masks_100m.npz"))
    direct = {g: m[f"{g}__mask"].astype(bool) for g in REGIONS}
    log(f"loaded products {W}x{H}")

    pairs = {"CMSA_vs_CMSSM": (arr["CMSA"], arr["CMSSM"]),
             "CMSA_vs_GEODATA": (arr["CMSA"], arr["GEODATA"]),
             "CMSSM_vs_GEODATA": (arr["CMSSM"], arr["GEODATA"])}

    rows, contrast_rows = [], []
    for policy in POLICIES:
        cap = int(policy.split("_")[1][:-2]) if policy.startswith("C") else None
        masks, resid, best_k, best_d = build_policy_masks(
            direct, arr, H, W, policy, cap)
        detail = {}
        for pair_label in PAIRS:
            a, b = pairs[pair_label]
            ya, xa, yb, xb = e5e.pair_pixels(a, b)
            for gname in REGIONS:
                mask = masks[gname]
                for bs_km in BLOCK_SIZES_KM:
                    bp = int(bs_km * 1000 / RES_M)
                    t = time.time()
                    ca, cb, ci, cu, nbh, nbw, cy, cx = e5e.block_counts(
                        ya, xa, yb, xb, mask, H, W, bp)
                    n_total = nbh * nbw
                    informative = cu > 0
                    n_inf = int(informative.sum())
                    if n_inf < 10:
                        rows.append({
                            "policy": policy, "pair": pair_label,
                            "scale": gname, "block_km": bs_km,
                            "resolution_m": RES_M, "exact_iou": "",
                            "ci_lo": "", "ci_hi": "",
                            "n_blocks_total": n_total,
                            "n_blocks_informative": n_inf,
                            "note": f"skipped: <10 informative blocks"})
                        continue
                    exact = float(ci.sum() / cu.sum())
                    i_arr, u_arr = ci[informative], cu[informative]
                    seed_summaries = []
                    for sd in e5e.SEEDS:
                        samples = e5e.boot_iou(i_arr, u_arr, e5e.N_BOOT,
                                                np.random.default_rng(sd))
                        seed_summaries.append(e5e.summarise(samples))
                    prim = seed_summaries[0]
                    lo_sp = float(np.std([s["ci_lo"] for s in seed_summaries], ddof=1))
                    hi_sp = float(np.std([s["ci_hi"] for s in seed_summaries], ddof=1))
                    rows.append({
                        "policy": policy, "pair": pair_label, "scale": gname,
                        "block_km": bs_km, "resolution_m": RES_M,
                        "exact_iou": round(exact, 4),
                        "ci_lo": round(prim["ci_lo"], 4),
                        "ci_hi": round(prim["ci_hi"], 4),
                        "n_blocks_total": n_total,
                        "n_blocks_informative": n_inf,
                        "note": "",
                    })
                    if bs_km == CONTRAST_BS_KM:
                        detail.setdefault(pair_label, {})[gname] = {
                            "inter": i_arr, "union": u_arr, "exact": exact}
                    log(f"  {policy:7s} {gname:13s} {pair_label:17s} "
                        f"{bs_km:2d}km IoU={exact:.4f} "
                        f"CI=[{prim['ci_lo']:.4f},{prim['ci_hi']:.4f}] "
                        f"N_inf={n_inf} ({time.time()-t:.1f}s)")
        # direct contrasts, E5e method
        for pair_label in PAIRS:
            dd = detail.get(pair_label, {})
            regs = [g for g in REGIONS if g in dd]
            for i in range(len(regs)):
                for j in range(i + 1, len(regs)):
                    gi, gj = regs[i], regs[j]
                    di, dj = dd[gi], dd[gj]
                    sd = e5e.SEEDS[0]
                    rng = np.random.default_rng(sd)
                    si = e5e.boot_iou(di["inter"], di["union"], e5e.N_BOOT, rng)
                    sj = e5e.boot_iou(dj["inter"], dj["union"], e5e.N_BOOT, rng)
                    diff = si - sj
                    with np.errstate(divide="ignore", invalid="ignore"):
                        ratio = np.where(sj != 0, si / sj, np.nan)
                    p_two = min(2.0 * min(float(np.mean(diff <= 0)),
                                          float(np.mean(diff >= 0))), 1.0)
                    contrast_rows.append({
                        "policy": policy, "pair": pair_label,
                        "region_high": gi, "region_low": gj,
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
                        "n_boot": e5e.N_BOOT, "seed": sd,
                        "n_blocks_high": len(di["inter"]),
                        "n_blocks_low": len(dj["inter"]),
                    })
                    log(f"  contrast {policy} {pair_label} {gi}-{gj}: "
                        f"ratio={di['exact']/dj['exact']:.2f} "
                        f"[{np.nanpercentile(ratio,2.5):.2f},"
                        f"{np.nanpercentile(ratio,97.5):.2f}] p={p_two:.4f}")

    with open(os.path.join(RESULTS, "r4_bootstrap_regional.csv"), "w",
              newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    with open(os.path.join(RESULTS, "r4_region_contrasts_policy.csv"), "w",
              newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(contrast_rows[0].keys()))
        w.writeheader()
        w.writerows(contrast_rows)

    meta = {
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "git_commit": _git(),
        "framework": "reuses e5e_bootstrap_100m (verified R3.1) verbatim: "
                     "estimand = IoU of regional totals at 100 m; square-block "
                     "resampling; blocks with union==0 excluded; 5 seeds x "
                     "1000 reps; direct two-region contrast by independent "
                     "in-region resampling",
        "policies": {"A": "direct marine-polygon membership only",
                     "C_5km": "nearest assignment capped at 5 km",
                     "C_10km": "nearest assignment capped at 10 km (primary)",
                     "C_20km": "nearest assignment capped at 20 km"},
        "not_rerun": "national scale and policy-B regional results "
                     "(e5e_bootstrap_100m.csv, e5e_region_contrasts_100m.csv) "
                     "are unchanged by R4-01 and were NOT recomputed",
        "primary_contrast_block_km": CONTRAST_BS_KM,
        "block_sizes_km": BLOCK_SIZES_KM,
        "seeds": e5e.SEEDS,
        "n_bootstrap_per_seed": e5e.N_BOOT,
        "runtime_s": round(time.time() - _T0, 1),
        "max_rss_gb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6, 2),
    }
    with open(os.path.join(RESULTS, "r4_bootstrap_meta.json"), "w") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    log(f"done in {time.time()-_T0:.1f}s")

if __name__ == "__main__":
    main()
