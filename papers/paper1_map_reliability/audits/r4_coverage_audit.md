# R4-02 — Coverage audit and coverage-normalized agreement

Run: 2026-11-08, commit `f2c7368`, script
`experiments/r4_coverage_agreement.py` (runtime 588 s), outputs
`results/r4_coverage_*`, figure `figures/fig_r4_coverage_strips.pdf`.

## Verified source-entity inventories (full resolution, this run)

**GEODATA 2020** (30 m raster, Krasovsky 1940 Albers, single band uint8,
70,184 × 43,575 = 3,058,267,800 px, block-window full read):

| Value | Pixels | Meaning |
|---|---|---|
| 1 | 577,657 (= 519.89 km²) | mapped S. alterniflora presence |
| 255 | 3,057,690,143 | uniform fill (everything else) |

**There is no explicit absence class and no valid-observation footprint.**
"True absence" and "no-data / outside mapped coverage" are indistinguishable
in the delivered entity. Any 100 m analysis pixel where GEODATA is not
positive could be either. (The published E3 harmonization warped with
`dst_nodata=0` and thresholded `==1`, which conflates the two; positive
areas are unaffected.)

**CMSA 2020** (vector, EPSG UTM 50N source): 8,914 polygons =
8,864 gridcode-2 (S. alterniflora) + 50 gridcode-0. Patch-level presence
product; no observation-domain raster ships with it.

**CM-SSM 2020** (vector): 148,072 province-coded patches
(FJ 28,619, GX 12,658, JS 2,418, GD 2,082, HB 510, …; full counts in
`r4_coverage_meta.json`). Patch-level presence product; no
observation-domain raster.

## Verdict: coverage-normalized IoU is NOT computable

A coverage-normalized IoU — IoU restricted to the intersection of the two
products' valid observation domains — cannot be computed from the delivered
entities for any pair:

- Restricting a GEODATA pair to "GEODATA's valid domain" would degenerate to
  GEODATA's own presence mask (that is all the entity contains), which is
  circular.
- CMSA and CM-SSM are patch-vector products; their observation domains exist
  only as documented study areas, not as per-pixel masks.

Per the R4 brief, **no mask was invented**. The published IoU values
therefore carry one explicit, now-documented assumption: *"not mapped as
presence == absence over the shared 100 m analysis domain"* for all three
products. This assumption is reasonable for a national coastal product trio
but is not verifiable from the delivered data, and any pixels outside a
product's true (unknown) mapping extent contribute apparent absence
disagreement.

## Computable proxies

### P1 — Coastal-strip co-mapping (0.5° latitude bands, 42 strips)

`results/r4_coverage_strips.csv`. Positive pixels of product A lying in
strips where product B maps **nothing** (segment-level footprint gaps):

| Pair | A→B-empty strips | share of A | B→A-empty strips | share of B |
|---|---|---|---|---|
| CMSA–GEODATA | 140 px (1.40 km²) | 0.25% | 0 px | 0.00% |
| CM-SSM–GEODATA | 0 px | 0.00% | 51 px (0.51 km²) | 0.10% |
| CMSA–CM-SSM | 159 px (1.59 km²) | 0.28% | 0 px | 0.00% |

At 0.5° coastal-strip granularity, all three products map presence over
essentially the same latitudinal footprint (positives span
20.9–41.0°N in every product). Whole-segment coverage differences are
negligible (<0.3% of any product's positives).

### P2 — Nearest-positive distances (per pair, symmetric)

| Direction | median km | ≤0.1 km | ≤0.5 km | ≤1 km | >5 km |
|---|---|---|---|---|---|
| CMSA→GEODATA | 0.0 | — | — | 91.69% | 1.42% |
| GEODATA→CMSA | 0.0 | — | — | 83.19% | 8.12% |
| CM-SSM→GEODATA | 0.1 | — | — | 82.75% | 5.09% |
| GEODATA→CM-SSM | 0.0 | — | — | 72.60% | 17.58% |
| CMSA→CM-SSM | 0.0 | — | — | 87.88% | 8.90% |
| CM-SSM→CMSA | 0.0 | — | — | 90.34% | 4.50% |

(full statistics in `r4_coverage_meta.json`). Most disagreement is at or near
the patch boundary (median nearest distances ≈ 0), but GEODATA has the
largest isolated-positive share: 8.1% of GEODATA positives lie >5 km from any
CMSA positive and 17.6% lie >5 km from any CM-SSM positive — candidates for
segment-level coverage/detection differences or commission, indistinguishable
without reference data (see R4-03 for the South China decomposition).

### Regional cross-check

`results/r4_coverage_by_region.csv` reproduces the E5d regional areas/IoUs
exactly (e.g. South_China: CMSA 19.27 km², CM-SSM 14.69, GEODATA 26.31;
IoU CMSA–GEODATA 0.1341), confirming cache integrity.

## Effect on the manuscript

1. The Methods/Discussion must state the "not mapped == absence" assumption
   explicitly (done in the R4-05 revision).
2. No coverage-normalized IoU numbers may be quoted (they do not exist);
   proxies above are quoted as proxies.
3. Claims about "GEODATA omission" vs "commission" are reframed as
   mutual spatial disagreement with documented isolation statistics.

## Deliverables

- `results/r4_coverage_normalized_iou.csv` (pair-level verdict + proxies)
- `results/r4_coverage_strips.csv`, `results/r4_coverage_by_region.csv`
- `results/r4_coverage_meta.json` (full entity inventories + distance stats)
- `figures/fig_r4_coverage_strips.pdf` / `.png`
