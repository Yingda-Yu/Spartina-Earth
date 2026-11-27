# LEGACY_RESULT_AUDIT.md

Audit of claims found in the legacy Spartina prototype (now under
[`../../legacy/`](../../legacy/)). Per the M0 rules, **a number appearing
in old code or an old draft is not evidence**. A claim is `VERIFIED` only
when raw evidence exists and it can be (or has been) reproduced.

Status vocabulary (closed set):

- **VERIFIED** — raw evidence present and reproduced/reproducible.
- **UNVERIFIED** — asserted or implied; no raw evidence available to check.
- **CONTRADICTED** — source inspection contradicts the claim.
- **MISSING** — the artifact/result the claim would require was searched
  for and not found.

> **Scope note.** Rows 1-14 audit the **tracked legacy repository** as it
> existed on `main` when the M0 reboot started (snapshot in
> `docs/audit/raw/`). The separately transferred, git-ignored
> `old datasets/` folder (real EO rasters, vector products, two manuscript
> drafts) is audited in rows 15-20 below and in
> [DATA_INVENTORY.md](DATA_INVENTORY.md) /
> [LABEL_INVENTORY.md](LABEL_INVENTORY.md).

## Claim ledger

| # | Claim | Source file | Claimed value | Raw evidence found? | Reproducible? | Status | Notes |
|---|---|---|---|---|---|---|---|
| 1 | Binary CNN classification performance (accuracy/IoU/etc.) | `2 CNN Set Up.py` | none reported anywhere (5 epochs, binary cross-entropy) | No logs, no metric table, no manuscript | No | MISSING | `model.fit(...)` result never recorded; no claimed value exists to verify. |
| 2 | Trained CNN artifact `spartina_model.h5` | `2 CNN Set Up.py` | file written after training | No `.h5` on server | No | MISSING | Also note: only the `spartina` class folder is ever populated; `other/` is created but never filled, so a meaningful binary classifier could not have been trained by this script as written. |
| 3 | Number of images used to train the CNN | `1 Image capture.py`, `2 CNN Set Up.py` | scraper clicks ≤50 thumbnails, downloads ≤10; split 80/20 of whatever exists | No `spartina_images/` directory on server | No | UNVERIFIED | Code caps download at 10 (`image_urls[:10]`); any larger number quoted elsewhere would be unsupported. |
| 4 | Segmentation performance of the U-Net (IoU/F1/Precision/Recall) | `3 U-NET.py` | none reported | No logs, no checkpoint, no dataset | No | MISSING | No evaluation code at all; only a per-epoch training loss print. |
| 5 | "U-Net" architecture as a functioning segmentation model | `3 U-NET.py` | standard U-Net, 3→1 channels, BCEWithLogits, 10 epochs | Source code itself | Not runnable as committed | CONTRADICTED | (a) `images, masks` used at module level are never defined; (b) decoder blocks receive only the previous block's output — encoder features are never cropped/concatenated, so the defining U-Net skip connections are absent; (c) same transform is applied to image and mask including ImageNet normalization, which corrupts masks. |
| 6 | COCO polygon annotation set exists | `4/5/8/9/10 *.py` | `D:\Spatina Test\cocojson.json` | JSON not on server; no record of category list/counts | No | MISSING | Windows-local path; number of images, annotations, and category names unknown. |
| 7 | Dataset split 70/15/15 train/val/test | `5 data set preparatioin.py` | 0.70 / 0.15 / 0.15 image-level split after `random.shuffle` | Source code itself | Reproducible only if the missing images/JSON reappear, but invalid under current rules | UNVERIFIED | Random **image-level** split with no spatial grouping → spatial leakage risk; **prohibited** by `benchmarks/spartinashift/SPEC.md` even if data is recovered. |
| 8 | Masks rasterize the Spartina polygons correctly | `5 data set preparatioin.py` | polygons filled with value 255, PNG masks | Source code itself | Not checkable without images/JSON | UNVERIFIED | Rasterization logic is simple fillPoly; coordinate validity depends on the padded-coordinate script (`9`) whose bbox shift ignores padding parity; polygon x/y shifts are computed per-point and look superficially consistent but are untested. |
| 9 | All images padded/resized to 2048×1367 | `7 image adjust.py`, `9 coco json adjust.py` | fixed canvas 2048×1367, black border | Source code itself | Reproducible given the missing image folder | UNVERIFIED | Integer division computes equal top/bottom borders; odd deltas leave final images not exactly 2048×1367 (canvas never asserted). Downstream model input is 224×224 anyway (`2`), so pipeline intent is itself unclear. |
| 10 | Mask-building script (`11 mask build.py`) | `11 mask build.py` | none | File is 0 bytes | No | MISSING | Empty file. |
| 11 | Defined study region / ROI (geography, year, sensor) | entire legacy set | none stated | No GeoJSON/Shapefile/bbox/config anywhere | No | MISSING | Images were Google Images web results, not georeferenced EO scenes; no acquisition year, region, or sensor metadata exists. |
| 12 | Earth Engine usage or assets | entire legacy set | none | No `ee` imports, no asset IDs, no scripts | No | MISSING | No GEE footprint in legacy. |
| 13 | Old manuscript / result figures | repository-wide | none | No `.docx/.tex/.pdf/result-figures` tracked or on disk | No | MISSING | Nothing to cross-check numbers against. |
| 14 | Project identity line in the old README | `README.md` (now `legacy/README.original.md`) | "An Open ESG Program for Long-term Monitoring of Coastal Biological Invasion" | File present | Yes | VERIFIED | This is a mission statement, not a scientific result; no metric claim. |

## Tally over the 14 rows

| Status | Count |
|---|---|
| VERIFIED | 1 (row 14 — a tagline, not a result) |
| UNVERIFIED | 4 (rows 3, 7, 8, 9) |
| CONTRADICTED | 1 (row 5) |
| MISSING | 8 (rows 1, 2, 4, 6, 10, 11, 12, 13) |

**Quantitative experimental results (IoU, Precision, Recall, F1, accuracy,
area estimates): 0 found, 0 verified.** Nothing in the legacy material can
be cited as a Spartina result in a new manuscript.

## Special-report answers (also surfaced in the M0 acceptance report)

Scoped to the **tracked legacy repo** (rows 1-14): no labels, no ROI, no
GEE assets, no checkpoints, no manuscripts. After the `old datasets/`
transfer was inspected (2026-09-27), the server-wide picture changes:

- **Real past Spartina labels?** **YES, in `old datasets/` only** - a
  national 30 m 2015 raster (L1), a 148,072-polygon 2020 national product
  CM-SSM (L2), a Hangzhou Bay binary mask (L3), and small CMSA polygon
  sets for 2019-2021 (L4-L6). All enter at WEAK / SILVER-candidate tier;
  see [LABEL_INVENTORY.md](LABEL_INVENTORY.md). The tracked legacy COCO
  JSON remains MISSING.
- **Real ROI / study areas?** **YES** - Hangzhou Bay (2015 L8+S1+index
  stack), Zhejiang coast (GEE feature stacks, 28.0-30.7 N), a
  Fujian-coast window (~121.2 E, 28.4 N; S2 2019-2025), and national
  extents. The multimodal draft names six study areas (YRDNNR, YNNR,
  JWNNR, SCWHB, LYB, LZB); their coordinate/sample tables are MISSING.
- **Real EO data?** **YES, derived composites/stacks only** - no raw
  scene archives; GEE export provenance is inferred from file names.
- **GEE scripts / asset information?** Still **MISSING** - no scripts,
  export logs, or asset IDs anywhere.
- **Old checkpoints?** Still **MISSING** - no
  `.pt/.pth/.h5/.ckpt/.onnx/.safetensors` in the repo or the transfer.
- **Old manuscripts?** **YES, two draft PDFs** authored by the repository
  owner (rows 15-20). All of their quantitative claims are UNVERIFIED,
  and one result table is arithmetically CONTRADICTED (row 17).

## Implications for M1+

1. Treat the project as starting from zero verified EO evidence; recovered
   legacy data would enter as **WEAK** labels pending re-validation, and
   must not be split randomly.
2. The 2048×1367 padding / 224×224 CNN pipeline has no geospatial basis and
   should inform nothing about the new EO data engine.
3. If the original COCO JSON is recovered, audit provenance, region, year,
   and image acquisition source before assigning a label-quality tier.


---

## Addendum (2026-09-27): claims in two manuscript drafts found in `old datasets/`

Source files: `old datasets/Spartina/zhejiang/Spartina_Detection.pdf`
(7 pp draft; CISNet; Landsat, nine time points 1985-2025; Zhejiang) and
`old datasets/Spartina/zhejiang/Journal_of_Remote_Sensing.pdf` (12 pp
draft; multi-head attention + transfer learning; six study areas; 2020).
Both list the repository owner as an author. Text was extracted with
`pdftotext`; no raw runs, logs, predictions, or sample tables exist on the
server to back any number below.

| # | Claim | Source | Claimed value | Raw evidence found? | Status | Notes |
|---|---|---|---|---|---|---|
| 15 | Existence/authorship of two manuscript drafts | PDFs on disk | two drafts, owner among authors | Files present | VERIFIED (existence only) | Draft/version status, venue, and co-author name spelling differ between files ("Yuling" vs "Yulin" Tang); bibliographic details UNKNOWN. |
| 16 | CISNet trained/evaluated on Landsat TM/OLI at nine time points 1985-2025 in Zhejiang | Spartina_Detection.pdf, Tables I-II; image dates listed (e.g. 08/15/1985...) | nine epochs 1985...2025; claimed Spartina points 15,544/16,540/12,347 (1995/2005/2015) vs background ~0.9-0.98 M | No imagery exports, point tables, code version, splits, seeds, or logs on server | UNVERIFIED | No 1985/1990/2000/2010 raw data anywhere in the transfer; the claimed temporal span cannot currently be reproduced. Extreme background/positive imbalance stated but handling not verifiable. |
| 17 | CISNet comparison metrics (Tables V-VI: IoU/Precision/Recall/F1 for DecisionTree, SVM, U-Net, WET-Net, MAR-Net, CIS-Net, years 2005 and 2015) | Spartina_Detection.pdf Tables V-VI | e.g. 2015 CISNet IoU 66.18, P 72.31, R 70.47, F1 71.38 | No predictions/labels; and the table is internally inconsistent | **CONTRADICTED** (arithmetic), otherwise UNVERIFIED | From the paper's own P/R, F1 must equal 2PR/(P+R): 2015 SVM (56.40, 52.89) gives 54.59, but the table prints 62.59; 2015 U-Net (61.34, 59.72) gives 60.52, but prints 64.52. The 2005 rows are internally consistent. A table that fails its own arithmetic in 2 of 6 rows cannot be quoted without re-derivation from raw outputs. |
| 18 | SAI/multi-head method performance across six study areas (2020) | JRS draft text/results | OA 87.73%-96.39%, kappa 0.73-0.94; 70% of 2,570 sample pixels used for training | No sample coordinates, per-area tables recovered into machine-readable form, no code/run | UNVERIFIED | Per-area OA values and confusion matrices are not extractable as data from the draft text seen in M0; sampling design (pixel, not spatial) would fail the current spatial-split rules regardless. |
| 19 | A 10 m S. alterniflora map of mainland China for 2020 was produced by the paper's method | JRS draft (conclusions) | national 10 m map, 2020 | CM-SSM polygon product (148,072 features, EPSG:32650) exists in the transfer and may be this map | UNVERIFIED (link OBSERVED only) | Vector product carries no resolution tag and no accuracy statement; ArcGIS metadata shows OBIA + dissolve/merge lineage (`ChinaSP1025.shp`, 2024-05-22). Confirm authorship/method match before treating as the manuscript's product. |
| 20 | "Over 34,000 hectares by 2007" and other background statistics | Spartina_Detection.pdf line citing reference [3] | 34,000 ha (by 2007) | Literature citation, not an own result | N/A (third-party claim) | Track with `TODO_CITATION`; not a Spartina-Earth result and not counted in the claim tally. |

**Revised tally (rows 1-20, excluding row 20 which is a cited third-party
statistic):** VERIFIED 2 (row 14 tagline; row 15 file existence only -
neither is a scientific result); UNVERIFIED 7 (rows 3, 7, 8, 9, 16, 18,
19); CONTRADICTED 2 (rows 5, 17); MISSING 8 (rows 1, 2, 4, 6, 10, 11, 12,
13 remain MISSING **for the tracked repo**; their subject matter is partly
present in `old datasets/` per the special-report section above).

**Quantitative Spartina results verified against raw evidence: still 0.**
