# GPU Policy

Project-level policy for the shared GPU server. Aligned with standing user
policy and [`SERVER_INVENTORY.md`](SERVER_INVENTORY.md).

## 1. Allocation

- **Project cap: at most 3× RTX 3090** for Spartina Earth unless the user
  explicitly approves more in writing.
- The server is shared with other people and projects. Always run
  `nvidia-smi` immediately before launching any GPU job.
- GPUs already running someone else's workload (significant memory **or**
  active utilization) must not be taken.
- GPUs that are effectively idle with only small residual memory
  (≈1–2 GiB from a dormant process) may be shared, provided the job's
  peak footprint fits comfortably in free VRAM; leave headroom.
- M0: **no GPU training or large inference at all.**

## 2. Job classes and resource separation

| Class | Typical resources | Timing discipline |
|---|---|---|
| Debug / smoke test | 1 GPU, tiny batches, minutes | anytime; required before full runs |
| Ablation / short training | 1 GPU | after smoke test; watch VRAM headroom |
| Formal pretraining / large runs | up to 3 GPUs (DDP, NCCL) | only after config/data are frozen; run when free capacity exists; record `gpu_ids` and world size |
| Inference / evaluation | 1–2 GPUs | separate queue/logs from pretraining; never contend with someone else's full-VRAM job |

## 3. Hygiene rules

- Pin visible devices via `CUDA_VISIBLE_DEVICES` per run; never assume GPU0.
- Set memory growth / bounded batch size; do not grab all free VRAM on
  shared cards.
- Record GPU model, count, driver/CUDA, and actual peak memory in the run
  manifest.
- For multi-GPU runs use `torch.distributed` (NCCL); sampler/world-size
  recorded for reproducibility.
- Kill only processes you own; never touch other users' processes or
  projects on the server.

## 4. Pre-flight checklist (M3+)

1. `nvidia-smi`: pick GPUs meeting the cap and sharing rule.
2. Dedicated conda env activated; package versions logged.
3. Smoke test passed (one GPU, few batches).
4. Data manifest + split version frozen; config checked in.
5. Run launched with explicit `CUDA_VISIBLE_DEVICES`; run manifest created
   with `status=running`.
6. Monitor first 10 minutes (VRAM, thermal, throughput), then proceed.

## 5. What this policy does not do

- It does not guarantee GPU availability; experiments wait for capacity.
- It does not authorize bulk data downloads or training during M0/M1.
- It does not permit modifying other projects or data on the server.
