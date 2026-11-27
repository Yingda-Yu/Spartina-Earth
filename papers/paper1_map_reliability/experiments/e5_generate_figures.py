#!/usr/bin/env python3
"""
Paper 1 — publication-quality figure generation.

Figures generated:
  fig04_stats.pdf/png  — 3-panel: area trend bars + IoU/Dice bars + resolution IoU curves
  fig05_resolution.pdf/png — standalone resolution sensitivity curves

Data sources:
  results/area_summary.json           (E2 area consistency)
  results/iou_dice_2020_multi_res.csv (E3+E4 spatial agreement)
"""

import json
import csv
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd

# ---------- paths ----------
HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "..", "results")
FIGURES = os.path.join(HERE, "..", "figures")
os.makedirs(FIGURES, exist_ok=True)

# ---------- global style ----------
plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "DejaVu Serif"],
    "mathtext.fontset": "dejavuserif",
    "font.size": 10,
    "axes.titlesize": 11,
    "axes.labelsize": 10,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "legend.fontsize": 8,
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "axes.linewidth": 0.8,
    "lines.linewidth": 1.8,
})

# color palette (colorblind-safe)
COLORS = {
    "CMSA": "#1f77b4",       # blue
    "GEODATA": "#ff7f0e",    # orange
    "CMSSM": "#2ca02c",      # green
    "CMSA_vs_CMSSM": "#1f77b4",
    "CMSA_vs_GEODATA": "#ff7f0e",
    "CMSSM_vs_GEODATA": "#2ca02c",
}

# =====================================================================
# Load data
# =====================================================================

# --- area_summary.json ---
with open(os.path.join(RESULTS, "area_summary.json")) as f:
    area_data = json.load(f)

# Build time-series for each product (JSON has dict-of-dicts structure)
cmsa_years = sorted([int(k) for k in area_data.get("cmsa_km2", {}).keys()])
cmsa_areas = [area_data["cmsa_km2"][str(y)] for y in cmsa_years]

geodata_years = sorted([int(k) for k in area_data.get("geodata_km2", {}).keys()])
geodata_areas = [area_data["geodata_km2"][str(y)] for y in geodata_years]

# CM-SSM: single 2020 value
cmssm_years = [2020]
cmssm_areas = [area_data.get("cmssm_2020_km2_planar", 593.71)]

print(f"CMSA time series: {len(cmsa_years)} points  ({cmsa_years})")
print(f"GEODATA time series: {len(geodata_years)} points  ({geodata_years})")
print(f"CM-SSM: {len(cmssm_years)} points")

# --- IoU/Dice CSV ---
iou_df = pd.read_csv(os.path.join(RESULTS, "iou_dice_2020_multi_res.csv"))
print(f"IoU/Dice: {len(iou_df)} rows")

# =====================================================================
# FIG 04 — 3-panel composite figure
# =====================================================================

fig, axes = plt.subplots(1, 3, figsize=(13, 4.2))
fig.subplots_adjust(left=0.08, right=0.97, top=0.88, bottom=0.15, wspace=0.32)

# Panel (a) — Area time series bars
ax = axes[0]
all_years = sorted(set(cmsa_years + geodata_years))
y_pos_all = np.arange(len(all_years))
year_to_idx = {y: i for i, y in enumerate(all_years)}

bar_width = 0.28
# CMSA
cmsa_x = [year_to_idx[y] - bar_width for y in cmsa_years]
ax.bar(cmsa_x, cmsa_areas, width=bar_width, color=COLORS["CMSA"],
       label="CMSA (10\,m vector)", edgecolor="white", linewidth=0.5)
# GEODATA
geodata_x = [year_to_idx[y] for y in geodata_years]
ax.bar(geodata_x, geodata_areas, width=bar_width, color=COLORS["GEODATA"],
       label="GEODATA (30\,m raster)", edgecolor="white", linewidth=0.5)
# CM-SSM (only 2020)
if cmssm_years:
    cmssm_x = [year_to_idx[y] + bar_width for y in cmssm_years]
    ax.bar(cmssm_x, cmssm_areas, width=bar_width, color=COLORS["CMSSM"],
           label="CM-SSM (sub-meter)", edgecolor="white", linewidth=0.5,
           hatch="//")

ax.set_xticks(y_pos_all)
ax.set_xticklabels([str(y) for y in all_years], rotation=45, ha="right")
ax.set_ylabel(r"Area (km$^2$)")
ax.set_title(r"(a) National \textit{S.~alterniflora} area")
ax.legend(loc="upper left", frameon=True, edgecolor="gray", fancybox=False)
ax.set_xlim(-0.6, len(all_years) - 0.4)
ax.grid(axis="y", linestyle=":", alpha=0.4)

# Panel (b) — IoU and Dice bars at 30m
ax = axes[1]
pairs_30 = iou_df[iou_df["resolution_m"] == 30.0].copy()
pairs_30 = pairs_30.sort_values("IoU", ascending=False)
pair_labels = [p.replace("_vs_", "\nvs.\n").replace("CMSSM", "CM-SSM")
               for p in pairs_30["pair"]]
pair_labels_short = [p.replace("_vs_", " vs. ").replace("CMSSM", "CM-SSM")
                     for p in pairs_30["pair"]]
x = np.arange(len(pairs_30))
w = 0.35
ax.bar(x - w/2, pairs_30["IoU"], width=w, label="IoU",
       color="#4a7db5", edgecolor="white", linewidth=0.5)
ax.bar(x + w/2, pairs_30["Dice"], width=w, label="Dice",
       color="#b57a4a", edgecolor="white", linewidth=0.5)
ax.set_xticks(x)
ax.set_xticklabels(pair_labels_short, fontsize=8)
ax.set_ylabel("Agreement metric")
ax.set_title(r"(b) 2020 pair-wise spatial agreement (30\,m)")
ax.legend(loc="upper right", frameon=True, edgecolor="gray", fancybox=False)
ax.set_ylim(0, 1.0)
ax.grid(axis="y", linestyle=":", alpha=0.4)
# Add value labels
for xi, iou_val, dice_val in zip(x, pairs_30["IoU"], pairs_30["Dice"]):
    ax.text(xi - w/2, iou_val + 0.02, f"{iou_val:.4f}", ha="center", fontsize=7, color="#4a7db5")
    ax.text(xi + w/2, dice_val + 0.02, f"{dice_val:.4f}", ha="center", fontsize=7, color="#b57a4a")

# Panel (c) — IoU vs resolution curves
ax = axes[2]
pairs = pairs_30["pair"].tolist()
for pair in pairs:
    sub = iou_df[iou_df["pair"] == pair].sort_values("resolution_m")
    color_key = pair
    ax.plot(sub["resolution_m"], sub["IoU"], "o-",
            color=COLORS[color_key], label=pair.replace("_", " "),
            markersize=5, markerfacecolor="white", markeredgewidth=1.2)
    # also Dice as dashed
    ax.plot(sub["resolution_m"], sub["Dice"], "--", color=COLORS[color_key],
            alpha=0.5, linewidth=1.0)

ax.set_xlabel("Resolution (m)")
ax.set_ylabel("Metric value")
ax.set_title(r"(c) Resolution sensitivity (solid = IoU, dashed = Dice)")
ax.legend(loc="best", frameon=True, edgecolor="gray", fancybox=False,
          fontsize=7, labels=[p.replace("CMSSM", "CM-SSM") for p in pairs])
ax.grid(linestyle=":", alpha=0.4)
ax.set_xticks([30, 50, 100])
ax.set_ylim(0.3, 0.75)

fig.savefig(os.path.join(FIGURES, "fig04_stats.pdf"), bbox_inches="tight")
fig.savefig(os.path.join(FIGURES, "fig04_stats.png"), bbox_inches="tight")
plt.close(fig)
print("Saved fig04_stats.pdf / .png")

# =====================================================================
# FIG 05 — Standalone resolution sensitivity
# =====================================================================

fig, ax = plt.subplots(figsize=(6.5, 4.0))

for pair in pairs:
    sub = iou_df[iou_df["pair"] == pair].sort_values("resolution_m")
    label = pair.replace("CMSSM", "CM-SSM").replace("_", " ")
    ax.plot(sub["resolution_m"], sub["IoU"], "o-", color=COLORS[pair],
            label=label, markersize=6, markerfacecolor="white", markeredgewidth=1.3)
    ax.plot(sub["resolution_m"], sub["Dice"], "s--", color=COLORS[pair],
            alpha=0.6, markersize=4, linewidth=1.0)

# Add stability annotation
ax.text(0.98, 0.04,
        r"IoU change 30$\rightarrow$100\,m: $\leq$0.4\,\%" "\n"
        r"Disagreement $\neq$ edge noise",
        transform=ax.transAxes, ha="right", va="bottom", fontsize=8,
        bbox=dict(boxstyle="round,pad=0.3", facecolor="wheat", alpha=0.8, edgecolor="gray"))

ax.set_xlabel("Resolution (m)")
ax.set_ylabel("Agreement metric")
ax.set_title(r"Resolution sensitivity of 2020 pair-wise IoU and Dice")
ax.legend(loc="best", frameon=True, edgecolor="gray", fancybox=False, fontsize=8)
ax.grid(linestyle=":", alpha=0.4)
ax.set_xticks([30, 50, 100])

fig.savefig(os.path.join(FIGURES, "fig05_resolution.pdf"), bbox_inches="tight")
fig.savefig(os.path.join(FIGURES, "fig05_resolution.png"), bbox_inches="tight")
plt.close(fig)
print("Saved fig05_resolution.pdf / .png")

# =====================================================================
# Summary print
# =====================================================================
print("\n=== FIGURE GENERATION COMPLETE ===")
print(f"Output directory: {FIGURES}")
for f in sorted(os.listdir(FIGURES)):
    size = os.path.getsize(os.path.join(FIGURES, f))
    print(f"  {f:40s} {size/1024:.0f} KB")
