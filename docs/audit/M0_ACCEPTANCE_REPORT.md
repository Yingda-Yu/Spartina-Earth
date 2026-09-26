# M0 Acceptance Report - Spartina Earth repository reboot

- Date: 2026-09-27
- Executor: autonomous M0 pass per the 28-section reboot specification
- Branch: `reboot/spartina-earth-m0` (created from `main`; **not pushed**)
- Rule reminders honored: audit before modify; legacy never deleted; no
  fabricated data/results; spatially-disjoint splits; no large files or
  secrets in Git; no GPU training; no GEE downloads; no model downloads.

## 1. Current branch

`reboot/spartina-earth-m0`, tracking nothing locally; remote
`https://github.com/Yingda-Yu/Spartina-Earth.git` unchanged.

## 2. git status

Clean working tree. `old datasets/` (7.2 GiB), `.trae/skills/`, IDE state,
caches, rasters, archives, and checkpoints are git-ignored.

## 3. Changed/new files vs `main`

Before this report: **116 paths changed, 5,298 insertions, 1 deletion** -
100 added (A), 15 pure renames (R100: 12 legacy `.py` + 3 `.drawio`),
1 modified; plus 7 tracked `.idea/*` files removed from the index (kept on
disk). Largest tracked blob is 40 KB. No raster/archive/checkpoint bytes
are tracked.

## 4. Repository tree (tracked content, condensed)

```
AGENTS.md  README.md  RESEARCH_CONTEXT.md  LICENSE  CITATION.cff
CONTRIBUTING.md  CODE_OF_CONDUCT.md  DATA_LICENSE.md  THIRD_PARTY_LICENSES
.gitignore  .editorconfig  .pre-commit-config.yaml  pyproject.toml
benchmarks/spartinashift/SPEC.md
configs/{data,eval,experiment,model,train}/  (+ README)
datasets/manifests/schema.json  (+ README)
docs/
  architecture/EO_DATA_ENGINE.md
  audit/{REPOSITORY_BASELINE,LEGACY_RESULT_AUDIT,DATA_INVENTORY,
         LABEL_INVENTORY,M0_ACCEPTANCE_REPORT}.md  raw/
  experiments/EXPERIMENT_STANDARD.md
  models/{SPARTINAFM_DESIGN,BASELINES}.md
  project/issues/ (README + M0-01, M1-01..M1-07 drafts)
  research/{SCIENTIFIC_QUESTIONS,HYPOTHESES,PUBLICATION_MAP}.md
  system/{SERVER_INVENTORY,GPU_POLICY}.md
integrations/spartinaguard/README.md
papers/{benchmark,dataset,flagship,recurrence}/
legacy/ (12 .py + 3 .drawio + README + README.original; unmodified)
scripts/system/probe.py (+ audit/data/eval/train dirs, README)
src/spartina/
  data/gee/{auth,catalog,collections,quality,export,manifest}.py
  data/sensors/registry.py  data/manifests/validator.py
  data/{harmonization,storage,tiling}/
  evaluation/splits.py  labels/__init__.py
  models/{adapters,baselines,heads,spartinfm}/  training/  inference/  utils/
tests/{smoke,unit,integration}/  (+ README)
```

## 5. Legacy file inventory (preserved verbatim under `legacy/`)

`image_collection/1 Image capture.py`;
`classification/2 CNN Set Up.py`;
`segmentation/3 U-NET.py`;
`segmentation/11 mask build.py` (empty file);
`annotations/4 coco json process.py`, `8 coco json information.py`,
`9 coco json adjust.py`, `10 image show.py`;
`preprocessing/5 data set preparatioin.py`, `6 image size test.py`,
`7 image adjust.py`; `play.py`;
diagrams `Spartina.drawio`, `Spatina Net.drawio`, `未命名绘图.drawio`;
original README retained as `legacy/README.original.md`.

## 6. Data assets found (see DATA_INVENTORY.md for evidence)

| Asset | VERIFIED essence |
|---|---|
| China 2015 national raster | 45,282x67,077, uint16, EPSG:32650, 30 m; positives 608,287 px = 547.46 km2 |
| CM-SSM 2020 polygons | 148,072 features, EPSG:32650, 9 provinces, `area` sum 59,371 (unit UNVERIFIED); OBIA lineage 2024-05-22 |
| Hangzhou Bay 2015 | binary mask (1,292x501, EPSG:32651, 15,600 positive px ~14.0 km2); L8 SR 7-band uint16 stack; S1 VV/VH float64 (different grid); NDVI/SAI |
| Zhejiang 2015 stacks | two GEE-export tiles, 11x float32, EPSG:4326, 28.0-30.7 N; band names UNKNOWN |
| Fujian window | S2 2019-2025, 669x669, 5x float32; CMSA polygons 2019/20/21 |
| Documents | two own manuscript drafts (CISNet; multimodal); unrelated reference PDFs and non-research files listed |

## 7. Label assets found (see LABEL_INVENTORY.md)

L1 national 2015 raster = **SILVER candidate, ingest as WEAK**
(citation/license missing); L2 CM-SSM = **WEAK** (SILVER candidate);
L3 Hangzhou Bay mask = WEAK (class semantics undocumented);
L4-L6 CMSA 2019-2021 = WEAK (only `gridcode=2`, 1 m2 slivers, odd year
changes); L7 SAI = weak index feature, not a label; L8/L9 manuscript
sample points = **MISSING**; L10 legacy COCO JSON = **MISSING**.
No GOLD (field/UAV) labels exist.

## 8. Legacy-claim tally

Tracked legacy rows 1-14 + manuscript rows 15-20 (row 20 is a cited
third-party statistic and is excluded): **VERIFIED 2** (old tagline;
existence of two draft PDFs - neither is a scientific result),
**UNVERIFIED 7**, **CONTRADICTED 2** (U-Net code lacks skip connections;
CISNet Table VI F1 for 2015 SVM/U-Net fails its own P/R arithmetic),
**MISSING 8** (scoped to the tracked repo; their subject matter partly
exists in `old datasets/`).
**Quantitative Spartina results verified against raw evidence: 0.**

## 9. Real host configuration (probe.py, 2026-09-27)

- CPU: Intel Xeon Gold 6248R class, 96 logical CPUs; RAM 503.5 GiB
  (466 GiB available observed)
- Storage: `/data` 7,391 GiB total, 2,755 GiB free
- GPU: **10x NVIDIA RTX 3090 24 GB**; driver 580.159.03 / CUDA 13.0
  (nvcc 11.5 also installed)
- GPU occupancy at audit: cards 1, 2, 4, 8 largely free; **card 9 at
  100% util and card 0 holding 12.6 GB (other projects)** - nvidia-smi
  pre-flight and the 3-GPU project cap remain mandatory
- Python 3.10.12; torch 2.5.1+cu118 importable, CUDA available, 10 devices
- Dev tools installed user-site for M0 verification: pytest 9.1.1,
  ruff 0.16.9, mypy 2.3.1; GDAL/rasterio NOT installed (M1)

## 10. pytest

`27 passed, 1 skipped` (the single skip is the opt-in `gee_integration`
test that requires real GEE credentials). Raw log:
`docs/audit/raw/2026-09-27_pytest.txt`.

## 11. Lint

`ruff check .`: **all checks passed**; `ruff format --check .`: **59 files
already formatted**. Legacy tree is excluded from lint by configuration
(preserved verbatim; its defects are documented, not silently edited).
Raw log: `docs/audit/raw/2026-09-27_ruff.txt`.

## 12. Type-check

`mypy src scripts tests` (strict): **Success: no issues found in 23 source
files**. Raw log: `docs/audit/raw/2026-09-27_mypy.txt`.

## 13. Git commits

```
cf64693 chore: stop tracking JetBrains .idea state
a6b5883 style: format GEE auth and sensor registry modules
c9f8c47 test: add M0 reproducibility and interface checks
95122f6 feat: add EO data interfaces and sensor registry skeleton
d0a753a docs: define scientific questions and SpartinaShift benchmark
ec6cb82 chore: establish Spartina Earth research repository
39d36ad chore: preserve legacy Spartina prototype
```

The spec suggested five commits; the five planned commits exist with the
exact suggested messages, plus three transparent housekeeping commits
(style fix exposed by correcting an over-broad ignore rule; `.idea`
index removal; this report). No history was amended.

## 14. Open issues

1. Remote **Issue #1 unread** (no `gh`, no token requested); drafts live
   in `docs/project/issues/` and must be reconciled online by the owner.
2. Licenses/citations UNKNOWN for every incoming EO product; redistribution
   blocked until resolved.
3. Band identities/scales UNKNOWN for the 11-band Zhejiang and 5-band S2
   stacks (no GDAL on host; M1).
4. CM-SSM `area` unit unverified; CM-SSM-to-multimodal-manuscript link is
   inference only.
5. No raw GEE scenes, export logs, GEE asset IDs, sample-point tables,
   training logs, or model checkpoints exist anywhere.
6. CRS/grid mismatches inside the Hangzhou Bay package (32651 mask vs
   4326 stacks; S1 grid 3x denser) require explicit reprojection QA.
7. GPUs 0 and 9 occupied by other projects at audit time.
8. Branch not pushed; no PR created (awaiting owner confirmation).

## 15. Recommended M1 actions (issue drafts provide acceptance criteria)

1. M1-01 reproducible conda env (torch cu118, rasterio/GDAL, dev tools)
2. M1-02 SHA-256 + schema-validated manifests for every asset
3. M1-03 label QA gates and license/citation resolution before any training
4. M1-04 EO/GEE data engine v1 starting from one small smoke export
5. M1-05 spatial-disjoint split tables + leakage CI (province-held-out track)
6. M1-06 adjudicate manuscript claims 15-19 (reproduce or retract)
7. M1-07 freeze the research->SpartinaGuard artifact contract

## Special report (explicit answers)

- **Past real Spartina labels found?** **YES, but only in the transferred
  `old datasets/`** (L1-L6; tiered WEAK / SILVER-candidate). In the tracked
  legacy repo itself: NO (COCO JSON MISSING).
- **Real ROI / study areas found?** **YES**: Hangzhou Bay, Zhejiang coast,
  a Fujian-coast window, and national extents; manuscript names six study
  reserves/bays.
- **Real EO imagery?** **YES, but only derived composites/stacks** (L8 SR,
  S1 VV/VH, S2 stacks, NDVI/SAI, GEE feature stacks); no raw scene archive.
- **GEE scripts / Asset information?** **NOT FOUND** anywhere; GEE
  provenance is inferred from export-style filenames only.
- **Old checkpoints?** **NOT FOUND** (no .pt/.pth/.h5/.ckpt/.onnx/
  .safetensors in repo or transfer).
- **Can any old-draft metric be reproduced now?** **NO.** No predictions,
  labels, sample tables, code versions, splits, or logs exist; one claimed
  table is additionally self-contradictory. Every manuscript number stays
  UNVERIFIED.
