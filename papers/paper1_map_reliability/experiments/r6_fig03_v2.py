#!/usr/bin/env python3
"""
R6 — Figure 2/3 redesign: national product agreement with full cartographic
context (successor of r4_fig03_upgrade.py).

  Row 1 (a-c): national panels per product pair on the unified basemap
     (land/sea fill, coastlines, province boundaries, 5° graticule, scale
     bar, north arrow); agreement classes as 1.5-km block-maximum scatter
     so the thin coastal fringe survives; red zoom box.
  Row 2 (d-f): full-resolution 100 m enlargements of the densest mapped
     window (Yangtze estuary / Jiangsu coast, data-driven) on the same
     basemap with graticule, scale bar and north arrow.

Colors follow the R6 design system: both = teal-green, only-A = blue,
only-B = orange (Okabe-Ito, colorblind- and grayscale-safe).

Outputs: figures/fig03_agreement_map.{pdf,png}
"""
import os
os.environ.setdefault("MPLCONFIGDIR", "/data/yingda/Spartina-Earth/work/tmp_mpl")
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch, Rectangle

import r6_cartography as cart

FIGURES = os.path.join(cart.ROOT, "papers/paper1_map_reliability/figures")

arrs, H, W, db = cart.load_products()
ARR = {"CMSA": arrs["cmsa"], "CMSSM": arrs["cmssm"], "GEODATA": arrs["geo"]}
PAIRS = [("CMSA vs. CM-SSM", "CMSA", "CMSSM"),
         ("CMSA vs. GEODATA", "CMSA", "GEODATA"),
         ("CM-SSM vs. GEODATA", "CMSSM", "GEODATA")]
REGIONS = ("Bohai_Yellow", "East_China", "South_China")
regions = cart.load_region_masks()

DS = 15                          # 1.5 km block-max for national panels
ZOOM_HALF_KM = 35

# ---- national extent: product domain --------------------------------------
ext_nat = (db[0], db[2], db[3] - H * 0.1, db[3])

# ---- densest zoom window (data-driven, same rule as R4) -------------------
union = ARR["CMSA"] | ARR["CMSSM"] | ARR["GEODATA"]
hp = ZOOM_HALF_KM * 10           # 100 m cells per 35 km
ys, xs = np.nonzero(union[::4, ::4])
ys, xs = ys * 4, xs * 4
best = None
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
ext_zoom = (db[0] + c0 * 0.1, db[0] + c1 * 0.1,
            db[3] - r1 * 0.1, db[3] - r0 * 0.1)

# ---- cropped full-res pair classes for the zoom row -----------------------
def zoom_slices(a):
    return a[r0:r1, c0:c1]

C_BOTH, C_A, C_B = cart.PAL["both"], cart.PAL["only_a"], cart.PAL["only_b"]

def ds_block(a, f=DS):
    h2, w2 = (a.shape[0] // f) * f, (a.shape[1] // f) * f
    b = a[:h2, :w2].reshape(h2 // f, f, w2 // f, f)
    return b.any(axis=(1, 3))

def class_overlay(ax, A, B, sub_db, z0=5):
    """3-colour agreement overlay for already-cropped boolean arrays."""
    from matplotlib.colors import to_rgba
    for mask, col in [(A & B, C_BOTH), (A & ~B, C_A), (~A & B, C_B)]:
        if not mask.any():
            continue
        r, g, b, a = to_rgba(col, 1.0)
        rgba = np.zeros((*mask.shape, 4), dtype=np.uint8)
        rgba[..., 0][mask] = int(r * 255)
        rgba[..., 1][mask] = int(g * 255)
        rgba[..., 2][mask] = int(b * 255)
        rgba[..., 3][mask] = 255
        im = ax.imshow(rgba, origin="upper", interpolation="nearest",
                       extent=cart.grid_extent_km(sub_db), zorder=z0)
        im.set_rasterized(True)

fig = plt.figure(figsize=(15.0, 10.6))
gs = fig.add_gridspec(2, 3, height_ratios=[1, 1.12],
                      left=0.045, right=0.985, top=0.97, bottom=0.075,
                      hspace=0.14, wspace=0.075)

for i, (label, pa, pb) in enumerate(PAIRS):
    A, B = ARR[pa], ARR[pb]

    # ---------------- national panel --------------------------------------
    ax = fig.add_subplot(gs[0, i])
    cart.add_basemap(ax, ext_nat, intl=False)
    cart.add_graticule(ax, ext_nat, step_deg=5,
                       label_x=False, label_y=(i == 0))
    Ab, Bb = ds_block(A), ds_block(B)
    for mask, col in [(Ab & Bb, C_BOTH), (Ab & ~Bb, C_A), (~Ab & Bb, C_B)]:
        yy, xx = np.nonzero(mask)
        if len(yy):
            ax.scatter(db[0] + (xx + 0.5) * DS * 0.1,
                       db[3] - (yy + 0.5) * DS * 0.1,
                       s=2.0, c=col, linewidths=0, rasterized=True, zorder=5)
    ax.add_patch(Rectangle((ext_zoom[0], ext_zoom[2]),
                           ext_zoom[1] - ext_zoom[0], ext_zoom[3] - ext_zoom[2],
                           fill=False, edgecolor=cart.PAL["zoombox"], lw=1.0,
                           zorder=7))
    ax.set_title(f"({'abc'[i]}) {label}", fontsize=9.5, pad=3)
    cart.add_scalebar(ax, 250, x_frac=0.05, y_frac=0.05)
    cart.add_north_arrow(ax, x_frac=0.95, y_frac=0.92, size=7)
    if i == 0:
        cart.add_locator_inset(ax, ext_nat, width="24%", height="22%",
                               loc="upper left", borderpad=0.4)

    # ---------------- enlargement panel -----------------------------------
    ax2 = fig.add_subplot(gs[1, i])
    cart.add_basemap(ax2, ext_zoom, intl=False)
    cart.add_graticule(ax2, ext_zoom, step_deg=1,
                       label_x=True, label_y=(i == 0))
    class_overlay(ax2, zoom_slices(A), zoom_slices(B),
                  (db[0] + c0 * 0.1, db[3] - r1 * 0.1,
                   db[0] + c1 * 0.1, db[3] - r0 * 0.1))
    ax2.set_title(f"({'def'[i]}) {label}", fontsize=9.5, pad=3)
    cart.add_scalebar(ax2, 10, x_frac=0.06, y_frac=0.06)
    cart.add_north_arrow(ax2, x_frac=0.95, y_frac=0.93, size=7)

legend_elements = [
    Patch(facecolor=C_BOTH, label="both products (agreement)"),
    Patch(facecolor=C_A, label="only first product (CMSA or CM-SSM)"),
    Patch(facecolor=C_B, label="only second product (CM-SSM or GEODATA)"),
    Patch(facecolor=cart.PAL["land"], edgecolor=cart.PAL["coast"],
          linewidth=0.6, label="Land (Natural Earth)"),
    Patch(facecolor=cart.PAL["sea"], edgecolor="#999999", linewidth=0.4,
          label="Sea"),
    Patch(facecolor="none", edgecolor=cart.PAL["zoombox"], linewidth=1.0,
          label="enlargement window (d)-(f)"),
]
fig.legend(handles=legend_elements, loc="lower center", ncol=3, fontsize=8.2,
           frameon=True, edgecolor="#888888", fancybox=False,
           bbox_to_anchor=(0.5, 0.008), columnspacing=1.4, handlelength=1.7)
cart.attribution_note(fig, cart.NE_NOTE +
                      " National panels: 1.5 km block-maximum classes; "
                      "enlargements: native 100 m. 2020 common year.",
                      y=0.0)

out_pdf = os.path.join(FIGURES, "fig03_agreement_map.pdf")
out_png = os.path.join(FIGURES, "fig03_agreement_map.png")
fig.savefig(out_pdf)
fig.savefig(out_png, dpi=200)
plt.close(fig)
print("saved:", out_pdf)
