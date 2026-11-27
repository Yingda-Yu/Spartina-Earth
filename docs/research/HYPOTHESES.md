# HYPOTHESES.md

Falsifiable hypotheses for Spartina Earth. Every hypothesis states what it
predicts, what evidence is required, the concrete result that would
falsify it, the experiment design, and the metrics. **These are
predictions, not findings.** No result here may be quoted as observed
until the corresponding experiment has actually run (status will be tracked
in `docs/experiments/` once M2/M3 begin).

Notation: a "track" refers to the SpartinaShift tracks in
[`../../benchmarks/spartinashift/SPEC.md`](../../benchmarks/spartinashift/SPEC.md).
All comparisons use spatially disjoint splits, equal data budgets, and
fairly tuned baselines. Statistical statements use confidence intervals
(bootstrap over spatial units); equivalence/non-inferiority margins are
fixed **before** seeing test results.

---

## H1 — Cross-era representation stability (→ RQ1)

**Hypothesis.** A model given explicit band-wavelength/sensor/date
identity and trained across multiple Landsat generations will show a
smaller held-out-era Spartina IoU degradation than separate per-sensor
models evaluated on an era they were not trained on.

**Evidence needed.**
- Same labeled coastal units observable from at least two Landsat
  generations (overlap years of Landsat 7/8; cross-era via Landsat 5-era
  labels).
- Per-sensor and unified models trained under equal budget.
- Radiance/reflectance harmonization documented at the input level.

**Falsification criterion.** On the `Historical-Sensor` track, the unified
model's mean held-out-era IoU is not higher (95% CI overlaps, or difference
within a pre-registered non-inferiority margin of ±2 IoU points) than the
best sensor-specific baseline, and representation-similarity metrics
(CKA/linear-probe stability across eras) show no stability advantage.

**Experiment.** Train: single multi-sensor model vs. one model per sensor.
Test: leave-one-era-out + leave-one-sensor-out; include a "naïve channel
order" ablation (bands presented as fixed channel indices) to isolate the
value of wavelength/sensor identity.

**Metrics.** Spartina IoU/F1, macro-F1, held-out-minus-in-domain ΔIoU,
ECE, linear-probe CKA across eras, area bias.

## H2 — Identity-aware inputs beat fixed channel order (→ RQ1, RQ5)

**Hypothesis.** Feeding band identity (name, wavelength, sensor,
resolution) instead of fixed "channel N" positions reduces cross-sensor
degradation and allows graceful handling of absent bands.

**Falsification criterion.** Removing identity embeddings changes
cross-sensor ΔIoU by less than 1 point (CI includes 0) on `Cross-Sensor`.

**Experiment.** Ablation within one architecture: fixed channels vs.
identity-aware band tokens, everything else identical.

**Metrics.** Cross-sensor ΔIoU, Missing-Modality degradation, calibration.

## H3 — Modality-dropout training enables missing-modality inference (→ RQ2)

**Hypothesis.** Training with randomized modality dropout (optical, SAR,
context) yields a fusion model whose test-time missing-modality
degradation is smaller than (a) late-fusion/averaging ensembles and
(b) the same model trained with all modalities always present.

**Evidence needed.** Co-located Sentinel-1/Sentinel-2 observations over
labeled units; DEM/inundation layers; realistic missingness masks derived
from actual cloud/acquisition statistics.

**Falsification criterion.** Under each single-modality-removed condition,
the dropout-trained model fails to beat the naïve-all-modality model by a
pre-registered margin (≥2 IoU points) on `Missing-Modality`, or beats the
strong ensemble baseline on no condition.

**Experiment.** Factorized fusion comparison (early/gated vs. late) ×
{always-all-modality, modality-dropout}; evaluate at 100%/66%/33% modality
availability and under real cloud masks.

**Metrics.** IoU/F1 per missingness condition, degradation slope vs.
availability, ECE, compute per inference.

## H4 — Irregular-time temporal representations (→ RQ3)

**Hypothesis.** An observation-time-aware temporal model (explicit
timestamps/DOY and arbitrary observation count) is more robust to temporal
sparsity shifts than a fixed-cadence stack model.

**Falsification criterion.** On `Sparse-Temporal`, when observations are
subsampled to match the sparsest realistic year, the time-aware model's
ΔIoU relative to dense conditions is not smaller than the fixed-cadence
model's (CI includes zero or favors the baseline).

**Experiment.** Same backbone; variable-observation encoder vs. fixed
monthly composite input; controlled subsampling (n = 2, 4, 6, 12
observations) and cadence permutation.

**Metrics.** IoU/F1 vs. observation count, temporal consistency of maps,
ECE, sensitivity to DOY permutation.

## H5 — Management is a distinct domain shift (→ RQ4)

**Hypothesis.** Models trained only on intact/invasion-era data degrade
systematically on mapped treatment units after eradication (confusing bare
mudflat/regrowth with Spartina), and this degradation is larger than
ordinary cross-year variation; adding treatment metadata or post-treatment
labels partially closes the gap.

**Evidence needed.** Treatment-unit boundaries + treatment dates
(government/management records; provenance audited); repeated observations
pre/post treatment; untreated controls matched by habitat.

**Falsification criterion.** Post-treatment performance loss on treated
units is statistically indistinguishable from cross-year loss on untreated
control units (CI overlaps zero for the difference-in-differences).

**Experiment.** Difference-in-differences evaluation: treated vs. matched
controls, pre vs. post, naïve model vs. management-aware adaptation.

**Metrics.** IoU/F1, commission error on treated non-Spartina surfaces,
change IoU, event F1, ECE.

## H6 — Unified model non-inferiority (→ RQ5)

**Hypothesis.** One unified multimodal temporal model is non-inferior to
the best sensor-specific model per track (pre-registered margin: 2 IoU
points), while providing operational advantages (single weights,
missing-modality robustness, era-spanning outputs).

**Falsification criterion.** On any primary track, unified-model IoU is
more than 2 points below the best fair baseline with CI excluding the
margin, and the deficit cannot be removed with matched tuning budget.

**Experiment.** Paired runs, identical label budgets, hyperparameter
budget matched; report per track plus average/rank. Pre-register the
margin before M3 evaluation.

**Metrics.** All primary pixel/boundary/area/calibration metrics;
parameter count and training/inference cost as secondary.

**Decision rule.** If strong foundation models + simple heads already
match this performance, contribution shifts to dataset, benchmark,
ecology, or recurrence — no architecture novelty is forced.

## H7 — Few-shot regional transfer (→ RQ6)

**Hypothesis.** A pretrained representation fine-tuned with ≤10 labeled
patches in an unseen China coastal region reaches within 5 IoU points of a
fully supervised model trained on that region's full labels.

**Evidence needed.** ≥3 disjoint coastal regions with independent labels;
strict leave-region-out; labeled-patch budgets logged.

**Falsification criterion.** Few-shot gap exceeds 5 IoU points with CI
excluding −5 at every budget ≤10 patches, or zero-shot performance is
below the spectral RF/XGBoost baseline.

**Experiment.** Leave-one-region-out; fine-tune at 0/1/5/10/50 patches;
compare against from-scratch and foundation-model baselines.

**Metrics.** IoU/F1 vs. label budget, small-patch recall, area bias,
calibration.

## H8 — Recurrence early warning (→ RQ8)

**Hypothesis.** Trajectory-derived features (pre-treatment spectral/SAR
history + first k months post-treatment) predict recurrence within a fixed
horizon (e.g., 12/24 months; exact horizon to be pre-registered with
managers) better than persistence and static habitat-suitability
baselines, at operationally acceptable false-alert rates.

**Evidence needed.** Confirmed treatment units with dates; recurrence
labels over multiple post-treatment years; manager-confirmed horizon and
alert thresholds. Absent such records, H8 stays untestable and is marked
`BLOCKED: DATA MISSING` rather than approximated.

**Falsification criterion.** Trajectory model does not exceed the best
static/persistence baseline on recurrence recall at a fixed false-alert
budget (CI overlaps), or shows no positive lead time advantage.

**Experiment.** Survival/event framing with train/test regions disjoint;
evaluate at fixed horizons; ablate trajectory vs. static-only inputs.

**Metrics.** recurrence recall, false alerts/km², lead time, high-risk
patch capture rate, time-dependent AUROC/AUPRC, calibration of risk.

---

## Hypothesis status ledger (updated when experiments run)

| ID | State now | Blocking requirement |
|---|---|---|
| H1 | not tested | harmonized multi-era data + labels (M1/M2) |
| H2 | not tested | multi-sensor co-located dataset |
| H3 | not tested | co-located S1/S2 + context + realistic cloud masks |
| H4 | not tested | multi-date time series per unit |
| H5 | not tested | treatment-unit records with dates (provenance audit) |
| H6 | not tested | completed benchmark tracks + fair baselines (M2/M3) |
| H7 | not tested | ≥3 independent labeled regions |
| H8 | **BLOCKED: DATA MISSING** | confirmed treatment dates + multi-year recurrence labels |
