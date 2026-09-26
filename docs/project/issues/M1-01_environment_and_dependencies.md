# [M1-01] Create reproducible M1 environment

**Milestone:** M1
**Type:** infra

## Context

M0 code is deliberately stdlib-only. Host facts
(`docs/system/SERVER_INVENTORY.md`): system Python 3.10.12 with
torch 2.5.1+cu118 importable and CUDA visible on 10x RTX 3090; no
GDAL/rasterio/pytest/ruff/mypy in system Python.

## Tasks

- [ ] Dedicated conda env for the project (never install into base);
      pin Python, torch (cu118), rasterio/GDAL, geopandas, pydantic,
      pytest, ruff, mypy
- [ ] Commit lockfile / `environment.yml`; document `nvidia-smi`
      pre-flight and the max-3-GPU project cap
- [ ] Smoke test: import torch + CUDA device count; read one local GeoTIFF
      with rasterio
- [ ] CI-equivalent local command documented in AGENTS.md

## Acceptance

A new shell can recreate the env and run `pytest` green with one
documented command.
