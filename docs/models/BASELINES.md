# Baselines Plan

Status: **M0 plan.** Baselines are selected to be *strong and fair*, never
deliberately weakened to favor a self-designed model. The scientific
decision rule (§5) is mandatory: if an existing foundation model plus a
simple head already solves the target tracks, the contribution moves to
dataset, benchmark, long-term ecology, or recurrence — not invented
architecture novelty.

Exact version pins, repository URLs, license verification, and citations
are `TODO_VERIFY` / `TODO_CITATION` at adoption time
(see [`../../THIRD_PARTY_LICENSES.md`](../../THIRD_PARTY_LICENSES.md));
nothing is downloaded during M0.

## 1. First tier — classical & standard deep baselines

| Baseline | Why it is required | Fair-tuning notes |
|---|---|---|
| Random Forest / XGBoost on spectral-temporal features | Non-deep, robust, interpretable; sanity floor and feature-attribution (SHAP) reference | Same observation set as deep models; tune on validation units only; report feature importances honestly |
| U-Net | The canonical compact segmentation architecture; also the architecture the legacy code attempted but did not implement correctly | Skip connections verified; same inputs, seed discipline |
| DeepLabV3+ | Strong CNN segmentation baseline with atrous context | Match backbone capacity budget; document pretrained backbone provenance/license |
| SegFormer | Strong lightweight transformer segmentation baseline | Match input resolution/patch strategy; document pretraining dataset |

## 2. Foundation-model baselines

| Baseline | Description (general) | Role |
|---|---|---|
| **SatMAE** | Pretrained satellite/ViT-style encoder using channel identity and temporal position; directly relevant to multi-band time series | Tests whether pretrained EO representations + simple head already transfer to Spartina |
| **Prithvi-EO-2.0** | NASA/IBM EO foundation model family (HLS-oriented in released versions); verify exact model card, inputs, and license before use | Tests a major EO foundation encoder; note sensor/band coverage limits (HLS) honestly — do not force S1 into it |
| **AnySat** | Earth-observation model designed around variable/heterogeneous sensor sets | Closest published analogue to the sensor-agnostic hypothesis; strongest conceptual baseline |

Rule: AnySat-like "any sensor" handling is prior art and must be compared
directly; SpartinaFM claims novelty only in what survives that comparison.

## 3. Mandatory ablations/controls across tiers

- fixed channel indices vs. band identity tokens (tests H2);
- single-date best composite vs. multi-date vs. full irregular series;
- optical-only, SAR-only, fusion (and modality-dropout) conditions;
- same-region vs. disjoint-region vs. leave-region-out;
- per-sensor models vs. one unified model under matched data and tuning
  budget (H6);
- calibration: raw vs. calibrated probabilities.

## 4. Fairness protocol

- Identical label set, split IDs, observation windows, and preprocessing
  across models where input modalities permit; document deviations.
- Hyperparameter search budget matched per family; all selection on
  validation units only.
- ≥3 seeds for stochastic models; report mean, spread, and per-spatial-
  unit CIs.
- Same compute accounting (parameters, training GPU-hours, inference cost).
- Report failures, not only successes (where each baseline collapses is the
  evidence that motivates any new component).
- No peeking at test regions for thresholds or calibration.

## 5. Decision rule

1. If foundation model + simple head is non-inferior on all primary tracks
   (margin defined in `HYPOTHESES.md` H6), **do not build a bespoke
   architecture for the paper**. Pivot/shape contribution as:
   - the SpartinaShift benchmark and its findings,
   - the Spartina Atlas dataset and long-term products,
   - long-term ecological / recurrence results.
2. Build bespoke components only for failure modes that are (a) replicated
   across seeds/regions, (b) attributable to a mechanism (missing modality,
   irregular time, management shift), and (c) not closed by tuning or by an
   existing published method.
3. Every new component enters with an ablation mapping it to one RQ/H.

## 6. Environment discipline (M3+)

- Dedicated `spartina-earth` conda environment (created in M1+), package
  versions locked; no global installs, no sudo; reuse existing
  system-level installs where possible.
- Smoke test on a tiny batch before full runs; check `nvidia-smi` and
  respect [`../system/GPU_POLICY.md`](../system/GPU_POLICY.md).
- All runs logged per
  [`../experiments/EXPERIMENT_STANDARD.md`](../experiments/EXPERIMENT_STANDARD.md).
