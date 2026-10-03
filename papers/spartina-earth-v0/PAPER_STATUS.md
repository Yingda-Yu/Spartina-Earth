# PAPER_STATUS — Spartina Earth v0

Updated: 2026-10-03 (M2.1b/Issue #13 evidence absorbed). Issue: #15.

## Draft status by section

| File | Section | Status (Issue #15 target) |
|---|---|---|
| sections/01_introduction.tex | Introduction | **Full prose drafted** |
| sections/02_related_work.tex | Related work | **Full v0 drafted** (3 subsections, 37 verified refs available) |
| sections/03_study_design.tex | Study design and data provenance | **Full prose drafted** |
| sections/04_data_and_provenance.tex | Data sources, tiers, rights | **Full prose drafted** |
| sections/05_observation_model.tex | Observation model (envelope→cell→event→QA) | **Full prose drafted** (R1-corrected semantics) |
| sections/06_zhejiang_pilot.tex | Zhejiang census, data factory, R1 corrections, M2.1b real-pixel pilot | **Full prose with executed M2.1b evidence** (§M2.1b; Table tab_m21b; Fig. 6 placeholder) |
| sections/07_pilot_baselines.tex | Pilot-0 baselines + M2.1b boundary | **Verified subsections drafted**; Pilot-0 carries tiny-support caveats; M2.1b subsection states what it adds and still does not |
| sections/08_national_scaling.tex | National scaling design | **Methods/design subsection drafted**; all results TODO_EVIDENCE (Issue #14) |
| sections/09_discussion.tex | Discussion | **Skeleton + verified discussion points**; pending-result paragraphs marked |
| sections/10_limitations.tex | Limitations | **Full prose drafted** |
| sections/11_conclusion.tex | Conclusion | **Skeleton drafted** |

Abstract: not drafted yet (per writing workflow, abstract follows
stable introduction/methods); placeholder in main.tex.

## Figures (see figures/FIGURE_MANIFEST.md)

Schemas exist for Figures 1–6 (Fig. 6: M2.1b integrity-evidence panel).
Per the writing skill's rendering gate,
only labeled placeholder boxes are compiled; no final artwork is
rendered without an explicit per-figure request. Figure 5 must remain a
design schematic, never a fabricated national result map.

## Tables (generated from tracked artifacts)

- `tables/tab_census.tex` — 18,435-scene census (source:
  `zhejiang_eo_scene_census_v0.parquet`, acceptance report §4.2).
- `tables/tab_grid.tex` — 5/10/20 km grid counts (M2.1a2 report A).
- `tables/tab_funnel.tex` — 2022 S2 funnel and R1 recovery.
- `tables/tab_pilot0.tex` — Pilot-0 main ladder (source:
  PILOT0_BASELINE_REPORT.md §1, frozen 49-run audit).
- `tables/tab_s1footprint.tex` — S1 representative-vs-actual audit.
- `tables/tab_m21b.tex` — M2.1b 13-product real-pixel inventory
  (source: zhejiang_m21b_pilot_v0.json + per-product manifests).

## Claim ledger counts (as of this draft)

VERIFIED_RESULT: 23 · VERIFIED_METHOD: 13 · PRELIMINARY_RESULT: 1 (C05,
bound to C06) · PLANNED: 3 (+1 flagship hypothesis C35) · UNKNOWN: 1 ·
BLOCKED: 2 (C37 management events; C38 observed tide); C12/C13/C31
upgraded to VERIFIED via M2.1b; new C39–C44 (M2.1b integrity evidence,
including the integrity≠accuracy boundary C44)
(full list in CLAIM_EVIDENCE_LEDGER.md; some IDs carry dual status).

## Missing evidence blocking upgrade of sections

1. CLOSED for M2.1b (Issue #13, READY_TO_CLOSE): 13 real-pixel
   products, first eligible L8/L9/S1 byte validations, S2 three-datatake
   accounting, and the nominal-MGRS-frame finding (5/8). Remaining:
   archive-scale pixel QA, 303-pair batch, cross-bay/season replication.
2. National domain, 2015 cell stratification and metadata census
   (Issue #14) — all national quantitative statements.
3. GOLD reference (Issue #11): currently GOLD = 0; accuracy claims
   beyond SILVER-reproduction are impossible.
4. Tide joins (FES2022b deployment; observed gauge licensing).
5. Verifiable management-event spatial ledger (0 events today).
6. SpartinaFM experiments (future; not part of this paper's claims).

## Paper family analysis (analysis only — nothing locked)

- **Paper A — methods/framework/benchmark.** Current draft lineage:
  provenance-aware observation architecture, acquisition-group QA,
  leakage controls, Zhejiang engineering verification, later the
  SpartinaShift benchmark. Potential venue family: *Remote Sensing of
  Environment*, *ISPRS Journal of Photogrammetry and Remote Sensing*,
  *IEEE TGRS*. Submission requires M2.1b closure, benchmark
  construction, and (for accuracy claims) GOLD evidence.
- **Paper B — national dataset/Atlas.** Only after a mature nationwide
  data product: *Scientific Data*, *Earth System Science Data*, or a
  remote-sensing data journal. Issue #14 builds the metadata frame only;
  it is not a data paper.

No venue is guaranteed or optimized for at this stage
(cf. RESEARCH_CONTEXT.md publication policy).

## Compile

`latexmk -pdf -interaction=nonstopmode main.tex` — must compile with zero
errors; warnings about missing figures are not expected (figures are
inline placeholder boxes, not missing includes).

## Update rule

After each of Issues #13 and #14: update the ledger first, then tables,
then prose; TODO_EVIDENCE markers are removed only when the artifact
exists and is fingerprinted.
