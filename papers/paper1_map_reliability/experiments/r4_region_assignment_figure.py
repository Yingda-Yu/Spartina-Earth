#!/usr/bin/env python3
"""
R4-01 (figure regeneration) — redraw figures/fig_r4_region_assignment.{pdf,png}
from the cached products + marine masks without rerunning the policy loops.
Assignment state (residual pixels, nearest group, distance) is recomputed
(~3 min); the figure logic mirrors r4_region_attribution.py.
"""
import os, subprocess
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

ROOT = "/data/yingda/Spartina-Earth"
FIGURES = os.path.join(ROOT, "papers", "paper1_map_reliability", "figures")
CACHE = os.path.join(ROOT, "work", "cache", "paper1_100m")
RES_M = 100
REGIONS = ["Bohai_Yellow", "East_China", "South_China"]

d = np.load(os.path.join(CACHE, "products_100m_epsg3410.npz"))
arr = {"CMSA": d["cmsa"].astype(bool), "CMSSM": d["cmssm"].astype(bool),
       "GEODATA": d["geo"].astype(bool)}
H, W = int(d["H"]), int(d["W"])
db = [float(v) for v in d["db"]]
m = np.load(os.path.join(CACHE, "marine_masks_100m.npz"))
direct = {g: m[f"{g}__mask"].astype(bool) for g in REGIONS}

union_pos = arr["CMSA"] | arr["CMSSM"] | arr["GEODATA"]
any_direct = np.logical_or.reduce([direct[g] for g in REGIONS])
resid = union_pos & ~any_direct
n_resid = int(resid.sum())
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
dist_km = best_d * RES_M / 1000.0

px_x = db[0] / 1000 + (xs + .5) * RES_M / 1000
px_y = db[3] / 1000 - (ys + .5) * RES_M / 1000
dy, dx = np.nonzero(union_pos & any_direct)
dx_x = db[0] / 1000 + (dx + .5) * RES_M / 1000
dx_y = db[3] / 1000 - (dy + .5) * RES_M / 1000

fig, ax = plt.subplots(figsize=(11, 6.2))
for g in REGIONS:
    sub = direct[g][::4, ::4]
    edge = sub & ~ndimage.binary_erosion(sub, structure=np.ones((3, 3), bool))
    gy, gx = np.nonzero(edge)
    ax.scatter(db[0] / 1000 + gx * 4 * RES_M / 1000,
               db[3] / 1000 - gy * 4 * RES_M / 1000,
               s=0.05, c="0.55", linewidths=0, rasterized=True, zorder=1)
for g in REGIONS:
    gy, gx = np.nonzero(direct[g][::4, ::4])
    if len(gy) == 0:
        continue
    ax.text(db[0] / 1000 + gx.mean() * 4 * RES_M / 1000,
            db[3] / 1000 - gy.mean() * 4 * RES_M / 1000,
            g.replace("_", " "), fontsize=9, style="italic",
            color="0.25", ha="center", zorder=4)
ax.scatter(dx_x, dx_y, s=0.6, c="#7aa6c2", alpha=0.8, linewidths=0,
           rasterized=True, zorder=2, label="direct marine-polygon pixels")
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
                  markersize=5, label="nearest-assigned (color = distance)")]
ax.legend(handles=handles, loc="lower left", fontsize=8, framealpha=0.9)
ax.set_xlabel("EPSG:3410 x (km)")
ax.set_ylabel("EPSG:3410 y (km)")
n_union = int(union_pos.sum())
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
print("saved figures/fig_r4_region_assignment.pdf/.png")
