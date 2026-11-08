# PROGRESS — Paper 1: Multi-Source Spartina alterniflora Map Reliability

**Branch:** `feat/paper1-map-reliability`
**Baseline for this round:** `e963b4a` (R5)
**Last updated:** 2026-11-09
**Publication route:** **EarthArXiv public preprint** (owner-directed R6
change); IJRS remains the recorded secondary possibility for later journal
submission.

---

## Current milestone: R6 — EarthArXiv preprint finalization

### What was done

| Task | Deliverable | Status |
|---|---|---|
| R6-01 baseline | HEAD `e963b4a`, in sync; one benign pre-existing line in `submission/ijrs/latex_source/main.tex` (Git-ref update) committed with R6 | DONE |
| R6-02 authorship | single author confirmed via git co-author check; Spartina Technology legal name remains TODO_VERIFY | DONE |
| R6-03 integrity audit | `audits/r6_scientific_integrity.md`; all primary numbers PASS vs committed artifacts; **one error fixed** (East China >50 km pixels 478→237) | DONE |
| R6-04 cartography | full redesign via `experiments/r6_cartography.py` design system; new Fig 1 (study area), rebuilt fig03 (NE basemap + enlargements), South China zoom, assignment figure, restyled coverage strips; `audits/r6_cartographic_qa.md` incl. §0.1 correction of a **metre-vs-km basemap rendering bug** (land layer invisible in all map figures; found, fixed, all figures regenerated + pixel/visual re-verified) | DONE |
| R6-05 manuscript repositioning | preprint author block/date; contributions rewritten C1–C3; 3 new Crossref-verified refs (20 total); Figure 1 inserted; 3 captions rewritten; CMSA producer corrected to Capital Normal University (was wrongly "CAS Institute of Coastal Research" — contradicted by Crossref); back-matter integrity fixes (funding claim removed, honest COI + AI-use statements); 35 pp, 0 undefined refs | DONE |
| R6-06 EarthArXiv requirements | `audits/r6_eartharxiv_requirements.md` (live check 2026-11-08, Moderation Policy v2.9) | DONE |
| R6-07 licensing/ESG | `audits/r6_data_licensing.md` — five-permission-tier matrix for CMSA/GEODATA/CM-SSM/Natural Earth; no restricted bytes in any deliverable | DONE |
| R6-08 submission package | `submission/eartharxiv/` — 36-pp single PDF (coversheet + manuscript), source zip, metadata.yaml, cover_abstract.txt, figures/, supplement pointers, LICENSE_AND_ATTRIBUTION.md, FINAL_CHECKLIST.md, README_submission.md | DONE |
| R6-09 final review | `audits/r6_final_review.md` — four reviewer roles (RS science / spatial statistics / cartography / integrity), all PASS | DONE |
| R6-10 final QA | pytest; rebuild; page-by-page checks; commit + push (this commit) | DONE |

### Key R6 findings and changes

1. **Critical figure defect caught:** the R6 design system initially
   rendered all basemaps without land (metre/km unit mismatch in
   `add_basemap`), which the first cartographic QA wrongly passed; the
   correction is documented in `r6_cartographic_qa.md` §0.1 and all four
   affected figures were regenerated and re-verified.
2. **Two factual corrections:** East China >50 km pixel count (237, not
   478); CMSA producer attribution (Capital Normal University / NESDC
   release, not CAS).
3. **Integrity hardening:** fabricated/unverified back-matter claims
   removed (funding, COI, reviewers acknowledgement); remaining
   TODO_VERIFY placeholders are intentional and enumerated in the
   submission checklist.
4. **Submission gating:** the package is complete but **not submitted**;
   the Owner-confirmation items (ORCID, preprint license, funding/COI/AI
   wording, CMSA/GEODATA/CM-SSM license confirmations, legal name,
   journal-submission line) are listed in
   `submission/eartharxiv/FINAL_CHECKLIST.md`.

### Verification record (R6)

| Check | Result |
|---|---|
| LaTeX build | 35 pp, 0 errors, 0 undefined refs/citations, 20 bib entries |
| Merged preprint PDF | 36 pp (coversheet + 35), single-PDF rule satisfied |
| Figures | land-layer pixel re-verification after unit-bug fix; visual review PASS |
| Cartographic QA | `r6_cartographic_qa.md` incl. §0.1 correction |
| Integrity audit | all primary numbers PASS vs committed CSVs/JSON |
| Commits | this commit on `feat/paper1-map-reliability` (not merged to `main`) |

---

## History: R5 — IJRS submission-targeted finalization

### What was done

| Task | Deliverable | Status |
|---|---|---|
| R5-01 baseline | HEAD `b84feda`, clean tree, tests 588 passed/21 skipped | DONE |
| R5-02 journal verification | `audits/r5_ijrs_journal_requirements.md` (live retrieval 2026-11-08) | DONE — all owner hard requirements PASS |
| R5-03 repositioning | new title "Spatial Agreement and Regional Uncertainty in Multi-Source Maps of *Spartina alterniflora* along the Chinese Coast"; abstract rewritten to 281 words (≤ 300 IJRS limit); storyline strengthened; draft-history wording removed | DONE |
| R5-04 R4 integration check | 4.06–4.18× robustness retained; coverage-mask absence explained; displacement claims softened to "consistent with, not conclusively" in 4 locations | DONE |
| R5-05 references + positioning | **12 unverifiable (fabricated) references removed**; 17-entry verified bibliography; 7 newly verified citations incl. the CMSA production paper (Li et al. 2024, IJRS 45(9)); `literature/r5_ijrs_related_work_matrix.md` | DONE |
| R5-06 figure/table QA | `audits/r5_figure_table_qa.md`; 8 figures @300 dpi, 12 tables; no regeneration needed | DONE |
| R5-07 language/length | 31→32 pp, ~10,200 words; secondary diagnostics moved to new `supplementary/supplementary_information.tex` (SI §S1, superseded meridian-band analysis) | DONE |
| R5-08 declarations | `audits/r5_submission_declarations.md` (licensing status + owner-confirmation checklist) | DONE |
| R5-09 submission package | `submission/ijrs/` — main.pdf (32 pp), LaTeX source, 8 TIFF figures @300 dpi, SI PDF, IJRS-specific cover letter, data + code availability statements, author/funding/COI checklist, submission checklist | DONE |
| R5-10 peer review | `audits/r5_ijrs_peer_review.md` — five perspectives; technical items (regional block-size sensitivity, phenology-window hypothesis, harmonization-envelope caveat) closed in-text | DONE |
| R5-11 final QA | tests 588 passed/21 skipped (76 s); LaTeX 32 pp, 0 undefined refs; commit + push | DONE |

### Key R5 findings and changes

1. **Journal (R5-02).** IJRS verified: SCIE (IF 2.6, 2025), CAS 2025 upgraded
   edition Q4 (Earth Sciences major category), subscription route with **zero
   mandatory APC** ("If you choose not to publish open access in this
   journal, there is no APC"; no submission/page/colour charges), fast
   review (4-day average first decision, 57-day post-review, 14-day
   acceptance→online). No hard requirement fails.
2. **Reference integrity (R5-05).** Full verification against
   CrossRef/doi.org found 12 of 17 scholarly entries unverifiable, several
   with DOIs resolving to unrelated papers. All removed/replaced; the final
   bibliography carries only verified entries plus 2 explicitly marked
   institutional dataset-release placeholders (owner must confirm formal
   citations). Notably the CMSA production paper was published in IJRS
   itself — a strong journal-fit anchor.
3. **Manuscript (R5-03/04/07).** Product-reliability framing; abstract within
   IJRS's 300-word limit; internal draft-history references removed; the
   superseded meridian-band analysis moved to Supplementary Information
   §S1 (published via Figshare at the journal side); IJRS-required
   declarations added (Disclosure of interest; generative-AI-use declaration
   placeholder pending owner wording; data availability aligned with the
   journal's "Share Upon Reasonable Request" policy).
4. **Peer review (R5-10).** Five-perspective verdict: scientifically sound,
   minor-revision-level technical concerns (all closed in-text during R5);
   submission blocked only by owner-dependent administrative items.

### Manuscript status (after R5)

| Metric | Value |
|---|---|
| Title | Spatial Agreement and Regional Uncertainty in Multi-Source Maps of *Spartina alterniflora* along the Chinese Coast |
| PDF pages | 32 |
| Word count | ~10,200 (incl. tables; command-stripped) |
| Abstract | 281 words (IJRS limit 300) |
| Figures included | 8 (all 300 dpi; TIFF exports in package) |
| Tables included | 12 |
| References | 17 (all verified or explicitly marked placeholders) |
| Undefined references | 0 |
| Owner-blocked placeholders | affiliation, e-mail, funding, COI, AI-use wording, 2 dataset citations |

### Remaining blockers

1. Owner-dependent front matter: authors, affiliation, corresponding author,
   ORCID, CRediT roles, funding confirmation, COI confirmation,
   generative-AI-use declaration (see
   `submission/ijrs/author_funding_coi_checklist.md`).
2. Dataset licensing: CMSA (unverified, provider contact needed), GEODATA
   (CC-BY-NC-ND?, confirm), CM-SSM (Zenodo DOI 10.5281/zenodo.16296823;
   mirror license conflict).
3. No GOLD reference data → accuracy not assessable (disclosed in the
   manuscript; scientific scope limit, not a submission blocker).

### Verdict

**Submission package complete.** The manuscript is genuinely ready for IJRS
submission once the owner completes the administrative checklist and authorizes
submission. Do not submit without owner authorization (per standing instruction).

### Verification record (R5-11)

| Check | Result |
|---|---|
| `pytest tests -q` | 588 passed, 21 skipped, 41 warnings, 76.2 s |
| LaTeX build | `main.pdf`, 32 pages, 0 undefined references |
| Abstract length | 281 words ≤ 300 |
| Bib integrity | 17 entries; 0 unverifiable scholarly entries (audit: `literature/r5_ijrs_related_work_matrix.md` §1) |
| Package | `submission/ijrs/` (PDF, source, 8 TIFFs, SI, cover letter, statements, 2 checklists) |
| Commits | R5 commit + follow-up Git-reference update; pushed to `origin/feat/paper1-map-reliability` (not merged) |

---

## History: R4 — regional attribution audit, coverage audit, manuscript revision

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
