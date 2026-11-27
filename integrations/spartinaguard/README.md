# SpartinaGuard Integration Contract

**SpartinaGuard is an independently developed and maintained Web GIS
operational product. Its frontend/backend code does not live in this
repository and is not copied here.** This directory defines only the
data/model interface that keeps research code and product code decoupled.

## Direction of integration

```
Spartina Earth (research)                         SpartinaGuard (operations)
-------------------------                         --------------------------
standardized products + manifests   ───consume──► Web GIS monitoring layer
(versioned, schema-described)
```

The research repo never depends on SpartinaGuard's database or UI for
training. SpartinaGuard never reaches into research checkpoints or raw
scenes directly; it consumes released, versioned artifacts.

## Outputs the research repo will provide (versions frozen per release)

| Artifact | Format | Notes |
|---|---|---|
| Classification / probability / cover maps | COG | cloud-optimized, overviews, CRS documented per tile |
| Uncertainty maps | COG | calibrated intervals/ECE-qualified products |
| Vector delineations / events | GeoJSON / GeoParquet | CRS + schema versioned |
| Change and treatment-event products | GeoParquet / COG | gains/losses with timestamps |
| Patch trajectories | GeoParquet | per-patch temporal states keyed by stable patch id |
| Recurrence risk products | GeoParquet / COG | only when verified management data exists; horizon + threshold declared |
| Time-series products | GeoParquet / tabular | irregular-time observations with sensor identity |
| Model manifest | JSON | model id, commit, training data manifest versions, input band map, calibration metadata, license |

## Contracts (to be formalized in M5+)

- Stable versioned schemas (aligned with
  `../../datasets/manifests/schema.json`); breaking changes bump a major
  contract version and include a migration note.
- Every artifact carries provenance: model id/commit, data manifest
  versions, inference config, timestamp, CRS, units.
- Uncertainty and "no data / cloud / treated" statuses are explicit bands
  or attributes, never encoded by silently zeroing pixels.
- No credentials or operational connection strings in this repo.
- Coordinate reference systems and area units (m²/km²) declared per
  product; no mixed-CRS area statistics.

## What this directory contains at M0

Only this README. Schema files, sample payloads, and conformance tests are
added when the first release candidate exists — no speculative interface
code is built now.
