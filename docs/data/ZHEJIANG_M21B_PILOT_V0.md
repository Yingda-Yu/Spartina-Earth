# Zhejiang M2.1b controlled real-pixel pilot — v0 record

Issue: [#13 M2.1b — Controlled real-pixel multimodal pilot on fixed
Zhejiang cells](https://github.com/Yingda-Yu/Spartina-Earth/issues/13)

Status: **PILOT COMPLETE — STOP GATE ENGAGED.** 13 real ObservationProducts
landed, byte-validated and checksummed. No model training. The previously
estimated 303-pair standard batch was **not** run.

- Bay: Hangzhou Bay (`ZJ-HZB`); year: 2022
- Season policy: `autumn_primary_v1_PROPOSED_NOT_FROZEN`, DOY 260–320
- Parent unit: fixed 10 km analysis cell, EPSG:32651 (UTM 51N)
- Aggregate manifest:
  [zhejiang_m21b_pilot_v0.json](../../datasets/manifests/zhejiang_m21b_pilot_v0.json)
  / [.csv](../../datasets/manifests/zhejiang_m21b_pilot_v0.csv)
- Frozen cell roster:
  [zhejiang_m21b_pilot_cells_v0.csv](../../datasets/manifests/zhejiang_m21b_pilot_cells_v0.csv)
- Frozen event plan:
  [zhejiang_m21b_pilot_event_plan_v0.json](../../datasets/manifests/zhejiang_m21b_pilot_event_plan_v0.json)
  / [.csv](../../datasets/manifests/zhejiang_m21b_pilot_event_plan_v0.csv)
  (signed by SHA-256 fingerprint)
- Per-product manifests + byte-validation records:
  `work/m21b/manifests/ZJ_M21B_*.json` (git-ignored bytes store; the JSON
  manifests themselves live outside Git by policy and are referenced from
  the tracked aggregate CSV/JSON)
- Raw pixels and task-state histories: `work/m21b/products/`,
  `work/m21b/tasks/task_store.json` (git-ignored)

## 1. Selected cells and rationale

Eight cells were chosen by deterministic, fixed-order stratified rules
implemented in
[m21b_pilot.py](../../src/spartina/data/zhejiang/m21b_pilot.py)
(`select_pilot_cells`). Every ranking key ends with the lexical cell id;
the roster is a pure function of the tracked overlap/disagreement
manifests. Label strata drove the selection; S2 coverage was recorded as
a separate constraint and never used for performance-based cherry picking.

| Order | Cell | Stratum | Rank value | Rationale (short) |
|---|---|---|---|---|
| 1 | ZJ_U51_10K_E033_N336 | HIGH_SILVER_FRACTION | 0.075546 | max SILVER bay-clip fraction |
| 2 | ZJ_U51_10K_E036_N332 | MEDIUM_SILVER_FRACTION | 0.045742 | SILVER rank 2 |
| 3 | ZJ_U51_10K_E034_N335 | MEDIUM_SILVER_FRACTION | 0.032283 | SILVER rank 3 |
| 4 | ZJ_U51_10K_E029_N336 | LOW_SILVER_FRACTION | 0.029912 | SILVER rank 4; only cell with S1 + L8 + L9 eligibility |
| 5 | ZJ_U51_10K_E031_N335 | SILVER_WEAK_DISAGREEMENT | Jaccard 0.0435 | lowest tier-agreement diagnostic |
| 6 | ZJ_U51_10K_E032_N336 | SILVER_WEAK_DISAGREEMENT | Jaccard 0.5942 | second-lowest, larger support on both tiers |
| 7 | ZJ_U51_10K_E039_N341 | VERY_LOW_SILVER_FRACTION | 0.000257 | smallest SILVER-positive fraction with v0_1 quality S2 |
| 8 | ZJ_U51_10K_E037_N339 | UNLABELED_COASTAL_CONTROL | 100.0 km² clip | largest unlabeled coastal clip with quality S2; **UNLABELED, not NEGATIVE** |

No cell is a train/test assignment. These are pipeline-validation units.

## 2. Products per sensor

13 products, 24 landed files, **127,253,613 bytes = 121.4 MiB = 0.119 GiB**
(hard cap 10 GiB; plan estimate was 176 MiB).

| Sensor | Products | Files/product | Bytes |
|---|---|---|---|
| Sentinel-2 (10 m) | 10 | 2 (B2/B3/B4/B8 float32 + VALID uint8) | 111,552,896 |
| Landsat 8 (30 m) | 1 | 3 (7×SR float32 + VALID uint8 + QA_PIXEL uint16) | 3,402,332 |
| Landsat 9 (30 m) | 1 | 3 (same) | 3,385,499 |
| Sentinel-1 (10 m) | 1 | 1 (VV,VH float32, identity dB) | 8,912,886 |

### Sentinel-2

All 8 cells received their clearest eligible event (coverage gate
≥ 0.99 on the group union; per-contributing-scene cloud ≤ 0.30). Two
cells additionally received one extra same-datatake multi-tile event,
for 10 S2 products.

- Only **two distinct datatakes** supply the ten products
  (2022-10-02 `GS_2022-10-02`, 2022-10-10, plus one extra 2022-10-15
  event): different cells clip the same event; the cell is the
  provenance unit, so these are distinct cell-level ObservationProducts,
  not duplicates. No cell+event pair repeats.
- Multi-tile same-datatake merges occurred with the exact contributing
  tile sets: RTP+RUP (2022-10-10), RUP+RUQ (2022-10-02 and 2022-10-10),
  RUQ+RVQ (2022-10-02). Merge is one ordered
  `ee.ImageCollection.mosaic()` restricted by exact `system:index` list;
  a server-side assert verifies a single `DATATAKE_IDENTIFIER` and a
  single UTC date. **No cross-date mosaic is possible.**
- Tile order, datatake id and reflectance scale are recorded per
  product (`processing_config`).
- VALID contract: S2 SCL classes {4 vegetation, 5 bare, 6 water} valid,
  snow/ice (11) invalid, policy version
  `s2_scl_qa_v1_1` (`S2_SCL_QA_POLICY_VERSION`), **intersected with the
  four-band observation mask in the source tile** (revision r5; see
  §7). 20 m bands were excluded; no resampling.

### Landsat 8/9 (first real C2 L2 byte validation)

First naturally eligible scene over the selected cells:

- L8 `LC08_119039_20220930` (WRS path 119, row 39), scene cloud 0.2329
- L9 `LC09_118039_20221001` (WRS path 118, row 39), scene cloud 0.0435

Both land as **single scenes, native 30 m, 334×334 px** on the 30 m
lattice covering the 10 km cell (10,020 m per side; never upsampled to
10 m). SR is the explicit C2 L2 physical transform
DN × 2.75e-5 − 0.2 applied server-side. Each product ships three files:
physical SR (7 float32 bands), VALID uint8 (QA_PIXEL clear bit with no
fill/dilated/cirrus/cloud/shadow/snow bit and QA_RADSAT = 0), and raw
QA_PIXEL uint16 for independent audit. WRS path/row, product id,
spacecraft, cloud metadata and scale/offset are in the manifest.

### Sentinel-1 (first real S1 byte validation)

- One eligible scene found in-window over the selected union:
  `S1A_IW_GRDH_1SDV_20220917T095509_..._045043_...` on cell E029_N336,
  ASCENDING pass, relative orbit 171, VV+VH, 10 m.
- Eligibility used the **actual per-scene GEE geometry** measured
  locally after the two-pass metadata+geometry fetch, not the nominal
  MGRS/frame approximation.
- Export is identity select only: `COPERNICUS/S1_GRD` is already sigma0
  in dB, so **no 10·log10 was applied**. ASC/DESC are separate products
  by construction (`first_s1_per_pass` keeps pass keys apart).
- **No DESCENDING scene reached 0.99 actual coverage in the window** —
  recorded in the failure ledger (§5); no substitute was fabricated.

## 3. QA distributions

S2 cell VALID fractions (fraction of the 1,000,000 cell pixels passing
SCL+observation VALID):

| Product | Cell | Tiles | Max scene cloud | VALID fraction |
|---|---|---|---|---|
| S2_001 | E029 | RTP,RUP | 0.00099 | 0.9737 |
| S2_002 | E031 | RUP | 0.00099 | 0.9610 |
| S2_003 | E032 | RUP | 0.00099 | 0.9996 |
| S2_004 | E033 | RUP | 0.00018 | 0.9996 |
| S2_005 | E034 | RUP | 0.00018 | 0.9616 |
| S2_006 | E036 | RUP | 0.00018 | 0.9874 |
| S2_007 | E037 | RUP,RUQ | 0.00036 | 1.0000 |
| S2_008 | E039 | RUQ,RVQ | 0.03258 | 0.9840 |
| S2_009 (extra) | E029 | RTP,RUP | 0.28687 | 0.9458 |
| S2_010 (extra) | E037 | RUP,RUQ | 0.04657 | 1.0000 |

(The extra 2022-10-15 event S2_009 is intentionally a stress case: high
whole-scene cloud but 94.6 % VALID inside the cell. It is an extra
observation, never a replacement of the clear primary.)

- L8 VALID fraction 0.8116; L9 VALID fraction 0.9779 — consistent with
  their scene-level cloud fractions (0.23 / 0.04).
- S1 has no cloud QA; all 1,000,000 pixels are observed (no nodata
  inside the scene footprint over the cell).

## 4. Byte-validation records

### Sentinel-2

`reflectance_sanity_masked` on every product: per-band percentiles
restricted to VALID = 1, DN-like fraction and |v| > 1.5 fraction
checked. All ten pass the explicit 1e-4 scaling audit (no product
carries DN-scale values); the landed SR grid is asserted identical to
the locked GridSpec and the VALID raster is uint8 with only {0,1}.

### Landsat

`qa.scaling_audit` per scene: SR p01/p99 must sit inside the physical
range [−0.30, 1.30] with ordered percentiles for all seven bands —
PASS for L8 and L9. Raw QA_PIXEL lands as uint16 (not re-scaled),
VALID as uint8 {0,1}, both grids asserted. Scale (2.75e-5) and offset
(−0.2) are recorded in `processing_config`; this is the first deferred
real Landsat byte/scaling validation and it passes.

### Sentinel-1

Observed VV percentiles p01/p50/p99 = −24.70 / −9.54 / +0.79 dB
(min −39.86, max +22.31); VH = −28.95 / −16.26 / −7.70 dB
(min −43.93, max +13.30). VV maxima above +20 dB occur at developed
shoreline / port corner-reflector targets and are within the documented
coastal-cell dB envelope (−50…+30 dB); the envelope is only a sanity
gate.

The decisive identity check is an **independent server-side
recomputation**: min/max and p1/p50/p99 were re-reduced from the source
scene over the exact projected region at 10 m and compared with the
landed GeoTIFF. Absolute deltas: min/max 0.000 dB, percentiles
≤ 0.116 dB (numpy vs GEE interpolation differences; tolerance 0.6).
A missed rescale or a second 10·log10 could not survive this. Result:
PASS (`qa.server_identity_check` in the S1 manifest).

## 5. Failure ledger

| Code | Object | Detail |
|---|---|---|
| NO_ELIGIBLE_S1_DESCENDING_SCENE_2022_AUTUMN | all selected cells | No IW VV+VH DESCENDING scene reached 0.99 actual-geometry coverage in DOY 260–320. ASC only; no substitute. |
| V0_1_NOMINAL_MGRS_FRAME_UNDERCOVERAGE | E031_N335, E032_N336, E033_N336, E034_N335, E036_N332 (5 cells) | The corrected v0_1 simulator used NOMINAL MGRS tile-frame polygons and recorded zero 2022-autumn S2 events for these cells; actual datatake footprints cover them, and the pilot exported real quality events for all five. The archive simulation needs an actual-geometry revision before the 303-pair batch. |

No export failures remain in the final build. Engineering iterations
during the pilot (region r1/r2, Landsat VALID r4, S2 mask r5) are
recorded transparently in §7; none of their bytes entered a manifest.

## 6. Provenance, grid and co-registration audit

- Every file: SHA-256, size, Drive name/folder, GEE task id and full
  READY→RUNNING→COMPLETED poll history (`export_tasks`); every product
  carries a canonical `bundle.fingerprint_sha256` over grid, source
  scene ids, file roles/sizes/hash and processing config, plus git
  commit, runtime environment and the frozen event-plan fingerprint.
- Retry/resume/idempotence: the JSON task store deduplicates by
  `(product, role, build_revision)` request ids; reruns verify stored
  COMPLETED tasks against GEE and re-hash landed bytes before skipping.
  The full rerun after completion skipped all 13 products with
  re-hashed bytes — zero duplicate exports.
- Actual-vs-manifest bounds/transform: every landed raster is asserted
  with `assert_grid_matches` against the GridSpec derived from the
  tracked cell registry; mismatches raise and never produce a manifest.
- Cross-sensor grid audit on E029_N336: S2 and S1 share the **exact**
  10 m lattice transform `[10,0,290000,0,-10,3370000]`, 1000×1000.
  L8/L9 are 334×334 on transform `[30,0,289980,0,-30,3370020]`,
  i.e. the global 30 m lattice with (10 m, 10 m) origin offset relative
  to the 10 m cell corner and a symmetric outward snap (10,020 m
  coverage). No 30 m value was resampled into a 10 m product.

## 7. Build-revision log (engineering evidence, not hidden)

- r1: WGS84 polygon region — GEE server-side reprojection added one
  pixel column (1001×1000); rejected by grid assert, bytes deleted.
- r2: projected-CRS rectangle alone — identical server-side expansion;
  rejected, bytes deleted.
- r3: added explicit `dimensions=[w,h]` pinning with `crsTransform` —
  grid exact (1000×1000 / 334×334). S1 product shipped at r3.
- r4: Landsat VALID fix (r3 emitted raw QA_PIXEL DNs, values {0,255});
  VALID is now the boolean decision byte. L8/L9 products shipped at r4.
- r5: S2 VALID intersected with the all-four-10 m-bands observation
  mask; the RUQ+RVQ seam of S2_008 had 10 pixels SCL-valid but
  surface-band-missing. All ten S2 products shipped at r5 with matched
  reflectance/VALID pixel counts.

## 8. Tide and label discipline

- Tide on every product: `observed_tide = MISSING`,
  `modeled_tide = NOT_DEPLOYED` (FES2022b selected, not deployed),
  inundation proxy MISSING, water-fraction proxy MISSING. No modeled or
  proxy value is labelled observed. The pilot was not blocked on tide.
- Labels: 2015 national product stays SILVER; local masks stay WEAK;
  the unlabeled control stays UNLABELED (never NEGATIVE); no GOLD
  promotion. **No label bytes were copied into any product** — only
  per-asset availability/tier/rights metadata. L1 redistribution = NO
  is honored; rights are recorded per asset in each manifest.

## 9. Blockers before the 303-pair standard batch

1. **Actual-geometry acquisition simulation is required archive-wide.**
   The v0_1 nominal-MGRS-frame simulator under-covered 5 of 8 pilot
   cells (failure ledger). The standard batch eligibility census must
   be rebuilt from real per-scene geometry before scene counts can be
   trusted.
2. **S1 DESCENDING coverage gap.** No descending scene met the gate in
   the autumn window over the selected union; archive-level descending
   coverage statistics over real geometry are needed before promising
   dual-pass observations.
3. **Tide remains undeployed.** FES2022b modeling or station data must
   land before tide-dependent intertidal comparisons.
4. **Season policy is PROPOSED_NOT_FROZEN.** DOY 260–320 is recorded
   but not frozen; freeze it deliberately before the archive batch.
5. The pilot export/validation driver is opt-in
   (`SPARTINA_M21B_EXPORT=1`) and plan-locked; scaling requires an
   explicit new approval and a new plan, not a flag change.

## 10. Reproduction

```bash
conda activate spartina-earth
export SPARTINA_GEE_PROJECT=<project-id>
# 1. freeze cells (offline, tracked manifests only)
PYTHONPATH=src python scripts/data/zhejiang/m21b_select_cells.py
# 2. live metadata+geometry discovery and plan fingerprint
PYTHONPATH=src python scripts/data/zhejiang/m21b_discover_events.py
# 3. authorised real exports + byte validation (resume-safe)
SPARTINA_M21B_EXPORT=1 \
  PYTHONPATH=src python scripts/data/zhejiang/m21b_export_products.py
```

QA gates run in this work: `pytest` → 286 passed, 15 skipped;
`pytest -m gee_integration` → 12 passed, 3 export-gated skips;
`ruff check .` clean; `mypy --strict src scripts` clean. Offline unit
tests for the selection/gating/dB rules:
[test_zhejiang_m21b_pilot.py](../../tests/unit/test_zhejiang_m21b_pilot.py)
(20 tests).
