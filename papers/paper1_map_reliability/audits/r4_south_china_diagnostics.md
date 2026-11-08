# R4-03 — South China Sea region low-IoU diagnostics

Run: 2026-11-08, commit `f2c7368`, script `experiments/r4_south_china.py`
(runtime 391 s). Domain: policy-B South_China sea-region mask
(4,344 positive-union px at 100 m, EPSG:3410). **Neither product is treated
as ground truth**; all quantities describe mutual spatial disagreement.

## Headline numbers (from `results/r4_south_china_diagnostics.csv`)

| Quantity | CMSA vs GEODATA | CM-SSM vs GEODATA |
|---|---|---|
| CMSA area | 19.27 km² | — |
| CM-SSM area | — | 14.69 km² |
| GEODATA area | 26.31 km² | 26.31 km² |
| Intersection | 5.39 km² | 3.16 km² |
| Union | 40.19 km² | 37.84 km² |
| IoU | 0.1341 | 0.0835 |
| only-CMSA / only-CM-SSM | 13.88 km² | 11.53 km² |
| only-GEODATA | 20.92 km² | 23.15 km² |

GEODATA maps the **largest** South China area of the three products
(26.31 km² vs CMSA 19.27, CM-SSM 14.69). The low IoU therefore does *not*
arise because GEODATA maps less — it arises because GEODATA's South China
positives are spatially displaced from the other two products' positives,
and CM-SSM–GEODATA is the pair with the smallest intersection (3.16 km², i.e.
CM-SSM and GEODATA largely map *different* patches).

## False spatial disagreement (mutual, no ground truth)

- CMSA–GEODATA: 13.88 km² mapped only by CMSA and 20.92 km² only by GEODATA
  (69.4% of the 40.19 km² union is disagreement).
- CM-SSM–GEODATA: 11.53 km² only CM-SSM, 23.15 km² only GEODATA
  (78.7% of union is disagreement).

## Boundary vs segment-level structure

Only-pixel proximity to the other product's positives:

| Quantity | only-CMSA→GEODATA | only-GEODATA→CMSA | only-CM-SSM→GEODATA | only-GEODATA→CM-SSM |
|---|---|---|---|---|
| within 100 m | 15.4% | 16.6% | 13.9% | 10.6% |
| within 500 m | 40.0% | 42.4% | 37.6% | 28.6% |
| within 1 km | 47.3% | 53.4% | 44.8% | 40.0% |
| beyond 5 km | 28.8% | 29.3% | 29.4% | **44.4%** |
| median distance | 1.44 km | 0.82 km | 1.61 km | 2.68 km |

Interpretation:
- Roughly half of each "only" class lies within 1 km of the other product's
  positives — patch-boundary misalignment at the 0.1–1 km scale.
- A substantial tail (29–44%) lies beyond 5 km — genuinely disjoint
  segments, not boundary offsets. This tail is largest for only-GEODATA
  relative to CM-SSM (44.4% beyond 5 km, median 2.68 km), consistent with the
  national-scale isolation statistic (17.6% of all GEODATA positives lie
  >5 km from any CM-SSM positive, R4-02).
- Without reference data these cannot be labelled omission or commission
  for either product; they are documented as *mutual disagreement with a
  spatially disjoint component*.

## Fragmentation and small-patch sensitivity

From `results/r4_south_china_fragmentation.csv`:

| Product | patches | mean ha | median ha | area <1 ha | area <5 ha |
|---|---|---|---|---|---|
| CMSA | 390 | 4.94 | 2.0 | 0.0% | 24.5% |
| CM-SSM | 337 | 4.36 | 2.0 | 0.0% | 28.7% |
| GEODATA | 196 | 13.42 | 4.0 | 0.0% | 9.5% |

GEODATA maps fewer, larger patches in the South (median 4 ha vs 2 ha), i.e.
it generalizes more; CMSA/CM-SSM delineate more, smaller patches. At the
100 m analysis resolution no product has patches <1 ha, so the low IoU is
not a sub-hectare small-patch artifact. The differing patch-size
distributions do mean that a single GEODATA patch often straddles multiple
smaller patches of the other products plus unmapped inter-patch area, which
mechanically depresses IoU when patch centroids do not coincide.

## Coverage / no-data context

Per R4-02: GEODATA's delivered entity is presence-only (255 fill), so
South China pixels where GEODATA maps nothing cannot be classified as true
absence vs no-data. The coastal-strip proxy shows *no* segment-level
footprint gap in the South (no product has positives in strips where another
maps nothing within this region), so the disagreement is not explained by
one product not covering the region. The 0.5°-strip chart
(`fig_r4_coverage_strips.pdf`) shows all three products mapping the same
southernmost strips (~21–24°N).

## Disagreement clusters and zoom maps

`results/r4_south_china_clusters.csv` lists the top-5 connected disagreement
clusters per class and pair. The three largest (used for
`figures/fig_r4_south_china_zoom.pdf`):

1. CM-SSM–GEODATA, only-GEODATA: 2.11 km² contiguous cluster
   (centre row 20,649 / col 4,510 on the 100 m grid) — the single largest
   disagreement object in the region.
2. CMSA–GEODATA, only-GEODATA: 1.55 km² (row 22,096 / col 1,370).
3. CMSA–GEODATA, only-CMSA: 0.58 km² (row 21,317 / col 882).

The zoom panels render full-resolution real data (100 m grid, EPSG:3410
coordinates) with legible agreement/disagreement colors (both / CMSA-CM-SSM
only / GEODATA only). The regional overview figure
(`fig_r4_south_china_overview.pdf`) shows (CMSA ∪ CM-SSM) vs GEODATA for the
whole South region.

## Verdict

The South China low IoU (0.134 / 0.084) is a genuine product disagreement
with three documented components: (1) patch-boundary misalignment (~half of
each only-class within 1 km), (2) a large disjoint-segment component
(29–44% beyond 5 km, largest for GEODATA-vs-CM-SSM), and (3) systematic
patch-granularity differences (GEODATA: fewer, larger, more generalized
patches). It is *not* explained by product coverage gaps, sub-hectare
small-patch encoding, or regional attribution (R4-01: the South region
definition is stable under all assignment policies). The manuscript must not
attribute the disagreement to either product's inaccuracy; it reports the
mutual disagreement structure.

## Deliverables

- `results/r4_south_china_diagnostics.csv`
- `results/r4_south_china_fragmentation.csv`
- `results/r4_south_china_clusters.csv`
- `figures/fig_r4_south_china_zoom.pdf` / `.png`
- `figures/fig_r4_south_china_overview.pdf` / `.png`
