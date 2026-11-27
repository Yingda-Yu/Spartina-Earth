# QA_RADSAT_EVIDENCE_REPORT — Phase 2C.1 P0

## 1. Existence and traceability

QA_RADSAT is a standard band of the Landsat Collection 2 Level-2 GEE
collections used by the frozen export machinery. Traceability chain:

1. Production code reads it at build time:
   `scripts/data/national/pilot19_export_products.py::build_landsat`
   line 545 — `radsat = img.select("QA_RADSAT")` — and folds
   `radsat.eq(0)` into the VALID predicate (line 549).
2. The exported task requests therefore carried QA_RADSAT as an input
   dependency of the VALID component (identifiable from the task
   request id and the scene `system:index` recorded in every manifest).
3. The raw QA_RADSAT raster itself was **not exported as a component**
   (component list: `sr`, `valid`, `qapixel` —
   `_LANDSAT_COMPONENTS`, line 201–203), so it is NOT part of any
   landed file.

## 2. Direct re-read for the target product (executed 2026-11-27)

QA_RADSAT **can** be re-read directly from the original GEE scene
(live `ee` metadata-scale read — no export, no modification). Executed
for `V021_R00372-C00139_L8_2015_E`
(`LANDSAT/LC08/C02/T1_L2`, `system:index = LC08_119037_20150927`,
cell region ~120.55–120.66°E / 32.53–32.65°N, 30 m scale):

```
pixels sampled: 152,766
QA_RADSAT min = 0, max = 0
saturated-flagged pixels (any band bit set): 0
```

**Direct verification result: QA_RADSAT == 0 for every pixel over the
cell** — consistent with the landed VALID raster (its QA_RADSAT term
contributed no exclusion here) and with the physical-audit saturation
proxy (0 px outside [-0.30, 1.6022]).

## 3. Evidence status per scope

| scope | QA_RADSAT evidence |
|---|---|
| target product `V021_R00372-C00139_L8_2015_E` | **direct** (live re-read above) |
| 34 other repair products | **proxy** (frozen physical-audit bounds on scaled SR; QA_RADSAT not re-read per product) |
| 443 panel products | **proxy** (same; and production VALID already asserted `QA_RADSAT==0` inside the VALID set at export time) |

The proxy in `VALID_MASK_CONSISTENCY_REPORT.md` §3 and
`FAILED_PRODUCT_FORENSIC_REPORT.md` §2 remains labelled *proxy* for all
non-target products; for the target product it is now superseded by
direct evidence. The original VALID predicate was not changed.

## 4. Reproducibility

Live read command (recorded in `V022_REGRESSION_EXECUTION_REPORT.md`
§4): `ee.Initialize(project=...)` +
`ImageCollection('LANDSAT/LC08/C02/T1_L2').filter(system:index=...)`
+ `select('QA_RADSAT').reduceRegion(minMax/count/sum)` over the cell
rectangle at scale 30. No export task was created.
