# R1 SCIENTIFIC REVIEW — Paper 1: Map Reliability

**Reviewer role:** Senior editor, *Remote Sensing of Environment* / *ISPRS Journal of Photogrammetry and Remote Sensing*  
**Date:** 2025-11-03  
**Manuscript revision:** After P1 scientific corrections, E4 extended robustness, E5 regional heterogeneity, RQ4 redesign  
**Acceptance criterion:** Manuscript conclusions must follow from reproducible experiments

---

## Executive verdict

**MAJOR REVISION** — The manuscript has materially improved after the scientific corrections and now adheres to basic evidence-based writing. However, three structural weaknesses remain that would prevent acceptance at RSE/ISPRS-level journals. These are listed in the major weaknesses below.

---

## 1. Major scientific weaknesses

### M1. Absence of independent validation — fundamental limitation acknowledged but insufficiently mitigated

The manuscript correctly states that all reported metrics measure *inter-product agreement*, not accuracy. However, it makes no attempt whatsoever at partial mitigation:

- No regional field survey synthesis (even published 2017-2020 field plots could narrow down which product is closer to ground truth in one or two pilot regions).
- No comparison with any third-party reference (e.g., *Spartina* occurrence records from the Global Biodiversity Information Facility, or published provincial survey maps from Jiangsu/Zhejiang coastal management agencies).
- The Discussion's recommendation that "independent GOLD reference datasets should be curated" is a correct observation, but leaves the manuscript without any anchor for *interpretation* of the IoU values. Readers cannot distinguish "both products are wrong in the same way" from "both products are independently accurate."

**Severity:** High. A review paper that only measures inter-product agreement, with no ground-truth contact, is fundamentally descriptive rather than diagnostic. The paper's title promises "Reliability" — reliability is relative to ground truth, not to sibling products.

**Mitigation path:** Add E7 (independent validation feasibility) as a genuine empirical section, even if the result is "we found N=0 usable reference sites" or "we found 5 usable 2018 field plots in Jiangsu province — here's how CMSA/GEODATA/CM-SSM perform on them."

### M2. Spatial autocorrelation and effective sample size not addressed

All IoU/Dice values are computed on ~15K × 22K = 335M pixels (100 m harmonized grid) or ~50K × 74K = 3.7B pixels (30 m). Each pixel is treated as an independent observation. The manuscript acknowledges this in Limitations ("Spatial autocorrelation in agreement metrics is not addressed") but does not quantify its magnitude.

Given that *Spartina* patches form spatially coherent stands of 10^2--10^4 contiguous pixels, the effective sample size is more like 100--1000 independent patch observations, not 3.35 billion. The reported IoU = 0.5375 for CMSA--CM-SSM has no uncertainty estimate — with the actual effective sample size, the uncertainty could be substantial.

**Severity:** Medium-High. Without uncertainty quantification, readers cannot tell whether the reported regional IoU variation (0.14 to 0.46) is statistically meaningful or consistent with noise.

**Mitigation path:** Apply Moran's I or a simple patch-level bootstrap to estimate IoU uncertainty. This is computationally tractable.

### M3. Subregion definitions are unvalidated

The three subregions (Bohai/Yellow, East China, South China) are defined purely as x-coordinate bands in EPSG:3410. The Bohai_focus subregion was dropped because it contains zero *Spartina* pixels (expected — Bohai *Spartina* is restricted to southern Yellow Sea shores, not the Bohai Sea itself).

The manuscript acknowledges this limitation. However:
- No experiment tests sensitivity to subregion boundary placement (e.g., shift boundaries by ±500 km and re-run IoU).
- The subregions mix ecological units (Bohai is temperate mudflat, Yellow is subtropical estuary) with arbitrary coordinate cuts (East China Sea is a single longitude band covering both Yangtze River delta and Zhejiang rocky coast, which are ecologically very different).
- The East China region shows the most puzzling IoU pattern (CMSA-CMSSM IoU = 0.3436, which is lower than Bohai, despite East China having higher *Spartina* density). This is not discussed.

**Severity:** Medium. The regional heterogeneity finding (3× IoU range) is potentially the paper's most interesting contribution, but readers cannot assess its robustness to boundary choices.

**Mitigation path:** Run a simple boundary sensitivity test (shift x = 11M boundary to 10.75M and 11.25M, re-run IoU). If the 3× range persists, the finding is robust.

---

## 2. Minor technical weaknesses

### m1. No experiment provenance table
The manuscript has 7 experiments (E1-E7) plus the resolution sensitivity, regional heterogeneity, and robustness extensions. None are recorded with run_id, git commit, data version, or environment hash. AGENTS.md §6 requires this.

### m2. Common domain not precisely defined
The manuscript says "CMSA bounds + 10 km buffer" but does not report the exact bbox coordinates. The Methods section cites a "conservative coastal mask derived from GSHHS Level-1 shoreline" but the experiments use CMSA total_bounds instead. These are two different domain definitions that should be reconciled.

### m3. GEODATA encoding caveat insufficiently emphasized
GEODATA is presence-only (Value=1, NoData=255, no explicit absence). The IoU metric treats NoData pixels as non-positive (False in logical OR/AND), which is technically correct but subtly misleading. Readers may assume IoU is computed over the entire coastal domain, when it is in fact computed over a masked domain where GEODATA has valid pixels.

### m4. Harmonization target CRS choice undefended
EPSG:3410 (North America Albers Equal-Area Conic) is designed for North America, not China. The distortion for China (19°N-41°N) is negligible, but the manuscript does not justify the choice over a China-specific equal-area projection (e.g., EPSG:2433, the native GEODATA projection).

### m5. Rasterization asymmetry not quantified
The all_touched robustness test shows that vector rasterization rule is a dominant confound, but the manuscript does not report how *all_touched=False* vs *True* affects the total area of CMSA and CM-SSM. The CSV shows CMSA goes from 571.63 km² to 966.97 km² (+69%) — this massive area inflation should be highlighted as a warning for all studies using all_touched=True on sparse vector data.

### m6. Figure 04 (panel a) mixes source-reported and harmonized values
Figure 04a plots CMSA 2017-2021 source-reported annual areas alongside CM-SSM 2020 source-reported and GEODATA source-reported years. The y-axis label says "Area (km²)" but these are from different projections and different harmonization states. The figure caption partially acknowledges this but the visual mixing is misleading.

### m7. No English check
Multiple sentences have awkward phrasing. Example (Discussion): "The resolution gap (30 m vs. 10 m vs. sub-meter) almost certainly explains..." — this is now fixed to "A priori, the resolution gap is a candidate explanation..." but other passive constructions and comma splices remain.

---

## 3. Unsupported claims audit (post-correction)

| # | Original claim | Status after R1 correction | Residual risk |
|---|---|---|---|
| 1 | Resolution is dominant cause of GEODATA-CMSA differences | Removed from Conclusions, qualified throughout | LOW |
| 2 | "Hard floor" IoU = 0.5375 | Replaced with "highest observed IoU among pairs" | LOW |
| 3 | Thematic encoding confirmed as causal | Now says "ruling out edge noise; specific drivers undetermined" | LOW |
| 4 | GEODATA and CMSA trends establish contradictory ecological history | Replaced with "within-product trajectories with no overlapping years" | LOW |
| 5 | "First systematic" comparison | Replaced with "complementing prior work" | LOW |
| 6 | 14.2% formula explicit | Verified: (593.71-519.89)/519.89 × 100 | LOW |
| 7 | Distinguishes source vs harmonized areas | Now explicit in Abstract | LOW |
| 8 | 46.2% precise statement | "46.2% of the union area (756.07 km²) was not co-identified" | LOW |
| 9 | Three independent products | Justified via different groups/sensors/methods; citation to feasibility gate | MEDIUM — citations are TODO placeholders |
| 10 | Code publicly released | Git URL + branch + commit added to Conclusions | MEDIUM — repository access not verified |

**Overall:** The 10 mandatory corrections from P1 are now in place. The two residual risks (#9, #10) are documented and acknowledged. No scientific overclaims remain in Results, Discussion, or Conclusions sections.

---

## 4. Missing experiments

| Experiment | Status | Impact on conclusion | Priority |
|---|---|---|---|
| E7 Independent validation | NOT RUN | Blocks interpretation of IoU values | **CRITICAL** |
| Patch-level bootstrap for IoU uncertainty | NOT RUN | Blocks regional heterogeneity interpretation | HIGH |
| Subregion boundary sensitivity | NOT RUN | Moderate — finding is strong enough to survive review even without this | MEDIUM |
| Coastline mask (GSHHS vs CMSA bounds) reconciliation | NOT RUN | Moderate — needs to be documented | MEDIUM |
| Multi-date IoU (CMSA 2017/2018/2019/2021 vs CM-SSM 2020) | NOT RUN | Low — only 2020 CM-SSM exists | LOW (data constraint) |

---

## 5. Strength of novelty

**Medium.** The paper makes a genuine contribution by:
1. Being the first to quantify IoU/Dice disagreement across three independent *Spartina* products in China
2. Demonstrating 3× regional IoU variation (Bohai vs South China)
3. Showing that rasterization rule (all_touched) dominates resolution and grid alignment as a processing confound
4. Providing a fully reproducible workflow with audited source data

However:
- IoU/Dice for land-cover products is well-established methodology (references cited correctly)
- The spatial pattern of agreement is consistent with what would be expected from resolution and patch-size mismatches (no fundamentally new insight)
- The paper would benefit from one genuinely novel methodological angle (e.g., patch-level IoU, or uncertainty propagation through harmonization)

---

## 6. Reproducibility assessment

**Good, with gaps.**

| Dimension | Status | Notes |
|---|---|---|
| Source data paths | VERIFIED | 3 products, full paths in e5_regional_heterogeneity.py |
| Processing scripts | VERIFIED | e3/e4/e5/e6/e7, all in experiments/ |
| Result CSVs | VERIFIED | iou_dice, regional, robustness, agreement_summary, area_summary |
| Common domain definition | PARTIAL | CMSA total_bounds + 10 km; not GSHHS coastline as Methods claim |
| Rasterization parameters | VERIFIED | all_touched=False, merge_algo=first, nearest-neighbour warp |
| Environment | PARTIAL | PROJ_LIB documented, PYTHON path given, but no environment.yml or requirements.txt |
| Run_id/metadata | MISSING | No manifest.json or run.json per AGENTS.md §6 |
| Commit reference | VERIFIED | Conclusions give branch/commit URL |

---

## 7. Data provenance gaps

| Dataset | License | Citation | Verification status |
|---|---|---|---|
| CMSA 2017-2021 | UNVERIFIED | TODO_CMSA_CITATION | CAS ICR — need to confirm redistribution |
| GEODATA 1990-2020 | CC-BY-NC-ND? | TODO_GEODATA_CITATION | IGSNRR — license stated with TODO |
| CM-SSM 2020 | CC-BY-4.0 (Zenodo) / CC-BY-NC-4.0 (mirror) | Xu et al. 2025 ESSD | DOI verified |

The manuscript correctly acknowledges these gaps. Data Availability section is transparent.

---

## 8. Submission-readiness recommendation

**Submission readiness: 6/10 — not yet ready for submission.**

To reach 8/10 (ready for RSE/ISPRS):
1. **CRITICAL:** Complete E7 (independent validation feasibility) — even a "found zero usable sites" result with documented search methodology is essential.
2. **HIGH:** Add patch-level bootstrap IoU uncertainty. This is tractable and adds statistical rigor.
3. **MEDIUM:** Reconcile GSHHS coastline mask vs CMSA bounds domain definition.
4. **MEDIUM:** Run subregion boundary sensitivity test (1 hour compute time).
5. **LOW:** Resolve remaining TODO citations (CMSA, GEODATA).

**If M1 is addressed with even partial validation (e.g., 5 published 2018 field plots in Jiangsu showing CMSA is closer to ground truth than GEODATA), the paper's fundamental weakness is mitigated and it becomes a solid 7.5-8/10.**

**Without M1, the paper is fundamentally descriptive ("here are three products and they disagree") and may not meet RSE's bar for empirical contribution.** Target: ISPRS Journal, Remote Sensing, or *Estuarine, Coastal and Shelf Science* (for which the scope is broader).

---

## 9. What we got right (balance for authors)

To be fair, the revisions addressed genuinely serious problems:

1. **All 10 scientific overclaims corrected.** The manuscript now reads as evidence-based science, not advocacy.
2. **E5 regional heterogeneity analysis.** The 3× IoU regional range is the paper's strongest finding and was not in the original draft.
3. **E4 extended robustness.** The all_touched=True finding is a genuinely novel cautionary result that any paper using IoU/Dice between vector and raster products should cite.
4. **RQ4 properly redesigned.** No longer makes cross-product trend claims. Instead focuses on hotspot stability and monitoring priority sensitivity.
5. **Clean LaTeX compile.** 20 pages, 0 errors, proper bibtex.
6. **Full traceability.** Every result CSV maps to a specific experiment script, which maps to audited source data.

---

*End of review.*
