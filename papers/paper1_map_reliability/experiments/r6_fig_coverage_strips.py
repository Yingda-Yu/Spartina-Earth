#!/usr/bin/env python3
"""
R6 — regenerate fig_r4_coverage_strips from results/r4_coverage_strips.csv
without the internal round label and with the unified product-colour scheme
(CMSA blue, CM-SSM teal, GEODATA orange), matching the product-identity
colours used in the other figures.

Outputs: figures/fig_r4_coverage_strips.{pdf,png}
"""
import os
os.environ.setdefault("MPLCONFIGDIR", "/data/yingda/Spartina-Earth/work/tmp_mpl")
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

import r6_cartography as cart

RESULTS = os.path.join(cart.ROOT, "papers/paper1_map_reliability/results")
FIGURES = os.path.join(cart.ROOT, "papers/paper1_map_reliability/figures")

df = pd.read_csv(os.path.join(RESULTS, "r4_coverage_strips.csv"))
df["lat_c"] = (df["lat_lo"] + df["lat_hi"]) / 2.0
df = df.sort_values("lat_c", ascending=True).reset_index(drop=True)
lat = df["lat_c"].to_numpy()
res_km2 = 0.1 * 0.1  # 100 m raster cell

y = np.arange(len(df))
h = 0.27
fig, ax = plt.subplots(figsize=(9.2, 6.6))
ax.barh(y + h, df["CMSA_px"].to_numpy() * res_km2, height=h,
        color=cart.PAL["only_a"], edgecolor="#0a4d78", linewidth=0.3,
        label="CMSA (10 m vector)")
ax.barh(y, df["CMSSM_px"].to_numpy() * res_km2, height=h,
        color=cart.PAL["spartina"], edgecolor="#0a5a48", linewidth=0.3,
        label="CM-SSM (sub-meter vector)")
ax.barh(y - h, df["GEODATA_px"].to_numpy() * res_km2, height=h,
        color=cart.PAL["only_b"], edgecolor="#a06a00", linewidth=0.3,
        label="GEODATA (30 m raster)")

ax.set_yticks(y[::2])
ax.set_yticklabels([f"{v:.1f}" for v in lat[::2]])
ax.set_ylabel("latitude band centre (°N)", fontsize=9)
ax.set_xlabel("mapped S. alterniflora area per 0.5° latitude strip (km²)",
              fontsize=9)
ax.set_xlim(0, np.ceil(df[["CMSA_px", "CMSSM_px", "GEODATA_px"]].to_numpy(
    ).max() * res_km2 / 10) * 10)
ax.tick_params(labelsize=8)
ax.grid(axis="x", color="#DDDDDD", lw=0.5)
ax.set_axisbelow(True)
ax.legend(fontsize=8.5, frameon=True, edgecolor="#888888", fancybox=False,
          loc="lower right")
for s in ax.spines.values():
    s.set_linewidth(0.5)

out_pdf = os.path.join(FIGURES, "fig_r4_coverage_strips.pdf")
out_png = os.path.join(FIGURES, "fig_r4_coverage_strips.png")
fig.tight_layout()
fig.savefig(out_pdf)
fig.savefig(out_png, dpi=200)
plt.close(fig)
print("saved:", out_pdf)
