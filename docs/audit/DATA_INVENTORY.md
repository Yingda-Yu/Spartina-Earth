# DATA_INVENTORY.md

Inventory of the **incoming legacy data transfer** at
`old datasets/` (top level of the working copy). This folder is
**git-ignored**; bytes are not and must not be committed. This document is
the M0 traceable record of what exists on disk.

- Audit date: 2026-09-27 (read-only inspection; no file moved or modified).
- Total size enumerated: **7.2 GiB**, 55 files (including zero-byte
  ArcGIS `.sr.lock` files).
- Method: pure-Python classic/BigTIFF IFD parser, pure-Python DBF header/
  record parser, `pdftotext`, `unzip -l`, `7z l`, byte/listing inspection.
  GDAL/OGR and rasterio are **not installed** on this host; CRS/dimensions
  below come from GeoTIFF GeoKeys / GDAL sidecar files, not from
  reprojection or pixel reads.
- Evidence labels: **VERIFIED** (independently read from file bytes on this
  host), **OBSERVED** (metadata present, not independently validated),
  **UNVERIFIED** (asserted by filename/manuscript only), **MISSING**
  (searched for, absent), **UNKNOWN** (not knowable from present evidence).

## 1. Asset summary table

Proposed `asset_id` values are identifiers for the JSON manifests to be
created in M1 (schema: `datasets/manifests/schema.json`). They are
**proposals**, not existing records.

| Proposed asset_id | What it is | Key VERIFIED facts | Label tier (see LABEL_INVENTORY) | License |
|---|---|---|---|---|
| `legacy-china-2015-raster-30m` | National binary Spartina distribution raster, 2015 | 45,282x67,077 px; 1 band; uint16; uncompressed BigTIFF; EPSG:32650; 30 m; 6,095,881,341 B | SILVER candidate | UNKNOWN |
| `legacy-china-2020-cmssm-polygons` | National Spartina polygon product "CM-SSM", 2020 | 148,072 polygons; EPSG:32650; fields `Id,name,area`; 9 provinces; 341 MB shp | WEAK (SILVER candidate) | UNKNOWN |
| `legacy-hangzhoubay-2015-dtsp-mask` | Binary mask over Hangzhou Bay, 2015 | 1,292x501 px; 8-bit; EPSG:32651 (GeoKey); ~30 m; VAT 0=631,692 / 1=15,600 px | WEAK | UNKNOWN |
| `legacy-hangzhoubay-2015-l8-sr` | Landsat 8 surface-reflectance stack, 2015 | 1,486x482; 7x uint16 bands `SR_B1..SR_B7`; LZW; CRS GeoKey EPSG:4326 | UNLABELED | USGS/NASA terms presumed; manifest provider UNKNOWN until source confirmed |
| `legacy-hangzhoubay-2015-ndvi` | NDVI raster, 2015 | 1,486x482; float32 | derived | UNKNOWN |
| `legacy-hangzhoubay-2015-s1-vh` | Sentinel-1 VH backscatter, 2015 | 4,456x1,445; float64 | UNLABELED (raw-derived) | UNKNOWN |
| `legacy-hangzhoubay-2015-s1-vv` | Sentinel-1 VV backscatter, 2015 | 4,456x1,445; float64 | UNLABELED (raw-derived) | UNKNOWN |
| `legacy-hangzhoubay-2015-sai` | SAI index raster, 2015 | 1,486x482; float64 | derived / weak-index | UNKNOWN |
| `legacy-zhejiang-2015-featurestack-t1` | GEE-exported 11-band feature stack tile | 7,622x9,984; 11x float32; LZW; EPSG:4326; origin lon 120.5 / lat 30.7; 668 MB | derived (label band presence UNVERIFIED) | UNKNOWN |
| `legacy-zhejiang-2015-featurestack-t2` | Same stack, second tile | 7,622 wide, 2,121 valid rows; 53 MB | derived | UNKNOWN |
| `legacy-fujian-2019..2025-s2` | Sentinel-2 stacks `S2_2019.tif`...`S2_2025.tif` (7 files) | each 669x669; 5x float32; LZW; EPSG:4326; origin lon 121.2 / lat 28.4; ~8.5 MB each | UNLABELED; band identities UNKNOWN | UNKNOWN |
| `legacy-fujian-cmsa-2019..2021` | CMSA polygon labels for the S2 window | 78 / 191 / 105 polygons; EPSG:4326; fields `Area_ha,Id,gridcode` | WEAK | UNKNOWN |
| `legacy-manuscript-cisnet` | PDF draft "...Spatial-Temporal Ensemble Deep Learning" (CISNet) | 7 pp; user is an author; claim ledger in LEGACY_RESULT_AUDIT addendum | - | author-held draft; redistribution right UNKNOWN |
| `legacy-manuscript-multimodal` | PDF draft "Multi-Modal Mapping of Invasive Spartina..." (J. Remote Sensing format) | 12 pp; user is an author | - | same |

## 2. National products under `30mSpartinaChina/`

### 2.1 2015 raster (`...(2015)-data entity/`)

- File: `30m中国互花米草空间分布数据集(2015年)-数据实体.tif`
- **VERIFIED**: BigTIFF (`II+\0`), little-endian; IFD0 dimensions 45,282 (W) x
  67,077 (H); `BitsPerSample=16`, `SamplesPerPixel=1`, `Compression=1`
  (none); GeoKey projected CRS = **EPSG:32650 (UTM zone 50N)**; model
  tiepoint (-345,246.5, 4,341,513.4); pixel scale 30.0 m.
- Sidecars: `.tfw`, `.ovr` (4.4 MB pyramids), `.aux.xml`, `.vat.dbf`,
  `.vat.cpg`, four zero-byte ArcGIS `.sr.lock` files (hostname `DEAN`).
- **VERIFIED** from VAT `.dbf`: one value class, `Value=1`,
  `Count=608,287`. At 30 m this equals **547.46 km2 (54,745.8 ha)** of
  positive pixels. Value 0 is absent from the VAT (GDAL commonly omits
  background); the background convention is therefore OBSERVED, not
  documented.
- Duplicate archive: top-level
  `30m分辨率中国互花米草空间分布数据集(2015年)-数据实体.rar` (665 KB; RAR
  stores the uncompressed TIF in 502 KB - all-zero/extreme compressibility)
  containing the same six files with original timestamps **2020-09-10 /
  2020-09-15**. The folder name calls this a published Chinese data
  product; citation and license are **UNKNOWN -> TODO_CITATION**.

### 2.2 2020 CM-SSM polygons (`2020/CM-SSM/`)

- `CM-SSM.shp` 341 MB (+ shx 1.1 MB, sbn/sbx spatial index, prj =
  **EPSG:32650**, CPG UTF-8, `shp.xml` metadata).
- **VERIFIED** from DBF: **148,072 records**, fields `Id(N6)`,
  `name(C50)` province code, `area(F13)` - unit not declared.
- **VERIFIED** per-province aggregation (sum of `area`; unit UNKNOWN):

  | Province | Polygons | Sum of `area` |
  |---|---:|---:|
  | FJ (Fujian) | 28,619 | 8,125.36 |
  | GD (Guangdong) | 2,082 | 317.33 |
  | GX (Guangxi) | 12,658 | 1,168.55 |
  | HB (Hebei) | 510 | 15.46 |
  | JS (Jiangsu) | 24,180 | 15,482.55 |
  | SD (Shandong) | 9,490 | 1,798.50 |
  | SH (Shanghai) | 24,566 | 18,860.39 |
  | TJ (Tianjin) | 6,203 | 212.01 |
  | ZJ (Zhejiang) | 39,764 | 13,390.84 |
  | **Total** | **148,072** | **59,371.0** |

  If the unit is hectares (UNVERIFIED - the field carries no unit), the
  total is approximately 593.7 km2. HB/TJ presence should be sanity-checked
  against known Spartina range; do not quote the total until the unit is
  proven.
- Provenance **OBSERVED** from `CM-SSM.shp.xml` (ArcGIS metadata):
  original item name `ChinaSP1025.shp`; created 2024-05-22 17:06:15;
  lineage shows per-province OBIA classification
  (`I:\ZXM\SP_XM\OBIA\OBIA_FJ_class_result\...`), dissolve steps in
  `D:\Deep Learning\XMproduct\fj2020\...`, and merges from LAN paths
  (`\\X23OPNA9EJQ8B8L\H\XM\final_result\Whole\...`). No citation, no
  accuracy statement, no producer name beyond machine paths.
- Plausible link (**UNVERIFIED inference**): the multimodal manuscript in
  `Spartina/zhejiang/` states the authors "applied the method of this
  paper to produce a map of the distribution of S. alterniflora at 10-m
  spatial resolution in mainland China in 2020". CM-SSM may be that
  product; confirm before asserting authorship/provenance.

## 3. Hangzhou Bay 2015 stack (`Spartina/HangZhouBay/`)

This is the only folder assembling a **co-registered multi-sensor
experiment package** (L8 + S1 + indices + mask).

- `c201511839DTSP_2.tif` (710 KB): 1,292x501, 8-bit palette, GeoKey
  **EPSG:32651**; tiepoint 309,298.1 E / 3,364,366.8 N; pixel scale
  29.98x29.95 m. VAT: value 0 = 631,692 px; value 1 = 15,600 px
  (approximately **14.0 km2** positive at ~900 m2/px; window ~58.1 km2).
  Class semantics (1 = Spartina?) are implied by folder context,
  **UNVERIFIED**.
- `L8_AllBands_2015.tif` (3.9 MB): 1,486x482; **7 bands, uint16**, band
  descriptions `SR_B1..SR_B7` (VERIFIED in `.aux.xml`; scaled surface
  reflectance, max approximately 25,255); GeoKey EPSG:4326.
- `NDVI_2015.tif`: 1,486x482 float32, same grid.
- `SAI_2015.tif`: 1,486x482 float64, same grid (SAI = Spartina
  alterniflora index per the multimodal manuscript; formula source
  UNVERIFIED).
- `S1_VH_2015.tif` (21 MB) / `S1_VV_2015.tif` (22 MB): 4,456x1,445
  float64 - a **different grid** (~3x denser than the L8 grid);
  pixel-by-pixel co-registration with the L8/NDVI/SAI stack is UNVERIFIED.
  Each has a 3 MB `.ovr`.
- Note: the mask GeoKey (32651) and the L8/S1 GeoKeys (4326) differ;
  overlay work in M1 must reproject explicitly, never assume alignment.

## 4. Zhejiang GEE feature stacks (`Spartina/zhejiang/`)

- `Spartina_2015-0000000000-0000000000.tif` (668 MB): 7,622x9,984;
  **11 bands x float32**; LZW; EPSG:4326; tile origin 120.5 E, 30.7 N.
- `Spartina_2015-0000009984-0000000000.tif` (53 MB): same width/band
  setup, 2,121 rows; origin 120.5 E, 28.0 N. GEE sharded-export naming;
  the two tiles form a ~7,622x12,105 composite covering the Zhejiang
  coast (28.0-30.7 N). Band identities are not in the parsed TIFF tags:
  **UNKNOWN** - enumerate with rasterio/GDAL in M1 before use. Do not
  assume the 11 bands match L8 `SR_B1..B7`.

## 5. `spartinatest/` (Fujian-coast window, ~121.2 E, 28.4 N)

- Sentinel-2 stacks 2019-2025: seven files `S2_2019.tif`...`S2_2025.tif`,
  each 669x669, **5 bands x float32**, EPSG:4326, LZW. Band order/names
  and reflectance scaling: UNKNOWN.
- CMSA shapefiles (EPSG:4326, CPG UTF-8, plus `.fix` files):
  2019 = 78 records (sum `Area_ha` 928.85), 2020 = 191 records (484.57),
  2021 = 105 records (949.24); every record has `gridcode=2`; minimum
  polygon area 0.01 ha (1 m2 slivers). The 2019 to 2020 area drop and
  sliver polygons make these **WEAK** labels requiring topology/QA.
- `CMSA_2020.zip` (58 MB, zip entries dated **2026-01-05**) is a snapshot
  of exactly this folder (all three shapefile sets + seven S2 tifs).

## 6. Documents and non-research files

- **Own manuscripts (drafts; authors include the repository owner):**
  - `Spartina/zhejiang/Spartina_Detection.pdf` - *A Coastal Invasive
    Species Monitoring System Based on Satellite Image and
    Spatial-Temporal Ensemble Deep Learning* (7 pp; introduces **CISNet**;
    Landsat TM/OLI, nine time points 1985-2025; Zhejiang study area;
    Hangzhou Bay figure). Co-author name spelling "Yuling Tang".
  - `Spartina/zhejiang/Journal_of_Remote_Sensing.pdf` - *Multi-Modal
    Mapping of Invasive Spartina alterniflora via Multi-Head Attention
    and Transfer Learning* (12 pp; six study areas: YRDNNR, YNNR, JWNNR,
    SCWHB/Hangzhou Bay, LYB, LZB; 2020; SAI index; OA 87.73-96.39%,
    kappa 0.73-0.94 claimed). Co-author spelling "Yulin Tang".
- Reference PDFs (third-party, not project data): `nature20584.pdf`
  (Pekel et al., surface water), `LiCSBAS_sample_CF.pdf` /
  `...(1).pdf` + `LiCSBAS_sample_CF.tar.gz` (LiCSBAS InSAR),
  `978-3-319-46448-0_7.pdf` (Springer chapter), `Witch-hunt.pdf`.
- Unrelated/non-research items: `CursorSetup-x64-1.6.35.exe` (114 MB
  installer), `QuizInstruction.docx`, `WordResearchPaper.zip` (airline
  coursework docx, 2015/2022), screenshots `channels_visualization.png`,
  `kepler.gl.png`, `Yingda Yu - Geospatial Analysis.png`.
- These files stay where they are (read-only M0); they must not be
  referenced as scientific inputs. Consider relocating/removing them when
  the data library is formalized in M1 (owner decision, not an M0 action).

## 7. Explicit negative findings (searched, absent)

- **No model checkpoints** anywhere under `old datasets/`: no
  `.pt/.pth/.ckpt/.h5/.onnx/.safetensors/.weights` files.
- **No training logs, metric CSVs, confusion matrices, TensorBoard runs.**
- **No GEE scripts or export logs** - GEE provenance is inferred only from
  export-style file names (`Spartina_2015-0000000000-...`).
- **No sample-point tables** behind the manuscripts' claimed sample counts
  (e.g. 2,570 pixels, 15,544 Spartina points).
- **No license files / data-use agreements / readmes** for any EO product.
- No field-UAV/GPS point data, no tide/ancillary tables.

## 8. Re-scan requirement

The folder was described as still transferring when the M0 audit began;
the final enumeration above (55 files, 7.2 GiB) found no partial/temp
files and matches the asset set described by the owner. If new files land
after 2026-09-27, this inventory and `LABEL_INVENTORY.md` must be re-run
before M1 manifest creation. Checksums are **MISSING** (no hashes taken
in M0); manifest creation in M1 must record SHA-256 per asset.
