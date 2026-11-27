#!/usr/bin/env python3
"""
E5f — Corrected regional IoU figure (replaces fig05_regional_iou, which was
built from the mislabelled EPSG:3410 longitude bands).

Inputs (all produced by the corrected analysis)
  results/regional_geographic_2020.csv      (E5d, IHO marine polygons)
  results/e5e_bootstrap_100m.csv            (E5e, 2 km block bootstrap)
  results/e5e_region_contrasts_100m.csv     (E5e, direct contrast inference)

Output
  figures/fig05_regional_iou.pdf / .png
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "..", "results")
FIGURES = os.path.join(HERE, "..", "figures")

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "DejaVu Serif"],
    "font.size": 9,
    "axes.titlesize": 10,
    "axes.labelsize": 9,
    "legend.fontsize": 8,
    "figure.dpi": 300,
    "savefig.dpi": 300,
})

REGIONS = ["Bohai_Yellow", "East_China", "South_China"]
REGION_LABEL = {
    "Bohai_Yellow": "Bohai/\nYellow Sea",
    "East_China": "East\nChina Sea",
    "South_China": "South\nChina Sea",
}
PAIRS = ["CMSA_vs_CMSSM", "CMSA_vs_GEODATA", "CMSSM_vs_GEODATA"]
PAIR_LABEL = {
    "CMSA_vs_CMSSM": "CMSA vs. CM-SSM",
    "CMSA_vs_GEODATA": "CMSA vs. GEODATA",
    "CMSSM_vs_GEODATA": "CM-SSM vs. GEODATA",
}
COLORS = {
    "CMSA_vs_CMSSM": "#1f77b4",
    "CMSA_vs_GEODATA": "#ff7f0e",
    "CMSSM_vs_GEODATA": "#2ca02c",
}


def normalise_pair(series):
    """E5d/E5e have used both `CMSA_vs_CM-SSM` and `CMSA_vs_CMSSM`."""
    return series.astype(str).str.replace("CM-SSM", "CMSSM", regex=False)


def main():
    reg = pd.read_csv(os.path.join(RESULTS, "regional_geographic_2020.csv"))
    reg["pair"] = normalise_pair(reg["pair"])
    reg = reg[(reg["resolution_m"] == 100) & (reg["subregion"].isin(REGIONS))]

    boot = pd.read_csv(os.path.join(RESULTS, "e5e_bootstrap_100m.csv"))
    boot["pair"] = normalise_pair(boot["pair"])
    boot = boot[(boot["block_km"] == 2) & (boot["scale"].isin(REGIONS))]

    contrast = pd.read_csv(os.path.join(RESULTS, "e5e_region_contrasts_100m.csv"))
    contrast["pair"] = normalise_pair(contrast["pair"])

    fig, axes = plt.subplots(1, 3, figsize=(11.4, 3.9), sharey=True)
    width = 0.26

    for ax_i, region in enumerate(REGIONS):
        ax = axes[ax_i]
        xs = np.arange(len(PAIRS))
        for k, pair in enumerate(PAIRS):
            row = reg[(reg["subregion"] == region) & (reg["pair"] == pair)]
            b = boot[(boot["scale"] == region) & (boot["pair"] == pair)]
            if row.empty or b.empty:
                continue
            iou = float(row["iou"].iloc[0])
            lo = float(b["ci_lo"].iloc[0])
            hi = float(b["ci_hi"].iloc[0])
            ax.bar(xs[k], iou, width=0.62, color=COLORS[pair],
                   edgecolor="white", linewidth=0.6)
            ax.errorbar(xs[k], iou, yerr=[[iou - lo], [hi - iou]],
                        fmt="none", ecolor="black", elinewidth=1.0,
                        capsize=3, capthick=1.0)
            ax.text(xs[k], hi + 0.018, f"{iou:.3f}", ha="center", fontsize=7)
        ax.set_xticks(xs)
        ax.set_xticklabels([PAIR_LABEL[p] for p in PAIRS], fontsize=7,
                           rotation=20, ha="right")
        ax.set_title(REGION_LABEL[region].replace("\n", " "))
        ax.set_ylim(0, 0.72)
        ax.grid(axis="y", linestyle=":", alpha=0.4)
        if ax_i == 0:
            ax.set_ylabel(r"IoU (2020, 100 m, 2 km-block 95% CI)")

    fig.suptitle(
        r"Regional IoU after geographic correction (IHO marine polygons)",
        fontsize=10,
    )
    handles = [plt.Rectangle((0, 0), 1, 1, facecolor=COLORS[p], edgecolor="white")
               for p in PAIRS]
    fig.legend(handles, [PAIR_LABEL[p] for p in PAIRS], loc="lower center",
               ncol=3, frameon=False, bbox_to_anchor=(0.5, -0.02))
    fig.subplots_adjust(left=0.07, right=0.98, top=0.84, bottom=0.28, wspace=0.28)

    fig.savefig(os.path.join(FIGURES, "fig05_regional_iou.pdf"), bbox_inches="tight")
    fig.savefig(os.path.join(FIGURES, "fig05_regional_iou.png"), bbox_inches="tight")
    plt.close(fig)

    # print the contrast summary used in the caption / text
    for _, r in contrast.sort_values(["pair", "region_high"]).iterrows():
        print(f"{r['pair']:20s} {r['region_high']:13s} vs {r['region_low']:13s} "
              f"ratio={r['ratio']:.3f} [{r['ratio_ci_lo']:.3f}, {r['ratio_ci_hi']:.3f}] "
              f"p={r['p_two_side']:.3f}")


if __name__ == "__main__":
    main()
