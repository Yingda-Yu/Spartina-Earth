#!/usr/bin/env python3
"""
R4-06 — Figure 03 upgrade: national agreement panels with legible regional
context + full-resolution coastal enlargements.

Problems with the R3 fig03 (identified in the R4 figure review):
  1. National extent shows a sparse coastal fringe of scattered dots; the
     gray "no data" background dominates the panel.
  2. No geographic context (no region boundaries, no scale).
  3. No zoom: patch-level disagreement structure is invisible.

Design of this replacement (cached 100 m EPSG:3410 grids, consistent with
all published IoU numbers):
  Row 1 (a-c): national panels, one per product pair. Background: white
     with light-grey sea-region boundary outlines (Natural Earth marine
     groups). Agreement classes rendered from 1.5-km block-max downsampled
     masks so thin coastal fringes remain visible. Red rectangles mark the
     enlargement windows of row 2.
  Row 2 (d-f): full-resolution 100 m enlargements of the densest mapped
     coastal window (Yangtze estuary / Jiangsu coast, selected
     data-drivenly as the window with the most positive-union pixels), one
     panel per pair, same pair order as row 1, km axes + scale bars.

Outputs
  figures/fig03_agreement_map.pdf  (vector, rasterized dots)
  figures/fig03_agreement_map.png  (300 dpi preview)
"""
import os
os.environ.setdefault("PROJ_LIB",
    "/data/yingda/software/miniconda3/envs/spartina-earth/share/proj")
os.environ.setdefault("MPLCONFIGDIR", "/data/yingda/Spartina-Earth/work/tmp_mpl")
import numpy as np
from scipy import ndimage

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch, Rectangle

ROOT = "/data/yingda/Spartina-Earth"
CACHE = os.path.join(ROOT, "work", "cache", "paper1_100m")
FIGURES = os.path.join(ROOT, "papers", "paper1_map_reliability", "figures")

RES_M = 100
REGIONS = ["Bohai_Yellow", "East_China", "South_China"]
REGION_LABELS = {"Bohai_Yellow": "Bohai/Yellow Sea", "East_China": "East China Sea",
                 "South_China": "South China Sea"}
PAIRS = [("CMSA vs. CM-SSM", "CMSA", "CMSSM"),
         ("CMSA vs. GEODATA", "CMSA", "GEODATA"),
         ("CM-SSM vs. GEODATA", "CMSSM", "GEODATA")]
DS = 15                     # 100 m -> 1.5 km block-max for national panels
                            # (1478x1006 blocks ~= display resolution at
                            #  300 dpi, so the coastal fringe survives)
ZOOM_HALF_KM = 35           # half-width of enlargement windows
COL_BOTH = "#1a7a3c"        # both products
COL_A = "#1f77b4"           # only first product (blue family)
COL_B = "#d95f02"           # only second product (orange family)
BG = "#f7f7f7"

d = np.load(os.path.join(CACHE, "products_100m_epsg3410.npz"))
arr = {"CMSA": d["cmsa"].astype(bool), "CMSSM": d["cmssm"].astype(bool),
       "GEODATA": d["geo"].astype(bool)}
H, W = int(d["H"]), int(d["W"])
db = [float(v) for v in d["db"]]
m = np.load(os.path.join(CACHE, "marine_masks_100m.npz"))
direct = {g: m[f"{g}__mask"].astype(bool) for g in REGIONS}

union_pos = arr["CMSA"] | arr["CMSSM"] | arr["GEODATA"]
print(f"grid {W}x{H}, union px {int(union_pos.sum()):,}")

# ---------------- pick densest zoom window (60 km boxes) --------------
hp = ZOOM_HALF_KM * 1000 // RES_M
best = None
ys, xs = np.nonzero(union_pos)
step = max(hp // 2, 50)
for cy in range(hp, H - hp, step):
    in_y = (ys >= cy - hp) & (ys < cy + hp)
    if not in_y.any():
        continue
    xs_y = xs[in_y]
    for cx in range(hp, W - hp, step):
        n = int(((xs_y >= cx - hp) & (xs_y < cx + hp)).sum())
        if best is None or n > best[0]:
            best = (n, cy, cx)
n_zoom, cy, cx = best
print(f"densest window: {n_zoom:,} union px around row {cy}, col {cx}")
r0, r1 = cy - hp, cy + hp
c0, c1 = cx - hp, cx + hp

# km coordinates
x0km = db[0] / 1000 + c0 * RES_M / 1000
x1km = db[0] / 1000 + c1 * RES_M / 1000
y0km = db[3] / 1000 - r1 * RES_M / 1000
y1km = db[3] / 1000 - r0 * RES_M / 1000

# region boundary pixel lists (downsampled) for context
bounds_px = []
for g in REGIONS:
    sub = direct[g][::4, ::4]
    edge = sub & ~ndimage.binary_erosion(sub, structure=np.ones((3, 3), bool))
    gy, gx = np.nonzero(edge)
    bounds_px.append((db[0] / 1000 + gx * 4 * RES_M / 1000,
                      db[3] / 1000 - gy * 4 * RES_M / 1000))

def ds_block(a, f=DS):
    h2, w2 = (a.shape[0] // f) * f, (a.shape[1] // f) * f
    b = a[:h2, :w2].reshape(h2 // f, f, w2 // f, f)
    return b.any(axis=(1, 3))

def render_class(mask_a, mask_b):
    """RGB array: BG / both / only A / only B."""
    rgb = np.full(mask_a.shape + (3,), np.array(
        matplotlib.colors.to_rgb(BG)), dtype=float)
    rgb[mask_a & mask_b] = matplotlib.colors.to_rgb(COL_BOTH)
    rgb[mask_a & ~mask_b] = matplotlib.colors.to_rgb(COL_A)
    rgb[~mask_a & mask_b] = matplotlib.colors.to_rgb(COL_B)
    return rgb

ext_nat = [db[0] / 1000, db[0] / 1000 + W * RES_M / 1000,
           db[3] / 1000 - H * RES_M / 1000, db[3] / 1000]
ext_zoom = [x0km, x1km, y0km, y1km]

fig = plt.figure(figsize=(15, 10.5))
gs = fig.add_gridspec(2, 3, height_ratios=[1, 1],
                      left=0.05, right=0.98, top=0.93, bottom=0.07,
                      hspace=0.16, wspace=0.06)

panel_tags = ["(a)", "(b)", "(c)", "(d)", "(e)", "(f)"]
for i, (label, pa, pb) in enumerate(PAIRS):
    A, B = arr[pa], arr[pb]
    ax = fig.add_subplot(gs[0, i])
    ax.set_facecolor(BG)
    # class-coloured block-max scatter: marker size is display-controlled,
    # so the thin coastal fringe stays visible at national scale (imshow
    # would render 1.5 km blocks at ~1 display px and alias them away)
    Ablk, Bblk = ds_block(A), ds_block(B)

    def blk_km(mask):
        yy, xx = np.nonzero(mask)
        return (db[0] / 1000 + (xx + 0.5) * DS * RES_M / 1000,
                db[3] / 1000 - (yy + 0.5) * DS * RES_M / 1000)

    for mask, col in [(Ablk & Bblk, COL_BOTH), (Ablk & ~Bblk, COL_A),
                      (~Ablk & Bblk, COL_B)]:
        bx, by = blk_km(mask)
        if len(bx):
            ax.scatter(bx, by, s=2.5, c=col, linewidths=0, rasterized=True,
                       zorder=3)
    for (bx, by) in bounds_px:
        ax.scatter(bx, by, s=0.05, c="#38627a", linewidths=0, rasterized=True)
    for g in REGIONS:
        gy, gx = np.nonzero(direct[g][::4, ::4])
        ax.text(db[0] / 1000 + gx.mean() * 4 * RES_M / 1000,
                db[3] / 1000 - gy.mean() * 4 * RES_M / 1000,
                REGION_LABELS[g], fontsize=8.5, style="italic", color="0.15",
                ha="center")
    ax.add_patch(Rectangle((x0km, y0km), x1km - x0km, y1km - y0km,
                           fill=False, edgecolor="#d7191c", lw=1.3,
                           zorder=5))
    ax.set_title(f"{panel_tags[i]} {label} — national", fontsize=10)
    ax.set_aspect("equal")
    ax.set_xlim(ext_nat[0], ext_nat[1])
    ax.set_ylim(ext_nat[2], ext_nat[3])
    ax.set_xticks([]); ax.set_yticks([])

    ax2 = fig.add_subplot(gs[1, i])
    rgb2 = render_class(A[r0:r1, c0:c1], B[r0:r1, c0:c1])
    ax2.imshow(rgb2, origin="upper", extent=ext_zoom, interpolation="nearest")
    ax2.set_title(f"{panel_tags[i + 3]} {label} — enlargement", fontsize=10)
    ax2.set_aspect("equal")
    ax2.set_xlim(ext_zoom[0], ext_zoom[1])
    ax2.set_ylim(ext_zoom[2], ext_zoom[3])
    ax2.set_xlabel("EPSG:3410 x (km)", fontsize=8)
    if i == 0:
        ax2.set_ylabel("EPSG:3410 y (km)", fontsize=8)
    ax2.tick_params(labelsize=7)
    # scale bar (10 km)
    sb_x = ext_zoom[0] + (ext_zoom[1] - ext_zoom[0]) * 0.06
    sb_y = ext_zoom[2] + (ext_zoom[3] - ext_zoom[2]) * 0.05
    ax2.plot([sb_x, sb_x + 10], [sb_y, sb_y], color="k", lw=2,
             solid_capstyle="butt", zorder=6)
    ax2.text(sb_x + 5, sb_y + 1.2, "10 km", fontsize=7, ha="center", zorder=6)

legend_elements = [
    Patch(facecolor=COL_BOTH, label="both products (agreement)"),
    Patch(facecolor=COL_A, label=f"only first product (CMSA or CM-SSM)"),
    Patch(facecolor=COL_B, label="only second product (CM-SSM or GEODATA)"),
    Patch(facecolor=BG, edgecolor="0.65", label="neither product"),
]
fig.legend(handles=legend_elements, loc="lower center", ncol=4, fontsize=9,
           frameon=True, edgecolor="gray", fancybox=False,
           bbox_to_anchor=(0.515, 0.005))
fig.suptitle("2020 S. alterniflora spatial agreement at 100 m (EPSG:3410)",
             fontsize=12)
pdf_path = os.path.join(FIGURES, "fig03_agreement_map.pdf")
png_path = os.path.join(FIGURES, "fig03_agreement_map.png")
fig.savefig(pdf_path)
fig.savefig(png_path, dpi=300)
plt.close(fig)
print(f"saved {pdf_path}")
print(f"saved {png_path}")
