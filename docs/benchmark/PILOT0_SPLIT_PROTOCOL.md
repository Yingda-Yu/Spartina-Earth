# Pilot-0 leakage-proof split protocol (M1.4 / Issue #4)

- Dataset: Hangzhou Bay 2015 Pilot-0, 30 m analysis grid (EPSG:32651),
  source version `v1` produced by Issue #3
  (`work/hangzhou2015/v1/`, manifests
  `datasets/manifests/hangzhou2015_pilot0_v1.{csv,parquet}`).
- Split registry version: **v1**
  (`benchmarks/spartinashift/pilot0_splits_v1.json`)
- Window manifest:
  `datasets/manifests/hangzhou2015_tiles_v1.{csv,parquet}`
- Config (single source of truth, fixed before any model work):
  `configs/data/hangzhou2015_pilot0.yaml`
- Builder: `scripts/data/hangzhou2015/build_pilot0_split.py`
- Label tiers: SILVER = 2015 national product (evaluation reference),
  WEAK = local legacy mask (auxiliary), IGNORE = uncertainty/disagreement
  buffer. **There are NO GOLD labels in Pilot-0.**
- Patch size, stride, guard and coverage thresholds were selected from
  geometry/coverage statistics only. Nothing here was chosen from model
  accuracy, and no model has been trained on this split.

## 1. Patch-size study (Step 2)

The patch side was not assumed. Connected-component statistics were
computed on the real 1292 x 501 grid for (a) all 30 SILVER components
(12.844 km^2 total) and (b) 91 *material* WEAK-only components
(>= 10 px = 0.90 ha; 4.20 km^2 total), with the pre-declared label
context margin of 9 px (270 m; the SPEC requires >= 250 m).

SILVER component geometry (px, 30 m):

| stat | P50 | P75 | P90 | P95 | P99 | max |
|---|---|---|---|---|---|---|
| bbox width | 12 | 43 | 107.1 | 142.5 | 166.7 | 171 |
| bbox height | 9.5 | 30.8 | 47.2 | 89.4 | 95.8 | 97 |
| equiv. diameter | 7.9 | 17.1 | 37.2 | 52.0 | 80.0 | 88.2 |
| area (ha) | 4.46 | 20.97 | 97.94 | 196.39 | 464.36 | 550.44 |

Material WEAK-only components are small (max bbox 42 x 80 px, max area
81.09 ha equivalent diameter 33.9 px).

Candidate evaluation (stride = P/2, containability includes the 9 px
context margin):

| patch | km | SILVER fully containable | too large | sliding windows | windows with SILVER | disjoint silver blocks |
|---|---|---|---|---|---|---|
| 64 | 1.92 | 0.767 | 6 | 546 | 117 | 31 |
| **96** | **2.88** | **0.800** | **5** | **225** | **64** | **21** |
| 128 | 3.84 | 0.900 | 2 | 114 | 49 | 15 |
| 192 | 5.76 | 1.000 | 0 | 48 | 26 | 7 |
| 256 | 7.68 | 1.000 | 0 | 18 | 13 | 5 |

### Decision: patch = 96 px (2.88 km), stride = 48 px (P/2)

Rationale:

1. 96 px is the smallest candidate that contains 24/30 SILVER
   components (80%) and 90/91 material WEAK-only components (99%)
   together with the 270 m context margin. All percentiles of component
   size up to P95 fit; only 5 very large, elongated coastal meadows
   (P95-P99 width, max bbox 171 px = 5.13 km) exceed the window.
2. Those 5 components are not discarded: they appear in multiple
   overlapping windows within one split, and evaluation against them
   must use coverage-union aggregation (an Issue #5 concern; the
   component registry retains full membership).
3. 96 px keeps 21 spatially independent silver-bearing blocks versus 15
   at 128 px, 7 at 192 px and 5 at 256 px. With three splits, the larger
   candidates leave fewer independent units than components; 64 px loses
   23% of components and 6 components are edge-truncated.
4. The choice is based solely on spatial structure, object sizes and
   the number of independent samples, per Issue #4.

## 2. Tile identity (Step 3)

Tile IDs are a pure function of grid id, row offset, column offset and
patch side:

```
HB2015_R{row:04d}_C{col:04d}_P{patch:03d}
```

e.g. `HB2015_R0192_C0864_P096`. Generation order never appears in the
ID; the same grid + config always yields the same IDs. Implementation:
`src/spartina/data/tiling/ids.py`; parser/regex round-trip tests in
`tests/unit/test_pilot0_tiling.py`.

## 3. Window manifest, no tile materialization (Step 4)

The dataset is a **window manifest**, not a folder of duplicated
GeoTIFFs. Each row records source stack version/checksum, pixel offsets,
UTM/WGS84 bounds, split, SILVER/WEAK/IGNORE/WEAK-only pixel counts and
fractions, per-modality valid fractions and availability flags,
component IDs, eligibility flags and `exclusion_reason`
(34 columns; see `MANIFEST_COLUMNS` in the builder). Windows are read
from the single source stack at training/evaluation time. The only
rasterized artifact is a human QA overview image
(`work/hangzhou2015/v1/previews/split_overview.png`, not committed).

## 4. Macro spatial blocks (Step 5)

The split unit is a contiguous macro stripe, not a window:

- split axis: **columns** (E-W stripes follow the elongated coastal
  window; the 501-row height cannot host three horizontal stripes with
  guards at 96 px),
- ownership boundaries (px, exclusive): train `[0, 803)`,
  val `[803, 1103)`, test `[1103, 1292)`,
- usable window interiors: train `[0, 755)`, val `[851, 1055)`,
  test `[1151, 1292)`.

Boundaries are chosen by an exhaustive deterministic search
(`src/spartina/benchmark/splits/blocks.py`) with hard feasibility
constraints (>= 2 window column tracks per split; >= 5 surviving
SILVER-eval windows per evaluation split after coverage and quarantine
rules) and a lexicographic objective (max SILVER-area deviation from
60/20/20, then viable-window-share deviation, then cut SILVER
components, then cut WEAK components, then valid-area deviation, then
earliest boundaries). No randomness, no window shuffling.

Achieved composition (usable interiors only; guard pixels belong to no
split):

| quantity | train | val | test |
|---|---|---|---|
| SILVER area share | 0.279 | 0.494 | 0.227 |
| optical-valid area share | 0.788 | 0.162 | 0.049 |
| viable windows | 94 | 19 | 7 |
| SILVER-eval-bearing windows | 34 | 11 | 7 |
| SILVER components assigned | 17 | 5 | 5 |
| material WEAK-only components assigned | 77 | 4 | 7 |

The split deviates from 60/20/20 SILVER area because (a) 33.1% of SILVER
pixels fall inside the guard bands and belong to no split, (b) the
val interior [851, 1055) contains the densest SILVER meadow complex and
(c) most optically valid land lies in the west while the eastern test
stripe is dominated by water. Per Issue #4, spatial independence wins
over ratio matching; the imbalance is reported, not repaired by moving
boundaries toward the numbers. Two SILVER components (9.54 ha) and 3
material WEAK-only components (9.09 ha) occur only in guard zones and
are retained in the registry as `GUARD_ZONE_ONLY` — not deleted.

## 5. Guard band (Step 6)

Guard = patch/2 = **48 px (1.44 km) on each side** of every ownership
boundary, i.e. 2.88 km between usable interiors of adjacent splits.

Geometric guarantee: any train window ends at column <= b1 - 48 and any
val window starts at column >= b1 + 48, so cross-split windows are
separated by at least 96 px center-interval (>= 48 px of fully unused
pixels on each side); the same holds for val/test. Within a split the
stride may be 48 px (overlap is allowed because those windows share a
label). Any candidate window crossing an interior edge or entering a
guard zone is excluded with a recorded `exclusion_reason`; the audit
checks `WINDOW_CROSSES_SPLIT_BOUNDARY` and `INSUFFICIENT_GUARD_DISTANCE`
as hard failures. No smaller guard is used, so no exception proof is
required.

## 6. Connected-component isolation (Step 7)

SILVER components (8-connected) and material WEAK-only components are
labelled independently (`src/spartina/benchmark/splits/components.py`)
and carried by ID in every window row. A component that touches both
sides of a chosen boundary is quarantined (option B): it is excluded
from every split and every window touching it is blocked with
`quarantined_component`. In v1 exactly one component is quarantined:

- `silver-0003` (38.43 ha), cut by a split line;
- zero material WEAK-only components are cut.

The hard-fail checks
`SILVER_COMPONENT_IN_MULTIPLE_SPLITS` /
`WEAK_COMPONENT_IN_MULTIPLE_SPLITS` forbid left-half-train /
right-half-test assignments; a synthetic
`fixture_same_component_two_splits` demonstrates the failure.

## 7. IGNORE policy (Step 8)

IGNORE pixels never enter a loss, an evaluation denominator or a
confusion matrix, and IGNORE is never background. Each manifest row
reports `ignore_pixels` / `ignore_fraction`; SILVER/WEAK evaluation
counts exclude IGNORE (`silver_eval_pixels <= silver_positive_pixels`,
audited). The distribution among *placed* windows (fraction P50/P95/max)
is train 0.188/0.654/0.715, val 0.188/0.684/0.688, test
0.470/0.710/0.710. The fixed exclusion threshold is
`max_ignore_fraction = 0.90`; it is non-binding at the optical-coverage
threshold and was set before any model run.

## 8. WEAK-only candidates (Step 9)

WEAK-only regions (WEAK positive, SILVER absent, outside IGNORE) are
preserved, never deleted or relabelled. Components >= 10 px
(0.90 ha) are "material" (91 components, 4.20 km^2), receive stable
`weakcand-XXXX` IDs, area, split membership and train/eval flags, and
are listed per window. They are **forbidden as SILVER evaluation truth**
(`eligible_for_eval` is driven by `silver_eval_pixels` only). Issue #5
must report model responses on these regions separately from SILVER
metrics. No true/false relabelling is performed in M1.4.

## 9. Modality coverage thresholds (Step 10)

Coverage distributions were measured before fixing thresholds (P=96,
225 global sliding windows; optical bins 0.00-0.10: 98, 0.10-0.25: 13,
0.25-0.50: 24, 0.50-0.75: 26, 0.75-1.01: 64). Water windows form a
natural low mode; 0.25 sits in the sparse 0.10-0.25 transition. Fixed
in config before training:

- minimum optical valid fraction: **0.25**
- minimum SAR valid fraction (VV and VH, individually): **0.25**
- minimum indices valid fraction (NDVI & SAI both finite): **0.25**
- maximum IGNORE fraction: **0.90**

A window is excluded if any threshold fails; every trigger is recorded
per window. 144 of 264 candidate windows are blocked (140 optical, 143
SAR, 143 indices, 124 ignore overlap, 2 quarantine — reasons overlap).

## 10. Leakage audit (Steps 11-12)

`src/spartina/benchmark/splits/leakage.py` hard-fails on:

1. shared source pixels across splits;
2-4. train/test, train/val, val/test window overlap;
5. windows crossing split boundaries;
6. insufficient guard distance;
7. a SILVER component in >1 split;
8. a material WEAK component in >1 split;
9. duplicate tile IDs;
10. duplicate source windows;
11. inconsistent CRS;
12. inconsistent transform;
13. source checksum mismatch;
14. invalid label values/fractions/counts;
15. IGNORE-handling errors.

`temporal_identity` duplicates are additionally rejected to reserve the
same-location/year/sensor identity check for future time series (no
temporal data is fabricated in Pilot-0). Synthetic fixtures in
`tests/unit/test_pilot0_leakage.py` (`fixture_overlap_pixels`,
`fixture_same_component_two_splits`, `fixture_guard_violation`,
`fixture_duplicate_tile_id`, `fixture_wrong_checksum`,
`fixture_cross_boundary_window`, plus duplicate-window, CRS/transform,
label/IGNORE and temporal fixtures) all FAIL the audit, while the
committed Pilot-0 manifest PASSES with zero violations.

## 11. Determinism (Step 13)

Two consecutive end-to-end runs (same source manifest, config, code)
produced identical tile IDs, split assignments, CSV bytes, logical JSON
content and fingerprints (only `generated_utc` differs):

- logical manifest fingerprint (sha256):
  `1d178352fad0b08f4dcc5dfb86b8be7050f4a6ae8d94bdc1ddbaf9284421dd80`
- the parquet container hash also happened to be identical
  (`287927eb569ff058...`); container hashes are tracked separately from
  the logical fingerprint because encoders may embed timestamps.

## 12. Reproduction

```bash
conda activate spartina-earth
CUDA_VISIBLE_DEVICES="" PYTHONPATH=src \
  python scripts/data/hangzhou2015/build_pilot0_split.py
```

Input checksum/CRS/shape verification runs first and aborts on any
mismatch with the Issue #3 manifest. `old datasets/` is never written;
all derived bytes live under `work/` or `artifacts/`; only manifests,
config, code, docs and tests are committed.

## 13. Open limitations

- SILVER is a national existence mask with MISSING-EVIDENCE background;
  WEAK is an auxiliary legacy mask; GOLD labels do not exist.
- Val is SILVER-dense (49% of usable SILVER area) and test has only 7
  viable windows; metrics must be reported with these small counts.
- 5 large SILVER components exceed the window and require union
  aggregation; 1 component is quarantined, 2 are guard-only.
- Composite acquisition dates remain UNKNOWN; no sub-10 m GCP check.
