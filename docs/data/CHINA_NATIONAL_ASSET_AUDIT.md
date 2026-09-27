# National China assets — 2015 raster vs 2020 CM-SSM comparability (M1.1)

## 1. The two products (independently measured)

### 2015 raster product
`30mSpartinaChina/30m…(2015年)-数据实体/…tif` (+ `.tfw/.ovr/.aux.xml/
.vat.dbf`, duplicate `.rar`)

- BigTIFF, int16, **45,282×67,077**, 1 band, tiled 128×128, no
  compression; EPSG:32650 (WGS 84 UTM zone 50N); 30.0 m; origin
  (−345,246.5 E, 4,341,513.4 N); nodata **255**; valid values: **{1}**
  only (background encoded as nodata, no 0 class).
- Windowed full-scan counts: value-1 pixels **608,287**; nodata
  3,036,772,427; sum = 3,037,380,714 = width×height exactly.
- Dataset-native area: 608,287 × 900 m² = **547.4583 km²**
  (54,745.83 ha). This independently reproduces the VAT `Count=608287`
  ⇒ product-internal figure **VERIFIED by recomputation** (M0 draft
  said dtype uint16; rasterio evidence: **int16** — corrected).
- Caveat: UTM zone 50N applied nationwide; 547.46 km² is the product's
  planar convention. A geodetic per-pixel/polygon area cross-check is
  TODO (coastal China spans ~zones 43–53; expect order-≤1% effects).

### 2020 vector product
`30mSpartinaChina/2020/CM-SSM/CM-SSM.shp`

- 148,072 single-part polygons, EPSG:32650; fields `Id`, `name`
  (province), `area`; lineage item name **ChinaSP1025.shp**, created
  2024-05-22, later merges 2024-10 (1016/1023/1025 steps).
- ArcGIS XML lineage: per-province **OBIA** classification results
  (e.g. `…\OBIA_FJ_class_result\fj001_clip.shp`, paths also named
  `D:\Deep Learning\XMproduct\fj2020\…`) → Dissolve (SINGLE_PART) →
  Merge across provinces → CalculateField province names →
  `CalculateGeometryAttributes area AREA … 公顷` (UTM 50N).
- `area` unit: **hectares, confirmed two independent ways** — ArcGIS
  lineage says 公顷, and computed geometry/field ratio =
  9,999.99999999; sum **59,370.98 ha = 593.710 km²**.
- Geometry QA: 0 empty, 0 duplicates; **2,402 self-intersecting rings**
  (1.6%); **100,455 features <100 m²** (67.8% of features; fragmentation
  from dissolve/OBIA — use unioned area, not feature counts).
- Province table:

| Province | Features | Area (ha) | Area (km²) |
|---|---|---|---|
| SH | 24,566 | 18,860.39 | 188.604 |
| JS | 24,180 | 15,482.55 | 154.826 |
| ZJ | 39,764 | 13,390.84 | 133.908 |
| FJ | 28,619 | 8,125.36 | 81.254 |
| SD | 9,490 | 1,798.50 | 17.985 |
| GX | 12,658 | 1,168.55 | 11.685 |
| GD | 2,082 | 317.33 | 3.173 |
| TJ | 6,203 | 212.01 | 2.120 |
| HB | 510 | 15.46 | 0.155 |

(LN appears in an intermediate Merge step but is absent from the final
`name` set; ZJ/TJ appear only in later merges. Final coverage: 9
province-level units.)

## 2. Can 2015 and 2020 be compared as change? — NO in M1.1

| Comparability axis | 2015 raster | 2020 CM-SSM | Risk |
|---|---|---|---|
| Geometry model | raster cells, background=nodata | dissolved polygons | sliver/min-mapping-unit differences dominate small changes |
| Resolution / MMU | 30 m pixels (900 m² MMU floor) | polygons down to 0.81 m², 68% <100 m² | 2020 maps sub-Landsat objects; not resolution-equivalent |
| Method | unknown (packaged dataset, no lineage file) | OBIA/deep-learning class results + ArcGIS dissolve (XML) | different classifiers ⇒ systematic bias unknown |
| Species/criterion | undocumented class definition | undocumented; "sp" two-product pipeline, no legend semantics | "Spartina" may include different cover thresholds |
| Coastline extent | single national raster extent | 9 units; LN dropped along the way; no documented exclusion criteria | extent differences masquerade as change |
| CRS/area basis | UTM 50N planar 30 m | UTM 50N planar hectares | same convention (good); geodetic check still open |
| Headline area | 547.46 km² | 593.71 km² | **+46.25 km² (+8.4%) — DESCRIPTIVE ONLY**, not a measured change |
| Geometry health | n/a (thematic cells) | 2,402 self-intersections | topology must be repaired on a *copy* before overlay |

No change detection, difference map or "increase/decrease by province"
is produced in M1.1. Doing so would mix methods, MMUs and extents and
violate the no-fabricated-result rule.

## 3. What is required before any 2015→2020 comparison (M1.2+)

1. Recover 2015 producer, class legend, mapping unit and license
   (DATA_PROVENANCE_AND_LICENSE.md); geodetic area check.
2. Document CM-SSM OBIA classifier, inputs (imagery dates/sensors),
   province pipeline and why LN is absent; repair geometry in `work/`.
3. Harmonize to a common MMU and area basis; report disagreement on a
   common grid with uncertainty, not net area arithmetic.
4. Independent validation (GOLD/SILVER) for both epochs.
