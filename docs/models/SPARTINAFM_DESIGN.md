# SpartinaFM — Architecture Design (Research Hypotheses, Not a Built Model)

Status: **M0 design document.** Nothing here is implemented or validated.
These are research hypotheses about an architecture, expressed clearly
enough to critique and test. Final architecture decisions wait until
strong foundation-model baselines
([`BASELINES.md`](BASELINES.md)) have established the real failure modes
on SpartinaShift (M3). Per project rules, we do not manufacture
architecture novelty if an existing foundation model plus a simple head
already solves the task.

## 1. Design objective

A model that ingests heterogeneous observations — different sensors,
bands, resolutions, modalities, times — as an *unordered/irregular set of
identity-tagged tokens* rather than a fixed channel stack, and produces a
shared spatiotemporal representation of Spartina cover and dynamics.

## 2. Logical data path

```
sensor-specific adapters (per modality/sensor family)
        │  raster/patch tokens at the observation's native grid
        ▼
band / wavelength embeddings      "this token is ~650 nm / B4 / VV ..."
        ▼
resolution embeddings             native GSD identity
        ▼
sensor embeddings                 L5/L7/L8/L9/S1/S2
        ▼
date / DOY / year embeddings      acquisition time identity, irregular
        ▼
geo embeddings                    location identity (coastal-grid tile)
        ▼
shared spatial representation     per-observation spatial tokens
        ▼
irregular temporal transformer    variable-length observation sequences
        ▼
gated multimodal fusion           modality availability-aware combination
        ▼
shared representation
   ├── semantic segmentation head          (Spartina / not)
   ├── change / event head                 (gain, loss, treatment state)
   ├── uncertainty head                    (calibrated probabilities / intervals)
   ├── patch-trajectory head               (per-patch temporal state path)
   └── recurrence head (M6, conditional)   (risk over horizon; needs labels)
```

## 3. Component rationale (each must map to an RQ)

- **Sensor-specific adapters** — normalize modality-specific statistics
  without pretending all sensors share channels (RQ1). Adapters are
  deliberately thin; heavy per-sensor towers would recreate sensor-
  specific models and defeat the unification hypothesis (H6).
- **Band/wavelength identity** — the model must never treat "channel 4"
  as a permanent semantic slot; wavelength + band name + sensor move with
  the data (RQ1; ablation H2).
- **Resolution embeddings + native-grid adapters** — state GSD explicitly;
  never encode an implicit "10 m-ness" by upsampling 30 m data. Cross-
  resolution comparisons remain resolution-honest in evaluation.
- **Time/DOY/year embeddings on irregular sequences** — observations
  arrive at arbitrary times and counts; time is data, not an array index
  (RQ3/H4).
- **Geo embedding** — let the model know coarse position (tile/region)
  while preventing trivial memorization of test geography; evaluate
  cross-region with geo embeddings ablated (RQ6).
- **Gated multimodal fusion** — combine optical/SAR/context conditioned on
  availability and reliability (cloud flags), trainable under modality
  dropout (RQ2/H3).
- **Heads** — segmentation is primary; change, uncertainty, trajectory,
  and recurrence heads share the backbone but are added only when their
  labels exist.

## 4. Candidate pretraining objectives (candidates, not commitments)

1. **Masked multimodal modeling** — mask spatial/temporal tokens and
   reconstruct across available modalities.
2. **Cross-sensor alignment** — co-located observations across sensors
   share representation space (contrastive/reconstruction hybrid).
3. **Temporal representation prediction** — predict held-out future
   observations or ordering-consistent embeddings.
4. **Modality-dropout reconstruction** — reconstruct a dropped modality
   from the others.

Each is a hypothesis about invariance; whether each helps target
performance is an M4 ablation question, not a claim.

## 5. Explicit non-goals at M0

- No model code beyond structural placeholders.
- No claim that this architecture is novel; much is deliberately
  conventional (SatMAE/AnySat/Prithvi-style identity tokenization is prior
  art to cite and benchmark against — `TODO_CITATION`).
- No results, no parameter counts claimed as achieved, no pretrained
  weights.
- No nationwide inference; no recurrence claims without management data.

## 6. Decision gates before building at scale

| Gate | Condition to proceed |
|---|---|
| G1 Sensor adapters | M2 shows measurable cross-sensor degradation that shared fixed-channel models cannot absorb |
| G2 Temporal transformer | Sparse-Temporal track exposes fixed-cadence failure |
| G3 Gated fusion | Missing-Modality shows fusion robustness gap vs. strong ensemble |
| G4 Full SpartinaFM pretraining | At least one foundation baseline + simple head leaves a documented, repeated gap on ≥2 tracks; otherwise contribution pivots to Atlas / Shift / recurrence |

## 7. Engineering constraints for M4

- Inputs are read only from local COG/Zarr via manifest version; no live
  GEE calls.
- Model config and token schema serialized per run; seed(s), commit,
  tokenizer/band-map version logged.
- Works within the project GPU budget (≤3 RTX 3090 unless explicitly
  approved; smoke tests first).
- Uncertainty is calibrated on disjoint validation units and evaluated on
  test units; never tuned on test.
