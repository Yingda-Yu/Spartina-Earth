# V022_FINAL_ACCEPTANCE_REPORT — independent QA acceptance (Phase 2C.1)

Verdict: **independent verification COMPLETE**; v0.2.2 remains
**PROPOSED — pending Owner approval** (no READY state was set, no
protocol made effective, no training started). All checks below were
executed fresh in this phase, not copied.

## 1. QA_RADSAT evidence (P0)

- QA_RADSAT confirmed present in the original GEE scene and traceable
  through the frozen export code (`build_landsat` line 545–549) and
  task requests; it was never an exported component.
- **Direct live re-read for the target product**: 152,766 px sampled,
  QA_RADSAT min=max=0 → zero saturation flags. Supersedes the proxy
  for `V021_R00372-C00139_L8_2015_E`. Proxy labelling retained for all
  other products (`QA_RADSAT_EVIDENCE_REPORT.md`). VALID predicate
  unchanged.

## 2. Raster-level regression (P1) — real reads, not manifest copies

From `V022_RASTER_LEVEL_REGRESSION.csv` (+ JSON summary):

| metric | value |
|---|---|
| optical products | 478 (443 panel + 35 repair) |
| fully readable (sr+valid+qapixel) | **198** (163 panel + 35 repair) |
| partial (sr+valid present, qapixel pruned locally) | 280 panel |
| unreadable GeoTIFFs | **0** |
| zero-valid candidates (the decisive subset) | 2/2 fully raster-covered |
| v0.2.2 reclassifications from raster evidence | **exactly 1** (`V021_R00372-C00139_L8_2015_E` HARD_ERROR → HONEST_REJECTION) |
| max nonfinite∩offline-QA-valid across readable products | 2,670 px (`V02_R00355-C00151_L8_2020_M`, panel) |

Missing-file accounting: all 280 missing entries are the **qapixel
component of panel products, absent from the local mirror** (post-QA
local disk cleanup; sr+valid remain). Reasons recorded per product in
the CSV. Consequence: QA_PIXEL bit census cannot be recomputed locally
for those 280 — their acceptance/rejection classifications still rest
on the frozen Phase J QA run (which processed the then-present files)
plus landed VALID rasters; this limitation is recorded, not hidden.
Drive-side originals were not fetched (read-only phase).

Semantic note confirmed by raster evidence: the offline QA-valid set is
a **superset** of landed VALID (gap = QA_RADSAT and all-SR-observed
terms). The 2,670-px case is the documented pilot-D1 phenomenon
(QA-clear pixels with interior band gaps; production VALID excludes
them; product VALID > 0 → accepted). v0.2.2 condition (e) applies only
to zero-valid products, so this case is unaffected — the rule and the
predicate are consistent.

## 3. Denominator semantics (P1) — fixed definitions

1. **Honest rejections are NOT QA-pass accepted products.** They are
   recorded, versioned rejections of the honest-source-quality class.
2. **Honest rejections never enter training, validation, or test
   denominators** — neither for support-matrix counts, model budgets,
   nor accuracy statistics.
3. **A QA batch verdict of PASS (with or without honest rejections)
   does not increase the count of usable observations**: the accepted
   denominator is the count of products with `VALID > 0` and passing
   contracts only (currently 34 of 35 repair products; the rejected
   product stays out regardless of batch verdict).
4. **All spatial-isolation rules and the Reserve are unchanged**:
   the 24-cell sealed reserve remains sealed-after-export, panel/repair
   role assignment untouched, no spatial re-labelling of any kind.

## 4. Acceptance summary

| acceptance item | status |
|---|---|
| QA_RADSAT direct verification (target) | PASS |
| classify_v022.py code audit (paths/coverage/evidence) | PASS |
| clean-worktree re-run, exit 0, identical result | PASS |
| raster-level regression executed (198 fully readable, 0 unreadable, missing accounted) | PASS |
| zero-valid subset raster coverage 2/2 | PASS |
| v0.2.2 changes exactly 1 historical classification | PASS |
| denominator semantics fixed and documented | PASS |
| restrictions (no re-export, no raster/label/Reserve/v0.2 changes, no training, no READY) | honored |

**Paused** — awaiting Owner decision on making v0.2.2 effective
(recorded in `V022_PROTOCOL_CHECKSUM.json`, still `PROPOSED_NOT_EFFECTIVE`).
