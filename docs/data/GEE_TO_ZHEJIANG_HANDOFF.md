# GEE Factory → Zhejiang Data Production Handoff (Issue #6 → #7)

Scope: state the **M1.6 GEE Data Factory v1** in terms a future
**M2.1 / Issue #7 (Zhejiang three-bay data preparation)** can safely
consume. This document plans only — **no Issue #7 batch production has
started**, no nationwide/bay-wide export has run, and no model training
is implied.

## 1. What is real and verified today

| Capability | State | Evidence |
|---|---|---|
| Lazy GEE connectors (L5/7/8/9, S1, S2) | Verified code; L8/S1/S2 exercised live | `src/spartina/data/gee/` |
| Real authenticated Initialize (project from `SPARTINA_GEE_PROJECT`) | VERIFIED (`ee.Number(1)=1`) | `pytest -m gee_integration` |
| Real metadata catalog, all candidates retained | VERIFIED (30 scenes, fixed ROI/window) | [GEE_REAL_QUERY_SMOKE.md](GEE_REAL_QUERY_SMOKE.md) |
| Server-side ROI pixel-QA counts (valid/cloud/shadow/cirrus/snow/saturated/clear) | VERIFIED | `pixelqa.counts_*` |
| Deterministic predeclared selection + fingerprints | VERIFIED across two live retrievals in BOTH windows (autumn + M1.6b backup) | fingerprints in §5/§8 of the smoke doc |
| SAR pass separation (ASCENDING/DESCENDING) | VERIFIED (15 ascending / 0 descending) | frozen fixture |
| Predeclared M1.6b summer backup window, L8 only | VERIFIED metadata — 2020-06-01..08-01, DOY 182, 2 scenes, double-run identical | [GEE_REAL_QUERY_SMOKE.md](GEE_REAL_QUERY_SMOKE.md) §8 |
| Export chain code (Drive → atomic land → grid/reflection/sha256 → manifest → chain assertion) | Implemented + reviewed; **not yet exercised with pixels** | `real_export_smoke.py`, `provenance.py` |
| One real L8 pixel export | **NOT VERIFIED — FAILED GATE in both predeclared windows**: 0/3 autumn (ROI cloud 0.78/1.0/1.0) and 0/2 summer backup (ROI cloud 1.0/1.0); token `L8_REAL_EXPORT_NOT_OBSERVED_UNDER_PREDECLARED_WINDOWS`; Issue #6 OPEN | NO_ELIGIBLE_LANDSAT8_SCENE |
| Authoritative three-bay ROI geometries (ZJ-HZB/ZJ-SMB/ZJ-YQB) | NOT VERIFIED — still MISSING | [ZHEJIANG_DATA_PREPARATION_V0.md](ZHEJIANG_DATA_PREPARATION_V0.md) |
| GOLD labels / GoldSet for the bay ROIs | NOT VERIFIED — no GOLD labels exist | [SPARTINA_GOLDSET_PROTOCOL.md](SPARTINA_GOLDSET_PROTOCOL.md) |

## 2. Supported inputs and their semantics

* **Stream L (30 m native)**: `LANDSAT/LT05/C02/T1_L2`,
  `LT07/C02/T1_L2`, `LC08/C02/T1_L2`, `LC09/C02/T1_L2`. Surface
  reflectance scaling **DN·2.75e-5 − 0.2**; fill masked (never a fake
  zero); QA uses QA_PIXEL plus QA_RADSAT; water valid. Do not call a
  30 m product "10 m" — `assert_no_forced_upsampling` raises otherwise.
* **Stream H optical (10 m native)**: `COPERNICUS/S2_SR_HARMONIZED`,
  ÷10000 scaling, SCL QA, `MSK_CLDPRB` present in this era/region
  (availability flag is recorded per scene).
* **Stream H SAR (native ~10 m GRD)**: `COPERNICUS/S1_GRD`, IW + VV/VH
  required for eligibility, values already in dB (**never apply
  10·log10 again**), ASCENDING and DESCENDING ranked separately.
  Observed ingestion reality: `productIdentifier` can be null →
  recorded MISSING, `system:index` retained; do not fabricate ids.
* **Composites**: forbidden for the first product per ROI/time — the
  policy is `NONE_BEST_SINGLE_SCENE` with an explicit ranking. A future
  compositing step needs its own predeclared design and provenance.
* **Tide**: PROXY-only fields; never label anything as observed tide.

## 3. What a future production job inherits

* Fixed dual grids (`grid.py`): 30 m Landsat stream with an
  anti-upsampling hard guard, and 10 m Sentinel stream; every export
  carries a 6-tuple transform, dimensions and bounds that are verified
  against the landed raster.
* Full candidate table (rejected rows + reasons), explicit selected
  scene(s), and canonical SHA-256 fingerprints so reruns are
  reproducible and auditable.
* Resumable JSON `TaskStore` (deterministic uuid5 task ids, bounded
  retries, full error history), atomic `.part` landing with mandatory
  SHA-256, Drive download under the same OAuth credentials.
* The `GEE_DATA_FACTORY_V1` manifest + `assert_provenance_chain`:
  source scene → UTC → product id → selection/processing config →
  COMPLETED task → fixed grid → landed file re-hash → project/code/
  environment. A manifest cannot silently claim an unverified export.
* Frozen regression evidence
  (`tests/fixtures/gee/real_smoke_catalog_v1.json`,
  `tests/fixtures/gee/real_smoke_backup_catalog_v1.json`) that locks the
  QA-counting and ranking behaviour offline for both predeclared windows.

## 4. Blockers that must be resolved before Issue #7 production

1. **Authoritative ROI geometry**: ZJ-HZB / ZJ-SMB / ZJ-YQB boundaries
   are MISSING with no traced provenance
   ([ZHEJIANG_DATA_PREPARATION_V0.md](ZHEJIANG_DATA_PREPARATION_V0.md)).
   The 0.02° HZB_TECH_SMOKE_V1 plumbing box must never be promoted to a
   production ROI. Each ROI needs a real source, date and license.
2. **First real pixel export is unproven (Issue #6 OPEN)**: the gate
   closed on ROI cloud cover in BOTH predeclared windows — 0/3 autumn
   (2020-09-01..11-01) and 0/2 in the documented summer backup
   (2020-06-01..08-01, DOY 182). The predeclared fallback is therefore
   exhausted; outcome token
   `L8_REAL_EXPORT_NOT_OBSERVED_UNDER_PREDECLARED_WINDOWS`, no third
   search made. Before trusting the Drive/GeoTIFF path at scale, one
   eligible L8 scene must pass the entire chain under a NEW, explicitly
   approved and **predeclared** window/ROI (chosen before inspection),
   producing a tracked manifest and verified checksums. A Sentinel-2
   real export may be proposed only as generic transport-pipeline
   validation and must not be presented as Landsat scaling validation.
3. **Season/window validation**: planning assumes primary DOY 260–305
   with a DOY 152–212 backup and same-season cross-year comparisons;
   these are hypotheses until validated with real per-year availability
   (the v0 availability matrix uses MISSING/UNKNOWN, not interpolation).
   First evidence at this one ROI in 2020: BOTH windows yielded zero
   L8-eligible scenes, which weakens (but does not disprove) the
   assumed summer-backup availability — more ROIs/years are required.
4. **Cloud-free L8 frequency**: this small coastal box showed 0/3 clean
   L8 scenes in Sep–Oct 2020 AND 0/2 in Jun–Jul 2020 (all five scenes
   ROI-cloud 0.78–1.0), whereas S2 had 5/12 eligible in autumn. Bay-
   scale L8 yield may be lower; per-year/per-ROI eligibility statistics
   are required before promising dense Stream L time series.
5. **Tide/inundation**: no observed-tide source; keep PROXY semantics.
6. **Labels/GoldSet**: no GOLD labels exist for these ROIs; follow
   [SPARTINA_GOLDSET_PROTOCOL.md](SPARTINA_GOLDSET_PROTOCOL.md); legacy
   and index-derived products are at most SILVER/WEAK, never ground truth.
7. **Rights/licensing**: derived Zhejiang products must not be
   redistributed before ownership and licensing are confirmed.

## 5. Recommended M2.1 startup sequence (planning only — do NOT execute here)

1. Freeze authoritative geometries + provenance for the three ROIs
   (replace MISSING entries under `docs/data/rois/`).
2. Both predeclared smoke windows are now exhausted (0/3 autumn, 0/2
   summer backup). Predeclare and obtain explicit approval for a NEW
   small window/ROI **before viewing results** to clear the single-scene
   L8 export gate; run the full manifest/provenance chain once and
   archive the tracked manifest. Any S2 export in the interim is
   transport validation only, not an L8 scaling substitute.
3. Generate metadata-only availability (no pixels) per ROI/year/sensor
   from 1985/1990→2026, keeping MISSING/UNKNOWN/NOT_ASSESSED states.
4. Aggregate per-year eligibility statistics (candidate/eligible counts
   and ROI QA fractions) to choose windows from evidence.
5. Only then plan any pixel exports, beginning with the smallest ROI,
   Stream L and H separately, with hard volume caps and GPU-independent
   QA. Every step needs explicit user approval; M0 constraints (no bulk
   GEE download, no large GPU work) remain until lifted in writing.

## 6. Explicit non-goals carried forward

* No nationwide export, no 30→10 m upsampling, no median-composite
  first product, no reverse-guessing of the 2015 legacy composite
  source scenes (remain UNKNOWN), no Pilot-0 split/TEST changes, no
  foundation-model work (AnySat/Prithvi/SatMAE/SpartinaFM) as part of
  this handoff.
