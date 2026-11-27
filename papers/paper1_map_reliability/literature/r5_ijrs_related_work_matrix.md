# R5-05 — IJRS Related-Work Matrix and Bibliography Verification Record

**Manuscript:** Spatial Agreement and Regional Uncertainty in Multi-Source
Maps of *Spartina alterniflora* along the Chinese Coast
**Verification date:** 2026-11-08, against CrossRef / doi.org / publisher pages

---

## 1. Bibliography verification outcome (integrity record)

A full verification pass of `manuscript/references.bib` found that 12 of the
17 scholarly entries carried in earlier drafts were **unverifiable** — with
unregistered DOIs or DOIs resolving to unrelated papers (hallmarks of
fabricated references). Per the repository's no-fabrication rules these were
**removed or replaced**. The final bibliography contains 17 entries, all
either verified against the publisher of record or explicitly marked as
institutional dataset releases pending owner confirmation:

- Verified and corrected in place: li_2009_spartina (Ecological Engineering
  35:511–520, DOI 10.1016/j.ecoleng.2008.05.013), zhou_2025_cmssm (ESSD
  17:6601–6620), wang_2024_ijde, zhao_2023_rs, xu_2024_rse (RSE 311:114316),
  ximenes_2023_stoten (STOTEN 860:160380), wessel_1996_gshhs (correct DOI
  10.1029/96JB00104), olofsson_2014_area_bias (added 6th author Wulder),
  cma_2021_eradication (corrected to the real five-ministry joint notice of
  March 2023).
- Newly added, verified: li_2024_cmsa (the CMSA production paper, published
  in IJRS itself), zhang_2023_jag, li_2022_jem, zhao_2023_rse_saltmarsh,
  zhou_2024_ijde_beibu, ding_2022_rs, zhang_2023_gwlfcs30.
- Placeholders retained with TODO notes (owner must confirm before
  submission): cmsa_2024_release, geodata_time_series.
- Removed as unverifiable: an_1985_spartina, zhou_2009_invasive (broken
  title), huang_2017_china_spartina, liu_2020_spartina,
  ren_2022_spartina_dynamics, zhao_2021_spartina, morton_2020_mangrove,
  he_2016_spartina_traits, chen_2020_yellow_sea, foody_2020_map_quality,
  stehman_2010_sampling, karra_2021_worldcover, zanaga_2022_worldcover21,
  bunting_2022_frome (last two were never cited in the manuscript text).

## 2. Related-work matrix

How this study differs from prior multi-source land-cover agreement and
wetland mapping studies. No priority claims are made; the CM-SSM data paper's
own two-product benchmark is explicitly acknowledged in the manuscript.

| Study | Venue (year) | Scope / method | Key difference from our study |
|---|---|---|---|
| Li et al. 2024 (CMSA production) | **IJRS** (2024) | DeepLabv3+ + spectral-phenological features on Sentinel-2; annual 10 m national maps 2017–2021; classification-accuracy focus | We treat CMSA as one of three compared products and quantify its *disagreement* with independent products, not its classification accuracy |
| Zhou et al. 2025 (CM-SSM) | ESSD (2025) | Sub-meter clump mapping 2020; benchmarks CM-SSM against **CMSA only** | We perform the three-way comparison with formal IoU/Dice, spatial block-bootstrap CIs, regional stratification and processing sensitivity; we add the 30 m GEODATA lineage and geographic attribution policies |
| Zhang et al. 2023 | JAG (2023) | Landsat phenology-based annual national *S. alterniflora* maps 1985–2020 (production study) | We do not produce a new map; we audit agreement among existing independent products, which their production paper assumes away |
| Li et al. 2022 | J. Environ. Manage. (2022) | Object-based SVM national maps 2015/2018/2020; control-effectiveness assessment | We show how product disagreement propagates uncertainty into exactly such national control assessments |
| Zhao et al. 2023 | RSE (2023) | Dual-temporal salt marsh mapping methodology (China case) | Method-development study; ours is a product-level comparison without new classification |
| Zhou et al. 2024 | Int. J. Digital Earth (2024) | Sub-meter *S. alterniflora* mapping in the Beibu Gulf (CM-SSM precursor) | Regional precursor; we scale the sub-meter-vs-10 m contrast nationally across three products |
| Wang et al. 2024 | Int. J. Digital Earth (2024) | Six global 10–30 m land-cover products over China: spatial/area consistency + accuracy | General land-cover classes with validation data; ours is single-species, mixed vector/raster, no reference data, region-stratified (IHO sea regions) |
| Zhao et al. 2023 | Remote Sensing (2023) | Stratified-random-sample validation of six fine-resolution GLC products | Accuracy-oriented with a validation sample; we compute inter-product agreement with uncertainty quantification because no reference sample exists |
| Xu et al. 2024 | RSE (2024) | Comparative validation of recent 10 m global land-cover maps | Same contrast: validation-with-reference vs our agreement-without-reference framing |
| Ding et al. 2022 | Remote Sensing (2022) | Field-data-aided comparison of three 10 m LC products (SE Asia) | Field-aided; our setting has no field truth, so agreement metrics carry the inference and their limits are stated |
| Zhang et al. 2023 (GWL_FCS30) | ESSD (2023) | Global 30 m wetland map; cross-comparison against prior global wetland maps | Wetland-class map production + comparison; ours is species-level, national, with geographic heterogeneity and attribution-sensitivity analysis |
| Ximenes et al. 2023 | STOTEN (2023) | Global mangrove map comparison at poleward range limits | Coastal-vegetation map comparison at biome scale; we work at national species level with regional stratification |
| Lothspeich et al. 2026 | **IJRS** (2026) | Multiscale accuracy assessment of waterbody products vs reference data | Accuracy assessment with reference data; ours is agreement-only — we quantify what can and cannot be concluded without a reference |
| Xu et al. 2026 | **IJRS** (2026) | Removal-effectiveness monitoring at Yancheng using multi-source time series | Site-scale removal detection with validation; ours is national multi-product reliability |
| Bian et al. 2025 | **IJRS** (2025) | SAR coherence+intensity plant classification, Yancheng wetland | Single-site classifier development; ours compares finished national products |

## 3. Positioning statement (reflected in the manuscript)

1. Prior *Spartina* studies produce maps or assess control effectiveness; the
   CM-SSM data paper itself benchmarks only CM-SSM vs CMSA. No prior study
   compares all three national products, and none quantifies regional
   disagreement heterogeneity with formal uncertainty under multiple
   geographic-attribution policies.
2. Prior land-cover comparison studies rely on reference/validation samples
   (OA/PA/UA/Kappa). We provide the agreement-without-reference analysis
   with IoU/Dice + spatial block bootstrap, and an explicit statement of what
   this cannot establish (absolute accuracy).
3. The CMSA production paper was published in IJRS, and IJRS has recently
   published both product-accuracy and coastal-wetland studies — the
   manuscript's product-reliability framing fits the journal's demonstrated
   scope. (Stated as journal fit, not as a novelty claim.)
