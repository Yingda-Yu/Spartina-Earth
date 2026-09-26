# SpartinaShift Benchmark — Specification (Contract)

Status: **SPEC v0.1, M0.** This document defines the benchmark *contract*
only. No results exist; no fake leaderboard will be generated. Data
construction begins in M2 after the M1 data engine.

Maintainers: Spartina Earth (Spartina Technology).

## 1. Purpose

Measure whether *S. alterniflora* predictions generalize across the axes
that matter for long-term coastal monitoring: region, year, sensor, sensor
generation, management intervention, modality availability, and temporal
density.

## 2. Tracks

| Track | Train domain | Test domain | Question |
|---|---|---|---|
| `ID` | standard disjoint units within region/year set | held-out spatial units, same domain | sanity baseline; ceiling reference |
| `Cross-Region` | selected coastal regions/segments | fully held-out regions (province/segment level) | RQ6 |
| `Cross-Year` | years T₁…Tₖ | unseen year(s) | inter-annual/phenology stability, RQ3 |
| `Cross-Sensor` | one sensor family (e.g. Landsat 8) | another (Sentinel-2), resampling documented, no fake-resolution claims | RQ1 |
| `Historical-Sensor` | modern sensors | Landsat 5/7-era observations | generation transfer, RQ1 |
| `Management-Shift` | intact / non-treated units | mapped post-treatment units (and vice versa) | RQ4 / RQ8 |
| `Missing-Modality` | full modality set | controlled modality dropout at test | RQ2 |
| `Sparse-Temporal` | dense observation schedule | sparse/irregular observations | RQ3 |

Each track version gets a `split_id` (region lists, year lists, random
seeds, geometry hashes) frozen and versioned in
`datasets/manifests/`-style split manifests. Test geometry is never edited
after freeze; errata require a new `split_id`.

## 3. Splitting rules (mandatory)

1. **No random neighboring-patch splits.** Assigning random image patches
   to train/test is forbidden and is rejected by the leakage checker
   (`src/spartina/evaluation/splits.py`).
2. Splits are **spatially disjoint at a defined geographic unit** (coastal
   segment or fixed grid cell) with an explicit **buffer** (default
   ≥250 m; exact buffer justified per track) so neighboring pixels and
   overlapping sensor footprints cannot cross splits.
3. All dates of the same spatial unit are grouped into the same split.
4. Test units never appear in training, validation, hyperparameter search,
   early stopping, or threshold/calibration fitting. Validation units are
   disjoint from both.
5. For `Cross-Region`, the held-out regions are fixed before model
   development and hidden from model selection.
6. Cloud/quality masks are properties of observations, never of labels, and
   never used as a proxy to move scenes between splits.
7. Label leakage audits: no GOLD/SILVER label polygon may intersect test
   geometry on the train side (computed in CRS-appropriate coordinates).
8. Resolution honesty: 30 m data evaluated at its native grid; comparisons
   with 10 m predictions are reported separately at each sensor's native
   resolution with the aggregation documented. **Never present upsampled
   30 m output as native 10 m results.**

## 4. Task definition

Primary task: per-pixel binary classification {Spartina, not-Spartina} for
each product timestep. Change/event and recurrence tasks are secondary and
defined on labeled temporal pairs/intervals.

The positive class is *S. alterniflora* as defined by the label tier's
mapping table (per-manifest `label_type` + `label_mapping`); mixed pixels
are handled per a documented rule (uncertain mask, not silent relabeling).

## 5. Metrics

All metrics are computed per test unit and summarized with spatial-unit
bootstrap confidence intervals; per-region and pooled numbers are both
reported (no single pooled number only).

### 5.1 Pixel

- IoU (Spartina)
- F1 (Dice)
- Precision
- Recall

Confidence thresholds for "Spartina" are chosen on validation units only;
calibrated threshold analysis is separate.

### 5.2 Boundary

- Boundary F1 (tolerance τ, with τ reported in meters at native resolution;
  default τ ∈ {1, 2, 4} pixels reported separately).

### 5.3 Patch / object

- Patch Precision
- Patch Recall
- Small Patch Recall (small-patch area threshold defined per track,
  default ≤ 9 connected positive pixels at native grid; distribution
  reported)
- connected-component matching rule: intersection-over-area-of-smaller
  ≥0.5, documented.

### 5.4 Area

- Absolute Area Error (km²)
- Relative Area Error (%)
- Area Bias (signed; sign convention documented)

### 5.5 Calibration

- Expected Calibration Error (ECE, binning scheme reported)
- Brier Score
- Negative Log-Likelihood
- reliability diagrams per track in reports.

### 5.6 Change / temporal

- Change IoU (gain / loss reported separately)
- Event F1
- Temporal Consistency (frame-to-frame disagreement corrected for true
  changes; definition documented with reference).

### 5.7 Management / recurrence (track `Management-Shift`)

- Recurrence Recall
- False Alerts per km²
- Lead Time (months)
- High-risk Patch Capture Rate

Only computed when verified treatment dates and recurrence labels exist;
otherwise the subtask is reported `BLOCKED: DATA MISSING`, never scored
with synthetic labels.

## 6. Required baselines

At minimum (see [`../../docs/models/BASELINES.md`](../../docs/models/BASELINES.md)):
spectral RF/XGBoost, U-Net, DeepLabV3+, SegFormer, and foundation baselines
(SatMAE, Prithvi-EO-2.0, AnySat) with identical data budgets and documented
tuning. Baselines must not be deliberately weakened.

## 7. Reporting

Each submission to the benchmark (a row in future leaderboard tables)
requires:

- model name/version and code commit;
- per-track metrics with CIs;
- training/validation/test `split_id`s and data manifest versions;
- seed set (≥3 seeds for stochastic models) and variance;
- compute used; modalities used; inference-time missingness handling;
- failure cases and known limitations.

## 8. What is explicitly out of scope at M0

- Any leaderboard numbers (none exist).
- Synthetic/simulated recurrence labels.
- Random patch splits even as a "quick test".
- Cross-resolution claims without native-grid evaluation.

## 9. Open questions for M1/M2

- Coastal-segment definition and buffer widths (sensitivity analysis).
- Minimum per-region label density for a region to qualify.
- Exact small-patch thresholds and boundary tolerances at 10 m vs. 30 m.
- Handling of label-tier mismatch between SILVER train labels and GOLD
  test labels (report separately; never silently mix).
