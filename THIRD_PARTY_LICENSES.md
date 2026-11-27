# THIRD_PARTY_LICENSES.md

Register of third-party software, pretrained models, and datasets used by
Spartina Earth. **Nothing is bundled in Git.** Entries are added when the
component is actually adopted; before adoption, license compatibility and
attribution requirements are verified.

## Status key

- **ADOPTED**: actually used by the project; license and source recorded.
- **PLANNED**: candidate for M1+; not downloaded, not used; license not
  yet vetted (`TODO_VERIFY`).

## Software dependencies

| Component | Version | Purpose | License | Status |
|---|---|---|---|---|
| Python | ≥ 3.10 | runtime | PSF | ADOPTED (system-provided; M0 code uses stdlib only) |
| pytest | ≥ 7.4 | test runner | MIT | PLANNED (`dev` extra) — `TODO_VERIFY` exact license text at lock time |
| ruff | ≥ 0.6 | linter/formatter | MIT | PLANNED (`dev` extra) — `TODO_VERIFY` |
| mypy | ≥ 1.10 | type checker | MIT | PLANNED (`dev` extra) — `TODO_VERIFY` |
| pre-commit | ≥ 3.7 | git hooks | MIT | PLANNED (`dev` extra) — `TODO_VERIFY` |
| earthengine-api | — | GEE client (M1+) | Apache-2.0 (per project metadata; `TODO_VERIFY`) | PLANNED |
| rasterio / shapely / pyproj / geopandas | — | geospatial I/O (M1+) | BSD-style (`TODO_VERIFY` per package) | PLANNED |
| PyTorch / torchvision | — | models (M3+) | BSD-style (`TODO_VERIFY`) | PLANNED |

No third-party Python package is installed or vendored at M0. When a
locked dependency file is created (M1), exact versions and license texts
must be exported (e.g. via an SBOM tool) and attached here.

## Pretrained models (candidate baselines; see docs/models/BASELINES.md)

| Model | Upstream | Intended role | License status | Status |
|---|---|---|---|---|
| SatMAE | official research release | foundation baseline | `TODO_VERIFY` — research code; confirm redistribution/weight terms before download | PLANNED |
| Prithvi-EO-2.0 | IBM/NASA via Hugging Face | foundation baseline | `TODO_VERIFY` — verify exact model card license and use restrictions before download | PLANNED |
| AnySat | official research release | foundation baseline | `TODO_VERIFY` — research code; confirm terms | PLANNED |
| U-Net / DeepLabV3+ / SegFormer implementations | chosen at M3 (own impl vs. library) | strong baselines | `TODO_VERIFY` per implementation | PLANNED |

**Rule:** a pretrained model is not downloaded or wrapped until its
license, card, and intended-use restrictions are recorded here. Foundation
models are never bundled into Git.

## Datasets

See [`DATA_LICENSE.md`](DATA_LICENSE.md) and per-asset manifests; datasets
are not duplicated in this table.

## Attribution procedure

1. Before adopting a component, add a row here with source URL, version,
   commit hash (for code), and license.
2. Preserve license/NOTICE files under a future
   `third_party_notices/` directory (generated; not hand-edited).
3. In papers, cite the component's paper and software release exactly as
   requested upstream (`TODO_CITATION` until verified).
