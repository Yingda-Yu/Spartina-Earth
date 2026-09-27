# Data provenance passports and license review (M1.1)

Web verification date: **2026-09-27**. Identity of a local file with a
remote product is asserted only when name + metadata + geometry agree;
license text was read from the provider page, not guessed.

## Passport 1 — 2015 national Spartina raster (IDENTIFIED)

- **Local:** `30mSpartinaChina/30m分辨率…(2015年)-数据实体/…tif`
  (6.10 GB; + `.rar` sample 681,048 B; VAT, tfw, ovr, aux.xml).
- **Is:** 30m分辨率中国互花米草空间分布数据集(2015年), Black Soil and
  Wetland SubCenter, **National Earth System Science Data Center**
  (国家地球系统科学数据中心-黑土与湿地分中心, northeast.geodata.cn /
  www.geodata.cn).
- **Providers/authors:** 王宗明 (Wang Zongming), 毛德华 (Mao Dehua),
  贾明明 (Jia Mingming), **Northeast Institute of Geography and
  Agroecology, CAS (IGA, 中国科学院东北地理与农业生态研究所)**.
- **Published:** 2020-09-18; page data-size 665.09 KB matches the
  on-disk `.rar` (681,048 B ≈ sample download) — name/size/CRS/tie
  points all consistent.
- **DOI:** **10.12041/geodata.65372070926827.ver1.db** (needs a formal
  download order record in the project's name; TODO_VERIFY that the
  local 5.7 GB entity exactly matches the order-delivered package —
  byte comparison at freeze time).
- **Method (provider text):** Landsat-8 OLI; eCognition 9.2
  multiscale segmentation; object-based + **SVM** classification;
  OLI 543 expert visual editing removing non-coastal patches;
  **field-survey validation points; OA 92%**; WGS_1984_UTM_Zone_50N.
- **Citations required in outputs:**
  - Mao D., Liu M., Wang Z. et al. 2019. Rapid Invasion of Spartina
    alterniflora in the Coastal Zone of Mainland China: Spatiotemporal
    Patterns and Human Prevention. *Sensors* 19:2308.
  - Liu M., Mao D., Wang Z. 2018. Rapid invasion of Spartina
    alterniflora… New observations from Landsat OLI images. *Remote
    Sensing* 10(12):1933.
  - Mao D. et al. 2020. National wetland mapping in China… *ISPRS J.
    Photogramm. Remote Sens.* 164:11–25.
- **License/terms:** platform data, **research use only; attribution +
  acknowledgement mandated; copying/redistribution/sale prohibited
  without written permission**; access via registered online order.
  ⇒ internal research use compliant with attribution; bytes stay out
  of Git (already); **do not redistribute**; record order/approval.
- **Tier now:** **SILVER** (national research-center product, peer
  methods, known provenance + validation protocol; not GOLD because no
  per-pixel field validation data accompany the file).

## Passport 2 — CM-SSM 2020 polygons (INTERNAL, provenance partial)

- **Local:** `30mSpartinaChina/2020/CM-SSM/CM-SSM.shp` (148,072 polys,
  593.710 km²; 2,402 self-intersecting; 100,455 <100 m²).
- **Evidence:** ArcGIS XML metadata — source item `ChinaSP1025.shp`
  (UNC `…\H\XM\final_result\Whole\`), created 2024-05-22; lineage =
  per-province OBIA class results (`I:\ZXM\SP_XM\OBIA\…`,
  `D:\Deep Learning\XMproduct\fj2020\…`) → Dissolve SINGLE_PART →
  Merge (FJ/GD/GX/HB/JS/LN/SD… → +sd006, sh02001 → ChinaSP1023/1025)
  → `CalculateGeometryAttributes area … 公顷`.
- **Relation to published products:** the geodata 2020 Spartina
  product by the IGA team is a small 30 m raster series (e.g.
  "2020年中国滨海30m分辨率互花米草空间分布动态数据集", ~679 KB class),
  which cannot be this 358 MB polygon set — **not the IGA product**.
  Possible relation to the 10 m 2020 map of the published SAI paper
  (Zuo et al. 2025, DOI 10.34133/remotesensing.0510; map "available on
  reasonable request", built Oct 2024 timeline overlap) — **plausible
  but UNCONFIRMED**; no asset id, map file, or method statement
  identifies CM-SSM in the paper.
- **Provider/license:** UNKNOWN — internal working files from someone
  else's Windows machines (identity UNKNOWN); underlying imagery is USGS
  Landsat / ESA Sentinel (open with attribution), but the derived map's
  ownership and sharing rights are undocumented. Tier **WEAK**.
  Redistribution: **do not** until owner resolves rights.

## Passport 3 — Hangzhou Bay 2015 bundle (DERIVED IN-HOUSE)

- Mask origin UNRESOLVED (LABEL_TIER_REVIEW.md §2; Jaccard 0.497 vs
  the SILVER 2015 national product; WEAK tier).
- L8/NDVI/SAI/S1 composites carry no export provenance; likely GEE
  exports cut to the mask rectangle (exact bound match).
- **Underlying source licenses:** Landsat courtesy USGS/NASA (public
  domain, attribution); Sentinel-1 © ESA (open data, attribution,
  terms apply); the **derived composites and mask: license/owner
  UNKNOWN**; manuscript-draft status (not published in this form).
- The SAI raster is consistent with the published index polarity
  (Zuo et al. 2025, SAI=(Red−NIR)/NIR; Spartina = more negative);
  formula version/parameters producing this exact file UNKNOWN.

## Passport 4 — Zhejiang 2015 fused stacks (DERIVED IN-HOUSE)

- Two GEE-export tiles, bands `SR_B1..B7,VV,VH,NDVI,SAI`, EPSG:4326,
  ~30 m grid, lon 120.54–122.59 / lat 27.46–30.72; no script/date
  metadata. Same source-license profile as Passport 3; derived
  product rights UNKNOWN. UNLABELED features.

## Passport 5 — Fujian S2 composites 2019–2025 (DERIVED IN-HOUSE)

- Seven annual `B4,B3,B2,NDVI,NDWI` composites, identical grid;
  Sentinel-2 © ESA (open, attribution under ESA/Copernicus terms —
  TODO_VERIFY exact current licence text); derived composites' owner
  UNKNOWN; no cloud/date provenance. UNLABELED features.

## Passport 6 — CMSA polygons 2019–2021 (INTERNAL)

- Legacy 10 m-grid raster→vector labels (98 m² floor = one S2 pixel),
  WEAK tier; rights UNKNOWN; `CMSA_2020.zip` is a byte-identical
  packaging snapshot (2026-01-05), not a separate source.

## Manuscripts

Both owner PDFs are **unpublished drafts** ("all rights reserved"
default; do not redistribute). The SAI work exists as a *different*,
published paper — Zuo Y., Yang G., Sun W. et al., *Journal of Remote
Sensing*, 2025, 5:0510, DOI **10.34133/remotesensing.0510** (3,672
labelled points; threshold SAI; OA 87.70% up; 10 m 2020 China map
available "on reasonable request"). The on-disk draft has a different
author line (Yu, Xuan, Tang, Tian, Xu) and adds a multi-head attention
+ transfer-learning model; the relationship between draft and paper
(reuse, extension, student version) is **UNKNOWN — ask the owner**.
The CISNet draft has no identifiable publication found
(TODO_VERIFY).

## Action items

1. Retrieve the formal geodata order record for Passport 1 and compare
   delivered bytes at freeze (V1 gate).
2. Ask the owner: CM-SSM identity/authors/sharing rights; Hangzhou
   mask producing workflow; GEE export scripts; draft-vs-paper
   relationship.
3. Maintain citation/acknowledgement strings for USGS, ESA and
   geodata.cn in every derived product manifest.
