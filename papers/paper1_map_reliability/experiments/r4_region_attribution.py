#!/usr/bin/env python3
"""
R4-01 — Regional attribution audit: how much do the offshore
nearest-region assignments (34.42% of the positive-union pixels in E5d)
matter for the regional IoU results?

Policies
--------
A. DIRECT   — region = direct marine-polygon membership only; pixels in no
              polygon are excluded from every region and the excluded share
              is reported explicitly as coverage.
B. NEAREST  — the E5d/E5e policy: every residual pixel assigned to the
              nearest group boundary (no distance limit).  This is the
              policy behind the published regional IoU values.
C. CAPPED(t) — nearest assignment with a documented distance cap; pixels
              farther than t km from every group boundary form a separate
              "unassigned" category that is excluded from all regions and
              reported.  Primary cap 10 km (intertidal Spartina habitat
              lies within a few km of the shoreline; Natural Earth 10m
              coastline generalization is of the same order, so larger
              caps increasingly attribute pixels across genuinely
              different coasts).  Sensitivity caps: 5, 20, 50 km.

For every product pair x region x policy we report:
  - direct / assigned / unassigned positive-union pixel counts
  - intersection and union contributions *from assigned pixels*
  - regional IoU and its change relative to policy A
Per region (shared across pairs): assignment distance distribution and
counts beyond 1/5/10/20/50 km.  Per product: direct vs assigned shares,
so no product is silently excluded.

Outputs
  results/r4_region_assignment_sensitivity.csv
  results/r4_assignment_distances.csv
  results/r4_attribution_meta.json
  figures/fig_r4_region_assignment.pdf  (+ .png preview)
"""
import os, csv, json, time, subprocess
os.environ.setdefault("PROJ_LIB",
    "/data/yingda/software/miniconda3/envs/spartina-earth/share/proj")
os.environ.setdefault("MPLCONFIGDIR", "/data/yingda/Spartina-Earth/work/tmp_mpl")
import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.lines import Line2D

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
PAPER = os.path.join(ROOT, "papers", "paper1_map_reliability")
RESULTS = os.path.join(PAPER, "results")
FIGURES = os.path.join(PAPER, "figures")
CACHE = os.path.join(ROOT, "work", "cache", "paper1_100m")
LOG_PATH = os.path.join(CACHE, "r4_attribution.log")

RES_M = 100
REGIONS = ["Bohai_Yellow", "East_China", "South_China"]
PAIRS = [("CMSA_vs_CMSSM", "CMSA", "CMSSM"),
         ("CMSA_vs_GEODATA", "CMSA", "GEODATA"),
         ("CMSSM_vs_GEODATA", "CMSSM", "GEODATA")]
DIST_BINS_KM = [1, 5, 10, 20, 50]
CAPS_KM = [5, 10, 20, 50]
PRIMARY_CAP_KM = 10
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

def main():
    open(LOG_PATH, "w").close()
    log("=" * 72)
    log("R4-01 — regional attribution audit (policies A/B/C)")
    log(f"git_commit={git_commit()}")

    # ---------------- inputs ----------------
    d = np.load(os.path.join(CACHE, "products_100m_epsg3410.npz"))
    arr = {"CMSA": d["cmsa"].astype(bool), "CMSSM": d["cmssm"].astype(bool),
           "GEODATA": d["geo"].astype(bool)}
    H, W = int(d["H"]), int(d["W"])
    db = [float(v) for v in d["db"]]
    m = np.load(os.path.join(CACHE, "marine_masks_100m.npz"))
    # cached group masks are DIRECT polygon membership (saved before
    # e5d's in-place nearest-assignment mutation) — exactly policy A.
    direct = {g: m[f"{g}__mask"].astype(bool) for g in REGIONS}
    log(f"loaded products {W}x{H}; positive px: "
        + ", ".join(f"{k}={int(v.sum()):,}" for k, v in arr.items()))

    union_pos = arr["CMSA"] | arr["CMSSM"] | arr["GEODATA"]
    n_union = int(union_pos.sum())
    any_direct = direct["Bohai_Yellow"] | direct["East_China"] | direct["South_China"]
    resid = union_pos & ~any_direct
    n_resid = int(resid.sum())
    n_direct = n_union - n_resid
    log(f"positive union {n_union:,}: direct {n_direct:,} "
        f"({n_direct/n_union*100:.2f}%), residual {n_resid:,} "
        f"({n_resid/n_union*100:.2f}%)")

    # ---------------- nearest assignment (E5d method, keep distances) -----
    ys, xs = np.nonzero(resid)
    query = np.column_stack([ys, xs]).astype(np.float32)
    trees = {}
    for g in REGIONS:
        edge = direct[g] & ~ndimage.binary_erosion(
            direct[g], structure=np.ones((3, 3), bool), border_value=0)
        ey, ex = np.nonzero(edge)
        trees[g] = cKDTree(np.column_stack([ey, ex]).astype(np.float32))
    best_d = np.full(n_resid, np.inf, dtype=np.float32)
    best_k = np.full(n_resid, -1, dtype=np.int8)
    for k, g in enumerate(REGIONS):
        dd, _ = trees[g].query(query, k=1, workers=-1)
        upd = dd < best_d
        best_d[upd] = dd[upd]
        best_k[upd] = k
    dist_km = best_d * RES_M / 1000.0
    log(f"assignment done: max {dist_km.max():.2f} km, median "
        f"{np.median(dist_km):.2f} km")

    # per-region distance distribution (shared across pairs)
    dist_rows = []
    for gi, g in enumerate(REGIONS):
        sel = best_k == gi
        dd = dist_km[sel]
        row = {"region": g, "n_assigned_px": int(sel.sum())}
        if len(dd):
            row.update({
                "dist_median_km": round(float(np.median(dd)), 3),
                "dist_p90_km": round(float(np.percentile(dd, 90)), 3),
                "dist_p99_km": round(float(np.percentile(dd, 99)), 3),
                "dist_max_km": round(float(dd.max()), 3)})
        else:
            row.update({"dist_median_km": None, "dist_p90_km": None,
                        "dist_p99_km": None, "dist_max_km": None})
        for b in DIST_BINS_KM:
            row[f"n_beyond_{b}km"] = int((dd > b).sum())
        dist_rows.append(row)
        log(f"  {g}: assigned {int(sel.sum()):,}, median "
            f"{row['dist_median_km']} km, >10km {row['n_beyond_10km']}, "
            f"max {row['dist_max_km']} km")

    with open(os.path.join(RESULTS, "r4_assignment_distances.csv"), "w",
              newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(dist_rows[0].keys()))
        w.writeheader()
        w.writerows(dist_rows)

    # per-product composition (no silent exclusion check)
    prod_rows = []
    for p, a in arr.items():
        assigned_n = int(a[resid].sum())
        prod_rows.append({"product": p, "positive_px": int(a.sum()),
                          "direct_px": int(a.sum()) - assigned_n,
                          "assigned_px": assigned_n,
                          "assigned_pct": round(assigned_n / float(a.sum()) * 100, 2)})
        log(f"  product {p}: {assigned_n:,}/{int(a.sum()):,} px assigned by "
            f"nearest ({prod_rows[-1]['assigned_pct']}%)")

    # ---------------- policy masks ----------------
    def build_masks(policy, cap_km=None):
        """Return (region masks, excluded-union-pixel mask)."""
        out = {g: direct[g].copy() for g in REGIONS}
        excluded = np.zeros_like(resid)
        if policy == "A":
            excluded = resid.copy()
        elif policy == "B":
            for k, g in enumerate(REGIONS):
                sel = best_k == k
                if sel.any():
                    out[g][ys[sel], xs[sel]] = True
        elif policy == "C":
            ok = dist_km <= cap_km
            excluded[ys[~ok], xs[~ok]] = True
            for k, g in enumerate(REGIONS):
                sel = (best_k == k) & ok
                if sel.any():
                    out[g][ys[sel], xs[sel]] = True
        else:
            raise ValueError(policy)
        return out, excluded

    policies = [("A", "direct membership only", None)]
    policies.append(("B", "nearest assignment (E5d/E5e, no cap)", None))
    for c in CAPS_KM:
        policies.append(("C", "nearest with cap", c))

    sens_rows = []
    iou_lookup = {}
    for policy, desc, cap in policies:
        pkey = f"{policy}" + ("" if cap is None else f"_{cap}km")
        masks, excluded = build_masks(policy, cap)
        n_excl = int(excluded.sum())
        excl_pct = round(n_excl / n_union * 100, 2) if n_union else 0.0
        if policy == "A":
            log(f"policy A ({desc}): excluded {n_excl:,} px = {excl_pct}% of union")
        for pair_label, pa, pb in PAIRS:
            a, b = arr[pa], arr[pb]
            for g in REGIONS:
                msk = masks[g]
                a_r, b_r = a[msk], b[msk]
                inter = int((a_r & b_r).sum())
                union_r = int((a_r | b_r).sum())
                # contributions from formerly-residual pixels inside mask
                m_as = msk & resid
                a_as = int((a & m_as).sum())
                b_as = int((b & m_as).sum())
                i_as = int((a & b & m_as).sum())
                u_as = int(((a | b) & m_as).sum())
                iou = inter / union_r if union_r else float("nan")
                iou_lookup[(pkey, pair_label, g)] = iou
                row = {
                    "policy": pkey, "policy_description": desc,
                    "cap_km": cap, "pair": pair_label, "region": g,
                    "region_union_px": union_r,
                    "region_union_km2": round(union_r * PX_KM2, 2),
                    "intersection_px": inter,
                    "intersection_km2": round(inter * PX_KM2, 2),
                    "iou": round(iou, 4) if union_r else "",
                    "direct_px_in_region": int((union_pos & direct[g]).sum()),
                    "assigned_px_in_region": int((union_pos & msk & resid).sum()),
                    "unassigned_px_excluded_total": n_excl,
                    "excluded_pct_of_union": excl_pct,
                    "assigned_intersection_px": i_as,
                    "assigned_union_px": u_as,
                    "assigned_union_share_pct": round(u_as / union_r * 100, 2)
                        if union_r else "",
                    "assigned_product_a_px": a_as,
                    "assigned_product_b_px": b_as,
                }
                sens_rows.append(row)
        # per-policy contrast summary
        for pair_label, _, _ in PAIRS:
            iou_b = iou_lookup.get((pkey, pair_label, "Bohai_Yellow"), float("nan"))
            iou_s = iou_lookup.get((pkey, pair_label, "South_China"), float("nan"))
            ratio = iou_b / iou_s if iou_s and iou_s == iou_s and iou_s > 0 else float("nan")
            sens_rows.append({
                "policy": pkey, "policy_description": desc, "cap_km": cap,
                "pair": pair_label, "region": "CONTRAST_Bohai_over_South",
                "region_union_px": "", "region_union_km2": "",
                "intersection_px": "", "intersection_km2": "",
                "iou": round(ratio, 3) if ratio == ratio else "",
                "direct_px_in_region": "", "assigned_px_in_region": "",
                "unassigned_px_excluded_total": n_excl,
                "excluded_pct_of_union": excl_pct,
                "assigned_intersection_px": "", "assigned_union_px": "",
                "assigned_union_share_pct": "",
                "assigned_product_a_px": "", "assigned_product_b_px": ""})

    out_csv = os.path.join(RESULTS, "r4_region_assignment_sensitivity.csv")
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(sens_rows[0].keys()))
        w.writeheader()
        w.writerows(sens_rows)
    log(f"saved {out_csv} ({len(sens_rows)} rows)")

    # quick log of key contrasts
    for pkey in ["A", "B", "C_5km", "C_10km", "C_20km", "C_50km"]:
        line = [pkey]
        for pair_label, _, _ in PAIRS:
            ib = iou_lookup.get((pkey, pair_label, "Bohai_Yellow"), float("nan"))
            is_ = iou_lookup.get((pkey, pair_label, "South_China"), float("nan"))
            line.append(f"{pair_label}: B={ib:.4f} S={is_:.4f}")
        log("  " + " | ".join(line))

    # ---------------- figure ----------------
    # map of positive-union pixels: direct in blue-grey, assigned colored
    # by nearest-assignment distance; region boundaries for context
    px_x = db[0] / 1000 + (xs + 0.5) * RES_M / 1000
    px_y = db[3] / 1000 - (ys + 0.5) * RES_M / 1000
    dy, dx = np.nonzero(union_pos & any_direct)
    dx_x = db[0] / 1000 + (dx + 0.5) * RES_M / 1000
    dx_y = db[3] / 1000 - (dy + 0.5) * RES_M / 1000

    fig, ax = plt.subplots(figsize=(11, 6.2))
    # region outlines (downsampled boundaries) for geographic context
    for g, gcol in zip(REGIONS, ["0.55", "0.55", "0.55"]):
        sub = direct[g][::4, ::4]
        edge = sub & ~ndimage.binary_erosion(sub,
                                             structure=np.ones((3, 3), bool))
        gy, gx = np.nonzero(edge)
        ax.scatter((db[0] / 1000 + gx * 4 * RES_M / 1000),
                   (db[3] / 1000 - gy * 4 * RES_M / 1000),
                   s=0.05, c=gcol, linewidths=0, rasterized=True, zorder=1)
    for g in REGIONS:
        gy, gx = np.nonzero(direct[g][::4, ::4])
        if len(gy) == 0:
            continue
        cx = db[0] / 1000 + gx.mean() * 4 * RES_M / 1000
        cy = db[3] / 1000 - gy.mean() * 4 * RES_M / 1000
        ax.text(cx, cy, g.replace("_", " "), fontsize=9, style="italic",
                color="0.25", ha="center", zorder=4)
    ax.scatter(dx_x, dx_y, s=0.6, c="#7aa6c2", alpha=0.8, linewidths=0,
               rasterized=True, zorder=2, label="inside marine polygon (direct)")
    # distance bins; a bin is shown only if it contains pixels (no pixel
    # exceeds 53.97 km, so the >50 km bin may be empty)
    cand = [(0, 1, "0–1"), (1, 5, "1–5"), (5, 10, "5–10"),
            (10, 20, "10–20"), (20, 50, "20–50"), (50, np.inf, ">50")]
    kept = [(lo, hi, lab) for lo, hi, lab in cand
            if ((dist_km >= lo) & (dist_km < hi)).any()]
    labels = [lab for _, _, lab in kept]
    bounds = [lo for lo, _, _ in kept] + [kept[-1][1]]
    cmap = ListedColormap(plt.cm.YlOrRd(np.linspace(0.3, 1.0, len(labels))))
    col_idx = np.searchsorted(bounds[1:-1], dist_km, side="left")
    sc = ax.scatter(px_x, px_y, s=1.8, c=col_idx, cmap=cmap,
                    norm=BoundaryNorm(np.arange(len(labels) + 1), len(labels)),
                    linewidths=0, rasterized=True, zorder=3)
    cbar = fig.colorbar(sc, ax=ax, ticks=np.arange(len(labels)) + 0.5, shrink=0.85)
    cbar.ax.set_yticklabels(labels, fontsize=8)
    cbar.set_label("nearest-assignment distance (km)", fontsize=9)
    handles = [Line2D([0], [0], marker="o", color="w", markerfacecolor="#7aa6c2",
                      markersize=5, label="direct marine-polygon pixels"),
               Line2D([0], [0], marker="o", color="w", markerfacecolor="#fc8d59",
                      markersize=5, label="nearest-assigned pixels (color = distance)")]
    ax.legend(handles=handles, loc="lower left", fontsize=8, framealpha=0.9)
    ax.set_xlabel("EPSG:3410 x (km)")
    ax.set_ylabel("EPSG:3410 y (km)")
    ax.set_title("R4-01 — regional attribution of mapped Spartina positives at 100 m:\n"
                 f"direct marine-polygon membership vs nearest assignment "
                 f"({n_resid:,} px = {n_resid/n_union*100:.1f}% of positive union)",
                 fontsize=10)
    pad = 60
    ax.set_xlim(min(dx_x.min(), px_x.min()) - pad, max(dx_x.max(), px_x.max()) + pad)
    ax.set_ylim(min(dx_y.min(), px_y.min()) - pad, max(dx_y.max(), px_y.max()) + pad)
    ax.set_aspect("equal")
    fig.tight_layout()
    for ext in ["pdf", "png"]:
        fig.savefig(os.path.join(FIGURES, f"fig_r4_region_assignment.{ext}"),
                    dpi=300 if ext == "png" else None)
    plt.close(fig)
    log(f"saved figures/fig_r4_region_assignment.pdf/.png")

    # ---------------- meta ----------------
    meta = {
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "git_commit": git_commit(),
        "positive_union_px": n_union,
        "direct_px": n_direct,
        "assigned_px": n_resid,
        "assigned_pct": round(n_resid / n_union * 100, 2),
        "products": prod_rows,
        "region_distance_summary": dist_rows,
        "policies": {
            "A": "direct marine-polygon membership only (residual excluded)",
            "B": "nearest assignment without cap (E5d/E5e policy)",
            "C": f"nearest assignment with cap; primary {PRIMARY_CAP_KM} km; "
                 f"sensitivity {CAPS_KM} km",
        },
        "primary_cap_rationale": "intertidal Spartina habitat lies within a few "
                                 "km of the shoreline; Natural Earth 10m coastline "
                                 "generalization error is of the same order, so "
                                 "caps beyond ~10 km increasingly attribute "
                                 "pixels across genuinely different coasts",
        "outputs": ["results/r4_region_assignment_sensitivity.csv",
                    "results/r4_assignment_distances.csv",
                    "figures/fig_r4_region_assignment.pdf"],
        "runtime_s": round(time.time() - _T0, 1),
    }
    with open(os.path.join(RESULTS, "r4_attribution_meta.json"), "w") as f:
        json.dump(meta, f, indent=2)
    log(f"done in {time.time()-_T0:.1f}s")

if __name__ == "__main__":
    main()
