# 2020 three-product Spartina label disagreement / scale audit — Issue #18

Status: executed (M0; CPU-only). Companion to
[EXTERNAL_REFERENCE_PRODUCT_2020_STUDY_DESIGN_V1.md](../research/EXTERNAL_REFERENCE_PRODUCT_2020_STUDY_DESIGN_V1.md),
which pre-registered hypotheses H1–H6 before any result was read.

- Run timestamp (support generation): 2026-10-07T17:28:03Z (`work/issue18/transform_manifest.json`); R1 re-run with `--independent-regions`: 2026-10-08
- **Post-decision addendum (2026-10-08, Issue #17):** the executed primary universe remains the 3,011 v1-candidate KEEP cells; the owner-decision v1.1 frozen core has 3,016 KEEP cells. The same bootstrap recomputed on 3,016 cells gives `table15_domain_v1_1_keep_effect.csv` (point shifts ≤0.0003, CI-bound shifts ≤0.0035, no hypothesis-decision change)
- Git commit: v1 `95f31528efa83da8c9858a0e394ecdb74ef6e9a1`; R1 closure `c2da9be` (base `ce34e63`; see v2 `result_manifest.json`)
- Code:
  [run_2020_scale_audit.py](../../scripts/analysis/labels/run_2020_scale_audit.py),
  [scale_agreement.py](../../src/spartina/labels/scale_agreement.py),
  [build_2020_scale_audit_report.py](../../scripts/analysis/labels/build_2020_scale_audit_report.py),
  [build_2020_scale_audit_figures.py](../../scripts/analysis/labels/build_2020_scale_audit_figures.py)
- Machine-readable outputs: `datasets/manifests/2020_label_scale_audit_v2/`
  (`table1..table14`, `hypothesis_evidence_v2.json`, `result_manifest.json`;
  generated 2026-10-08 in the Issue #18 R1 closure). The v1 tables
  (`2020_label_scale_audit_v1/`, `table1..table10`,
  `hypothesis_evidence_v1.json`) are retained unchanged for traceability.
  Bulk per-stripe aggregates under `work/issue18/derived/` (gitignored)
- R1 closure scope: (A) source-independent regional attribution
  (§4a), (B) KEEP_ONLY vs KEEP_PLUS_PROVISIONAL bootstrap sensitivity
  (§4b/§5), (C) H2 wording changed to NOT_SUPPORTED with observed
  direction (§6). National pixel counts, mapped areas, H1/H3/H5/H6
  pixel-level numbers and the full-extent Dice values are unchanged
  (identical rasters; region keying and domain-membership selection do
  not alter them outside explicitly reported tables).

## 1. What this audit is — and the terminology rule

Three independently produced **2020 Spartina alterniflora** map products of
China's coast are compared for pairwise **agreement/disagreement**:

| Tag | Product | Native representation | Role here |
|---|---|---|---|
| GEO | GEODATA 2020 30 m China coastal Spartina distribution dataset | 30 m raster, Krasovsky Albers, uint8 value 1 / nodata 255 | comparison support only |
| CMSA | CMSA_2020 (China mainland 2017–2021 annual Spartina; 2020 layer) | nominal 10 m vector polygons (`gridcode=2`) | external reference candidate |
| CM-SSM | CM-SSM 2020 national sub-metre-mapped vector layer | sub-metre-derived vector polygons | external reference candidate |

No field/UAV/expert-verified labels exist for these products in this
repository (GOLD labels = 0). Therefore **no statement in this audit is an
accuracy statement**: GEO is not ground truth, and disagreement is not error.
Throughout, we use: *agreement / disagreement*, *external-reference
agreement*, *source transfer* (one product's label transferred onto another's
grid), *scale*, *boundary*, and *patch size*. The words "accuracy",
"correct/incorrect mapping", "omission/commission error" are deliberately
not applied to products; "zero-GEODATA fraction" is a literal occupancy
description.

## 2. Provenance and geometry hygiene

Input paths (gitignored data root), checksums, CRS WKT and repair audit are
in `work/issue18/transform_manifest.json` (GEODATA sha256 recorded there).

- CMSA `gridcode=0` features (50) are excluded upstream. Their class meaning
  is **UNKNOWN / TODO_VERIFY**; they were never relabelled as negative.
- Both vector products were repaired on a **derived copy only**; source
  files are untouched. Repair = `GeoDataFrame.make_valid()` (shapely 2 /
  GEOS MakeValid), explode to single parts, drop empty/non-polygonal parts.
  Code asserts the stop condition `|area_change_pct| < 1 %`.

| Product | Features before | Invalid before (self-intersections) | Slivers < 100 m² | Parts after | Invalid after | Dropped | Area change |
|---|---:|---:|---:|---:|---:|---:|---:|
| CMSA gridcode 2 | 8,864 | 499 | 22 | 8,870 | 0 | 0 | 0.0 % |
| CM-SSM 2020 | 148,072 | 2,402 | 100,455 | 148,072 | 0 | 0 | 0.0 % |

Native planar areas (EPSG:32650): CMSA **571.3516 km²**, CM-SSM **593.7098 km²**;
GEODATA native pixel-count area (30 m): **519.8913 km²** (577,657 px).
These reproduce the independently computed intake values exactly, so the
pipeline's inputs are verified against the intake manifest.

## 3. Two comparison supports (and why the pre-registered 5 m lattice was abandoned)

The study design initially proposed a common 5 m fine lattice onto which all
three products would be binary-rasterised, with fractional aggregation to
10/30 m. Executing that design revealed it to be methodologically unsound for
these inputs:

1. GEO exists only at 30 m. Rasterising GEO onto a 5 m lattice would create
   36 binary "5 m pixels" per real observation — a fabricated resolution that
   violates AGENTS.md integrity rule 7 and would make every 5 m cross-product
   comparison circular near boundaries.
2. CMSA is a *nominal* 10 m vector product whose polygon edges inherit the
   10 m source raster topology; a 5 m lattice adds no information.
3. The 5 m lattice is not traceable to any product's native observation
   grid, and the ~2.3 trillion-pixel national grid could only be handled by
   artificial tiling that obscured the scale accounting.

The executed protocol instead uses **two documented, non-fabricated supports**:

- **30 m GEODATA native grid** (Krasovsky Albers, global origin offset
  (−16, −8309), 43,822 × 78,450 px). GEO contributes its native binary
  indicator; each vector product contributes its **exact fractional cover**
  per 30 m pixel (intersection area / 900 m²), plus binary hit masks
  (nearest-neighbour raster reads for GEO; `all_touched=False` centre
  containment for vectors; province LUTs use `all_touched=True` burns).
  All three pairs (GEO–CMSA, GEO–CMSSM, CMSA–CMSSM) are evaluated here.
- **10 m project lattice** (China Albers EPSG:2327-compatible project CRS,
  origin (401,580 m E, 4,533,340 m N), 124,181 × 234,986 px). This is a
  *project comparison lattice*, explicitly **not** declared to be CMSA's
  native pixel grid. Only CMSA vs CM-SSM are compared here (GEO cannot be
  down-transferred without the fabricated upsampling problem).

Tally geometry: 2,048-px block stripes with halos (16 px @30 m; 40 px @10 m)
so 300 m boundary-distance transforms never see block edges; only block
cores are tallied; only blocks intersecting any mapped feature are
processed. Denominator footprint: 319,610,880 30 m pixels
(≈287,650 km² core coverage) and 959,047,680 10 m pixels (≈95,905 km²).

Area transfer check (support total vs native area): GEO 519.4386 km²
(−0.09 %), CMSA 569.6966 km² (−0.29 %), CM-SSM 591.7026 km² (−0.34 %) on
the 30 m support; CMSA 569.6773 / CM-SSM 591.6826 km² on the 10 m lattice.
Small deficits are the expected, documented combination of CRS projection
(UPS/UTM 50N → equal-area) and nearest/centre rasterization; no area is
relabelled.

## 4. Analysis universe, domain cells, and regional attribution

- Spatial accounting and the cluster bootstrap use the W10 coastal cell
  system (`work/national/domain/cells_china_albers_W10000.csv`) with the
  Issue #16 membership registry: 2,752 KEEP_MAINLAND_COASTAL, 259
  KEEP_ISLAND_COASTAL = **3,011 owner-signed KEEP cells (primary R1
  universe)**, plus 10 PROVISIONAL_UNRESOLVED = 3,021 sensitivity
  universe; 298 EXCLUDE_DOMAIN_ARTIFACT cells are outside the analysis
  universe and contain zero processed pixels from any product
  (consistent with the intake finding that mapped positives avoid the
  artifact regions).
- Regional attribution in R1 is **source-independent** (see §4a);
  residual code-0 pixels are called **UNKNOWN** rather than the v1
  product-derived label **UNATTRIBUTED**. Only 1,093 GEO-positive 30 m
  pixels (**0.98 km²**, 0.19 % of 519.44 km²) remain UNKNOWN after
  correction, versus 139,122 pixels (**125.21 km²**) under the v1
  product-derived region burn. UNKNOWN pixels are retained in national
  tallies but excluded from H4, as pre-registered.
- Full-core mapped totals slightly exceed domain-cell totals because blocks
  include mapped patches beyond the 10 km coastline corridor / 25 km island
  reach (e.g. inland estuarine/plantation stands): GEO 33.99 km², CMSA
  39.15 km², CM-SSM 18.71 km² of full-core area lies outside domain cells.
  Table 1 and the national pairwise metrics use the **full product extent**;
  Table 10 and the bootstrap use the **domain-cell universe**. Both
  denominators are labelled on every table.
- The 10 PROVISIONAL cells (owner review pending, see
  [W10_PROVISIONAL_CELL_REVIEW_PACK_V1](data/owner_review/W10_PROVISIONAL_CELL_REVIEW_PACK_V1.md)
  and the owner-decision table
  [w10_owner_decision_table_v1.csv](../data/owner_review/w10_owner_decision_table_v1.csv))
  are excluded from the primary R1 inference; they contain GEO 0.684 /
  CMSA 0.063 / CM-SSM 0.565 km² (6 of 10 cells carry 30 m pixels). Any
  membership finalisation or M1 eligibility decision is deferred to the
  owner (OWNER_SIGNOFF_REQUIRED).

### 4a. R1 independent regional attribution (root cause and algorithm)

**Root cause of the v1 125.21 km² gap.** The v1 region label
(`region_label_block`) was itself *derived from the audited products*:
all-touched raster burns of the CMSA and CM-SSM patch footprints mapped
each patch to a province via patch attributes (CM-SSM native province
with priority), and the GEODATA raster carries no province attribute.
GEO-positive pixels on seaward tidal flats that extend beyond the
fine-polygon footprints therefore received region 0. Both fine
products had zero area in region 0, so the gap was entirely GEO-only
and could not be regionally analysed without circular label-derived
attribution.

**Independent evidence.** Natural Earth 1:10m admin-1 states/provinces
v5.1.1 (`ne_10m_admin_1_states_provinces`, public domain; passport
`docs/audit/source_passports/naturalearth_10m_admin1_states_provinces_5_1_1.json`
with sha256 values), filtered to the same ten coastal provinces used
elsewhere in the project, reprojected to the analysis CRS and dissolved
by province code. No CMSA/CM-SSM/GEODATA label enters the rule.

**Deterministic per-pixel rule** (pixel centroid geometry only):

1. centroid inside exactly one province polygon → that province
   (`CENTROID_IN_PROVINCE`);
2. otherwise nearest province polygon if distance ≤ 25 km (the
   project's existing island reach) **and** the second-nearest
   province is > 300 m farther → that province
   (`NEAREST_PROVINCE_WITHIN_25KM`);
3. otherwise UNKNOWN (`UNKNOWN_OFFSHORE_OR_BORDER_TIE`): beyond reach
   or an inter-province border tie too close to force. Ambiguous
   border pixels are never assigned.

**Result on the 30 m support.** Of 519.44 km² GEO-positive area,
70.21 km² is centroid-in-province and 448.25 km² nearest-province.
Of the 125.21 km² of v1-unattributed GEO pixels, 125.205 km² is now
attributed (Hebei 4.91, Tianjin 0.43, Shandong 16.55, Jiangsu 24.72,
Shanghai 16.20, Zhejiang 36.03, Fujian 8.46, Guangdong 9.02, Guangxi
8.89 km²; table13 crosswalk) and 0.0045 km² (5 pixels) stays UNKNOWN.
The total residual UNKNOWN GEO area is 0.98 km² (1,093 pixels, 0.19 %
of 519.44 km²): 5 pixels from the old gap plus 1,088 pixels that v1
product-derived labels assigned to Jiangsu (524) or Shanghai (564) but
the independent rule leaves as offshore/border-tie UNKNOWN. Net GEO
area by province after all moves is in table11 (e.g. Jiangsu 161.13 vs
136.99 km², Zhejiang 93.85 vs 57.82). Across
all labelled pixels 85.7 % are nearest-province assignments because
most mapped Spartina sits on seaward tidal flats outside the
generalised Natural Earth coastline; the maximum observed centroid
offset offshore is 20.95 km, inside the 25 km reach (diagnostic over
all 577,657 native GEO positives; median 2.62 km). On the 10 m lattice
4.32 km² of labelled footprint (CMSA 1.27 / CM-SSM 4.19 km²) stays
UNKNOWN.

**Cross-validation against v1 product labels** (table13): where both
labellings carry a code, 99.0 % of fine-product pixels agree
(812,922 / 821,043; 98.4 % over all 825,870 fine pixels);
0.98 % move province, concentrated at documented border conventions
(e.g. 5,630 CM-SSM pixels carried product region Shanghai but sit on
the Jiangsu side of the independent border geometry). The independent
labelling is used for all R1 regional tables; the product-derived
tables are retained in tables 11/13 strictly for the before/after
audit.

**Ambiguous boundaries.** The residual UNKNOWN pixels are either
>25 km offshore (none observed for GEO; max 20.95 km) or ≤ 300 m
province-border ties; they are retained as an explicit limitation, not
forced. No province boundary is altered; Natural Earth coastlines are
generalised, so centroid coverage is low by construction and the
25 km nearest rule, not centroid containment, does most of the work.

### 4b. Domain-membership sensitivity

The v1 bootstrap pooled all 3,021 candidate cells although ten cells
had no owner sign-off. R1 recomputes every membership-conditioned
statistic for two explicit variants (table14):
**KEEP_ONLY** (3,011; manuscript primary) and
**KEEP_PLUS_PROVISIONAL** (3,021; sensitivity), via the pure helper
`spartina.labels.scale_agreement.domain_variant_mask`.
Membership status itself is not finalised here.

## 5. Result tables (`datasets/manifests/2020_label_scale_audit_v2/`)

Every table states product A/B, support, semantics (binary indicator vs
exact fractional cover), and the denominator/valid-ignored area.

1. `table1_mapped_area.csv` — native vs per-support areas (above).
2. `table2_pairwise_agreement_by_region.csv` — per region & national
   under the **independent** regional attribution (R1): area A/B,
   intersection, Jaccard, Dice, area bias, binary disagreement
   fraction, denominator pixels.
3. `table3_block_bootstrap_dice.csv` — W10-cell cluster bootstrap for
   **both** domain variants (KEEP_ONLY primary;
   KEEP_PLUS_PROVISIONAL sensitivity).
4. `table4_boundary_distance_disagreement.csv` — disagreement fraction by
   distance to nearest mapped boundary band (region-keyed; pooled
   per-band pixel denominators identical to v1).
5. `table5_patch_size_disagreement_{30m,10m}.csv` — pairwise class grids by
   per-product patch size (`none` = outside that product's patch raster).
6. `table6_patch_omission_by_size.csv` — patch counts, area, median GEO
   fraction, zero-GEO fraction per patch size class, per fine product.
7. `table7_coarse_pixel_occupancy.csv` — GEO=0/1 × fine fractional-cover
   bin contingency over the full 30 m core.
8. `table8_fractional_cover_by_region.csv` — mean binary GEO and mean
   fractional covers per region with per-region pixel denominators.
9. `table9_w10_block_fractional_correlation.csv` — Spearman ρ of W10-cell
   mean covers, both domain variants (occupied cells only; contextual).
10. `table10_domain_accounting.csv` — per membership status: cell counts,
    cells with pixels, per-product area.
11. `table11_region_attribution_comparison.csv` — R1: independent vs
    product-derived regional areas/intersections/Dice per pair, with
    dice deltas (before/after).
12. `table12_region_attribution_method.csv` — attribution-method ledger
    (centroid / nearest≤25 km / UNKNOWN) with pixel counts and areas.
13. `table13_region_crosswalk_validation.csv` — product-region ×
    independent-region crosswalk and fine-pixel agreement counts.
14. `table14_domain_membership_sensitivity.csv` — KEEP_ONLY (3,011) vs
    KEEP_PLUS_PROVISIONAL (3,021) pooled Dice, CIs and Spearman ρ with
    absolute and relative deltas.
15. `table15_domain_v1_1_keep_effect.csv` (+ `table15_note_domain_v1_1.json`)
    — post-owner-decision recompute on the 3,016-cell v1.1 frozen core:
    pooled Dice/CIs, deltas vs the executed 3,011-cell primary, added
    areas, promoted-cell IDs, source checksums (no raster re-export).

Key national results (full product extent, binary indicators):

| Pair (support) | Dice | Jaccard | Area A / B (km²) |
|---|---:|---:|---|
| GEO–CMSA (30 m) | 0.6195 | 0.4487 | 519.44 / 568.30 |
| GEO–CMSSM (30 m) | 0.5225 | 0.3536 | 519.44 / 588.41 |
| CMSA–CMSSM (30 m) | 0.7148 | 0.5562 | 568.30 / 588.41 |
| CMSA–CMSSM (10 m lattice) | 0.7032 | 0.5423 | 569.58 / 591.63 |

Regional Dice spans (independent attribution; UNKNOWN excluded) are
wide — see §6 H4 and table11 for the full before/after comparison.
Under R1 the 30 m CMSA–CMSSM range runs from 0.00 (Liaoning: 1.41 km²
CMSA-only, no CM-SSM) to 0.80 (Tianjin); Shandong shows CMSA 63.87 vs
CM-SSM 17.77 km² and Shanghai the reverse sign (CMSA 116.97 vs CM-SSM
180.69 km²).

Cluster bootstrap (W10 cells as spatial blocks, drawn with replacement
including empty blocks, 500 resamples, seed 20201018, pooled Dice
recomputed per resample as 2ΣI / Σ(A+B), percentile 95 % CI). Primary
universe = 3,011 KEEP cells:

| Pair (support) | Pooled Dice | 95 % CI |
|---|---:|---|
| GEO–CMSA (30 m) | 0.6076 | 0.5507–0.6556 |
| GEO–CMSSM (30 m) | 0.5290 | 0.4631–0.5848 |
| CMSA–CMSSM (30 m) | 0.7217 | 0.6738–0.7629 |
| CMSA–CMSSM (10 m) | 0.7096 | 0.6637–0.7507 |

Sensitivity universe = KEEP plus ten provisional cells (3,021;
identical procedure): 0.6073 [0.5452–0.6570], 0.5293 [0.4696–0.5838],
0.7214 [0.6803–0.7622], 0.7093 [0.6677–0.7490] — the v1 values exactly,
which cross-validates the variant machinery. Absolute differences are
≤ 0.0003 (relative ≤ 0.06 %) for every pooled Dice (table14).

Contextual only (W10-cell means over occupied KEEP cells, 1,869 on
30 m / 1,217 on 10 m; 1,875 / 1,222 in the provisional-inclusive
universe): Spearman ρ GEO–CMSA 0.75, GEO–CMSSM 0.73, CMSA–CMSSM 0.87
(30 m) and 0.86 (10 m); including provisional cells moves ρ by ≤ 0.0008.
Aggregated to 10 km blocks the products rank coastline
segments similarly even where pixel-level Dice is moderate; the ρ is not an
agreement coefficient and is reported separately to avoid scale conflation.

## 6. Hypothesis verdicts (rules fixed before results)

Bin convention: distance and cover bin edges are **right-inclusive** (the
30 m lattice ring at exactly 30 m belongs to 0–30 m; an early run with
left-inclusive edges structurally emptied the near band and was corrected
and rerun before any verdict was read).

- **H1 boundary effect — SUPPORTED.** Rule: for all three pairs,
  disagreement fraction at 0–30 m exceeds that at 120–300 m by > 1.2×.
  Result (near / far, ratio): GEO–CMSA 0.3075 / 0.0400 = 7.69;
  GEO–CMSSM 0.3538 / 0.0603 = 5.87; CMSA–CMSSM 0.2387 / 0.0405 = 5.90
  (10 m lattice CMSA–CMSSM: 0.3048 / 0.0373 = 8.17). Disagreement is
  overwhelmingly a boundary-band phenomenon and decays monotonically
  with distance on both supports.
- **H2 fine-patch-size effect — NOT_SUPPORTED (observed direction
  opposite to the preregistered expectation).**
  Pre-registered rule: CMSA–CMSSM discordance within CM-SSM patches
  < 2,500 m² exceeds that within ≥ 10⁵ m² patches by > 1.2×. Result:
  0.2095 (small) vs 0.3162 (large). The two fine products agree *better*
  inside small patches than inside large continuous meadows, where
  systematic boundary offsets along Jiangsu/Shanghai meadow margins
  dominate. This is a directional non-support statement for one
  conditional estimand, not a claim that patch-size effects are
  universally falsified; the numerical result is reported unchanged.
  **H2 and H3 are not contradictory** because the estimands and
  denominators differ: H2 is an overall CMSA–CMSSM discordance rate
  conditional on CM-SSM patch-size strata (denominator: 300 m band
  pixels per stratum), whereas H3 is the fraction of fine-reference
  patches receiving zero coarse cover (denominator: fine patches).
  Coarse products can omit most small fine patches (H3 supported)
  while the two fine products still agree more where small patches
  occur (H2 not supported).
- **H3 coarse-product small-patch omission — SUPPORTED.** Rule: fraction
  of 100–900 m² fine patches with zero GEO cover exceeds the same fraction
  for ≥ 10⁵ m² patches, for both fine products. CMSA 0.8916 vs 0.1773;
  CM-SSM 0.8648 vs 0.2363. Monotone ordering across all size classes for
  both products (89 % → 81–89 % → 73–81 % → 56–59 % → 18–24 %). This is a
  scale/detection-threshold description, not an accuracy claim about which
  product is right.
- **H4 province/geomorphology interaction — SUPPORTED (R1 independent
  attribution; verdict unchanged).** Rule: regional binary Dice range
  ≥ 0.10 for every pair (UNKNOWN excluded; regions where both products
  have zero extent have no estimable Dice and are omitted).
  Independent ranges: GEO–CMSA 0.752 (0.00 Liaoning–0.75 Jiangsu);
  GEO–CMSSM 0.583 (0.07 Hebei–0.65 Fujian; Liaoning omitted, both
  zero); CMSA–CMSSM 0.798 (0.00 Liaoning–0.80 Tianjin); 10 m
  CMSA–CMSSM 0.775 (0.00–0.78). Product-derived v1 ranges were 0.676,
  0.680, 0.450 and 0.425 over the nine provinces with fine-product
  presence; the wider R1 ranges primarily reflect (i) the formerly
  unattributed 125.21 km² entering provinces with strong GEO presence
  (Jiangsu/Zhejiang) and (ii) Liaoning now appearing as a fine-only
  region with zero GEO cover. The pre-registered threshold is met under
  both labelings; the H4 scientific verdict does not change.
- **H5 area agreement vs patch agreement — SUPPORTED.** Rule: national
  |GEO–CMSA area bias| < 20 % while national binary Dice < 0.70.
  Area bias 8.6 % (full-extent areas on the 30 m support) with Dice 0.6195:
  similar national totals are compatible with only moderate spatial
  agreement — area totals alone must not be used as product-consistency
  evidence.
- **H6 binary labelling hides mixed support — SUPPORTED.** Rule: ≥ 5 % of
  GEO=1 pixels carry < 50 % fine occupancy for both fine products.
  GEO=1 pixels below half fine cover: CMSA 0.3655, CM-SSM 0.4248
  (exact-zero: 0.3152 / 0.3509; strict mixed bins 0.25–0.75: 0.0499 /
  0.0892). Reciprocally, 0.13 % / 0.17 % of GEO=0 pixels have > 50 % fine
  occupancy over a much larger background (≈204k / 250k pixels). Binary
  cross-grading would discard between ~1/3 and ~2/5 of the coarse product's
  spatial support as "disagreement" even though fractional cover is partial
  rather than absent.

## 7. Candidate figures and ranking

All in `docs/analysis/figures/`; ranking criteria fixed at figure
construction: (i) directly visualises a pre-registered hypothesis with
readable effect size; (ii) cannot be misread as an accuracy claim;
(iii) national coverage, not anecdote; (iv) legible in monochrome/print.

1. **Fig C `figC_boundary_distance.png`** — H1 in one panel; monotone
   decay and 6–8× near/far ratios for three pairs on one axis. Recommended
   main-text figure.
2. **Fig E `figE_occupancy.png`** — GEO×fine occupancy contingency (H6);
   makes the mixed-support argument and the scale-mismatch mechanism
   explicit without naming a product correct.
3. **Fig D `figD_patch_size.png`** — H3 monotone zero-GEO fraction by
   patch size, plus the NOT_SUPPORTED H2 direction (opposite to the
   preregistered expectation) visible in the same panel.
4. **Fig B `figB_site_panels.png`** — two 2.4 km × 2.4 km UTM50 local
   panels (continuous-meadow site 975168 E / 3461816 N; fragmented-small
   site 904596 E / 3134916 N; coordinates in `work/issue18/figB_sites.json`)
   showing actual boundary offsets; illustrative only, no population
   inference.
5. **Fig A `figA_mapped_area.png`** — area inventory by product/support;
   useful provenance/QA graphic, weakest inferential content.

## 8. Strongest findings and limitations

Strongest defensible findings:

1. **National area similarity conceals moderate spatial agreement** (H5):
   519.9 vs 571.4 vs 593.7 km² totals with national Dice 0.52–0.71 and
   W10-bootstrap CIs that stay below 0.77 for every pair.
2. **Disagreement is structured, not random**: boundary-concentrated
   (H1, 6–8×), region-dependent (H4, independent-attribution Dice spans
   0.58–0.80 across pairs, including a fine-only Liaoning), and
   scale-dependent (H3, 86–89 % of sub-900 m² fine patches have no coarse
   support vs 18–24 % of ≥ 0.1 km² patches).
3. **Binary transfer discards real information** (H6): 37–42 % of coarse
   positive pixels are partially occupied by fine products; fractional-cover
   transfer is required for any multi-source 2020 training label, and even
   then the products cannot be merged without an explicit conflict rule.
4. One pre-registered prediction (H2) is **NOT_SUPPORTED, with the
   observed direction opposite to the preregistered expectation**;
   large-meadow margins, not small patches, carry the largest fine–fine
   discordance. This is not contradictory with H3 (different estimand
   and denominator; §6).
5. The ten unsigned provisional cells are immaterial to the inference
   but are excluded from the primary result on principle: adding them
   moves every pooled bootstrap Dice by ≤ 0.0003 and every block ρ by
   ≤ 0.0008.

Limitations:

- No GOLD labels: agreement is not correctness; no product is truth.
- Single year (2020); phenology/tide state per source acquisition is not
  modelled here; boundary offsets conflate positional error, acquisition
  date, and ecological change within 2020.
- Regional attribution relies on generalised Natural Earth 10m
  admin-1 coastlines: 85.7 % of labelled pixels are assigned by the
  25 km nearest-province rule rather than centroid containment, and
  0.98 km² of GEO-positive area (0.19 %) plus 4.32 km² of the 10 m
  labelled footprint remain UNKNOWN (offshore or ≤ 300 m border ties);
  a survey-grade coastline could move a small number of near-border
  assignments (99.0 % fine-pixel agreement with the product-derived
  labelling where both exist).
- 10 m lattice is a project lattice, not a reconstructed CMSA native grid;
  CMSA native edge topology cannot be recovered from the vector release.
- Geometry repair audit is area-based; although 0 features were dropped and
  area change is 0.0 %, vertex-level changes from MakeValid are not
  enumerated.
- W10 bootstrap blocks tile the corridor but are arbitrary spatial units;
  CI widths reflect that choice.
- The 10 PROVISIONAL cells remain unresolved pending owner sign-off and
  are excluded from the primary inference (sensitivity quantified,
  table14); SILVER training eligibility of all three products stays a
  recommendation only; the label registry is unchanged.

## 9. What this audit does not authorise

No SILVER admission, no training-label merge rule, no per-product quality
ranking, no use of GEO as validation truth, and no claim about years other
than 2020. Those are M1 decisions requiring GOLD evidence and owner review.
