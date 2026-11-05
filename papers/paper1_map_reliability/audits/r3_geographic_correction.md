# R3.1 — Geographic correction of the E5 regional analysis

**Date:** 2026-11-05
**Branch:** `feat/paper1-map-reliability`
**Baseline:** `da51613`
**Status:** CORRECTED AND ARCHIVED

---

## 1. What was wrong

R2's E5 regional analysis split the harmonized EPSG:3410 domain at
`x = 11,000,000 m` and `x = 11,500,000 m` and named the three slices
`Bohai_Yellow`, `East_China`, `South_China`.

EPSG:3410 (NSIDC EASE-Grid Global) is a cylindrical equal-area projection
whose x coordinate is linear in longitude at approximately 96.3 km per
degree. The cuts at 11.0 Mm and 11.5 Mm therefore correspond to meridians
near 114.2 °E and 119.4 °E. They are **longitudinal bands**, not sea regions.

The labelling was also **inverted**:

| Band | x range | What it actually contained | Old label |
|---|---|---|---|
| A | x < 11.0 Mm | Guangxi, Hainan, western Guangdong (~18 km² of CMSA) | "Bohai/Yellow Sea" |
| B | 11.0–11.5 Mm | Fujian, Zhejiang, southern Jiangsu, Bohai rim | "East China Sea" |
| C | x ≥ 11.5 Mm | Shanghai, Jiangsu, Shandong, Liaoning (~469 km² of CMSA) | "South China Sea" |

Verified city → x mapping (computed with pyproj, EPSG:4326 → EPSG:3410):

| City | x (m) | Band | Actual sea |
|---|---|---|---|
| Beihai | 10,505,700 | A | South China Sea |
| Haikou | 10,621,800 | A | South China Sea |
| Guangzhou | 10,910,900 | A | South China Sea |
| Xiamen | 11,372,900 | B | Taiwan Strait |
| Tianjin | 11,334,800 | B | Bohai Sea |
| Yancheng | 11,574,700 | C | Yellow Sea |
| Qingdao | 11,595,300 | C | Yellow Sea |
| Shanghai | 11,700,900 | C | East China Sea |
| Dalian | 11,710,400 | C | Bohai / North Yellow Sea |

Consequence: every R2 statement of the form "the South China Sea shows the
highest agreement and the Bohai/Yellow Sea the lowest" described the
**northern** coast as the south and vice versa.

## 2. Files inspected

| File | Role |
|---|---|
| `experiments/e5_regional_heterogeneity.py` | band definition and regional metrics |
| `experiments/e5b_boundary_sensitivity.py` | band-shift stress test |
| `experiments/e5c_bootstrap_iou.py` | band-based bootstrap |
| `experiments/r3_bootstrap_validation.py` (interrupted) | also band-based; renamed to `superseded_r3_bootstrap_validation_DO_NOT_RUN.py` |
| `manuscript/main.tex` | Abstract, Methods E5, Results E5, bootstrap, hotspots, Discussion, Conclusions, Limitations |
| `figures/fig05_regional_iou.{pdf,png}` | affected regional figure |
| `results/regional_agreement_2020.csv`, `e5b_boundary_sensitivity.csv`, `e5c_iou_bootstrap.csv` | affected result tables |

All occurrences of the three region names were located with a repository-wide
search over `Spartina-Earth/papers/paper1_map_reliability`.

## 3. Preservation

Nothing was deleted. The affected outputs and the R2 regional figure were
copied to:

```
results/superseded_e5_longitude_bands/
├── README.md                       (defect, city→band table, replacement)
├── regional_agreement_2020.csv
├── e5b_boundary_sensitivity.csv
├── e5c_iou_bootstrap.csv
├── fig05_regional_iou.pdf
└── fig05_regional_iou.png
```

The README states explicitly that these files are superseded, are not
citable, and do not describe Bohai/Yellow Sea, East China Sea or South China
Sea.

## 4. Correct regionalisation

**Boundary source.** Natural Earth 1:10m Physical Vectors, *Geography Marine
Polygons* (v5.1.1, public domain, IHO-derived named sea areas). Local copy
`work/external/naturalearth_10m_marine/ne_10m_geography_marine_polys.shp`,
downloaded from naciscdn.org. Names verified against the `name_zh` field
(渤海, 黄海, 东海, 南海, 台湾海峡, 杭州湾, 北部湾, 琼州海峡).

**Region groups.**

| Region | Natural Earth polygons |
|---|---|
| `Bohai_Yellow` | Bo Hai + Yellow Sea |
| `East_China` | East China Sea + Hangzhou Bay + Taiwan Strait |
| `South_China` | South China Sea + Gulf of Tonkin + Qiongzhou Strait |

The Taiwan Strait assignment is an explicit convention, recorded in
`grouping_conventions` in the JSON.

**Processing.**

1. Select polygons intersecting the domain in EPSG:4326.
2. Clip to the domain box, reproject to EPSG:3410 (nearest-neighbour for the
   raster step).
3. Rasterize at 100 m with `all_touched=False`.
4. Assign positive pixels outside every polygon to the nearest group, using a
   KD-tree on group boundary pixels.

`Qiongzhou Strait` vanishes after clipping to the domain and is logged as
absent rather than treated as an error.

**Coastal residual.** 90,641 positive union pixels; 59,440 (65.58 %) fall
directly inside a marine polygon; 31,201 (34.42 %) are nearest-assigned
(Bohai 7,678 / East 22,262 / South 1,261); maximum nearest distance
53.97 km. Recorded in `results/region_definitions_geographic.json`.

**Rejected alternative.** Natural Earth 1:10m admin-1 provinces: 86.0 % of
positive union pixels fall outside the land polygons because the generalized
coastline omits intertidal flats. Documented in the same JSON under
`explored_but_not_primary`.

**Provenance file.** `results/region_definitions_geographic.json` records
dataset, version, licence, path, grouping conventions, per-group polygon
lists, grid dimensions, residual counts, and the arithmetic check
`15096 × 22166 = 334,617,936`.

## 5. Recomputed E5

Script: `experiments/e5d_geographic_regions.py`
Runtime 234.8 s. Outputs:

- `results/regional_geographic_2020.csv`
- `results/regional_area_share_geographic_2020.csv`
- `results/regional_by_marine_polygon_2020.csv`
- `results/region_definitions_geographic.json`

Regional areas (domain, 100 m): Bohai/Yellow 341,706 km²; East China
349,137 km²; South China 225,940 km².

| Region | CMSA–CM-SSM | CMSA–GEODATA | CM-SSM–GEODATA |
|---|---|---|---|
| Bohai/Yellow | 0.4665 | 0.5599 | 0.3646 |
| East China | 0.5902 | 0.3923 | 0.3499 |
| South China | 0.4772 | 0.1341 | 0.0835 |

Area shares (CMSA / CM-SSM / GEODATA, % of national total):

| Region | CMSA | CM-SSM | GEODATA |
|---|---|---|---|
| Bohai/Yellow | 40.8 | 32.1 | 44.2 |
| East China | 55.8 | 65.4 | 50.7 |
| South China | 3.4 | 2.5 | 5.1 |

## 6. Does the 3× contrast survive?

**The direction does not; the magnitude does, but only for two of the three
pairs.**

| Question | Answer |
|---|---|
| Is the old 3.2× ratio reproduced? | No. Corrected ratio is 4.18× [2.74, 7.51] |
| Is the old ordering (South high, Bohai low) reproduced? | No. It is reversed: Bohai 0.5599, South 0.1341 |
| Is the magnitude statistically resolved? | Yes for CMSA–GEODATA (p < 0.001) and CM-SSM–GEODATA (4.37× [2.64, 9.10]) |
| Is it general across pairs? | No. CMSA–CM-SSM ratio 0.98 [0.81, 1.19], p = 0.88 |
| Is it representative of the national product? | No. South China is 3.4 % of CMSA's national area |

The manuscript therefore states a **pair-specific, direction-corrected**
contrast and no longer carries a general "3×" claim.

## 7. Verification notes

- The three regional areas sum to the national harmonized area for each
  product (568.98 / 590.79 / 521.23 km² at 100 m), confirming that the
  regional masks partition the positive pixels exactly once.
- `e6_agreement_map.py` was rerun independently and reproduced the national
  IoU values exactly (0.5395 / 0.4444 / 0.3432), so the correction did not
  disturb the underlying harmonization.
- The provenance JSON records `git_commit` as `da51613` because the corrected
  scripts ran on the working tree before the R3.1 commit; after the commit
  the scripts are rerun so that the recorded commit matches the code.
