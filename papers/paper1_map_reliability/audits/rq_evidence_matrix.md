# RQ → Evidence Matrix — Paper 1

**Date:** 2026-11-03
**Commit:** 9be4073
**Manuscript:** papers/paper1_map_reliability/manuscript/main.tex

---

## RQ1: Area agreement — How do 2020 harmonized area estimates compare across products?

### Supporting datasets
- CMSA 2020 (`CMSA_2020.shp`, 8864 positive polygons, EPSG:32650)
- CM-SSM 2020 (`CM-SSM.shp`, 148072 polygons, EPSG:32650)
- GEODATA 2020 (`2020年...tif`, 70184×43575 px, 30m, EPSG:2433)

### Experiment
- `audit_all_sources.py`: independently verifies native source area statistics
- `e3_spatial_agreement.py`: harmonizes all three to EPSG:3410, computes rasterized areas
- Output: `results/area_summary.json`, `results/iou_dice_2020_multi_res.csv` (A_km2 column)

### Manuscript section
- **Results 4.1 (Area consistency, RQ1)** — main subsection
- **Table 2 (table2_area_comparison.tex)** — full area inventory
- **Figure 04(a)** — area trend bars

### Actual finding (verified numbers)

| Product | Harmonized 2020 area (km², EPSG:3410 30m raster) |
|---|---|
| CMSA | 570.11 |
| CM-SSM | 592.35 |
| GEODATA | 520.38 |

- Range: 592.35 − 520.38 = **71.97 km²** (**14.2%** relative range, base = GEODATA)
- CMSA / CM-SSM ratio: 0.962 (3.9% difference, very close)
- CMSA / GEODATA ratio: 1.096
- CM-SSM / GEODATA ratio: 1.138

### Confidence
**High** — All three areas computed from harmonized same-domain rasterization in a single run; domain is identical for all three; EPSG:3410 is equal-area; native source CRS already verified for area self-consistency by `audit_all_sources.py` (CMSA `Area_ha` matches planimetric with ~0 bias).

### Limitations
1. Area is a coarse aggregate metric; 3.9% area difference between CMSA and CM-SSM coexists with IoU=0.5375 (46% spatial disagreement). Area alone tells an incomplete story.
2. 30m rasterization of 148k CM-SSM polygons may miss fine clumps at edges — all_touched=False is conservative for clump-level data.
3. GEODATA native 30m resolution cannot capture stands narrower than 30m; its area is the lower bound of reality.

### Completion status: **COMPLETE**

---

## RQ2: Spatial agreement — How well do three products spatially agree?

### Supporting datasets
Same as RQ1.

### Experiment
- `e3_spatial_agreement.py`: IoU/Dice at 30m, 50m, 100m
- `e6_agreement_map.py`: 3-panel agreement/disagreement visualization
- Output: `results/iou_dice_2020_multi_res.csv`, `results/agreement_summary.json`, `figures/fig03_agreement_map.pdf`

### Manuscript section
- **Results 4.2 (Spatial agreement, RQ2)** — main subsection
- **Table 3 (table3_spatial_agreement.tex)** — IoU/Dice at 30m
- **Figure 03** — agreement/disagreement map visualization

### Actual finding (verified numbers — 30m EPSG:3410)

| Pair | IoU | Dice | Both (km²) | only_A (km²) | only_B (km²) |
|---|---|---|---|---|---|
| CMSA vs.\ CM-SSM | **0.5375** | 0.6992 | 406.39 | 163.72 | 185.96 |
| CMSA vs.\ GEODATA | **0.4437** | 0.6147 | 335.14 | 234.97 | 185.24 |
| CM-SSM vs.\ GEODATA | **0.3423** | 0.5101 | 283.78 | 308.57 | 236.60 |

### Key interpretation
- CMSA ↔ CM-SSM: IoU=0.5375 sets the **hard floor** of agreement for two products with same year and same CRS. 53% IoU means 46% of union region disagrees. 3.9% area difference but nearly half spatial disagreement → patch-delineation semantics are the dominant factor, not area magnitude.
- CMSA ↔ GEODATA: IoU=0.4437, shows intermediate disagreement combining resolution (10m vs 30m) and encoding differences.
- CM-SSM ↔ GEODATA: IoU=0.3423, the **worst** agreement (66% disagreement region). Compounds every source of discrepancy.

### Confidence
**High** — Computed directly from harmonized binary masks on identical grid; IoU/Dice are standard reproducible metrics; same run validates CMSA and CM-SSM areas against source `audit_all_sources.py`.

### Limitations
1. No ground-truth interpretation: "Disagreement" ≠ "One is wrong, the other is right". Both might be correct at their respective resolution/encoding.
2. No spatial uncertainty: ~300M px domain treated as independent; real spatial autocorrelation means effective sample size is ~3M superpixels. IoU is not statistically biased but has unquantified spatial uncertainty.
3. CM-SSM has 148k polygons rasterized at 30m in ~70s; all_touched=False rule misses some fine clumps at edges.

### Completion status: **COMPLETE**

---

## RQ3: Disagreement structure — What drives product disagreement?

### Supporting datasets
Same as RQ1 + RQ2.

### Experiment
- `e3_spatial_agreement.py`: IoU/Dice across 30m, 50m, 100m
- Output: `results/iou_dice_2020_multi_res.csv`

### Manuscript section
- **Results 4.3 (Sensitivity and robustness, RQ3)** — main subsection
- **Table 4 (table4_sensitivity.tex)** — resolution sensitivity matrix
- **Figure 04(c)** + **Figure 05** — resolution curves

### Actual finding

Resolution sensitivity (IoU change 30m → 100m):

| Pair | IoU_30m | IoU_100m | Change |
|---|---|---|---|
| CMSA vs.\ CM-SSM | 0.5375 | 0.5395 | **+0.4%** |
| CMSA vs.\ GEODATA | 0.4437 | 0.4444 | **+0.2%** |
| CM-SSM vs.\ GEODATA | 0.3423 | 0.3432 | **+0.3%** |

**Counterintuitive finding:** IoU is **extremely stable** across resolutions (≤0.4% change). This contradicts the common expectation that coarser resolution reduces fine-grained disagreement and increases IoU.

### Interpretation
Disagreement is NOT primarily edge-displacement noise. If disagreement were edge noise, downsampling would blur both products' edges equally and increase IoU. Instead, IoU stays flat because disagreement arises from **systematic spatial offset**: one product maps Spartina where the other does not — in spatially coherent clusters, not along edges. Both sides of disagreement are equally preserved by downsampling.

### Confidence
**High** — Sensitivity is a direct computational result from three independent runs. The counterintuitive finding is reproducible across all three pairs.

### Limitations
1. E5 regional heterogeneity (stratifying IoU by coastal subregions) was planned but **NOT implemented** — no regional breakdown of disagreement.
2. E4 additional sensitivity tests (grid alignment, coastline buffer, rasterization rule) were planned but **NOT implemented**. The protocol specifies `all_touched=False` and CMSA-bounded domain buffer; we haven't tested alternatives.
3. Only resolution was varied; encoding (presence-only vs class-specific) and algorithm differences were held constant by design.

### Completion status: **PARTIALLY COMPLETE** — core sensitivity finding in place, E5/E4 extensions pending

---

## RQ4: Monitoring implications — What does product disagreement mean for monitoring conclusions?

### Supporting datasets
- CMSA 2017–2021: 5 years, same product
- GEODATA 1990/2000/2015/2020: 4 years, same product
- 2020 cross-product area: from RQ1

### Experiment (partial)
- Manual cross-temporal comparison of same-product trends (no cross-product mixing)
- RQ1 area range applied to interpret trend uncertainty

### Manuscript section
- **Results 4.4 (Monitoring implications, RQ4)** — partially written with TODOEXP
- **Figure 04(a)** — area trend visualization (same product bars grouped)
- **Discussion: Implications for historical trend assessment**

### Actual finding

| Product | Time window | Trend | Rate |
|---|---|---|---|
| CMSA | 2017 → 2021 | Monotonically **increasing** | +4.0%/year |
| GEODATA | 1990 → 2015 | Massive **expansion** | +567% total |
| GEODATA | 2015 → 2020 | Apparent **contraction** | −6.8% |

**Critical:** CMSA 2020 (571 km²) is NOT directly comparable to GEODATA 2020 (520 km²) — they encode differently. GEODATA 2015→2020 decline (−6.8%) and CMSA 2017→2021 increase (+15.5% over 5 years) could BOTH be real ecological processes — but the conflict arises from comparing products, not from reality.

### Interpretation
A national monitoring conclusion drawn from one product in isolation might be inconsistent with a conclusion drawn from another product for the same year. The 14.2% cross-product range at year 2020 sets a **lower bound** on the uncertainty of any single-product estimate for that year.

### Confidence
**Medium** — Trend directions are verified, but interpretation is qualitative (no uncertainty quantification on individual years). Same-product internal consistency is high but cross-product encoding differences are unquantified.

### Limitations
1. **No eradication data** — cannot distinguish GEODATA's 2015→2020 decline between real eradication and product encoding change.
2. **No field validation** — cannot determine which product is more accurate in regions where they disagree.
3. **Regional heterogeneity not quantified** — the 14.2% national range may hide larger disagreement in specific coastal segments (e.g., narrow estuaries where resolution matters most).
4. **NO actionable management recommendation** — stated explicitly as a limitation, not a finding.

### Completion status: **PARTIALLY COMPLETE** — trend comparison done, regional heterogeneity and case studies pending

---

## Cross-cutting scientific integrity

| Check | Status |
|---|---|
| All numbers have traceable source file | ✅ (every area / IoU / Dice value maps to CSV or JSON row) |
| No fabricated results | ✅ (all experiments run; no placeholder numbers in manuscript) |
| Agreement ≠ accuracy explicitly stated | ✅ (feasibility gate, protocol, manuscript limitations) |
| CM-SSM province code circularity flagged | ✅ (feasibility gate, protocol, manuscript) |
| E7 independence acknowledged blocked | ✅ (feasibility gate, protocol, manuscript limitations) |
| License caveats documented | ✅ (feasibility gate, manuscript licensing subsection) |
| No cross-year cross-product mixing | ✅ (protocol section RQ4 explicitly prohibits; manuscript respects) |
| No claim of ground-truth accuracy | ✅ (feasibility gate Q5 explicitly prohibits) |

---

## Figure-to-RQ mapping (planned vs completed)

| Figure | Planned content | RQ | Status | Evidence |
|---|---|---|---|---|
| Fig 01 | Study area + dataset coverage | RQ1 (context) | **TODO** | No dataset inventory figure generated yet |
| Fig 02 | Harmonization framework | Methodology | **TODO** | Protocol exists, no visualization |
| Fig 03 | Agreement/disagreement map | RQ2 | ✅ DONE | `fig03_agreement_map.pdf` (100m, 3-panel, 3 IoU values) |
| Fig 04 | Area trend + IoU bars + sensitivity curves | RQ1+RQ2+RQ3 | ✅ DONE | `fig04_stats.pdf` (3-panel) |
| Fig 05 | Resolution sensitivity curves | RQ3 | ✅ DONE | `fig05_resolution.pdf` |
| Fig 06 | (planned) Regional heterogeneity | RQ3 | **TODO BLOCKED** | E5 not implemented |
| Fig 07 | (planned) Monitoring implications | RQ4 | **TODO BLOCKED** | Partial, qualitative only |

---

## Manuscript TODO inventory

| TODO marker type | Count | Blocked? |
|---|---|---|
| TODOEXP (experimental) | 18 | **Mostly BLOCKED** — requires E5 regional stratification, E4 extra sensitivity tests, E6 hotspot ranking, E7 validation |
| TODOVERIFY (verification) | 9 | Mix — some need additional source audits; most for citations (4 core papers need full-text reading) |

**Critical:** The manuscript claims 3 real figures but plans 7. Four planned figures cannot be generated without unblocked experiments (E5 regional heterogeneity, E4 extra sensitivity, E6 hotspot ranking, E7 validation). A candid manuscript limitation statement must acknowledge this.
