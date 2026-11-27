# R3.1 — Independent review

**Reviewer role:** independent statistical and geographic audit of the R3.1
revision. Scores below are assigned from the evidence in this repository, not
carried over from R1/R2.
**Date:** 2026-11-05
**Manuscript:** `manuscript/main.tex` (24 pp.)

---

## Summary judgement

The revision repairs the two most serious defects found in R3: (i) a
geographic mislabelling that inverted the regional narrative, and (ii) a
point-estimate/interval mismatch in the bootstrap. Both repairs are
traceable to output files, and the corrected numbers are reproducible. The
paper is materially more honest than the R2 version.

It is **not submission-ready**. The central limitation is unchanged and
unfixable with the current data: the study measures *agreement*, not
*accuracy*, and no nationally representative reference data exist. A second,
newly visible limitation is that the regional analysis is descriptive and
pair-specific, so the paper's most eye-catching number (4.18×) describes
3.4 % of one product's national area.

## Scores (0–10)

| Dimension | Score | Basis |
|---|---|---|
| Scientific validity | 6.0 | Claims now match the computations; still no accuracy assessment |
| Novelty | 5.0 | First systematic three-product comparison for Chinese *S. alterniflora*, but the method is standard IoU/Dice harmonization |
| Experimental completeness | 5.5 | 2020 only; no multi-year overlap; no coverage-normalized IoU; no reference validation |
| Statistical rigour | 7.0 | Same-resolution estimand, block bootstrap, direct contrast inference, Moran's *I*, MC uncertainty reported; exchangeability assumption remains |
| Writing quality | 6.5 | Clear, dense, occasionally repetitive; the correction paragraph is unusually candid and appropriate |
| Figure quality | 5.5 | fig03 is a national-extent map where the signal occupies <1 % of pixels; regional figure is now correct and readable |
| Reproducibility | 7.5 | Scripts, seeds, caches, JSON provenance; `work/` outside git is documented |
| **Overall** | **6.0** | Major revision before external submission |

## Scientific validity

Supported by evidence:

- National 100 m IoU 0.5395 / 0.4444 / 0.3432 with same-resolution CIs.
- Resolution stability ≤0.4 % between 30 and 100 m.
- Areas from audited source files, with harmonized raster areas separately
  reported.
- Regional ordering (Bohai/Yellow > East > South for the GEODATA pairs) with
  a direct-bootstrap ratio of 4.18 [2.74, 7.51].
- Pair-specificity of the regional contrast.

Not supported / must stay out:

- Any statement that one product is more *accurate*.
- Any causal ecological explanation of the regional differences (sediment,
  tidal range, management). The manuscript correctly declines this.
- Any generalisation of the 4.18× contrast to "regional context modulates
  agreement" across products.
- Any claim that boundary-shift robustness validates the regionalisation.

## Novelty

The contribution is a reproducible harmonization and comparison protocol plus
an uncertainty quantification, not a new method or model. For a Q3–Q4 remote
sensing journal this is publishable if the framing is "map reliability audit"
rather than "new mapping product". The paper should not be pitched as
delivering a national consensus map, because it does not.

## Experimental completeness

Gaps that a referee will raise:

1. **No common multi-year window.** CMSA (2017–2021) and GEODATA
   (1990/2000/2015/2020) overlap only in 2020. The trend contrast
   (+4.0 %/yr vs −5.0 %) cannot be attributed to ecological change.
2. **No coverage-normalized IoU.** The limitation is acknowledged but not
   computed; it is cheap to compute and would strengthen the paper.
3. **No accuracy assessment.** Acknowledged; E7 found no GOLD data.
4. **Regional unevenness.** The South China region has 19.27 km² of CMSA area
   and 211–259 informative blocks; conclusions there are necessarily weak.

## Statistical rigour

Improvements verified:

- Point estimate and CI are both at 100 m.
- Resampling unit is a 2 km block; 1/2/5/10 km tested.
- 2,014–2,256 informative blocks out of 837,295 are reported.
- Moran's *I* = 0.31–0.44 at 2 km justifies blocking.
- Contrasts are bootstrapped directly; marginal-CI non-overlap is no longer
  used as a test.
- Five seeds; Monte Carlo SD 0.0004–0.0060.

Remaining concerns:

- The bootstrap assumes blocks are exchangeable within a region. Spatial
  dependence is not fully absorbed; 5–10 km intervals are 1.7–2.4× wider,
  which bounds the optimism.
- The regional ratio CI [2.74, 7.51] is wide; the point value 4.18 should
  always be quoted with it.
- `p < 0.001` is a floor statement from 1,000 replicates, not an exact value.

## Writing and figures

- The correction paragraph in Results-e5 is appropriate and should stay; it
  pre-empts a reader who has seen the earlier version.
- fig03 remains weak: at national extent the mapped area is a thin coastal
  fringe. A zoomed panel (Yangtze delta / Jiangsu) would materially improve it.
  This is a figure-quality issue, not a validity issue.
- fig05_regional_iou is now correct and legible.
- The manuscript still carries `TODO_AFFILIATION`, `TODO_EMAIL` and
  ownership-dependent statements. These are blocked items, not oversights.

## Reproducibility

Good. Every revised number maps to a CSV or JSON under `results/`, and the
scripts that produce them are in `experiments/`. The large raster caches live
outside git and are regenerable. Seeds and replicate counts are recorded.

Weak point: `results/superseded_e5_longitude_bands/` contains the old figures
and CSVs; the README explains them, but a reader must be told explicitly not
to cite them. The manuscript does so once.

## Submission readiness

**Not ready.** Blocking items:

1. Owner confirmation of affiliation, e-mail, funding, competing interests.
2. Decision on whether to compute coverage-normalized IoU (recommended) or
   leave it as an acknowledged gap.
3. Figure 03 improvement (zoom panel) — recommended, not strictly blocking.
4. External co-author / domain-expert read of the regional interpretation.
5. Target-journal selection and reformatting.

Non-blocking but should be fixed: none of the corrected numbers require
further revision; the geographic and bootstrap repairs are complete and
verified.

## Recommendation

**Major revision.** The revision has removed a false geographic claim and a
mismatched statistical pairing, and the manuscript is now internally
consistent. It should not be submitted until the owner-blocked items are
resolved and the figure/multi-year limitations are either addressed or
explicitly accepted by the authors as scope decisions.

Score: **6.0/10** (previous R2 self-assessment of 8.5/10 is not supported by
this audit).
