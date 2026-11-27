# V0.2.1 CANDIDATE AUDIT — repair candidate re-verification (Phase 1.1)

Scope: re-audit of `v0_2_1_repair_candidate_table.csv` (14 candidates)
against the frozen artifacts, with a focused audit of
`CNA10K-R00163-C00067`. Nothing was re-selected or re-ranked; no frozen
file was modified; no minimum-event-count threshold was invented after
the fact.

## 1. Corrections to Phase 1 statements (all corrected, original data untouched)

| Phase 1 statement | Wrong because | Corrected statement |
|---|---|---|
| "4–21 events per cell-year" (all 14 candidates) | included a 2-event cell-year | **All 14 candidates: 2–21**; positive candidates alone: 4–21; background candidates: 2–12 |
| "9 lost positives: 6 NO_ELIGIBLE … + 3 NO_SCENE cells" | mixed cell-year reasons conflated cells with cell-years | **9 cells / 10 failed cell-years**; primary reasons: NO_ELIGIBLE_EVENT_ACTUAL_MASK = 6 cell-years, NO_SCENE = 4 cell-years; 6 of 10 failed cell-years carry two failure reasons; failure classes: 2020-only 7 cells, 2015-only 1 cell, both-year 1 cell |
| "2020-dominated deficit" (Phase 1) | correct direction but imprecise | precise ledger in `V0_2_1_FAILURE_LEDGER.csv` (10 rows, per-slot statuses, primary/secondary per cell-year) |

## 2. Focused audit: CNA10K-R00163-C00067

### 2.1 Identity and role

- Role in candidate table: **CLEAN_BACKGROUND_REPAIR** (background, not a
  GEODATA-positive candidate). `geodata_2015_pos_px = 0`,
  `geodata_2020_pos_px = 0`; consistent with its `clean_background`
  definition (no positive pixels in GEODATA 2015/2020, no CMSA
  2020/2021 area, no CM-SSM 2020 positive, no SILVER 2015 positive).
  Role-vs-label consistency verified for all 14 candidates: 0 violations.
- Membership: `KEEP_MAINLAND_COASTAL`, `production_eligible = True`
  (`china_coastal_cells_v1_1_core_frozen.csv`, membership reason
  `CHINA_SEAWARD_WATER`, deterministic rule v1).
- Province attribution: `UNKNOWN` (target-independent rule could not
  assign; legal for background — UNKNOWN can never anchor a region
  holdout, and this cell is not used for one).
- Context caveat (recorded, not an exclusion): `admin_class =
  WATER_NEAR_CHINA`, JRC water occurrence ≈ 94.5 % year-round, 7.5 km
  from mainland. **This is consistent with the original frozen protocol**:
  the already-frozen 53-cell panel contains 5 `WATER_NEAR_CHINA`
  background/context cells (JRC water 92–99 %), so the repair selection
  introduces no policy deviation. Its scientific weight as a
  "background" control is nevertheless weaker than a tidal-flat
  background cell; this is flagged for Owner awareness in Phase 2, and
  it is not counted on for anything beyond the ≥12 background gate.
- Spatial distinctness: 450.8 km from the nearest panel cell (largest in
  the candidate set).

### 2.2 Census provenance and Landsat dates (from frozen EO census v0_1, metadata only)

- 2015 autumn window (DOY 260–320): **6 events**, sensors
  {landsat7, landsat8} — 2015-09-23 (DOY 266, L8), 2015-10-17 (DOY 290,
  L7), 2015-10-18 (DOY 291, L8), 2015-10-25 (DOY 298, L8),
  2015-11-03 (DOY 307, L8), 2015-11-10 (DOY 314, L8).
- 2020 autumn window: **2 events**, sensor {landsat8} — 2020-09-29
  (DOY 273), 2020-10-15 (DOY 289).
- Season eligibility: every listed event carries
  `AUTUMN_PRIMARY_V1_CANDIDATE` with DOY inside the frozen window
  260–320; `coverage = FULL_CELL_COVERED`,
  `geometry_basis = WRS2_NOMINAL_FRAME`, `member_scene_count = 1`.
- The 2020 count of 2 sits at the **lower bound of the frozen desired
  range** (`observations_per_cell_year_desired: [2, 3]` in
  `SPARTINASHIFT_V0_2_SUPPORT_REQUIREMENTS.json`). No post-hoc minimum
  threshold is created; per the frozen protocol this is admissible.

### 2.3 Evidence status

- All evidence is `CENSUS_METADATA_ONLY_V0_1` — nominal-frame coverage
  from the metadata census. **No live-GEE actual-footprint verification
  has been run for this (or any) candidate** (`live_gee_verified=false`
  in the candidate table); the ≥0.95 actual-observed-mask gate is applied
  only in the Phase 2 planner re-run. If it fails that gate, it drops by
  the frozen QA rules — not by any new threshold.
- Sensor availability note: S1 autumn-full flags are 0 for this cell
  (2020/2021); S2 autumn-full both years = 1. Under Option B it would be
  Landsat + S2 only; under Option A, Landsat-only — no S1-pair impact on
  the q5 gate either way.

### 2.4 Verdict

**KEEP.** The cell complies with the frozen selection protocol and frozen
acquisition rules; its description in Phase 1 (event range, role) is
corrected in §1 and the readiness report. No re-selection is performed
because no protocol violation exists.

## 3. Projection integrity (corrected framing)

The four support states are now strictly separated everywhere:

| State | Meaning | Where it lives |
|---|---|---|
| **Measured support** | counts on landed, QA-passed v0.2 bytes | `v02_support_matrix_per_cell.csv` (11/11/5) |
| **Metadata-eligible support** | counts on frozen census metadata (nominal frames, no actual-mask evidence) | 291 pool cells; 14 selected candidates |
| **Projected support** | scenario arithmetic on metadata-eligible support | `v0_2_1_projected_support_matrix.csv` — **reference scenario only** |
| **Landed & QA-passed support** | post-export, post-QA v0.2.1 bytes | **does not exist yet** |

The "≈55 %" figure is the **observed metadata→landed pass rate of the 20
GEODATA-positive panel cells (11/20) under the Phase H export+QA rules**.
It is a historical reference scenario used only to size candidate
selection margin — it is **not** a validated success probability for the
new candidates: the new cells differ in WRS geometry, sensor mix (L7/L8),
and cloud climatology, and their live-GEE actual-mask behavior is
unknown until the Phase 2 planner runs. The projected matrix carries a
`scenario` qualifier and the readiness verdict remains NOT_READY on
measured support alone.

### Re-check of the 14-candidate projected matrix

Projection recomputed under the reference-scenario qualifier:

- Positives: 11 measured + k landed both-year positives; gate ≥12 needs
  k ≥ 1 of 8. Reference scenario (k ≈ 0.55 × 8 ≈ 4.4 → ≈15): not a
  prediction, a sizing argument only.
- Backgrounds: 11 measured + k landed; gate ≥12 needs k ≥ 1 of 6.
- Regions: 5 measured ≥ 3 already; the candidates cannot reduce this.
- No other gate is touched by the repair.
- Sensitivity floor: even if **only the single strongest-margin candidate
  set result k = 1** materializes per stratum, the gate still passes at
  exactly 12/12 — the projection is therefore robust to large pass-rate
  errors, but the PASS claim itself waits for landed bytes.
