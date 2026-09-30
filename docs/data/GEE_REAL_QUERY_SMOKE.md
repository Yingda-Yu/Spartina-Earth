# GEE Real Query Smoke — Issue #6 (M1.6 / M1.6b)

Status: **real, authenticated catalog retrieval PASSED for both
predeclared windows; the real Landsat-8 pixel-export gate is FAILED in
BOTH windows (zero policy-eligible L8 scenes in the autumn window AND in
the predeclared summer backup window).** No pixel export occurred; both
are honest `NO_ELIGIBLE_LANDSAT8_SCENE` results, not silent relaxations
of the predeclared rules. The M1.6b closure token is
**`L8_REAL_EXPORT_NOT_OBSERVED_UNDER_PREDECLARED_WINDOWS`**: per the
owner protocol no third date search was made, no threshold was relaxed,
and no Sentinel-2 export was substituted. **Issue #6 remains OPEN; the
real byte-export/provenance chain is NOT YET VERIFIED.**

This document is the tracked human-readable evidence. The machine
evidence is frozen at
[tests/fixtures/gee/real_smoke_catalog_v1.json](../../tests/fixtures/gee/real_smoke_catalog_v1.json)
(30 fully-typed candidate rows + fingerprints, autumn primary window)
and
[tests/fixtures/gee/real_smoke_backup_catalog_v1.json](../../tests/fixtures/gee/real_smoke_backup_catalog_v1.json)
(2 L8 candidate rows + fingerprints, M1.6b predeclared backup window),
replayed offline by `tests/unit/test_gee_real_smoke_fixture.py` and
`tests/unit/test_gee_real_smoke_backup_fixture.py`.

## 1. What ran

* **Action**: metadata-only Earth Engine catalog smoke (no bytes exported
  by this stage); each of the three sensors was retrieved **twice in
  independent calls** to prove determinism.
* **Authenticated run date (UTC)**: 2026-09-30 (frozen snapshot retrieval
  timestamp `2026-09-30T06:44:50Z`; earlier identical-fingerprint double
  retrieval at `06:40:52Z`/`06:40:55Z`).
* **Cloud project**: `project-795fc21c-e217-47f3-adb` (non-secret project
  id, read from `SPARTINA_GEE_PROJECT`; no credential/token material is
  stored in the repository or this document).
* **Software**: `earthengine-api` 1.7.46 in the `spartina-earth` conda
  environment.
* **Driver**: `scripts/data/gee/real_catalog_smoke.py`
  (`run_smoke(sensors, out_dir)`).

## 2. ROI — technical box, NOT an authoritative boundary

* `roi_id`: **HZB_TECH_SMOKE_V1**
* Geometry (EPSG:4326 rectangle): 121.10–121.12 E, 30.30–30.32 N
  (0.02° box, northern Hangzhou Bay coast).
* Geometry SHA-256:
  `b72d475976e4ff3e775defb467ec4a62f880a5df1bc42aa0c0a882be7d9da43f`
* This box is a **plumbing-verification ROI**. It is explicitly **not**
  the Hangzhou Bay authoritative/administrative/ecological boundary. The
  formal Issue #7 three-bay ROIs (ZJ-HZB / ZJ-SMB / ZJ-YQB) still have
  `MISSING` authoritative geometry and provenance — see
  [ZHEJIANG_DATA_PREPARATION_V0.md](ZHEJIANG_DATA_PREPARATION_V0.md).

## 3. Predeclared, fixed query configuration

These parameters were fixed **before** looking at results and were not
edited after inspection:

* Window: `2020-09-01T00:00:00Z` … `2020-11-01T00:00:00Z` (EE `filterDate`
  end is exclusive).
* Target DOY: **275** (≈ 1 October; autumn planning window v0).
* Selection policy `SingleScenePolicy`:
  `min_footprint_coverage=0.99`, `min_valid_pixel_fraction=0.95`,
  `max_cloud_fraction=0.30`, `target_doy=275`.
* No catalog cloud prefilter; **every candidate scene retained**
  (rejected rows carry explicit reasons).
* Sentinel-1 queried **without** mode/polarisation filters so non-IW /
  non-VV-VH scenes would remain visible as rejected candidates.
* No median / mean / mosaic — `best_single_scene` only.

Collections (exact GEE ids):

| Sensor | Collection |
|---|---|
| Landsat 8 | `LANDSAT/LC08/C02/T1_L2` |
| Sentinel-1 | `COPERNICUS/S1_GRD` |
| Sentinel-2 | `COPERNICUS/S2_SR_HARMONIZED` |

## 4. Candidate and eligibility counts (ROI pixel QA)

| Sensor | Candidates | Policy-eligible | Selected |
|---|---:|---:|---:|
| Landsat 8 | 3 | **0** | **0** |
| Sentinel-1 | 15 | 15 | 1 (ASCENDING) |
| Sentinel-2 | 12 | 5 | 1 |

QA is computed **server-side inside EE as pixel counts over the ROI**
(sum reducer with an explicit total-pixel denominator, `unmask(0)`), not
guessed from scene-level metadata. Fractions: total / valid / cloud /
cloud-shadow / cirrus / snow / saturated / clear. Water is treated as
valid (L8 QA_PIXEL water bit is not a defect; S2 SCL class 6 water is
valid).

### 4.1 Landsat 8 — all three rejected (the export gate is closed)

All three scenes are WRS-2 path/row **118/39**, full ROI coverage
(1.0), valid-pixel fraction 1.0, but ROI cloud fraction exceeds 0.30:

| Scene (system:index) | Product id | Acquisition UTC | Catalog CLOUD_COVER | ROI cloud | ROI shadow | ROI clear | Reason |
|---|---|---|---:|---:|---:|---:|---|
| LC08_118039_20200901 | LC08_L2SP_118039_20200901_20200906_02_T1 | 2020-09-01T02:25:33.653000+00:00 | 0.7068 | 0.7833 | 0.3229 | 0.1563 | high_roi_cloud_fraction |
| LC08_118039_20200917 | LC08_L2SP_118039_20200917_20201005_02_T1 | 2020-09-17T02:25:39.673000+00:00 | 0.5943 | 1.0000 | 0.0 (cirrus 1.0) | 0.0000 | high_roi_cloud_fraction |
| LC08_118039_20201003 | LC08_L2SP_118039_20201003_20201015_02_T1 | 2020-10-03T02:25:43.465000+00:00 | 0.8902 | 1.0000 | 0.0 | 0.0000 | high_roi_cloud_fraction |

This is the **real autumn cloud situation over this tiny box**, not a
code defect. Per the predeclared rules the driver refuses with
`NO_ELIGIBLE_LANDSAT8_SCENE`; the window was not widened, the 0.30
threshold was not relaxed, and no cloudy scene was exported and labelled
"selected".

### 4.2 Sentinel-1 — 15 candidates, all ASCENDING; passes kept separate

* 15/15 are IW mode with both VV and VH → all eligible; S1A and S1B both
  present; native ~10 m GRD; relative orbits 69 and 171.
* **ASCENDING: 15 candidates / 15 eligible. DESCENDING: 0 candidates.**
  The two passes are ranked independently and never merged.
* Selected ASCENDING (rank 1):
  `S1A_IW_GRDH_1SDV_20201002T100300_20201002T100325_034616_0407DA_822F`
  — UTC `2020-10-02T10:03:00+00:00`, relative orbit **69**.
* No descending best exists for this window/ROI (recorded as `null`, not
  fabricated).
* **Data-quality note (MISSING evidence)**: GEE returned `null` for the
  S1 `productIdentifier` property on every scene. The table records
  `product_id = "MISSING"` and keeps `system:index` as the identifier;
  no product identifier was invented.

### 4.3 Sentinel-2 — 12 candidates, 5 eligible, one selected

All 12 scenes are MGRS tile **51RUP**, processing baseline **02.14**
(S2A + S2B), and the `MSK_CLDPRB` cloud-probability band is present on
every scene (`cloud_probability_available=true`). Eligible ranking:

| Rank | Scene (system:index) | Date (UTC) | ROI cloud | ROI clear |
|---:|---|---|---:|---:|
| 1 (selected) | `20200905T023549_20200905T024731_T51RUP` | 2020-09-05 | 0.0 | 0.8627 |
| 2 | `20201030T023831_20201030T023833_T51RUP` | 2020-10-30 | 0.0011 | 0.7938 |
| 3 | `20201010T023631_20201010T024205_T51RUP` | 2020-10-10 | 0.0071 | 0.8043 |
| 4 | `20200930T023551_20200930T023909_T51RUP` | 2020-09-30 | 0.1049 | 0.4958 |
| 5 | `20200925T023549_20200925T024420_T51RUP` | 2020-09-25 | 0.1944 | 0.5687 |

Selected product id:
`S2B_MSIL2A_20200905T023549_N0214_R089_T51RUP_20200905T053156`,
acquisition UTC `2020-09-05T02:49:21.773000+00:00`. The other seven
candidates (09-10, 09-15, 09-20, 10-05, 10-15, 10-20, 10-25) exceed the
0.30 ROI cloud threshold and are retained with reasons.

## 5. Determinism and fingerprints

Two independent retrievals produced identical scene-id sets and
identical canonical fingerprints:

* `rerun_identical = true`, `rerun_scene_id_sets_equal = true`.
* **Catalog fingerprint (SHA-256)**:
  `ddf6f158eff85dbc74b7be5f2780319da44cc2910f3ca930917bbc7df6692f28`
* **Selection fingerprint (SHA-256)**:
  `b659c68b0018b09328b61a5cbaf64ad21a282594e81834173815db7bdc9d4f4e`

The fingerprint payloads exclude retrieval-wall-clock timestamps and
derived annotations; they cover stable scene identity, tile/orbit and
the ROI pixel-QA counts (catalog) plus the policy and eligible/selected
sets (selection). The offline unit test recomputes both hashes from the
frozen rows and fails on any silent change to the QA counting or ranking
code.

Optical ranking key (descending): ROI coverage → valid-pixel fraction →
ROI cloud (lower) → ROI shadow (lower) → circular DOY distance to 275 →
acquisition UTC → scene id. SAR ranking uses coverage → valid → season
(then UTC → id) within each orbit pass; cloud/shadow score the neutral
best for SAR.

## 6. Artifacts (bytes git-ignored; fixture tracked)

* `artifacts/gee/real_smoke/candidate_scenes_real_smoke_v1.{parquet,csv,json}`
  — 30 rows, 51 columns; the JSON copy is canonical and keeps rich types,
  the Parquet copy stringifies cross-sensor sentinel columns
  (`NOT_APPLICABLE` / `MISSING`) because a column cannot mix numeric and
  string.
* `artifacts/gee/real_smoke/run_summary_real_smoke_v1.json` — ROI/window/
  collections/policy/counts/S1 pass split/selected scenes/fingerprints.
* `tests/fixtures/gee/real_smoke_catalog_v1.json` — tracked frozen
  evidence used by the no-network regression test.

## 7. Export gate: FAILED (no eligible L8 scene)

The export driver (`scripts/data/gee/real_export_smoke.py`, gated by
`SPARTINA_GEE_SMOKE_EXPORT=1`) was driven to its gate under the real
credentials. It exits:

```
NO_ELIGIBLE_LANDSAT8_SCENE: the predeclared single-scene policy rejected
all 3 L8 candidates, so the export gate is CLOSED ...
```

Consequences recorded honestly:

* **No Earth Engine batch export task was started** (neither the 7-band
  float32 SR file nor the byte VALID file).
* **No Google Drive folder/file, no download, no landed GeoTIFF, no
  SHA-256 of pixels, no GridSpec raster verification, no export manifest
  claiming COMPLETED.** Those acceptance items therefore remain
  **NOT RUN / FAILED GATE** for this fixed window.
* The gate behavior itself is covered by a real integration test
  (`test_real_export_gate_blocks_zero_eligible_l8`), which asserts the
  refusal and asserts that no `.tif`, manifest or task store is created.

The export plumbing is fully implemented and reviewed for when an
eligible scene exists: single source scene (never a composite),
SR_B1..B7 float32 with DN·2.75e-5−0.2 and fill masked (no fake-zero
nodata), separate byte VALID mask (QA_PIXEL clear + QA_RADSAT==0, water
valid), EPSG:32651 with an explicit non-contradictory `crsTransform` and
`fileDimensions` on the 30 m `covering_grid`, atomic `.part` landing,
rasterio grid match, reflectance scaling sanity, SHA-256, full
`GEE_DATA_FACTORY_V1` manifest, and an end-to-end provenance-chain
assertion.

## 8. M1.6b — predeclared seasonal fallback (second, final L8 attempt)

After the autumn gate closure, the owner fixed the next attempt in the
Issue #6 comment "M1.6b closure protocol" (2026-09-30) **before any
backup-window retrieval**: the documented backup seasonal policy
(DOY 152–212, see
[ZHEJIANG_DATA_PREPARATION_V0.md](ZHEJIANG_DATA_PREPARATION_V0.md)),
same ROI, same thresholds, same eligibility/ranking code, Landsat 8 only,
single scene only. This is a predeclared seasonal fallback, not a
data-driven relaxation.

* **Action**: metadata-only L8 retrieval, executed **twice in
  independent calls** (run timestamps `2026-09-30T08:00:32Z` /
  `2026-09-30T08:00:33Z`).
* **Window**: `2020-06-01T00:00:00Z` … `2020-08-01T00:00:00Z`
  (`filterDate` end exclusive); **target DOY 182**.
* **Policy (unchanged)**: `min_footprint_coverage=0.99`,
  `min_valid_pixel_fraction=0.95`, `max_cloud_fraction=0.30`.
* **Collection**: `LANDSAT/LC08/C02/T1_L2` only.
* **Driver profile**: `real_catalog_smoke.py --window-profile backup_v1`;
  gate profile `real_export_smoke.py --window-profile backup_v1`.
* **Counts**: 2 candidates / **0 policy-eligible / 0 selected**.

### 8.1 Both backup L8 candidates rejected by ROI cloud

Both scenes are WRS-2 path/row **118/39** with full ROI coverage (1.0)
and valid-pixel fraction 1.0; the ROI is entirely inside the cloud/cirrus
family on both dates:

| Scene (system:index) | Product id | Acquisition UTC | DOY | Catalog CLOUD_COVER | ROI cloud | ROI cirrus | ROI shadow | ROI clear | Reason |
|---|---|---|---:|---:|---:|---:|---:|---:|---|
| LC08_118039_20200613 | LC08_L2SP_118039_20200613_20200824_02_T1 | 2020-06-13T02:25:01.898000+00:00 | 165 | 0.9772 | 1.0000 | 1.0000 | 0.0000 | 0.0000 | high_roi_cloud_fraction |
| LC08_118039_20200731 | LC08_L2SP_118039_20200731_20200908_02_T1 | 2020-07-31T02:25:20.994000+00:00 | 213 | 0.5977 | 1.0000 | 0.9962 | 0.0140 | 0.0000 | high_roi_cloud_fraction |

ROI pixel totals: 5509 pixels per scene; ROI cloud pixels 5509/5509 on
both dates (QA_PIXEL cloud family: dilated | cirrus | cloud). Snow and
saturation are zero everywhere; this is purely a cloud gate failure.

* **Observation, not an inference (MISSING explanation)**: the 61-day
  window nominally contains four L8 overpasses of WRS 118/39 (16-day
  revisit); the `T1_L2` filtered collection returned exactly the two
  scenes above. Why the other nominal dates are absent from this
  collection/filter response was **not investigated and is UNKNOWN**; no
  third search or collection change was made.
* Determinism: `rerun_identical = true`, `rerun_scene_id_sets_equal =
  true`. **Catalog fingerprint (SHA-256)**:
  `f9a9c0b4241fc0932535c21b408872db8054e62bf2bd4d7ce4de31ac63423109`;
  **selection fingerprint (SHA-256)**:
  `8c2d37cab34a6252b1edfe97cda5552a1a133abb21b1c5ba2990b8e0d8fac14b`.
  Both are pinned in the frozen backup fixture and reproduced offline by
  `tests/unit/test_gee_real_smoke_backup_fixture.py`.

### 8.2 Gate closure and what did NOT happen

Driven to the export gate under real credentials with
`SPARTINA_GEE_SMOKE_EXPORT=1`, the backup profile refuses with
`NO_ELIGIBLE_LANDSAT8_SCENE`
(`test_real_backup_export_gate_blocks_zero_eligible_l8` asserts the
refusal and that no `.tif`, manifest or task store is created).

Outcome: **`L8_REAL_EXPORT_NOT_OBSERVED_UNDER_PREDECLARED_WINDOWS`**.

* **No Earth Engine batch task was started**, no Drive folder/file, no
  download, no GeoTIFF, no SHA-256 of pixels, no GridSpec raster
  verification, no export manifest, no ~500 m sub-ROI export, no
  `datasets/manifests/gee_real_l8_export_smoke_v1.json` (the planned
  tracked manifest name is simply not produced).
* **No third arbitrary date search**, no `cloud <= 0.30` relaxation, no
  ROI move, no manual scene pick, no median/mosaic, no sensor
  substitution.
* Per the owner protocol, a separate Sentinel-2 real export may be
  *proposed* later purely as generic transport/export-pipeline
  validation, but it must not be presented as a substitute for Landsat
  scaling validation without explicit approval. No such S2 export was
  run in M1.6b.
* **Issue #6 stays OPEN**: it closes only after at least one real sensor
  export lands with a complete manifest/provenance chain and precise
  sensor-specific validation claims.
* Combined with section 7, **5 real L8 scenes across 2 predeclared
  windows (3 autumn + 2 summer) all fail the unchanged ROI cloud gate.**

## 9. Known limitations

1. **Zero export evidence** — the L8 cloud reality on this 0.02° box
   closes the gate in both predeclared windows; real byte export is
   NOT YET VERIFIED. Any future attempt must predeclare its window/ROI
   **before** inspecting it; the fixed policy code must not be edited to
   force a pass.
2. One tiny ROI, two fixed 61-day windows in 2020 — no cross-year,
   cross-region or cross-sensor-generation inference is supported.
3. S1 `productIdentifier` is MISSING from GEE responses (pipeline-level);
   only `system:index` identity is evidenced.
4. Tide/inundation is not assessed here; any such field stays PROXY,
   never observed tide.
5. The legacy 2015 Hangzhou composite's exact source scenes remain
   **UNKNOWN**; this smoke does not attempt to reverse-guess them and
   must not be cited as their identification.
6. HZB_TECH_SMOKE_V1 is not an authoritative bay boundary; do not reuse
   it as an Issue #7 production ROI.
7. The absence of two nominal L8 overpass dates from the backup
   collection response is UNVERIFIED (section 8.1); it was not probed,
   in keeping with the no-third-search protocol.

## 10. Reproduce

```bash
conda activate spartina-earth
export SPARTINA_GEE_PROJECT="project-795fc21c-e217-47f3-adb"
# primary autumn window, metadata-only, two independent real retrievals:
python scripts/data/gee/real_catalog_smoke.py
# M1.6b predeclared summer backup, Landsat 8 only, two retrievals:
python scripts/data/gee/real_catalog_smoke.py --window-profile backup_v1 \
    --sensors landsat8
# real integration suite (catalog + honest gate-closure tests, both
# windows; export tests require the explicit operator opt-in):
SPARTINA_GEE_SMOKE_EXPORT=1 pytest -m gee_integration -v
# offline replay of both frozen evidence sets (no credentials/network):
pytest tests/unit/test_gee_real_smoke_fixture.py \
    tests/unit/test_gee_real_smoke_backup_fixture.py -v
```
