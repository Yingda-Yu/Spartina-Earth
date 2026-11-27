# FOUNDATION_MODEL_COMPARISON — preparation and compatibility matrix

Version: v1.0 prep (2026-11-27). Preparation document for Stage D (EO
foundation models). **No weights have been downloaded, no adapter run, no
result exists.** The matrix below is verified against public
documentation as of this date and must be re-verified against the actual
downloaded release before any run; adapters validate on landed bytes
first.

## 1. Candidate models

| Model | Source | Pretraining data | Sensors supported | Input bands required | Resolution | Temporal support | License | Weights availability | Notes |
|---|---|---|---|---|---|---|---|---|---|
| Prithvi-EO-2.0 | IBM/NASA (HLS) | HLS-30 multispectral global archive | optical (HLS-style) | 6 bands: blue, green, red, NIR, SWIR-1, SWIR-2 (+S1/S2 versions in 2.0 family — verify at download) | 30 m native (HLS) | temporal tokens (T steps) | Apache-2.0 (verify) | public on HF (verify) | 30 m native matches Landsat family; band mapping to L8 documented per adapter |
| SatMAE++ | Stanford | fMoW + fMoW-Sentinel multispectral | optical multispectral | RGB + additional MS groups (per config) | variable (patch-based) | temporal (multi-shot) | MIT (verify) | public (verify) | temporal tokenization candidate for RQ3 comparison |
| AnySat | Ubéda et al. | PlanetScope + S1/S2 + others (JEPA) | multimodal optical+SAR | per-modality patch schemas (S1 GRD, S2 L2A among supported) | native per modality | multi-temporal multi-modal | MIT (verify) | public (verify) | closest match to multimodal identity-token design; benchmark for SpartinaFM decision |

Selection rule: these three are mandated by BENCHMARK_NEXT_STAGE_PLAN §2;
any additional model requires justification + the same verification row
before integration (no unverified implementations).

## 2. Compatibility against landed data (predicted — validated at adapter time)

| Landed family | Prithvi-EO-2.0 | SatMAE++ | AnySat |
|---|---|---|---|
| L8/L7 30 m SR | direct (6-band subset; coastal/cirrus dropped — documented) | possible (band-group mapping) | possible (as generic optical) |
| S2 10 m | resample to 30 m for native-grid comparability (honest: reported as 30 m family) | direct-ish (10/20 m bands) | direct (S2 L2A schema) |
| S1 dualpol | 2.0 S1 variants (verify) | not native | direct (S1 GRD schema) |
| L7 SLC-off gaps | handled by VALID masking; adapter must accept nodata | same | same |

Key risks to verify at adapter time: (1) exact band lists/normalization
statistics of each release; (2) license terms for research use; (3)
inference memory on 24 GB RTX 3090 (Prithvi-2.0 may need tiling);
(4) reproducibility of released checkpoints.

## 3. Comparison protocol (after M-BASE-A/B/C)

1. Adapter validation on landed bytes: forward pass → output shape/NaN
   check → linear probe on validation cells (no test access).
2. Four regimes per model (BENCHMARK_NEXT_STAGE_PLAN): frozen encoder +
   linear probe; frozen encoder + segmentation head; parameter-efficient
   fine-tuning; full fine-tune (justified only if PEFT leaves a
   documented gap).
3. Same manifests/splits/seeds/budgets as conventional ladder.
4. Deliverable: measured compatibility matrix (replaces the predicted
   one above) + per-regime results tables.

## 4. Download policy

Each model download requires prior disk audit (686 GB free) and records
weight SHA-256 in the dataset/experiment manifest. No model is loaded
into training before its adapter passes validation. GPU discipline: ≤3
GPUs, never GPU 0.
