# V0.2.1 READINESS REPORT — SpartinaShift GEODATA-temporal repair

Issue #21 gate `q1_geodata_temporal` is the only failing gate of
`V0_2_READINESS_DECISION.json` (verdict
`NOT_READY_FOR_SPARTINASHIFT_V0_2_PROTOCOL`, commit `c6cbd50`):
measured positives = 11 (min 12), background = 11 (min 12), regions = 5
(min 3). This report is the **Phase 1 deliverable: audit + metadata
planner + cost estimate**. No GEE export, no QA relaxation, no
label-model-driven re-picking was performed.

## 1. Gate audit (why 11/11 and not 20+25)

Measured on `v02_support_matrix_per_cell.csv` (53 panel cells):

| Definition (frozen) | Count | Detail |
|---|---|---|
| GEODATA-positive both years (geo15 ∧ geo20) | 20 | 5 regions: FJ 3, JS 3, SD 4, ZJ 2, GD 2, GX 1, SH 1, HEB 2 (20 total) |
| … with Landsat **landed** 2015 ∧ 2020 | **11** | SD 4, FJ 3, JS 2, ZJ 1, HEB 1 — regions = 5 ✔ |
| Clean background with Landsat landed both years | **11** | JS 3, SD 3, FJ 2, HEB 1, LN 1, JL 1 |
| (background with any landed EO is 25; the gate counts the Landsat-both-years form) | | |

Root cause of the 9 lost positives: 2020 Landsat eligibility failures in
`v02_landsat_acquisition_plan.csv` — `NO_ELIGIBLE_EVENT_ACTUAL_MASK` for
R00224-C00049, R00344-C00157, R00377-C00131/C00133, R00428-C00110 (autumn
window events existed but failed the ≥0.95 actual-observed-mask gate) and
`NO_SCENE` for R00231-C00083 / R00233-C00083; plus R00320-C00161 failing
both years and R00297-C00151 failing 2015. The 2015 side is healthy for
these cells (eligible observations landed); the deficit is 2020-dominated.

## 2. Candidate pool re-scan (metadata only, target-independent)

Inputs (all frozen, checksummed in Issue #21 Phase A):
`work/issue21/derived/v02_cell_features.csv` (3,016 KEEP cells with
GEODATA 2015/2020 positive-pixel counts and census-derived
`landsat_autumn_full_*` flags), EO census v0_1
(10,923,012 cell-event rows), frozen cell registry.

Excluded from selection reasoning: any model output, Stage-1 errors,
uncertainty, failure maps — none used.

| Pool slice | Count | Provinces |
|---|---|---|
| Non-panel, GEODATA 2015∧2020 positive, Landsat autumn-full **both years** | **291** | ZJ 92, FJ 57, JS 55, SD 28, SH 20, GD 19, GX 10, TJ 6, HEB 3, UNK 1 |
| … additionally ≥12 km from every panel cell (non-adjacency buffer) | **252** | ZJ 82, FJ 50, JS 49, SD 20, GD 18, SH 16, GX 9, TJ 4, HEB 3, UNK 1 |
| Non-panel clean background + Landsat both years | **2,421** (≥12 km: 2,316) | GD 537, SD 330, LN 321, HN 256, ZJ 232, FJ 215, JS 144, … |

The pool is deep; the gate needs ≥1 more landed positive and ≥1 more
landed background. Selection therefore optimizes margin, not sufficiency.

## 3. Repair candidate table (deterministic, reproducible)

Artifact: `benchmarks/spartinashift/v0_2_1_repair/v0_2_1_repair_candidate_table.csv`.
Selection rule (frozen before any imagery): filter pool →
SHA-256 rank key `V0_2_GEODATA_REPAIR_V1|{cell_id}` → ≤4 per province →
top 8 positives + top 6 backgrounds. Every candidate has census-verified
autumn-window Landsat 7/8 events in BOTH 2015 and 2020 (4–21 events per
cell-year; details per cell in the CSV). All are ≥12 km from panel cells.

Positives (8): ZJ R00331-C00149 (118/132 px), SH R00348-C00154 (765/39),
JS R00352-C00155 (1550/1410), JS R00372-C00139 (2364/943), ZJ
R00324-C00156 (31/54), GX R00224-C00047 (472/49), ZJ R00315-C00157
(752/436), SD R00416-C00120 (203/90).
Backgrounds (6): HN R00188-C00044, JS R00364-C00141, GD R00215-C00058,
HN R00205-C00047, UNK R00163-C00067, GD R00232-C00095.

**Evidence status per candidate: `CENSUS_METADATA_ONLY_V0_1`,
live_gee_verified = false.** The Phase 2 step must re-run the frozen
Landsat planner (`scripts/benchmarks/spartinashift/build_v02_acquisition_plan.py`
with `SPARTINA_V02_SELECT=1` + GEE project) over these 14 cells to obtain
`LIVE_GEE_EXPORT_GRID` actual-footprint evidence before any export.

## 4. Revised acquisition plan + support matrix projection

`v0_2_1_projected_support_matrix.csv` (same directory) projects gate
outcomes after a Phase 2 export+QA pass:

| Gate | v0.2 measured | v0.2.1 projected |
|---|---|---|
| positives both years ≥12 | 11 | PASS if ≥1/8 candidates lands both years; expected ≈15 (observed metadata→landed pass rate on geo-positive panel cells: 11/20 ≈ 55%) |
| regions ≥3 | 5 | PASS (≥5; candidates add SH/GX/SD depth) |
| background ≥12 | 11 | PASS if ≥1/6 lands; expected ≈14 |
| all other gates | PASS | unchanged |

Projection is **not** a result. The verdict below stays NOT_READY until
landed, QA-passed bytes exist.

## 5. Reserve isolation audit (53-cell panel / 24-cell reserve)

Verified facts (checksums re-hashed today and matching the frozen JSONs):

1. The 24 reserve cells are a subset of the 53-cell exported panel; all 24
   have role `V0_2_NEW_PANEL_EXPORTED` and landed EO (24/24 `any_landed`).
   Reserve CSV SHA-256 and panel CSV SHA-256 match the frozen JSON records.
2. **Export-status wording inconsistency found and normalized here:**
   internal notes variously say `FRESH_TEST_RESERVE_UNTOUCHED` / "sealed",
   which can be misread as "never exported". The accurate, consistent
   statement (already present in `V0_2_READINESS_DECISION.json` q6 note) is:
   **reserve cells were exported and landed as part of the Phase H panel
   export; they are sealed from training, tuning, role assignment and
   inspection; no model output influenced their selection; final roles are
   frozen only by the future v0.2 protocol.** Future artifacts must use
   "sealed-after-export", never "untouched/unexported".
3. Stage-1 overlap: 0 reserve members are Stage-1 panel/test/witness cells;
   the 4 inspected test/witness cells are excluded from the reserve.
4. Known structural caveat (already recorded in the Issue #21 final
   report): reserve strata (15 CMSA-positive / 8 background) make the
   reserve 45%-positive vs. a train pool that is not; Variant 1 vs
   Variant 2 holdout interpretation remains an owner-level protocol
   decision for the v0.2 protocol freeze.
5. Adding the 14 repair cells does **not** touch the reserve: repair cells
   are separate cells; reserve membership is not extended in this phase.

## 6. Cost estimate (`V0_2_1_REPAIR_SCOPE_ESTIMATE.json`)

| Option | Component tasks | Landed bytes | Caps (96 cells / 40 GiB / 10k tasks) |
|---|---|---|---|
| A: Landsat-only, ≤3 obs × 2 years per cell (83 obs max) | ≤249 | ≤0.36 GiB | all clear |
| B: full multimodal (S2 + S1 pairs added, panel-comparable) | ≈350 | ≈2.25 GiB | all clear |

Both options include the 14 repair cells on top of the existing 53-cell
panel: total new cells 67 ≤ 96. **No cap breach; export requires explicit
owner approval (Issue #21 hard scope rule), and Option A vs B is an owner
decision** (B keeps the new cells usable for CMSA/pair tracks at ~6× bytes).

## 7. Readiness decision v0.2.1

**Verdict: `NOT_READY_FOR_SPARTINASHIFT_V0_2_PROTOCOL` (unchanged).**

Flip condition (pre-declared): after owner-approved Phase 2 —
(1) live-GEE planner re-run over the 14 cells with the frozen rules,
(2) export within the chosen option, (3) QA pass per the frozen
actual-mask/QA contract — the GEODATA-temporal gate is re-measured on
**landed** evidence. It flips to READY only if measured positives ≥12,
background ≥12, regions ≥3, with zero QA relaxation and zero
model-informed selection. If fewer than 1 positive lands, the honest
fallback is a scientifically-scoped alternative (e.g., restricting the
Landsat-temporal track to the 11 landed positives + expanding the CMSA
S2 temporal track as the primary temporal benchmark) — decided by Owner,
never by threshold adjustment.
