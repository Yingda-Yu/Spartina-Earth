# BENCHMARK_V1_DESIGN — SpartinaShift Benchmark V1

Version: v1.0 design (2026-11-27). Contract supersedes SPEC v0.1 with
per-track operational detail; SPEC.md's mandatory splitting rules and
metric definitions remain binding. **Nothing in this document is a
result.** Execution is gated: Owner approval of v0.2.2 → readiness
decision → split freeze → training authorization.

## 0. Gating (critical readiness dependency)

Phase 2C.2 grid-alignment verification is complete (QA_RADSAT
pixel-perfect, commit fdda75a). Remaining gates before any training:
1. Owner approval of v0.2.2 effectiveness (V022_PROTOCOL_CHECKSUM.json,
   currently PROPOSED_NOT_EFFECTIVE).
2. Independent readiness decision issued on the approved protocol.
3. Split + dataset manifest frozen (split_id + checksums).
4. Training authorization; smoke tests precede formal runs.

## 1. Data basis

- Landed frozen bytes: 722 panel products (8.1 GB) + 35 v0.2.1 repair
  products, all QA-gate-pass, manifest SHA-256 per file.
- Sensor-years: L8 2015/2020, L7 2015/2020, S2 2020/2021, S1 2020/2021
  (53 cells, CNA10K grid).
- Labels: SILVER families (GEODATA 2015/2020; CMSA 2020/2021; CM-SSM) as
  frozen; GOLD = 0; WEAK excluded; management events = 0.
- Honest-rejection semantics: products classified as honest rejections
  (e.g. zero-QA-valid) are excluded from all denominators and never
  counted as observations.

## 2. Spatial unit and splits

- Unit: W10/CNA10K cell (cell-level assignment; all dates of a cell share
  its split). Buffer ≥250 m between split units, verified by
  `src/spartina/evaluation/splits.py` (`assert_spatially_disjoint`,
  `find_cross_split_overlaps`, `check_temporal_grouping`).
- Roles: train / validation / test cells assigned per frozen v0.2
  protocol (Variant 1 vs 2 reserve decision by Owner at freeze time).
- Cross-Region holdouts: fixed province-level region lists frozen before
  development; never used in model selection.
- Details and audit results: SPLIT_DESIGN_AND_LEAKAGE_AUDIT.md.

## 3. Tracks

Per-track definitions, denominators, exclusions, metrics:
BENCHMARK_TRACK_MATRIX.csv (authoritative machine-readable matrix).
Summary:

| Track | Question | Domain shift | Test data | Status |
|---|---|---|---|---|
| ID | ceiling | none | held-out cells, same domain | ready post-freeze |
| Cross-Year | RQ3 | year | CMSA 2020→2021; GEODATA 2015→2020 | ready post-freeze |
| Cross-Region | RQ6 | region | leave-region-out provinces | ready post-freeze |
| Cross-Sensor | RQ1 | sensor | L8↔S2, leave-sensor-out | ready post-freeze |
| Historical-Sensor | RQ1 | generation | modern-trained → L7 (2015) era | ready (L7 products landed); L5 requires Atlas-era export authorization |
| Missing-Modality | RQ2 | modality | controlled S1/S2 dropout 100/66/33% + real missingness masks | ready (S1+S2 co-located 2020/2021) |
| Sparse-Temporal | RQ3 | temporal density | n ∈ {1,2,3,4,6,12} per cell-year | ready post-freeze |
| Management-Shift | RQ4/RQ8 | treatment | pre/post-treatment units vs matched controls | **BLOCKED: 0 treatment records** — track defined, not executed; reported BLOCKED, never scored synthetically |

## 4. Label tier policy per track

- Training labels: SILVER only (frozen families). No WEAK, no GOLD in
  training.
- Test labels: SILVER for v1 conventional ladder; GOLD becomes the
  independent test overlay once Tier ≥1 exists, reported separately and
  never silently mixed with SILVER evaluation (SPEC §9 open question
  resolved as "report separately").
- Label-tier mismatch is a reported stratification, not a silent merge.

## 5. Exclusion policy (denominators)

- Honest rejections (QA-classified) never enter train/val/test
  denominators and are never counted as valid observations.
- Products failing readability/finite checks are excluded by the QA
  ledger, not by result-dependent post filtering.
- Cloud/quality masks are properties of observations and never used to
  move scenes between splits (SPEC §3.6).

## 6. Uncertainty estimation

- Every metric reported with spatial-unit bootstrap 95% CI
  (cluster = cell; B=2000 resamples fixed seed 2026; see
  BENCHMARK_METRIC_SPEC.md and engineering/tests/test_metrics_and_bootstrap.py).
- Per-region and pooled both reported; no pooled-only headline.
- Calibration (ECE/Brier/NLL) required for every probabilistic run;
  reliability diagrams per track.

## 7. Execution order and review gates

Stage A (in-domain + cross-year, conventional ladder) → Owner review →
Stage B (cross-region + Landsat tracks) → Stage C (modality/temporal) →
Stage D (EO foundation models) → Stage E (failure extraction → gap
analysis). Each stage stops for Owner review; negative runs preserved.

## 8. Reporting requirements per run

Full provenance (Git SHA, dataset manifest SHA, split_id, config SHA,
seeds 42/17/2026, checkpoint SHA, environment hash, GPU ids, artifact
paths) enforced by `engineering/run_manifest/generate_run_manifest.py`;
runs missing fields are rejected at submission time.
