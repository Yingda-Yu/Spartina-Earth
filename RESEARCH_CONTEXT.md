# RESEARCH_CONTEXT.md

> Single-page research context consumed by agents and by the academic
> writing skill (`.trae/skills/research-english-academic-paper-writing-guide/`,
> local-only, not committed). Keep this file factual; no marketing claims.

## Project

**Spartina Earth** — a long-term, open, reproducible Earth-observation + AI
research program for *Spartina alterniflora* (smooth cordgrass / 互花米草),
maintained by Spartina Technology.

## Organism

*Spartina alterniflora* — a perennial salt-marsh grass native to the
Atlantic/Gulf coasts of North America and a major invasive species along
the coast of China (and elsewhere), with active large-scale eradication
programs and documented post-eradication recurrence.

## Long-term scope

**China coast first, global transfer second.**

- Phase A: sensor-harmonized, long-term reconstruction and monitoring along
  the China coast.
- Phase B: transfer evaluation to native and invaded ranges in other
  countries.

## Primary scientific contribution

A **sensor-agnostic multimodal temporal Earth-observation representation**
that remains ecologically stable as sensors, resolutions, modalities,
years, phenology, regions and management regimes change.

## Core challenges

- cross-sensor generalization (Landsat 5/7/8/9, Sentinel-1, Sentinel-2)
- cross-era / cross-generational consistency
- cross-region transfer (China coastal provinces; later global)
- multimodal fusion (optical + SAR + environmental context)
- irregular temporal observations and cloud contamination
- missing modalities at inference time
- phenological variation
- management domain shift (pre/post eradication)
- post-eradication recurrence detection / forecasting
- calibrated uncertainty

## Primary data families

| Family | Role | Status in repo at M0 |
|---|---|---|
| Landsat 5 / 7 / 8 / 9 | Decadal optical backbone (30 m) | Interfaces only; no data downloaded |
| Sentinel-2 | Optical high-revisit (10/20 m) | Interfaces only |
| Sentinel-1 | SAR, cloud-free / tide-independent signal | Interfaces only |
| HLS | Harmonized Landsat-Sentinel, where scientifically justified | Not yet adopted; pending justification |
| DEM | Environmental / elevation context | Not yet acquired |
| inundation / tidal proxies | Ecological context | Not yet acquired |
| UAV / high-resolution / field reference | GOLD labels | Legacy references only; actual labels MISSING at M0 |
| Existing Spartina mapping products | SILVER labels / comparison | One known product under `old datasets/` audit (2015, 30 m China) |

## Long-term products

- **SpartinaFM** — the model family (design doc only at M0:
  `docs/models/SPARTINAFM_DESIGN.md`)
- **Spartina Atlas** — data products (not built at M0)
- **SpartinaShift** — generalization benchmark (spec only at M0:
  `benchmarks/spartinashift/SPEC.md`)
- **SpartinaGuard integration** — standardized outputs for the separate Web
  GIS product (`integrations/spartinaguard/`)

## Milestones

| Milestone | Theme | M0 status |
|---|---|---|
| M0 | Evidence audit & repository reboot | **in progress → this branch** |
| M1 | Data engine (GEE catalog, grid, QA, storage, manifests) | not started |
| M2 | SpartinaShift benchmark construction | not started |
| M3 | Strong, fairly-tuned baselines | not started |
| M4 | SpartinaFM pretraining & adaptation | not started |
| M5 | China-scale reconstruction (Atlas v1) | not started |
| M6 | Recurrence analysis & forecasting | not started |
| M7 | Global transfer | not started |

## Publication ambition

High-quality Earth observation / environmental science research (venues
such as Remote Sensing of Environment, ISPRS Journal of Photogrammetry and
Remote Sensing, IEEE TGRS, or a Nature Portfolio journal when the evidence
genuinely supports it). **Do not optimize research decisions for a
specific journal before evidence exists**, and do not write journal targets
as guarantees. See `docs/research/PUBLICATION_MAP.md`.

## Evidence status at M0 (summary)

- Legacy prototype code: present, preserved, **UNVERIFIED**; it was a
  Windows-local, Google-Images + CNN/U-Net/COCO sketch with no recorded
  metrics, checkpoints, or EO data.
- Real GOLD Spartina labels on this server: **not found** in the audited
  repository at M0.
- Real ROI / study-area geometries: **not found** in the audited
  repository at M0.
- GEE scripts or asset identifiers: **not found** at M0.
- Old checkpoints: **not found** at M0.
- Reproducibility of any legacy manuscript metric: **not possible at M0**
  (no raw evidence located).
- Older external datasets are being transferred by the user into
  `old datasets/`; audited separately in `docs/audit/DATA_INVENTORY.md`
  and treated as raw, unverified inventory.
