# R2 SCIENTIFIC REVIEW — Paper 1: Map Reliability

**Reviewer role:** Senior editor, *International Journal of Digital Earth* / *Estuarine, Coastal and Shelf Science*
**Date:** 2026-11-04
**Manuscript revision:** After R2 scientific corrections, uncertainty quantification (E5c), boundary sensitivity (E5b), full manuscript rewrite
**Acceptance criterion:** Manuscript conclusions must follow from reproducible experiments

---

## Executive verdict

**ACCEPT with minor revisions (pending trivial fixes).** The manuscript now has a fully defensible scientific structure with independent validation of key claims through two new experiments that directly address R1 major weaknesses (M1, M2, M3). The contribution is substantive, methods are rigorous, and findings are scientifically meaningful for coastal monitoring practice.

---

## 1. Strengths of this revision

### S1. Key finding now statistically validated (addresses M2 and M3)
The 3× IoU regional heterogeneity (Bohai/Yellow IoU ≈ 0.14 vs. South China IoU ≈ 0.46) is now confirmed:
- **Boundary sensitivity** (E5b): South/North IoU ratio remains 3.2–3.96× across all reasonable boundary positions (10.75M–11.25M m x-coordinate), only collapsing when boundaries merge ecologically distinct regions. This rules out "arbitrary segmentation" as an alternative explanation.
- **Block bootstrap uncertainty** (E5c): Bohai/Yellow 95% CI [0.078, 0.211] and South China [0.424, 0.487] **do not overlap**. The 3× ratio is statistically meaningful at all reasonable confidence levels.

These two experiments transform the regional heterogeneity finding from "potentially the paper's most interesting contribution" (R1 review) to "a rigorously validated core finding."

### S2. Bootstrap provides critically important context
Only 0.24% of 2km blocks (1,993/835,432) contain any *Spartina* pixel. This quantifies the *effective sample size* problem — the paper has billions of pixels but real information content is ~2,000 independent observations. This is an important methodological contribution that future land-cover agreement studies should cite.

### S3. Processing confound quantified as a cautionary result
The `all_touched=True` rasterization finding (22–29% IoU swing for mixed vector–raster pairs) with accompanying area inflation numbers (+69% CMSA, +107% CM-SSM) is now prominently placed with quantitative context. This is genuinely useful for the field — any paper using IoU/Dice between vector and raster products should report this.

### S4. All R1 major weaknesses explicitly addressed
| R1 Weakness | R2 Mitigation | Status |
|---|---|---|
| M1: No independent validation | Acknowledged and contextualized; bootstrap provides partial interpretation | ACCEPTABLE — limitation stated upfront; paper reframed as "agreement quantification" not "reliability against truth" |
| M2: No uncertainty estimate | E5c bootstrap provides global and per-region CI; effective sample size quantified | COMPLETELY ADDRESSED |
| M3: Subregion definitions unvalidated | E5b boundary sensitivity confirms 3× finding is robust | COMPLETELY ADDRESSED |

### S5. Manuscript structure is now clean and evidence-based
- **23 pages, ~9,500 words** — substantial without padding
- **Zero undefined LaTeX references**
- **Zero residual citation TODO markers** in the scientific body
- **Conclusions** rewritten to cite specific evidence from each experiment
- **Limitations** now specific (7 items, all concrete)
- **Recommendations** now 4 concrete items including the rasterization rule warning
- **Data/Code Availability** complete with actual license info and commit reference

### S6. RQ4 appropriately redesigned (from R1)
No longer attempts cross-product trend validation. Instead focuses on what the data CAN show: hotspot stability (robust), secondary rankings sensitivity (not robust), resource allocation implications (concrete).

---

## 2. Remaining minor issues

### m1. Author affiliation and email are placeholders
`TODO_AFFILIATION, TODO_EMAIL` in author field. Fix before submission.

### m2. CMSA license "under verification" should be explicit
The manuscript says "publication permission is granted for aggregated results" but doesn't specify what that means for supplementary materials or data availability. Consider stating "source geometries available from CAS ICR upon signed agreement."

### m3. GEODATA CRS should be EPSG:2433, not "Krasovsky 1940 Albers"
Check: the manuscript says "Krasovsky 1940 Albers equal-area" but the actual EPSG code is 2433. Not a problem per se but EPSG code is more precise.

### m4. Figures 04a mixing source-reported and harmonized values
This was flagged in R1 and is still present in the figure description. If figure 04a plots source-reported CMSA areas alongside harmonized areas for CM-SSM and GEODATA, this is misleading. Either harmonize all or label each axis clearly.

### m5. No GSHHS coastline mask used for domain definition
Methods says "conservative coastal mask derived from GSHHS Level-1 shoreline" but experiments use "CMSA total_bounds + 10km buffer." These are different definitions. Should reconcile or be explicit that CMSA bounds define the domain.

### m6. `sec:methods-e5` label placement
The label was added to the subsection heading but the subsection doesn't start on the same line as the label in all read paths. Should compile fine now (verified) but worth double-checking the compiled PDF for correct link targets.

---

## 3. Contribution strength

**Strong — SCI Q3/Q4 appropriate.**

The paper makes a substantive contribution because it:
1. Quantifies and validates (via bootstrap + boundary sensitivity) that Chinese *S. alterniflora* products disagree by 3× across coastal subregions
2. Demonstrates that this disagreement structure is NOT an artifact of resolution, grid alignment, coastline buffering, or subregion boundary placement
3. Provides a cautionary result about rasterization rule that benefits all IoU/Dice studies
4. Provides a reproducible protocol and all raw result files

For Q2 journals (RSE, ISPRS), independent ground-truth validation would be required. For Q3 (IJDE, Remote Sensing, STOTEN), the paper is strong.

---

## 4. Reproducibility assessment

**Excellent.**

| Dimension | Status | Notes |
|---|---|---|
| Source data paths | VERIFIED | 3 products, all files accessible |
| Processing scripts | VERIFIED | e3, e4, e5, e5b, e5c, all in experiments/ |
| Result CSVs | VERIFIED | 8 result files in results/ |
| Rasterization parameters | VERIFIED | all_touched=False, nearest-neighbour warp |
| Environment | DOCUMENTED | Python 3.11, geopandas 1.0.1, rasterio 1.4.3 |
| Block size choice | DOCUMENTED | 2km blocks justified |
| Commit reference | VERIFIED | Branch + commit in Conclusions |

---

## 5. Submission readiness

**Submission readiness: 8.5/10 — near ready for IJDE/STOTEN/Remote Sensing.**

To reach 9.5/10 (submission-ready):
1. **m1**: Fill in author affiliation (required for submission)
2. **m2**: Clarify CMSA license language (5 minutes)
3. **m4**: Fix figure 04a caption (recompile figure or clarify description)
4. **m5**: Explicitly state domain definition (1 paragraph change)

These are all minor; the scientific content is ready.

---

*End of R2 review.*
