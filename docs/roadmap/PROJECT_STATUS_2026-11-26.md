# PROJECT_STATUS — 2026-11-26

Research reboot status. Paper 1 independent submission is **paused**; all
Paper 1 code, figures, data audits and results are retained on
`feat/paper1-map-reliability` (nothing deleted). Work continues on branch
`reboot/spartina-earth-m2-7-repair` (based on Paper 1 branch tip `07dfff2`,
which contains the full reboot lineage — see `GIT_BRANCH_AUDIT.md`).

Statuses are strict: **DONE** = executed with tracked evidence;
**PARTIAL** = some executed evidence exists, stated scope not met;
**BLOCKED** = cannot proceed without an external dependency;
**NOT STARTED**. Nothing below is inflated.

## Milestone ledger

| Milestone | Status | Evidence / blocker |
|---|---|---|
| M0 repository reboot, governance, legacy audit | DONE | `AGENTS.md`, `docs/audit/*`, `legacy/` preserved |
| National EO metadata census (Issue #16) | DONE | `work/national/census_r1/`, 10.9 M cell-event rows, EO_CENSUS_RUN_MANIFEST |
| W10 domain v1.1 core frozen (Issue #17) | DONE | `datasets/manifests/china_coastal_cells_v1_1_core_frozen.csv` (3,016 KEEP) |
| 2020 three-product disagreement audit (Issue #18) | DONE | Dice 0.52–0.71 cluster-bootstrap; H2 NOT_SUPPORTED recorded honestly |
| M2.4 national label-family intake (10 products, byte-audited) | DONE | `china_spartina_label_products_v0.csv`; GOLD = 0 (honest) |
| M2.5 20-cell real-pixel pilot (Issue #19) | DONE | landed products + QA manifests under `work/national/pilot19/` |
| M2.6 Silver v0.1 benchmark, Stage 1 (Issue #20) | DONE (as scoped) | RF/U-Net/DeepLabV3+/SegFormer executed for C2/C4/C5; C1/C3 honestly INSUFFICIENT_SUPPORT |
| M2.7 v0.2 support expansion (Issue #21) Phases A–L | DONE (executed) | 53-cell panel exported (722 products, 8.14 GB), readiness verdict **NOT_READY** (GEODATA temporal 11/12 positives, 11/12 background) |
| M2.7 v0.2 **gate closure** (GEODATA temporal) | **PARTIAL → repair planned this round** | metadata planner done (`v0_2_1_repair/`); export NOT executed (owner gate) |
| GOLD reference labels (Issue #11) | PARTIAL | 30 candidate sites registered, CANDIDATE_ONLY; field/UAV acquisition NOT STARTED; permissions UNVERIFIED_PENDING_OWNER |
| M2.6 Stage 2 (full v0.2 benchmark incl. cross-year/cross-region on new panel) | NOT STARTED | blocked on v0.2.1 readiness |
| M3 EO foundation-model baselines (SatMAE/Prithvi/AnySat) | NOT STARTED | gated behind conventional baselines on defensible support |
| SpartinaFM design/architecture | NOT STARTED (by design) | failure-case analysis must precede architecture work |
| Spartina Atlas data products | NOT STARTED | requires verified long-term label/observation backbone |
| Global transfer (M7) | NOT STARTED | gated on China-coast validation maturity |
| Paper 1 submission / EarthArXiv | PAUSED (owner decision) | branch frozen; no submission executed |

## Current P0 path (this round)

1. GEODATA temporal gate repair — metadata planner + cost estimate DONE;
   14 ranked candidates (8 positive + 6 background) with census-verified
   Landsat 7/8 autumn events in both 2015 and 2020. Export awaits owner
   approval (`V0_2_1_REPAIR_SCOPE_ESTIMATE.json`: ≤0.36 GiB Option A,
   ≤2.25 GiB Option B — far inside caps).
2. Reserve isolation wording normalized (sealed-after-export, see
   `V02_1_READINESS_REPORT.md` §5).
3. GOLD acquisition plan produced (`GOLDSET_ACQUISITION_PLAN.md`) — plan
   only; no reference data collected, no promotion executed.
4. Benchmark next-stage plan + research roadmap updated (plan documents).

## What this round did NOT do (per execution discipline)

- No Paper 1 submission or packaging for submission.
- No GEE pixel export of any kind (planner is metadata-only).
- No model training or benchmark run on non-gate-passing data.
- No threshold relaxation, no label redesign, no test-set re-picking.
