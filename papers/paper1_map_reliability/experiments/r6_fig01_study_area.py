#!/usr/bin/env python3
"""
R6 — Figure 1: Study area and source products (new cartographic figure).

Panels:
  (a) study area: land/sea base, province boundaries, graticule, the three
      sea-region groups used throughout the analysis (subtle tints + labels),
      scale bar, north arrow, locator inset; a local zoom shows the three
      products' positives co-located (same teal, partial alpha).
  (b)-(d) 2020 distribution of CMSA (10 m), CM-SSM (sub-meter) and
      GEODATA (30 m) on the identical base and extent.

Output: figures/fig01_study_area.{pdf,png}
Data: cached 100 m EPSG:3410 grids (identical to analysis grids) + Natural
Earth 1:10m base (public domain).
"""
import os
os.environ.setdefault("MPLCONFIGDIR", "/data/yingda/Spartina-Earth/work/tmp_mpl")
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from matplotlib.patches import Patch, Rectangle

import r6_cartography as cart

FIGURES = os.path.join(cart.ROOT, "papers/paper1_map_reliability/figures")
REGIONS = ("Bohai_Yellow", "East_China", "South_China")

arrs, H, W, db = cart.load_products()
regions = cart.load_region_masks()
union = arrs["cmsa"] | arrs["cmssm"] | arrs["geo"]

# ---- extent: positives bounds + 120 km margin, snapped to 25 km ----------
ys, xs = np.nonzero(union[::10, ::10])
px_x = db[0] + (xs * 10 + 5) * 0.1
px_y = db[3] - (ys * 10 + 5) * 0.1
M = 120.0
snap = 25.0
x0 = np.floor((px_x.min() - M) / snap) * snap
x1 = np.ceil((px_x.max() + M) / snap) * snap
y0 = np.floor((px_y.min() - M) / snap) * snap
y1 = np.ceil((px_y.max() + M) / snap) * snap
EXT = (float(x0), float(x1), float(y0), float(y1))
print("extent km:", EXT)

ZOOM = (11550, 11790, 3770, 3890)   # Yangtze estuary / Hangzhou Bay

fig = plt.figure(figsize=(9.6, 11.4))
gs = GridSpec(2, 2, figure=fig, hspace=0.16, wspace=0.13,
              left=0.055, right=0.975, top=0.965, bottom=0.075)
axes = [fig.add_subplot(gs[i, j]) for i in range(2) for j in range(2)]

# ---------------- panel (a): study area + regions --------------------------
axA = axes[0]
cart.add_basemap(axA, EXT)
cart.add_graticule(axA, EXT, step_deg=5)

tints = {"Bohai_Yellow": "region1", "East_China": "region2",
         "South_China": "region3"}
for g in REGIONS:
    cart.overlay_mask(axA, regions[g], db, cart.PAL[tints[g]], alpha=0.55,
                      zorder=3.5, block=10, extent_km=EXT)
    gy, gx = np.nonzero(regions[g][::6, ::6])
    cx = db[0] + (gx.mean() * 6 + 3) * 0.1
    cy = db[3] - (gy.mean() * 6 + 3) * 0.1
    axA.text(cx, cy, cart.REGION_LABEL[g], fontsize=7.5, style="italic",
             ha="center", va="center", color=cart.PAL["text"], zorder=7)

# zoom box + local inset: all three products, same teal with alpha
axA.add_patch(Rectangle((ZOOM[0], ZOOM[2]), ZOOM[1] - ZOOM[0],
                        ZOOM[3] - ZOOM[2], fill=False,
                        edgecolor=cart.PAL["zoombox"], linewidth=1.0,
                        linestyle="-", zorder=8))
ins = axA.inset_axes([0.615, 0.028, 0.365, 0.30])
cart.add_basemap(ins, ZOOM, provinces=False, intl=False)
for k in ("cmsa", "cmssm", "geo"):
    cart.overlay_mask(ins, arrs[k], db, cart.PAL["spartina"], alpha=0.55,
                      zorder=4, extent_km=ZOOM)
ins.set_xticks([]); ins.set_yticks([])
for s in ins.spines.values():
    s.set_linewidth(0.9); s.set_color(cart.PAL["zoombox"])
# connector lines: zoom box corners -> inset top corners
ix0 = EXT[0] + 0.615 * (EXT[1] - EXT[0])
iy1 = EXT[2] + 0.328 * (EXT[3] - EXT[2])
axA.plot([ZOOM[0], ix0], [ZOOM[2], iy1], lw=0.6, color=cart.PAL["zoombox"],
         zorder=7.5, clip_on=True)
axA.plot([ZOOM[1], ZOOM[1]], [ZOOM[2], iy1], lw=0.6,
         color=cart.PAL["zoombox"], zorder=7.5, clip_on=True)
axA.text(0.5, 0.988, "(a) Study area and sea-region groups",
        transform=axA.transAxes, ha="center", va="top", fontsize=8.5)

# ---------------- panels (b)-(d): products --------------------------------
PROD = [
    ("cmsa", "(b) CMSA — 10 m vector, 2020"),
    ("cmssm", "(c) CM-SSM — sub-meter vector, 2020"),
    ("geo", "(d) GEODATA — 30 m raster, 2020"),
]
for ax, (key, title) in zip(axes[1:], PROD):
    cart.add_basemap(ax, EXT)
    cart.add_graticule(ax, EXT, step_deg=5)
    cart.overlay_mask(ax, arrs[key], db, cart.PAL["spartina"], alpha=0.95,
                      zorder=5, block=10, extent_km=EXT)
    ax.text(0.5, 0.988, title, transform=ax.transAxes, ha="center", va="top",
            fontsize=8.5)

# shared map furniture: scale bar + north arrow on every panel
for ax in axes:
    cart.add_scalebar(ax, 250)
    cart.add_north_arrow(ax, x_frac=0.955, y_frac=0.90, size=7)
    cart.clean_axes(ax)

# ---------------- legend + attribution ------------------------------------
legend_items = [
    Patch(facecolor=cart.PAL["land"], edgecolor=cart.PAL["coast"],
          linewidth=0.6, label="Land (Natural Earth)"),
    Patch(facecolor=cart.PAL["sea"], edgecolor="#999999", linewidth=0.4,
          label="Sea"),
    Patch(facecolor=cart.PAL["spartina"], label="S. alterniflora mapped presence (2020)"),
    Patch(facecolor=cart.PAL["region1"], label="Bohai / Yellow Sea group"),
    Patch(facecolor=cart.PAL["region2"], label="East China Sea group"),
    Patch(facecolor=cart.PAL["region3"], label="South China Sea group"),
    Patch(facecolor="none", edgecolor=cart.PAL["zoombox"], linewidth=1.0,
          label="Zoom (a): three products co-located"),
]
fig.legend(handles=legend_items, loc="lower center", ncol=4, fontsize=7.2,
           frameon=True, edgecolor="#888888", fancybox=False,
           bbox_to_anchor=(0.5, 0.012), columnspacing=1.2, handlelength=1.6)
cart.attribution_note(fig, cart.NE_NOTE + " Product positives shown at "
                      "1 km block-maximum.", y=0.0)

out_pdf = os.path.join(FIGURES, "fig01_study_area.pdf")
out_png = os.path.join(FIGURES, "fig01_study_area.png")
fig.savefig(out_pdf)
fig.savefig(out_png, dpi=200)
plt.close(fig)
print("saved:", out_pdf)
