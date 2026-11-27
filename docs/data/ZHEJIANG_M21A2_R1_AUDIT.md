# M2.1a2-R1 Observation-Unit Audit and Correction

Status: **SCIENTIFIC BLOCKERS RESOLVED — READY FOR RE-REVIEW (no M2.1b start)**
Date: 2026-10-03
Branch: `reboot/spartina-earth-m0` (local commits only; not pushed)
Scope: metadata / geometry / audit only. No `ee.batch.Export`, no pixel
production, no training, no split freeze, no GOLD promotion.

This document answers the 44 final-report questions from the Issue #12
review instruction in order (A–G).

## Evidence index

| Artifact | Role |
|---|---|
| `datasets/manifests/zhejiang_label_cell_overlap_v0_1.{csv,parquet}` | Cell x label overlap with both full-square and bay-clip measurements |
| `datasets/manifests/zhejiang_label_bay_reconciliation_v0_1.csv` | Direct envelope intersection vs sum of clipped cells, per grid size |
| `datasets/manifests/zhejiang_hzb_label_disagreement_v0_1.csv` | HZB L1/L3 disagreement layer on bay-clip common 30 m grid (diagnostic) |
| `datasets/manifests/zhejiang_label_cell_overlap_v0.SUPERSEDED.json` | v0 marker (bytes preserved) |
| `datasets/manifests/zhejiang_s2_2022_funnel_audit_v0.csv` | 2022 autumn S2 funnel stages A–J per bay |
| `datasets/manifests/zhejiang_s2_2022_funnel_rejections_v0.csv` | Pair rejection buckets, both gates |
| `datasets/manifests/zhejiang_s2_2022_funnel_audit_v0.verdict.json` | Machine-readable verdict + datatake verification |
| `datasets/manifests/zhejiang_s2_2022_spotcheck_v0.csv` | 9-scene live GEE metadata spot-check, all PASS |
| `datasets/manifests/zhejiang_s1_footprint_audit_v0.{csv,parquet}` | Scene x cell approx-vs-actual S1 coverage |
| `datasets/manifests/zhejiang_s1_footprint_audit_summary_v0.csv` | MAE/P95/max + false eligible/rejected by stratum |
| `datasets/manifests/zhejiang_s1_footprint_audit_v0.policy.json` | Production footprint policy |
| `datasets/manifests/zhejiang_cell_observation_stats_v0_1.csv` | Regenerated pair statistics (all years/sensors) |
| `datasets/manifests/zhejiang_monthly_availability_v0_1.csv` | Regenerated monthly table |
| `datasets/manifests/zhejiang_s2_recovery_v0_1.csv` | Regenerated S2 recovery table |
| `datasets/manifests/zhejiang_export_volume_estimate_v0_1.csv` | Regenerated export volume planning estimate |
| `datasets/manifests/zhejiang_m21a2_r1_artifact_fingerprints_v0.csv` | SHA-256 of every R1 artifact |

v0 superseded artifacts retain bytes; each has a `.SUPERSEDED.json`
sidecar. The acquisition group manifest
`zhejiang_acquisition_group_simulation_v0.parquet` is **byte-identical**
to the pre-R1 commit (grouping did not change).

Defect markers:
`M21A_SMB_ZERO_WAS_MASK_FAILURE`,
`CELL_EDGE_BLEED_CONFIRMED`,
`S2_2022_ZERO_WAS_GROUPWIDE_CLOUD_BUG`,
`S1_REPRESENTATIVE_FOOTPRINT_NOT_PRODUCTION_GEOMETRY`.

---

## A. Label contradiction (Q1–Q8)

**Q1. Why did M2.1a report SMB label = 0 while M2.1a2 found 21 positive cells?**
Two independent defects, both now evidenced:
1. The M2.1a zero was a **silently swallowed geometry failure**. The SMB
   polygon in `datasets/rois/zhejiang_bays_v0.geojson` is an invalid
   `GeometryCollection` containing non-polygon parts (`is_valid=False`).
   `build_label_inventory.py`'s raster mask raised `ValueError`, caught by
   a broad `except ValueError: counts=(0,0.0)`, so the missing
   measurement was recorded as zero. Extracting the polygonal part
   (MultiPolygon, 1 part) gives **46,310 px / 41.6790 km2** of L1 SILVER
   label inside the SMB envelope. Marker
   `M21A_SMB_ZERO_WAS_MASK_FAILURE`. The M2.1a inventory parquet is
   unchanged; its SMB L1 row is to be treated as `CONTRADICTED`.
2. M2.1a2 counted label pixels on the **full 10 km fixed square**
   regardless of bay membership (`CELL_EDGE_BLEED_CONFIRMED`).

**Q2. Was it cell bleed?** Yes, partially. Full-square attribution
counted label area outside the provisional bay envelope. On 10 km L1:

| Bay | full-square positive px | bay-clip px | outside-bay px |
|---|---:|---:|---:|
| HZB | 22,193 (19.9737 km2) | 19,268 (17.3412 km2) | 2,925 (2.6325 km2) |
| SMB | 50,649 (45.5841 km2) | 46,310 (41.6790 km2) | 4,339 (3.9051 km2) |
| YQB | 30,369 (27.3321 km2) | 22,927 (20.6343 km2) | 7,442 (6.6978 km2) |

**Q3–Q5. Corrected SILVER-bearing 10 km cells** (`cell_label_status_bay_scoped`,
L1-china2015, SILVER or SILVER+WEAK):
**HZB 13, SMB 17, YQB 11**. Full 10 km status table:

| Bay | SILVER | SILVER+WEAK | WEAK | UNLABELED |
|---|---:|---:|---:|---:|
| ZJ-HZB | 9 | 4 | 1 | 54 |
| ZJ-SMB | 17 | 0 | 0 | 13 |
| ZJ-YQB | 6 | 5 | 0 | 5 |

**Q6. WEAK counts (10 km, bay-scoped):** HZB 1 WEAK-only (L3 hangzhou
mask, 14.0039 km2 inside envelope); SMB 0; YQB 0 WEAK-only (all weak
presence co-occurs with SILVER). 5 km and 20 km tables are in the v0_1
CSV; 5 km: HZB SILVER 10 / S+W 9 / WEAK 3 / UNL 209, SMB SILVER 43 /
UNL 55, YQB SILVER 17 / S+W 7 / UNL 15; 20 km: HZB 6/3/1/13,
SMB 6/0/0/2, YQB 3/3/0/2.

**Q7. Bay-level vs clipped-cell area error:** zero for HZB and SMB L1
(17.3412 vs 17.3412; 41.6790 vs 41.6790 km2), 0.0054 km2 (0.026%) for
YQB L1 due to independent rasterization; L3 HZB 7e-6 relative;
YQB polygon layers 0.09–0.24% feature/rasterization tolerance. All 54
rows (18 assets x 3 grid sizes) are
`MATCH_WITHIN_RASTERIZATION_TOLERANCE` (rel < 1%). Clipped-cell sums are
computed **per grid size**; summing across the three independent grids
triple-counts and is not a reconciliation.

**Q8. Old/new fingerprints:** v0
`zhejiang_label_cell_overlap_v0.csv` =
`2e204cc1...3867cbd40` (marker sidecar); v0_1 =
`370584b6c1d3b06cd4f6fb22f48a507cee17bdcb041735597d7ae000dcdd15a3`.
Cell ids are identical between v0 and v0_1 at every grid size (identity
did not change; only attribution did). Disagreement layer (HZB,
diagnostic, no relabeling): 4 cells, Jaccard 0.0435 / 0.5942 / 0.7319 /
0.6126. GoldSet reserved cells remain 3
(`ZJ_U51_10K_E032_N313`, `ZJ_U51_10K_E033_N336`,
`ZJ_U51_10K_E034_N320`), recomputed under the clip semantics; no GOLD
promotion occurred.

---

## B. 2022 Sentinel-2 anomaly (Q9–Q18)

Window: `autumn_primary_v1`, DOY 260–320, 10 km COASTAL_RELEVANT cells;
thresholds unchanged: coverage >= 0.99, scene_cloud <= 0.30.

| Stage | HZB | SMB | YQB |
|---|---:|---:|---:|
| A raw census rows | 373 | 147 | 584 |
| B physical unique scenes | 373 | 147 | 584 |
| C autumn scenes | 63 | 26 | 100 |
| D autumn datatake groups intersecting bay | 25 | 25 | 25 |
| E cell x group candidate pairs | 573 | 750 | 400 |
| G coverage-pass pairs (>=0.99) | 399 | 750 | 375 |
| H valid-pixel (SCL) layer | DEFERRED to M2.1b | DEFERRED | DEFERRED |
| I/J v0 cloud pass / final quality pairs | 0 | 0 | 0 |
| I/J R1 contributing-scene cloud / final pairs | **51** | **150** | **89** |

Rejection buckets over all candidate pairs:

| Bucket | HZB | SMB | YQB |
|---|---:|---:|---:|
| LOW_COVERAGE (<0.99) | 174 | 0 | 25 |
| FAIL_CLOUD under both gates | 348 | 600 | 286 |
| RECOVERED (poisoned by non-covering tile only) | 51 | 150 | 89 |
| cloud metadata missing (either gate) | 0 | 0 | 0 |

Buckets reconcile exactly: E = low + G; G = both-fail + R1 final.

**Q9–Q16** are the table above. **Q14 (valid pass):** the pixel-level
SCL valid-layer check does not exist yet — it is explicitly
`DEFERRED_PIXEL_SCL_CLOUD_VALIDATION_TO_M21B`; no pixel number is
claimed. Note the SCL layer could not have caused the geometric
mis-attribution described below.

**Q17. REAL or BUG? — `ZERO_WAS_PIPELINE_BUG`.** The v0 pair cloud gate
computed `max(scene_cloud_fraction)` over **every member of the datatake
group**, including adjacent MGRS tiles whose frame never intersects that
cell. Every 2022 autumn datatake over the region is a multi-tile group
(25 groups; all three bays are intersected by the same 25 cross-bay
groups), and each contains at least one cloudy tile, so 0/0/0 pairs
survived even though 51/150/89 cell events have only clear contributing
tiles. The library docstring already described the intended semantics
("every member scene **contributing geometry** must pass"); the
implementation did not match it.

Datatake verification: 25/25 groups grouped by real
`DATATAKE_IDENTIFIER`; zero groups span multiple UTC dates; groups are
not split by baseline or timestamp; the 14,401-scene supplement covers
all 9,138 physical S2 scenes (0 missing). A deterministic live GEE
spot-check (9 scenes, one `getInfo`, metadata-only) confirmed
MGRS_TILE, DATATAKE_IDENTIFIER, sensing time and cloud percentage
against census/supplement — 9/9 PASS
(`zhejiang_s2_2022_spotcheck_v0.csv`).

**Q18. Affected scope:** the bug is generic to every multi-frame optical
group, not just S2-2022. Archive-wide at 10 km: quality pairs grew from
**56,096 (v0) to 87,231 (v0_1)**; 31,135 pairs were wrongly rejected
(S2 10,154; Landsat 5/7/8/9: 6,422 / 7,268 / 5,116 / 2,175), across
**every year 1986–2026** present in the census. All dependent artifacts
were regenerated as v0_1; v0 bytes are preserved with SUPERSEDED
sidecars. No thresholds were relaxed.

---

## C. Sentinel-1 footprint audit (Q19–Q28)

Method: deterministic sample of **60 IW GRD scenes** (one
`getInfo` on a `FeatureCollection` for actual per-scene geometries;
metadata+geometry only, export guard installed; no pixels). Sampling
strata = bay x orbit direction x relative orbit, candidates in
year-round-robin order, global scene-id de-duplication; **EW
open-ocean scenes excluded** (16 census rows; not a coastal land mode).
Actual footprint areas sanity-checked at 42,800–48,100 km2 (consistent
with IW ~250x170 km).

- **Q19 sample size:** 60 scenes, 1,301 scene x cell rows.
- **Q20 bays:** HZB 25, SMB 18, YQB 17 (a scene can serve multiple bays;
  global unique = 60).
- **Q21 passes:** ASCENDING and DESCENDING both present.
- **Q22 relative orbits:** 69, 171 (ascending), 3, 105 (descending);
  ascending track 98 has only EW scenes here and is correctly absent.
- **Years:** all 12 years 2015–2026 represented.

- **Q23 coverage MAE:** **0.5585** (fraction of 10 km cell area).
- **Q24 P95 abs error:** **1.0000**.
- **Q25 max abs error:** **1.0000** (cells covered by one geometry and
  missed entirely by the other occur 695 and 172 ways).
- **Q26 false eligible** (approx says >=0.99, actual does not): **207**.
- **Q27 false rejected** (actual >=0.99, approx does not): **474**.

Per-stratum highlights: ascending 171 representative frame is shifted
south by tens to ~200 km versus real footprints (HZB stratum MAE 0.95;
373 false rejections); the descending-105 representative polygon spans
~179,000 km2 (bbox ~489x490 km) versus actual ~48,000 km2, producing
false eligibilities (HZB D105: 124).

**Q28 production footprint policy
(`S1_REPRESENTATIVE_FOOTPRINT_NOT_PRODUCTION_GEOMETRY`):**
actual per-scene GEE geometry is the **production eligibility and QA
geometry**; representative frames are a **planning/prefilter estimate
only** and must never be silently used as final pair geometry. This
does not change acquisition groups or any threshold; it governs M2.1b
pair eligibility.

---

## D. Unit semantics (Q29–Q31)

**Q29. 10 km cell role.** The 10 km fixed grid cell is the *observation
unit*: stable identity, archive, spatial-disjoint split/leakage control,
acquisition accounting, and label attribution (via bay clip). It stays
`RECOMMENDED_NOT_FROZEN`.

**Q30. Training chip distinction.** A 10 km cell is **not** a training
chip. Future 256/512-pixel patches must carry `parent_cell_id`; split
membership is decided at cell level so no patch leaks across groups.

**Q31. cell_geometry vs bay_clip_geometry.**
- `cell_geometry`: full fixed square (stable id, archive, split,
  leakage). Label pixels measured on it are recorded as
  `*_full_cell` columns for provenance.
- `bay_clip_geometry = cell_geometry n PROVISIONAL_BAY_ENVELOPE_V0`:
  authoritative geometry for bay-scoped label statistics
  (`cell_label_status_bay_scoped`, `*_bay_clip`); the complementary
  `*_outside_bay_in_cell` quantity is kept explicit. Envelope remains
  PROVISIONAL; if the envelope is revised, clip products re-version.
- UNLABELED is never written as NEGATIVE. The disagreement layer is
  diagnostic only; no labels were re-adjudicated; no GOLD promotion.

---

## E. Reproducibility (Q32–Q34)

All SHA-256 in `zhejiang_m21a2_r1_artifact_fingerprints_v0.csv`.

**Q32. Corrected label:**
`zhejiang_label_cell_overlap_v0_1.csv`
= `370584b6c1d3b06cd4f6fb22f48a507cee17bdcb041735597d7ae000dcdd15a3`;
reconciliation v0_1; disagreement v0_1; builder
`scripts/data/zhejiang/build_label_cell_overlap_v0_1.py`.

**Q33. S2 funnel:**
`zhejiang_s2_2022_funnel_audit_v0.csv`
= `f359eda8dd8c8e96cdb1ddf630cfddbd668ad9061b883073ae862c08b7567d5a`;
verdict JSON
= `4695e36eaf531eace37989f2f894b57ea55da22b063571fc6ed5ccb3db325ed1`;
live spot-check CSV
= `c7f33a46b26ca72d065b2d37c1e44a541b54666b2c752937521fe45cb55e4d84`.
Scripts: `audit_s2_2022_funnel.py`, `spotcheck_s2_2022_gee.py`.

**Q34. S1 audit:**
`zhejiang_s1_footprint_audit_v0.csv`
= `a67148b6236d6f7fbf46936829a58c66257fa21e19e3973abadb331fdba0f700`;
parquet
= `e3a327066a0f44b7c6a5d699017172e0ae29861198d88174cff5328a47337094`;
summary
= `0f67417e3be2bca03d53b94260dd050e9104b81a40de932a804d5d97c3a92f2c`;
policy JSON
= `68e6a015d0497a52a1b3c2dc44a5e3f8986370b32e26fe6540182c793d1d57a3`.
Script: `audit_s1_footprints.py`.

Reproduce:

```bash
conda activate spartina-earth
PYTHONPATH=src python scripts/data/zhejiang/build_label_cell_overlap_v0_1.py
PYTHONPATH=src python scripts/data/zhejiang/simulate_acquisition_groups.py
PYTHONPATH=src python scripts/data/zhejiang/estimate_export_volume.py
PYTHONPATH=src python scripts/data/zhejiang/audit_s2_2022_funnel.py
SPARTINA_GEE_PROJECT=<project> PYTHONPATH=src \
  python scripts/data/zhejiang/spotcheck_s2_2022_gee.py   # 1 getInfo
SPARTINA_GEE_PROJECT=<project> PYTHONPATH=src \
  python scripts/data/zhejiang/audit_s1_footprints.py     # 1 getInfo
```

---

## F. Engineering (Q35–Q39)

**Q35. pytest (unit):** 263 passed (248 prior + 15 new R1 tests in
`tests/unit/test_zhejiang_m21a2_r1_units.py`: contributing-scene gate
regression incl. missing-cloud and SAR NA, funnel count locks and bucket
reconciliation, bay-clip semantics and artifact invariants
(HZB13/SMB17/YQB11, cell-id stability, no NEGATIVE, reconciliation
closure), S1 deterministic sampler, flag consistency, export guard on a
fake ee).

**Q36. gee_integration:** 12 passed, 3 skipped (export smoke tests that
require explicit `SPARTINA_GEE_SMOKE_EXPORT=1`). New:
`test_s2_2022_funnel_spotcheck.py` (9/9 metadata match) and
`test_s1_footprint_audit.py` (60-scene geometry audit). No pixels
read; guards verified.

**Q37. ruff:** `ruff check .` — All checks passed.

**Q38. mypy:** `mypy --strict src scripts` — no issues, 122 files.

**Q39. commits:** four local commits (label clip correction; S2 funnel
audit + contributing-scene gate; S1 actual-footprint audit; R1 docs),
not pushed. See repository log for hashes.

---

## G. Decision (Q40–Q44)

**Q40. Issue #12 blockers:** the three scientific blockers are resolved
with executed evidence; recommendation to reviewer = **PASS / accept
M2.1a2-R1** (subject to review of this report). Nothing is promoted,
frozen, or exported.

**Q41. Is 10 km suitable for the M2.1b pilot?** Yes as the *observation
and accounting unit*: cell identities are stable, bay-scoped label
counts reconcile to direct intersections within rasterization
tolerance, and acquisition pairs are now geometrically and
cloud-gated correctly. It is still `RECOMMENDED_NOT_FROZEN`; training
chips remain a separate concept with `parent_cell_id`.

**Q42. Controlled pixel production ready?** The metadata/geometry
gate is ready. Pixel production still requires: SCL valid-pixel
implementation at M2.1b (the deferred stage H), actual S1 geometry
wired into the production pair builder, and envelope v1 review. So:
**pipeline planning ready; pixel production not yet executed.**

**Q43. First small pilot.** Do NOT start with 303 pairs. Recommended
first pilot (proposal, for user/reviewer approval in M2.1b planning):
one bay (HZB), one autumn window (2022 DOY 260–320), the 13
SILVER-bearing 10 km cells, S2 pairs passing the R1 contributing-scene
gate (51 cell events in-bay; pick the first few cells x dates), SCL
valid-pixel QA executed for the first time, plus a side-by-side S1
actual-footprint comparison. No split freeze and no GOLD promotion in
the pilot.

**Q44. Remaining blockers / known unknowns:**
1. Pixel-level SCL validation does not exist (stage H, M2.1b).
2. Bay envelopes are PROVISIONAL; clip products depend on them.
3. S1 production pair builder must consume actual GEE footprints;
   representative frames are prefilter-only.
4. M2.1a inventory SMB L1 row is CONTRADICTED but preserved; an
   inventory correction version belongs to a later manifest version.
5. Cloud thresholds (0.30) and coverage (0.99) are retained
   deliberately; sensitivity analysis is not part of R1.
6. M0 constraints remain: no bulk GEE download, no GPU training.
