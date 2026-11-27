# EO Data Engine — Target Architecture (M1 design)

Status: **architecture design, M0.** No GEE exports and no downloads have
been performed. This document defines the target so M1 starts from an
agreed contract rather than ad-hoc scripts.

## 1. Goal

Produce fully traceable, quality-controlled, sensor-documented Earth
observation data for the China coastal zone (later global), from raw
catalog scenes to training-ready arrays and archive products.

Every byte must answer: which scene, which preprocessing version, which
label version, which grid cell, at what time — see
[`../../AGENTS.md`](../../AGENTS.md) §4.8.

## 2. Pipeline

```
Google Earth Engine (catalog / compute / export)
        │
        ▼
Scene Query  ──►  sensor-specific collections
        │           (date window, region, cloud/QA filter)
        ▼
Quality Assessment  ──►  per-scene QA flags, coverage, metadata record
        │
        ▼
Sensor-specific preprocessing
  Landsat 5/7/8/9: C2 L2 SR/ST, scaling, QA-PIXEL masking, SLC-off policy
  Sentinel-2:     COPERNICUS/S2_SR_HARMONIZED, SCL/cloud masking, band mapping
  Sentinel-1:     GRD, orbit/edge handling, dB conversion, terrain policy
        │
        ▼
Fixed coastal grid  (versioned CRS + tile schema, overlapping footprint rule)
        │
        ▼
Async export (batched, rate-limited, resumable; no training-time GEE calls)
        │
        ▼
Object storage on server / future object store
        │
        ▼
COG archive  (raw-ish analysis-ready tiles + overviews)
        │
        ▼
Training data format  (Zarr or WebDataset — decided after an M1 I/O benchmark)
        │
        ▼
GPU cluster  (M3+: pretraining / fine-tuning / inference / evaluation)
```

## 3. Responsibility split

| Concern | Where it lives |
|---|---|
| Catalog queries, cloud-side preprocessing, compositing, export tasks | Google Earth Engine |
| Credentials / auth | local-only, never in Git; `src/spartina/data/gee/auth.py` detects them, tests mock them |
| Grid definition, manifest records, checksums | this repository |
| Bulk bytes | server storage outside Git (`datasets/raw`, `datasets/processed` — gitignored) |
| Self-supervised learning, fine-tuning, inference, evaluation | server GPUs |
| **Hard rule: no per-batch live GEE requests during training** | enforced by architecture; training reads local COG/Zarr only |

## 4. Supported sensors at M1

- Landsat 5 (TM), 7 (ETM+; explicit SLC-off gap policy), 8 & 9 (OLI) —
  Collection 2 Level-2.
- Sentinel-1 GRD (IW, VV/VH as available).
- Sentinel-2 Surface Reflectance Harmonized.
- **HLS:** deferred. It is adopted only with a documented scientific
  justification (specific harmonization need that sensor adapters cannot
  otherwise address); no HLS exports in M1 by default.

Every sensor is described by a `SensorSpec`
([`../../src/spartina/data/sensors/registry.py`](../../src/spartina/data/sensors/registry.py)):
name, platform, modality, native resolution, bands+wavelengths, scale
factor, nodata, operational date range, QA bands. Bands are referenced by
**identity** (name/wavelength), never by hard-coded channel index.

## 5. Grid and tile scheme (to be finalized in M1)

- Fixed coastal grid buffered inland to cover estuarine extent; versioned
  definition stored as a manifest + geometry outside Git.
- One CRS strategy documented (e.g. UTM zones per tile segment vs. an
  equal-area analysis CRS); resampling between CRS/resolutions explicit.
- Tiles carry unique `tile_id`, geometry hash, CRS, and resolution.
- Footprints that overlap tiles follow a fixed assignment rule; no scene
  pixel may silently enter two adjacent tiles' train/test sides (enforced
  with the leakage checker).

## 6. Storage formats

| Format | Role |
|---|---|
| **Cloud-Optimized GeoTIFF (COG)** | analysis-ready archive, visualization, inference outputs, uncertainty maps |
| **Zarr or WebDataset** | training arrays; choice after an M1 benchmark comparing sequential/remote I/O, sharding, and random-access trajectory reads |
| **GeoParquet** | spatial metadata, tile index, patch trajectories, label indices |
| PostGIS | operational SpartinaGuard layer only — **not** a research-training dependency at this stage |

Naming and layout are specified in a storage contract to be added in M1
(`docs/data/STORAGE_CONTRACT.md`), including: read-only raw zone,
versioned processed zone, per-tile manifests, and atomic writes.

## 7. Quality and manifests

- Each exported scene/tile writes a manifest entry following
  [`../../../datasets/manifests/schema.json`](../../../datasets/manifests/schema.json):
  ids, times, bbox/CRS/resolution, bands, checksum, QA summary,
  provenance chain, status.
- QA rejects/flags: cloud/coverage thresholds, missing bands, corrupt
  rasters (checksum fail), SLC-off-heavy scenes (flagged, not auto-deleted),
  SAR edge/orbit anomalies.
- Pipeline versions (collection ID, code commit, preprocessing params) are
  part of every product; reruns create new versions, never overwrite.

## 8. Failure handling and safety

- Exports are batched, resumable, and rate-limited; failures logged to a
  task manifest, retried with backoff, and surfaced rather than hidden.
- M0/M1 guardrails: no nationwide export without explicit approval;
  smoke-test exports on ≤ a few tiles first (per project smoke-test-first
  policy).
- No secrets logged; export logs may contain task IDs but not credentials.

## 9. Interfaces in this repository (skeleton only at M0)

`src/spartina/data/gee/` contains contracts without large fake
implementations:

- `auth.py` — credential detection (no credential storage).
- `catalog.py` — scene query interface.
- `collections.py` — collection/band mapping per sensor.
- `quality.py` — QA predicate interface.
- `export.py` — export-task interface.
- `manifest.py` — manifest writing from task metadata.

Integration tests are marked `gee_integration` and auto-skip without
credentials; unit tests use mocks.

## 10. M1 deliverables (preview, not commitments of results)

- Frozen grid v0 and `SensorSpec` entries for the six sensors.
- Storage contract and I/O benchmark memo (Zarr vs. WebDataset decision).
- Small end-to-end smoke export on a handful of tiles, manifest-complete.
- Data-inventory update marking assets VERIFIED only after checksum and
  QA pass.
