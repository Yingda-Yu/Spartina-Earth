# Experimental Protocol — Paper 1 E1–E6

**Date frozen:** 2026-11-03
**Git commit at freeze:** 9be4073 (`feat/paper1-map-reliability Final Stage D`)
**Subsequent changes:** none (any deviation recorded below with justification)

---

## 0. Protocol separation principle

This protocol explicitly separates two distinct question types:

- **Inter-product agreement:** How well do three products agree with each other? (MEASUREABLE — this is the focus of Paper 1)
- **Accuracy vs.\ ground truth:** How well do products agree with reality? (UNMEASUREABLE here — E7 blocked, explicitly acknowledged)

No result in this paper shall be interpreted as accuracy against ground truth.

---

## E1 — Harmonization protocol

### Inputs
| Product | Version | Native CRS | Format | License | Provenance |
|---|---|---|---|---|---|
| CMSA | `CMSA_2020.shp` (and 2017/2018/2019/2021) | EPSG:32650 | Vector shapefile | UNVERIFIED | CAS researchers, Sentinel-2 10m |
| CM-SSM | `CM-SSM.shp` (2020 only) | EPSG:32650 | Vector shapefile | CONFLICTED (CC-BY-4.0 vs CC-BY-NC-4.0) | Zenodo-hosted, sub-meter + Sentinel-2 |
| GEODATA | `2020年...tif` (and 1990/2000/2015) | EPSG:2433 | 30m GeoTIFF | CC-BY-NC-ND | Landsat-based, separate research group |

### Harmonization target
- **Common CRS:** EPSG:3410 (North America Albers Equal-Area Conic) — chosen for accurate area measurement on the national China coast domain
- **Domain boundary:** CMSA 2020 `total_bounds` + 10\,km geodesic buffer = tightest domain covering all three products' 2020 extents
- **Common grid:** Regular grid at `RES_M` resolution covering the domain bounds exactly (`width = ceil((maxx − minx) / RES_M)`, `height = ceil((maxy − miny) / RES_M)`)

### Species class mapping
| Product | Native class code | Meaning | Harmonized value |
|---|---|---|---|
| CMSA | `gridcode = 2` | Spartina alterniflora present | 1 (positive) |
| CMSA | `gridcode = 0` | Absent (50 polygons, dropped) | Excluded from harmonization |
| CM-SSM | All polygons | Spartina alterniflora clumps (presence-only) | 1 (positive) |
| GEODATA | `Value = 1` | Spartina present (from VAT dbf) | 1 (positive) |
| GEODATA | `Value = 255` | NoData | 0 in binary mask |

### No-data / unknown handling
- GEODATA `Value = 255` → treated as 0 in binary mask (not Spartina)
- CMSA `gridcode = 0` polygons → explicitly excluded from positive class
- CM-SSM is presence-only (all polygons positive); no absence class
- No "unknown" pixel class is retained in harmonized masks; all pixels are either 0 or 1

### Area calculation
- Areas computed from **harmonized raster counts**: `area_km² = sum(binary_mask) × RES_M² × 10⁻⁶`
- Native source areas NOT used for cross-product comparison (different CRS)
- `audit_all_sources.py` independently verifies CMSA's `Area_ha` field matches UTM-planar area almost exactly (0 bias)
- `audit_all_sources.py` confirms CMSA planimetric differs from geodesic by ~0.5% (expected UTM scale factor)

---

## E3 — Spatial agreement protocol

### Pair-wise IoU and Dice
For each product pair (A, B) at each resolution r ∈ {30, 50, 100}:

1. Rasterize product A to binary mask M_A[r] on harmonized grid
2. Rasterize product B to binary mask M_B[r] on harmonized grid
3. Compute:
   - Intersection = M_A ∧ M_B
   - Union = M_A ∨ M_B
   - IoU = sum(Intersection) / sum(Union)
   - Dice = 2 × sum(Intersection) / (sum(M_A) + sum(M_B))

### Rasterization rules (vector products)
- Library: `rasterio.features.rasterize`
- Rule: `all_touched = False` (standard vector-to-raster convention; a pixel must have its center inside the polygon)
- Fill value: 0 (no Spartina)
- Output dtype: `uint8`

### Warping rule (GEODATA raster)
- Library: `rasterio.warp.reproject`
- Method: Nearest-neighbour resampling (`Resampling.nearest`) — preserves binary class
- NoData handling: `src_nodata = 255`, `dst_nodata = 0`
- Output binary threshold: `M[r] = (warped_tif == 1).astype("uint8")`

### Agreement/disagreement mask
3-class mask derived from pair (A, B):
- 0 = neither product maps Spartina (no data for agreement)
- 1 = both products agree on Spartina present (agreement)
- 2 = only product A maps Spartina (A-unique)
- 3 = only product B maps Spartina (B-unique)

**Critical:** Classes 2 and 3 quantify spatial conflict; they are NOT omission/commission errors. A pixel classified as "only CMSA" does NOT mean CM-SSM incorrectly omitted Spartina; it means CMSA and CM-SSM disagree about the presence boundary.

### Statistical independence
Pixels in remotely-sensed data are spatially autocorrelated (~5–10 effective resolution units correlation length). The ~300M px domain at 30m contains ~3M independent "superpixels" if assuming 100m effective resolution. No formal spatial uncertainty test is applied (E5 regional heterogeneity was planned but not implemented). This is an open limitation.

---

## E4 — Resolution sensitivity protocol

For each product pair, IoU and Dice computed independently at 30m, 50m, and 100m. Domain and common grid regenerated at each resolution (exact pixel coverage, no sub-sampling of finer grid).

Resolution sensitivity = |metric_100m − metric_30m| / metric_30m × 100%

Empirical finding: ≤0.4% IoU change across all pairs. Conclusion: resolution is NOT the dominant driver of product disagreement.

---

## E6 — Monitoring implications protocol (partial)

Two sub-analyses:
1. **National trend conflict**: CMSA 2017–2021 monotonically increasing (+4.0%/year, same product = consistent encoding) vs.\ GEODATA 2015→2020 apparent decline (−6.8%, same product). **Never** mixed across products within same time window.
2. **2020 area range**: 14.2% cross-product range at year 2020. Used to frame interpretation of historical trend uncertainty.

**Explicitly NOT done (blocked):**
- Regional heterogeneity by subdomain (E5 not implemented)
- Eradication effectiveness assessment
- Province-level ranking (CM-SSM circular attribution prohibited)
- Independent ground-truth validation (E7 impossible)

---

## Uncertainty estimation

**None applied.** All reported metrics are deterministic harmonized outputs. This is an open limitation acknowledged in the manuscript. No bootstrap, jackknife, or spatial-block uncertainty quantification has been performed.

---

## Validation strategy

**E7 blocked.** No independent ground-truth reference dataset exists in the repository (audited). Three products, all SILVER tier or below (CMSA UNVERIFIED open license, CM-SSM license conflict, GEODATA CC-BY-NC-ND). No GOLD tier data found.

The paper explicitly states in limitations that all results measure inter-product agreement, NOT ground-truth accuracy.

---

## Changes to protocol since freeze

| Date | Section | Change | Justification |
|---|---|---|---|
| (freeze) | — | — | — |

No deviations from the protocol described above have been recorded. All experiment scripts (e3_spatial_agreement.py, e6_agreement_map.py) implement this protocol faithfully.
