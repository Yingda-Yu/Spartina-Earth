# RANK2_EXPORT_LOG — Phase 2A.1

Owner decision: Option B (rank-2 substitute for
`V021_R00372-C00139_L8_2015_E`). **Outcome: substitute does NOT exist
under the frozen rules — replacement export NOT executed; paused and
reported per the Owner's own instruction ("如果 rank-2 不存在或不符合冻结
条件，暂停并报告").**

## 1. Manifest remediation (executed first, independent of the pause)

`UPDATED_REPAIR_EXPORT_MANIFEST.json` rebuilt with provenance strictly
from the frozen `LIVE_GEE_REPAIR_PLAN.json` slots (matched by
cell_id/sensor/year/tertile — no filename inference) and real bytes read
from the landed files:

| Verification | Result |
|---|---|
| products | 35/35 |
| unique component task IDs | 105/105 (real GEE backend ids, e.g. `NDWUZZZPJ4DH765RWWP3DPZE`) |
| landed GeoTIFFs re-hashed | 105/105 SHA-256 match |
| landed bytes (disk, not estimate) | 132,432,833 |
| product→scene mapping (manifest `source_scene_ids` == frozen plan `scene_id`) | 35/35 |
| product→event mapping (manifest `observation_event_id` == frozen plan `event_id`) | 35/35 |
| event_id / scene_id / acquisition_date backfilled | 35/35 (previously empty due to runner field-name mismatch — runner bug, fixed) |

## 2. Rank-2 audit (evidence chain, frozen sources only)

1. **Frozen evaluated pool** for the slot (LIVE_GEE_REPAIR_PLAN.json,
   `n_candidates_evaluated = 2`):
   - rank-1: `LE07_119037_20150919` (L7, DOY 262) — live actual-mask
     **0.74625 < 0.95 → gate-failed pre-export**, never eligible;
   - rank-2: `LC08_119037_20150927` (L8, DOY 270) — live actual-mask
     0.990 → the ONLY gate-passing candidate → selected and exported →
     failed POST-export QA (zero QA_PIXEL-valid surface pixels).
2. **Census universe audit** (all 16 autumn Landsat events for the cell
   in 2015): EARLY tertile (DOY 260–279) FULL_CELL_COVERED events are
   exactly the two above plus `EVT-L-af7f425d3981f139` (L7, DOY 278,
   `LE71190372015278EDC00`) — **excluded by the frozen scene-cloud
   prefilter** (cloud_cover 43 % > 0.30; verified against the frozen
   planner source, lines 189–196, using the `cloud_cover` field).
   Remaining EARLY events are `PARTIAL_CELL_OVERLAP` (nominal < 0.90).
3. **Conclusion: no gate-passing rank-2 substitute exists.** Producing
   one would require either re-admitting the 0.746 scene (QA threshold
   violation) or expanding the discovery pool (cloud 43 % / partial
   coverage — frozen-rule violation). Neither is permitted.

## 3. Actions taken / not taken

- Replacement export: **NOT executed** (no eligible substitute).
- The other 34 clean products: untouched, not re-exported.
- Frozen v0_2 files: untouched. Labels/QA thresholds/Reserve: untouched.
- No training, no paper action.

## 4. Consequences (unchanged from Phase 2A, formally re-stamped)

- GEODATA gate support on the QA-clean accepted denominator: positives
  11+4 = **15 ≥ 12**, backgrounds 11+1 = **12 ≥ 12**, regions 5 ≥ 3 —
  R00372-C00139 keeps both-year support via its 2015-MID slot (frac 1.0)
  and 3 × 2020 slots, so the single product failure does not affect
  counts.
- QA batch verdict: **QA_FAIL_SYSTEMATIC_STOP** (unchanged, frozen
  contract) → final readiness verdict
  **NOT_READY_FOR_SPARTINASHIFT_V0_2_PROTOCOL** (frozen QA-verdict
  semantics).

## 5. PAUSED — Owner decision required

Under the current freeze the agent cannot resolve the single QA item.
Owner options (recorded in `V0_2_1_FINAL_READINESS_DECISION.json`):

1. **Accept** `V021_R00372-C00139_L8_2015_E` as a source-quality
   rejection (same phenomenon as the panel's honest rejection
   `V02_R00355-C00151_L8_2015_L`; only the strict all-bands-finite
   precondition differs). Explicit Owner decision → batch becomes
   QA_PASS_WITH_HONEST_SOURCE_REJECTIONS → gate READY.
2. **Commission a protocol revision (v0.2.2)** that explicitly redefines
   the honest-rejection contract or discovery pool for this class — an
   Owner-level protocol change, out of agent scope under the current
   freeze.
