# DATASET_VERSIONING_PLAN

Version: v1.0 (2026-11-27). Defines how every dataset artifact used by
training or evaluation is versioned, checksummed, and frozen. Principles:
training reads only local frozen bytes referenced by manifest version; no
live GEE calls; nothing versioned here is modified after freeze (errata =
new version).

## 1. Versioned entities

| Entity | Versioned form | Location | Checksum basis |
|---|---|---|---|
| Raw EO product bundle | product_id + manifest JSON (per-file SHA-256) | work/issue21/export{,_repair}/ | manifest bundle fingerprint_sha256 |
| Dataset release | DATASET_MANIFEST_<name>_<ver>.json listing product_ids + label family + QA ledger | benchmarks/spartinashift/<proto>/datasets/ | SHA-256 of the manifest file itself |
| Label family | label tier + product list + mapping table (label_type/label_mapping) | as above | included in dataset manifest |
| Split | split_id = {region lists, year lists, seeds, geometry hashes} | benchmarks/spartinashift/<proto>/splits/ | SHA-256 of split manifest |
| QA verdict ledger | per-product classification (accepted / partial-finite / honest-rejection / blocked) | per-protocol QA artifacts | V022_PROTOCOL_CHECKSUM.json |
| Experiment run | run manifest (see engineering/run_manifest/generate_run_manifest.py) | work/experiments/<run_id>/ | SHA-256 of run manifest |

## 2. Version scheme

`<protocol>-<dataset>-v<major>.<minor>.<patch>`
- major: label family or split semantics change (new split_id)
- minor: additional products/sensors added under same semantics
- patch: metadata-only fixes (errata recorded; original bytes never edited)

v0.2 panel export and v0.2.1 repair export are **frozen**; a v0.2.2 dataset
release is only minted after Owner approval, and only reclassifies the
documented honest-rejection verdict — label bytes never change.

## 3. Freeze procedure

1. Build dataset manifest from landed bytes (validator:
   `engineering/dataset_validation/validate_landed_products.py`).
2. Compute SHA-256 of manifest; record product count, byte count, QA
   ledger reference.
3. Record freeze in the protocol's checksum JSON (e.g.
   V022_PROTOCOL_CHECKSUM.json pattern).
4. Git-commit manifest; bytes stay outside Git with path recorded.

## 4. Storage policy

- Git: manifests, registries, code, docs. Never raster bytes.
- Local: work/ (raw landed bytes), work/derived/, checkpoints, experiment
  outputs.
- Disk discipline: /data at 91% (686 GB free); every planned addition
  (foundation-model weights, Atlas exports) requires a prior `df`/`du`
  audit recorded in the run manifest.

## 5. Run-time linkage

Every experiment config carries `dataset_manifest_sha256`,
`split_id`, and `qa_ledger_ref`; the run manifest generator rejects runs
missing any of these fields. Provenance requirements per
EXPERIMENT_STANDARD.md and BENCHMARK_NEXT_STAGE_PLAN §4 are enforced at
config-validation time, not post hoc.
