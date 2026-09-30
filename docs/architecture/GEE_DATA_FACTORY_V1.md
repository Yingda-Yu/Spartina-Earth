# GEE EO Data Factory v1 — Issue #6 (M1.6)

Status (updated 2026-09-30 after real authentication): **real catalog
retrieval VERIFIED** against Earth Engine with project
`project-795fc21c-e217-47f3-adb` (L8/S1/S2 over HZB_TECH_SMOKE_V1, double
retrieval deterministic); **the first real Landsat-8 export is GATE-FAILED
because all 3 fixed-window L8 scenes exceed the predeclared 0.30 ROI cloud
threshold** — no bytes were exported. Evidence:
[GEE_REAL_QUERY_SMOKE.md](../data/GEE_REAL_QUERY_SMOKE.md). Nothing here
performs a nationwide download; the first real run targets one small
Hangzhou Bay ROI and is exercised only via `pytest -m gee_integration`.

## 1. Goals and hard rules

1. Every exported asset traces back to its **exact source scenes**
   (scene ID, product ID, acquisition UTC, sensor, tile/orbit, cloud and
   ROI coverage). "2015 composite, source scenes UNKNOWN" must never
   recur.
2. Two fixed science streams, never mixed:
   * `landsat_30m` — Landsat 5/7/8/9 C2 L2 on a 30 m grid;
   * `sentinel_10m` — Sentinel-1/2 native 10 m on a 10 m grid.
   Placing 30 m native data on a 10 m grid raises `GridError`
   (`assert_no_forced_upsampling`); upsampled 30 m is never presented as
   a true 10 m historical product (AGENTS.md rule 7).
3. Rejected scenes stay in the candidate table; selection is explicit.
4. Tide/inundation is **PROXY only** until a real gauge feed is
   integrated and evidenced.
5. `ee` is imported lazily in every module; unit tests need no network,
   no credentials and not even the `earthengine-api` package.

## 2. Modules (`src/spartina/data/gee/`)

| Module | Responsibility |
|---|---|
| `auth.py` | Credential detection + lazy `ee.Initialize()`; never logs secrets or performs interactive login. |
| `sensors/registry.py` | Identity-based `SensorSpec` for L5/7/8/9, S1, S2 (bands, wavelengths, native resolution, scale/offset, QA bands, valid period, modality). |
| `collections.py` | Central GEE collection-ID map + C2/S2 scaling constants. |
| `landsat.py` | L5/7/8/9 collection filtering, pure `QA_PIXEL`/`QA_RADSAT` decoders, EE clear-mask and per-family scaling (SR 2.75e-5−0.2; ST ×0.00341802+149 K), scene-property mapping. |
| `sentinel2.py` | S2 SR Harmonized: pure SCL class decoder (valid 4/5/6/11), `MSK_CLDPRB` mask, ÷10000 scaling, MGRS tile / product / cloud metadata. |
| `sentinel1.py` | S1 GRD IW: IW-mode + polarization filters, orbit direction validation, relative orbit / platform / resolution provenance; no scaling (GEE sigma0 dB). |
| `catalog.py` | `CatalogClient` protocol, `MockCatalogClient`, and the real `EarthEngineCatalogClient` (lazy `ee`, ROI footprint-coverage annotation, ISO UTC conversion). |
| `quality.py` | Metadata QA filters, `CandidateScene` + `build_candidate_table` (all candidates retained), coverage rule. |
| `pixelqa.py` | Pure QA bit/SCL decoders **plus server-side ROI pixel COUNTS** (`counts_landsat`/`counts_sentinel2`/`counts_sentinel1`): explicit total denominator via a constant-1 band and `unmask(0)`, yielding valid/cloud/shadow/cirrus/snow/saturated/clear fractions computed inside EE rather than from scene-level metadata. |
| `selection.py` | Deterministic `best_single_scene` policy; `rank_eligibles` (coverage → valid → cloud → shadow → circular DOY → UTC → id), `best_per_sar_pass` (ASCENDING/DESCENDING ranked separately), multi-key `footprint_coverage` reader, explainable rejection reasons, `canonical_fingerprint` (canonical-JSON SHA-256). |
| `driveio.py` | Google Drive download of finished exports using the same Earth Engine OAuth credentials (Drive scope included); `download_latest(name_prefix)` skips trashed files. |
| `provenance.py` | `git_context`, `runtime_environment`, `sha256_file`, `raster_grid_info` + `assert_grid_matches`, `reflectance_sanity` (per-band percentiles + un-scaled-DN screen), and `assert_provenance_chain` — the end-to-end source-scene → landed-file hard assertion. |
| `grid.py` | `GridSpec` (crs, 6-tuple affine transform, width/height, pixel size, bounds), pixel-snapped covering grids, stream constructors, anti-upsampling guard. |
| `tide.py` | `TideProxyRecord` — `method="PROXY"` mandatory, `gauge_observed=False` mandatory. |
| `export.py` | `ExportRequest` (now carries grid, exact source scenes, stream), `NullExporter`, atomic `land_bytes()` with mandatory SHA-256. |
| `tasks.py` | JSON-backed `TaskStore` (deterministic IDs, bounded retry, full error history, crash resume), `TaskRunner`, lazy `EarthEngineBatchBackend`. |
| `manifest.py` | M0 scene/export records plus `build_data_factory_manifest()` — the full source→artifact provenance document. |

## 3. Provenance chain

```
EarthEngineCatalogClient.query  -> all scenes as SceneMetadata
        |                         (scene/product id, UTC, tile/orbit,
        |                          cloud, ROI coverage)
        v
build_candidate_table           -> one row per candidate; rejected rows
        |                          retained with reasons; selection explicit
        v
per-sensor QA (lazy EE)         -> QA_PIXEL/RADSAT or SCL/CLDPRB masks;
        |                          valid-pixel fraction per scene
        v
GridSpec (landsat_30m/sentinel_10m; upsampling refused)
        v
ExportRequest(source_scene_ids, grid_spec, science_stream)
        v
TaskRunner/TaskStore            -> enqueue/poll/retry/resume, errors kept
        v
land_bytes()                    -> atomic local landing + SHA-256 verify
        v
build_data_factory_manifest()   -> GEE_DATA_FACTORY_V1 JSON
```

The manifest (`manifest_version: GEE_DATA_FACTORY_V1`) contains: ROI,
science stream, full grid spec, export request, selected scene IDs, the
**entire** candidate table, PROXY tide records, processing config
(QA policy, scaling), export task state, and landed files with
`local_uri`/`sha256`/`size_bytes`. Builder hard-fails when a selected
scene is absent from candidates, the grid spec is incomplete, or a
landed file lacks checksum provenance.

The real-smoke driver additionally attaches `query` (window, target DOY,
candidate-table path), `source_product` (scene/product id, UTC,
WRS/MGRS, selection metrics), `project_id`, `code`
(`git_commit` + `dirty_tree`) and `environment` (python / earthengine-api
/ rasterio versions), then calls `assert_provenance_chain`, which
hard-fails unless all of the following hold: manifest version; selected
ids equal `export_request.source_scene_ids` and are present in the
candidate table with real acquisition UTC and a non-`MISSING` product id;
grid has crs/transform/width/height/pixel_size_m/bounds; export task is
`COMPLETED`; processing config documents scale/offset/masking/band order/
composite; every landed file exists on disk, re-hashes to its recorded
SHA-256, has positive `size_bytes` and `grid_verified is true`; and the
project/code/environment sections are present. Raster grid agreement is
checked separately by `assert_grid_matches` (CRS, dimensions, transform,
pixel size) and float32 reflectance by `reflectance_sanity`.

## 4. Quality metadata

* Optical: catalog cloud fraction (CLOUD_COVER / CLOUDY_PIXEL_PERCENTAGE)
  is retained as a feature but never removes a candidate. The real smoke
  uses **ROI-level raster pixel counts computed server-side**
  (`pixelqa.counts_*`): Landsat per-pixel decision (fill, dilated cloud,
  cirrus, cloud, shadow, snow excluded; Clear bit required;
  `QA_RADSAT == 0`; water allowed), S2 SCL classes (cloud family 8/9/10,
  shadow 3, cirrus 10, snow 11, invalid 0/1; water 6 valid) with a
  recorded `cloud_probability_available` flag for `MSK_CLDPRB`.
* ROI coverage: footprint intersection fraction annotated server-side;
  valid-pixel fraction comes from the same counted denominator; values
  are never guessed (a missing property is `None`/`UNKNOWN`, not 0).
* Sentinel-1: orbit direction, relative orbit number, platform, IW mode,
  polarization, nominal resolution, and per-band availability flags
  (VV/VH/HH/HV/angle); no cloud fields (scored neutral). The raw
  collection is queried **unfiltered** so non-IW / non-VV-VH scenes stay
  visible as rejected candidates.
* Selection thresholds are predeclared (`SingleScenePolicy`: coverage
  ≥0.99, valid ≥0.95, cloud ≤0.30) and frozen before inspection; a fixed
  window with zero eligible scenes is reported as a closed gate, never
  fixed by widening the window after looking.

## 5. Async execution semantics

`TaskStore` persists PENDING/ENQUEUED/RUNNING/COMPLETED/FAILED with
attempt count, bounded `max_attempts`, timestamped error records and
deterministic task IDs (`uuid5` of the request id — re-submitting the
same request raises rather than duplicating). A crashed process resumes
every non-terminal task via `TaskRunner.resume()`; a FAILED backend poll
with attempts remaining re-enqueues with the stored spec. The GEE
backend translates `READY/RUNNING/COMPLETED/FAILED/CANCELLED`.

## 6. Testing

* `tests/unit/test_gee_data_factory.py` — offline unit tests (run on
  system Python 3.10): grids, QA bit decoders, SCL decoding, S1 property
  mapping, candidate-table invariants, PROXY tide enforcement, task
  retry/resume/persistence, checksum landing, manifest guards, lazy-`ee`
  source scan, and a deterministically monkeypatched BLOCKED_BY_AUTH
  behaviour (independent of whether the dev machine is authenticated).
* `tests/unit/test_gee_real_smoke_fixture.py` — replays the selection
  code on the 30 frozen real candidate rows **with no network and no
  credentials**: counts, exact selected ids/ranks, the S1
  15-ascending/0-descending split, L8 zero-eligibility, ROI hash, and
  recomputation of both frozen SHA-256 fingerprints.
* `tests/unit/test_gee_interfaces_mock.py` (M0 contracts) remains green.
* `tests/integration/test_gee_integration.py` — real init smoke; real
  per-sensor candidate-provenance queries (S1 null `productIdentifier`
  accepted as MISSING evidence); the real catalog driver evidence test
  (double retrieval, fingerprints, exact S1/S2 selections); and an
  operator-opt-in test proving the export gate **closes with
  `NO_ELIGIBLE_LANDSAT8_SCENE`** and creates no tif/manifest/task store.
  All skip without credentials/project; the gate test additionally
  requires `SPARTINA_GEE_SMOKE_EXPORT=1`. No fake success is possible.

## 7. Real-run status and remaining blockers

Resolved on 2026-09-30:

1. `earthengine-api==1.7.46` installed in the `spartina-earth` conda
   environment only; real OAuth credentials provisioned by the operator;
   project id supplied via `SPARTINA_GEE_PROJECT` (never hard-coded).
2. Real catalog retrieval VERIFIED (two independent runs, identical
   fingerprints) — 3 L8 / 15 S1 / 12 S2 candidates over the small ROI.

Still open:

1. **Export gate FAILED for the fixed 2020 window**: all three L8 scenes
   have ROI cloud fraction 0.783 / 1.0 / 1.0 > 0.30, so no
   policy-eligible scene exists. No Drive task, GeoTIFF, checksum or
   COMPLETED manifest exists; the export acceptance items are NOT RUN /
   FAILED GATE, not "done". A future attempt must predeclare a different
   window/ROI before inspecting it — it must not edit the policy to
   force a pass.
2. Issue #7 production ROIs (ZJ-HZB / ZJ-SMB / ZJ-YQB) authoritative
   boundaries are still MISSING; the smoke box is not a substitute.
3. Season/window validation, tide handling (PROXY only), and labels/
   GoldSet for Zhejiang remain open (see
   [GEE_TO_ZHEJIANG_HANDOFF.md](../data/GEE_TO_ZHEJIANG_HANDOFF.md)).

Bytes stay out of Git per `.gitignore`; only manifests, the frozen JSON
fixture, code and documents are tracked.

## 8. Out of scope for v1

* Bulk / nationwide exports, model training, rebuilding the legacy
  composite (its exact S1/L8 dates remain UNKNOWN and must not be
  guessed), modifying Pilot-0 split v1 or any TEST artifact, and real
  tide-gauge ingestion.
