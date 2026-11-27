# REPOSITORY_BASELINE.md

Spartina Earth — M0 repository baseline audit.
Captured **2026-09-27** (server local time) on branch `main`, immediately
before any M0 modification. Raw command output is preserved at
[`raw/2026-09-27_m0_pre_change_snapshot.txt`](raw/2026-09-27_m0_pre_change_snapshot.txt).

Evidence labels used throughout the M0 audit docs:

- **VERIFIED** — directly confirmed by a command executed during this audit.
- **OBSERVED** — seen in source material but not executed/reproduced.
- **UNVERIFIED** — claimed somewhere, not independently confirmed.
- **MISSING** — searched for and not found at audit time.

---

## 1. Git baseline (VERIFIED)

| Item | Value |
|---|---|
| Working directory | `/data/yingda/Spartina-Earth` |
| Branch at audit | `main` (new work moved to `reboot/spartina-earth-m0`) |
| Remote | `https://github.com/Yingda-Yu/Spartina-Earth.git` (fetch/push, HTTPS) |
| HEAD at audit | `2be4672 Create README.md` |
| Recent history | `2be4672 Create README.md`, `40fc5c5 MA`, `c92cee7 AP.drawio`, `45f4f6f ALL.drawio`, `8f611f7 1.drawio`, `e39fffc 1Spatina Net.drawio`, `054aca0 更新adsSpatina Net.drawio`, `13004bb 更新8 Spatina Net.drawio`, `3a8215a Spatina Net8.drawio`, `51f2e71 Spatina Net7.drawio` |
| Working tree at audit | tracked files clean; two untracked items: `.trae/`, `old datasets/` (user data transfer in progress) |
| Repository size at audit | 3.4 GB (dominated by incoming `old datasets/`; Git history itself is small) |
| Author identity | not configured globally; repository-local identity set to `Yingda Yu <yuying@kean.edu>` matching prior commit history |

## 2. Files present at audit (VERIFIED)

Tracked files (24):

- 12 Python scripts (the numbered legacy pipeline + `play.py`)
- 3 DrawIO diagrams (`Spartina.drawio`, `Spatina Net.drawio`,
  `未命名绘图.drawio`)
- 1 one-line `README.md`
- 6 PyCharm/IntelliJ files under `.idea/` (IDE settings, incl.
  `workspace.xml`)

Extension counts (excluding `.git`, `old datasets`, `.trae`):
`12 .py, 6 .xml, 3 .drawio, 1 .md, 1 .iml`.

## 3. Presence checks requested by the reboot plan

| Item requested | Finding | Status |
|---|---|---|
| Uncommitted modifications | none on tracked files; untracked `.trae/`, `old datasets/` | VERIFIED |
| Large files in Git | none >1 MiB in the tracked tree (largest non-data file was inside the untracked `.trae/skills/…`, 1.2 MB) | VERIFIED |
| Credentials / `.env` / keys / service-account JSON | filename scan: none found | VERIFIED (filename-level scan; content deep-scan recommended in M1) |
| GEE code | no Earth Engine code/imports anywhere in tracked files | MISSING |
| GeoJSON / Shapefile | none in tracked tree | MISSING |
| COCO labels | code references `D:\Spatina Test\cocojson.json` (Windows-local); no JSON file present on server | MISSING (file not on server) |
| TIFF / GeoTIFF | none in tracked tree; incoming data under `old datasets/` audited separately | MISSING (tracked tree) |
| Checkpoints (`.pt/.pth/.ckpt/.h5`) | none; legacy script 2 writes `spartina_model.h5` at runtime but no artifact exists | MISSING |
| Notebooks | none | MISSING |
| Old experiment logs / metric tables | none | MISSING |
| Old manuscripts | none (`.docx/.tex/.pdf` absent from tracked tree) | MISSING |
| README | present, 1 line: "An Open ESG Program for Long-term Monitoring of Coastal Biological Invasion" (preserved at `legacy/README.original.md`) | VERIFIED |
| DrawIO diagrams | 3 present (legacy UI/architecture sketches) | VERIFIED |
| Data directories | none at audit except incoming `old datasets/` (`30mSpartinaChina/`, `Spartina/`, `spartinatest/`, one `.rar` being transferred) | OBSERVED |
| `.gitignore` | did not exist | MISSING → created in M0 |
| Python packaging / tests / CI configs | none | MISSING → created in M0 |

## 4. Host environment (VERIFIED)

| Item | Value |
|---|---|
| OS | Linux (server) |
| CPU | Intel Xeon Gold 6248R @ 3.00 GHz, **96 logical CPUs** |
| RAM | **503 GiB total** (~30 GiB used at audit); swap 286 GiB (~108 GiB used) |
| Data disk | `/dev/sdb` mounted at `/data`: 7.3 TB, 63% used, **2.7 TB available** |
| GPUs | **10× NVIDIA GeForce RTX 3090, 24 GB each** (PCI bus IDs 1A–1E, 3D–3F, 40–41; confirmed by `scripts/system/probe.py` query output — an early truncated interactive view misleadingly showed 8) |
| Driver / CUDA | driver 580.159.03, reported CUDA 13.0; PyTorch in system python3 is 2.5.1+cu118 (runtime CUDA 11.8); `nvcc` 11.5 in PATH (versions to be reconciled in M1) |
| GPU occupancy at audit | GPU0 12.6 GB; GPU5 1.8 GB; GPU6 1.8 GB @ ~30–43% util; GPU7 2.3 GB; GPU9 4.8 GB @ 100% util; GPU1/2/4 effectively idle; GPU3/8 near-idle. Shared server — see GPU policy. |
| System Python | `python3` 3.10.12 at `/usr/bin/python3`; **no `python` alias**; pip 22.0.2; torch 2.5.1+cu118 importable; pytest/ruff/mypy not installed |
| Conda | miniconda3 at `/data/yingda/software/miniconda3`; base Python 3.13.13 (no torch in base) |
| Conda envs | base, comfy, glaucoma-research, glaucoma-vf, kwallet, kwallet-gpu, pcbgen (**no project-specific env yet** — recommended M1 action) |
| `gh` CLI | not installed → GitHub issues drafted under `docs/project/issues/` |

## 5. Legacy content summary (OBSERVED from source reading)

All 12 Python files were read line-by-line. They constitute an early,
Windows-local, exploratory pipeline: Google Images scraping → a TensorFlow
binary CNN → a PyTorch U-Net sketch → COCO-polygon tooling, mask
rasterization, random image-level 70/15/15 splitting, and image padding to
2048×1367. See [`LEGACY_RESULT_AUDIT.md`](LEGACY_RESULT_AUDIT.md) for the
claim-by-claim table and [`../../legacy/README.md`](../../legacy/README.md)
for the file map.

Notable integrity observations (not "bugs to fix", but facts for future
design):

- The CNN script creates `spartina/` and `other/` class folders but only
  ever fills `spartina/` — a binary classifier as written would have no
  negative examples.
- Dataset preparation shuffles images globally and splits at image level;
  spatial adjacency is not controlled (forbidden under the new benchmark
  contract).
- The U-Net script references undefined `images, masks` variables and its
  decoder does not concatenate encoder features (so it is architecturally a
  plain down/up stack, not a U-Net with skip connections); it is not
  runnable as committed.
- All paths are `D:\…` Windows paths; no referenced data exists on this
  server.
- **No quantitative results exist anywhere**: no IoU/F1/precision/recall/
  accuracy numbers, no logs, no figures of results, no checkpoints.

## 6. Actions taken during M0 (branch `reboot/spartina-earth-m0`)

1. This raw snapshot captured before modification.
2. Legacy files relocated with `git mv` into `legacy/` (history preserved,
   nothing deleted).
3. `.gitignore` added: excludes `.trae/skills/`, IDE state, secrets, large
   data/raster/checkpoint artifacts, and `old datasets/`.
4. Modern repository structure, governance docs, audit docs, interface
   skeletons, manifest schema, and stdlib-only tests added.
5. No training, no GEE calls, no downloads, no data movement performed.

## 7. Known unknowns - resolved and open

Resolved on 2026-09-27 by full read-only enumeration of the completed
`old datasets/` transfer (7.2 GiB, 55 files), documented in
[`DATA_INVENTORY.md`](DATA_INVENTORY.md) and
[`LABEL_INVENTORY.md`](LABEL_INVENTORY.md):

- Real EO stacks DO exist (Hangzhou Bay 2015 L8+S1+indices; Zhejiang GEE
  11-band stacks; Fujian-window S2 2019-2025) - all derived composites,
  no raw scenes.
- Real label products DO exist (national 2015 30 m raster; national 2020
  CM-SSM polygons, 148,072 features; Hangzhou Bay mask; CMSA 2019-2021) -
  tiered WEAK / SILVER-candidate; licenses UNKNOWN.
- Two manuscript drafts authored by the repository owner DO exist; every
  quantitative claim stays UNVERIFIED and one table is arithmetically
  CONTRADICTED (see LEGACY_RESULT_AUDIT addendum).
- Model checkpoints, training logs, GEE scripts/asset IDs, and sample-point
  tables: still **MISSING** after the full enumeration.

Still open:

- Whether the original `cocojson.json` / image set / any checkpoint survive
  on the former Windows machine or other media: **UNKNOWN**.
- Licenses, citations, band-name tables, and checksums for all incoming
  assets: **MISSING**, required at M1 manifest creation.
- Any files added to `old datasets/` after 2026-09-27 require re-running
  the inventory.
