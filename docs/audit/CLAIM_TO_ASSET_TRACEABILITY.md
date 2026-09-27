# Claim → asset traceability matrix (M1.1)

Rule: a claim is traceable only if each link exists on disk:
`source scene → preprocessing → label → model → checkpoint →
inference config → output`. This matrix audits the two owner
manuscripts against the 82 transferred files. Status vocabulary:
**PRESENT** (bytes exist), **PARTIAL** (some links), **MISSING_EVIDENCE**,
**CONTRADICTED** (conflicting evidence within/near the claim).

## A. CISNet manuscript (`Spartina_Detection.pdf`)

| Claim | Required evidence | On disk | Status |
|---|---|---|---|
| 27 Landsat scenes, 1985–2025, path/row 119/39 | 27 source scenes (or GEE export provenance) | only `HangZhouBay/L8_AllBands_2015.tif` (one 7-band composite) | MISSING_EVIDENCE (26 scenes) |
| Nine time-point labels (1985…2025), Hangzhou/Wenzhou/Sanmen | 9-year label rasters per region | one Hangzhou 2015 mask `c201511839DTSP_2.tif` (0/1, 15,600 px) | MISSING_EVIDENCE (labels for other years/regions) |
| Table I sample counts | sample/pixel lists or masks | no sample table; 2015 mask positives = 15,600 ≠ 12,347 printed | UNVERIFIED — counts do not match the only available mask (see §D) |
| CISNet training (100 epochs, batch 8) | code, config, seed | none anywhere in tree | MISSING_EVIDENCE |
| Model checkpoints | `.pt/.pth/.ckpt` | zero checkpoint files in 82 assets | MISSING_EVIDENCE |
| Tables IV–VI metrics | predictions + eval script + split | none | UNVERIFIED; Table VI F1 CONTRADICTED by arithmetic (54.59 vs 62.59; 60.52 vs 64.52) |
| "Most images March–May" | Table II dates | Table II lists Aug–Oct only | CONTRADICTED |
| 2015 sensor = TM | sensor metadata | on-disk file is Landsat-8 (`L8_AllBands_2015`, SR_B*), TM impossible in 2015 | CONTRADICTED / TODO_VERIFY |
| Baselines (DT/SVM/U-Net/MAR-Net/CNN-UNet) | code/scripts | none | MISSING_EVIDENCE |
| Figures 3–5 image/label panels | rendered source images/labels | partial: 2015 Hangzhou inputs only; no Wenzhou/Sanmen data | PARTIAL |

## B. Multi-Head Attention / SAI manuscript (`Journal_of_Remote_Sensing.pdf`)

| Claim | Required evidence | On disk | Status |
|---|---|---|---|
| SAI index on Sentinel-2 L2A | S2 L2A inputs + SAI code | SAI exists as a derived band on **Landsat-grid** stacks (`SAI_2015.tif`; zhejiang stacks); the formula/code is not in the tree | PARTIAL; provenance UNCONFIRMED |
| 6 study areas, 2020 | S1/S2/L8 imagery per area | none for YRDNNR/YNNR/JWNNR/LYB/LZB; only Hangzhou/Zhejiang 2015-era data | MISSING_EVIDENCE (5 areas) |
| 2,570 training pixels / 70:30 | sample point table | none | MISSING_EVIDENCE |
| OA 87.73–96.39%, kappa 0.73–0.94 | confusion matrices per area, code | none | UNVERIFIED (abstract ranges only) |
| SAI vs SVM comparison | SVM scripts/results | none | MISSING_EVIDENCE |
| Multi-head attention model, transfer learning | code, checkpoint, config | none | MISSING_EVIDENCE |
| National 10 m 2020 distribution map | map file + GEE asset/reference | `30mSpartinaChina/2020/CM-SSM/CM-SSM.shp` (148,072 polygons; lineage `ChinaSP1025.shp`, 2024-05-22 ArcGIS OBIA workflow) | CANDIDATE ONLY — name/date/method do not yet prove identity; UNCONFIRMED |
| Application to Landsat-8 | L8 SAI outputs | `SAI_2015.tif` on the L8 geographic grid (1486×482) | PARTIAL (file exists, producing script/parameters missing) |
| Phenology windows Nov–Feb etc. | composite date metadata | none of the rasters carry acquisition/composite dates in tags | MISSING_EVIDENCE |

## C. Data products asserted by dataset packaging (not papers)

| Asset | Assertion (from name/sidecar) | Evidence | Status |
|---|---|---|---|
| 2015 national raster | "30 m China Spartina distribution 2015" | independent windowed recompute: 608,287 px of value 1, EPSG:32650, 30 m → **547.4583 km²**; matches VAT count 608,287 | product-internal value VERIFIED; publisher/method/license UNKNOWN; nationwide single-UTM-zone area distortion TODO_VERIFY (geodetic) |
| CM-SSM 2020 | "2020 China Spartina" polygons | 148,072 polygons, 59,370.98 ha field sum vs 593.710 km² computed (ratio exactly 10,000 → hectares); 2,402 self-intersecting rings; 100,455 features <100 m² | geometry/unit VERIFIED; mapping method/provenance UNKNOWN beyond ArcGIS XML lineage; quality issues documented |
| Zhejiang 2015 stacks (2 tiles) | 11-band fused stacks | bands verified `SR_B1..B7,VV,VH,NDVI,SAI`, float32, EPSG:4326, ~30 m grid, lon 120.54–122.59, lat 27.46–30.72 | structure VERIFIED; export script/date/cloud handling UNKNOWN |
| Fujian S2 2019–2025 | annual S2 composites | identical 669×669 EPSG:4326 ~10 m grids; bands `B4,B3,B2,NDVI,NDWI`; no date/Cloud bands | structure VERIFIED; actual acquisition dates/cloud masks MISSING_EVIDENCE |
| CMSA 2019–2021 labels | annual polygon labels | fields `Area_ha,Id,gridcode`; geodetic area ≈ field×~9,960 (hectares); 78/191/105 features | geometry VERIFIED; labeling method/provenance UNKNOWN |

## D. Specific traceability finding — the Hangzhou 2015 mask vs Table I

The only label in the tree (`c201511839DTSP_2.tif`) contains 15,600
positive pixels. Table I prints **12,347** S. alterniflora sample pixels
for 2015. These numbers do not match; possible explanations (crop,
sampling, different label version, or different region split) are all
**unconfirmed**. The mask therefore cannot be used as the paper's test
truth without resolving its provenance (see
`docs/audit/LABEL_TIER_REVIEW.md`, item J-1).

## E. Chain elements absent everywhere

Search of all 82 assets found **no**: model checkpoints, training logs,
GEE scripts, sample/ground-truth tables, prediction rasters, configs or
seeds. Neither manuscript's quantitative result is currently
reproducible from this repository.
