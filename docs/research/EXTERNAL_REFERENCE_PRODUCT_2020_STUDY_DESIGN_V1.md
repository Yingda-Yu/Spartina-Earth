# Study design — 2020 three-product external-reference comparison (v1)

Status: **DESIGN ONLY — NO EXPERIMENT EXECUTED.** Every outcome stated
here is a hypothesis or plan (`HYPOTHESIS`, `TODO_EXPERIMENT`), never a
result. Written for M2.4 Phase H; companion to
[CHINA_EXTERNAL_LABEL_INTAKE_AUDIT_V1.md](../audit/CHINA_EXTERNAL_LABEL_INTAKE_AUDIT_V1.md).

## 1. Purpose and framing

Three independent published products all claim to depict Spartina
alterniflora across mainland China in roughly 2020, at three different
measurement scales:

1. **CM-SSM 2020** — polygons from 0.9 m Google-Earth RGB plus 10 m
   Sentinel-2 phenological features; OSPPF + Random Forest + manual
   refinement; 593.71 km² measured; reported OA 96.76 %/F1 0.95.
2. **CMSA 2020** — polygons vectorised from a 10 m DeepLabv3+
   Sentinel-2 segmentation (transfer-learned); 571.35 km² positive
   (`gridcode=2`).
3. **GEODATA 2020 30 m** — Landsat-era 30 m binary OBIA mask in
   Krasovsky Albers; 519.89 km².

The scientific objective is **not** to rank products and never to treat
one as ground truth. It is to quantify how scale, geometry type and
pipeline choices propagate into mapped area and spatial configuration,
so that downstream SpartinaFM / Spartina Atlas work can state explicitly
what "a Spartina map at 10 m vs 30 m vs sub-meter" means. All three are
*external reference products*; the only adjudicator is a future GOLD
sample (field/UAV/expert), of which there are currently zero points.

Existing descriptive diagnostics (measured, not experiments): 274 W10
cells contain all three, 103 exactly two, 126 exactly one;
Spearman per-cell area CMSA–CM-SSM = 0.875, GEODATA–CMSA = 0.761,
GEODATA–CM-SSM = 0.747; GEODATA is the sole product in 72/126
single-product cells; polygon/grid allocation numbers are in
`datasets/manifests/china_label_domain_overlap_v1.csv`.

## 2. Core hypotheses (HYPOTHESIS, untested)

* **H1 (scale-driven area bias).** Coarser products systematically
  lose small/linear tidal-creek patches and gain area via boundary
  dilation around big meadows; the net sign is region-dependent.
* **H2 (small-patch loss ordering).** Patch-count and total-area loss
  should follow 0.9 m → 10 m → 30 m monotonically for patches below the
  coarser MMU; the 126 single-product cells and the 103 two-product
  cells are the natural strata for testing this.
* **H3 (boundary-band disagreement).** Most pairwise disagreement lives
  inside a boundary band whose width scales with the coarser product's
  pixel (0/15/30 m bands pre-registered); deep-interior disagreement is
  rare and more likely semantic (mudflat/cloud/phenology confusion).
* **H4 (omission/commission asymmetry).** Relative to the finest
  product, GEODATA will show more omission of narrow fringes and more
  commission at complex boundaries than CMSA; CMSA vs CM-SSM will show
  residual 10 m-scale commission on exposed tidal flats.
* **H5 (province/geomorphology interaction).** Disagreement rates
  differ by coastal stratum (large Jiangsu tidal flats vs narrow
  Zhejiang/Fujian estuarine fringes vs Guangxi mangrove-adjacent
  stands); pooled national numbers will conceal this.
* **H6 (vector artefact control).** Self-intersecting polygons and
  < 100 m² slivers do not materially (>1 %) change any harmonized area
  after documented make-valid handling.

## 3. Harmonization protocol (to be executed later; no results yet)

1. **Common frame.** Reproject all three to the project China Albers
   (`spartina.data.national.geometry.CHINA_ALBERS_CRS`); no product
   stays in its native CRS for comparison. Use nearest-neighbour /
   vector-rasterisation onto pre-registered grids at **5 m** (fine
   reference lattice; 0.9 m polygons rasterised) and resampled 10 m /
   30 m lattices. Never upsample the 30 m product to 10 m and present it
   as 10 m information (AGENTS.md integrity rule 7) — upsampling is an
   interpolation visual only, explicitly labelled.
2. **Fractional-cover representation.** On the common 5 m lattice each
   product contributes a binary indicator; aggregation to 30/100 m
   produces *fractional cover* in [0,1] per product. Comparisons use
   fractional differences and pre-registered cover bins
   (0, (0,0.25], (0.25,0.5], (0.5,0.75], (0.75,1), 1), never forced
   binary cross-grading.
3. **Pure vs mixed pixels.** Report pure-pixel agreement (both ends)
   separately from mixed-pixel behaviour; a 30 m pixel is "mixed" if
   the 5 m lattice fraction is strictly inside (0,1).
4. **Boundary bands.** Erode/dilate each product's mask by 0/15/30/60 m;
   classify every disagreement cell as interior-of-both, boundary-band,
   or interior-of-one (candidate omission/commission).
5. **Geometry hygiene.** Fix self-intersections with a documented
   make-valid step (`buffer(0)`/`make_valid`) and log area delta; retain
   or drop < 100 m² features as a sensitivity arm; CMSA `gridcode=0`
   features stay excluded until producers clarify semantics.
6. **Geographic strata.** Province-level (9-province polygon embedded
   in CM-SSM) and geomorphic strata (open tidal flat / estuary /
   mangrove-adjacent / artificial coast), plus the v1 W10
   KEEP/PROVISIONAL membership tokens; no spatial random scattering
   (grouped, buffered units per the no-leakage rule).
7. **Temporal alignment.** Treat all three as nominal-2020 with
   documented windows; CM-SSM explicitly uses 2019/2021 Google-Earth
   fallback where 2020 imagery failed. Label this as an uncertainty
   source; quantify it only if fallback extents can be reconstructed
   (`TODO_VERIFY`).

## 4. Metrics to report (TODO_EXPERIMENT)

* Fractional-cover distributions per product and per bin; area after
  harmonization (with and without boundary bands).
* Pairwise cell-level presence Jaccard, area ratio, Spearman (current
  descriptive ρ values listed above are not these results).
* Omission/commission area in boundary bands vs deep interiors, by
  stratum.
* Patch-size spectra (log bins) and minimum-mappable-patch curves at
  each scale.
* Sensitivity table: make-valid handling, sliver threshold, lattice
  choice, CRS, and PROVISIONAL-cell inclusion — each with its area
  delta.
* Optional HYPOTHESIS-only triangulation against Sentinel-2 / GE
  imagery and, only if acquired, a stratified GOLD sample; without GOLD
  the output is a *disagreement characterisation*, not an accuracy
  statement.

## 5. Explicit prohibitions

* No product is "ground truth" or "reference truth"; language must be
  "external reference product" / "agreement" / "disagreement".
* No nationwide change or expansion claim from cross-product
  disagreement; cross-product differences measure scale/pipeline
  effects in this study.
* No numbers published unless the experiment actually runs
  (`TODO_EXPERIMENT` markers until then).
* No redistribution of GEODATA pixels or CM-SSM bytes; outputs are
  fractional/statistical aggregates within the project license
  envelope, never reconstructed source rasters.
