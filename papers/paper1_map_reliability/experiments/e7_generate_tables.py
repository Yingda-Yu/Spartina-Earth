"""
Generate LaTeX table files from CSV/JSON results.
Output: papers/paper1_map_reliability/tables/
  table2_area_comparison.tex
  table3_spatial_agreement.tex
  table4_sensitivity.tex
"""
import json, os, sys
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "..", "results")
TABLES = os.path.join(HERE, "..", "tables")

# ----- Table 2: Area comparison -----
with open(os.path.join(RESULTS, "area_summary.json")) as f:
    area = json.load(f)

# CMSA annual
cmsa = area["cmsa_km2"]
cmsa_years = sorted(cmsa.keys(), key=int)
geodata = area["geodata_km2"]
geodata_years = sorted(geodata.keys(), key=int)
cmssm_2020 = area.get("cmssm_2020_km2_planar", None)

with open(os.path.join(TABLES, "table2_area_comparison.tex"), "w") as f:
    f.write(r"""\begin{table}[htpb]
\centering
\caption{\label{tab:area_full}National \textit{S.~alterniflora} area estimates
  per product and year, from audited source statistics. CMSA and GEODATA values
  are source-reported; CM-SSM is 2020 UTM-planar (EPSG:32650). All three 2020
  values are independently derived from raw source files in this study.}
\begin{tabular}{l c c l}
\toprule
Product & Years & Area (km$^2$) & Source \\
\midrule
CMSA & 2017 & 494.69 & Sentinel-2, 10\,m vector \\
     & 2018 & 504.31 & \\
     & 2019 & 532.99 & \\
     & \textbf{2020} & \textbf{571.35} & \\
     & 2021 & 586.51 & \\
\midrule
GEODATA & 1990 & 43.77 & Landsat, 30\,m Albers \\
        & 2000 & 256.43 & \\
        & 2015 & 547.46 & \\
        & \textbf{2020} & \textbf{519.89} & \\
\midrule
CM-SSM & \textbf{2020} & \textbf{593.71} & Sub-meter, 148\,072 polygons \\
\bottomrule
\end{tabular}
\end{table}
""")
print("  table2_area_comparison.tex")

# ----- Table 3: Spatial agreement (30m) -----
df = pd.read_csv(os.path.join(RESULTS, "iou_dice_2020_multi_res.csv"))
d30 = df[df["resolution_m"] == 30.0]

with open(os.path.join(TABLES, "table3_spatial_agreement.tex"), "w") as f:
    f.write(r"""\begin{table}[htpb]
\centering
\caption{\label{tab:spatial_agreement}Pair-wise 2020 spatial agreement at 30\,m
  resolution (EPSG:3410). Areas are harmonized rasterized totals from this study's
  rasterization protocol. Disagreement masses ($only\_A$, $only\_B$) quantify
  spatial conflict; \emph{not} to be interpreted as omission/commission errors.}
\begin{tabular}{l c c c c c c}
\toprule
Product Pair & IoU & Dice & $A$ (km$^2$) & $B$ (km$^2$) & Both & Disagree \\
\midrule
""")
    for _, r in d30.iterrows():
        pair = r["pair"].replace("_vs_", " vs.\ ").replace("CMSSM", "CM-SSM")
        both = r["intersection_km2"]
        disagree = r["only_A_km2"] + r["only_B_km2"]
        f.write(f"{pair} & {r['IoU']:.4f} & {r['Dice']:.4f} & "
                f"{r['A_km2']:.2f} & {r['B_km2']:.2f} & {both:.2f} & "
                f"{disagree:.2f} \\\\\n")
    f.write(r"""\bottomrule
\end{tabular}
\end{table}
""")
print("  table3_spatial_agreement.tex")

# ----- Table 4: Sensitivity -----
with open(os.path.join(TABLES, "table4_sensitivity.tex"), "w") as f:
    f.write(r"""\begin{table}[htpb]
\centering
\caption{\label{tab:sensitivity_full}Resolution sensitivity of IoU and Dice
  coefficients. Values change by $\leq$0.4\,\% between 30\,m and 100\,m for all
  pairs, indicating that thematic encoding (patch-delineation semantics) rather
  than spatial resolution dominates product disagreement.}
\begin{tabular}{l l c c c c}
\toprule
Product Pair & Metric & 30\,m & 50\,m & 100\,m & 100\,m / 30\,m \\
\midrule
""")
    for pair in sorted(df["pair"].unique()):
        pair_display = pair.replace("_vs_", " vs.\ ").replace("CMSSM", "CM-SSM")
        sub = df[df["pair"] == pair].sort_values("resolution_m")
        for i, metric in enumerate(["IoU", "Dice"]):
            vals = sub[metric].tolist()
            ratio = vals[-1] / vals[0] - 1
            first_col = (pair_display if i == 0 else "")
            f.write(f"{first_col} & {metric} & {vals[0]:.4f} & {vals[1]:.4f} & "
                    f"{vals[2]:.4f} & {ratio*100:+.1f}\\,\% \\\\\n")
        f.write(r"\midrule" + "\n")
    f.write(r"""\bottomrule
\end{tabular}
\end{table}
""")
print("  table4_sensitivity.tex")

print("\nDone. All LaTeX tables generated.")
