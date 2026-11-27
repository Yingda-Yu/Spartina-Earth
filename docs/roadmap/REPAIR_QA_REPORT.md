# REPAIR_QA_REPORT — Phase 2A Step 4

Full machine-readable evidence: `REPAIR_QA_REPORT.json` (checksum in
document). QA executed by the frozen Phase J contract
(`qa_v02_export.py` machinery, redirected to the repair namespace, zero
modification). Contracts replayed per product: landed SHA-256, locked
transform/dimensions/CRS rebuild, ≥0.95 actual-mask gate replay on landed
bytes (grid + W10 cell), physical scaling/band order/QA semantics,
informative-raster check, Issue #21 provenance block.

## Verdict (frozen contract, unchanged)

`QA_FAIL_SYSTEMATIC_STOP` — exactly one product fails a check:

- `V021_R00372-C00139_L8_2015_E` — "VALID component has zero valid
  pixels": the landed QA_PIXEL-valid surface mask is 0/151,285 while SR
  bands are 98.9–100 % finite and the byte-level actual-mask is 0.990
  (≥0.95). The frozen honest-rejection class `ZERO_QA_VALID_SURFACE_PIXELS`
  requires every SR band 100 % finite; band_1/band_2 have 1.0 %/0.3 %
  non-finite pixels, so the precondition is unmet and the frozen
  implementation classifies it as a hard error. **No threshold was
  changed and no reclassification was performed.** Materially this is
  the same source-quality phenomenon as the panel run's honest rejection
  (`V02_R00355-C00151_L8_2015_L`), which is an Owner-review item, not
  something the agent resolves by contract change.

## Accepted-denominator results (34 products, 12 cells)

| sensor | landed | failed checks | W10 fraction min | median | below gate |
|---|---|---|---|---|---|
| landsat7 | 5 | 0 | 0.9511 | 0.9752 | 0 |
| landsat8 | 29 | 1 (excluded) | 0.9795 | 0.99999 | 0 |

- The excluded product's cell (R00372-C00139, positive) retains both-year
  support through its 2015-M and 3 × 2020 slots — the gate outcome does
  not depend on the excluded product.
- Honest rejections in the accepted set: none.
- Figures/contact sheets: `work/issue21/qa_repair/` (SHA-256s in the JSON).

## Gate-support alignment (repair-only, QA-clean)

- positive cells (GEODATA 2015∧2020) with landed, QA-passed Landsat in
  **both** years: 4 — R00331-C00149, R00352-C00155, R00372-C00139,
  R00416-C00120
- background cells with landed, QA-passed Landsat in both years: 1 —
  R00364-C00141
- combined with frozen v0.2 measured support: positives 11 + 4 = **15 ≥ 12**,
  backgrounds 11 + 1 = **12 ≥ 12**, regions 5 ≥ 3 (see final readiness
  decision JSON for the strict verdict semantics).
