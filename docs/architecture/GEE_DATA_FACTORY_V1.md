# GEE EO Data Factory v1 — Issue #6 (M1.6)

Status (updated 2026-09-30 after M1.6b): **real catalog retrieval
VERIFIED** against Earth Engine with project
`project-795fc21c-e217-47f3-adb` (L8/S1/S2 over HZB_TECH_SMOKE_V1, double
retrieval deterministic in both predeclared windows). **REAL BYTE EXPORT:
NOT VERIFIED** — the real Landsat-8 export gate is GATE-FAILED in BOTH
predeclared windows: all 3 autumn L8 scenes AND both predeclared summer
backup L8 scenes exceed the unchanged 0.30 ROI cloud threshold
(`L8_REAL_EXPORT_NOT_OBSERVED_UNDER_PREDECLARED_WINDOWS`); no bytes were
exported, no third search was made. Evidence:
[GEE_REAL_QUERY_SMOKE.md](../data/GEE_REAL_QUERY_SMOKE.md). Nothing here
performs a nationwide download; the first real run targets one small
Hangzhou Bay ROI and is exercised only via `pytest -m gee_integration`.

Update 2026-10-01 (M1.6c): **the generic real byte export chain is
VERIFIED ON SENTINEL-2** (one frozen single S2 scene -> two COMPLETED
Drive tasks -> atomic landing -> SHA256 -> GridSpec/dtype/band checks ->
complete GEE_DATA_FACTORY_V1 manifest; closure token
`PASS_WITH_SCOPED_SENSOR_CAVEAT`). Landsat real byte export stays
NOT OBSERVED / NOT VERIFIED (M1.6b token unchanged); Sentinel-1 real
byte export is NOT YET VERIFIED.

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
| `driveio.py` | Google Drive download of finished exports using the same Earth Engine OAuth credentials (Drive scope included); `download_latest(name_prefix)` skips trashed files. Real-verified M1.6c; constructs `Credentials(token=None, ...)` because `ee.oauth.get_credentials_arguments()` carries no access token. |
| `provenance.py` | `git_context`, `runtime_environment`, `sha256_file`, `raster_grid_info` + `assert_grid_matches`, `reflectance_sanity` (per-band percentiles + un-scaled-DN screen), `valid_mask_info` (exactly 1 uint8 band, values subset of {0,1}), `reflectance_sanity_masked` (stats on VALID==1 pixels only, per-band valid-pixel counts must match the mask), and `assert_provenance_chain` — the end-to-end source-scene → landed-file hard assertion. |
| `grid.py` | `GridSpec` (crs, 6-tuple affine transform, width/height, pixel size, bounds), pixel-snapped covering grids, stream constructors, anti-upsampling guard. |
| `tide.py` | `TideProxyRecord` — `method="PROXY"` mandatory, `gauge_observed=False` mandatory. |
| `export.py` | `ExportRequest` (now carries grid, exact source scenes, stream), `NullExporter`, atomic `land_bytes()` with mandatory SHA-256. |
| `tasks.py` | JSON-backed `TaskStore` (deterministic IDs, bounded retry, full error history, `state_history` of every GEE poll incl. repeated states, `get_by_request_id`, crash resume), `TaskRunner`, lazy `EarthEngineBatchBackend`. |
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
Since M1.6c every GEE poll is additionally appended to a persisted
`state_history` (UTC + state, repeated states kept), and the S2 driver
resumes a stored COMPLETED task instead of creating a duplicate export
when the process died after completion (it re-verifies terminal state
with GEE, requires the Drive artefact, and records a resume poll).

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
* `tests/unit/test_gee_real_smoke_backup_fixture.py` — offline replay of
  the 2 frozen L8 rows from the predeclared M1.6b backup window:
  2/0/0 counts, both scenes rejected solely for ROI cloud, unchanged ROI
  hash, and both backup fingerprints recomputed.
* `tests/unit/test_gee_s2_real_smoke_offline.py` — offline M1.6c
  coverage: deterministic +/-250 m / 10 m export GridSpec (51x51),
  frozen SCL {4,5,6,11} policy identity with the catalog code, persisted
  poll state history (incl. backward compat with pre-history stores),
  binary-mask accept/reject, masked-reflectance stats and DN-scale
  rejection, and the `SPARTINA_GEE_SMOKE_EXPORT` gate.
* `tests/unit/test_gee_interfaces_mock.py` (M0 contracts) remains green.
* `tests/integration/test_gee_integration.py` — real init smoke; real
  per-sensor candidate-provenance queries (S1 null `productIdentifier`
  accepted as MISSING evidence); the real catalog driver evidence test
  (double retrieval, fingerprints, exact S1/S2 selections); the real
  M1.6b L8-only backup-window evidence test (2 scenes, 0 eligible,
  double-retrieval deterministic); and operator-opt-in tests proving
  the export gate **closes with `NO_ELIGIBLE_LANDSAT8_SCENE`** for BOTH
  windows and creates no tif/manifest/task store. All skip without
  credentials/project; the gate tests additionally require
  `SPARTINA_GEE_SMOKE_EXPORT=1`. No fake success is possible.
  M1.6c adds a metadata-only live replay of the frozen S2 selection
  (`test_s2_selection_replays_frozen_fixture_live`, no exports) and an
  opt-in test that only RE-AUDITS the recorded S2 manifest/lock/landed
  bytes (`test_s2_real_byte_evidence_bundle_recorded`) — it never
  re-exports, honouring "do not repeat a successful export".

## 7. Real-run status and remaining blockers

Resolved on 2026-09-30:

1. `earthengine-api==1.7.46` installed in the `spartina-earth` conda
   environment only; real OAuth credentials provisioned by the operator;
   project id supplied via `SPARTINA_GEE_PROJECT` (never hard-coded).
2. Real catalog retrieval VERIFIED (two independent runs, identical
   fingerprints) — 3 L8 / 15 S1 / 12 S2 candidates over the small ROI.

Still open:

1. **GENERIC REAL BYTE EXPORT VERIFIED ON SENTINEL-2 (M1.6c,
   2026-10-01).** One frozen single S2 scene (S2B, 2020-09-05,
   T51RUP), native 10 m B2/B3/B4/B8 float32 /10000 + separate uint8 SCL
   VALID, deterministic ~500 m export ROI: two real Drive tasks reached
   COMPLETED with full READY->RUNNING->COMPLETED poll histories;
   GeoTIFFs landed atomically, passed the exact GridSpec/dtype/band
   checks, masked reflectance sanity and both provenance assertions
   (`PASS_WITH_SCOPED_SENSOR_CAVEAT`). See
   [GEE_REAL_QUERY_SMOKE.md](../data/GEE_REAL_QUERY_SMOKE.md) section
   11 and `datasets/manifests/gee_real_s2_export_smoke_v1.json`.
2. **LANDSAT REAL BYTE EXPORT: NOT OBSERVED / NOT VERIFIED — export gate
   FAILED in both predeclared windows.** Autumn (2020-09-01..11-01, DOY 275): three L8
   scenes, ROI cloud 0.783 / 1.0 / 1.0. Predeclared M1.6b summer
   fallback (2020-06-01..08-01 end-exclusive, DOY 182, L8 only): two L8
   scenes, ROI cloud 1.0 / 1.0. No policy-eligible scene exists in
   either window; no Drive task, GeoTIFF, checksum or COMPLETED
   manifest exists (`L8_REAL_EXPORT_NOT_OBSERVED_UNDER_PREDECLARED_
   WINDOWS`); the L8 byte acceptance items are NOT RUN / FAILED GATE,
   not "done"; the S2 closure above is generic-pipeline evidence only,
   never a substitute for Landsat scaling/availability validation. No
   third date search was made and the 0.30 threshold was not relaxed. A
   future attempt must predeclare its window/ROI before inspecting it —
   it must not edit the policy to force a pass.
3. **SENTINEL-1 REAL BYTE EXPORT: NOT YET VERIFIED.** The S2 closure
   makes no claim about SAR export behaviour or bytes.
4. Issue #7 production ROIs (ZJ-HZB / ZJ-SMB / ZJ-YQB) authoritative
   boundaries are still MISSING; the smoke box is not a substitute.
5. Season/window validation, tide handling (PROXY only), and labels/
   GoldSet for Zhejiang remain open (see
   [GEE_TO_ZHEJIANG_HANDOFF.md](../data/GEE_TO_ZHEJIANG_HANDOFF.md)).

Bytes stay out of Git per `.gitignore`; only manifests, the frozen JSON
fixture, code and documents are tracked.

## 8. Out of scope for v1

* Bulk / nationwide exports, model training, rebuilding the legacy
  composite (its exact S1/L8 dates remain UNKNOWN and must not be
  guessed), modifying Pilot-0 split v1 or any TEST artifact, and real
  tide-gauge ingestion.
