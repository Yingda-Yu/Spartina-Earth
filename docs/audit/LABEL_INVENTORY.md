# LABEL_INVENTORY.md

Every label-like artifact found in the incoming `old datasets/` transfer
(git-ignored; see [DATA_INVENTORY.md](DATA_INVENTORY.md) for byte-level
facts), assigned to the closed label-quality vocabulary implemented in
[`src/spartina/labels/__init__.py`](../../src/spartina/labels/__init__.py):

| Tier | Meaning |
|---|---|
| **GOLD** | Field / UAV / expert-verified high-quality labels |
| **SILVER** | Credible government or peer-reviewed mapping products with known provenance |
| **WEAK** | Index/rule/legacy automatic labels |
| **UNLABELED** | Raw EO observations (no label claim) |

Assignment rule for M0: provenance, class semantics, and accuracy evidence
must each be present for SILVER. If any is missing, the artifact starts at
**WEAK** regardless of apparent quality. No artifact here qualifies for
GOLD (no field/UAV/GPS data exists in the transfer).

## 1. Label ledger

| # | Asset (proposed id) | Geometry / encoding | Class semantics | Quantity (VERIFIED unless noted) | Provenance | Starting tier | Upgrade condition |
|---|---|---|---|---|---|---|---|
| L1 | `legacy-china-2015-raster-30m` | Raster mask, EPSG:32650, 30 m, uint16 | VAT contains only `Value=1`; meaning "Spartina" implied by product title, not by embedded metadata | 608,287 positive px = 547.46 km2 | Distributed Chinese 30 m product (folder name); `.rar` timestamps 2020-09; producer/citation/license UNKNOWN | **SILVER candidate, ingest as WEAK** | Identify the published product + citation (`TODO_CITATION`), confirm class table and 0/1 convention, obtain license; then SILVER |
| L2 | `legacy-china-2020-cmssm-polygons` | 148,072 polygons, EPSG:32650, attributes `Id/name/area` | Polygons themselves = Spartina patches (inferred); `gridcode`-like status field absent; no non-Spartina class | 9 provinces; `area` sum 59,371 (unit UNKNOWN) | ArcGIS lineage: OBIA per-province classification, dissolve/merge; item `ChinaSP1025.shp`, 2024-05-22; possibly the map claimed by the multimodal manuscript (UNVERIFIED) | **WEAK** | Confirm authorship link to manuscript, area unit, OBIA rules/input imagery, validation protocol, license |
| L3 | `legacy-hangzhoubay-2015-dtsp-mask` | Raster mask, EPSG:32651, ~30 m, 8-bit palette | VAT 0 (631,692 px) / 1 (15,600 px, ~14.0 km2); meaning of 1 undocumented | 2 classes, binary | Filename `c201511839DTSP_2` opaque; likely a downloaded/reference mask; producer UNKNOWN | **WEAK** | Locate source product/acquisition; verify class table; cross-check against L1/L2 overlap |
| L4 | `legacy-fujian-cmsa-2019` | Polygons, EPSG:4326 | `gridcode=2` only (legend MISSING); `Area_ha` | 78 polygons, 928.85 ha | Same product family as L5/L6; source method UNKNOWN | **WEAK** | Obtain gridcode legend, production method, validation; clean sliver polygons |
| L5 | `legacy-fujian-cmsa-2020` | Polygons, EPSG:4326 | same | 191 polygons, 484.57 ha | zip snapshot dated 2026-01-05 | **WEAK** | same |
| L6 | `legacy-fujian-cmsa-2021` | Polygons, EPSG:4326 | same | 105 polygons, 949.24 ha | same | **WEAK** | same |
| L7 | `legacy-hangzhoubay-2015-sai` | Float64 index raster, EPSG:4326 | Continuous SAI; thresholding rule that turns it into a mask is MISSING | 1,486x482 grid | Manuscript defines SAI conceptually; exact implementation/constants UNVERIFIED | **WEAK index feature, not a label** | Recover SAI formula + threshold + validation; store as derived feature meanwhile |
| L8 | Manuscript sample points (multimodal draft) | Points/pixels, six study areas | Spartina / other-vegetation / non-vegetation | Claimed 2,570 pixels (70% train); six reserves/bays | Described in PDF only | **MISSING** | Recover point table with coordinates; then tier by inspection (likely SILVER if photo-interpreted) |
| L9 | Manuscript sample points (CISNet draft) | Points/pixels, Zhejiang, 1995/2005/2015 | Spartina / background | Claimed Spartina 15,544/16,540/12,347; background 899,050/979,984/887,966 | Described in PDF Table I only | **MISSING** | same |
| L10 | Legacy `cocojson.json` (referenced by tracked legacy scripts) | COCO polygons, Windows-local path | Unknown categories | Unknown | `D:\Spatina Test\cocojson.json`, not on server | **MISSING** | Archival recovery from original machine; audit region/year/source before any tier |

## 2. Quantities that must not be quoted as results

- 547.46 km2 (L1) and 593.71 km2-equivalent (L2, only **if** `area` is
  hectares) are inventory measurements of file contents, **not** validated
  national area estimates. Do not cite them as scientific results.
- The CMSA per-year sums (928.85 / 484.57 / 949.24 ha) come from
  self-describing `Area_ha` fields in a WEAK product with 1 m2 slivers;
  they are not validated change trajectories.
- The ~14.0 km2 Hangzhou Bay positive area (L3) is a window-scoped pixel
  count in an undocumented mask.

## 3. Split handling (binding for M1+)

These labels are spatial products; benchmark rules in
[`benchmarks/spartinashift/SPEC.md`](../../benchmarks/spartinashift/SPEC.md)
apply:

1. **No random image/pixel splits.** L2 carries province codes (`name`)
  that naturally support a province-held-out track; polygons must be
  grouped into spatial units before any split (see
  `src/spartina/evaluation/splits.py`).
2. L1 and L2 are both national products using overlapping underlying
  imagery; a polygon/pixel appearing (even transformed) in both products
  would create cross-split leakage. M1 must compute spatial overlap
  between any derived tiles before assigning folds.
3. L3 (UTM 50N mask) and the Hangzhou Bay index/EO stack (geographic
  degrees) need explicit reprojection before overlap checks; grids were
  VERIFIED to differ (S1 grid is ~3x denser than L8).
4. L4-L6 share the same window as the S2 2019-2025 stacks; using adjacent
  years across train/test is a temporal-leakage risk and must follow the
  temporal split rules in the benchmark spec.

## 4. QA gates before any label can train a model (M1 checklist)

1. SHA-256 every asset; attach JSON manifests per
   `datasets/manifests/schema.json` (22 required fields; `UNKNOWN`/null,
   never guessed).
2. Enumerate band names and value meanings with GDAL/rasterio (the M0
   host has no GDAL): 11-band Zhejiang stacks and 5-band S2 stacks are
   UNKNOWN.
3. Confirm CRS/pixel grids; build overviews; run topology checks on L2/L4-L6
   (slivers, self-intersections, duplicate polygons, `Id=0` placeholders).
4. Verify L2 `area` unit against re-computed geodesic/projected area.
5. Resolve license and redistribution for L1/L2 before any external
   sharing; until then they remain local-only (already git-ignored).
6. Cross-compare L1 (2015), L2 (2020), and L3 (2015 Hangzhou Bay) for
   agreement where footprints overlap; disagreement does not decide which
   is right - it flags a needed adjudication record.
