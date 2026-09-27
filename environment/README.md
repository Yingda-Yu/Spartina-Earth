# Spartina Earth — frozen research environment (M1.0)

This environment is the single, reproducible interpreter for all M1+ audit,
data and modelling work. It never replaces the conda `base` environment and
no `sudo` / system Python modification is involved.

## Files

- `environment.yml` — human-maintained, pinned dependency specification.
- `versions.txt` — exact solved versions actually installed (conda + pip),
  generated once the environment was verified. This is the reproducibility
  record; `environment.yml` is the recipe.

## Reproduce

```bash
conda env create -f environment/environment.yml
conda activate spartina-earth
python scripts/system/verify_environment.py --require-gpu   # GPU host
python scripts/system/verify_environment.py                 # CPU-only host
```

Update procedure (requires explicit project decision, never ad hoc): edit
`environment.yml`, recreate the environment, re-run verification, refresh
`versions.txt`, and record the change in an experiment/audit log.

## Frozen stack (key versions)

- Python 3.11.x, conda-forge only (`nodefaults`)
- numpy 1.26, pandas 2.2, pyarrow, scipy 1.13, scikit-learn 1.5
- rasterio 1.4 (GDAL 3.10), rioxarray 0.17, xarray, geopandas 1.0,
  shapely 2.0, pyproj 3.6, fiona 1.10
- torch 2.5.1+cu118 / torchvision 0.20.1+cu118 (pip, CUDA 11.8 wheel index)
- dev: pytest 8.3, ruff 0.7, mypy 1.11

## Deliberately NOT installed in M1

AnySat, Prithvi, SatMAE foundation-model weights/SDKs, FlashAttention,
DeepSpeed, and any large model/weight download. M1 is audit-only; these
are M2+ decisions.

## GPU policy

GPU smoke tests use a single free RTX 3090 via `CUDA_VISIBLE_DEVICES` and
tensors are tiny (minute-level occupancy). Project cap: at most 3 GPUs;
check `nvidia-smi` first; never occupy GPUs already held by other projects.
See `docs/system/GPU_POLICY.md`.

## Verification record

The accepted probe (versions, CUDA, single-GPU matmul smoke) is written to
`artifacts/system/environment_probe.json` (git-ignored artifact; summarized
in M1.1 audit docs).
