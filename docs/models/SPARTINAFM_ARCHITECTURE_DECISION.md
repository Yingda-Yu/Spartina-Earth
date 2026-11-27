# SPARTINAFM_ARCHITECTURE_DECISION — gate document

Version: v1.0 (2026-11-27). Records the architecture decision framework
for SpartinaFM. **Decision status: NO DECISION POSSIBLE YET** — the gate
inputs (benchmark Stages A–D + failure analysis) do not exist. This
document exists so the decision procedure is fixed before results, and
cannot be rewritten after seeing them.

## 1. Decision inputs (all required, none exist today)

| Input | Source | Status |
|---|---|---|
| Quantified failure gaps on ≥2 tracks | SPARTINAFM_RESEARCH_GAP_ANALYSIS_PLAN §2–3 | NOT_PRODUCED |
| Foundation-model regime results (probe/PEFT/FT) | FOUNDATION_MODEL_COMPARISON §3 | NOT_PRODUCED |
| Component-level evidence: G1 adapters, G2 temporal, G3 fusion | SPARTINAFM_DESIGN §6 gates | NOT_TESTED |
| Owner acceptance of gap analysis | Owner review | PENDING |

## 2. Decision procedure

1. If SPARTINAFM_GAP_ANALYSIS.md is Owner-rejected or its conditions are
   unmet → NO BUILD; contribution pivots (documented, H6 rule); this
   file records the pivot with evidence refs. End of line for
   SpartinaFM v1.
2. If ≥1 gap qualifies → component-wise build decision:
   - G1 sensor adapters: build only if Cross-Sensor/Historical-Sensor
     degradation is measurable and fixed-channel models fail to absorb it.
   - G2 irregular temporal encoder: build only if Sparse-Temporal exposes
     fixed-cadence failure beyond pre-registered margin.
   - G3 gated multimodal fusion: build only if Missing-Modality shows a
     robustness gap vs the strongest ensemble baseline.
   - G4 full pretraining objective: justified only per
     SPARTINAFM_DESIGN §4 with per-objective ablations planned.
3. Any build decision specifies: parameter budget ≤ GPU discipline (≤3×
   RTX 3090), ablation matrix, and the pre-registered evaluation tracks.

## 3. Design constraints carried from SPARTINAFM_DESIGN (unchanged)

- Identity-tagged observation tokens (sensor/band/wavelength/resolution/
  date/quality) — never fixed channel semantics.
- Irregular temporal encoder: variable-length sequences, timestamp-aware.
- Multimodal gated fusion with modality dropout; quality-conditioned.
- Native-grid honesty: resolution embeddings; no upsampling claims.
- Heads: segmentation primary; change/uncertainty/trajectory/recurrence
  heads only when their labels exist (recurrence head stays BLOCKED
  until the treatment ledger is non-empty).

## 4. Record

| Field | Value |
|---|---|
| decision_date | — (not taken) |
| decision | NONE — awaiting gate inputs |
| evidence_refs | none yet |
| next_review | after Stage E gap analysis + Owner review |
