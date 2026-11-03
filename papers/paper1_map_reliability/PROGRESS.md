# PROGRESS — Paper 1: Multi-Source Spartina alterniflora Map Reliability

**Branch:** feat/paper1-map-reliability
**Last commit:** ca11141 (R2 comprehensive revision in progress — local changes)
**Target journal:** SCI Q3–Q4 (candidate: International Journal of Digital Earth, Remote Sensing, or Science of the Total Environment)

---

## Current milestone: R2 revision — manuscript substantially rewritten and strengthened

### Manuscript status (after R2)

| Metric | Value |
|---|---|
| PDF pages | **23** |
| Word count (raw tex) | **~9,500** |
| Sections | 7 (Introduction, Study Area/Datasets, Methodology, Results, Discussion, Conclusions, Data Availability) |
| Subsections | 32 |
| Figures (included) | 5 (fig03 agreement map, fig04 stats composite, fig05 resolution, fig05b regional IoU, fig06 robustness) |
| Tables (included) | 6 (table1 datasets, table2 area comparison, table3 IoU/Dice, table4 sensitivity, **table5 bootstrap uncertainty**, **table6 boundary sensitivity**) |
| TODO markers in scientific body | **0** (all citations resolved, all TODOEXP/TODOVERIFY removed from text) |
| TODO markers in appendix | 2 (license gaps, honest data statements) |
| Citations in .bib | 28 entries (all with DOIs where applicable) |
| Cross-reference errors | **0** (clean LaTeX compile, 3 pdflatex + bibtex passes) |

### Experiments completed

| Experiment | What it does | Script | Output file(s) | Status |
|---|---|---|---|---|
| E1 Harmonization | CRS/domain/class map | e3_spatial_agreement.py (embedded) | experiments/protocol.md | ✅ FROZEN |
| E2 Area consistency | Native + harmonized areas | audit_all_sources.py | area_summary.json | ✅ VERIFIED |
| E3 Spatial agreement | IoU/Dice 30/50/100m | e3_spatial_agreement.py | iou_dice_2020_multi_res.csv | ✅ VERIFIED |
| E3 Agreement maps | 3-panel visualization | e6_agreement_map.py | fig03_agreement_map.pdf | ✅ VERIFIED |
| E4 Resolution sensitivity | IoU change 30→100m | e3_spatial_agreement.py | (embedded in CSV) | ✅ VERIFIED |
| E4 Extended robustness | Grid shift, coastline buffer, all_touched | e4_robustness_extended.py | robustness_2020.csv | ✅ VERIFIED |
| E5 Regional heterogeneity | Stratified IoU by subregion | e5_regional_heterogeneity.py | regional_agreement_2020.csv | ✅ VERIFIED |
| **E5b Boundary sensitivity** | Shift subregion boundaries ±250–500km | e5b_boundary_sensitivity.py | e5b_boundary_sensitivity.csv | ✅ NEW (R2) |
| **E5c Bootstrap IoU** | Block-bootstrap uncertainty quantification | e5c_bootstrap_iou.py | e5c_iou_bootstrap.csv | ✅ NEW (R2) |
| E6 Monitoring implications | Hotspot stability, rankings | (embedded in manuscript Results/RQ4) | (descriptive, quantitative) | ✅ VERIFIED |
| E7 Independent validation | Feasibility scan for GOLD data | (manuscript search, documented) | audits/ | ❌ BLOCKED (no national GOLD data) |

### Key R2 findings (NEW — not in R1)

| Finding | Evidence |
|---|---|
| 3× IoU regional heterogeneity is **robust to boundary placement** | E5b: South/North IoU ratio remains 3.2–3.96× across x=10.75M–11.25M m boundary positions (CMSA–GEODATA pair) |
| 3× IoU regional heterogeneity is **statistically meaningful** | E5c: Bohai/Yellow 95% CI [0.078, 0.211] and South China [0.424, 0.487] **do not overlap** |
| Effective sample size for IoU is **~2,000 blocks**, not 3.35B pixels | E5c: Only 0.24% of 2km blocks contain *Spartina* pixels |
| Global IoU is precise despite autocorrelation (±3% relative uncertainty) | E5c: Global CMSA–GEODATA IoU CI = [0.4182, 0.4719], 3% relative width |
| Bootstrap uncertainty is now quantified for all three pairs | E5c CSV includes global + 3 regional CIs |

### Scientific contribution gate

| Contribution | Evidence level | Verdict |
|---|---|---|
| C1: Reproducible and defensible comparison protocol | Full | ✅ CONFIRMED — protocol frozen, audited |
| C2: Quantitative spatial agreement/disagreement characterization | Full | ✅ CONFIRMED — IoU/Dice, area ranges, agreement masks |
| C3: Structure or sensitivity of discrepancies | Full | ✅ CONFIRMED — resolution, grid shift, boundary sensitivity, all_touched, bootstrap uncertainty |
| C4: Substantive monitoring implication | Quantitative | ✅ STRENGTHENED — hotspot stability (robust), secondary rankings (not robust), resource allocation sensitivity |

**Overall gate verdict:** The work is now **a defensible SCI Q3–Q4 submission candidate**. The core 3× IoU regional heterogeneity finding is:
- Quantitatively measured (E5 regional)
- Robust to boundary placement (E5b sensitivity)
- Statistically meaningful (E5c bootstrap CI non-overlap)

### Remaining minor issues (before submission)

1. **[Trivial]** Fix author affiliation/email placeholder in manuscript
2. **[Minor]** Clarify CMSA license language in Data Availability
3. **[Minor]** Figure 04a may mix source-reported vs. harmonized values — check caption
4. **[Minor]** GSHHS coastline mask mentioned in Methods but experiments use CMSA bounds — reconcile or clarify

### Git commit history (cumulative)

| Commit | Description |
|---|---|
| cb90ad7 | Stage A — manuscript foundation (14 pages) |
| 7f65e14 | Stage B — E3 IoU/Dice + E4 resolution |
| 5dea0fe | Stage D — manuscript integration |
| 9be4073 | fig03 agreement map |
| ced3c43 | Phase 0–3 — feasibility gate, protocol, evidence matrix |
| a0241a4 | PROGRESS.md update |
| ca11141 | R1 scientific corrections (10 overclaims fixed) |
| *(local)* | **R2 comprehensive revision** — +2 experiments, bootstrap, boundary sensitivity, manuscript rewrite |

### Next execution step

1. Commit and push R2 revisions to `feat/paper1-map-reliability`
2. Fix minor remaining issues (affiliation, figure 04a caption)
3. Target journal selection: IJDE (International Journal of Digital Earth) — strongest Q3 fit for this paper
4. External peer review via colleagues
5. Optional: Improve figures (vector quality, label consistency)

---

*Last updated: 2026-11-04*
