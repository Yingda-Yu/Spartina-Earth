#!/usr/bin/env python3
"""
R4-03 — South China Sea region low-IoU diagnostics (100 m, EPSG:3410).

Scope: CMSA–GEODATA (IoU 0.1341) and CM-SSM–GEODATA (IoU 0.0835) inside the
policy-B South_China sea-region mask.  Neither product is treated as ground
truth; all quantities are symmetric descriptions of spatial disagreement.

Quantified, per product and per pair:
  - positive area, intersection, union, only-A / only-B ("false spatial
    disagreement relative to each other")
  - fragmentation: patch counts (connected components, 8-connectivity),
    mean/median patch area, share of area in patches < 1 ha and < 5 ha
    (small-patch sensitivity)
  - boundary sensitivity: share of only-A pixels within 100 m / 500 m /
    1 km / 5 km of the nearest B-positive pixel (boundary misalignment vs
    disjoint-segment disagreement)
  - disagreement clustering: largest connected disagreement clusters with
    location and area, used to pick zoom windows
  - coverage / no-data: cross-reference to the R4-02 verdict (GEODATA
    entity is presence-only; absence and no-data indistinguishable) and
    the coastal-strip proxy gaps in the South

Outputs
  results/r4_south_china_diagnostics.csv
  results/r4_south_china_clusters.csv
  figures/fig_r4_south_china_zoom.{pdf,png}
  figures/fig_r4_south_china_overview.{pdf,png}
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
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
PAPER = os.path.join(ROOT, "papers", "paper1_map_reliability")
RESULTS = os.path.join(PAPER, "results")
FIGURES = os.path.join(PAPER, "figures")
CACHE = os.path.join(ROOT, "work", "cache", "paper1_100m")
LOG_PATH = os.path.join(CACHE, "r4_south_china.log")

RES_M = 100
REGIONS = ["Bohai_Yellow", "East_China", "South_China"]
PX_KM2 = RES_M ** 2 / 1e6
ZOOM_KM = 45  # half-width of zoom windows
N_ZOOM = 3

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

def fragmentation(mask):
    lab, n = ndimage.label(mask, structure=np.ones((3, 3), bool))
    if n == 0:
        return {"n_patches": 0, "mean_patch_ha": None, "median_patch_ha": None,
                "area_lt_1ha_pct": None, "area_lt_5ha_pct": None}
    sizes = np.bincount(lab.ravel())[1:]  # exclude background
    ha = sizes * PX_KM2 * 100  # ha
    total = sizes.sum()
    return {
        "n_patches": int(n),
        "mean_patch_ha": round(float(ha.mean()), 2),
        "median_patch_ha": round(float(np.median(ha)), 2),
        "area_lt_1ha_pct": round(float(sizes[ha < 1].sum() / total * 100), 2),
        "area_lt_5ha_pct": round(float(sizes[ha < 5].sum() / total * 100), 2),
    }

def boundary_shares(only_mask, other_pos):
    """Share of `only_mask` pixels within given distances of other's positives."""
    ys, xs = np.nonzero(only_mask)
    oy, ox = np.nonzero(other_pos)
    tree = cKDTree(np.column_stack([oy, ox]).astype(np.float32))
    dd, _ = tree.query(np.column_stack([ys, xs]).astype(np.float32), k=1,
                       workers=-1)
    dd_km = dd * RES_M / 1000.0
    return {"within_100m_pct": round(float((dd_km <= 0.1).mean() * 100), 2),
            "within_500m_pct": round(float((dd_km <= 0.5).mean() * 100), 2),
            "within_1km_pct": round(float((dd_km <= 1.0).mean() * 100), 2),
            "beyond_5km_pct": round(float((dd_km > 5.0).mean() * 100), 2),
            "median_km": round(float(np.median(dd_km)), 3)}

def main():
    open(LOG_PATH, "w").close()
    log("=" * 72)
    log("R4-03 — South China low-IoU diagnostics")
    log(f"git_commit={git_commit()}")

    d = np.load(os.path.join(CACHE, "products_100m_epsg3410.npz"))
    arr = {"CMSA": d["cmsa"].astype(bool), "CMSSM": d["cmssm"].astype(bool),
           "GEODATA": d["geo"].astype(bool)}
    H, W = int(d["H"]), int(d["W"])
    db = [float(v) for v in d["db"]]
    m = np.load(os.path.join(CACHE, "marine_masks_100m.npz"))
    direct = {g: m[f"{g}__mask"].astype(bool) for g in REGIONS}
    union_pos = arr["CMSA"] | arr["CMSSM"] | arr["GEODATA"]
    regions_b = policy_b_masks(direct, union_pos, H, W)
    south = regions_b["South_China"]
    log(f"loaded products {W}x{H}; South_China mask "
        f"{int(south.sum()):,} px")

    # crop to South bounding box for speed
    ys, xs = np.nonzero(south | (union_pos & south))
    sy, sx = np.nonzero(south)
    y0, y1 = max(sy.min() - 50, 0), min(sy.max() + 50, H)
    x0, x1 = max(sx.min() - 50, 0), min(sx.max() + 50, W)
    S = {p: a[y0:y1, x0:x1] & south[y0:y1, x0:x1] for p, a in arr.items()}
    S_union = arr["CMSA"] | arr["CMSSM"] | arr["GEODATA"]
    S_union = S_union[y0:y1, x0:x1] & south[y0:y1, x0:x1]
    log(f"South crop rows {y0}:{y1} cols {x0}:{x1} "
        f"({y1-y0}x{x1-x0}); union px {int(S_union.sum()):,}")

    # ---------------- per-product fragmentation ----------------
    frag_rows = []
    for p, a in S.items():
        f = fragmentation(a)
        f.update({"product": p, "positive_px": int(a.sum()),
                  "area_km2": round(int(a.sum()) * PX_KM2, 3)})
        frag_rows.append(f)
        log(f"  {p}: {f['n_patches']} patches, median "
            f"{f['median_patch_ha']} ha, <1ha share {f['area_lt_1ha_pct']}%")

    # ---------------- pair diagnostics ----------------
    pair_rows, cluster_rows = [], []
    cluster_top = []
    for pair_label, pa, pb in [("CMSA_vs_GEODATA", "CMSA", "GEODATA"),
                               ("CMSSM_vs_GEODATA", "CMSSM", "GEODATA")]:
        a, b = S[pa], S[pb]
        inter = int((a & b).sum())
        union_r = int((a | b).sum())
        only_a = a & ~b
        only_b = b & ~a
        iou = inter / union_r if union_r else float("nan")
        bs_a = boundary_shares(only_a, b)
        bs_b = boundary_shares(only_b, a)
        pair_rows.append({
            "pair": pair_label, "region": "South_China",
            "a_area_km2": round(int(a.sum()) * PX_KM2, 3),
            "b_area_km2": round(int(b.sum()) * PX_KM2, 3),
            "intersection_km2": round(inter * PX_KM2, 3),
            "union_km2": round(union_r * PX_KM2, 3),
            "iou": round(iou, 4),
            "only_a_km2": round(int(only_a.sum()) * PX_KM2, 3),
            "only_b_km2": round(int(only_b.sum()) * PX_KM2, 3),
            "only_a_within_100m_of_b_pct": bs_a["within_100m_pct"],
            "only_a_within_500m_of_b_pct": bs_a["within_500m_pct"],
            "only_a_within_1km_of_b_pct": bs_a["within_1km_pct"],
            "only_a_beyond_5km_of_b_pct": bs_a["beyond_5km_pct"],
            "only_a_median_dist_to_b_km": bs_a["median_km"],
            "only_b_within_100m_of_a_pct": bs_b["within_100m_pct"],
            "only_b_within_500m_of_a_pct": bs_b["within_500m_pct"],
            "only_b_within_1km_of_a_pct": bs_b["within_1km_pct"],
            "only_b_beyond_5km_of_a_pct": bs_b["beyond_5km_pct"],
            "only_b_median_dist_to_a_km": bs_b["median_km"],
        })
        log(f"  {pair_label}: IoU {iou:.4f}; only-{pa} {int(only_a.sum())} px "
            f"(median dist to {pb} {bs_a['median_km']} km); "
            f"only-{pb} {int(only_b.sum())} px (median {bs_b['median_km']} km)")
        # disagreement clusters (only_a + only_b combined disagreement map)
        for tag, om in [(f"only_{pa}", only_a), (f"only_{pb}", only_b)]:
            lab, n = ndimage.label(om, structure=np.ones((3, 3), bool))
            if n == 0:
                continue
            sizes = np.bincount(lab.ravel())[1:]
            order = np.argsort(sizes)[::-1][:5]
            for rank, ci in enumerate(order):
                yy, xx = np.nonzero(lab == ci + 1)
                cluster_rows.append({
                    "pair": pair_label, "class": tag, "rank": rank + 1,
                    "cluster_px": int(sizes[ci]),
                    "cluster_km2": round(float(sizes[ci]) * PX_KM2, 3),
                    "row_min": int(yy.min() + y0), "row_max": int(yy.max() + y0),
                    "col_min": int(xx.min() + x0), "col_max": int(xx.max() + x0),
                    "row_centre": int(yy.mean() + y0),
                    "col_centre": int(xx.mean() + x0),
                })
                if rank == 0:
                    cluster_top.append((pair_label, tag, int(sizes[ci]),
                                        int(yy.mean() + y0), int(xx.mean() + x0)))

    with open(os.path.join(RESULTS, "r4_south_china_diagnostics.csv"), "w",
              newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(pair_rows[0].keys()))
        w.writeheader()
        w.writerows(pair_rows)
    frag_csv = os.path.join(RESULTS, "r4_south_china_fragmentation.csv")
    with open(frag_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(frag_rows[0].keys()))
        w.writeheader()
        w.writerows(frag_rows)
    with open(os.path.join(RESULTS, "r4_south_china_clusters.csv"), "w",
              newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(cluster_rows[0].keys()))
        w.writeheader()
        w.writerows(cluster_rows)
    log(f"saved CSVs: diagnostics ({len(pair_rows)}), fragmentation "
        f"({len(frag_rows)}), clusters ({len(cluster_rows)})")

    # ---------------- figures ----------------
    # agreement classes: both=green, CMSA/CMSSM only=orange, GEODATA only=purple
    def agree_rgb(a, b):
        rgb = np.ones(a.shape + (3,), dtype=float)
        rgb[a & b] = [0.05, 0.55, 0.25]
        rgb[a & ~b] = [0.9, 0.5, 0.1]
        rgb[~a & b] = [0.55, 0.3, 0.75]
        return rgb

    def window(r, c, half=ZOOM_KM * 1000 // RES_M):
        return (max(r - half, 0), min(r + half, H), max(c - half, 0),
                min(c + half, W))

    # choose zoom windows: top disagreement clusters across both pairs,
    # deduplicated by proximity (< 30 km); half-width scales with cluster
    # size so small clusters are not lost in empty panels
    zooms = []
    for pair_label, tag, sz, rr, cc in sorted(cluster_top,
                                              key=lambda t: -t[2]):
        if any(abs(rr - r2) < 300 and abs(cc - c2) < 300
               for r2, c2 in [(z[0], z[1]) for z in zooms]):
            continue
        half_px = max(int(np.ceil(np.sqrt(sz) * 6)), 60)   # >= 6 km
        half_px = min(half_px, ZOOM_KM * 1000 // RES_M)
        zooms.append((rr, cc, pair_label, tag, sz, half_px))
        if len(zooms) >= N_ZOOM:
            break
    log(f"zoom windows: {[(r, c, p, t, s, h) for r, c, p, t, s, h in zooms]}")

    fig, axes = plt.subplots(1, len(zooms), figsize=(5.2 * len(zooms), 5.6))
    if len(zooms) == 1:
        axes = [axes]
    for ax, (rr, cc, pair_label, tag, sz, half_px) in zip(axes, zooms):
        r0, r1, c0, c1 = window(rr, cc, half_px)
        pa, pb = ("CMSA", "GEODATA") if "CMSA" in pair_label else ("CMSSM", "GEODATA")
        A = arr[pa][r0:r1, c0:c1]
        B = arr[pb][r0:r1, c0:c1]
        rgb = agree_rgb(A, B)
        ext = [db[0] / 1000 + c0 * RES_M / 1000,
               db[0] / 1000 + c1 * RES_M / 1000,
               db[3] / 1000 - r1 * RES_M / 1000,
               db[3] / 1000 - r0 * RES_M / 1000]
        ax.imshow(rgb, origin="upper", extent=ext, interpolation="nearest")
        ax.set_xlim(ext[0], ext[1]); ax.set_ylim(ext[2], ext[3])
        ax.set_aspect("equal")
        ax.set_xlabel("x (km)", fontsize=8)
        ax.set_ylabel("y (km)", fontsize=8)
        ax.tick_params(labelsize=7)
        disp = pair_label.replace("CMSSM", "CM-SSM").replace("_", " ")
        ax.set_title(f"{disp}: largest {tag.replace('only_', 'only-')} cluster\n"
                     f"({sz * PX_KM2:.2f} km², centre row {rr}, col {cc})",
                     fontsize=9)
    handles = [Patch(facecolor=[0.05, 0.55, 0.25], label="both products"),
               Patch(facecolor=[0.9, 0.5, 0.1], label="CMSA/CM-SSM only"),
               Patch(facecolor=[0.55, 0.3, 0.75], label="GEODATA only"),
               Patch(facecolor="white", edgecolor="0.7", label="neither")]
    axes[-1].legend(handles=handles, loc="lower right", fontsize=7,
                    framealpha=0.9)
    fig.suptitle("R4-03 — South China Sea region: largest disagreement "
                 "clusters (100 m, EPSG:3410)", fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    for ext_f in ["pdf", "png"]:
        fig.savefig(os.path.join(FIGURES, f"fig_r4_south_china_zoom.{ext_f}"),
                    dpi=300 if ext_f == "png" else None)
    plt.close(fig)
    log("saved figures/fig_r4_south_china_zoom.pdf/.png")

    # region overview: full South extent
    fig, ax = plt.subplots(figsize=(8.5, 6))
    rgb = agree_rgb(S["CMSA"] | S["CMSSM"] | np.zeros_like(S["GEODATA"]),
                    S["GEODATA"] | S["CMSSM"] | np.zeros_like(S["CMSA"]))
    # clearer: show three one-vs-rest? Use CMSA+CMSSM union vs GEODATA union
    U_vec = S["CMSA"] | S["CMSSM"]
    U_geo = S["GEODATA"]
    rgb = agree_rgb(U_vec, U_geo)
    ys2, xs2 = np.nonzero(S_union)
    ext = [db[0] / 1000 + x0 * RES_M / 1000,
           db[0] / 1000 + x1 * RES_M / 1000,
           db[3] / 1000 - y1 * RES_M / 1000,
           db[3] / 1000 - y0 * RES_M / 1000]
    ax.imshow(rgb, origin="upper", extent=ext, interpolation="nearest",
              vmin=0, vmax=1)
    ax.set_aspect("equal")
    ax.set_xlabel("x (km)")
    ax.set_ylabel("y (km)")
    handles = [Patch(facecolor=[0.05, 0.55, 0.25], label="CMSA+CM-SSM and GEODATA"),
               Patch(facecolor=[0.9, 0.5, 0.1], label="CMSA+CM-SSM only"),
               Patch(facecolor=[0.55, 0.3, 0.75], label="GEODATA only")]
    ax.legend(handles=handles, loc="lower left", fontsize=8)
    ax.set_title("R4-03 — South China Sea region overview: (CMSA ∪ CM-SSM) "
                 "vs GEODATA, 100 m", fontsize=10)
    fig.tight_layout()
    for ext_f in ["pdf", "png"]:
        fig.savefig(os.path.join(FIGURES,
                    f"fig_r4_south_china_overview.{ext_f}"),
                    dpi=300 if ext_f == "png" else None)
    plt.close(fig)
    log("saved figures/fig_r4_south_china_overview.pdf/.png")

    log(f"done in {time.time()-_T0:.1f}s")

if __name__ == "__main__":
    main()
