# Fujian temporal bundle audit — `spartinatest/` (M1.1)

## 1. Contents (read-only inspection)

- `S2_2019.tif … S2_2025.tif` (7 files): identical grid every year —
  669×669, EPSG:4326, 0.0000898315° (8.64×9.96 m ground at lat 28.34),
  float32, bands **B4, B3, B2, NDVI, NDWI** (no date tags, no cloud /
  QA / SCL bands, no nodata marker), bounds lon 121.1599–121.2200,
  lat 28.3100–28.3701.
- `CMSA_2019/2020/2021.shp` (+ `.fix` sidelcars ⇒ edited/repaired in
  ArcGIS at some point): EPSG:4326, fields `Area_ha (float), Id,
  gridcode` (gridcode = 2 in all features), 78 / 191 / 105 features.
- `CMSA_2020.zip` (2026-01-05 08:4x timestamps): byte-identical bundle
  of the loose folder — verified by SHA-256 streaming from the archive
  (`CMSA_2020.shp`, `CMSA_2019.shp`, `S2_2019.tif` hashes match the
  loose files). It is a packaging snapshot, not new data.

## 2. Answers to the required questions

1. **Actual acquisition dates per year: UNKNOWN.** Only filename years
   exist; tags carry no composite dates, and no GEE script/export log
   is present. Sentinel-2-era years 2019–2025 are sensor-possible but
   unverified.
2. **Cloud metadata: ABSENT.** No SCL/QA/CloudScore/band-mask layers;
   the 5-band composites contain no evidence of cloud/tide filtering.
   NDWI presence suggests water masking was done upstream, but its
   parameters are missing.
3. **Grid consistency: YES for imagery** — identical dimensions,
   bounds and transform for all seven years (deterministic export
   grid). Label bounds differ slightly year to year
   (2019 121.1497–121.2194/28.2687–28.3757;
   2020 121.1513–121.2194/28.2967–28.3734;
   2021 121.1504–121.2196/28.2690–28.3795) and extend **beyond the
   image footprint** (image south edge 28.310; polygons reach 28.269),
   i.e. the 2019/2021 labels cannot be fully evaluated against the
   provided imagery.
4. **CMSA years/method:** only 2019–2021 vector labels exist though
   imagery runs to 2025 (2022–2025 labels MISSING). No method metadata;
   the geometry minimum (98.2 m² all years) and the 0.01 ha field floor
   indicate **10 m-grid raster→vector conversion** (one Sentinel pixel
   ≈ 100 m² = 0.01 ha), consistent with thresholded-index or pixel
   classification polygons — WEAK tier.
5. **Sliver cause:** `Area_ha` rounds to 4 decimals (0.01 ha floor) and
   smallest polygons ≈98–99 m² ≈ single 10 m pixels; 2020 has 38
   sub-100 m² features (vs 5 in 2019, 8 in 2021), one MultiPolygon and
   the lowest area — signature of noisier segmentation that year, not
   of digitising errors. Fragments are preserved (read-only policy);
   they are evidence of the raster-vector conversion resolution.

## 3. Numbers (independent computation)

| Year | Features | `Area_ha` sum | Geodetic area (km²) | Features <100 m² |
|---|---|---|---|---|
| 2019 | 78 | 928.85 | 9.258 | 5 |
| 2020 | 191 (+1 MultiPolygon) | 484.57 | 4.829 | 38 |
| 2021 | 105 | 949.24 | 9.461 | 8 |

`Area_ha` vs geodetic-area ratio ≈ 9,958–9,966 (hectares confirmed by
field name + ratio). The 2019↔2020 −48% and 2020↔2021 +96% swings are
not interpretable as ecological change until acquisition dates, cloud
filtering, label method and the coverage mismatch are closed — they may
be processing artefacts. No change-detection is performed in M1.1.

## 4. Gaps for M1.2+

Recover GEE export script (dates, cloud threshold, tide window),
obtain/derive 2022–2025 labels or mark the gap, crop/flag label
geometry outside imagery, and re-tier only with provenance evidence.
