# UPDATED_RESEARCH_ROADMAP — 2026-11-26 reboot

Paper 1 submission is paused (owner decision); its assets stay frozen on
`feat/paper1-map-reliability`. The center of gravity returns to the full
Spartina Earth program. Order below is execution order; earlier items gate
later ones.

## Phase 1 — Data gates (NOW)

- **P0-A GEODATA temporal repair (Issue #21).** DONE: metadata planner,
  14-cell ranked candidate table, cost estimate, reserve wording audit
  (`V02_1_READINESS_REPORT.md`). NEXT: owner-approved live-GEE planner
  re-run + export + QA → re-measure gate on landed evidence.
- **P0-B GOLD validation system.** Registry exists (30 candidates, GOLD=0);
  acquisition plan written (`GOLDSET_ACQUISITION_PLAN.md`). NEXT: owner
  permission gate → Tier-1 pilot (4 sites) with double review.

## Phase 2 — Formal benchmark (P1)

`BENCHMARK_NEXT_STAGE_PLAN.md`. Conventional ladder first; EO foundation
models only after adapters verified on landed bytes; every run fully
provenance-tagged; per-stage owner review.

## Phase 3 — SpartinaFM research preparation (P1)

**Failure analysis precedes architecture.** After Stages A–D, extract and
classify failures into a reproducible taxonomy with quantified shares:

| Failure source | Diagnostic method |
|---|---|
| Label quality | errors concentrated at SILVER-source disagreement/boundary strata; cross-check with GOLD pilot sites |
| Sensor difference | per-sensor ΔIoU; error vs band-identity ablation |
| Time/phenology | error vs DOY tertile, vs observation count; cross-year residual maps |
| Modality missing | dropout-condition error increments |
| Regional ecology | leave-region-out residual clustering vs coastal-segment covariates |

Output: `docs/research/SPARTINAFM_GAP_ANALYSIS.md` with per-cause evidence
and only gaps that are (a) quantified, (b) reproducible, (c) not solvable
by more data of existing type. SpartinaFM architecture design starts only
after this document is Owner-accepted. If foundation models already solve
the measured gaps, the contribution redirects to data/benchmark/ecology
(pre-declared in HYPOTHESES.md H6 decision rule).

## Phase 4 — Spartina Atlas (P2, China coast)

- Data production plan using Landsat 5/7/8/9 (30 m historical backbone)
  and Sentinel-1/2 (10 m modern layer), **managed as separate resolution
  families**; 30 m never upsampled and presented as 10 m.
- Products: historical distribution, expansion, disappearance, recurrence,
  per-cell uncertainty, management-response linkage (requires the
  management-event ledger, currently 0 events → H8 stays
  `BLOCKED: DATA MISSING` until real treatment records exist).
- **Temporal-integrity rule: a year with no valid observation for a cell
  is reported as NO_VALID_OBSERVATION, never as species disappearance.**
  Disappearance requires a passing observation with label-negative or
  expert evidence.
- Map standards for every Atlas figure: real geographic context
  (international/administrative boundaries, coastline, ocean, graticule,
  scale bar, north arrow, inset locator, legend, native-resolution
  statement). Bare colored rasters without basemap are rejected.

## Phase 5 — Global transfer (P3)

Starts only after China-coast validation is mature (GOLD ≥ Tier-2,
benchmark tracks executed). China-region results are never narrated as
"global generalization"; international evaluation uses independent
non-China labels only (RQ7; licensing status UNKNOWN today).

## Publication posture (unchanged policy)

Venue ambitions remain evidence-gated (`RESEARCH_CONTEXT.md`); no
submission, preprint, or accuracy claim is made before the corresponding
evidence exists. Negative and "foundation model already solves this"
results are acceptable outcomes and redirect effort to data/ecology.
