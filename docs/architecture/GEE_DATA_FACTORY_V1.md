# GEE EO Data Factory v1 — Issue #6 (M1.6)

Status: **code + mocked tests complete; real exports BLOCKED_BY_AUTH** on
this server (no `earthengine-api`, no GEE credentials at build time).
Nothing here performs a nationwide download; the first real run targets
one small Hangzhou Bay ROI and is exercised only via
`pytest -m gee_integration`.

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

## 4. Quality metadata

* Optical: catalog cloud fraction (CLOUD_COVER / CLOUDY_PIXEL_PERCENTAGE),
  Landsat per-pixel clear decision (fill, dilated cloud, cirrus, cloud,
  shadow, snow excluded; Clear bit required; `QA_RADSAT == 0`; water
  allowed), S2 SCL clear classes plus optional cloud-probability mask.
* ROI coverage: footprint intersection fraction annotated server-side;
  pixel-valid fraction is attached by the raster QC pass and stays
  `None` until computed (never guessed).
* Sentinel-1: orbit direction, relative orbit number, platform, IW mode,
  polarization, nominal resolution; `angle` band available for incidence
  statistics.

## 5. Async execution semantics

`TaskStore` persists PENDING/ENQUEUED/RUNNING/COMPLETED/FAILED with
attempt count, bounded `max_attempts`, timestamped error records and
deterministic task IDs (`uuid5` of the request id — re-submitting the
same request raises rather than duplicating). A crashed process resumes
every non-terminal task via `TaskRunner.resume()`; a FAILED backend poll
with attempts remaining re-enqueues with the stored spec. The GEE
backend translates `READY/RUNNING/COMPLETED/FAILED/CANCELLED`.

## 6. Testing

* `tests/unit/test_gee_data_factory.py` (20 tests, standard library +
  optional sklearn-style deps; runs on system Python 3.10): grids, QA
  bit decoders, SCL decoding, S1 property mapping, candidate-table
  invariants, PROXY tide enforcement, task retry/resume/persistence,
  checksum landing, manifest guards, lazy-`ee` source scan,
  BLOCKED_BY_AUTH behaviour.
* `tests/unit/test_gee_interfaces_mock.py` (M0 contracts) remains green.
* `tests/integration/test_gee_integration.py` — real init smoke, a real
  L8 small-ROI candidate-provenance query, and an operator-opt-in tiny
  export; all skip without credentials
  (`SPARTINA_GEE_SMOKE_EXPORT=1` additionally gates bytes). No fake
  success is possible.

## 7. Current blockers (this server)

1. No GEE credentials (`GOOGLE_APPLICATION_CREDENTIALS`,
   `EE_SERVICE_ACCOUNT_JSON`, `~/.config/earthengine/*` all absent).
2. `earthengine-api` not installed in either Python environment.

Therefore real small-ROI export status is **BLOCKED_BY_AUTH**, not
"done". Once credentials are provisioned outside Git: install the
`gee` extra, run `pytest -m gee_integration`, then drive one small ROI
through the pipeline and commit only its manifest/candidate table (bytes
stay out of Git per `.gitignore`).

## 8. Out of scope for v1

* Bulk / nationwide exports, model training, rebuilding the legacy
  composite (its exact S1/L8 dates remain UNKNOWN and must not be
  guessed), modifying Pilot-0 split v1 or any TEST artifact, and real
  tide-gauge ingestion.
