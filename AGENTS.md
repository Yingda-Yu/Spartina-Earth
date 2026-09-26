# AGENTS.md — Operating Rules for Spartina Earth

**Every agent (human or AI) must read this file before doing any work in
this repository.** This is a long-term research system, not a one-off
coursework code drop. When a rule below conflicts with convenience, the
rule wins.

---

## 1. Project mission

Spartina Earth is a long-term, open, reproducible Earth-observation + AI
research program maintained by Spartina Technology around the coastal
invasive plant **Spartina alterniflora** (互花米草). It aims to produce
trustworthy, traceable, cross-decade monitoring products and models for
invasion, eradication, and post-eradication recurrence.

## 2. Flagship scientific question

> Can a sensor-agnostic multimodal temporal Earth-observation model learn a
> stable representation of Spartina alterniflora across changing satellite
> generations, regions, phenological stages and management interventions,
> enabling consistent long-term monitoring and early detection of
> post-eradication recurrence?

## 3. Naming (do not invent variants)

| Name | Meaning |
|---|---|
| **Spartina Earth** | Umbrella name for the research, data, model and open ESG program |
| **SpartinaFM** | Cross-sensor, cross-era, multimodal temporal EO representation model |
| **Spartina Atlas** | Long-term distribution / change / eradication / recurrence / uncertainty data products (China coast first, global later) |
| **SpartinaShift** | Benchmark for cross-region, cross-year, cross-sensor, management and missing-modality generalization |
| **SpartinaGuard** | Independently developed Web GIS operational product. **Not** part of this repository; it consumes standardized outputs via `integrations/spartinaguard/` contracts |

## 4. Non-negotiable integrity rules

1. Never delete legacy research code or overwrite legacy experiment records.
   Legacy lives under `legacy/` and is retained for traceability.
2. Every number in old papers, spreadsheets or code is **UNVERIFIED** until
   reproduced from raw evidence.
3. A claim is not true because an old draft said so.
4. Never fabricate missing data, labels, results, file paths, or GEE assets.
5. If something cannot be found, write `UNKNOWN` / `MISSING`. Do not guess.
6. No random splits of adjacent remote-sensing patches into train/test
   (spatial leakage). Splits must be spatially disjoint.
7. Never upsample Landsat 30 m to 10 m and present the result as a true
   10 m long-term product.
8. Every data product must be traceable:
   `source scene → preprocessing → label → model → checkpoint → inference config → output`.
9. Every experiment records Git commit, config, data version, and seed.
10. No promotional claims ("Nature-level", "world's first", "first national
    map") unless supported by strict, documented evidence.
11. No OAuth tokens, GEE credentials, SSH keys, API keys, service-account
    JSON, or passwords in Git (see `.gitignore`).
12. No large files, imagery, or checkpoints in Git.
13. Do not modify other projects or data on this server.
14. M0 constraints (lifted only by explicit user decision): no large-scale
    GPU training; no bulk GEE downloads.

## 5. Data provenance policy

- Every dataset/asset gets an entry conforming to
  `datasets/manifests/schema.json`, with checksum, provider, license, and
  provenance chain.
- Label quality tiers: **GOLD** (field/UAV/expert-verified),
  **SILVER** (credible government or peer-reviewed mapping products with
  known provenance), **WEAK** (index/rule/legacy automatic labels),
  **UNLABELED** (raw EO for self-supervised pretraining).
- External data licenses are confirmed per item; nothing is assumed
  Apache-licensed (see `DATA_LICENSE.md`).
- If legacy code references data outside the repository, record the path;
  do not move or copy it without explicit instruction.

## 6. Experiment reproducibility policy

See `docs/experiments/EXPERIMENT_STANDARD.md`. Minimum per run:
`run_id, timestamp, git_commit, dataset_manifest_version, split_version,
model, checkpoint, config, seed, gpu_ids, software_environment, metrics,
artifact_paths`.

No config-less experiments, no manual renaming of result folders, no
overwriting checkpoints, no terminal-screenshot-only reporting. Git stores
manifests and summaries; bytes live outside Git.

## 7. No spatial leakage rule

- Train/val/test must be spatially disjoint (grouped by defined spatial
  units, e.g. grid tiles or coastal segments with buffers).
- Test regions never participate in hyperparameter selection.
- Scenes of the same location across dates are grouped, not scattered.
- `src/spartina/evaluation/splits.py` provides the leakage-check utility;
  benchmark splits must pass it.

## 8. No fabricated result rule

- If an experiment has not actually run, expected outcomes may be written
  **only** as hypotheses/predictions, clearly marked, never as results.
- Tables without executed runs contain `TODO_EXPERIMENT` / `NOT RUN`,
  never invented numbers.
- Placeholders for citations: `TODO_CITATION`; for verification:
  `TODO_VERIFY`. Never invent references.

## 9. No large files in Git

Rasters, arrays, archives, checkpoints, and the local `old datasets/`
directory are ignored. Track manifests, configs, code, and summaries.
Enforced by `.gitignore` and the `check-added-large-files` pre-commit hook
(1 MiB threshold).

## 10. Legacy result policy

Legacy code (`legacy/`) is unverified history. Its implied or stated
metrics must not appear in new manuscripts until independently reproduced.
Audit statuses: `VERIFIED`, `UNVERIFIED`, `CONTRADICTED`, `MISSING` — see
`docs/audit/LEGACY_RESULT_AUDIT.md`.

## 11. GPU resource policy

- Check `nvidia-smi` before launching anything; this is a shared server.
- M0: no GPU training.
- User-level standing policy: at most 3× RTX 3090 for this project; GPUs
  already heavily used by others must not be taken; idle GPUs with small
  residual memory (≈1–2 GB) may be shared. See
  `docs/system/GPU_POLICY.md`.

## 12. Paper evidence policy

- Claims map to executed experiments; experiments map to manifests.
- Unverified IRB / consent / data-governance facts stay explicit
  placeholders; never invent ethics approvals.
- Manuscript stage focuses on consolidation and evidence closure, not new
  exploratory experiments, unless explicitly planned.

## 13. Definition of Done (M0)

- [x] Repository audited before modification; snapshot in
      `docs/audit/raw/`
- [x] Legacy preserved under `legacy/` with an explanatory README
- [x] Repository structure, governance docs, and specs created
- [x] Data/label inventories and manifest schema created
- [x] GEE and sensor interfaces are clean skeletons with mocked tests only
- [x] Smoke/unit tests pass with the standard-library-only M0 package
- [x] Audit docs distinguish VERIFIED / OBSERVED / UNVERIFIED / MISSING
- [ ] (M1+) real data engine, real labels, baselines, benchmark runs

**M0 stops after acceptance. M1 begins only after user review.**
