# Hangzhou Bay 2015 Pilot-0 — Co-registration & Grid Report (M1.3)

Outputs: `artifacts/audit/pilot0/coregistration.json`,
`work/hangzhou2015/v1/grid_spec.json`
Script: `scripts/data/hangzhou2015/coregister.py` (deterministic)

Pre-declared tolerances (fixed before running):
optical↔label ≤ **15 m**; S1↔optical ≤ **10 m**.
Gate result: **PASS** (`alignment_gate.pass = true`).

All measurements were made by warping every source onto the common
EPSG:32651 grids and comparing *content* (edge normalised
cross-correlation, NCC). Footprint-rectangle differences are reported
separately because they are export-origin phase, not image shifts.

---

## A. Same region / same reasonable period?

**Same region: YES (geometrically).** All six rasters cover the same
window when projected to UTM 51N; edge content correlates at zero lag
(see C) and the label mask sits inside the optical/SAR coverage.

**Same period: PARTIALLY SUPPORTED, dates UNKNOWN.** All filenames and
composites say 2015; the manuscript gives nominal 2015 dates
(08-15 / 09-01 / 10-03) that match no real L8 overpass, and the TIFFs
carry no acquisition tags. L8 NDVI phenology and S1 are 2015 annual /
multi-date composites by construction. Exact scene sets and the
compositing rule are **MISSING_EVIDENCE** — see the date inventory in
`artifacts/audit/pilot0/date_recovery.json` (77 L8/L7 C2-L2 scenes and
25 S1 GRD scenes intersect the window in 2015).

## B. Why is S1 ~3× denser? Native resolution / resampling?

- Source S1 rasters are 4 456×1 445 in EPSG:4326, i.e. 8.64×9.96 m
  ground sample distance — exactly 3× the optical raster pixel count
  per axis. This matches Sentinel-1 IW GRD **~10 m native pixel
  spacing**, not Landsat's 30 m.
- The files are float dB composites (VV −29.1…20.8 dB, mean −12.56;
  VH −40.1…8.7 dB, mean −20.03) with overviews.
- Factor-3 nearest-neighbour-upsampling test on the 10 m grid
  (`resampling_signature`): identical 3×3-block share = **0.0**
  (synthetic NN control = 1.0); high-frequency energy above 1/60 m
  cycles ≈ **4.1 % (VV) / 3.9 % (VH)**. The S1 products therefore
  carry genuine fine-grid information and are **not** a factor-3 NN
  enlargement of a 30 m product. Whether the composites were
  resampled from a slightly different native grid (e.g. 10→8.64 m
  during the geographic projection) cannot be determined from the
  file; **MISSING_EVIDENCE** on the original projection/processing
  chain.
- For modelling v1 keeps both: S1 at its own 10 m-density grid and
  bilinear-warped S1 at 30 m in the stack. The 30 m Landsat grid is
  never upsampled and presented as 10 m information.

## C. Is the ~17 m offset real?

The M1.1 footprint comparison found S1 rectangle edges offset from the
mask rectangle (west edge +17.29 m, north edge −10.26 m, east
−0.14 m, south 0 m). Content-based co-registration:

| Pair (grid) | best integer lag | subpixel dx/dy (px) | shift E/N (m) | peak NCC | sharpness |
|---|---|---|---|---|---|
| S1 VV vs optical NDVI (10 m) | (0, 0) | +0.28 / −0.13 | **+2.8 / +1.2** | 0.226 | 0.009 |
| S1 VH vs optical NDVI (10 m) | (0, 0) | +0.20 / −0.11 | **+2.0 / +1.1** | 0.221 | 0.013 |
| WEAK mask edge vs optical NDVI (30 m) | (0, 0) | +0.31 / +0.04 | **+9.3 / −1.2** | 0.010 | 0.0004 |

- Best **integer lag is (0,0) for every pair**: no shift of one whole
  pixel exists at either grid.
- Sub-pixel estimates are 2–3 m for S1 (below one 10 m pixel) but the
  NCC peaks are weak/broad (cross-sensor optical–SAR edges genuinely
  correlate weakly), so these are reported as "<~3–5 m, not sharply
  estimable", not as surveyed offsets.
- The mask-edge sub-pixel value (~9 m) comes from an essentially flat
  NCC surface (peak 0.010, sharpness 4e-4): vegetation-boundary vs
  diffuse-NDVI-edge matching is not a reliable GCP signal. It is
  within the 15 m tolerance but should **not** be quoted as a measured
  9 m shift.
- Independent label-level check: Jaccard between SILVER and WEAK was
  scanned over integer translations ±5 px; the global maximum is
  exactly at **(0,0)** (`systematic_shift_scan.peak_at_zero = true`),
  ruling out a residual systematic translation between label maps.

**Answer:** the ~17 m figure is an export-rectangle origin/phase
difference (different raster origins, e.g. 309 313 E vs 309 290 E
anchor), **not** a 17 m misregistration of image content. Content is
aligned to within one 30 m pixel (best case <~10 m). Validation with
stable man-made controls (seawalls, roads, jetties) on best-available
imagery remains an **owner task**; no high-resolution imagery was
downloaded in M0/M1 (bulk download prohibited), and open-water edges
are unstable controls.

## D. Which grid is the analysis grid?

**30 m UTM-51N anchored grid** (origin 309 290 E / 3 364 370 N,
1 292×501). Reasons:

1. It is the native resolution of both labels (mask 29.98×29.95 m;
   national product 30 m) and of Landsat — the label geometry is
   preserved with nearest neighbour without invented detail.
2. It avoids presenting 30 m optical information at 10 m (integrity
   rule #7).
3. S1 ~10 m content is preserved separately on the 10 m-density grid
   and only aggregated for the fused stack; Issue #5's
   optical-vs-SAR comparisons can therefore use a defensible grid.
4. Deterministic anchor at the UTM false easting gives stable tile IDs
   for Issue #4 across future windows.

## Gate and limitations

- Gate: S1-VV 3.1 m, S1-VH 2.3 m, mask 9.3 m (weak peak) — all within
  pre-declared tolerances; **PASS**.
- Bilinear resampling of continuous data and nearest-neighbour for
  labels were declared before running and recorded in the SPEC.
- No ground control points were surveyed; sub-pixel accuracy beyond
  "within one pixel" is **not claimed**.
