# REPAIR_EXPORT_LOG — Phase 2A Step 4 (Option A Landsat-only)

Owner authorization: Option A (2026-11-26). Export executed 2026-11-27
with `scripts/benchmarks/spartinashift/export_v02_1_repair.py` — a repair
namespace runner reusing the frozen Issue #21 Phase H export machinery
(pilot19 V2 scheduler, task store, Drive landing, watchdog) with all
paths, Drive folder (`SpartinaEarthV021Repair`), product ids (`V021_*`),
revision (`V0_2_1_REPAIR`) and task requests redirected. No frozen v0_2
export artifact, task, or Drive product was touched.

## Gates passed before submission

1. `LIVE_GEE_REPAIR_PLAN.json` checksum verified.
2. `V0_2_1_REPAIR_SCOPE_ESTIMATE.json` checksum verified; owner
   authorization present; plan products (35) == estimate planned
   observations (35); 3×35 = 105 tasks == estimate; 0.150 GiB ≤ Option A
   cap; global caps (96 cells / 40 GiB / 10,000 tasks) untouched and not
   breached (35 repair products on top of the existing 53-cell panel =
   67 ≤ 96; landed bytes ≈ 0.13 GiB this run).
3. Canary first: `V021_R00163-C00067_L8_2015_E` — 1st attempt failed on a
   runner defect (panel missing `coastal_segment` for manifest
   validation; runner bug, not GEE/QA — fixed by mapping province →
   coastal_segment via the frozen `pilot_panel.coastal_segment` table);
   2nd attempt LANDED (3 files, 3.5 MB), no hard stop afterwards.

## Execution record (real GEE task IDs)

- 35 products × 3 component tasks = **105 GEE export tasks submitted,
  105 succeeded, 0 failed** (task store:
  `work/issue21/export_repair/tasks/task_store.json`, 105 entries with
  real backend task ids, e.g. `NDWUZZZPJ4DH765RWWP3DPZE`,
  `3KB6GSFOM73XAWA4POQFLDD3`, `JUF6J54SLL35IOEQC4IDIA32`; every
  task-id ↔ product mapping in `REPAIR_EXPORT_MANIFEST.json`).
- Landed: **35/35 products, 132,432,833 bytes (126.3 MiB)**, Drive folder
  `SpartinaEarthV021Repair`, local mirrors + per-product manifests under
  `work/issue21/export_repair/{products,manifests}/`.
- Concurrency 7, run duration ≈ 25 min, no hard stop, no retry storms
  (`attempts: 1` for all tasks).

## Post-export per-product QA (Step 4 checklist)

Run via `qa_v02_1_repair.py` (frozen Phase J QA machinery redirected to
the repair namespace; zero threshold change). Full JSON:
`REPAIR_QA_REPORT.json`; narrative: `REPAIR_QA_REPORT.md`.

| Check | Result |
|---|---|
| files landed / readable | 105/105 GeoTIFFs opened |
| SHA-256 of landed files | 105/105 match manifest |
| CRS / locked transform / dimensions | 105/105 rebuilt and identical to plan grid |
| 30 m pixel resolution | verified via locked-transform rebuild |
| NoData semantics | physical audit pass on all products |
| QA_PIXEL masking | valid-mask component verified; 1 product zero-valid (see QA report) |
| actual valid fraction ≥0.95 (replayed on landed bytes) | 34/34 products in accepted denominator ≥ 0.9504 (min) |
| manifest ↔ file consistency | 35/35 |

## Outcome

- 34/35 products clean (L7 5, L8 29).
- 1 product — `V021_R00372-C00139_L8_2015_E` — byte-faithful and
  gate-passing on byte fraction (0.990 ≥ 0.95) but its VALID component
  has **zero QA_PIXEL-valid surface pixels**; band_1/band_2 finite
  fractions 0.990/0.997 (< 1.0), so the frozen honest-rejection
  precondition (every SR band finite) is NOT met → classified as hard
  error per the unchanged frozen contract, excluded from the accepted
  denominator. No threshold was relaxed; no reclassification.
