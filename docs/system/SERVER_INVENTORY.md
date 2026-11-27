# SERVER_INVENTORY.md

Recorded from real probes on **2026-09-27** (raw output:
[`../audit/raw/2026-09-27_m0_pre_change_snapshot.txt`](../audit/raw/2026-09-27_m0_pre_change_snapshot.txt)).
Only detected hardware is recorded. Re-run
[`../../scripts/system/probe.py`](../../scripts/system/probe.py) for a
fresh snapshot. The machine is shared — occupancy changes continuously.

## Host

| Item | Value |
|---|---|
| OS | Linux |
| CPU | Intel Xeon Gold 6248R @ 3.00 GHz |
| Logical CPUs | 96 |
| RAM | 503 GiB total (≈30 GiB used at audit; ≈466 GiB available) |
| Swap | 286 GiB total (≈108 GiB used) |
| Data filesystem | `/dev/sdb` on `/data`: 7.3 TB total, 4.5 TB used, **2.7 TB available (63%)** |

## GPUs (VERIFIED via `nvidia-smi` and `scripts/system/probe.py`)

**10× NVIDIA GeForce RTX 3090, 24 GB VRAM each.**
(Note: an early terminal view truncated to 8 rows; the count of 10 was
confirmed by `--query-gpu` and the probe script — trust the script output,
not the truncated interactive view.)

| GPU index | Bus ID | VRAM used at audit | Utilization at audit | Note |
|---|---|---|---|---|
| 0 | 1A:00.0 | 12.6 GiB | 0% | occupied by another workload/user |
| 1 | 1B:00.0 | 21 MiB | 0% | effectively idle |
| 2 | 1C:00.0 | 21 MiB | 0% | effectively idle |
| 3 | 1D:00.0 | 416 MiB | 0% | near idle |
| 4 | 1E:00.0 | 23 MiB | 0% | effectively idle |
| 5 | 3D:00.0 | 1.8 GiB | 0% | residual process |
| 6 | 3E:00.0 | 1.8 GiB | ~30–43% | active other workload — do not take |
| 7 | 3F:00.0 | 2.3 GiB | 0% | residual process |
| 8 | 40:00.0 | 420 MiB | 0% | near idle |
| 9 | 41:00.0 | 4.8 GiB | 100% | active other workload — do not take |

- Driver: **580.159.03**; reported CUDA version: **13.0**
- `nvcc` in PATH: **11.5** (toolkit/driver mismatch — reconcile when the
  project environment is built in M1; PyTorch ships its own runtime, so
  this is an M1 verification item, not an M0 blocker).

## Software

| Item | Value |
|---|---|
| `python3` (system) | 3.10.12 at `/usr/bin/python3` |
| `python` alias | not present |
| pip (system) | 22.0.2 |
| PyTorch in system python3 | **2.5.1+cu118 importable, CUDA available, sees all 10 devices** (pre-existing install; not a project-controlled environment — versions to be locked in M1) |
| pytest / ruff / mypy | not installed in system python3 (M0 smoke tests run via a lightweight tool install in M1 or a dedicated venv) |
| Conda | miniconda3 at `/data/yingda/software/miniconda3` |
| Conda base Python | 3.13.13 (no torch in base) |
| Existing conda envs | base, comfy, glaucoma-research, glaucoma-vf, kwallet, kwallet-gpu, pcbgen |
| Project conda env | **not created in M0** (create dedicated `spartina-earth` in M1) |
| GitHub CLI (`gh`) | not installed |

## Storage-relevant findings

- Project directory size at audit: 3.4 GB, dominated by incoming
  `old datasets/` transfers (user-initiated; see
  [`../audit/DATA_INVENTORY.md`](../audit/DATA_INVENTORY.md)).
- No checkpoints, rasters, or data arrays tracked in Git.

## M0 posture

No GPU work is performed in M0 (no training, no inference benchmarks).
This document records capacity only; resource use begins in M3 under
[`GPU_POLICY.md`](GPU_POLICY.md).
