# PROGRESS — Paper 1: Multi-Source Spartina alterniflora Map Reliability

**Branch:** feat/paper1-map-reliability
**Last commit:** ced3c43 (Phase 0-3 scientific audit)
**Target journal:** SCI Q3–Q4 (candidate: International Journal of Digital Earth, Remote Sensing, or Science of the Total Environment)

---

## Current milestone: Phase 0–3 completed (audit, gate, protocol, evidence mapping)

### Manuscript status

| Metric | Value |
|---|---|
| PDF pages | 16 |
| Word count (raw tex) | ~6,150 |
| Sections | 7 (Introduction, Study Area/Datasets, Methodology, Results, Discussion, Conclusions, Data inventory) |
| Subsections | 25 |
| Figures (included) | 3 (fig03 agreement map, fig04 stats composite, fig05 resolution curves) |
| Tables (included) | 5 (table1–4 + 1 in Results body) |
| TODOEXP markers | 18 (most blocked — E5/E6/E7) |
| TODOVERIFY markers | 9 (citation full-text reading) |
| Citations in .bib | 30 entries (ASCII-clean, verified DOIs where available) |

### Experiments completed

| Experiment | What it does | Script | Output file(s) | Status |
|---|---|---|---|---|
| E1 Harmonization | CRS/domain/class map | e3_spatial_agreement.py (embedded) | protocol.md | ✅ FROZEN |
| E2 Area consistency | Native + harmonized areas | audit_all_sources.py, e3_spatial_agreement.py | area_summary.json | ✅ VERIFIED |
| E3 Spatial agreement | IoU/Dice 30/50/100m | e3_spatial_agreement.py | iou_dice_2020_multi_res.csv | ✅ VERIFIED |
| E3 Agreement maps | 3-panel visualization | e6_agreement_map.py | fig03_agreement_map.pdf | ✅ VERIFIED |
| E4 Resolution sensitivity | IoU change 30→100m | e3_spatial_agreement.py | (embedded in CSV) | ✅ VERIFIED |
| E5 Regional heterogeneity | Stratified IoU | — | — | ❌ BLOCKED |
| E6 Monitoring implications | Trend conflict + hotspot | — | (qualitative only) | ⚠️ PARTIAL |
| E7 Independent validation | Ground-truth accuracy | — | — | ❌ BLOCKED (no GOLD ref data) |

### Audit and protocol files (created this session)

| File | Purpose |
|---|---|
| audits/feasibility_gate.md | 5 critical scientific questions + explicit PASS with caveats |
| experiments/protocol.md | Full frozen experimental protocol at commit 9be4073 |
| audits/rq_evidence_matrix.md | RQ1–RQ4 → experiment → figures → actual numbers → caveats |

### Results summary (VERIFIED numbers)

| Metric | Value | Source |
|---|---|---|
| CMSA 2020 (harmonized 30m EPSG:3410) | 570.11 km² | e3_spatial_agreement.py |
| CM-SSM 2020 (harmonized) | 592.35 km² | e3_spatial_agreement.py |
| GEODATA 2020 (harmonized) | 520.38 km² | e3_spatial_agreement.py |
| 2020 cross-product range | **14.2%** | Max − min / min |
| CMSA ↔ CM-SSM IoU | **0.5375** | e3, 30m |
| CMSA ↔ GEODATA IoU | **0.4437** | e3, 30m |
| CM-SSM ↔ GEODATA IoU | **0.3423** | e3, 30m |
| Resolution sensitivity max | **≤0.4% IoU change 30→100m** | e4, all pairs |
| CMSA 2017→2021 trend | +4.0%/year (monotonic) | CMSA time series |
| GEODATA 1990→2015 trend | +567% total | GEODATA time series |
| GEODATA 2015→2020 trend | −6.8% apparent contraction | GEODATA time series |

### Scientific contribution gate (from rq_evidence_matrix.md)

| Contribution | Evidence level | Verdict |
|---|---|---|
| C1: Reproducible and defensible comparison protocol | Full | ✅ CONFIRMED — protocol frozen, audited |
| C2: Quantitative spatial agreement/disagreement characterization | Full | ✅ CONFIRMED — IoU/Dice, area ranges, agreement masks |
| C3: Structure or sensitivity of discrepancies | Partial (resolution sensitivity only) | ⚠️ PARTIAL — ≤0.4% resolution stability confirmed, but E5 regional heterogeneity not done |
| C4: Substantive monitoring implication | Qualitative only | ⚠️ PARTIAL — trend conflict identified, no quantitative uncertainty bounds |

**Overall gate verdict:** The work is **not yet a confirmed SCI Q3–Q4 submission candidate**. It is a **defensible early research draft** with reproducible methodology, quantitative core findings, and clear blocked extensions. Submission readiness requires either:
1. Implementing E5 regional heterogeneity + E6 hotspot ranking (to strengthen C3 and C4), OR
2. Explicitly limiting the scope and framing the paper as a protocol/methodology contribution targeting a methods-oriented journal.

### Scientific blockers

| Blocker | Severity | Mitigation |
|---|---|---|
| E7 independent validation impossible | HIGH (no GOLD ref data) | Explicitly state in limitations; paper is inter-product agreement, not accuracy |
| E5 regional heterogeneity not done | MEDIUM | Can be added as a simple domain mask + stratified IoU computation (no new downloads needed) |
| E6 hotspot ranking uses CM-SSM province codes (circular) | HIGH (scientific integrity) | Prohibited by feasibility gate; must either use external admin boundaries or abandon regional attribution |
| 4 planned figures (01,02,06,07) missing | LOW | Can be added as context figure (01,02) or explicitly marked as pending |
| Statistical independence not quantified | MEDIUM | Acknowledge autocorrelation caveat; spatial-block bootstrap would fix but adds complexity |

### Critical open issues (TODOEXP markers)

1. **Regional stratification** (E5): Split domain by 4 coastal subregions (e.g., Bohai/Yellow/East/South China Sea) and compute per-subregion IoU. No new data needed — CMSA bounds + manual polygon masks.
2. **E4 extra sensitivity tests**: Grid alignment (shift harmonization grid by half RES_M), coastline buffer (test 0km vs 10km vs 50km), rasterization rule (all_touched=True vs False).
3. **Monitoring implications writing**: Expand Results 4.4 with trend interpretation, add cross-conflict explanation.
4. **4 core reference full-text reading**: Wang 2024 IJDE, Zhao 2023 RS, Xu 2024 RSE, Ximenes 2023 STOTEN. Currently only partially retrieved.

### Git commit history

| Commit | Description |
|---|---|
| cb90ad7 | Stage A — manuscript foundation, compiled 14-page PDF, audited areas |
| a5b2b45 | Remove debug LaTeX test files |
| 7f65e14 | Stage B — E3 IoU/Dice + E4 resolution sensitivity (CSV + JSON) |
| 5dea0fe | Stage D — manuscript integration, 2 figures, 3 tables |
| 9be4073 | Final Stage D — fig03 agreement map, manuscript fully integrated (16 pages) |
| ced3c43 | Phase 0–3 — feasibility gate, frozen protocol, RQ evidence matrix |

### Next execution step

1. **Optional (high impact, medium effort):** Implement E5 regional heterogeneity. Split domain by 4 coastal subregions (predefined masks), compute per-subregion IoU and area ratios. Add Figure 06. Strengthens C3 (structure of discrepancies) from Partial to Full.
2. **Required before submission:** Read full text of 4 core comparison studies, extract methodological differences, write comparative subsection.
3. **Required:** Expand monitoring implications writing with trend conflict explanation and cross-product uncertainty framing.
4. **Quality pass:** Visual inspection of fig03–fig05 for any remaining issues (label clipping, color consistency).
