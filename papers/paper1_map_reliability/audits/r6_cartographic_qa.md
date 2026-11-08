# R6 Cartographic QA — Per-Figure Audit of the Redesigned Figures

**Date:** 2026-11-08 (corrected 2026-11-09, see §0.1)
**Design system:** `experiments/r6_cartography.py` (shared palette, basemap,
graticule, scale-bar, north-arrow, locator-inset helpers)
**Base geographic data:** Natural Earth 1:10m (public domain, v5.1.1
admin0/admin1, v5.1.0 marine), source passports at
`work/external/*/SOURCE_PASSPORT.json` and
`docs/audit/source_passports/2016/naturalearth/*/license.txt` (CC0). No
Google/commercial tiles; no fabricated boundaries.
**Projection:** EPSG:3410 (NSIDC EASE-Grid Global, cylindrical equal-area,
lat_ts=30°) — identical to the analysis grid, so figure pixels correspond
1:1 to the statistics; north-up, rectangular graticule.

---

## 0.1 Correction — basemap unit bug discovered and fixed (2026-11-09)

**Defect.** `add_basemap()` plotted the clipped Natural Earth geometries in
their native EPSG:3410 **metre** coordinates, while every other panel element
(products, graticule, scale bars, zoom boxes, tints) and the final
`ax.set_xlim/ylim` used **kilometres**. The land polygons therefore fell
entirely outside the axes view window: every figure built with the R6 design
system rendered as sea-coloured panels with data overlays but **no land fill,
no coastline, no province boundaries**. The first version of this audit
(2026-11-08) wrongly marked those figures PASS; its per-figure "land/sea
basemap" checks verified only the sea face colour and the km-based overlays,
not the land layer. Status of that audit: **superseded for the basemap
element**; the per-figure checks below were re-verified after the fix.

**Fix.** `r6_cartography.py` now converts clipped geometries to km
(`_as_km()` scale ×1e-3) before plotting. A second defect was fixed in the
same pass: `add_graticule(..., label_x=False/label_y=False)` previously left
matplotlib's default raw km-number tick labels in place; it now clears the
ticks (detected in fig03 panel (a)).

**Regenerated and re-verified (pixel + visual):** fig01_study_area,
fig03_agreement_map, fig_r4_south_china_zoom, fig_r4_region_assignment.
Re-verification evidence: rendered PNG pixel counts of the land colour
(#EDE7DC) rose from 15,536 px (broken fig01) to 1.61–1.82 M px per figure;
independent visual review confirms cream land vs pale-blue sea, dark
coastlines, province lines, and correct degree tick labels in all map
panels. Numerical outputs unchanged: densest window row 9975 / col 12600
(same as R4), residuals 31,201 px, median 5.5 km, p99 52.48 km, legend
counts direct 59,440 px / union 90,641 px / 34.4 %.

---

## 0. Unified design system

| Element | Specification | Rationale |
|---|---|---|
| Land | `#EDE7DC` warm gray | neutral, muted |
| Sea | `#D7E0E8` light blue-gray | neutral, muted |
| Coastline | `#3F3F3F` dark gray, 0.45 lw | visible at print size |
| Province boundaries | `#C9C3B8`, 0.30 lw | context without clutter |
| International borders | `#9C9C9C` dashed, 0.35 lw | neutral treatment of neighbors |
| Spartina / agreement | `#0F8A6D` teal-green | high-recognition green |
| Only-A / CMSA | `#0072B2` blue (Okabe-Ito) | colorblind-safe |
| Only-B / GEODATA | `#E69F00` orange (Okabe-Ito) | colorblind-safe |
| Disagreement ramp | YlOrRd 0.25–1.0 sequential | single-hue, CB-safe |
| Region tints | `#7FA8CC`/`#B0C4D6`/`#D3DEE8` | luminance ladder (grayscale-safe) |
| Typography | DejaVu Serif, 6.5–9.5 pt, thin spines/ticks | consistent across figures |
| Graticule | 5° national / 1° zoom, °E/°N labels | geographic reference |
| Scale bars | geodesic-true at panel centre latitude | honest measurement |
| North arrows | plain N-arrow | valid for north-up CEA |
| Output | vector PDF (dense layers rasterized at 200 dpi) + 200 dpi PNG previews | brief §4.5 |

Colorblind safety: Okabe-Ito classes + single-hue sequential ramps; grayscale
check: classes have distinct luminance (teal ≈ 45 %, blue ≈ 40 %, orange ≈
65 %, red ≈ 45 % vs. land/sea > 80 % backgrounds).

---

## 1. Figure 1 — Study area and source products (NEW: `fig01_study_area`)

| Item | Record |
|---|---|
| Pre-R6 problem | No study-area map existed at all; the manuscript opened with no geographic orientation for non-China readers. |
| What was drawn | 2×2: (a) study area + three sea-region groups (luminance-ladder tints, labels) + Yangtze-estuary zoom box/inset (all three products co-located); (b–d) CMSA / CM-SSM / GEODATA 2020 positives on the identical base and extent. |
| Data source | Cached 100 m EPSG:3410 product grids (analysis grids); NE 10m basemap; region masks from `marine_masks_100m.npz` (IHO-derived, used consistently with the analysis). |
| Elements | graticule (5°, °E/°N labels), scale bar 250 km, north arrow ×4, locator inset in (a), zoom box + connectors, unified legend, attribution note. |
| Rendering | 1 km block-max positives; full-res inside the zoom inset. |
| QA verdict | **PASS** — visually inspected 200 dpi PNG (twice, after fixes: inset border disambiguated, region tints re-laddered, graticule labels on all panels, block size note corrected). |
| Script | `experiments/r6_fig01_study_area.py` |

## 2. Figure 2 — National product agreement (`fig03_agreement_map`)

| Item | Record |
|---|---|
| Pre-R6 problem | Data-only panels: no land/sea context, no province boundaries, km-only axes, no locator. |
| What was redrawn | 2×3 (national + zoom) on the unified basemap; graticule labels on outer edges; locator inset in (a); zoom row at native 100 m with coastlines; scale bars 250 km / 10 km; north arrows. |
| Zoom window | Data-driven densest window — identical to R4 (Yangtze estuary/Jiangsu coast, 70 km span). |
| Colors | both=teal, only-A=blue, only-B=orange — unchanged semantics, now with basemap. |
| QA verdict | **PASS** — inspected: classes, basemap, boxes, legend, insets all render correctly; same window as R4 so all in-text references remain valid. |
| Script | `experiments/r6_fig03_v2.py` (replaces `r4_fig03_upgrade.py` output) |

## 3. Figure — Spatial mismatch case study (`fig_r4_south_china_zoom`)

| Item | Record |
|---|---|
| Pre-R6 problem | Raw row/col axes, no coastline, no basemap, no scale — unusable for publication. |
| What was redrawn | Three named localities at native 100 m on the unified basemap: (a) Pearl River estuary (113.42°E, 22.14°N), (b) Beibu Gulf (110.16°E, 20.93°N), (c) Leizhou Bay (109.66°E, 21.58°N); ±2.5 km windows on rank-1 clusters from `results/r4_south_china_clusters.csv`. |
| Colors | product-identity (CMSA blue / CM-SSM teal / GEODATA orange, explicit legend); alpha blending shows overlap. Caption explicitly states the per-figure color meaning (brief rule: no silent color-meaning changes). |
| Elements | corner-coordinate annotations, 1 km scale bars, north arrows, legend, attribution note. |
| QA verdict | **PASS** — inspected: all three localities show the intended evidence (offset, GEODATA-only, three-way overlap). |
| Script | `experiments/r6_fig_south_china_v2.py` |

## 4. Figure — Regional attribution (`fig_r4_region_assignment`)

| Item | Record |
|---|---|
| Pre-R6 problem | Data-only map + histogram, no geographic context. |
| What was redrawn | (a) national map on unified basemap: direct-membership pixels (muted teal, 1 km block-max) vs. nearest-assigned residuals (distance-binned YlOrRd ramp), region outlines + labels, locator inset, scale bar, north arrow, colorbar; (b) distance histogram with overall median 5.5 km / p99 52.5 km markers. |
| Recomputation | Distances recomputed with scipy cKDTree on the 100 m grid (same method as R4): 31,201 residual px, median 5.5 km, p99 52.5 km — consistent with per-region values in `r4_attribution_meta.json` (the 6.83 km East China median in the text is region-specific and unchanged). Caption updated to state both. |
| QA verdict | **PASS** — inspected: classes, ramp, histogram, labels render correctly. |
| Script | `experiments/r6_fig_assignment_v2.py` |

## 5. Figure — Coverage strips (`fig_r4_coverage_strips`)

| Item | Record |
|---|---|
| Pre-R6 problem | Embedded internal round label ("R4-02 —"); product colors inconsistent with the rest of the paper (purple/teal/orange vs. blue/teal/orange). |
| What was redrawn | Same bar chart from `results/r4_coverage_strips.csv`, no embedded title (caption carries it), unified product colors (CMSA blue, CM-SSM teal, GEODATA orange). |
| QA verdict | **PASS** — title removed (pdftotext check), colors unified. |
| Script | `experiments/r6_fig_coverage_strips.py` |

## 6. Statistical figures kept after inspection

| Figure | Check | Verdict |
|---|---|---|
| `fig04_stats` | embedded titles have no internal round labels; CMSA blue / GEODATA orange / CM-SSM green consistent with new system | **PASS, unchanged** |
| `fig05_regional_iou` | clean title, CI whiskers, colorblind-safe | **PASS, unchanged** |
| `fig05_resolution` | clean title; pair colors consistent | **PASS, unchanged** |
| `fig06_robustness` | clean title | **PASS, unchanged** |

## 7. Brief §4.1 checklist (element applicability)

| Element | Applied where |
|---|---|
| Coastlines + land outline | All 4 map figures (NE admin0) |
| Province boundaries | Fig01 (all panels), Fig02 national row; omitted on ≤5 km zooms (visual crowding) |
| International boundaries | Fig01 panel (a) only (locating China); dashed neutral elsewhere as needed |
| Graticule / coordinate labels | Fig01 + Fig02 (°E/°N), Fig04 (°E/°N), Fig-SouthChina (corner coordinates), Fig-assignment (°E/°N) |
| Scale bar | Every map panel (geodesic-true) |
| North arrow | Every map panel (valid: north-up CEA) |
| Legend | Every figure |
| Source/cartographic note | Every figure (Natural Earth public domain + projection + rendering rule) |
| Study-area locator | Fig01 inset (a); Fig02 inset (a); Fig-assignment inset |
| Region grouping labels | Fig01 (tints + labels), Fig-assignment (labels) |

## 8. Licensing of geographic base data

Natural Earth (v5.1.1/v5.1.0) is public domain (CC0); no attribution legally
required but credited on every figure and in every caption as good practice.
IHO-derived sea-region polygons: internal research use (cited in text); the
published figures only show tinted region groups derived from them —
provenance documented in `datasets/manifests/` and R1–R3 audits. No restricted
boundaries, no commercial tiles, no politically sensitive base layers; the
China coastline is rendered at its Natural Earth generalized form with no
boundary-claim implications (maritime region groups are ocean-unit labels, not
sovereignty claims).

**Overall cartographic verdict: PASS — all 9 figures audit clean; every map
now carries full geographic context on licensed public-domain basemaps.**
