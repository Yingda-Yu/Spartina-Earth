# CHINA_COASTAL_ATLAS_SPEC

Version: v1.0 spec (2026-11-27). Production specification for the China
Coastal Historical Atlas (1985–2025). **Spec only; no Atlas product exists.**
Nationwide export requires separate Owner authorization; the 53-cell
SpartinaShift footprint is not an Atlas product.

## 0. Integrity rules (non-negotiable)

- **Temporal honesty**: a cell-year with no valid observation is reported
  `NO_VALID_OBSERVATION`, never as species disappearance. Disappearance
  requires a passing observation with label-negative or expert evidence.
- **Resolution families separate**: Landsat 5/7/8/9 30 m historical
  backbone and Sentinel-1/2 10 m modern layer are never merged or
  cross-promoted; 30 m output never presented at 10 m.
- **Recurrence candidates ≠ recurrence**: candidates from Product E are
  never called confirmed recurrence without independent evidence.
- **Uncertainty everywhere**: every map carries per-cell confidence /
  observation coverage (Product F layers are co-released, not optional).

## 1. Product definitions

| Product | Content | Resolution family | Status |
|---|---|---|---|
| A Historical distribution | annual/observation-supported presence maps per coastal segment | 30 m (1985–2012 L5; 1999–2013 L7; 2013– L8/9); 10 m (2015– S2) | NOT_STARTED |
| B Expansion | newly detected invasion areas + expansion rates with date uncertainty | same families | NOT_STARTED |
| C Disappearance | confirmed disappearance only under the temporal-integrity rule | same families | NOT_STARTED |
| D Residual populations | fragmented residual patches post-management | 10 m preferred | BLOCKED (needs mgmt context) |
| E Recurrence candidates | possible new growth in treated areas — candidate flag only | 10 m + S1 trajectories | BLOCKED (0 treatment records) |
| F Uncertainty | pixel-level + region-level confidence, observation coverage, label uncertainty, model disagreement | per family | co-released with A–E |
| G Management response | treatment events linked to before/after change | per family | **BLOCKED: 0 verified treatment records** |

## 2. Observation accounting

- Per cell-year: n_valid_obs, obs dates, sensor list, QA-pass fractions,
  cloud/fraction statistics — all from the QA ledger semantics
  (v0.2.2 predicates per sensor).
- Seasons: autumn phenology window preferred for Spartina discrimination;
  off-window observations labeled as such in coverage metadata
  (ZHEJIANG_PHENOLOGY_AND_SEASON_POLICY_V0.md).

## 3. Classification and provenance

- Model versions behind Atlas layers are frozen benchmark artifacts with
  full run provenance; no ad-hoc retraining for Atlas figures.
- SILVER-trained model outputs are labeled as model estimates with
  uncertainty — never as authoritative presence/absence; GOLD validation
  upgrades the claim only when Tier ≥2 exists.
- Per-figure provenance: model run_id, dataset manifest SHA, split ref,
  inference date.

## 4. Aggregation and reporting units

- Native-grid pixels → coastal-segment statistics (km², ±CI from
  spatial bootstrap) → province rollups. Gridded uncertainty products
  released alongside raster maps (GeoTIFF COG).
- Change statistics require ≥2 valid observations in the relevant years;
  otherwise interval reported as open-ended.

## 5. Production pipeline (planned)

catalog planner → per-cell-year export (asynchronous, resumable, same
export/QA machinery as Issue #21) → QA ledger → inference (frozen models)
→ uncertainty propagation → segment/province aggregation → cartographic
rendering per CARTOGRAPHIC_DESIGN_STANDARD.md → release manifest.

Each nationwide batch requires: disk audit, export authorization record,
and Owner review of the pilot province before scale-up.
