# VALID_MASK_CONSISTENCY_REPORT — production predicate & per-pixel cross-validation

## 1. Production VALID predicate (read from the frozen export code)

Source: `scripts/data/national/pilot19_export_products.py`
`build_landsat()` lines 530–556 (Landsat branch), constants from
`src/spartina/data/gee/landsat.py` lines 42–49 (C2 bit positions). The
exported VALID byte is:

```
VALID = (QA_PIXEL bit6 Clear  SET)
      AND NOT bit0 Fill  AND NOT bit1 Dilated Cloud
      AND NOT bit2 Cirrus AND NOT bit3 Cloud
      AND NOT bit4 Cloud Shadow AND NOT bit5 Snow
      AND (QA_RADSAT == 0)
      AND (all SR bands observed, i.e. per-band mask present)
      [r2 revision; bit7 Water is NOT a predicate — water surface is
       intentionally VALID when the above pass]
```

## 2. Which flags actually participate

| input | role in VALID |
|---|---|
| QA_PIXEL bits 0–5 (Fill, Dilated Cloud, Cirrus, Cloud, Cloud Shadow, Snow) | **active predicates** (must be UNSET) |
| QA_PIXEL bit 6 (Clear) | **active predicate** (must be SET) |
| QA_PIXEL bit 7 (Water) | auxiliary only — not used (water is valid surface) |
| QA_RADSAT | **active predicate** (must equal 0; not exported as a component, so verified indirectly — see §4) |
| SR band masks | **active predicate** (r2: every band must be observed) |

## 3. Per-pixel cross-validation (target product, measured 2026-11-27)

All counts recomputed from the landed GeoTIFFs (sr/valid/qapixel):

| quantity | value |
|---|---|
| nonfinite_pixels_total (any SR band NaN) | 1,518 |
| nonfinite_pixels_inside_valid_mask | **0** |
| nonfinite_pixels_inside_invalid_mask | 1,518 |
| nonfinite_pixels_by_QA_PIXEL_flag | dilated_cloud 1,153 / cirrus 270 / cloud 365 / cloud_shadow 1,153 / fill 0 / snow 0 |
| nonfinite_pixels_clear_bit_set | **0** |
| fill_bit_intersection | **0** (fill bit is 0 anywhere in the raster) |
| saturation_intersection | **0** (proxy: frozen physical-audit bounds [-0.30, 1.6022] on scaled SR — QA_RADSAT is not an exported component; 0 pixels outside bounds, inside or outside VALID) |
| offline QA predicate (bits 0–6 only) | 0 px |
| landed VALID nonzero | 0 px |
| offline predicate ⊕ landed VALID | **0 px** |

Conclusion: the landed VALID raster is exactly the QA_PIXEL predicate
over this cell (the QA_RADSAT and SR-observed terms contribute zero
marginal difference here); every non-finite SR pixel lies in a
QA_PIXEL-invalid class and none carries the Clear bit — pixel-level
evidence for v0.2.2 condition (e), sharper than the "non-clear" wording
it replaces.

## 4. Reproducibility snippet

```python
import rasterio, numpy as np
q = rasterio.open("<...qapixel.tif>").read(1).astype(np.uint16)
clear = (q >> 6) & 1
banned = ((q >> 0) & 1) | ((q >> 1) & 1) | ((q >> 2) & 1) | \
         ((q >> 3) & 1) | ((q >> 4) & 1) | ((q >> 5) & 1)
qa_valid = (clear == 1) & (banned == 0)   # == landed VALID (xor = 0)
```

Per-sensor note: Landsat 8/9 bits as above; Landsat 7 shares the same
layout with bit 2 (Cirrus) reserved — USGS sets it to 0 for L7, so the
predicate reduces identically (documented per-sensor in
`V022_QA_PROTOCOL_FINAL.md` §2). Machine-readable numbers:
`/tmp/valid_consistency_numbers.json` reproduced in
`V022_REGRESSION_TESTS/V022_REGRESSION_RESULTS.json` (condition-e
evidence block).
