# SPARTINA EARTH MASTER RESEARCH PROGRAM

Version: v1.0 (2026-11-27). This is the central document for the complete
Spartina Earth research program. It reconciles every governing document
into one authoritative reference and maps the full execution state —
completed, in progress, and gated.

Status semantics: statuses describe **verified state of evidence**, never
intent. `COMPLETED` requires an artifact + evidence (commit, exit code,
or data bytes). Nothing in this document is a scientific result until the
corresponding experiment has run and been accepted by an Owner review.

Governing inputs reconciled here: AGENTS.md, RESEARCH_CONTEXT.md, README.md,
docs/research/SCIENTIFIC_QUESTIONS.md, docs/research/HYPOTHESES.md,
docs/roadmap/UPDATED_RESEARCH_ROADMAP.md,
docs/roadmap/BENCHMARK_NEXT_STAGE_PLAN.md, docs/models/SPARTINAFM_DESIGN.md,
docs/models/BASELINES.md, docs/data/SPARTINA_GOLDSET_PROTOCOL.md,
docs/roadmap/GOLDSET_ACQUISITION_PLAN.md,
benchmarks/spartinashift/SPEC.md, docs/experiments/EXPERIMENT_STANDARD.md,
docs/architecture/EO_DATA_ENGINE.md, Issues #19/#20/#21/#22, and all
v0.2 / v0.2.1 / proposed-v0.2.2 QA artifacts.

---

## 1. Overall scientific mission

Build a reproducible, uncertainty-honest Earth-observation system for
monitoring invasive *Spartina alterniflora* across China's coast and,
ultimately, global native/invaded ranges — spanning satellite generations,
irregular acquisition, missing modalities, and management interventions —
so that invasion, eradication and recurrence can be quantified with
defensible error bounds.

Umbrella question (SCIENTIFIC_QUESTIONS.md): can a sensor-agnostic
multimodal temporal EO model learn a stable representation of *S.
alterniflora* across changing satellite generations, regions, phenological
stages and management interventions, enabling consistent long-term
monitoring and early detection of post-eradication recurrence?

## 2. Eight research questions and hypotheses

| RQ | Question | Hypotheses | Primary track | Status |
|---|---|---|---|---|
| RQ1 | Cross-generation representation stability (L5/7/8/9, S1/S2) | H1, H2 | Historical-Sensor, Cross-Sensor | NOT_STARTED (data ready) |
| RQ2 | Optical/SAR fusion under modality dropout | H3 | Missing-Modality | NOT_STARTED (S1+S2 landed for 2020/2021) |
| RQ3 | Irregular temporal observation | H4 | Sparse-Temporal, Cross-Year | NOT_STARTED |
| RQ4 | Management-induced domain shift | H5 | Management-Shift | **BLOCKED: 0 treatment records** |
| RQ5 | Unified vs specialized models | H6 | all tracks (paired) | NOT_STARTED |
| RQ6 | Zero-/few-shot regional transfer | H7 | Cross-Region | NOT_STARTED |
| RQ7 | International transfer | (RQ7, no H id) | Cross-Region (international) | **BLOCKED: license/label availability UNKNOWN** |
| RQ8 | Post-eradication recurrence prediction | H8 | Management-Shift (recurrence) | **BLOCKED: DATA MISSING (H8 ledger)** |

Hypothesis ledger state (HYPOTHESES.md, unchanged): H1–H7 not tested;
H8 BLOCKED: DATA MISSING.

## 3. Research architecture

Four layers, each with hard gates:

1. **Data layer** — EO Data Engine (catalog → QA → export → COG →
   manifest/SHA-256), label governance (GOLD/SILVER/WEAK/UNLABELED tiers,
   no auto-promotion), dataset versioning.
2. **Benchmark layer** — SpartinaShift: 8 independent tracks, spatially
   disjoint splits, leakage-checked, resolution-honest, frozen split
   manifests.
3. **Experiment layer** — conventional ladder → EO foundation models →
   failure analysis; every run provenance-tagged (Git SHA, manifest SHA,
   split_id, seed, checkpoint SHA, env).
4. **Product layer** — China Coastal Atlas (1985–2025), management &
   recurrence research, international transfer.

## 4. Dataset inventory and provenance (current landed state)

Detailed machine-readable inventory: docs/data/MASTER_DATA_INVENTORY.csv.

- **Panel export (v0.2, frozen)**: 722 products / 53 cells, 8,135,988,437
  bytes landed, QA gate pass 722/722. Sensor-year mix: L8 2015 (86),
  L8 2020 (49), L7 2015 (11), L7 2020 (17), S1 2020 (144), S1 2021 (135),
  S2 2020 (144), S2 2021 (136). Manifests with per-file SHA-256: 722
  (work/issue21/export/manifests/). Roles per product: sr, valid, qapixel
  (Landsat/S2) or vvvh + dualpol_valid (S1).
- **Repair export (v0.2.1)**: 35 Landsat-8 2015 products re-exported
  (105 files), QA-passed; target of the v0.2.1 temporal repair.
- **QA evidence**: QA_RADSAT verified pixel-perfect on the frozen grid for
  V021_R00372-C00139_L8_2015_E (151,285/151,285 px, all 8 bits zero;
  QA_RADSAT_GRID_ALIGNMENT_REPORT.md, commit fdda75a). For all other
  historical products QA_RADSAT is documented as **proxy** only (never
  claimed as direct per-product verification).
- **Labels**: SILVER = GEODATA/CMSA/CM-SSM (audited products); GOLD = 0
  (30 candidates, CANDIDATE_ONLY, permissions UNVERIFIED_PENDING_OWNER);
  WEAK = legacy; management events = 0.
- **Not landed / not authorized**: nationwide bulk exports (requires
  separate Owner authorization); international EO/labels (UNKNOWN
  licensing).

## 5. Model development roadmap

Staged, each stage Owner-gated (BENCHMARK_NEXT_STAGE_PLAN §5):

1. Stage A: in-domain + cross-year (CMSA/S2) — conventional ladder
   (RF/XGBoost, U-Net, DeepLabV3+, SegFormer-B0/B2).
2. Stage B: cross-region + Landsat tracks (GEODATA temporal) after gate
   closure.
3. Stage C: modality/missing-modality/temporal-density tracks.
4. Stage D: EO foundation models (Prithvi-EO-2.0, SatMAE(++), AnySat) —
   adapters validated on landed bytes first; compatibility matrix
   (docs/models/FOUNDATION_MODEL_COMPARISON.md) before large runs.
5. Stage E: failure extraction → SpartinaFM gap analysis
   (docs/research/SPARTINAFM_RESEARCH_GAP_ANALYSIS_PLAN.md).
6. SpartinaFM architecture decision only after gap analysis is
   Owner-accepted (docs/models/SPARTINAFM_ARCHITECTURE_DECISION.md).

No training until: (1) Owner approves v0.2.2 effectiveness, (2) independent
readiness decision issued, (3) split + manifest frozen. Smoke tests then
precede formal runs (seeds 42/17/2026).

## 6. Benchmark tracks and experimental designs

Eight tracks (SPEC.md): ID, Cross-Year, Cross-Region, Cross-Sensor,
Historical-Sensor, Missing-Modality, Sparse-Temporal, Management-Shift.
Full per-track design, denominators, label tiers, exclusions and metrics:
docs/benchmark/BENCHMARK_V1_DESIGN.md + BENCHMARK_TRACK_MATRIX.csv.
Metrics spec incl. spatial-unit bootstrap CIs:
docs/benchmark/BENCHMARK_METRIC_SPEC.md. Split/leakage rules and audit:
docs/benchmark/SPLIT_DESIGN_AND_LEAKAGE_AUDIT.md.

Non-negotiables: no random neighboring-patch splits; all dates of one
spatial unit share a split; test units touched once; 30 m never presented
as 10 m; Management-Shift/recurrence metrics scored only with real
treatment/recurrence records (currently none → reported BLOCKED).

## 7. Independent validation strategy

- **GOLD system** (0 today): 30-candidate registry → Tier-1 pilot of 4
  sites (2 source-disagreement, 1 boundary, 1 small-patch; ZJ/FJ/SD/JS) →
  double annotation + adjudication → GOLD consideration. Permission gate
  blocks all collection until written per-site permission exists.
- **Calibration**: ECE/Brier/NLL required on every run; reliability
  diagrams per track.
- **Uncertainty**: spatial-unit bootstrap CIs; per-region and pooled both
  reported; no single pooled headline number.
- **Isolation**: GOLD sites inherit cell-level split isolation; reserve
  (24 sealed cells) untouched until v0.2 roles freeze; test regions
  excluded from all model selection.

## 8. China Coastal Atlas

Plan: docs/atlas/CHINA_COASTAL_ATLAS_SPEC.md,
docs/atlas/HISTORICAL_RECONSTRUCTION_PLAN.md,
docs/atlas/CARTOGRAPHIC_DESIGN_STANDARD.md.

Products A–G (distribution, expansion, disappearance, residual, recurrence
candidates, uncertainty, management response). Landsat 5/7/8/9 30 m
historical backbone + Sentinel-1/2 10 m modern layer, **separate
resolution families**. A year without valid observations is
NO_VALID_OBSERVATION, never disappearance. Product G (management response)
BLOCKED until real treatment records exist. Status: NOT_STARTED (data
production plan only; nationwide export requires separate Owner
authorization).

## 9. Management and recurrence research

Depends on verified treatment boundaries + dates + intervention types,
and multi-year recurrence labels. Both = 0 today. H5/H8 remain
untestable (BLOCKED: DATA MISSING); RQ4/RQ8 planning-only. No synthetic
events. Data acquisition actions are tracked in
docs/data/CHINA_EXTERNAL_LABEL_ACCESS_ACTIONS.md.

## 10. International transfer

Global inventory: docs/atlas/GLOBAL_TRANSFER_DATA_INVENTORY.csv.
Feasibility UNKNOWN until per-region licensing, label availability,
species definitions and acquisition dates are established. China results
are never narrated as global generalization (RQ7 gate; RESEARCH_CONTEXT.md
publication policy).

## 11. Expected scientific contributions

1. SpartinaShift benchmark: first spatially-isolated, multi-track,
   resolution-honest benchmark for invasive-marsh mapping under real
   observation conditions.
2. Quantified cross-generation sensor stability for coastal wetland
   mapping (incl. Landsat 5→9 era transfer).
3. Evidence-based answer whether optical+SAR fusion and temporal-aware
   models materially help invasive-marsh monitoring — negative results
   acceptable and publishable as evidence.
4. GOLD-validated accuracy bounds replacing SILVER-agreement claims.
5. China Coastal Atlas: 40-year distribution/expansion/disappearance
   product with NO_VALID_OBSERVATION honesty.
6. SpartinaFM **only if** the measured gap analysis justifies it
   (pre-declared pivot to data/benchmark/ecology contributions otherwise,
   HYPOTHESES.md H6 decision rule).

## 12. Technical dependencies

See SPARTINA_EARTH_DEPENDENCY_GRAPH.md. Hard chain: QA v0.2.2 approval →
readiness decision → split freeze → smoke tests → baselines → FM
comparisons → failure analysis → (conditional) SpartinaFM; GOLD Tier-1 is
parallel and gates only independent-accuracy claims; Atlas production
gates on separate export authorization.

## 13. Milestone acceptance criteria

Machine-readable: docs/roadmap/SPARTINA_EARTH_MILESTONE_REGISTRY.csv.
Summary of gates:

| Milestone | Acceptance criterion | Status |
|---|---|---|
| M-QA-v022 | Owner approval recorded; protocol checksum updated | OWNER_REVIEW |
| M-READY | Independent readiness decision issued on approved protocol | NOT_STARTED |
| M-SPLIT | split_id frozen, leakage checker exit 0, manifest checksummed | NOT_STARTED |
| M-SMOKE | smoke runs exit 0 on landed bytes, ≤3 GPUs, budget recorded | NOT_STARTED |
| M-BASE | Stage A formal runs, 3 seeds, full provenance, negative runs kept | NOT_STARTED |
| M-FM | adapter compatibility matrix validated on landed bytes first | NOT_STARTED |
| M-GAP | failure taxonomy quantified on ≥2 tracks; Owner-accepted | NOT_STARTED |
| M-GOLD-T1 | 4 sites double-reviewed with permission refs; GOLD count still honest | BLOCKED (permissions) |
| M-ATLAS | Atlas products with full cartographic standard; separate export auth | NOT_STARTED |
| M-MGMT | ≥1 verified treatment record with provenance | BLOCKED (data missing) |
| M-INTL | ≥1 non-China region with license + labels verified | BLOCKED (UNKNOWN) |

## 14. Risks and blocked dependencies

| Risk | Impact | Mitigation |
|---|---|---|
| v0.2.2 not approved | blocks entire benchmark chain | Owner decision queued; nothing bypassed |
| GOLD permissions unverified (30/30) | all accuracy claims stay "agreement, not accuracy" | Tier-1 permission drive; fallback: benchmark remains SILVER-evaluation-only |
| Treatment records = 0 | RQ4/RQ8 blocked indefinitely | keep BLOCKED honestly; pursue ledgers; no synthetic data |
| International licensing UNKNOWN | RQ7 blocked | inventory-first; no acquisition before license review |
| Disk 91% used (/data, 686 GB free) | large FM weights + Atlas exports risk filling disk | audit before each download; keep raw/checkpoints outside Git; prune intermediates |
| GPU contention (10×3090 shared) | training interruptions | never GPU 0; ≤3 GPUs; smoke-first; resumable checkpoints |
| Single-product QA history | historical claims overreach | per-product proxy labeling retained in all reports |

## 15. Actual versus planned completion status

- COMPLETED: Phase 1/1.1 audits; Phase 2A (35/35 repair export landed, QA);
  2A.1 manifest provenance; 2B QA semantics + v0.2.2 proposal; 2C bit-level
  audit + VALID cross-validation + v0.2.2 final contract + regression
  tests; 2C.1 independent acceptance (QA_RADSAT direct read, clean-worktree
  rerun exit 0, raster regression 478); 2C.2 grid alignment
  (pixel-perfect, commit fdda75a); master program infrastructure (this
  document set + engineering scripts, this commit).
- OWNER_REVIEW: v0.2.2 protocol effectiveness.
- BLOCKED: M-GOLD-T1 (permissions), M-MGMT (0 records), M-INTL (UNKNOWN).
- NOT_STARTED: everything downstream of the Owner gates (training, FM,
  Atlas production, international transfer).

Execution status ledger with per-item evidence:
docs/roadmap/MASTER_EXECUTION_STATUS.md.
