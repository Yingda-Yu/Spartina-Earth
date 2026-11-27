# HISTORICAL_RECONSTRUCTION_PLAN — China coastal Spartina 1985–2025

Version: v1.0 plan (2026-11-27). Data-production plan for the Atlas
historical backbone. Plan only; nationwide export requires separate Owner
authorization. All layer definitions respect the Atlas integrity rules
(CHINA_COASTAL_ATLAS_SPEC.md §0).

## 1. Sensor-era plan

| Era | Sensor | Resolution | Years | Role | Notes |
|---|---|---|---|---|---|
| 1985–2011 | Landsat 5 TM | 30 m | annual candidate set | historical backbone | 16-day revisit; winter/cloud gaps expected — NO_VALID_OBSERVATION semantics |
| 1999–2013 | Landsat 7 ETM+ | 30 m | overlap era | backbone + cross-era calibration | SLC-off after 2003: VALID mask + coverage stats per cell-year |
| 2013–2025 | Landsat 8/9 OLI(-2) | 30 m | modern 30 m layer | backbone continuity to present | QA_PIXEL/QA_RADSAT C2 predicates |
| 2015–2025 | Sentinel-2 MSI | 10 m | modern high-res layer | modern refinement; separate family | 5-day revisit; s2_scl_qa_v1_1 mask |
| 2014–2025 | Sentinel-1 SAR | 10 m | all-weather layer | inundation-insensitive support; separate family | dualpol; S1B gap 2021+ documented |

Key requirement (RQ1 dependency): cross-era stability is a research
output, not an assumption — era-specific models are evaluated on
held-out eras (Historical-Sensor track) before multi-era Atlas
classification is trusted.

## 2. Historical label strategy

- No historical GOLD exists. Historical layers are model estimates with
  uncertainty, anchored by:
  1. frozen SILVER families (2015 GEODATA, 2020 GEODATA, 2020/2021 CMSA)
     for model calibration points;
  2. peer-reviewed historical Spartina extent studies (literature
     digitization with citation per segment) as coarse plausibility
     anchors — never used as pixel labels without provenance;
  3. GOLD pilot/Tier sites as they materialize (independent validation,
     not training).
- 1980s–1990s layers are declared lower-confidence in Product F metadata;
  temporal claims that span eras carry era-specific uncertainty.

## 3. Coverage accounting (per cell-year, per family)

- n_obs_total, n_valid_obs (QA-pass), valid area fraction per observation,
  best-observation selection rule (deterministic, documented: max valid
  fraction within autumn window, else max valid fraction any window),
  tide-state proxy where available.
- Cells failing coverage are `NO_VALID_OBSERVATION` in the year grid;
  coverage rasters co-released.

## 4. Change products (B/C/D/E)

- Expansion (B): first-passaging detection on ≥2 consecutive valid years;
  date uncertainty interval reported.
- Disappearance (C): last-passaging + a passing observation with
  negative evidence (label-negative or expert annotation); otherwise
  candidate-only.
- Residual (D): fragments ≤9 px flagged as residual stratum; requires
  management context for interpretation.
- Recurrence candidates (E): positive re-detection inside verified
  treatment boundaries only; treatment ledger is empty → Product E
  stays BLOCKED.

## 5. Batch plan (authorization-gated)

1. Pilot batch: 1 province (ZJ), 2015–2025, both families — validates
   pipeline end-to-end on already-familiar territory.
2. Era-bridge batch: L7↔L8 overlap years for cross-era calibration
   evidence (feeds Historical-Sensor track too).
3. Backward batches: L5 era 1985–2011 by coastal segment, north→south.
4. Each batch: disk audit, export authorization record, QA ledger,
   Owner review before next batch.

## 6. Environmental context integration

- DEM (Copernicus GLO-30) for elevation/habitat context; tidal exposure
  proxies per ZHEJIANG_TIDE_INUNDATION_POLICY_V0.md; coastline and admin
  boundaries for reporting units. Licenses recorded at integration.
