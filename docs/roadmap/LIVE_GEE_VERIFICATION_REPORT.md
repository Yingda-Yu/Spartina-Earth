# LIVE_GEE_VERIFICATION_REPORT — Phase 2A Step 1 (Option A)

Executed 2026-11-27 with live GEE (`project-795fc21c-e217-47f3-adb`, fresh
user credentials after re-authentication). Scope: exactly the 14 frozen
repair candidates, Landsat 7/8, years 2015/2020 — no cell added, no
re-ranking, no QA change. Evidence source for every decision:
`LIVE_GEE_EXPORT_GRID` (actual 30 m export grid, per-scene `ee` evaluation
of QA_PIXEL fill bit + all SR bands masked-present), identical to the
frozen Issue #21 Phase D/E contract. Frozen artifacts: none modified.

Froze plan: `LIVE_GEE_REPAIR_PLAN.json` (checksum `3a7e4669f287`),
`LIVE_GEE_REPAIR_PLAN.csv`. Discovery prefilter (DOY 260–320 autumn,
nominal coverage ≥0.95, scene cloud ≤0.30) then tertile slotting (≤1
event per tertile, ≤3 per cell-year, no cross-tertile borrowing) then
the ≥0.95 actual-observed-mask gate. Slot-level tally across the run:
35 `V02_ELIGIBLE`, 28 `NO_SCENE`, 21 `NO_ELIGIBLE_EVENT_ACTUAL_MASK`.

## Per-cell results (live verified)

| cell | role | 2015 elig | 2020 elig | verdict | scenes |
|---|---|---|---|---|---|
| R00331-C00149 (ZJ) | POS | 1 | 1 | **both-year PASS** | L8 2015-10-13 (M); L8 2020-11-11 (L) |
| R00348-C00154 (SH) | POS | 2 | 0 | 2020 fail (no eligible event) | L8 2015-10-06 (E), 2015-10-22 (M) |
| R00352-C00155 (JS) | POS | 2 | 2 | **both-year PASS** | L8 2015-10-06/22; L7 2020-10-11 (M, frac 0.950), L7 2020-11-12 (L, 0.962) |
| R00372-C00139 (JS) | POS | 2 | 3 | **both-year PASS** | L8 2015-09-27 (E, 0.990), 2015-10-13 (M); L8 2020-09-24 (E), 10-10 (M), 11-11 (L) |
| R00324-C00156 (ZJ) | POS | 0 | 0 | both-year fail | — |
| R00224-C00047 (GX) | POS | 2 | 0 | 2020 fail | L8 2015-09-30 (E), 10-16 (M) |
| R00315-C00157 (ZJ) | POS | 0 | 0 | both-year fail | — |
| R00416-C00120 (SD) | POS | 3 | 2 | **both-year PASS** | L7 2015-10-03 (E, 0.972), 10-19 (M, 0.983); L8 2015-10-27 (L); L7 2020-09-30 (E, 0.9999); L8 2020-10-24 (M) |
| R00188-C00044 (HN) | BG | 2 | 0 | 2020 fail | L8 2015-09-30 (E), 10-16 (M) |
| R00364-C00141 (JS) | BG | 2 | 3 | **both-year PASS** | L8 2015-09-27 (E), 10-13 (M); L8 2020-09-24 (E), 10-10 (M), 11-11 (L) |
| R00215-C00058 (GD) | BG | 2 | 0 | 2020 fail | L8 2015-09-30 (E), 10-16 (M) |
| R00205-C00047 (HN) | BG | 2 | 0 | 2020 fail | L8 2015-09-30 (E, 0.9999), 10-16 (M) |
| R00163-C00067 (UNK) | BG | 3 | 0 | 2020 fail | L8 2015-09-23 (E, 1.0), 10-25 (M, 0.980), 11-10 (L, 0.999) |
| R00232-C00095 (GD) | BG | 1 | 0 | 2020 fail | L8 2015-09-25 (E, 0.996) |

All landed-eligible fractions quoted are `actual_observed_fraction` on the
exact 30 m export grid (≥0.95 gate; minimum in the accepted set: 0.9504,
an L7 2020 SLC-off era scene — SLC-off quality recorded per scene via
`l7_era`; L7 products carry `qapixel` components and passed the same
gates). Every slot row records WRS path/row, scene ID, source product ID,
acquisition date, grid CRS/transform/136,518-pixel dimensions.

## Notes

- The 2020 deficit pattern observed in the original panel repeats: all 6
  background candidates and 2 of 8 positive candidates have zero
  2020-eligible events under the unchanged QA contract. This is recorded,
  not repaired by relaxation.
- R00163-C00067 (background audited in Phase 1.1): its metadata 2-event
  2020 estimate did NOT survive live verification (0 eligible). The cell
  is kept with 2015-only support and is excluded from both-year
  background support — consistent with the frozen QA rules, no post-hoc
  threshold was applied.
- Grid identity for every candidate: CRS/transform/width/height frozen in
  the plan JSON (`grid` block) and reproduced in export manifests.
