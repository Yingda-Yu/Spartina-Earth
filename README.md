# Spartina Earth

**Long-term, open, reproducible Earth observation and AI for the invasive
coastal grass *Spartina alterniflora* across changing satellites, years,
regions, and management regimes.**

[![status](https://img.shields.io/badge/status-M0%20repository%20reboot-yellow)]()
[![license](https://img.shields.io/badge/code%20license-Apache--2.0-blue)]()
[![python](https://img.shields.io/badge/python-%E2%89%A53.10-blue)]()

## Why Spartina?

*Spartina alterniflora* is a perennial salt-marsh grass native to the
Atlantic and Gulf coasts of North America. Introduced to China in 1979, it
spread rapidly across intertidal zones, altering sediment dynamics,
hydrology, and native habitats, and has become one of China's most
prominent coastal invasive species. Large-scale eradication programs are
under way, and cleared areas can recur.

Monitoring this invasion consistently over decades is hard: the satellite
record spans multiple sensor generations (Landsat 5/7/8/9, Sentinel-1/2),
different spatial resolutions, optical and radar modalities, irregular and
cloud-contaminated observations, shifting phenology, expanding geographic
extent, and a landscape transformed by management. A model trained on one
sensor, year, or region is not automatically trustworthy on another.

## Research Vision

Build and evaluate a **sensor-agnostic, multimodal, temporal
representation** that identifies *S. alterniflora* stably across that
entire variation, and use it to produce traceable, uncertainty-qualified
long-term products — including the dynamics of invasion, eradication, and
post-eradication recurrence.

## Scientific Questions

See [`docs/research/SCIENTIFIC_QUESTIONS.md`](docs/research/SCIENTIFIC_QUESTIONS.md)
and falsifiable hypotheses in
[`docs/research/HYPOTHESES.md`](docs/research/HYPOTHESES.md). Headline
questions:

1. Can a stable ecological representation be learned across satellite
   generations?
2. How should optical, SAR, and environmental context fuse under missing
   modalities?
3. Can temporal representations stay stable under irregular observation,
   cloud, and phenology?
4. Is pre/post-eradication change a distinct management domain shift?
5. Can a unified model outperform sensor-specific models, fairly tuned?
6. Zero-/few-shot transfer to unseen China coastal regions?
7. Transfer to native/invaded Spartina contexts in other countries?
8. Do historical trajectories predict post-treatment recurrence?

## Project Ecosystem

| Component | Role | M0 state |
|---|---|---|
| **SpartinaFM** | Cross-sensor, cross-era multimodal temporal model | [design doc](docs/models/SPARTINAFM_DESIGN.md) only; hypotheses, not validated innovation |
| **Spartina Atlas** | Long-term distribution/change/recurrence/uncertainty products | not built |
| **SpartinaShift** | Generalization benchmark (region/year/sensor/management/missing-modality) | [SPEC](benchmarks/spartinashift/SPEC.md) contract only, no results |
| **SpartinaGuard** | Separate operational Web GIS product | consumes outputs via [integration contract](integrations/spartinaguard/README.md); code lives elsewhere |

## Repository Status

**M0 — Repository Reboot / Evidence Audit.**

This repository currently contains governance, specifications, interface
skeletons, tests, and audits. It does **not** yet contain trained models,
benchmark results, or a completed China-scale dataset. No claim in this
repository should be read as asserting completed model performance or
national mapping results. Historical prototype code is preserved under
[`legacy/`](legacy/README.md) as unverified history and must not be cited
as current evidence.

## Research Roadmap

- **M0 — Evidence Audit (current):** audit repository and legacy claims,
  stand up governance, specs, interfaces, and tests. No bulk GEE
  downloads, no GPU training.
- **M1 — Data Engine:** GEE catalog/QA, fixed coastal grid, sensor
  preprocessing, object storage, COG/Zarr formats, provenance manifests.
- **M2 — Benchmark:** construct spatially disjoint SpartinaShift tracks.
- **M3 — Strong Baselines:** RF/XGBoost, U-Net, DeepLabV3+, SegFormer, and
  foundation baselines (SatMAE, Prithvi-EO, AnySat), fairly tuned.
- **M4 — SpartinaFM:** only after baseline failure modes are known.
- **M5 — China-scale Reconstruction:** Atlas v1 with uncertainty.
- **M6 — Recurrence:** post-eradication recurrence detection/forecasting.
- **M7 — Global Transfer:** evaluation outside China.

## Reproducibility

All formal experiments record Git commit, config, data-manifest version,
split version, seed, software environment, and metrics
([standard](docs/experiments/EXPERIMENT_STANDARD.md)). Data assets are
described by machine-readable manifests
([schema](datasets/manifests/schema.json)). Train/test splits must be
spatially disjoint — random neighboring-patch splits are prohibited.

## Data Governance

Code is Apache-2.0 licensed; **data are not**. Sentinel, Landsat,
government products, third-party paper data, and collaborator UAV data
each carry their own licenses, which are confirmed per asset
([DATA_LICENSE.md](DATA_LICENSE.md)). Raw imagery, labels, and checkpoints
are stored outside Git; this repository tracks manifests, code, configs,
and summaries. Findings about existing data assets are in
[`docs/audit/DATA_INVENTORY.md`](docs/audit/DATA_INVENTORY.md) and
[`docs/audit/LABEL_INVENTORY.md`](docs/audit/LABEL_INVENTORY.md).

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) and
[`AGENTS.md`](AGENTS.md) (mandatory reading for agents). All work happens
on branches; M0 work is on `reboot/spartina-earth-m0`.

## Citation

If you use this repository in academic work before a formal release paper,
cite the repository via [`CITATION.cff`](CITATION.cff). A paper-level
citation will be added when a peer-reviewed publication exists. Do not
fabricate citation details.

## License

Original code in this repository: [Apache-2.0](LICENSE). Data and
third-party models follow their own licenses
([DATA_LICENSE.md](DATA_LICENSE.md),
[THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md)).
