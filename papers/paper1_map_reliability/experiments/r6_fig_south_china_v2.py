#!/usr/bin/env python3
"""
R6 — South China spatial-mismatch case study (redesign of
fig_r4_south_china_zoom): three representative localities from the R4
cluster analysis (results/r4_south_china_clusters.csv, ranks 1), drawn on
the unified basemap with product-identity colours.

  (a) Pearl River estuary (113.42°E, 22.14°N): CMSA–GEODATA displacement
      window (largest GEODATA-only cluster vs CM-SSM, with CMSA positives
      nearby);
  (b) Beibu Gulf (110.16°E, 20.93°N): largest GEODATA-only cluster with no
      CMSA/CM-SSM positives within ±3 km;
  (c) Leizhou Bay (109.66°E, 21.58°N): three-way co-location with partial
      overlap — the displacement/offset case.

Colours encode product identity (explicit per-figure legend, distinct from
the pair-class colours of the agreement figure): CMSA blue, CM-SSM teal,
GEODATA orange; alpha blending reveals overlap.

Outputs: figures/fig_r4_south_china_zoom.{pdf,png}
"""
import os
os.environ.setdefault("MPLCONFIGDIR", "/data/yingda/Spartina-Earth/work/tmp_mpl")
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

import r6_cartography as cart

FIGURES = os.path.join(cart.ROOT, "papers/paper1_map_reliability/figures")
arrs, H, W, db = cart.load_products()

HALF = 25   # ±2.5 km (50 x 50 cells of 100 m)
WINDOWS = [
    ("(a) Pearl River estuary", 20649, 4510),
    ("(b) Beibu Gulf", 22096, 1370),
    ("(c) Leizhou Bay", 21317, 882),
]
PROD = [("cmsa", "CMSA", cart.PAL["only_a"], 0.80),
        ("cmssm", "CM-SSM", cart.PAL["spartina"], 0.80),
        ("geo", "GEODATA", cart.PAL["only_b"], 0.80)]

fig, axes = plt.subplots(1, 3, figsize=(12.0, 4.55))
fig.subplots_adjust(left=0.03, right=0.985, top=0.90, bottom=0.185,
                    wspace=0.10)

for ax, (title, row, col) in zip(axes, WINDOWS):
    r0, r1 = row - HALF, row + HALF
    c0, c1 = col - HALF, col + HALF
    ext = (db[0] + c0 * 0.1, db[0] + c1 * 0.1,
           db[3] - r1 * 0.1, db[3] - r0 * 0.1)
    cart.add_basemap(ax, ext, provinces=False, intl=False)

    sub_db = (db[0] + c0 * 0.1, db[3] - r1 * 0.1,
              db[0] + c1 * 0.1, db[3] - r0 * 0.1)
    for key, name, colr, alpha in PROD:
        cart.overlay_mask(ax, arrs[key], db, colr, alpha=alpha, zorder=5,
                          extent_km=ext)

    lon0, lat0 = cart._Ti.transform(ext[0] * 1000, ext[2] * 1000)
    lon1, lat1 = cart._Ti.transform(ext[1] * 1000, ext[3] * 1000)
    ax.set_xlabel(f"{lon0:.2f}–{lon1:.2f}°E,  {lat0:.2f}–{lat1:.2f}°N",
                  fontsize=7.2)
    ax.set_title(title, fontsize=9.5, pad=4)
    cart.add_scalebar(ax, 1, x_frac=0.07, y_frac=0.08, fontsize=7)
    cart.add_north_arrow(ax, x_frac=0.94, y_frac=0.90, size=7)
    cart.clean_axes(ax)
    ax.tick_params(labelbottom=False, labelleft=False,
                   bottom=False, left=False)

legend_items = [
    Patch(facecolor=cart.PAL["only_a"], alpha=0.85, label="CMSA (10 m)"),
    Patch(facecolor=cart.PAL["spartina"], alpha=0.85, label="CM-SSM (sub-meter)"),
    Patch(facecolor=cart.PAL["only_b"], alpha=0.85, label="GEODATA (30 m)"),
    Patch(facecolor=cart.PAL["land"], edgecolor=cart.PAL["coast"],
          linewidth=0.6, label="Land (Natural Earth)"),
    Patch(facecolor=cart.PAL["sea"], edgecolor="#999999", linewidth=0.4,
          label="Sea"),
]
fig.legend(handles=legend_items, loc="lower center", ncol=5, fontsize=8,
           frameon=True, edgecolor="#888888", fancybox=False,
           bbox_to_anchor=(0.5, 0.018), columnspacing=1.4, handlelength=1.6)
cart.attribution_note(fig, cart.NE_NOTE + " Native 100 m product rasters, "
                      "2020. Panel colours denote product identity; "
                      "blended tones mark spatial overlap.", y=0.0)

out_pdf = os.path.join(FIGURES, "fig_r4_south_china_zoom.pdf")
out_png = os.path.join(FIGURES, "fig_r4_south_china_zoom.png")
fig.savefig(out_pdf)
fig.savefig(out_png, dpi=200)
plt.close(fig)
print("saved:", out_pdf)
