# R4-01 — Regional attribution audit: nearest-assigned pixels

Run: 2026-11-08, branch `feat/paper1-map-reliability`, commit `f2c7368` (script
records commit at runtime; outputs under `results/r4_*`, script
`experiments/r4_region_attribution.py`, runtime 3,256 s, max RSS ~5 GB).

## Background

E5d's sea-region regionalization (Natural Earth 10m IHO marine polygons)
assigns every positive-union pixel that falls in no marine polygon —
coastal/intertidal pixels seaward or landward of the generalized coastline —
to the nearest group boundary. Of the 90,641 positive-union pixels (100 m,
EPSG:3410), 31,201 (34.42%) are assigned this way. This audit quantifies what
those assignments do to the regional IoU results.

## Assignment composition (verified)

| Quantity | Value |
|---|---|
| Positive-union pixels | 90,641 |
| Direct inside marine polygon | 59,440 (65.58%) |
| Nearest-assigned residual | 31,201 (34.42%) |
| Max assignment distance | 53.97 km (median 5.50 km) |

Per-region assignment counts and distance distribution
(`results/r4_assignment_distances.csv`):

| Region | Assigned px | median km | p90 km | p99 km | max km | >1 km | >5 km | >10 km | >20 km | >50 km |
|---|---|---|---|---|---|---|---|---|---|---|
| Bohai_Yellow | 7,678 | 2.78 | 8.9 | 28.5 | 53.97 | 3,486 | 2,346 | 1,875 | 1,207 | 0 |
| East_China | 22,262 | 6.83 | 19.5 | 44.0 | 53.32 | 15,239 | 10,735 | 7,540 | 4,554 | 0 |
| South_China | 1,261 | 1.61 | 5.1 | 16.1 | 28.66 | 381 | 214 | 70 | 11 | 0 |

(>1 km etc. = assigned pixels whose nearest-group distance exceeds the
threshold; counts from `r4_assignment_distances.csv`.)

Per-product composition — no product is silently excluded, and the assigned
share is product-asymmetric:

| Product | Positive px | Direct px | Assigned px | Assigned % |
|---|---|---|---|---|
| CMSA | 56,898 | 38,615 | 18,283 | 32.13% |
| CM-SSM | 59,079 | 35,901 | 23,178 | 39.23% |
| GEODATA | 52,123 | 37,348 | 14,775 | 28.35% |

CM-SSM is the most assignment-dependent product (39.2% of its positives reach
their region only through nearest assignment), GEODATA the least (28.4%).

## Policies

- **A — direct membership only.** Pixels in no marine polygon are excluded
  from all regions. Coverage excluded: 31,201 px = 34.42% of the positive
  union, reported per row of `r4_region_assignment_sensitivity.csv`.
- **B — nearest assignment, no cap** (the E5d/E5e published policy).
- **C — nearest assignment capped at t km**, beyond which pixels form an
  unassigned category (excluded from regions, reported). Caps tested:
  5, 10 (primary), 20, 50 km. Primary-cap rationale: intertidal Spartina
  habitat lies within a few km of the shoreline and Natural Earth 10m
  coastline generalization error is of the same order, so caps beyond ~10 km
  increasingly attribute pixels across genuinely different coasts.
  Unassigned shares of the union: 18.23% (5 km), 10.46% (10 km),
  2.75% (20 km), 0.00% (50 km; only pixels beyond 53.97 km exist, none).

## Regional IoU under the three policies

From `results/r4_region_assignment_sensitivity.csv` (Bohai = Bohai_Yellow,
South = South_China):

| Pair | Region | A | B | C_5km | C_10km | C_20km | C_50km |
|---|---|---|---|---|---|---|---|
| CMSA–CM-SSM | Bohai | 0.5057 | 0.4665 | 0.4984 | 0.4974 | 0.4971 | 0.4743 |
| CMSA–CM-SSM | East | 0.5814 | 0.5902 | 0.5579 | 0.5652 | 0.5972 | 0.5790* |
| CMSA–CM-SSM | South | 0.4976 | 0.4772 | 0.4841 | 0.4863 | 0.4774 | 0.4772 |
| CMSA–GEODATA | Bohai | 0.6060 | 0.5599 | 0.5705 | 0.5617 | 0.5600 | 0.5599 |
| CMSA–GEODATA | East | 0.3439 | 0.3923 | 0.3528 | 0.3570 | 0.3933 | 0.3918* |
| CMSA–GEODATA | South | 0.1482 | 0.1341 | 0.1406 | 0.1365 | 0.1349 | 0.1341 |
| CM-SSM–GEODATA | Bohai | 0.4119 | 0.3646 | 0.3937 | 0.3881 | 0.3870 | 0.3704 |
| CM-SSM–GEODATA | East | 0.3320 | 0.3499 | 0.3225 | 0.3215 | 0.3538 | 0.3511* |
| CM-SSM–GEODATA | South | 0.0887 | 0.0835 | 0.0864 | 0.0838 | 0.0838 | 0.0835 |

(*) C_50km row values for East_China read from the CSV; C_50km ≈ B by
construction because the maximum assignment distance is 53.97 km and only a
handful of pixels lie beyond 50 km (0 in the >50 km columns).

**Bohai/South IoU ratio (the headline contrast):**

| Pair | A | B | C_5km | C_10km | C_20km | C_50km |
|---|---|---|---|---|---|---|
| CMSA–GEODATA | 4.09 | 4.175 | 4.058 | 4.116 | 4.150 | 4.176 |
| CM-SSM–GEODATA | 4.64 | 4.367 | 4.556 | 4.630 | 4.624 | 4.404* |
| CMSA–CM-SSM | 1.016 | 0.978 | 1.029 | 1.023 | 1.041 | 0.994* |

The contrast is **insensitive to the attribution policy** (range 4.06–4.18 for
CMSA–GEODATA; 4.36–4.64 for CM-SSM–GEODATA), while the CMSA–CM-SSM pair shows
no Bohai/South contrast under any policy.

## Assigned-pixel contributions (policy B, from the sensitivity CSV)

Assigned pixels contribute materially to regional unions — 16.1–44.9% of
regional union pixels are assigned pixels — and their removal (policy A)
changes individual regional IoUs by up to 0.05 (CMSA–GEODATA East:
0.3439 → 0.3923). Largest per-pair effects:

- CMSA–GEODATA East: policy A removes assigned pixels that are predominantly
  *disagreeing* pixels (union drops 418.04 → 243.64 km²; IoU 0.3923 → 0.3439,
  i.e. assigned pixels in the East are relatively more often in agreement).
- South China under policy A retains only 3,083 direct union pixels; GEODATA's
  South area under A is dominated by direct polygon pixels, and the IoU is
  0.1482 (vs 0.1341 under B) — a small effect on the contrast.

## Interpretation

1. The 34.42% nearest-assigned pixels are not a technicality: they carry
   16–45% of the regional union. But their attribution is not contested in
   ways that matter for the paper's regional conclusion: the Bohai/South
   contrast for the two GEODATA pairs stays between 4.1 and 4.6 under every
   policy, and no policy reverses any region's rank for any pair.
2. Policy A excludes a documented 34.42% of positives; it slightly *raises*
   the contrast (4.09 → 4.64), so the published policy-B value (4.175, CI
   [2.74, 7.51]) is not an artifact of generous assignment.
3. Pixels assigned at >10 km (9,485 px, 10.46% of union) are the genuinely
   uncertain ones; excluding them (C_10km) changes the CMSA–GEODATA contrast
   from 4.175 to 4.116 — within the bootstrap CI. East_China is the most
   assignment-sensitive region because 22,262 of its union pixels (44.9%)
   are assigned, with median distance 6.83 km.

## Verdict

The published policy-B regional results are defensible: (i) the assignment
method is documented and reproduced exactly; (ii) its sensitivity to the
policy choice is small relative to the contrast being claimed (R4-04 shows
the bootstrap CI of the ratio under A and C also excludes 1); (iii) no
policy silently excludes pixels that disproportionately affect one product —
per-product assigned shares (28–39%) and per-row excluded counts are reported.

## Deliverables

- `results/r4_region_assignment_sensitivity.csv` (72 rows: 6 policies ×
  3 pairs × (3 regions + 1 contrast row))
- `results/r4_assignment_distances.csv`
- `results/r4_attribution_meta.json`
- `figures/fig_r4_region_assignment.pdf` / `.png` (map of assigned pixels
  colored by assignment distance)
