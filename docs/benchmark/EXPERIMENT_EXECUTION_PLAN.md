# EXPERIMENT_EXECUTION_PLAN

Version: v1.0 (2026-11-27). How Benchmark V1 experiments are executed on
the available infrastructure. Plan only — no run has been executed; all
statuses live in SPARTINA_EARTH_MILESTONE_REGISTRY.csv.

## 1. Resource budget (audited 2026-11-27)

- GPUs: 10× NVIDIA RTX 3090 (24 GB). Discipline: **never GPU 0**; ≤3 GPUs
  concurrently per experiment; free-memory check before each launch
  (`nvidia-smi`). Current shared load: several GPUs busy with other
  users' work (up to ~24 GB on 1/2/3/7); prefer GPUs 5/8/9 when free.
- CPU/RAM: 96 cores, 503 GB RAM (shared; ~150 GB available).
- Disk: /data 7.3T (686 GB free, 91% used) — foundation-model weights and
  Atlas outputs require a pre-download disk audit recorded in the run
  manifest. Root disk 103 GB free.
- Data: landed EO bytes 8.1 GB panel + 128 MB repair (work/, outside Git).

## 2. Environment

- Python: /data/yingda/software/miniconda3/envs/spartina-earth/bin/python3.11
  (numpy 1.26.4, rasterio 1.4.3 verified). Torch availability unverified —
  checked at smoke-test time; recorded in run manifest environment hash.
- Every run records: conda env, pip freeze hash, Git SHA, GPU ids.

## 3. Execution stages (each stops for Owner review)

| Stage | Content | Entry gate | Outputs |
|---|---|---|---|
| S0 freeze | dataset manifest + split_id frozen; A1–A7 leakage audit exit 0 | v0.2.2 approval + readiness | SPLIT_V1 manifest + checksum |
| S1 smoke | 1 cell, 1 epoch, RF + U-Net + SegFormer-B0; loader round-trip test | S0 + training authorization | smoke logs; exit codes |
| S2 Stage A | in-domain + cross-year formal runs (conventional ladder, 3 seeds) | S1 pass | results tables + CIs; failure registry |
| S3 Stage B | cross-region + Landsat/Historical-Sensor | S2 Owner review | per-region results |
| S4 Stage C | missing-modality + sparse-temporal | S3 Owner review | degradation curves |
| S5 Stage D | foundation models (adapter validation on landed bytes first) | S4 review + disk/GPU audit | compatibility matrix → results |
| S6 Stage E | failure extraction → SPARTINAFM_GAP_ANALYSIS.md | S5 review | gap taxonomy document |

## 4. Run protocol (per run, mandatory)

1. Config from `engineering/configs/` templates; no inline-edited
   hyperparameters; config SHA recorded.
2. `engineering/run_manifest/generate_run_manifest.py` before launch —
   rejects runs missing dataset_manifest_sha256 / split_id / seeds /
   git_sha / environment.
3. GPU pick: check free memory; never GPU 0; ≤3 GPUs; record ids.
4. Checkpoints resumable; outputs under work/experiments/<run_id>/
   (outside Git); manifest + SHA-256 in Git.
5. Evaluation only via BENCHMARK_METRIC_SPEC implementation; test cells
   touched once per frozen protocol.

## 5. Failure handling

- Smoke failure → fix loader/config; rerun smoke; never proceed to
  formal runs on a failing smoke.
- OOM/contention → reduce batch or move GPU; never exceed 3 GPUs; never
  kill other users' processes.
- Crash mid-run → resume from checkpoint; record interruption in run
  manifest.
- Negative or failed results are committed and preserved (no hidden
  failures).
