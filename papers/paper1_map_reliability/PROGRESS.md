# PROGRESS — Paper 1: Multi-Source Spartina alterniflora Map Reliability

**Branch:** `feat/paper1-map-reliability`
**Baseline for this round:** `f2c7368` (R3.1)
**Last updated:** 2026-11-08
**Target journal:** SCI Q3–Q4 (candidate: International Journal of Digital Earth, Remote Sensing)

---

## Current milestone: R4 — regional attribution audit, coverage audit, manuscript revision

R4 audits the two structural vulnerabilities a reviewer would attack first:
the nearest-assignment of 34.4 % of positive pixels to sea regions, and the
implicit "not mapped == absence" assumption. It also upgrades the flagship
figure and refreshes the manuscript to reflect the audited evidence.

### What was done

| Task | Deliverable | Status |
|---|---|---|
| R4-01 attribution audit | `experiments/r4_region_attribution.py`, `experiments/r4_region_assignment_figure.py`; `audits/r4_regional_attribution.md`; `results/r4_region_assignment_sensitivity.csv`, `r4_assignment_distances.csv`, `r4_attribution_meta.json`; `figures/fig_r4_region_assignment.*` | DONE |
| R4-02 coverage audit | `experiments/r4_coverage_agreement.py`; `audits/r4_coverage_audit.md`; `results/r4_coverage_normalized_iou.csv`, `r4_coverage_strips.csv`, `r4_coverage_by_region.csv`, `r4_coverage_meta.json`; `figures/fig_r4_coverage_strips.*` | DONE (verdict: NOT computable; proxies reported) |
| R4-03 South China diagnostics | `experiments/r4_south_china.py`; `audits/r4_south_china_diagnostics.md`; `results/r4_south_china_diagnostics.csv`, `r4_south_china_fragmentation.csv`, `r4_south_china_clusters.csv`; `figures/fig_r4_south_china_zoom.*`, `fig_r4_south_china_overview.*` | DONE |
| R4-04 bootstrap reruns | `experiments/r4_bootstrap.py`; `results/r4_bootstrap_regional.csv`, `r4_region_contrasts_policy.csv`, `r4_bootstrap_meta.json` | DONE (policies A/C5/C10/C20; B = R3.1 run, unchanged estimand) |
| R4-05 manuscript revision | `manuscript/main.tex`; new `tables/tab_region_policy.tex`, `tables/tab_south_china.tex` | DONE |
| R4-06 figure upgrade | `experiments/r4_fig03_upgrade.py`; `figures/fig03_agreement_map.*` (national block-max row + 70 km full-res zoom row) | DONE |
| R4-07 submission audit | `audits/r4_submission_readiness.md` | DONE |
| R4-08 QA + commit | tests, LaTeX build, PROGRESS, commit/push | DONE |

### Key findings

1. **Attribution (R4-01).** 34.42 % of positive-union pixels are
   nearest-assigned; they concentrate in the East China group (22,262 px =
   44.9 % of its union; median 6.83 km, p99 50.4 km). Under policies A /
   C5 / C10 / C20 / B, absolute regional IoUs shift by ≤ 0.05, no region
   rank reverses, and the Bohai/Yellow-over-South-China ratio is 4.06–4.18
   (CMSA–GEODATA) and 4.37–4.64 (CM-SSM–GEODATA); CMSA–CM-SSM stays at
   0.98–1.04.
2. **Coverage (R4-02).** Coverage-normalized IoU is NOT computable: no
   product ships a valid-observation domain (GEODATA is presence-only with
   uniform 255 fill; CMSA/CM-SSM are patch vectors). Proxies: strip-level
   footprint gaps ≤ 0.28 % of any product's positives; but 17.6 % of
   GEODATA positives lie > 5 km from any CM-SSM positive (8.1 % vs CMSA).
   Limitation documented in the manuscript, not masked.
3. **South China (R4-03).** Low IoU = spatial displacement, not omission:
   GEODATA maps the largest South China extent (26.31 km² vs CMSA 19.27,
   CM-SSM 14.69); 40–53 % of disagreement pixels lie within 1 km of the
   other product's positives; 28–44 % lie beyond 5 km; largest single
   disagreement cluster 2.11 km².
4. **Statistics (R4-04).** The 4.18× contrast survives every policy with
   the CI excluding unity: A 4.09 [2.58, 9.80]; C5 4.06 [2.73, 7.07];
   C10 4.12 [2.67, 7.15]; C20 4.15 [2.78, 7.41]; B 4.18 [2.74, 7.51].
   CM-SSM–GEODATA: A 4.64 [2.50, 11.73], C10 4.63 [2.84, 8.62].

### Manuscript status (after R4)

| Metric | Value |
|---|---|
| PDF pages | 30 |
| Sections | 7 (+ R4 methods subsection, 2 R4 results subsubsections) |
| Figures included | 8 (fig03 upgraded; + assignment, coverage strips, South China zoom) |
| Tables included | 8 (+ tab_region_policy, tab_south_china) |
| Undefined references | 0 |
| Residual `TODO_EXPERIMENT` markers | 0 |
| Owner-blocked placeholders | affiliation, e-mail, funding, competing interests |

### Remaining blockers (updated)

1. No GOLD reference data → accuracy not assessable (E7 BLOCKED) — scientific.
2. CMSA license and citation verification; GEODATA license confirmation —
   provider-dependent (see `audits/r4_submission_readiness.md` S3/S4).
3. CM-SSM mirror-side license conflict — owner/provider.
4. Owner-confirmation items: affiliation, e-mail, funding, competing
   interests, journal choice.
5. External domain-expert read of the regional interpretation.

### Verdict

**Not submission-ready.** The science content is now internally audited
(attribution, coverage, diagnostics, statistics) and the manuscript reflects
the corrected evidence; submission remains blocked by license/citation
verification and owner front-matter items.

### Verification record (R4-08)

| Check | Result |
|---|---|
| `pytest tests -q` | 588 passed, 21 skipped, 41 warnings, 90.7 s |
| LaTeX build | `main.pdf`, 30 pages, 0 undefined references, 0 warnings |
| South China rerun | 351.6 s; diagnostics/fragmentation/clusters identical to first run (first rerun had crashed on a dict-key typo; fixed and rerun) |
| Coverage rerun (figure labels) | strip gaps identical (140/0, 0/51, 159/0 px); only the figure legend changed |
| Commits | `3ed17a8` (R4 audits + manuscript) + follow-up commit updating the manuscript Git reference |
| Remote | pushed to `origin/feat/paper1-map-reliability` (not merged to `main`) |

---

## History: R3.1 — geographic correction and statistical recovery (2026-11-05)

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
