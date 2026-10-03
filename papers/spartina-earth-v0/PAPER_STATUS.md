# PAPER_STATUS — Spartina Earth v0

Updated: 2026-10-03. Issue: #15.

## Draft status by section

| File | Section | Status (Issue #15 target) |
|---|---|---|
| sections/01_introduction.tex | Introduction | **Full prose drafted** |
| sections/02_related_work.tex | Related work | **Full v0 drafted** (3 subsections, 37 verified refs available) |
| sections/03_study_design.tex | Study design and data provenance | **Full prose drafted** |
| sections/04_data_and_provenance.tex | Data sources, tiers, rights | **Full prose drafted** |
| sections/05_observation_model.tex | Observation model (envelope→cell→event→QA) | **Full prose drafted** (R1-corrected semantics) |
| sections/06_zhejiang_pilot.tex | Zhejiang census, data factory, R1 corrections | **Full prose drafted**, verified numbers |
| sections/07_pilot_baselines.tex | Pilot-0 baselines | **Verified subsection drafted** with tiny-support limitations; real-pixel M2.1b results are TODO_EVIDENCE |
| sections/08_national_scaling.tex | National scaling design | **Methods/design subsection drafted**; all results TODO_EVIDENCE (Issue #14) |
| sections/09_discussion.tex | Discussion | **Skeleton + verified discussion points**; pending-result paragraphs marked |
| sections/10_limitations.tex | Limitations | **Full prose drafted** |
| sections/11_conclusion.tex | Conclusion | **Skeleton drafted** |

Abstract: not drafted yet (per writing workflow, abstract follows
stable introduction/methods); placeholder in main.tex.

## Figures (see figures/FIGURE_MANIFEST.md)

Schemas exist for Figures 1–5. Per the writing skill's rendering gate,
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

## Claim ledger counts (as of this draft)

VERIFIED_RESULT: 21 · VERIFIED_METHOD: 9 · PRELIMINARY_RESULT: 1 (C05,
the Pilot-0 ladder, bound to C06) · PLANNED: 4 · UNKNOWN: 1 · BLOCKED: 3
(full list in CLAIM_EVIDENCE_LEDGER.md; some IDs carry dual status).

## Missing evidence blocking upgrade of sections

1. M2.1b real-pixel products (Issue #13): first real S2 cell-level
   products, first eligible Landsat and S1 byte validations.
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
