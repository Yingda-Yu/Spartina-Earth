# R5-06 — Figure and Table QA for IJRS Submission

**Manuscript:** Spatial Agreement and Regional Uncertainty in Multi-Source
Maps of *Spartina alterniflora* along the Chinese Coast
**QA pass:** 2026-11-08, after R5 repositioning edits; manuscript compiles to
29 pp with 0 undefined references.

---

## 1. Figure inventory and format compliance

IJRS Instructions for Authors: figures should be high quality — 1200 dpi line
art, 600 dpi grayscale, 300 dpi colour at correct size; preferred formats
PS, EPS, TIFF, JPG.

| Figure (file) | Role | Render size | PNG DPI | IJRS status |
|---|---|---|---|---|
| fig03_agreement_map | National + zoom agreement maps (RQ2 core) | 4500×3150 | 300 | OK (colour) |
| fig04_stats | Area trends, IoU/Dice overview | 3842×1162 | 300 | OK (colour) |
| fig05_regional_iou | Regional IoU with 95% CIs | 3314×1213 | 300 | OK (colour) |
| fig_r4_region_assignment | Attribution-distance map | 3300×1860 | 300 | OK (colour) |
| fig_r4_coverage_strips | Footprint proxy by latitude strip | 3000×2100 | 300 | OK (colour) |
| fig_r4_south_china_zoom | Largest disagreement clusters | 4680×1680 | 300 | OK (colour) |
| fig05_resolution | Resolution sensitivity curves | 1740×1166 | 300 | OK (colour) |
| fig06_robustness | Processing robustness panels | 3570×1348 | 300 | OK (colour) |

All eight figures are rendered maps/charts with colour, so the 300 dpi
colour requirement applies and is met. Vector PDFs are the in-repo canonical
render (used by the manuscript build); EPS/TIFF exports are produced for the
submission package (R5-09). `fig_r4_south_china_overview.png/pdf` is an
unreferenced supporting render retained in `figures/` (audit support); it is
correctly NOT part of the manuscript's figure count.

## 2. Visual inspection findings (2026-11-08)

**fig03_agreement_map** — PASS with notes: panel titles, sea-region labels,
legend (green = both, blue = only first, orange = only second, pale = neither)
and 10 km scale bars in zoom panels are correct and legible; the caption
carries the per-pair IoU values. Minor (accepted, non-blocking): sea labels
are small italic; no scale bar on the national row (axis tick labels in km
provide scale); "neither" swatch is low contrast but the class is panel
background and unambiguous.

**fig_r4_region_assignment** — PASS: teal/blue = direct polygon membership,
warm binned colours = nearest-assignment distance with the discrete colorbar
bins 0–1/1–5/5–10/10–20/20–50/>50 km; the manuscript caption names the bins
explicitly, resolving the single-dot legend ambiguity. Region labels legible;
no artifacts.

**fig_r4_south_china_zoom** — PASS: three cluster panels with per-panel
titles including cluster area (2.11, 1.55, 8.50 km²) and grid coordinates;
legend green/orange/purple matches the caption semantics; axes in km provide
scale; no artifacts.

Remaining figures (fig04_stats, fig05_regional_iou, fig05_resolution,
fig06_robustness, fig_r4_coverage_strips) were re-rendered and inspected in
R4-06/R4-08; captions re-checked against current numbers in R5 (values
unchanged: IoU 0.5395/0.4444/0.3432, ratio 4.18 [2.74, 7.51], policy range
4.06–4.18).

## 3. Caption / coordinate / unit checks

- All map figures use EPSG:3410 coordinates labelled in km on axes; captions
  state the projection and resolution (100 m) — consistent.
- Areas are km², distances km, percentages with \,\% spacing — consistent
  across captions and tables.
- Caption numeric spot-checks against `results/`: fig03 caption IoUs
  (0.5395/0.4444/0.3432) match `results/e5e_bootstrap_100m.csv`; fig05 CIs
  match the bootstrap table; fig_r4_region_assignment "31,201 px = 34.4%"
  matches `results/r4_region_assignment_sensitivity.csv` totals;
  fig_r4_coverage_strips ≤0.28% bound matches `r4_coverage_audit.md`;
  fig_r4_south_china_zoom cluster areas match
  `results/r4_south_china_clusters.csv`.

## 4. Table inventory

12 numbered tables: 3 input files (`table1_datasets.tex`,
`tab_region_policy.tex`, `tab_south_china.tex`) and 9 inline
(tab:area2020, tab:iou30, tab:regional_iou, tab:bootstrap, tab:sens,
tab:robustness, tab:hotspots, appendix tab:data_inv, tab:licenses).
Unreferenced legacy files `table2_area_comparison.tex`,
`table3_spatial_agreement.tex`, `table4_sensitivity.tex` remain in
`tables/` as traceability orphans (superseded by the inline versions); they
are not part of the manuscript.

Numeric checks (already verified in R4-08; re-confirmed unchanged in R5):
tab:area2020 vs `results/area_summary.json`; tab:iou30 vs
`results/iou_dice_2020_multi_res.csv`; tab:regional_iou vs
`results/regional_geographic_2020.csv`; tab:bootstrap vs
`results/e5e_bootstrap_100m.csv`; tab:sens vs
`results/robustness_2020.csv`; policy table vs
`results/r4_region_assignment_sensitivity.csv`.

Known intentional placeholder cells retained (owner-dependent, flagged in
R5-08 checklist): appendix tab:data_inv / tab:licenses carry TODO_VERIFY
for the CMSA license and CC-BY-NC-ND? for GEODATA — these reflect the true
verification state and must be resolved by the owner before submission.

## 5. Figure-count decision

Eight figures, all carrying non-redundant evidence: coverage/area (fig04),
agreement maps (fig03), regional IoU + CIs (fig05_regional_iou),
attribution sensitivity (fig_r4_region_assignment), coverage proxy
(fig_r4_coverage_strips), South China clusters (fig_r4_south_china_zoom),
resolution sensitivity (fig05_resolution), processing robustness
(fig06_robustness). No figure was added merely to reach a target count; no
evidence-bearing figure was dropped. This satisfies the "do not force seven
figures" constraint: the count follows the evidence.

## 6. Verdict

**PASS for submission packaging**, with two owner-dependent items carried in
the R5-08 checklist: (1) appendix license placeholders, (2) author metadata.
No figure or table requires regeneration on scientific grounds.
