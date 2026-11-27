#!/usr/bin/env python3
"""
R6 — Regional attribution figure redesign (successor of
r4_region_assignment_figure.py): same audited computation, unified
cartography.

  (a) National map on the R6 basemap: direct marine-polygon membership pixels
      (muted teal) vs nearest-assigned residual pixels binned by distance
      (warm sequential ramp to hot red); region outlines + labels;
      graticule, scale bar, north arrow, locator inset.
  (b) Histogram of nearest-assignment distances with median and 99th
      percentile markers (matches results/r4_attribution_meta.json).

Outputs: figures/fig_r4_region_assignment.{pdf,png}
"""
import os
os.environ.setdefault("MPLCONFIGDIR", "/data/yingda/Spartina-Earth/work/tmp_mpl")
import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

import r6_cartography as cart

FIGURES = os.path.join(cart.ROOT, "papers/paper1_map_reliability/figures")
RES_M = 100
REGIONS = ["Bohai_Yellow", "East_China", "South_China"]

arrs, H, W, db = cart.load_products()
direct = cart.load_region_masks()

union_pos = arrs["cmsa"] | arrs["cmssm"] | arrs["geo"]
any_direct = np.logical_or.reduce([direct[g] for g in REGIONS])
resid = union_pos & ~any_direct
n_resid = int(resid.sum())
ys, xs = np.nonzero(resid)
query = np.column_stack([ys, xs]).astype(np.float32)
best_d = np.full(n_resid, np.inf, dtype=np.float32)
for g in REGIONS:
    edge = direct[g] & ~ndimage.binary_erosion(
        direct[g], structure=np.ones((3, 3), bool), border_value=0)
    ey, ex = np.nonzero(edge)
    tree = cKDTree(np.column_stack([ey, ex]).astype(np.float32))
    dd, _ = tree.query(query, k=1, workers=-1)
    upd = dd < best_d
    best_d[upd] = dd[upd]
dist_km = best_d * RES_M / 1000.0
print("resid px:", n_resid, "median", np.median(dist_km).round(2),
      "p99", np.percentile(dist_km, 99).round(2))

px_x = db[0] + (xs + .5) * RES_M / 1000.0
px_y = db[3] - (ys + .5) * RES_M / 1000.0
dy, dx = np.nonzero(union_pos & any_direct)
dx_x = db[0] + (dx + .5) * RES_M / 1000.0
dx_y = db[3] - (dy + .5) * RES_M / 1000.0

pad = 60
ext = (min(dx_x.min(), px_x.min()) - pad, max(dx_x.max(), px_x.max()) + pad,
       min(dx_y.min(), px_y.min()) - pad, max(dx_y.max(), px_y.max()) + pad)

fig = plt.figure(figsize=(13.4, 5.6))
gs = fig.add_gridspec(1, 2, width_ratios=[1.75, 1],
                      left=0.035, right=0.865, top=0.94, bottom=0.14,
                      wspace=0.06)
ax = fig.add_subplot(gs[0, 0])
axh = fig.add_subplot(gs[0, 1])

# ---------------- panel (a): map --------------------------------------------
cart.add_basemap(ax, ext, provinces=False, intl=False)
cart.add_graticule(ax, ext, step_deg=5, label_x=True, label_y=True)

# direct pixels: 1 km block-max for render weight
blk = 10
h2, w2 = (H // blk) * blk, (W // blk) * blk
dblk = (union_pos & any_direct)[:h2, :w2].reshape(
    h2 // blk, blk, w2 // blk, blk).any(axis=(1, 3))
gy, gx = np.nonzero(dblk)
ax.scatter(db[0] + (gx + 0.5) * blk * RES_M / 1000.0,
           db[3] - (gy + 0.5) * blk * RES_M / 1000.0,
           s=1.6, c=cart.PAL["direct"], linewidths=0, rasterized=True,
           zorder=5)

cand = [(0, 1, "0–1"), (1, 5, "1–5"), (5, 10, "5–10"),
        (10, 20, "10–20"), (20, 50, "20–50"), (50, np.inf, ">50")]
kept = [(lo, hi, lab) for lo, hi, lab in cand
        if ((dist_km >= lo) & (dist_km < hi)).any()]
labels = [lab for _, _, lab in kept]
bounds = [lo for lo, _, _ in kept] + [kept[-1][1]]
cmap = ListedColormap(plt.cm.YlOrRd(np.linspace(0.25, 1.0, len(labels))))
col_idx = np.searchsorted(bounds[1:-1], dist_km, side="left")
sc = ax.scatter(px_x, px_y, s=2.0, c=col_idx, cmap=cmap,
                norm=BoundaryNorm(np.arange(len(labels) + 1), len(labels)),
                linewidths=0, rasterized=True, zorder=6)
cbar = fig.colorbar(sc, ax=ax, ticks=np.arange(len(labels)) + 0.5,
                    shrink=0.72, pad=0.012)
cbar.ax.set_yticklabels(labels, fontsize=7.5)
cbar.set_label("nearest-assignment distance (km)", fontsize=8.5)
cbar.outline.set_linewidth(0.5)

# region outlines + labels
for g in REGIONS:
    sub = direct[g]
    edge = sub & ~ndimage.binary_erosion(sub,
                                         structure=np.ones((3, 3), bool))
    ey, ex = np.nonzero(edge[::3, ::3])
    ax.scatter(db[0] + ex[::1] * 3 * RES_M / 1000.0,
               db[3] - ey * 3 * RES_M / 1000.0,
               s=0.05, c="0.45", linewidths=0, rasterized=True, zorder=4)
    gy, gx = np.nonzero(sub[::6, ::6])
    ax.text(db[0] + gx.mean() * 6 * RES_M / 1000.0,
            db[3] - gy.mean() * 6 * RES_M / 1000.0,
            cart.REGION_LABEL[g], fontsize=7.5, style="italic", color="0.25",
            ha="center", zorder=7)

cart.add_scalebar(ax, 250, x_frac=0.05, y_frac=0.05)
cart.add_north_arrow(ax, x_frac=0.955, y_frac=0.92, size=7)
cart.add_locator_inset(ax, ext, width="22%", height="20%",
                       loc="upper left", borderpad=0.4)
ax.set_title("(a) Attribution of mapped positives (100 m)", fontsize=9.5)
n_union = int(union_pos.sum())
handles = [Line2D([0], [0], marker="o", color="w",
                  markerfacecolor=cart.PAL["direct"], markersize=5,
                  label="direct marine-polygon membership "
                        f"({n_union - n_resid:,} px)"),
           Line2D([0], [0], marker="o", color="w", markerfacecolor="#FC8D59",
                  markersize=5,
                  label=f"nearest-assigned residuals ({n_resid:,} px = "
                        f"{n_resid / n_union * 100:.1f} % of positive union)")]
ax.legend(handles=handles, loc="lower left", fontsize=7.5, framealpha=0.92,
          edgecolor="#888888")

# ---------------- panel (b): distance histogram -----------------------------
axh.hist(np.clip(dist_km, 0, 80), bins=np.arange(0, 81, 2.5),
         color=cart.PAL["only_b"], alpha=0.85, edgecolor="#8c6d1f",
         linewidth=0.4)
med = float(np.median(dist_km))
p99 = float(np.percentile(dist_km, 99))
axh.axvline(med, color=cart.PAL["hot"], lw=1.2, linestyle="--")
axh.axvline(p99, color="#7B1FA2", lw=1.2, linestyle=":")
axh.text(med + 1, axh.get_ylim()[1] * 0.95, f"median {med:.1f} km",
         color=cart.PAL["hot"], fontsize=8, va="top")
axh.text(p99 + 1, axh.get_ylim()[1] * 0.85, f"p99 {p99:.1f} km",
         color="#7B1FA2", fontsize=8, va="top")
axh.set_xlim(0, 80)
axh.set_xlabel("nearest-assignment distance (km)", fontsize=8.5)
axh.set_ylabel("residual pixels", fontsize=8.5)
axh.tick_params(labelsize=7.5)
axh.set_title("(b) Distance to nearest sea polygon", fontsize=9.5)
for s in axh.spines.values():
    s.set_linewidth(0.5)

cart.attribution_note(fig, cart.NE_NOTE + " Distances computed on the "
                      "100 m grid (scipy cKDTree).", y=0.022)

out_pdf = os.path.join(FIGURES, "fig_r4_region_assignment.pdf")
out_png = os.path.join(FIGURES, "fig_r4_region_assignment.png")
fig.savefig(out_pdf)
fig.savefig(out_png, dpi=200)
plt.close(fig)
print("saved:", out_pdf)
