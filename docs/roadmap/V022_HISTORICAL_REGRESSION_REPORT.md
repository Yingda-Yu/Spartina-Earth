# V022_HISTORICAL_REGRESSION_REPORT — read-only reclassification of 478 optical products

Test: `benchmarks/spartinashift/v0_2_1_repair/V022_REGRESSION_TESTS/classify_v022.py`
Machine-readable results:
`benchmarks/spartinashift/v0_2_1_repair/V022_REGRESSION_TESTS/V022_REGRESSION_RESULTS.json`
Run 2026-11-27, read-only (rasters opened only for the 2 zero-valid
candidates; all other classifications from manifest QA blocks; no file
modified).

## 1. Population

478 optical products = 443 panel (Issue #21 Phase H) + 35 repair
(Phase 2A). Sentinel-1 products (no QA_PIXEL semantics) excluded from
the optical contract.

## 2. v0.2 classification (frozen Phase J rule)

| class | n |
|---|---|
| accepted (all bands finite, VALID > 0) | 308 |
| accepted, partial-finite (min band finite < 1.0, VALID > 0) | **168** (146 panel + 22 repair) |
| honest rejection ZERO_QA_VALID_SURFACE_PIXELS (zero-valid, all-finite) | 1 — `V02_R00355-C00151_L8_2015_L` (panel) |
| hard error (zero-valid, partial-finite) | 1 — `V021_R00372-C00139_L8_2015_E` (repair) |

## 3. v0.2.2 classification (pixel-evidence rule) — differences

**Exactly one reclassification** (all 477 other products identical):

| product | v0.2 | v0.2.2 | pixel evidence |
|---|---|---|---|
| `V021_R00372-C00139_L8_2015_E` | HARD_ERROR | HONEST_REJECTION_ZERO_QA_VALID_SURFACE_PIXELS | nonfinite_total 1,518; nonfinite_inside_offline_qa_valid_set **0**; fill_bit_pixels_anywhere **0**; SHA-256/grid/physical/mask-gate all pass |

The panel's honest rejection also re-passes under v0.2.2 (condition 5
vacuously true — it has zero non-finite pixels), so both contracts agree
on it; no retroactive change.

## 4. Assertions (all PASS)

```
panel_optical_products = 443                 ✔
repair_optical_products = 35                 ✔
exactly_1_panel_honest_rejection             ✔
panel_partial_finite_accepted_146            ✔
repair_partial_finite_accepted_22            ✔
exactly_1_zero_valid_partial_finite_product  ✔
v0_2_2_changes_only_that_product             ✔
```

## 5. Traceability

- Per-product classifications: `V022_REGRESSION_RESULTS.json`
  (`document_checksum` in `V022_PROTOCOL_CHECKSUM.json`).
- Pixel evidence recomputed from landed rasters; deterministic predicate
  documented in `V022_QA_PROTOCOL_FINAL.md` §2 and
  `VALID_MASK_CONSISTENCY_REPORT.md` §4.
- v0.2 rule source: `qa_v02_export.py::_informative_check` (frozen,
  unmodified); v0.2.2 rule: `V022_QA_PROTOCOL_FINAL.md` (proposal, not
  yet effective).
- No special exception was written for any single product: the rule is
  a general predicate, and the regression proves it leaves 477/478
  historical classifications untouched.
