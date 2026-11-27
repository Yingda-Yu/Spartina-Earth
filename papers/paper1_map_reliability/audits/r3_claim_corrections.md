# R3.1 — Claim corrections ledger

**Date:** 2026-11-05
**Branch:** `feat/paper1-map-reliability`
**Rule:** every quantitative claim in `manuscript/main.tex` was re-traced to
an output file. For each corrected claim this ledger records the previous
value, the revised value, the reason, and the supporting output.

---

## A. Numerical errors independent of the geographic defect

### A1. GEODATA 2015→2020 area change

| Field | Content |
|---|---|
| Previous | **−6.8 %** |
| Revised | **−5.0 %** |
| Reason | Arithmetic error. The audited source areas are 547.46 km² (2015) and 519.89 km² (2020): (519.89 − 547.46)/547.46 = −5.04 %. |
| Support | `results/area_summary.json`; `audit_all_sources.py` |
| Occurrences fixed | Abstract, Results (RQ1), Discussion, RQ4, Conclusions |

### A2. Raster pixel count

| Field | Content |
|---|---|
| Previous | **3.35 billion** 100 m cells |
| Revised | **334,617,936** cells (334.62 million) |
| Reason | 15096 × 22166 = 334,617,936, i.e. 3.346 × 10⁸ not 3.35 × 10⁹. |
| Support | `results/region_definitions_geographic.json` → `grid.total_px`; `e6` stdout "Grid: 15096x22166 px = 334.6 M px" |
| Note on the brief | The task brief quoted 334,917,936. Independent multiplication gives **334,617,936**; the brief's value is 300,000 high. The manuscript uses the verified product. |

### A3. "Maps 11.0 % less area" (30 m, CMSA vs GEODATA)

| Field | Content |
|---|---|
| Previous | 11.0 % less |
| Revised | **8.7 %** less |
| Reason | (570.11 − 520.38)/570.11 = 8.72 %. The 11.0 % figure did not match either the harmonized or the source-reported areas. |
| Support | `results/iou_dice_2020_multi_res.csv`; `tables/table3_spatial_agreement.tex` |

### A4. Effective-sample framing

| Field | Content |
|---|---|
| Previous | "despite *de facto* billion-pixel sample sizes" and a 3.35-billion-pixel comparison |
| Revised | "about 2,000 informative 2 km blocks (0.24–0.27 % of all blocks)" |
| Reason | Only 2,014–2,256 of 837,295 blocks contain any union pixel. |
| Support | `results/e5e_bootstrap_100m.csv` → `n_blocks_informative` |

## B. Geographic regionalisation corrections

### B1. Region definitions

| Field | Content |
|---|---|
| Previous | Three EPSG:3410 x-coordinate bands (`x < 11.0 Mm`, `11.0–11.5 Mm`, `x ≥ 11.5 Mm`) called Bohai/Yellow Sea, East China Sea, South China Sea |
| Revised | Three groups of Natural Earth 10m IHO-derived marine polygons, clipped to the domain, rasterized at 100 m |
| Reason | EPSG:3410 x is linear in longitude (~96.3 km/°), so the bands were meridian slices, and their labels were inverted relative to the coast they contained |
| Support | `experiments/e5d_geographic_regions.py`; `results/region_definitions_geographic.json`; `results/superseded_e5_longitude_bands/README.md` |

### B2. CMSA–GEODATA regional ordering

| Field | Content |
|---|---|
| Previous | Highest agreement in the **South China Sea** (0.4570); lowest in the **Bohai/Yellow Sea** (0.1437); ratio 3.2× |
| Revised | Highest in the **Bohai/Yellow Sea** (0.5599); lowest in the **South China Sea** (0.1341); ratio 4.18× [2.74, 7.51], p < 0.001 |
| Reason | The old labels were inverted; the numbers were computed on bands, not sea regions |
| Support | `results/regional_geographic_2020.csv`; `results/e5e_region_contrasts_100m.csv` |

### B3. East China Sea (CMSA–GEODATA)

| Field | Content |
|---|---|
| Previous | 0.4751 |
| Revised | 0.3923 |
| Reason | Replaced band B with the East China Sea + Hangzhou Bay + Taiwan Strait group |
| Support | `results/regional_geographic_2020.csv` |

### B4. Regional CI values

| Field | Previous | Revised |
|---|---|---|
| Bohai/Yellow | [0.078, 0.211] | [0.519, 0.600] |
| East China | [0.405, 0.529] | [0.355, 0.429] |
| South China | [0.424, 0.487] | [0.077, 0.191] |

Reason: different regions and a corrected estimand. Support:
`results/e5e_bootstrap_100m.csv` (2 km, seed 202601).

### B5. Regional hotspot shares

| Region | Previous CMSA / CM-SSM / GEODATA | Revised |
|---|---|---|
| Bohai/Yellow | 3.3 / 2.4 / 4.6 % | **40.8 / 32.1 / 44.2 %** |
| East China | 14.3 / 6.8 / 16.6 % | **55.8 / 65.4 / 50.7 %** |
| South China | 82.2 / 90.4 / 79.1 % | **3.4 / 2.5 / 5.1 %** |

Reason: same inverted labels. Support:
`results/regional_area_share_geographic_2020.csv`.

### B6. Rank correlation

| Field | Content |
|---|---|
| Previous | ρ = 1.00 (CMSA vs GEODATA), ρ = 0.50 (CMSA vs CM-SSM); "secondary regional rankings are not robust" |
| Revised | ρ = 1.00 for all three pairs; the rank order East > Bohai/Yellow > South is identical across products |
| Reason | Recomputed on corrected regions; products differ in magnitude, not rank |
| Support | `results/regional_area_share_geographic_2020.csv` |

### B7. Monitoring-allocation sensitivity

| Field | Content |
|---|---|
| Previous | "GEODATA allocates 4.6 % to Bohai/Yellow while CMSA allocates 3.3 %, a 40 % relative difference" |
| Revised | "GEODATA allocates 44.2 % while CMSA allocates 40.8 %, an 8.4 % relative difference" |
| Reason | Both the shares and the relative gap were artifacts of the band labels |
| Support | `results/regional_area_share_geographic_2020.csv` |

### B8. Coverage

| Field | Content |
|---|---|
| Previous | South China "4.4–5.0 % coverage"; Bohai/Yellow "0.1–0.2 % coverage" |
| Revised | Bohai/Yellow 0.068 %, East China 0.091 %, South China 0.009 % |
| Reason | Coverage = mapped area / region area; both changed with the corrected region masks |
| Support | `results/regional_geographic_2020.csv` → `a_coverage_pct`, `region_area_km2` |

### B9. Boundary-shift robustness

| Field | Content |
|---|---|
| Previous | "The 3× finding is robust to ±250–500 km boundary shifts, therefore it is a genuine ecological signal" |
| Revised | Claim withdrawn; the band-shift table is removed from the manuscript |
| Reason | Shifting a meridian band is not a perturbation of a geographic boundary; its "robustness" cannot transfer to sea regions |
| Support | `results/superseded_e5_longitude_bands/e5b_boundary_sensitivity.csv` (archived, not cited) |

## C. Statistical pairing corrections

### C1. Point estimate vs interval resolution

| Field | Content |
|---|---|
| Previous | 30 m IoU point estimates (0.5375 / 0.4437 / 0.3423) paired with 100 m bootstrap CIs ([0.5101, 0.5689] / [0.4182, 0.4719] / [0.3139, 0.3731]) |
| Revised | 100 m point estimate and 100 m CI on the same grid: 0.5395 [0.5096, 0.5708]; 0.4444 [0.4128, 0.4733]; 0.3432 [0.3139, 0.3714] |
| Reason | Two different estimands were paired. The 30 m table is retained, explicitly labelled as a resolution-sensitivity table; primary inference is at 100 m. |
| Support | `results/iou_dice_2020_multi_res.csv`; `results/e5e_bootstrap_100m.csv` |

### C2. Significance from marginal CIs

| Field | Content |
|---|---|
| Previous | "The 95 % CIs for Bohai/Yellow [0.078, 0.211] and South China [0.424, 0.487] do not overlap, confirming that the observed 3× IoU regional variation is statistically meaningful" |
| Revised | Direct bootstrap of the difference and ratio: +0.426 [0.346, 0.499]; ratio 4.18 [2.74, 7.51]; p < 0.001 |
| Reason | Non-overlap of marginal intervals is not a test of a difference; the contrast must be bootstrapped directly |
| Support | `results/e5e_region_contrasts_100m.csv` |

### C3. Pair-specificity

| Field | Content |
|---|---|
| Previous | Regional contrast described as a general property of product agreement |
| Revised | Contrast resolved for CMSA–GEODATA (4.18×) and CM-SSM–GEODATA (4.37× [2.64, 9.10]) but absent for CMSA–CM-SSM (0.98 [0.81, 1.19], p = 0.88) |
| Reason | Direct ratios; the old generalisation rested on mislabelled regions and two pairs |
| Support | `results/e5e_region_contrasts_100m.csv` |

### C4. Monte Carlo uncertainty

| Field | Content |
|---|---|
| Previous | Not reported |
| Revised | SD of interval endpoints across 5 seeds = 0.0004–0.0060 IoU units (median 0.0016); seeds 202601–202605; 1,000 replicates each |
| Support | `results/e5e_bootstrap_100m.csv` → `mc_seed_*_std`; `results/e5e_bootstrap_meta.json` |

## D. Checked and unchanged

| Claim | Verification |
|---|---|
| National 2020 areas 571.35 / 519.89 / 593.71 km²; 14.2 % of minimum | `results/area_summary.json`; (593.71 − 519.89)/519.89 = 14.20 % |
| Harmonized 100 m areas 568.98 / 590.79 / 521.23 km² | `e3_spatial_agreement.py` rerun |
| National IoU 0.5395 / 0.4444 / 0.3432 | `e6_agreement_map.py` rerun reproduced exactly |
| Resolution stability ≤0.4 % between 30 and 100 m | `results/iou_dice_2020_multi_res.csv` |
| CM-SSM 148,072 patches | source shapefile record count |
| CMSA 6,474 polygons (2020) | source shapefile after gridcode filter |

## E. Open items (not corrected here)

1. Coverage-normalized IoU restricted to pixels mapped by both products: NOT RUN.
2. No nationally representative GOLD data: accuracy not assessable (E7 BLOCKED).
3. Author affiliation, e-mail, funding, competing interests: BLOCKED pending owner confirmation.
4. Journal-specific data-availability/licence wording: BLOCKED pending owner confirmation.
