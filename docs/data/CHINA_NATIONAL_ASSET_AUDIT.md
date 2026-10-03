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

---

## 4. Official CM-SSM archive verification (Issue #14, 2026-10-03)

The pre-existing local copy under
`old datasets/30mSpartinaChina/2020/CM-SSM/` was compared byte-for-byte
against the publisher archive:

* Archive: `CM-SSM.zip` from Zenodo record 16296823
  (DOI 10.5281/zenodo.16296823), 77,339,180 B,
  md5 `f1f2592ca5d965fa8bf6a008a3fa1a73` (matches Zenodo file metadata),
  sha256 `93411e765d185b5ae48a84850a1773776e6308bd56a433fa553c23dc49b66238`.
* All 8 shapefile components (shp/shx/dbf/prj/cpg/sbn/sbx/shp.xml) are
  SHA256-identical between the local copy and the extracted archive.
* Verdict: **VERIFIED_CM_SSM_2020**. The local copy is the unaltered
  published dataset, not a derived variant. Full record:
  `docs/audit/vector_reports/30mSpartinaChina__2020__CM-SSM__OFFICIAL_IDENTITY.json`;
  download passport: `work/external/cm_ssm_2020_official/SOURCE_PASSPORT.json`.
* Method context is now paper-documented (Xu, Tian, Zhou et al.,
  *Earth System Science Data* 17, 6601-6624, 2025,
  DOI 10.5194/essd-17-6601-2025): OSPPF, Sentinel-2 phenological
  features + 0.9 m Google Earth RGB, multi-scale object segmentation +
  Random Forest (200 trees) + manual refinement; 1,396 field DGPS points
  in three southern validation sites; reported OA 96.76 % / F1 0.95.
  Reported figures remain paper-held until independently reproduced.

**SOURCE_LICENSE_CONFLICT**: Zenodo record metadata and DataCite both
declare **CC-BY-4.0**; the NESDC mirror of the same DOI declares
**CC-BY-NC-4.0**. Per project policy the permissive license was not
auto-selected: analysis/validation proceed, internal training,
redistribution and commercial model release remain **UNKNOWN** pending
contributor clarification. See
`datasets/manifests/china_spartina_label_products_v0.csv`.

## 5. Family access ledger (no login/order wall was bypassed)

| Product | DOI / id | Access state | Evidence |
|---|---|---|---|
| 1990 Spartina map | 10.12041/geodata.195159798810196.ver1.db | BLOCKED_BY_ORDER (0.23 MiB listing) | portal landing page only |
| 2000 Spartina map | 10.12041/geodata.140184217931452.ver1.db | BLOCKED_BY_ORDER (592 KiB; Krasovsky Albers; OBIA) | portal landing page only |
| 2015 30 m product | 10.12041/geodata.65372070926827.ver1.db | local copy present; byte-identity to ordered archive RELATIONSHIP_UNKNOWN | measured 547.46 km2, 608,287 px |
| 2020 "30 m Spartina" entry | 10.12041/geodata.254533427778392.ver1.db | EXISTS_WITH_METADATA_CONTRADICTION (Spartina title, mangrove abstract) | do not use until clarified |
| 2010 30 m Spartina | — | NOT_FOUND | no fabricated row created |
| CMSA 2017-2021 | 10.12199/nesdc.ecodb.mon.2026.013 (CSTR …2026.017) | OPEN_WITH_PURPOSE_REGISTRATION; 6.1561 GB aggregate zip, JWT download; not obtained | 5 per-year rows registered; archive contents unaudited; CC-BY-NC-4.0 |
| CM-SSM 2020 | 10.5281/zenodo.16296823 | DOWNLOADED + byte-verified (section 4) | identity audit JSON |

Portal metadata defect for CMSA: temporalCoverage text says 2017-2020
while title/description say 2017-2021 (TODO_VERIFY). The 58,006 ha CMSA
figure quoted in the CM-SSM paper is a comparator number for 2020 only,
not an independently verified per-year area; the paper also reports
57.73 % spatial discrepancy and ~17x patch-count differences between
CM-SSM and CMSA — evidence that the two 2020 maps are **not
geometry-equivalent** and their difference is not change.

## 6. Cross-decade comparability rules (family level)

1. The 1990 and 2000 products remain **unobtained**: no area, accuracy
   or geometry claim about them enters manuscripts; their slots are
   access-state evidence, not data.
2. 2015 (30 m Landsat raster) vs 2020 (0.9 m Google-Earth/Sentinel-2
   polygons): area delta 547.46 -> 593.71 km2 stays DESCRIPTIVE ONLY
   (section 2); no change map.
3. CMSA per-year products 2017-2021 may only be compared *after* the
   archive is obtained, its contents audited year by year, projection
   and semantics verified, and the CC-BY-NC consequence for derived
   releases resolved.
4. Any long-term product must be traceable through
   source -> preprocessing -> label -> model -> checkpoint -> output,
   and differences between maps must be reported as spatial
   disagreement with uncertainty, never as net-area change.

## 7. National domain and cell strata (Issue #14, v0)

Built deterministically from passported inputs only
(GSHHG 2.3.7 LGPL; Natural Earth 5.1.1 public domain):

* coastline-specific corridor (seaward = buffer(China, W) minus *all*
  GSHHS land; onshore = land within W of that water), so inland
  international borders never enter the domain;
* small-island recovery rule (polygons <= 100 km2 whose representative
  point lies within 25 km of the China polygon and outside every other
  admin-0 polygon, excluding polygons already inside the China polygon):
  3,093 islands, 1,898 km2;
* cell inclusion requires >= 1 % of the 10 km cell to intersect the
  corridor (removes border slivers).

| Width | Corridor km2 | Albers cells | UTM-zone cells (49/50/51/52) |
|---|---|---|---|
| 5 km | 142,048 | 2,542 | 2,771 (719/792/1250/10) |
| 10 km | 235,984 | **3,319** | 3,670 (963/1058/1630/19) |
| 20 km | 388,139 | 4,767 | 5,341 (1423/1571/2304/43) |

Sensitivity: full-resolution (f) GSHHS sensitivity is within +4/+1/+6 Albers cells at
W5/W10/W20 (<=0.16 %, see DOMAIN_BUILD_v0.json); without island recovery
W10 = 2,912 (-12.3 % relative to the canonical 3,319).
UTM and Albers cover equal ground (332,713 vs 332,000 km2) but UTM
double-counts along the 114 E and 120 E seams (75 + 301 overlapping
cell pairs; pairwise overlap 2,038 + 8,026 km2), so **Albers is the
seam-free canonical lattice**, UTM retained only for sensor-native
checks. Full artifacts: `docs/data/national/DOMAIN_BUILD_v0.json`,
bytes/cell lists regenerated by
`scripts/data/national/build_national_domain.py`.

W10 strata (Albers, v0): 406 SILVER_2015_POSITIVE, 812
SILVER_2015_NEARBY-only, 385 CMSSM_2020_POSITIVE, 482 cells positive
in either obtained product, 2,913 UNLABELED_COASTAL (absence of
evidence, not negatives). CMSA/MANAGEMENT/GOLD strata are
DESIGNED_NOT_BUILD with reasons in
`docs/data/national/CELL_STRATA_v0.json`.

Tier scale with measured counts (model estimates,
`docs/data/national/NATIONAL_TIER_MODEL_v0.json`): Tier0 metadata
census 0.53 GiB over 139,440 cell-years; Tier1 482 cells ~83 GiB;
Tier2 standard national year ~572 GiB; Tier3 full 42-year archive
~137 TiB of raw product equivalents — the archive is deliberately
staged, never bulk-downloaded in M0/M1.
