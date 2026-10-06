# China external-label intake & byte audit — v1 (M2.4)

Date: 2026-10-06. Status: **AUDIT COMPLETE — bytes verified, rights
restricted, SILVER reference only (GOLD count unchanged at 0).**

This document is the formal intake record for four GEODATA national
30 m Spartina masks (1990, 2000, 2015, 2020) and the NESDC CMSA annual
vector series 2017–2021, delivered by the project owner after the manual
order/purpose flows described in
[CHINA_EXTERNAL_LABEL_ACCESS_ACTIONS.md](../data/CHINA_EXTERNAL_LABEL_ACCESS_ACTIONS.md).
It supersedes the order-blocked / not-audited rows of
`datasets/manifests/china_spartina_label_products_v0.csv` via the new
canonical registry
`datasets/manifests/china_external_label_registry_v1.csv` (supersession
only; the v0 file is retained unchanged for traceability).

## 0. Scope and hard-rule compliance

In scope: file inventory, cryptographic integrity, extraction into
isolated staging, format/CRS/grid/semantic verification, portal
provenance and license, cross-year comparability, lightweight spatial
consistency checks, tier/rights policy, registry, passports, tests.

**Out of scope (not done):** model training; pixel export into the
project; the 303-pair batch; any promotion to GOLD; any redistribution;
change inference from disagreements between maps; calling any external
product "ground truth". No external product is used beyond
analysis/validation as an *external reference product*.

Compliance: source archives under `old datasets/` were not modified,
renamed or deleted; hashes were taken before extraction; extraction went
only to the gitignored `work/intake/staging/`; no payload bytes, rasters,
checkpoints or credentials enter Git; the login/order/JWT flows were not
bypassed (owner delivered the archives through legitimate channels);
every uncertain item is marked `UNKNOWN`, `MISSING`, `TODO_VERIFY` or
`TODO_OWNER_RECORD`; no number here is inferred from an old paper or
draft — areas and counts were recomputed from the delivered bytes.

Machine-readable intermediates (gitignored):
`work/intake/00_raw_inventory.json`, `01_extracted_files.json`,
`02_raster_histograms.json`, `03_cmsa_vector_facts.json`,
`04_cmsa_gridcode_slivers.json`, `05_geodata_grid_facts.json`,
`10_domain_allocation.json`, `11_2020_cell_cooccurrence.csv`.
Tracked outputs: the registry v1 CSV, two family passports under
`docs/audit/source_passports/`, the overlap manifest
`datasets/manifests/china_label_domain_overlap_v1.csv`, the allocator
script `scripts/data/labels/audit_label_domain_overlap.py`, and this
document.

## 1. Raw inventory (six delivered files)

| File | Size (bytes) | SHA-256 (prefix) |
|---|---:|---|
| 1990年…互花米草…-数据实体.rar | 245,971 | `8fb616afccfe26be…` |
| 2000年…-.rar | 606,691 | `c55f5a5019810fb7…` |
| 2020年…-.rar | 695,700 | `c37bffcdfeffb0df…` |
| 30m分辨率中国互花米草…(2015年)-数据实体.rar | 681,048 | `470aa0275adaa264…` |
| 中国大陆2017-2021互花米草CMSA.zip | 6,455,174 | `5876d9780cf581cf…` |
| 2017-2021年中国大陆10 m互花米草数据集.xls | 7,680 | `13b083b14dbbb16a…` |

Full hashes: `work/intake/00_raw_inventory.json`.

## 2. Extraction integrity

* GEODATA archives are RAR5 with a method the system p7zip 16.02 cannot
  read ("Unsupported Method"); extraction used the conda-forge `unrar`
  client (`unrar x -o+`). CMSA extracted with `7z x -y`.
* Result: **zero corrupt, unreadable or duplicate members**; member
  sizes match the archive listings.
* GEODATA per archive: `.tif` (uncompressed tiled BigTIFF, 128×128
  blocks) + `.tfw` + `.tif.aux.xml` + `.tif.ovr` + `.tif.vat.dbf`; the
  2015 archive additionally has `.tif.vat.cpg` (UTF-8).
* CMSA: one folder with 20 files = 5 shapefile sets
  (dbf/prj/shp/shx) for 2017–2021.
* Every extracted member was hashed (`01_extracted_files.json`). The
  2015 extracted TIF (`39a2d535…`, 6.10 GB) is **byte-identical** to the
  pre-existing read-only copy in
  `old datasets/30mSpartinaChina/` — the prior audit's
  `RELATIONSHIP_UNKNOWN` blocker for 2015 is resolved.
* Pre-existing `old datasets/spartinatest/CMSA_2019|2020|2021.*` are
  tiny EPSG:4326 working subsets (78/191/105 features), byte-different
  from the official package, provenance MISSING; they are **not** part
  of this intake and were left untouched.

## 3. GEODATA raster facts (measured from the delivered bytes)

All four are single-band binary masks: positive value `1`,
background/nodata `255`, nominal 30 m pixels. VAT counts were exactly
reproduced by an independent full block-window raster scan.

| Year | dtype | CRS | Width × Height | Positive px | Area (px × 900 m²) | WGS84 bounds (°) |
|---|---|---|---|---:|---:|---|
| 1990 | uint8 | Krasovsky_1940_Albers | 39,337 × 67,187 | 48,628 | 43.7652 km² | 110.33–125.39 E, 21.88–38.43 N |
| 2000 | uint8 | Krasovsky_1940_Albers | 48,709 × 68,485 | 284,927 | 256.4343 km² | 107.64–125.40 E, 21.63–38.42 N |
| 2015 | int16 | EPSG:32650 WGS84 UTM 50N | 45,282 × 67,077 | 608,287 | 547.4583 km² | 108.89–122.93 E, 20.87–39.07 N |
| 2020 | uint8 | Krasovsky_1940_Albers | 43,575 × 70,184 | 577,657 | 519.8913 km² | 108.13–124.21 E, 21.00–38.46 N |

VAT class names: 1990 `CLass_1990='hhmc'`, 2000 `Class_2000='hhmc'`
(pinyin initialism of 互花米草); 2020 `Class_name` = UTF-8 `互花米草`
(console mojibake is a display artefact; bytes decode as UTF-8); 2015
VAT has Value/Count only.

Reported methods/accuracies (portal/papers, **not independently
re-derived**): 1990/2000 Landsat-era OBIA (Mao et al. 2019 *Sensors*
19:2308) with a generic ">90 %" level-1 class-accuracy boilerplate;
2015 Landsat-8 OLI, eCognition 9.2 multiscale segmentation +
object-oriented/SVM + expert visual editing with field samples,
**reported OA 92 %** (Mao et al. 2019; Liu, Mao, Wang 2018 *Remote
Sensing* 10:1933). Image acquisition dates per year remain
`TODO_VERIFY`.

## 4. Grid alignment and cross-year comparability

Even the three Krasovsky-Albers years (1990/2000/2020) are **not
pixel-aligned**: pairwise origin offsets are non-integer pixels
(1990→2000 dx = −9322.79, dy = −7.15 px; 1990→2020 dx = −7557.31,
dy = −564.02 px; 2000→2020 dx = 1765.48, dy = −556.87 px), and extents
and dimensions also differ. The 2015 product uses a different datum and
projection (WGS84 UTM 50N) and requires reprojection.

**Verdict — `NOT_DIRECTLY_COMPARABLE`** for pixelwise work across any
pair, and `NOT_DIRECTLY_COMPARABLE` for area time series across the
projection boundary. After a documented harmonization protocol the
series may be used only as `COMPARABLE_WITH_CAVEATS` (resampling, mixed
pixels, minimum mapping unit). Area figures remain valid only in each
product's own planar convention; year-to-year area differences mix
methods, scale and real dynamics and **must not be presented as change**.

## 5. The 2020 Spartina/mangrove portal contradiction — resolved for the bytes

The 2020 GEODATA portal record is internally contradictory: the title
and archive name say *30 m Spartina 2020*, while the abstract says
*2020 30 m mangrove (红树林) distribution*, carries mangrove keywords,
a sentence about 1980 greater-Pearl-River-Delta mangroves, and a mangrove
citation (Jia et al. 2019). Archive size matches the listing
(679.39 KiB).

Evidence from the delivered bytes: (i) VAT `Class_name` decodes as
UTF-8 `互花米草`; (ii) positive pixels extend to **39.35 N**, with
~13.3 % of positives at 36–42 N — beyond mangrove biogeographic range,
where Spartina occurs; (iii) the spatial pattern matches the
Jiangsu/Shanghai/Zhejiang Spartina coast and is incompatible with a
mangrove map.

**Verdict: `DELIVERED_BYTES_VERIFIED_SPARTINA` + `PORTAL_ABSTRACT_CONFLICT`.**
The product is admitted as a Spartina SILVER reference on byte evidence;
the portal defect stays open. Owner action retained: write to the listed
contact (宋春雨, northeast.data@iga.ac.cn) requesting correction, keep
the reply, and do not silently "fix" the portal record.

## 6. Provenance and rights evidence (captured 2026-10-06)

* GEODATA: National Earth System Science Data Center portal
  (geodata.cn), Black Soil & Wetland sub-center, NEIGAE CAS; online
  order (在线订单获取) with manual approval; platform terms restrict to
  scientific research use and prohibit copying/redistribution without
  written permission; no machine-readable CC license.
  Classification: **RESTRICTED_RESEARCH_ONLY**. CSTRs:
  1990 `17099.11.G195159798810196.20220225.v1`,
  2000 `17099.11.G140184217931452.20220225.v1`,
  2015 `17099.11.G65372070926827.20200918.v1`,
  2020 `17099.11.G254533427778392.20220225.v1`. Order IDs/approver/
  exact license snapshots: `TODO_OWNER_RECORD`. The 2000 keywords carry
  minor mangrove boilerplate (the abstract is Spartina).
* CMSA: DOI `10.12199/nesdc.ecodb.mon.2026.013`, CSTR
  `15732.11.nesdc.ecodb.mon.2026.017`; NESDC landing page declares
  **CC BY-NC 4.0** with open sharing under a purpose statement and
  required attribution (NESDC + Li, Tian, Li et al. 2024,
  *Int. J. Remote Sens.* 45:3172–3199, DOI
  `10.1080/01431161.2024.2343136`). Producers 李夏荣/田金炎
  (tjyremote@126.com); generated 2024-05-02, published 2026-04-20 v1.
* CM-SSM 2020: record unchanged — Zenodo CC-BY-4.0 vs NESDC mirror
  CC-BY-NC-4.0 remains a **SOURCE_LICENSE_CONFLICT**; analysis/
  validation only pending contributor clarification (see
  [cm_ssm_2020_zenodo.json](source_passports/cm_ssm_2020_zenodo.json)).

## 7. CMSA 2017–2021 vector facts and metadata defects

All five years are present in the delivered archive — the year
inventory is **COMPLETE**. The XLS time-range field "2017–2020" is a
stale text defect (title, abstract and archive all cover 2017–2021).
The XLS "GeoTIFF / 38 MB" format text is also wrong: the entities are
shapefile vectors; the zip is 6,455,174 bytes (the v0 manifest's
"6.1561 GB" was a unit error, corrected in v1).

| Year | Features | Invalid (self-int.) | `gridcode=0` n / km² | Positive area (code 2, km²) | All-feature km² |
|---|---:|---:|---:|---:|---:|
| 2017 | 5,341 | 125 | 49 / 0.89 | 494.69 | 495.59 |
| 2018 | 5,985 | 162 | 53 / 2.56 | 504.31 | 506.87 |
| 2019 | 6,097 | 186 | 62 / 6.96 | 532.99 | 539.95 |
| 2020 | 8,914 | 499 | 50 / 2.80 | 571.35 | 574.15 |
| 2021 | 6,295 | 253 | 18 / 0.11 | 586.51 | 586.63 |

All years: EPSG:32650 Polygon/MultiPolygon, fields
`Id, gridcode, Area_ha, geometry`; `Area_ha` exactly equals geometry
area / 1e4; zero null/empty geometries; zero duplicate geometries;
extent ≈ 108.8–124.3 E, 21.0–41.0 N (mainland coast). Caveats recorded:
`Id` is not a unique key (duplicate-value rows per year); 0–22 slivers
< 100 m² per year; the meaning of `gridcode=0` features is **UNKNOWN**
(probably low-confidence/uncertain; `TODO_VERIFY` with producers; they
are excluded from positive totals and from all analyses). The polygons
are vectorised from 10 m model outputs and must not be described as
"10 m geometric resolution" vector data.

## 8. Lightweight spatial consistency against the v1 W10 domain

Allocation of mapped area onto the immutable 10 km coastal-cell grid
(script: `scripts/data/labels/audit_label_domain_overlap.py`; tracked
summary: `datasets/manifests/china_label_domain_overlap_v1.csv`).

| Product | KEEP | PROVISIONAL | OUTSIDE_GRID | EXCLUDE |
|---|---:|---:|---:|---:|
| GEODATA 1990 | 43.762 km² (48,624 px) | 0.004 km² (4 px) | 0 | **0** |
| GEODATA 2000 | 256.431 km² (284,923 px) | 0.004 km² (4 px) | 0 | **0** |
| GEODATA 2015 | 528.656 km² (587,396 px) | 0.253 km² (281 px) | 18.549 km² (20,610 px) | **0** |
| GEODATA 2020 | 485.215 km² (539,128 px) | 0.684 km² (760 px) | 33.992 km² (37,769 px) | **0** |
| CMSA 2017 | 458.386 km² | 0.028 km² | 34.870 km² | **0** |
| CMSA 2018 | 465.041 km² | 0.014 km² | 37.796 km² | **0** |
| CMSA 2019 | 492.940 km² | 0.071 km² | 38.431 km² | **0** |
| CMSA 2020 | 530.499 km² | 0.063 km² | 39.120 km² | **0** |
| CMSA 2021 | 540.251 km² | 0.158 km² | 44.383 km² | **0** |
| CM-SSM 2020 | 572.586 km² | 0.565 km² | 18.608 km² | **0** |

No product maps Spartina inside any `EXCLUDE` cell — a positive
consistency signal for the published products and the domain mask. All
OUTSIDE_GRID elements lie within ~7.1 km of the corridor edge at
31.1–38.1 N (Jiangsu–Shandong open tidal flats); none is an inland
anomaly. This is expected corridor-width boundary behaviour and is
logged for the W5/W10/W20 width sensitivity, not treated as product
error.

**2020 three-product diagnostic (cell level, spatial agreement only —
not accuracy):** 274 W10 cells contain all three products, 103 exactly
two, 126 exactly one, 2,816 none. In exactly-one cells GEODATA is the
sole product in 72 (coarse-pixel boundary/expansion signature); in
exactly-two cells the pairs are dominated by CMSA+CM-SSM (85/82), i.e.
GEODATA omits small patches the finer products capture. Spearman
correlation of per-cell mapped area: CMSA vs CM-SSM 0.875; GEODATA vs
either ≈ 0.75. This motivates the controlled 2020 cross-product study
design (`docs/research/EXTERNAL_REFERENCE_PRODUCT_2020_STUDY_DESIGN_V1.md`).

## 9. Tier and usage policy

| Product | Tier | GOLD use | Analysis | Validation | Training labels | Redistribution |
|---|---|---|---|---|---|---|
| GEODATA ×4 | SILVER | **false** | yes | external reference only | no (reference-only policy) | no (RESTRICTED_RESEARCH_ONLY) |
| CMSA ×5 | SILVER | **false** | yes | external reference only | no (reference-only policy) | CC BY-NC 4.0 (attribution, NC) |
| CM-SSM 2020 | SILVER | **false** | yes | external reference only | no (reference-only policy) | UNKNOWN (license conflict) |

Publication by an authority, 10 m or sub-meter inputs, or reported high
accuracy does not confer GOLD: none of these products ships a
field/UAV/expert-verified label chain under our control, and none has
been independently validated by us. The project GOLD count stays at
zero (see `docs/data/SPARTINA_GOLDSET_PROTOCOL.md`).

## 10. Canonical registry and supersession

`datasets/manifests/china_external_label_registry_v1.csv` is the
canonical register (10 entities, 28 fields) with explicit status tokens:

* `acquisition_status`: `ACQUIRED` for the 9 GEODATA/CMSA entities
  (owner-delivered through legitimate order/purpose channels; JWTs not
  stored), `DOWNLOADED` for CM-SSM.
* `provenance_status`: `VERIFIED`; `VERIFIED_BYTE_IDENTICAL_LOCAL`
  (GEODATA 2015); `CONFLICT_PORTAL_METADATA` (GEODATA 2020, bytes
  separately verified as Spartina).
* `semantic_status`: `VERIFIED_SPARTINA` everywhere.
* `license`: `RESTRICTED_RESEARCH_ONLY`, `CC-BY-NC-4.0`,
  `SOURCE_LICENSE_CONFLICT`.
* `label_tier=SILVER`, `gold_use=FALSE` everywhere.

The v0 manifest is retained unchanged; each v1 row carries the v0 id in
`supersedes`. Nothing is deleted or overwritten.

## 11. Anomaly register and interpretation

| Observation | Classification |
|---|---|
| 1990→2000→2015→2020 area steps (43.8 → 256.4 → 547.5 → 519.9 km²) | MIXED METHODOLOGY_EFFECT + SCALE_EFFECT + possibly real change; **not** a change measurement |
| CMSA annual drift 494.7 → 586.5 km² | transfer-learning/year-specific pipeline + scale effects; not change |
| GEODATA 2020 portal mangrove abstract | PORTAL METADATA DEFECT (bytes verified Spartina); owner to request correction |
| CMSA XLS "2017–2020" and "GeoTIFF/38 MB" | stale/inaccurate metadata text; archive content complete and vector |
| CMSA `gridcode=0` features | UNKNOWN semantics; excluded; TODO_VERIFY |
| Invalid/self-intersecting polygons (both vector families) | data-quality caveat for geometric ops; make-valid/buffer(0) required before area work |
| Corridor-edge OUTSIDE_GRID elements | domain-width boundary effect; feed width-sensitivity analysis |

## 12. Remaining open items (owner)

1. `TODO_OWNER_RECORD`: geodata.cn order IDs, approver, approval
   timestamps and exact license-text snapshots for the four orders.
2. `TODO_OWNER_RECORD`: NESDC purpose-statement text, holder and
   timestamp for the CMSA download (never the JWT).
3. Request correction of the GEODATA 2020 portal abstract/keywords;
   retain the written reply.
4. Report the CMSA stale time-range field and format error to NESDC;
   ask producers for the meaning of `gridcode=0` and per-year
   validation metrics (`TODO_VERIFY`).
5. `TODO_VERIFY`: GEODATA image acquisition dates and per-year
   validation behind the ">90 %" statement; the 2020 production method.

## 13. Acquisition posture

All ten identified national external-label entities for the GEODATA /
CMSA / CM-SSM families are now physically present and byte-audited.
Acquisition is therefore **COMPLETE for the identified family set**,
with three qualifications that do not block analysis: restricted GEODATA
rights (research use, no redistribution), the open GEODATA-2020 portal
metadata conflict, and the CM-SSM license conflict. GOLD promotion is
not part of this milestone and remains at zero.
