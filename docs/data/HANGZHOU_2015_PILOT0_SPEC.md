# Hangzhou Bay 2015 Pilot-0 — Analysis-Ready Data Specification (v1)

Status: **PILOT0_V1 ANALYSIS-READY (labels are NOT GOLD)**
Version: `v1` (grid + products frozen for the Pilot-0 tiling/split work)
Created: 2026-09-27 (M1.3)
Grid/products builder: `scripts/data/hangzhou2015/{coregister.py,
arbitrate_labels.py,build_stack.py}`
Manifest: `datasets/manifests/hangzhou2015_pilot0_v1.{csv,parquet}`
(bytes live under `work/`, never in Git; checksums are in the manifest)

---

## 1. Window

- Geographic window: lon 121.018–121.418 E, lat 30.266–30.396 N
  (~581 km² rectangle; valid optical land/intertidal fraction ~0.34,
  the remainder is open water / fill in the legacy export).
- Analysis CRS: **EPSG:32651 (UTM zone 51N)**. This is the correct zone
  for 121° E. The national 2015 product is stored in EPSG:32650 (zone
  50N); it is reprojected per-pixel, never used zone-wise.
- Two deterministic grids, both anchored at false easting 500 000:
  - **30 m analysis grid**: origin (309 290 E, 3 364 370 N),
    1 292 × 501 px, bounds 309 290–348 050 E / 3 349 340–3 364 370 N.
  - **10 m S1-density grid**: same anchor, 3 874 × 1 501 px
    (bounds differ by ≤20 m at two edges; see co-registration doc).
- Grid anchour rule: multiples of pixel size measured from
  easting/northing 500 000, snapped to cover the mask footprint with
  ceil/floor (`snapped_grid()`). Re-running the builders reproduces the
  same grids bit-for-bit.

## 2. Source assets (read-only, never modified)

`old datasets/Spartina/HangZhouBay/`:

| File | Native properties | Role |
|---|---|---|
| `c201511839DTSP_2.tif` | uint8, 1 292×501, EPSG:32651, 29.977×29.946 m, origin 309 313.04/3 364 351.78; VAT {0:631 692, 1:15 600}; `.tfw`; ArcGIS `.sr.lock` sidecars (host DEAN) | **WEAK** local binary mask, 14.00 km² positive |
| `L8_AllBands_2015.tif` | 7 bands SR_B1..B7, uint16 unscaled DN (fill 0), 1 486×482, EPSG:4326 | Landsat-8 C02-L2-style surface reflectance composite |
| `NDVI_2015.tif` | float, EPSG:4326, same raster | legacy NDVI composite (−0.153…0.456) |
| `SAI_2015.tif` | float, EPSG:4326 | SAI composite; published definition SAI=(Red−NIR)/NIR (Zuo et al. 2025, JRS 5:0510, DOI 10.34133/remotesensing.0510) |
| `S1_VV_2015.tif`, `S1_VH_2015.tif` | float dB, 4 456×1 445, EPSG:4326, 8.64×9.96 m ground sample distance (exactly 3× the optical pixel count per axis); `.ovr` pyramids | Sentinel-1 GRD composites |

National label source (read-only):
`old datasets/30mSpartinaChina/30m分辨率中国互花米草空间分布数据集(2015年)-数据实体/…tif`
— int16, 45 282×67 077, EPSG:32650, 30 m, storage nodata 255; VAT has a
**single class Value=1 (608 287 px = 547.46 km²)**. Presence-only
thematic product. Provider DOI 10.12041/geodata.65372070926827.ver1.db
(geodata.cn / IGA), restrictive licence — see
`docs/data/DATA_PROVENANCE_AND_LICENSE.md`.

## 3. Provenance status (do not overstate)

- **Acquisition dates: UNKNOWN.** None of the six TIFFs carries any
  acquisition/date metadata tag (only GDAL statistics). Evidence:
  `artifacts/audit/pilot0/date_recovery.json`.
- The filename token `11839` is **consistent-but-not-proven** to mean
  WRS-2 path/row **118/39**. STAC (earth-search, metadata-only query,
  retrieval 2026-09-27) confirms 118/39 scene centers (~121.40 E,
  30.50 N) cover this window; 119/39 centers (~119.85 E) do not — so
  manuscript Table II's "119/39" is inconsistent with catalog geometry.
- 2015 L8/L7 C2-L2 intersecting the window: **77 scenes** (118/39 and
  119/39, T1+T2). Cloud-free-ish 118/39 L8 T1 examples:
  2015-08-03 (5.2% cc), 08-19 (29.7%), 08-27 (25.0%), 10-22 (24.9%).
- Manuscript nominal dates (2015-08-15, 09-01, 10-03) match **no real
  WRS 16-day overpass**; identical nominal dates appear for other years
  (1985–2010), so they are treated as nominal placeholders only.
- Sentinel-1 GRD in 2015 intersecting the window: **25 scenes**
  (2015-02…12, ascending, 6/12-day revisit). The exact scenes used and
  the compositing rule are **MISSING_EVIDENCE**.
- The local mask's production method and date are **UNKNOWN**. The
  threshold-generation tests are in the label-arbitration report.

## 4. v1 products (`work/hangzhou2015/v1/`)

| Product | Spec |
|---|---|
| `pilot0_stack_30m.tif` | 11 float32 bands on the 30 m grid: L8 SR B1–B7 transformed `DN×2.75e-5−0.2` (DN=0 fill → NaN, bilinear warp), NDVI, SAI, S1 VV/VH dB (bilinear warp to 30 m); nodata NaN |
| `pilot0_labels_30m.tif` | uint8: (1) WEAK local mask NN-warped; (2) SILVER national-2015 window NN-warped EPSG:32650→32651; (3) IGNORE mask; nodata 127 |
| `label_disagreement_30m.tif` | 0 neither / 1 both / 2 silver-only / 3 weak-only (full window; national 255 read as background — see arbitration doc) |
| `silver_2015_30m.tif` | SILVER window, binary presence |
| `ignore_30m.tif` | invalid optical pixels + disagreement pixels within 60 m of either label boundary |
| `s1_vv_10m.tif`, `s1_vh_10m.tif` | S1 on the 10 m-density grid |
| `grid_spec.json`, `pilot0_stack_v1.meta.json` | machine-readable grid/band provenance |

Resampling rules used (pre-declared in Issue #3): labels and masks →
**nearest neighbour**; continuous reflectance/indices/SAR →
**bilinear**; no cubic was used in v1. Reprojection crosses one UTM
zone boundary only for the label warp (32650→32651), nearest neighbour.

## 5. Quality tiers

- `l8/ndvi/sai/s1 bands`: UNLABELED features; dates UNKNOWN.
- `weak_local_mask`: **WEAK** — legacy automatic/unknown-rule mask, not
  ground truth.
- `silver_national_2015`: **SILVER** — peer-reviewed/distributed
  government-portal mapping product with known provenance and a known
  DOI; still not field-verified GOLD.
- No GOLD pixels exist in Pilot-0. See
  `HANGZHOU_2015_LABEL_ARBITRATION.md` for how labels may be used.

## 6. Hard constraints inherited

- Source files are read-only; every derived pixel is under `work/`.
- This spec does not train models; it is the input to Issue #4 tiling.
- No metric from the old manuscript is treated as reproduced.
