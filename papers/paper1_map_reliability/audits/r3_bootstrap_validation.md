# R3.1 — Bootstrap validation and statistical recovery

**Date:** 2026-11-05
**Branch:** `feat/paper1-map-reliability`
**Scripts:** `experiments/e5e_bootstrap_100m.py` (new);
`experiments/e5c_bootstrap_iou.py` (superseded)
**Outputs:** `results/e5e_bootstrap_100m.csv`,
`results/e5e_region_contrasts_100m.csv`,
`results/e5e_moran_100m.csv`,
`results/e5e_bootstrap_meta.json`

---

## 0. The defect being repaired

The R2 manuscript paired **30 m IoU point estimates** with **100 m bootstrap
confidence intervals**. Those are two different estimands. `e5c_bootstrap_iou.py`
hard-coded `RES_M = 100` and bootstrapped at 2 km blocks on the 100 m grid,
while `Table 3` (and the RQ2 summary) quoted the 30 m grid values 0.5375 /
0.4437 / 0.3423. The CI and the point estimate did not describe the same
quantity, and the R2 text compounded this by inferring significance from
non-overlapping marginal intervals.

**Primary estimand chosen:** 100 m. Justification: E4 shows IoU changes by
at most 0.4 % between 30 m and 100 m (0.5375→0.5395, 0.4437→0.4444,
0.3423→0.3432), so 100 m loses no material information; and the corrected
analysis computes point estimate, interval and regional contrast all on the
100 m grid.

## 1. Resampling unit (checklist item 1)

A **square spatial block** on the fixed 100 m EPSG:3410 grid. At the primary
scale the block is 2 km × 2 km = 20 × 20 cells. Blocks are the unit of
resampling because individual cells are strongly autocorrelated (§5).
For each block and product pair the script precomputes

- `c_a[b]`, `c_b[b]`: positive-cell counts of product A and B in block `b`;
- `c_i[b]`: intersection-cell count;
- `c_u[b]`: union-cell count.

Each bootstrap replicate draws block indices with replacement and computes
`IoU*_r = Σ_b i_b / Σ_b u_b`. This is O(n) per replicate over ~2,000
informative blocks and runs in 122 s for 3 pairs × 4 block sizes
× 3 scales × 5 seeds.

## 2. Does the resampling match the estimand? (item 2)

Yes. The point estimate in `regional_geographic_2020.csv` is
`Σ_pixels (A∧B) / Σ_pixels (A∨B)` over the region. The bootstrap statistic
is `Σ_blocks i_b / Σ_blocks u_b` over resampled blocks of the same region,
which is the same ratio-of-sums estimator, not the mean of per-block IoUs.
The mean of the bootstrap distribution tracks the exact value to within
0.001–0.002 in every cell of the CSV.

## 3. Empty, positive and informative blocks (item 3)

At 2 km the domain contains **837,295** blocks:

| Pair | Empty (union = 0) | Positive (union > 0) | Informative | Both-positive |
|---|---|---|---|---|
| CMSA–CM-SSM | 835,281 | 2,014 | 2,014 | 1,384 |
| CMSA–GEODATA | 835,205 | 2,090 | 2,090 | 1,072 |
| CM-SSM–GEODATA | 835,039 | 2,256 | 2,256 | 1,036 |

"Positive" and "informative" coincide here (any union pixel makes the block
informative about intersection). The "both-positive" count is the subset
where the two products actually overlap in that block. **0.24–0.27 %** of
blocks carry all the information, which fixes the effective sample size at
about 2,000 spatial units, not the 334.62 million cells of the 100 m grid.

## 4. Multiple block sizes (item 4)

Tested at **1, 2, 5 and 10 km**. National 95 % interval half-widths:

| Pair | 1 km | 2 km (primary) | 5 km | 10 km |
|---|---|---|---|---|
| CMSA–CM-SSM | 0.018 | 0.030–0.031 | 0.050–0.058 | 0.059–0.072 |
| CMSA–GEODATA | 0.017 | 0.029–0.032 | 0.043–0.049 | 0.054–0.062 |
| CM-SSM–GEODATA | 0.019–0.020 | 0.028–0.029 | 0.048–0.050 | 0.063–0.070 |

Interval width increases monotonically with block size, as expected when
fewer independent units remain. **2 km is reported as primary** because it
brackets stand-scale dependence while retaining ~2,000 informative blocks;
1, 5 and 10 km are released as sensitivity scales.

## 5. Spatial dependence and block-size justification (item 5)

Moran's *I* on block-level IoU, row-standardised k-nearest-neighbour weights
(k = 8), 999-permutation null (`results/e5e_moran_100m.csv`):

| Scale / pair | 2 km | 5 km | 10 km |
|---|---|---|---|
| CMSA–CM-SSM, national | 0.312 (p = 0.001) | 0.290 | 0.249 |
| CMSA–GEODATA, national | **0.444** (p = 0.001) | 0.340 | 0.305 |
| CM-SSM–GEODATA, national | 0.407 (p = 0.001) | 0.281 | 0.220 |

Dependence is strong and decays slowly, so pixel-level resampling would
understate variance by roughly an order of magnitude. Block resampling is
required, and the growth of CI width from 1→10 km quantifies the residual
dependence that a 2 km block does not absorb.

A notable exception: in the **South China Sea** the dependence is not
detectable for the GEODATA pairs at larger blocks (CMSA–GEODATA: I = 0.052,
p = 0.197 at 5 km; I = 0.004, p = 0.944 at 10 km; CM-SSM–GEODATA:
I = 0.072, p = 0.056 at 5 km). CMSA–CM-SSM retains a weak positive value
(I = 0.186, p = 0.002 at 5 km; I = 0.219, p = 0.004 at 10 km), though those
estimates rest on only 57–99 blocks. Positive area there is small and
scattered, so block-level IoU behaves close to independent noise. This
supports treating the wide South China interval as genuine sampling
uncertainty rather than unmodelled autocorrelation.

## 6. Empty and boundary block treatment (item 6)

- Blocks with `union = 0` are **excluded from the resampling pool** and
  reported in `n_blocks_empty`. Including them would have added draws that
  contribute nothing and would have distorted the replicate distribution.
- Blocks that straddle a region boundary contribute only the cells that fall
  inside the region mask. The region mask is applied before the block
  histogram, so the resampled domain is exactly the intended region, not
  a bounding box.
- Regions are disjoint, so regional bootstraps are independent and can be
  combined replicate-by-replicate for contrasts.

## 7. Direct inference on differences and ratios (item 7)

Non-overlapping marginal intervals are **not** used as a test. Instead the
difference and ratio distributions are formed replicate by replicate from
independent regional bootstraps (`results/e5e_region_contrasts_100m.csv`,
2 km, 1,000 replicates, seed 202601). The two-sided p value is the fraction
of replicates whose sign contradicts the point estimate.

| Pair | Contrast | Difference [95 % CI] | Ratio [95 % CI] | p |
|---|---|---|---|---|
| CMSA–GEODATA | Bohai/Yellow − South China | +0.426 [0.346, 0.499] | 4.18 [2.74, 7.51] | < 0.001 |
| CMSA–GEODATA | East China − South China | +0.258 [0.181, 0.329] | 2.93 [1.93, 5.19] | < 0.001 |
| CMSA–GEODATA | Bohai/Yellow − East China | +0.168 [0.113, 0.223] | 1.43 [1.27, 1.62] | < 0.001 |
| CM-SSM–GEODATA | Bohai/Yellow − South China | +0.281 [0.209, 0.345] | 4.37 [2.64, 9.10] | < 0.001 |
| CM-SSM–GEODATA | Bohai/Yellow − East China | +0.015 [−0.045, 0.074] | 1.04 [0.88, 1.22] | 0.646 |
| CMSA–CM-SSM | Bohai/Yellow − South China | −0.011 [−0.100, 0.077] | 0.98 [0.81, 1.19] | 0.876 |
| CMSA–CM-SSM | East China − South China | +0.113 [0.040, 0.200] | 1.24 [1.08, 1.50] | 0.008 |

The regional contrast is therefore **pair-specific**: resolved for the two
GEODATA pairs, and absent (or reversed but non-significant) for
CMSA–CM-SSM.

## 8. Monte Carlo uncertainty and seeds (item 8)

Seeds: **202601–202605** (five independent runs of 1,000 replicates each).
Monte Carlo uncertainty = standard deviation of interval endpoints across
seeds (`mc_seed_*_std` columns): 0.0004–0.0060 IoU units, median 0.0016.
This is an order of magnitude below the reported interval half-widths
(0.017–0.072), so 1,000 replicates are sufficient and interval endpoints
are stable to the third decimal.

## 9. Why the earlier R3 bootstrap job stalled

The interrupted R3 run was the first version of `e5d_geographic_regions.py`
(the admin-1 province variant). It was killed after **16 min 40 s**, at
**23.7 GB RSS**, with a single core at 95 %.

**Root cause.** `assign_residual()` built four full-grid float64
`distance_transform_edt` arrays to compute nearest-region assignment
(15096 × 22166 = 334.6 M cells × 8 bytes ≈ 2.7 GB each, ≈ 10.7 GB for the
four, plus the masks, KD-tree inputs and temporaries). The process was
memory-bound, not compute-bound, and swapping/allocator pressure made it
effectively stall rather than fail with an exception.

**Fix.** Replaced the four full-grid distance transforms with one KD-tree
built on the boundary pixels of each group mask (a few thousand points),
querying only the ~31 k residual positive cells. No full-grid float64 array
is allocated.

**Post-fix cost:**

| Job | Runtime | Peak RSS | Output |
|---|---|---|---|
| `e5d_geographic_regions.py` | 234.8 s | < 4 GB | regional metrics, region JSON |
| `e5e_bootstrap_100m.py` | 121.8 s | 3.68 GB | bootstrap, contrasts, Moran |
| `e6_agreement_map.py` (rerun) | 88.7 s | — | fig03 |

No repeated expensive jobs were launched before the diagnosis above.

### 9.1 The other interrupted R3 script

`experiments/r3_bootstrap_validation.py` (renamed to
`experiments/superseded_r3_bootstrap_validation_DO_NOT_RUN.py`) was the
first attempt at this audit. It was not run to completion and its output is
not used. Three defects are recorded:

1. **Resampling memory.** At the 1 km pass it builds
   `idx = rng.randint(0, n, size=(200, n))` with `n = 3,344,088` blocks, i.e.
   a 200 × 3.34 M int64 index array of ≈5.35 GB, plus two gathered arrays of
   the same shape. Peak allocation per chunk is ≈16 GB, on a process that
   already holds the 334.6 M-cell masks. This is the same class of
   full-grid-size allocation that stalled the geometric run (§9).
2. **Wrong regions.** Its Part B stratifies at x = 11.0 Mm / 11.5 Mm, i.e.
   the superseded meridian bands.
3. **Invalid Moran's I.** `morans_i_block()` replaces S0 by
   `sum(kernel) * nobs / 2` and applies a neighbour mean over a masked grid
   without renormalising for missing cells, yielding |I| ≤ 0.12. The
   correctly computed values are 0.31–0.44 at 2 km, so the script's
   "autocorrelation is negligible" verdict is an artefact of the estimator.

Consequently its self-written verdict ("R2 bootstrap results are
independently confirmed and strengthened") is not an independent finding and
is not cited.

## 10. Residual limitations

- The bootstrap treats 2 km blocks as exchangeable within a region. Spatial
  dependence is not fully absorbed; the 5–10 km sensitivity shows the
  direction of the bias (intervals too narrow at 2 km).
- The South China Sea has only 211–259 informative 2 km blocks; its interval
  is correspondingly wide and its Moran's *I* is not detectable at 5–10 km.
- Blocks are aligned to the global grid, not to coastline geometry; a
  coastline-following block design would be preferable but is not
  implemented.
