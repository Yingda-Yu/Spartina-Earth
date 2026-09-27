# Manuscript inventory — owner-authored and other PDFs (M1.1)

Extraction method: `pdftotext -layout` only (no OCR). Text copies live in
`artifacts/audit/manuscript_text/` (git-ignored). Every quantitative claim
below is a **manuscript statement**, status UNVERIFIED unless an executed
reproduction exists; none do in M1.1.

## M1 — `Spartina/zhejiang/Spartina_Detection.pdf`

- **Title (as printed):** "A Coastal Invasive Species Monitoring System
  Based on Satellite image …" (CISNet; 7-page draft, two-column layout).
- **Authors (as printed):** Yingda Yu¹, **Yuling Tang**², Shiqi Xu²,
  Shuyang Xu*; Wenzhou-Kean University, Wenzhou, China (kean.edu mails).
- **Model/method:** CISNet = Multi-Attention residual network with
  transfer learning (MMD domain adaptation + entropy minimization),
  IoU-based loss, "redundant cutting and splicing" post-processing;
  epochs 100, batch size 8; baselines Decision Tree, SVM, CNN-UNet,
  MAR-NET.
- **Sensors claimed:** Landsat 5 TM + Landsat 8 OLI.
- **Temporal claim:** 27 original Landsat images, nine time points
  **1985, 1990, 1995, 2000, 2005, 2010, 2015, 2020, 2025**, WRS path/row
  **119/39**, 3 dates per year (Table II).
- **Regions:** Hangzhou Bay (Fig. 3), Wenzhou river mouths (Fig. 5),
  Sanmen Bay (Fig. 4); Zhejiang Province.
- **Labels claimed:** per-year binary labels (S. alterniflora vs
  background); Table I sample pixels 1995: 15,544 / 899,050;
  2005: 16,540 / 979,984; 2015: 12,347 / 887,966.
- **Transfer experiments (Table III):** leave-one-year-out SD→TD among
  1995/2005/2015.
- **Reported metrics (printed):**
  - Table IV (year not legibly captured, TODO_VERIFY): SVM
    IoU 53.78 / P 60.93 / R 58.20 / F1 59.53; U-Net 58.66 / 66.12 /
    63.34 / 64.70.
  - Table V (2005): SVM 51.89 / 60.02 / 57.41 / 58.69; U-Net 56.23 /
    64.89 / 61.36 / 63.07.
  - Table VI (2015): SVM 48.12 / 56.40 / 52.89 / **62.59**; U-Net
    53.76 / 61.34 / 59.72 / **64.52**.
- **Internal contradictions found in text extraction:**
  1. Table VI F1 arithmetic: SVM F1 implied by P/R =
     2·56.40·52.89/(56.40+52.89) = **54.59**, printed **62.59**
     (CONTRADICTED). U-Net implied = **60.52**, printed **64.52**
     (CONTRADICTED). Tables IV/V rows are arithmetically consistent
     (59.53 and 58.69/63.08 within rounding).
  2. Text: "Most images were acquired between March and May, during the
     peak growing season"; Table II lists only **August–October** dates
     for all years (CONTRADICTED, phenology statement).
  3. Table II labels the 2015 scenes "TM"; Landsat 5 TM was retired in
     November 2011, so 2015 data cannot be TM (sensor mislabel; the
     on-disk file is named `L8_AllBands_2015.tif`, bands SR_B1..B7).
- **On-disk evidence linked:** only
  `old datasets/Spartina/HangZhouBay/L8_AllBands_2015.tif`
  (SR_B1..B7), plus NDVI/SAI/S1 and one mask
  `c201511839DTSP_2.tif`. The other 8 time points, the 27 original
  scenes, 1995/2005/2020/2025 labels, Wenzhou/Sanmen data, training
  code, checkpoints and prediction maps are **not present**
  (MISSING_EVIDENCE).

## M2 — `Spartina/zhejiang/Journal_of_Remote_Sensing.pdf`

- **Title (as printed):** "Multi-Modal Mapping of Invasive Spartina
  alterniflora via Multi-Head Attention and Transfer Learning"
  (12-page draft; author form/template pages appended).
- **Authors (as printed):** Yingda Yu¹, Jiaqi Xuan², **Yulin Tang**²,
  Jiaqi Tian* (Nanjing University / NUS address string), Shuyang Xu*;
  Wenzhou-Kean University.
- **Methods/claims:** SAI (Spartina alterniflora index) for Sentinel-2
  MSI L2A; multi-head attention network; transfer learning across
  regions/datasets; SVM and existing-product comparisons; application
  to Landsat-8; national 2020 mapping.
- **Sensors claimed:** Sentinel-2 (10 m; key window: senescence
  November–February + peak period), Sentinel-1, Landsat-8 (30 m);
  platform Google Earth Engine.
- **Study areas (6):** YRDNNR (Yellow River Delta, Shandong), YNNR
  (Yancheng, Jiangsu), JWNNR (Jiuduansha, Shanghai), SCWHB (south coast
  of Hangzhou Bay, Zhejiang), LYB (Luoyuan Bay, Fujian), LZB (Lianzhou
  Bay, Guangxi).
- **Samples:** visual interpretation on Google Earth Pro imagery;
  "70% of the samples (i.e., **2,570 pixels**) … training", 30% test
  (total ≈ 3,671 pixels, derived — TODO_VERIFY against Table 2).
- **Reported results:** OA **87.73%–96.39%**, kappa **0.73–0.94**
  (abstract-level ranges; per-area table not yet extracted,
  TODO_VERIFY); "OA of SAI … and SVM is not much different".
- **National claim:** "a map of the distribution of S. alterniflora at
  10-m spatial resolution in mainland China in 2020".
- **On-disk evidence linked:** SAI exists as a band/file in the
  Hangzhou bundle and in the two Zhejiang 11-band stacks
  (`SR_B1..B7,VV,VH,NDVI,SAI`). No S2 imagery for the six areas, no
  sample table, no GEE asset id, no national map file is explicitly
  identified; `CM-SSM.shp` (lineage item `ChinaSP1025.shp`) is a
  **candidate** for the national 2020 product but the link is
  UNCONFIRMED (no path/asset reference in extracted text; no figure
  output present). All per-area metrics, code, checkpoints:
  MISSING_EVIDENCE.

## Other files in the transfer (not owner Spartina manuscripts)

| File | Appraisal from bytes/name only |
|---|---|
| `978-3-319-46448-0_7.pdf` | Springer book chapter PDF (unrelated subject; UNKNOWN relevance) |
| `LiCSBAS_sample_CF.pdf` + `.tar.gz` (66 MiB) + duplicate `(1).pdf` | LiCSBAS InSAR tutorial materials; byte-duplicate PDF confirmed by SHA-256 |
| `nature20584.pdf` | Nature article PDF (9.0 MB; content not audited; unrelated transfer content) |
| `Witch-hunt.pdf` | unrelated PDF (6.9 MB) |
| `WordResearchPaper.zip` | 3 unrelated `.docx` ("Airlines"/"script"/"Analysis" Word tutorial files, 2015/2022) |
| `QuizInstruction.docx` | unrelated course file |
| `CursorSetup-x64-1.6.35.exe` | Windows installer (120 MB) found inside the evidence tree; **not executed**, hash recorded; relevance UNKNOWN |
| `*.png` (3) | screenshots (channels_visualization, kepler.gl, Geospatial Analysis) — plausibly project-related, provenance UNKNOWN |

These non-Spartina files are preserved untouched per the read-only
policy; they must not be cited as research evidence.
