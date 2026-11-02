#!/usr/bin/env python3.11
"""
Generate publication-quality figures for Paper 1 — Multi-Source
Spartina alterniflora Map Reliability.

Run from repo root:
    export PROJ_LIB=/data/yingda/software/miniconda3/envs/spartina-earth/share/proj
    /data/yingda/software/miniconda3/envs/spartina-earth/bin/python3.11 \
        papers/paper1_map_reliability/experiments/generate_figures.py
"""

import json
import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# ── paths ──────────────────────────────────────────────────────────────────
REPO = Path(__file__).resolve().parent.parent
RESULTS = REPO / "results"
FIGURES = REPO / "figures"
FIGURES.mkdir(exist_ok=True)

# ── journal-quality rcParams ────────────────────────────────────────────────
plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "DejaVu Serif", "Nimbus Roman"],
    "font.size": 9,
    "axes.titlesize": 10,
    "axes.labelsize": 9,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "legend.fontsize": 8,
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.05,
    "axes.linewidth": 0.8,
    "lines.linewidth": 1.5,
    "lines.markersize": 5,
    "xtick.major.width": 0.8,
    "ytick.major.width": 0.8,
})

# ── figure helper ──────────────────────────────────────────────────────────
def savefig(fig, stem: str):
    fig.savefig(FIGURES / f"{stem}.pdf")
    fig.savefig(FIGURES / f"{stem}.png", dpi=300)
    plt.close(fig)
    print(f"  saved {stem}.pdf / {stem}.png")


# ============================================================================
# Load data
# ============================================================================

# Area data from audit
area_json = json.loads((RESULTS / "area_summary.json").read_text())

# IoU/Dice from harmonization
iou_csv = pd.read_csv(RESULTS / "iou_dice_2020_multi_res.csv")

# Manual area numbers for figure (from audited source)
cmsa_years = [2017, 2018, 2019, 2020, 2021]
cmsa_area = [494.69, 504.31, 532.99, 571.35, 586.51]
geodata_years = [1990, 2000, 2015, 2020]
geodata_area = [43.77, 256.43, 547.46, 519.89]
cmssm_2020 = 593.71

# ============================================================================
# Figure 4 — Area and spatial agreement statistics (3-panel)
# ============================================================================
print("Generating fig04_stats...")

fig, axes = plt.subplots(1, 3, figsize=(7.2, 2.8))

# (a) Area trend
ax = axes[0]
bar_width = 0.5
x_cmsa = np.arange(len(cmsa_years))
x_geodata = np.array([cmsa_years.index(y) if y in cmsa_years else -1 for y in geodata_years], dtype=float)
# GEODATA at positions that don't align with CMSA get their own offset
geodata_positions = []
geodata_values = []
geodata_labels = []
for gyear, gval in zip(geodata_years, geodata_area):
    if gyear in cmsa_years:
        geodata_positions.append(cmsa_years.index(gyear) + 0.22)
    else:
        geodata_positions.append(-0.6 + 0.3 * (geodata_years.index(gyear)))
    geodata_values.append(gval)
    geodata_labels.append(str(gyear))

# Simpler approach: scatter-style bars
ax.bar(np.arange(len(cmsa_years)), cmsa_area, width=0.6, color="#3B7DD8",
       label="CMSA (10 m vector)", alpha=0.9, edgecolor="black", linewidth=0.5)
# GEODATA bars at appropriate positions
geo_x = [-0.5, 0.0, 1.5, 3.0]  # approximate positions that don't overlap CMSA much
ax.bar(geo_x, geodata_area, width=0.5, color="#D83B3B",
       label="GEODATA (30 m raster)", alpha=0.9, edgecolor="black", linewidth=0.5)
# CM-SSM as a single marker at 2020
ax.scatter([3], [cmssm_2020], color="#2E8B57", s=70, zorder=5,
           marker="D", label="CM-SSM 2020")

ax.set_xticks(geo_x + list(np.arange(len(cmsa_years))))
ax.set_xticklabels(geodata_labels + [str(y) for y in cmsa_years], rotation=45, ha="right", fontsize=7)
ax.set_ylabel(r"National $\mathit{Spartina\ alterniflora}$ area (km$^2$)")
ax.set_title("(a) Area estimates across products and years", fontsize=9)
ax.legend(loc="upper left", fontsize=7, framealpha=0.9)
ax.grid(axis="y", alpha=0.3, linestyle="--")

# (b) IoU and Dice bar chart
ax = axes[1]
pairs = ["CMSA\nvs\nCM-SSM", "CMSA\nvs\nGEODATA", "CM-SSM\nvs\nGEODATA"]
iou_30 = iou_csv[iou_csv["resolution_m"] == 30.0]["IoU"].values
dice_30 = iou_csv[iou_csv["resolution_m"] == 30.0]["Dice"].values

x = np.arange(len(pairs))
w = 0.35
ax.bar(x - w/2, iou_30, w, label="IoU", color="#3B7DD8",
       edgecolor="black", linewidth=0.5)
ax.bar(x + w/2, dice_30, w, label="Dice", color="#D83B3B",
       edgecolor="black", linewidth=0.5)
for xi, v in zip(x - w/2, iou_30):
    ax.text(xi, v + 0.015, f"{v:.4f}", ha="center", fontsize=6.5)
for xi, v in zip(x + w/2, dice_30):
    ax.text(xi, v + 0.015, f"{v:.4f}", ha="center", fontsize=6.5)

ax.set_xticks(x)
ax.set_xticklabels(pairs, fontsize=8)
ax.set_ylim(0, 0.9)
ax.set_ylabel("Agreement metric value")
ax.set_title("(b) Pair-wise IoU and Dice (30 m, 2020)")
ax.legend(loc="upper right", fontsize=7, framealpha=0.9)
ax.grid(axis="y", alpha=0.3, linestyle="--")

# (c) Resolution sensitivity curves
ax = axes[2]
colors = {"CMSA_vs_CMSSM": "#3B7DD8", "CMSA_vs_GEODATA": "#D83B3B", "CMSSM_vs_GEODATA": "#2E8B57"}
labels_map = {"CMSA_vs_CMSSM": "CMSA vs. CM-SSM",
              "CMSA_vs_GEODATA": "CMSA vs. GEODATA",
              "CMSSM_vs_GEODATA": "CM-SSM vs. GEODATA"}
resolutions = [30, 50, 100]

for pair in ["CMSA_vs_CMSSM", "CMSA_vs_GEODATA", "CMSSM_vs_GEODATA"]:
    sub = iou_csv[iou_csv["pair"] == pair].sort_values("resolution_m")
    ax.plot(sub["resolution_m"], sub["IoU"], marker="o", linewidth=1.5,
            color=colors[pair], label=labels_map[pair])

ax.set_xlabel("Target resolution (m)")
ax.set_ylabel("IoU")
ax.set_title("(c) IoU vs.\ resolution (2020)")
ax.legend(fontsize=7, framealpha=0.9)
ax.grid(alpha=0.3, linestyle="--")
ax.set_xticks(resolutions)

fig.tight_layout()
savefig(fig, "fig04_stats")


# ============================================================================
# Figure 5 — Resolution sensitivity curves (standalone, larger)
# ============================================================================
print("Generating fig05_res_curves...")

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(6.0, 3.0))

for pair in ["CMSA_vs_CMSSM", "CMSA_vs_GEODATA", "CMSSM_vs_GEODATA"]:
    sub = iou_csv[iou_csv["pair"] == pair].sort_values("resolution_m")
    ax1.plot(sub["resolution_m"], sub["IoU"], marker="o", linewidth=1.5,
             color=colors[pair], label=labels_map[pair])
    ax2.plot(sub["resolution_m"], sub["Dice"], marker="s", linewidth=1.5,
             color=colors[pair], label=labels_map[pair])

ax1.set_xlabel("Target resolution (m)")
ax1.set_ylabel("IoU")
ax1.set_title("IoU vs. resolution (2020, EPSG:3410)")
ax1.legend(fontsize=7, framealpha=0.9, loc="lower right")
ax1.grid(alpha=0.3, linestyle="--")
ax1.set_xticks([30, 50, 100])

ax2.set_xlabel("Target resolution (m)")
ax2.set_ylabel("Dice coefficient")
ax2.set_title("Dice vs. resolution (2020, EPSG:3410)")
ax2.legend(fontsize=7, framealpha=0.9, loc="lower right")
ax2.grid(alpha=0.3, linestyle="--")
ax2.set_xticks([30, 50, 100])

fig.tight_layout()
savefig(fig, "fig05_res_curves")


# ============================================================================
# Summary print
# ============================================================================
print("\n=== All figures generated ===")
for p in sorted(FIGURES.iterdir()):
    print(f"  {p.name}")
