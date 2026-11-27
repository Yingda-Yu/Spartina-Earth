# Label quality re-tiering and Hangzhou mask provenance investigation (M1.1)

Tier policy (AGENTS.md §5): **GOLD** = field/UAV/expert-verified;
**SILVER** = credible government or peer-reviewed mapping product with
*known provenance*; **WEAK** = index/rule/legacy automatic labels;
**UNLABELED** = raw EO composites. Provenance unknown ⇒ cannot be
awarded SILVER on filename goodwill.

## 1. Tier decisions (asset-level)

| Asset | Form | Evidence used | M1.1 tier |
|---|---|---|---|
| 2015 national raster (`30m…2015年)-数据实体.tif`) | 0/1 (nodata 255), int16, 608,287 px | geodata.cn product identified (DOI 10.12041/geodata.65372070926827.ver1.db; IGA/CAS Wang Zongming team; object+SVM, field-validated OA 92%; see DATA_PROVENANCE_AND_LICENSE.md) | **SILVER** (redistribution restricted; order record still to be attached) |
| CM-SSM 2020 polygons | 148,072 polygons | ArcGIS XML lineage (OBIA + dissolve, 2024-05-22, local Windows paths); 2,402 self-intersecting rings; 100,455 features <100 m²; 593.71 km² | **WEAK** (legacy automatic OBIA output; publication link unconfirmed) |
| Hangzhou 2015 mask `c201511839DTSP_2.tif` | 0/1, 15,600 px | see §2; origin unresolved; disagrees with paper Table I count | **WEAK** (legacy automatic label); **not usable as GOLD test truth** |
| CMSA 2019/2020/2021 polygons | 78/191/105 polys | legacy shapefiles, `gridcode=2`, Area_ha; no method/producer metadata | **WEAK** (legacy automatic labels) |
| Zhejiang 11-band stacks ×2 | float32 composites | raw derived features, no labels | **UNLABELED** (feature stacks) |
| Hangzhou L8/NDVI/SAI/S1 ×5 | composites | features only | **UNLABELED** |
| Fujian S2_2019…2025 ×7 | `B4,B3,B2,NDVI,NDWI` | composites only; no cloud/date metadata | **UNLABELED** |

**Counts: GOLD = 0; SILVER = 1 (2015 national raster; geodata.cn product
identified 2026-09-27); WEAK = 5 label products (2020 CM-SSM, Hangzhou
mask, CMSA ×3); UNLABELED feature assets = 15 GeoTIFF composites.**

No field GPS, UAV maps, expert-verified polygons, or signed validation
records exist anywhere in the 82 assets ⇒ **there is currently no GOLD
label in the entire evidence store.**

## 2. J-1: Hangzhou 2015 mask (`c201511839DTSP_2.tif`) — origin test

Facts established from bytes:

- uint8 thematic 0/1; 1,292×501; EPSG:32651; ~29.98×29.95 m/px;
  positives **15,600** (14.004 km² at native pixel area 897.694 m²);
  negatives 631,692; no nodata; VAT/histogram sidecars agree
  (`15600`), ArcGIS-style `.sr.lock` files present.
- Footprint reprojects **exactly** to the L8/NDVI/SAI grid bounds
  (`309298.053 E … 3364366.757 N`), i.e. the GEE exports were cut to
  this mask's rectangle (see HANGZHOU_2015_ALIGNMENT_AUDIT.md).
- Paper Table I prints **12,347** S. alterniflora sample pixels for
  2015 ≠ 15,600.

Hypotheses tested:

1. **Window of the national 2015 product?** Nearest-neighbour in-memory
   comparison on the national UTM-50 grid: national positives in window
   14,319; reprojected mask positives 15,618; agreement only 9,934;
   national-only 4,385; mask-only 5,684; **Jaccard = 0.497**.
   ⇒ REJECTED as a direct crop/reprojection; the two products disagree
   on roughly half the positive area (artifact JSON:
   `artifacts/audit/hangzhou_mask_origin_check.json`).
2. **SAI threshold product?** On the L8 grid, mask-positive pixels have
   SAI mean **−0.384** (median −0.386) vs mask-negative −0.141
   (−0.108) — positives are *more negative*. The index was later
   published as SAI = (Red−NIR)/NIR (Zuo et al. 2025,
   DOI 10.34133/remotesensing.0510), under which dense green
   *Spartina* gives more **negative** values; the mask polarity is
   therefore *consistent* with a low-SAI (negative) threshold rule.
   However no threshold value, date/composite config or producing
   script exists, so threshold origin remains **plausible but
   unproven** (MISSING_EVIDENCE for the exact rule).
3. **Manual digitisation / GOLD?** No field/UAV/expert metadata, no
   project file, no digitising provenance. ⇒ no evidence.
4. **Old model prediction / legacy automatic label?** NDVI is higher
   inside the mask (0.244 vs 0.059), i.e. it at least selects green
   vegetation; index-threshold (SAI) or legacy classifier origins both
   remain plausible. Status: **unproven** (MISSING_EVIDENCE for the
   producing model/config and for the SAI threshold).

Conclusion: provenance **UNKNOWN/UNRESOLVED**; tier **WEAK**. It may
serve as a *candidate prior* for Pilot-0 co-registration experiments,
never as evaluation truth. Resolving it requires owner testimony or the
missing 2015 ArcGIS/GEE project files.

## 3. Consequences

- Any manuscript accuracy computed against this mask is
  label-conditional and cannot be quoted as independent accuracy.
- Pilot-0 must plan a fresh GOLD/SILVER label acquisition (field/UAV or
  expert image interpretation with documented protocol) before any
  benchmark metric is reported externally.
