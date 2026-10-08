# PAPER_STATUS — Spartina Earth v0

Updated: 2026-10-08 (Issue #18 R1 scientific closure: (A)
source-independent Natural Earth 10m admin-1 regional attribution
replaces product-derived region keys — 125.21 km² unattributed GEO area
reduced to 0.98 km² residual UNKNOWN, H4 still SUPPORTED with ranges
0.75/0.58/0.80 (10 m 0.78); (B) primary inference switched to
KEEP_ONLY 3,011 cells, 3,021 provisional-inclusive retained as
sensitivity (max pooled-Dice delta 0.0003); (C) H2 wording changed to
NOT_SUPPORTED / observed direction opposite, with explicit H2≠H3
estimand distinction; v2 manifest tables 11–14, ledger C61–C63,
§08/§10/table/analysis-note updated, figures manifest source v2;
2026-10-07: Issue #18 2020 three-product disagreement/scale
audit executed: pre-registered 5 m lattice abandoned for two
documented supports (30 m GEODATA native grid + 10 m project
lattice); H1/H3/H4/H5/H6 SUPPORTED, H2 NOT_SUPPORTED (opposite
direction); Dice 0.52–0.71 with W10 cluster-bootstrap CIs; repair
audit 0 dropped / 0.0% area change; agreement not accuracy, GOLD=0;
§08 new subsection, Table tab_labeldisagreement2020, Fig. 7
placeholder, §04 cross-ref, §10 paragraph, ledger C57–C60; prior
update 2026-10-06: M2.4 external-label intake: GEODATA 1990/2000/
2015/2020 and CMSA 2017–2021 archives delivered, byte-audited and
registered in china_external_label_registry_v1.csv; table/§04/ledger
C45/C56 updated; GOLD still 0; prior update: Issue #16 census
supersession v0_1; Issue #17 domain membership v1, W10 verdict
REMAIN_PROVISIONAL; first-pixel pilot designed, not executed, but
re-validated against v1 membership).

## Draft status by section

| File | Section | Status (Issue #15 target) |
|---|---|---|
| sections/01_introduction.tex | Introduction | **Full prose drafted** |
| sections/02_related_work.tex | Related work | **Full v0 drafted** (3 subsections, 37 verified refs available) |
| sections/03_study_design.tex | Study design and data provenance | **Full prose drafted** |
| sections/04_data_and_provenance.tex | Data sources, tiers, rights, national label family | **Full prose + Table tab_label_products (10 acquired, byte-audited products; M2.4)**; measured GEODATA/CMSA areas, 2020 contradiction resolution, grid non-alignment, CM-SSM byte-identity integrated |
| sections/05_observation_model.tex | Observation model (envelope→cell→event→QA) | **Full prose drafted** (R1-corrected semantics) |
| sections/06_zhejiang_pilot.tex | Zhejiang census, data factory, R1 corrections, M2.1b real-pixel pilot | **Full prose with executed M2.1b evidence** (§M2.1b; Table tab_m21b; Fig. 6 placeholder) |
| sections/07_pilot_baselines.tex | Pilot-0 baselines + M2.1b boundary | **Verified subsections drafted**; Pilot-0 carries tiny-support caveats; M2.1b subsection states what it adds and still does not |
| sections/08_national_scaling.tex | National scaling (v0 grid + v1 membership candidate) | **Full prose with executed census and membership audit**: 3,319 immutable Albers cells distinguished from membership (v1: 3,011 KEEP / 298 EXCLUDE / 10 PROVISIONAL; REMAIN_PROVISIONAL), strata on grid and active subset, Murray/JRC context-only, tier estimates, Issue #16 v0_1 census (227,505 scenes; S1 DESCENDING_REGIONALLY_AND_TEMPORALLY_IMBALANCED; 2026 PARTIAL_YEAR); 20-cell panel designed not executed and re-validated as all-active; **Issue #18 2020 three-product audit executed (R1 closed 2026-10-08)**: two supports, H1–H6 pre-registered decisions (H2 NOT_SUPPORTED, observed direction opposite; independent regional attribution; KEEP_ONLY primary bootstrap + provisional sensitivity), Table tab_labeldisagreement2020, Fig. 7 placeholder |
| sections/09_discussion.tex | Discussion | **Skeleton + verified discussion points**; pending-result paragraphs marked |
| sections/10_limitations.tex | Limitations | **Full prose drafted** |
| sections/11_conclusion.tex | Conclusion | **Skeleton drafted** |

Abstract: not drafted yet (per writing workflow, abstract follows
stable introduction/methods); placeholder in main.tex.


## Phase 3 evidence status (2026-10-03)

**VERIFIED (may be stated in manuscript):**
- Zhejiang real-byte controlled pilot (8 cells / 13 products; Issue #13,
  closed): 3 S2 datatakes (5/4/1), 2022-10-15 =
  PRODUCTION_ELIGIBLE_EXTRA_NONPRIMARY.
- Provenance architecture and executed correction audits (false-zero
  labels; group-wide cloud-gate bug; S1 representative-frame errors).
- National label-family audit: 10 entities all acquired and
  byte-audited (M2.4): four GEODATA masks (research-only; 2020 bytes
  verified Spartina against a mangrove portal abstract defect; 2015
  local copy byte-identical to the ordered archive), five CMSA vector
  years 2017–2021 (CC BY-NC 4.0; measured areas), CM-SSM byte-identical
  to official Zenodo; 2010 not found and not fabricated; GOLD = 0;
  cross-family differences explicitly not change.
- CM-SSM official/local identity (8 shapefile components, SHA256) with
  SOURCE_LICENSE_CONFLICT preserved.
- 2020 three-product disagreement/scale audit (Issue #18, executed
  2026-10-07; R1 scientific closure 2026-10-08): two non-fabricated
  supports; MakeValid repair 0 dropped / 0.0 % area change; Dice
  0.52–0.71; W10 cluster bootstrap primary universe KEEP_ONLY 3,011
  cells (3,021 provisional-inclusive reported as sensitivity, deltas
  ≤0.0003); H1/H3/H4/H5/H6 SUPPORTED; H2 NOT_SUPPORTED — observed
  direction opposite to the preregistered expectation (0.2095 vs
  0.3162; not described as universally falsified; H2≠H3 estimand
  distinction explicit); independent Natural Earth regional
  attribution leaves only 0.98 km² GEO area UNKNOWN (from 125.21);
  agreement characterisation only (GOLD = 0); no SILVER eligibility or
  merge-rule change.
- Mainland China coastal domain v0: target-independent corridor,
  Albers-vs-UTM comparison, 3,319 provisional W10 cells, flags/strata,
  13-source multimodal registry, Tier 0-3 model estimates.

- National EO metadata census and actual-footprint indices (Issue #16):
  EXECUTED metadata-only (184,051 scenes, 79,265 events,
  10,058,703 cell-event pairs; EO_CENSUS_RUN_MANIFEST_v0.json).

- Mainland coastal-domain membership v1 (Issue #17): deterministic
  target-independent GIS rule; 3,011 keep / 298 exclude / 10
  provisional; all 20 #16 flags confirmed artifacts; W5/W10/W20
  artifact-rate sensitivity; Murray/JRC 30 km context only; freeze
  verdict REMAIN_PROVISIONAL (claims C52-C55).

**PENDING (must not be presented as results):**
- First-pixel pilot pixel download (20-cell panel designed, not
  executed; design re-validated: all 20 cells are active v1 members).
- National pixel archive at any tier.
- GOLD field/UAV labels (GOLD = 0).
- Management-event geometry ledgers (0 events).
- Tide deployment (FES2022b selected, not deployed; observed tide
  missing).
- Nationwide accuracy, cross-region generalization, recurrence
  experiments, SpartinaFM representation results.

## Claim-to-source support audit (Phase 3)

`CLAIM_SUPPORT_AUDIT.md` — 18 highest-impact external claims audited
claim -> citation -> source support (DOI existence is not treated as
support). Two claims were narrowed (1979-introduction citations;
dieback vs post-treatment regrowth), one wording softened (single SAR +
optical study "illustrates" not "confirms"), one verified citation
added (wang2018soilcarbon), and the S1 dB product fact is explicitly
marked as platform documentation with TODO_CITATION.


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
- `tables/tab_label_products.tex` — 10 audited national label products
  (source: china_spartina_label_products_v0.csv; rotated page; no GOLD,
  2010 absent by verification, roles and license conflict explicit).

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
2. (DONE) National domain, 2015 cell stratification and metadata census
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
