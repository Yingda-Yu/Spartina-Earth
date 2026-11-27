# SCIENTIFIC_QUESTIONS.md

Research questions for Spartina Earth. Each RQ is stated so that it can be
answered with a defined experiment on a defined benchmark track
(see [`../../benchmarks/spartinashift/SPEC.md`](../../benchmarks/spartinashift/SPEC.md)).
Questions are not claims; falsifiable hypotheses derived from them live in
[`HYPOTHESES.md`](HYPOTHESES.md).

Flagship question (umbrella):

> Can a sensor-agnostic multimodal temporal Earth-observation model learn a
> stable representation of *Spartina alterniflora* across changing
> satellite generations, regions, phenological stages and management
> interventions, enabling consistent long-term monitoring and early
> detection of post-eradication recurrence?

---

## RQ1 — Cross-generation sensor stability

Can a single learned representation remain stable for *S. alterniflora*
across satellite generations (Landsat 5 → 7 → 8 → 9, and against
Sentinel-1/2), given different band passes, radiometry, resolutions, and
observation eras?

- Why it matters: decadal ecological trajectories (invasion, treatment,
  recurrence) span sensor generations; era-specific models make
  before/after comparisons uninterpretable.
- Primary track: `Historical-Sensor`, `Cross-Sensor`.
- What would answer it: held-out-era and held-out-sensor performance gaps,
  calibrated uncertainty, and feature/representation stability measures
  versus strong per-sensor baselines.

## RQ2 — Multimodal fusion under modality dropout

How should optical, SAR, and environmental context (DEM, inundation/tidal
proxies) be fused, and how is performance preserved when a modality is
missing at inference (no Sentinel-2 observation, no SAR pass)?

- Why it matters: clouds, acquisition schedules, and sensor lifetimes make
  missing-modality the operational norm, not the exception.
- Primary track: `Missing-Modality`.
- What would answer it: paired comparison of fusion schemes under
  controlled modality dropout, including degradation curves vs. fraction
  of modalities present.

## RQ3 — Temporal stability under irregular observation

Can temporal representations stay stable under irregular sampling, cloud
contamination, and phenological differences, rather than memorizing
calendar/DOY signatures or a fixed monthly cadence?

- Primary track: `Sparse-Temporal`, `Cross-Year`.
- What would answer it: performance under controlled temporal subsampling
  and shifted acquisition schedules; invariance to observation density at
  matched information content.

## RQ4 — Management as a domain shift

Do pre-eradication and post-eradication ecological states constitute an
independent management domain shift that a naïvely trained model fails on,
and can the shift be characterized and bridged?

- Why it matters: treated surfaces (mudflat, recovering vegetation,
  recurring Spartina) violate the label distribution of intact invasion.
- Primary track: `Management-Shift`.
- What would answer it: performance on mapped treatment units
  pre/post-intervention vs. untreated controls, with treatment metadata as
  the domain variable.

## RQ5 — Unified model vs. sensor-specific models

Does a unified sensor-agnostic model match or beat fairly tuned
sensor-specific models under equal data, budget, and tuning — and where
exactly does it lose, if anywhere?

- Primary track: all tracks (paired model comparison).
- What would answer it: non-inferiority/equivalence tests per track, plus a
  single-model-vs-ensemble operational comparison. Guardrail: the
  comparison must not be designed to make the unified model look good (see
  [`../models/BASELINES.md`](../models/BASELINES.md)).

## RQ6 — Zero-/few-shot transfer within China

Can a model trained on some China coastal regions transfer zero-shot (or
with very few labels) to unseen provinces/segments with different climate,
tidal range, sediment, and land-use?

- Primary track: `Cross-Region`.
- What would answer it: leave-one-region-out evaluation, few-shot curves
  (0, 1, 5, 10, 50 labeled patches), with test regions excluded from all
  model selection.

## RQ7 — International transfer

Does a China-trained representation transfer to native-range sites (e.g.
North American salt marshes) and invaded sites in other countries, with
different genotypes, competitors, tidal and climatic regimes?

- Primary track: `Cross-Region` (international split; M7, data permitting).
- What would answer it: independent evaluation on non-China labels only;
  no Chinese labels in test-region tuning. Status is contingent on
  acquiring legal, licensed external data — currently `UNKNOWN`.

## RQ8 — Recurrence predictability

Do pre-treatment and post-treatment temporal trajectories contain signal
that predicts *where and when* Spartina recurs after eradication, beyond
static covariates and baseline rates?

- Primary track: `Management-Shift` (recurrence subtask).
- What would answer it: event-based evaluation (recurrence recall, lead
  time, false alerts per km², high-risk patch capture) against operational
  baselines (persistence, static habitat suitability).

---

## Cross-cutting requirements for every RQ

- Spatially disjoint evaluation units; test regions excluded from
  hyperparameter selection.
- Calibrated uncertainty reported alongside every point estimate
  (ECE, Brier, NLL).
- Area-level and boundary-level metrics in addition to pixel scores.
- Negative results and "the foundation model already solves this" results
  are valid answers and redirect the research contribution toward data,
  benchmark, ecology, or recurrence work rather than architecture novelty.
