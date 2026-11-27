# BENCHMARK_METRIC_SPEC

Version: v1.0 (2026-11-27). Normative metric definitions for Benchmark V1.
Extends SPEC.md §5 with exact computation rules; the reference
implementation is `src/spartina/evaluation/metrics.py` and the test suite
`engineering/tests/test_metrics_and_bootstrap.py` (tests executed; exit
codes recorded in MASTER_EXECUTION_STATUS.md).

## 1. Definitions

| Metric | Definition | Implementation anchor |
|---|---|---|
| IoU (Spartina) | TP / (TP+FP+FN) on binary Spartina mask | `confusion` + `pixel_rates` |
| F1 (Dice) | 2TP / (2TP+FP+FN) | `pixel_rates` |
| Precision / Recall | TP/(TP+FP), TP/(TP+FN) | `pixel_rates` |
| Boundary F1 | F1 over boundary pixels within tolerance τ ∈ {1,2,4} px reported separately; τ converted to meters at native resolution | `boundary_f1` |
| Patch Precision/Recall | connected-component matching, IoU-of-smaller ≥ 0.5 rule documented | `patch_matching` |
| Small Patch Recall | recall over connected positives ≤ 9 px at native grid (per-track threshold allowed, distribution reported) | `patch_matching` + size filter |
| Absolute/Relative Area Error | per-cell Spartina area (km²) vs label area; relative = abs/label | `area_metrics` |
| Area Bias | signed (pred − label); sign convention: positive = overestimate | `area_metrics` |
| ECE | 15 equal-width bins on predicted probability; |mean(conf) − mean(acc)| weighted per bin | `calibration` |
| Brier | mean squared (prob, outcome) | `calibration` |
| NLL | mean negative log-likelihood of binary outcome | `calibration` |
| Change IoU | gain and loss reported separately on labeled temporal pairs | deferred to cross-year runs |
| Event F1 / recurrence metrics | only with verified treatment/recurrence records; otherwise `BLOCKED: DATA MISSING` | not implemented until data exists |

Threshold selection for binarization happens on validation cells only;
threshold-independent calibration metrics use raw probabilities.

## 2. Aggregation rules (mandatory)

1. Metrics computed **per test cell** first; then pooled summaries.
2. Confidence intervals: nonparametric cluster bootstrap over cells,
   B = 2000, seed 2026, percentile method, 95% level. Cluster = cell
   (never pixel bootstrap — pixel resampling is forbidden as it
   understates spatial autocorrelation).
3. Both per-region and pooled numbers reported; a pooled number without
   per-region and CI is not accepted in any table.
4. Sensor-resolution families never pooled across native resolutions:
   30 m and 10 m results are separate tables.
5. Honest-rejection cells excluded from denominators before any
   aggregation (QA ledger reference recorded per table).

## 3. Fairness rules

- All models: identical manifests, split_id, and label mapping.
- Equal tuning budgets: one shared search space per architecture class;
  same number of configs × seeds {42, 17, 2026}; selection on validation
  only.
- No baseline may be deliberately weakened; failing configs recorded,
  not silently dropped (negative results preserved).
- Non-inferiority margin for unified-vs-specialized comparisons fixed at
  ±2 IoU points, pre-registered before M3 evaluation (HYPOTHESES.md H6).

## 4. Reporting per run

- Per-track table: metric, value, 95% CI, n_cells, n_pixels, QA-ledger ref.
- Reliability diagram per track for probabilistic runs.
- Confusion counts (TP/FP/FN/TN) retained so any metric can be recomputed.
- Failure-case registry entry per run (feeding M-GAP).
