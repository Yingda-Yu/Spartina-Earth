# QA_RADSAT_GRID_ALIGNMENT_REPORT — Phase 2C.2

Scope: only the spatial-grid correspondence of the QA_RADSAT direct
verification for `V021_R00372-C00139_L8_2015_E`. No export, no raster
modification, no VALID-predicate change, no v0.2/Reserve change.

## 1. Frozen grid reconstruction

Frozen export grid (from the landed manifest / plan, identical values):
`EPSG:32651`, affine `(30.0, 0.0, 255330.0, 0.0, -30.0, 3765570.0)`,
width 395, height 383 → 395 × 383 = **151,285 px**. Both the landed
grid and a 30 m GEE scale-grid anchor to exact multiples of 30 in
EPSG:32651 (255330/30 = 8511; 3765570/30 = 125519), so a GEE
`reduceRegion` with `crs='EPSG:32651', scale=30` over the exact grid
rectangle shares the same pixel lattice.

Two execution defects were found and corrected en route (recorded for
transparency): (i) a self-intersecting corner order in the first
polygon attempt produced a bowtie (75,637 px ≈ half); (ii) GEE
`reduceRegion` rejects `dimensions` and `crsTransform`+`scale`
combinations in this API version. The final call uses a proper
`ee.Geometry.Rectangle` with the exact projected bounds and `scale=30`.

## 2. Alignment verification (live GEE, 2026-11-27)

```
scene: LANDSAT/LC08/C02/T1_L2, system:index LC08_119037_20150927
region: exact projected bounds of the frozen grid, EPSG:32651
pixel count sampled: 151,285  ==  landed raster 395 × 383  ✓ PIXEL-PERFECT
QA_RADSAT min = 0, max = 0
```

The earlier Phase 2C.1 read (152,766 px) used a slightly larger
WGS84 rectangle — it is hereby superseded by this grid-aligned read.

## 3. Per-bit statistics on the aligned grid (USGS C2 QA_RADSAT)

| bit | meaning | set pixels |
|---|---|---|
| 0 | Band 1 saturated | 0 |
| 1 | Band 2 saturated | 0 |
| 2 | Band 3 saturated | 0 |
| 3 | Band 4 saturated | 0 |
| 4 | Band 5 saturated | 0 |
| 5 | Band 6 saturated | 0 |
| 6 | Band 7 saturated | 0 |
| 7 | Terrain occlusion | 0 |

**Every QA_RADSAT bit is 0 for every one of the 151,285 aligned
pixels.** Direct verification is therefore pixel-perfect for the
target product: the production VALID predicate's `QA_RADSAT == 0`
term excluded nothing on this cell, consistent with the landed VALID
(XOR = 0, Phase 2C) and with the physical-audit saturation proxy.

## 4. Evidence-status bookkeeping

- Target product: **direct, grid-aligned, pixel-perfect** (this report
  supersedes the scene-region wording of Phase 2C.1 for this product).
- 34 other repair products + 443 panel products: **proxy** labelling
  unchanged and still explicit in
  `QA_RADSAT_EVIDENCE_REPORT.md` §3 (per-scope table) and
  `VALID_MASK_CONSISTENCY_REPORT.md` §3 (proxy method note). The
  `FAILED_PRODUCT_FORENSIC_REPORT.md` §2 saturation line keeps its
  proxy framing for all non-target products.
- VALID predicate: unchanged. No export task created; reads were
  metadata-scale reducers only.

Reproducibility: grid parameters and bit sums saved to
`/tmp/qa_radsat_grid_alignment.json`; commands transcribed in §1–§3.
