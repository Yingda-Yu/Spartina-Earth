# Experiment Standard

Every formal experiment from M3 onward follows this contract. The goal is
that any reported number can be traced from a run record back to code,
data, and config, and that no expected result is ever written as an
observed one.

## 1. Required run record

Every run writes a machine-readable `run.json` (or equivalent manifest)
under its run directory with at least:

| Field | Meaning |
|---|---|
| `run_id` | unique, time-ordered identifier; never reused |
| `timestamp` | UTC start time, ISO 8601 |
| `git_commit` | full commit hash (dirty tree = abort or explicit `git_diff` capture) |
| `dataset_manifest_version` | hash/version of the data manifest used |
| `split_version` | `split_id` of train/val/test assignment |
| `model` | model name, architecture config, pretrained-weights id if any |
| `checkpoint` | URI/hash of the checkpoint produced or loaded |
| `config` | full resolved configuration (all effective hyperparameters) |
| `seed` | seed (list for multi-seed runs); deterministic-flag status |
| `gpu_ids` | GPUs used; mode (DDP/single) |
| `software_environment` | python/torch/CUDA/library versions or env lock reference |
| `metrics` | metric name → value, per track/region, with CIs where applicable |
| `artifact_paths` | relative URIs of logs, checkpoints, outputs (bytes outside Git) |
| `status` | `planned / running / completed / failed / aborted` |
| `notes` | anomalies, manual interventions, deviations |

## 2. Directory contract (outside Git)

```
runs/<run_id>/
    run.json           # manifest (summary may be copied into Git-tracked tables)
    config.yaml        # effective config snapshot
    train.log
    metrics.json
    checkpoints/       # gitignored
    artifacts/         # gitignored
```

`runs/`, `checkpoints/`, `artifacts/`, and `outputs/` are git-ignored.
Git tracks experiment **manifests/summaries** only (a curated index, not
the raw bytes).

## 3. Prohibitions

- No manual renaming of result folders; IDs are generated and immutable.
- No overwriting checkpoints (write new files; retain best-on-validation
  pointer inside the manifest).
- No experiment without a checked-in config (CLI parameters may override
  but must be captured in the resolved config).
- No "terminal screenshot only" reporting; stdout/stderr are logged to
  files and metrics written to `metrics.json`.
- No test-set tuning: thresholds, calibration, early stopping, model
  selection use validation units only.
- No random neighboring-patch splits (see benchmark SPEC).
- No test-region hyperparameter selection.
- No starting from a copied old run with edited numbers; reruns are new
  `run_id`s referencing the old one.

## 4. Seeds and stochasticity

- Seed Python, NumPy, framework RNGs, and dataloaders; record
  nondeterministic operations honestly.
- Stochastic headline results use ≥3 seeds; report spread, never the best
  seed alone.
- DDP: record backend (NCCL), world size, and sampler settings.

## 5. Metrics discipline

- Metrics follow `benchmarks/spartinashift/SPEC.md` definitions; unit
  conventions (IoU vs. percentage, meters vs. pixels) frozen in code.
- Confidence intervals by spatial-unit bootstrap; pooled and per-region
  numbers both reported.
- Negative/regressed results are kept; deleting failed runs is forbidden
  (mark `status=failed/aborted` with reason).

## 6. Experiment registry

A curated index `docs/experiments/REGISTRY.md` (created in M3 at the first
real run) lists every `run_id` with one line: date, branch, question (RQ/H),
track, headline result, manifest link. The registry contains only values
read from actual run manifests — no hand-typed estimates.

## 7. Placeholder policy for planned work

Before runs exist, documents and manuscript tables use:
`TODO_EXPERIMENT` (experiment not run), `TODO_VERIFY` (fact to confirm),
`TODO_CITATION` (reference to add). Inventing numbers or references is a
hard violation.

## 8. Smoke-test-first policy (project convention)

Before any full-scale run: a tiny-batch smoke test (single GPU, few
batches) validates data loading, shapes, loss decreases, checkpoint write,
and metrics plumbing; the smoke run is logged like any run.
