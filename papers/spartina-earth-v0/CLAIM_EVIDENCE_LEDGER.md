# Claim–Evidence Ledger — Spartina Earth v0 manuscript

Status vocabulary (Issue #15):

- **VERIFIED_RESULT** — executed and frozen/reconciled in a tracked artifact.
- **VERIFIED_METHOD** — designed, implemented, and tested; not itself an empirical result.
- **PRELIMINARY_RESULT** — executed but explicitly limited in scope/support.
- **PLANNED** — designed/authorized, not executed.
- **UNKNOWN** — relevant quantity not known.
- **BLOCKED** — cannot be obtained without an external dependency/license/decision.

Every evidence path is relative to the repository root. Manifests carry
row-level fingerprints; file-level SHA-256 live in the cited fingerprint
CSVs. Ledger last updated: 2026-10-03.

| ID | Claim (short) | Status | Evidence |
|---|---|---|---|
| C01 | The 2015 national 30 m Spartina raster contains 608,287 positive pixels = 547.4583 km² in its own planar convention (EPSG:32650, int16, nodata 255) | VERIFIED_RESULT | docs/data/CHINA_NATIONAL_ASSET_AUDIT.md §1 (VAT Count independently reproduced) |
| C02 | The 2015 raster is SILVER, not GOLD; producer, class legend, mapping unit, acquisition dates and redistribution license are not documented | VERIFIED_RESULT | docs/audit/DATA_PROVENANCE_AND_LICENSE.md; docs/data/CHINA_NATIONAL_ASSET_AUDIT.md §3 |
| C03 | 2015 raster vs 2020 CM-SSM cannot be interpreted as change (different MMU, method, extent, semantics; +46.25 km² descriptive only) | VERIFIED_RESULT | docs/data/CHINA_NATIONAL_ASSET_AUDIT.md §2 |
| C04 | Pilot-0 labels = SILVER national map + WEAK local mask; no GOLD labels exist in the project (GOLD = 0) | VERIFIED_RESULT | docs/experiments/PILOT0_BASELINE_REPORT.md header; docs/data/SPARTINA_GOLDSET_PROTOCOL.md; Issue #11 comments |
| C05 | Pilot-0 main ladder: RF ~0.69 core IoU; U-Net optical_indices 0.816; DeepLabV3+ optical_indices 0.749; SAI 0.181; SegFormer unstable incl. collapses to IoU 0.000 on seeds | PRELIMINARY_RESULT | docs/experiments/PILOT0_BASELINE_REPORT.md §1, §3; docs/experiments/PILOT0_BASELINE_INTEGRITY_AUDIT.md (49 runs reconciled) |
| C06 | Pilot-0 support is tiny: TEST = 7 windows / 5 SILVER components; no spatial block CI; 3 seeds cover training randomness only | VERIFIED_RESULT | docs/experiments/PILOT0_BASELINE_REPORT.md header, §11 |
| C07 | WEAK-only response is a candidate-response diagnostic, not accuracy/recall (no GOLD) | VERIFIED_METHOD | docs/experiments/PILOT0_BASELINE_REPORT.md §5 |
| C08 | SILVER vs WEAK masks disagree: arbitration Jaccard 0.4929 (P 0.633, R 0.691); on evaluable core pixels after boundary handling Jaccard 0.953 | VERIFIED_RESULT | docs/data/HANGZHOU_2015_LABEL_ARBITRATION.md §E, §Arbitration; artifacts/audit/pilot0/label_arbitration.json |
| C09 | Hangzhou 2015 co-registration: best integer lag (0,0) for every pair (no whole-pixel shift); residual sub-pixel differences remain estimable uncertainty | VERIFIED_RESULT | docs/data/HANGZHOU_2015_COREGISTRATION.md §C–D |
| C10 | GEE catalog + export chain verified end-to-end on one real S2 scene (S2B_MSIL2A_20200905T...T51RUP, 10 m, 4 bands + valid mask, COMPLETED, checksums) | VERIFIED_RESULT | datasets/manifests/gee_real_s2_export_smoke_v1.json |
| C11 | S2 SCL VALID policy is classes 4/5/6 only; snow/ice 11 is invalid (corrected in Issue #6 re-review) | VERIFIED_METHOD | Issue #6 closure comments; configs; s2_scl_qa_v1_1 |
| C12 | Real scientifically eligible Landsat byte/scaling validation has not yet been observed (two predeclared windows had zero eligible L8 scenes) | BLOCKED→PLANNED | docs/data/GEE_REAL_QUERY_SMOKE.md; Issue #13 §Landsat |
| C13 | Real scientifically eligible S1 byte validation has not yet been observed | BLOCKED→PLANNED | docs/data/GEE_REAL_QUERY_SMOKE.md; Issue #13 §Sentinel-1 |
| C14 | Metadata-only Zhejiang census covers 18,435 physical scenes, 1985–2026, six sensors, three bays; L5 2,098 / L7 2,180 / L8 1,511 / L9 546 / S1 2,962 / S2 9,138 | VERIFIED_RESULT | datasets/manifests/zhejiang_eo_scene_census_v0.parquet; docs/data/ZHEJIANG_M21A_ACCEPTANCE_REPORT.md §4.2 |
| C15 | Operational observation spans differ from declared mission spans (S1 first scene 2015-02-09 not 2014; L7 last 2023; …) | VERIFIED_RESULT | ZHEJIANG_M21A_ACCEPTANCE_REPORT.md §4.1 |
| C16 | A bay-wide single-scene coverage ≥0.99 rule is structurally wrong for multi-tile S2 (HZB best single tile 0.909; YQB 0.98994) | VERIFIED_RESULT | ZHEJIANG_M21A_ACCEPTANCE_REPORT.md §4.4 |
| C17 | Fixed grid ZJ_U51_FIXED_V0 (EPSG:32651, UTM-zone-grid origin): 5/10/20 km cells; 10 km gives 114 cells (113 coastal), RECOMMENDED_NOT_FROZEN | VERIFIED_METHOD | docs/data/ZHEJIANG_M21A2_ACCEPTANCE_REPORT_V0.md A |
| C18 | Bay envelopes are Tier-C PROVISIONAL, not authoritative shoreline truth | VERIFIED_METHOD | docs/data/ZHEJIANG_ROI_PROVENANCE_V0.md; M2.1a acceptance |
| C19 | M2.1a SMB label "zero" was a false zero: invalid GeometryCollection + swallowed mask ValueError; polygonal count 46,310 px / 41.6790 km² | VERIFIED_RESULT | docs/data/ZHEJIANG_M21A2_R1_AUDIT.md A; zhejiang_label_cell_overlap_v0_1.csv |
| C20 | Full-square label counting bleeds outside bay envelopes; v0_1 separates full / bay-clip / outside-bay areas | VERIFIED_RESULT | zhejiang_label_cell_overlap_v0_1.csv; R1 audit B |
| C21 | Bay-scoped 10 km SILVER-bearing cell counts: HZB 13 / SMB 17 / YQB 11; clipped sums reconcile to direct envelope intersections (≤0.24%) | VERIFIED_RESULT | zhejiang_label_bay_reconciliation_v0_1.csv (54/54 MATCH) |
| C22 | 2022 autumn S2 three-bay zero-event was a pipeline bug (group-wide cloud max over non-contributing tiles); contributing-scene gate yields 51/150/89 final pairs | VERIFIED_RESULT | zhejiang_s2_2022_funnel_audit_v0.csv; verdict ZERO_WAS_PIPELINE_BUG; spotcheck 9/9 PASS |
| C23 | The cloud-gate bug affected all multi-frame optical groups and years: 31,135 wrongly rejected 10 km pairs; quality pairs 56,096 → 87,231 | VERIFIED_RESULT | datasets/manifests/zhejiang_cell_observation_stats_v0_1.csv |
| C24 | S1 representative frame geometry is not production geometry: 60-IW-scene audit MAE 0.559, P95/max 1.0, 207 false eligible, 474 false rejected | VERIFIED_RESULT | zhejiang_s1_footprint_audit_v0.csv; policy JSON |
| C25 | Actual per-scene GEE geometry is the production eligibility geometry for S1; representative frames are planning prefilter only | VERIFIED_METHOD | zhejiang_s1_footprint_audit_v0.policy.json |
| C26 | Label rights: redistribution and internal-training rights are separate; audited label layers are predominantly rights-UNKNOWN; no label bytes may be assumed redistributable | VERIFIED_METHOD | docs/data/ZHEJIANG_LABEL_RIGHTS_MATRIX_V0.md |
| C27 | Autumn primary window 260–305 is a hypothesis; evidence supports MODIFY to v1 candidate DOY 260–320, per-bay calibration pending (PROPOSED_NOT_FROZEN) | VERIFIED_METHOD | docs/data/ZHEJIANG_PHENOLOGY_AND_SEASON_POLICY_V0.md; M2.1a §5 |
| C28 | Tide: FES2022b SELECTED_NOT_DEPLOYED; observed gauges limited (Kanmen, Lüsi); modeled/observed/proxy terms must never be conflated | VERIFIED_METHOD | docs/data/ZHEJIANG_TIDE_INUNDATION_POLICY_V0.md |
| C29 | Spatial splits must be group-disjoint (coastal segments + projected buffer, same-site cross-date grouping); leakage utility provided | VERIFIED_METHOD | src/spartina/evaluation/splits.py; AGENTS.md §7 |
| C30 | 10 km cell is archive/observation/provenance/split unit; it is not a training chip; future patches carry parent_cell_id | VERIFIED_METHOD | docs/data/ZHEJIANG_OBSERVATION_UNIT_DESIGN_V0.md §9 |
| C31 | A 6–8-cell, 12–30-product, <10 GB real-pixel multimodal HZB pilot is authorized and deterministic | PLANNED | Issue #13; execution this round |
| C32 | National coastal domain independent of Spartina labels; 2015 map used as SILVER stratification only | PLANNED | Issue #14 |
| C33 | National metadata-only EO census via footprint indexing (no per-cell brute force) | PLANNED | Issue #14 §D |
| C34 | National multimodal registry with CORE/OPTIONAL/VALIDATION_ONLY/BLOCKED roles and storage tiers T0–T3 | PLANNED | Issue #14 §E–F |
| C35 | Sensor-agnostic multimodal temporal representation (SpartinaFM) can stably monitor across sensor generations | PLANNED (flagship hypothesis; no results) | docs/models/SPARTINAFM_DESIGN.md; RESEARCH_CONTEXT.md |
| C36 | National Atlas completed / global monitoring / real-time recurrence detection | UNKNOWN (do not claim) | — |
| C37 | Any management-event aligned before/after result for Zhejiang | BLOCKED: 0 verifiable management events with spatial ledgers | ZHEJIANG_M21A_ACCEPTANCE_REPORT.md §7.1 |
| C38 | Observed tide joins for pilot scenes | BLOCKED/NOT_DEPLOYED: no station joins yet | tide policy; Issue #13 §Tide |

## Cross-checks enforced while drafting

1. C05/C06 always appear together: Pilot-0 numbers are never quoted
   without the tiny-support caveat.
2. C19–C24 supersede earlier v0 numbers; v0 artifacts remain on disk
   with SUPERSEDED sidecars and are not silently overwritten.
3. No claim of accuracy on unlabeled pixels (C07).
4. C31–C34 are described as plans until the corresponding issues close;
   their sections use `TODO_EVIDENCE` markers.
5. C35 is framed as future work; the word "foundation model" is not used
   as a contribution claim.
