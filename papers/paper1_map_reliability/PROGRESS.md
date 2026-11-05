# PROGRESS — Paper 1: Multi-Source Spartina alterniflora Map Reliability

**Branch:** `feat/paper1-map-reliability`
**Baseline for this round:** `da51613` (R2)
**Last updated:** 2026-11-05
**Target journal:** SCI Q3–Q4 (candidate: International Journal of Digital Earth, Remote Sensing)

---

## Current milestone: R3.1 — geographic correction and statistical recovery

R3 was interrupted by the discovery that the E5 regional analysis used
EPSG:3410 x-coordinate bands mislabelled as sea regions. R3.1 supersedes
manuscript polishing and repairs the geography and the statistics first.

### What was found

The old "regions" were meridian slices at x = 11.0 Mm (≈114.2 °E) and
x = 11.5 Mm (≈119.4 °E) in EPSG:3410, whose x axis is linear in longitude.
Worse, the labels were inverted: the band called "Bohai/Yellow Sea" was the
**southern** coast (Guangxi/Hainan/Guangdong, 18.6 km² of CMSA) and the band
called "South China Sea" was the **northern** coast
(Jiangsu/Shanghai/Shandong, 468.7 km²). Every regional statement in R2 was
therefore geographically false.

### What was done

| Task | Deliverable | Status |
|---|---|---|
| T1 preserve evidence | `results/superseded_e5_longitude_bands/` + README | DONE |
| T2 correct regionalisation | `experiments/e5d_geographic_regions.py`; `results/region_definitions_geographic.json` | DONE |
| T3 recompute E5 | `results/regional_geographic_2020.csv`; `results/regional_area_share_geographic_2020.csv`; `results/regional_by_marine_polygon_2020.csv` | DONE |
| T4 repair bootstrap | `experiments/e5e_bootstrap_100m.py`; `results/e5e_bootstrap_100m.csv`; `results/e5e_region_contrasts_100m.csv`; `results/e5e_moran_100m.csv` | DONE |
| T5 repair numbers | `manuscript/main.tex`; ledger in `audits/r3_claim_corrections.md` | DONE |
| T6 update manuscript/figures | `manuscript/main.tex`, `manuscript/main.pdf`, `figures/fig05_regional_iou.*`, `figures/fig03_agreement_map.*` | DONE |
| T7 audit deliverables | 5 audit files (see below) | DONE |
| T8 verify/commit | tests, git commit, push | DONE |

### Corrected regional definitions

Source: Natural Earth 1:10m *geography marine polygons* (v5.1.1, public
domain, IHO-derived).

| Region | Polygons |
|---|---|
| Bohai/Yellow Sea | Bo Hai + Yellow Sea |
| East China Sea | East China Sea + Hangzhou Bay + Taiwan Strait |
| South China Sea | South China Sea + Gulf of Tonkin + Qiongzhou Strait |

Coastal residual: 65.6 % of positive union pixels fall directly inside a
polygon; 34.4 % (31,201 px) are nearest-assigned, max distance 53.97 km.
Admin-1 provinces were tested and rejected (86.0 % of positive pixels outside
the land polygons).

### Corrected numbers (100 m, 2020)

| Region | CMSA–CM-SSM | CMSA–GEODATA | CM-SSM–GEODATA |
|---|---|---|---|
| Bohai/Yellow | 0.4665 | 0.5599 | 0.3646 |
| East China | 0.5902 | 0.3923 | 0.3499 |
| South China | 0.4772 | 0.1341 | 0.0835 |

National (same-resolution 95 % block-bootstrap CI, 2 km, seed 202601):

| Pair | IoU | 95 % CI |
|---|---|---|
| CMSA–CM-SSM | 0.5395 | [0.5096, 0.5708] |
| CMSA–GEODATA | 0.4444 | [0.4128, 0.4733] |
| CM-SSM–GEODATA | 0.3432 | [0.3139, 0.3714] |

**Does the old 3× claim survive?** Not as stated. Direction is reversed
(Bohai/Yellow highest, South China lowest). Magnitude is 4.18×
[2.74, 7.51], p < 0.001 for CMSA–GEODATA and 4.37× [2.64, 9.10] for
CM-SSM–GEODATA, but 0.98× [0.81, 1.19] (p = 0.88) for CMSA–CM-SSM. The
contrast is pair-specific and covers only 3.4 % of CMSA's national area.

### Manuscript status

| Metric | Value |
|---|---|
| PDF pages | 24 |
| Sections | 7 |
| Figures included | 5 |
| Tables included | 6 |
| Undefined references | 0 |
| Residual `TODO_EXPERIMENT` markers | 0 |
| Owner-blocked placeholders | affiliation, e-mail, funding, competing interests |

### Experiments

| Experiment | Script | Output | Status |
|---|---|---|---|
| E1 Harmonization | `e3_spatial_agreement.py` + `protocol.md` | — | DONE |
| E2 Area consistency | `audit_all_sources.py` | `area_summary.json` | VERIFIED |
| E3 Spatial agreement | `e3_spatial_agreement.py` | `iou_dice_2020_multi_res.csv` | VERIFIED (rerun) |
| E3 Agreement map | `e6_agreement_map.py` | `fig03_agreement_map.*` | REGENERATED |
| E4 Resolution / robustness | `e3_spatial_agreement.py`, `e4_robustness_extended.py` | `robustness_2020.csv` | VERIFIED |
| E5 Regional (corrected) | `e5d_geographic_regions.py` | `regional_geographic_2020.csv` | NEW |
| E5 Bootstrap (corrected) | `e5e_bootstrap_100m.py` | `e5e_*.csv/json` | NEW |
| E5 Regional figure | `e5f_regional_figure.py` | `fig05_regional_iou.*` | NEW |
| E5 old band analysis | `e5*.py` (R2) | `superseded_e5_longitude_bands/` | SUPERSEDED |
| E6 Monitoring implications | embedded in Results/RQ4 | manuscript | DESCRIPTIVE |
| E7 GOLD validation | — | `audits/feasibility_gate.md` | BLOCKED (no data) |

### Audit deliverables

| File | Content |
|---|---|
| `audits/r3_geographic_correction.md` | mislabelling evidence, corrected definitions, does the 3× survive |
| `audits/r3_bootstrap_validation.md` | 8-point bootstrap checklist, Moran's I, contrasts, stall diagnosis |
| `audits/r3_claim_corrections.md` | previous → revised → reason → output for every changed number |
| `audits/r3_regional_boundary_validation.md` | perturbation classes, definitions, residual |
| `audits/r3_independent_review.md` | independent scores (6.0/10) and recommendation |

### Remaining blockers

1. No nationally representative GOLD reference data → accuracy is not
   assessable (E7 BLOCKED).
2. Coverage-normalized IoU not computed (acknowledged as a gap).
3. Author affiliation, e-mail, funding, competing interests: owner
   confirmation required.
4. Figure 03 remains a national-extent map where the signal occupies <1 % of
   pixels; a zoom panel is recommended.
5. External domain-expert read of the regional interpretation.

### Verdict

**Not submission-ready.** Geographic interpretation and statistical
uncertainty are now corrected and traceable, but the paper still lacks any
accuracy assessment and has owner-blocked front-matter items.

### Verification record (T8)

| Check | Result |
|---|---|
| `pytest tests -q` (repository suite) | 588 passed, 21 skipped, 41 warnings, 43.7 s |
| E5d rerun on `1c98369` | 249.0 s; all nine regional IoUs and the three national IoUs identical |
| E5e rerun on `1c98369` | 106.7 s, maxrss 3.68 GB; all CIs and contrasts identical |
| E5f rerun | nine bars, 2 km CIs; contrast ratios reproduce the paper's table |
| LaTeX build | `main.pdf`, 24 pages, 0 undefined references |
| Provenance | `region_definitions_geographic.json` and `e5e_bootstrap_meta.json` record `1c98369` |
| Commits | `1c98369` (corrections), `41cba80` (rerun provenance + fig05 fix) |
| Remote | pushed to `origin/feat/paper1-map-reliability` (not merged to `main`) |

---

*Supersedes the 2026-11-04 R2 PROGRESS entry, which recorded the now-retracted
"3× regional heterogeneity" finding as robust and statistically meaningful.*
