# BENCHMARK_NEXT_STAGE_PLAN — SpartinaShift v0.2 → formal benchmark

Plan document (nothing here is a result). Execution is gated: **no model
training until `V02_1_READINESS_REPORT.md` §7 flips to READY on landed,
QA-passed evidence.**

## 1. Preconditions (frozen gates)

1. v0.2.1 gate closure (GEODATA temporal) verified on landed bytes.
2. v0.2 protocol freeze: cell-level train/val/test roles assigned with
   spatially disjoint splits (Variant 1 vs 2 reserve decision made by
   Owner); splits pass `src/spartina/evaluation/splits.py` leakage checks.
3. Data manifest frozen: dataset manifest version, split version, cell
   registry checksum, per-product QA ledger.

## 2. Model ladder (equal budget, equal data, fair tuning)

| Class | Models | Notes |
|---|---|---|
| Classical | RF (pixel-level spectral) | Issue #20 baseline, carried forward |
| CNN | U-Net | |
| Semantic seg | DeepLabV3+ (ResNet-50), SegFormer-B0/B2 | |
| EO foundation | Prithvi-EO-2.0, SatMAE(-++), AnySat (or justified alternative) | adapters validated on landed bytes first; frozen features + fine-tune both reported |

Tuning rules (pre-registered before first run): one shared search space
per architecture class (LR, schedule, augmentation, loss), identical
budget (N configs × seeds {42, 17, 2026}), selection only on validation
cells of training regions; test cells touched once per frozen protocol.
Seeds, configs, Git SHA, checkpoint SHA, environment recorded per run
(`docs/experiments/EXPERIMENT_STANDARD.md`).

## 3. Evaluation tracks

| Track | Design | Requirement source |
|---|---|---|
| In-domain (CMSA 2020) | within-region disjoint cells | RQ1 baseline |
| Cross-year | CMSA 2020→2021; GEODATA 2015→2020 (Landsat) | Issue #20 RQ3 |
| Cross-region | leave-region-out holdouts (6 defensible) | q3 gate |
| Cross-sensor | Landsat-trained vs S2-trained vs unified; leave-sensor-out | RQ1 |
| Optical vs optical+SAR | identical splits, paired | q5 ledger |
| Missing modality | controlled S1/S2 dropout; degradation curves | RQ2 |
| Temporal density | n ∈ {1, 2, 3} obs per cell-year (multi-date view) | q4 anti-confound design |
| Calibration | ECE/Brier/NLL reported for every run | cross-cutting |
| Small-patch recall | per SMALL_FRAGMENTED_PATCH stratum | GOLD plan §2 |
| Area bias | per-cell Spartina area estimate vs label area; |bias| distribution | cross-cutting |

Metrics: Spartina IoU/F1, macro-F1, boundary F1, area bias, ECE, plus
cluster-bootstrap CIs over cells. Non-inferiority margins (2 IoU points)
pre-registered per HYPOTHESES.md before evaluation.

## 4. Provenance requirements (hard)

Every formal result row carries: Git SHA, data manifest SHA, split
version, config path+SHA, seed, checkpoint SHA, software environment
(conda lock / pip freeze hash), GPU ids, artifact paths. Results without
these are not accepted into any table or paper.

## 5. Stage sequence

1. Stage A: in-domain + cross-year on CMSA (S2), conventional ladder.
2. Stage B: cross-region + Landsat tracks (GEODATA temporal) once gate
   closed.
3. Stage C: modality + missing-modality + temporal-density.
4. Stage D: EO foundation models.
5. Stage E: failure-case extraction feeding SpartinaFM gap analysis.

Each stage stops for Owner review before the next, with negative results
preserved.
