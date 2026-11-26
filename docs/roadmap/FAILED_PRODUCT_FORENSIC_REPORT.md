# FAILED_PRODUCT_FORENSIC_REPORT — V021_R00372-C00139_L8_2015_E

Forensic analysis only: no re-export, no data modification, no QA change.
All numbers below re-measured from the landed files (2026-11-27), not
copied from manifests. Landed file names/SHA-256s: see
`UPDATED_REPAIR_EXPORT_MANIFEST.json` (SHA-256 re-verified 105/105).

## 1. Identity

| field | value |
|---|---|
| cell / year / tertile | CNA10K-R00372-C00139 (Jiangsu, POS) / 2015 / EARLY |
| scene | LC08_119037_20150927 (source LC08_L2SP_119037_20150927_20200908_02_T1, WRS 119/037) |
| acquisition | 2015-09-27 (DOY 270), scene cloud metadata 0.2238 ≤ 0.30 prefilter |
| planned actual-mask (live, pre-export) | 0.98997 (≥ 0.95 → eligible) |

## 2. Landed-file forensics (measured 2026-11-27)

- **GeoTIFF readability**: sr (7-band float32), valid, qapixel — all open;
  CRS EPSG:32651, locked transform equal to plan grid, 30.0 m × 30.0 m.
- **VALID component**: valid pixels **0 / 151,285** (all-zero raster).
- **QA_PIXEL decode** (C2 bit-packed; fill bit is 0 in every pixel —
  0/151,285): 60.6 % `cirrus+cloud` (55052), 31.2 % `cloud` (22280),
  6.0 % `dilated_cloud+cloud_shadow` (23826), 1.9 %
  `dilated_cloud+cirrus+cloud_shadow` (56598), 0.2 %
  `cloud_shadow+clear` (23888). **`clear` bit is 0 in 100 % of pixels**
  → the scene-level cloud metadata (0.22) diverged from the actual
  on-cell condition (fully cloud/shadow-flagged). This is a source-data
  characterization mismatch, not an export defect.
- **Per-band finite fractions** (NaN count over 151,285):
  band_1 0.989999 (1,513 non-finite), band_2 0.996774 (488), bands
  3–7 1.000000.
- **Cross-tabulation (decisive)**: every non-finite band-1/2 pixel lies
  inside a QA_PIXEL cloud/shadow-flagged class (cloud/shadow/dilated
  classes; 0 non-finite pixels in clear classes — and there are no clear
  pixels anyway). The fill bit is never set. Therefore the partial gaps
  are co-located with non-clear pixels and **cannot affect surface
  validity even hypothetically**.
- **Physical audit**: pass (per manifest `qa.physical_audit`; scaling,
  saturation, band order verified by the frozen Phase J audit).
- **Actual observed fraction** (byte-level replay): grid 0.98997, W10
  cell 0.98977 → ≥ 0.95 gate PASS. Planned vs landed delta 0.0002.

## 3. Diagnosis

The product is a **byte-faithful export whose scene was genuinely fully
cloud-flagged over the cell** (QA_PIXEL `clear` = 0 everywhere), with an
incidental ~1 % band-1/2 NaN gap entirely inside non-clear pixels. The
phenomenon is identical in kind to the panel's accepted honest rejection
`V02_R00355-C00151_L8_2015_L` (100 % `cloud`, all bands 100 % finite) —
the only difference is the incidental partial gaps, which the frozen
honest-rejection precondition (`every SR band finite`) treats as
disqualifying. Under the frozen contract the product remains classified
as a hard error and excluded from the accepted denominator; whether that
precondition should be revised is a protocol question addressed in
`V022_QA_PROTOCOL_PROPOSAL.md`, not an agent decision.

## 4. Gate impact

None on counts: the cell retains both-year support via its 2015-MID slot
(landed, QA-clean, finite 1.0, VALID > 0) and three 2020 slots.
