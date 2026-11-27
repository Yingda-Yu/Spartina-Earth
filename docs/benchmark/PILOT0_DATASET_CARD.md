# Pilot-0 dataset card — Hangzhou Bay 2015 leakage-proof split (v1)

> This is NOT a high-quality ground-truth dataset. Pilot-0 has **no GOLD
> labels**; it is a small, fully traced pilot for validating the
> leakage-proof tiling and split machinery before M1.5 baselines.

## Identity

- Name: Hangzhou Bay Pilot-0 window manifest v1
- Dataset id: `hangzhou2015_pilot0`; grid id: `HB2015`
- Region: Hangzhou Bay coastal window, China
  (bounds and per-tile WGS84 coordinates in the manifest)
- Year: nominal **2015**; actual composite/individual acquisition dates
  are **UNKNOWN** (date recovery in M1.2 could not establish them from
  the available evidence; see `docs/data/HANGZHOU_2015_PILOT0_SPEC.md`)
- Split registry: `benchmarks/spartinashift/pilot0_splits_v1.json`
- Window manifest: `datasets/manifests/hangzhou2015_tiles_v1.csv` /
  `.parquet` (264 candidate windows: 120 assigned, 144 blocked with
  documented reasons; rows are windows on ONE source stack, not copied
  imagery)

## Grid and geometry

- CRS: EPSG:32651 (UTM zone 51N)
- Resolution: 30 m analysis grid; extent 1292 x 501 px
- Source transform: `(30, 0, 309290, 0, -30, 3364370)`
- Model window: 96 x 96 px = 2.88 x 2.88 km; stride 48 px
- Splits are column-wise contiguous macro stripes with 48 px (1.44 km)
  guard bands on each boundary:
  - train ownership `[0, 803)`, usable `[0, 755)`
  - val ownership `[803, 1103)`, usable `[851, 1055)`
  - test ownership `[1103, 1292)`, usable `[1151, 1292)`
- Random window/pixel shuffling is impossible by construction; tile IDs
  are geometry-derived (`HB2015_R{row:04d}_C{col:04d}_P{patch:03d}`).

## Modalities (11-band float32 source stack)

1-7. Landsat 8 Collection 2 Level-2 surface reflectance bands
     (transformed DN x 2.75e-5 - 0.2; DN 0 = fill -> NaN)
8.    NDVI
9.    SAI (Spartina alterniflora index; legacy rule)
10.   Sentinel-1 VV (dB)
11.   Sentinel-1 VH (dB)

Per-window valid fractions are recorded for optical, VV, VH and indices.
Windows below 0.25 valid fraction in any modality (or above 0.90 IGNORE)
are blocked; thresholds were fixed from the coverage distribution before
any model work.

## Labels (tiers)

- **SILVER**: 2015 national Spartina mapping product, nearest-neighbour
  warped from EPSG:32650. Evaluation reference for Pilot-0. It is an
  existence mask; its background semantics are MISSING EVIDENCE, not
  verified absence.
- **WEAK**: local legacy mask (index/rule-derived lineage). Auxiliary
  only; never written as ground truth.
- **IGNORE**: disagreement / boundary-uncertainty pixels (60 m boundary
  buffer). Never used as loss target, evaluation denominator, background
  class or confusion-matrix entry.
- **WEAK-only candidates**: WEAK positive / SILVER absent outside IGNORE
  are retained by component ID (91 material components >= 0.90 ha) and
  must never serve as SILVER evaluation truth.
- **GOLD labels: NONE.** No field, UAV or expert-verified pixels exist in
  Pilot-0.

## Composition

| quantity | train | val | test |
|---|---|---|---|
| viable windows | 94 | 19 | 7 |
| SILVER-eval-bearing windows | 34 | 11 | 7 |
| usable SILVER area share | 0.279 | 0.494 | 0.227 |
| optical-valid area share | 0.788 | 0.162 | 0.049 |
| SILVER components | 17 | 5 | 5 |
| material WEAK-only components | 77 | 4 | 7 |
| mean optical valid fraction | 0.780 | 0.753 | 0.523 |
| mean IGNORE fraction | 0.251 | 0.280 | 0.533 |

One SILVER component (38.43 ha) is quarantined at a split boundary;
2 SILVER and 3 material WEAK-only components occur only in guard zones.
33.1% of SILVER pixels lie inside guard bands and belong to no split.
SILVER/WEAK raw agreement was Jaccard 0.493 (0.953 after the 60 m
boundary buffer) in the Issue #3 arbitration — the two sources genuinely
disagree over large areas.

## Provenance and verification

- Every source asset has a sha256 in
  `datasets/manifests/hangzhou2015_pilot0_v1.csv`; the builder aborts on
  checksum/CRS/shape mismatch.
- Every manifest row carries `source_stack_version` and
  `source_stack_checksum`; chain: source scene -> preprocessing
  (Issue #3) -> labels -> split config -> window manifest.
- Logical manifest fingerprint (sha256):
  `1d178352fad0b08f4dcc5dfb86b8be7050f4a6ae8d94bdc1ddbaf9284421dd80`;
  split generation is deterministic across reruns.
- Leakage audit: 15 hard-fail checks + reserved temporal identity;
  zero violations on v1; deliberate fault fixtures are tested.
- Derived bytes live outside Git (`work/`, `artifacts/`); Git stores
  only manifests, configs, code, docs and tests.

## Known limitations

1. No GOLD labels; SILVER background is not verified absence; WEAK is a
   legacy rule mask. The SILVER/WEAK disagreement is unresolved.
2. Acquisition-date provenance is UNKNOWN for the nominal-2015
   composite; the stack must not be described as a dated 2015 product.
3. No sub-10 m GCP co-registration verification was performed;
   cross-sensor alignment is inherited from the Issue #3 30 m
   co-registration (documented RMS residuals therein).
4. Test is small (7 viable windows, 5 SILVER components) and the val
   stripe holds 49% of usable SILVER area; uncertainty on test metrics
   will be large and must be reported as such.
5. Five large SILVER components exceed the 2.88 km window; evaluation
   must aggregate overlapping windows by coverage union.
6. Optical/SAR coverage is strongly imbalanced (open water dominates the
   east); the split preserves spatial independence rather than ratio
   balance, by design.
7. Data licenses remain item-specific and restricted (see
   `DATA_LICENSE.md`); national and local label products are not
   open-data assets. Do not redistribute rasters.

## Intended use / forbidden use

- Intended: developing and auditing the SpartinaShift split pipeline,
  and weak-only exploratory baselines in M1.5 that report SILVER and
  WEAK-only responses separately.
- Forbidden: presenting labels as GOLD, treating IGNORE as background,
  using WEAK-only candidates as SILVER truth, mixing windows or
  components across train/val/test, or selecting thresholds/splits from
  model results.
