# SPARTINAFM_RESEARCH_GAP_ANALYSIS_PLAN

Version: v1.0 plan (2026-11-27). Defines exactly how the SpartinaFM gap
analysis will be produced after benchmark Stages A–D. SpartinaFM itself
is NOT built (SPARTINAFM_DESIGN.md is a hypothesis document); this plan
is the gate discipline that decides whether it should be. Final gap
document will be `docs/research/SPARTINAFM_GAP_ANALYSIS.md` — does not
exist yet, by design.

## 1. Trigger

Runs M-BASE-A/B/C and M-FM complete with preserved failure registries.
Stage E then executes this plan. No architecture implementation starts
before `SPARTINAFM_GAP_ANALYSIS.md` is Owner-accepted.

## 2. Failure extraction protocol

For every completed formal run (all seeds, all tracks):

1. Collect per-cell error tensors (pred vs label disagreement maps,
   calibration residuals, area errors) into a failure registry keyed by
   run_id.
2. Stratify every failure instance by:
   - label stratum (source-agreement / source-disagreement / boundary /
     small-patch / confounder-prone; GOLD pilot sites when they exist);
   - sensor identity + band-availability condition;
   - DOY tertile, observation count, observation gap length;
   - modality condition (optical-only / +SAR / missing-modality);
   - region + coastal-segment covariates (tidal range, sediment class,
     latitude band).
3. Collapse to candidate gaps only when a failure pattern:
   (a) is quantitatively measured (effect size + CI),
   (b) recurs across independent spatial units (≥3 cells in ≥2 regions),
   (c) persists for the best foundation-model run (not just the ladder),
   (d) maps to ≥2 primary benchmark tracks.

## 3. Failure source taxonomy (pre-declared, from roadmap Phase 3)

| Source | Diagnostic | Quantification |
|---|---|---|
| Label quality | error concentration at SILVER-disagreement/boundary strata; GOLD cross-check | error-rate ratio vs agreement stratum, 95% CI |
| Sensor difference | per-sensor ΔIoU; band-identity ablation (H2) | cross-sensor ΔIoU with/without identity embeddings |
| Time/phenology | error vs DOY tertile; vs observation count; cross-year residual maps | slope + CI; permutation sensitivity |
| Modality missing | dropout-condition error increments | degradation slope per availability level |
| Regional ecology | leave-region-out residual clustering vs coastal-segment covariates | cluster separation statistic + covariate loadings |

A gap is attributable to a source only if the diagnostic effect survives
the confound controls above (e.g. sensor-stratified analysis must hold
DOY and region fixed or covary them out).

## 4. Decision rules (pre-registered)

- BUILD: ≥1 gap satisfies (a)–(d) AND the gap analysis argues no existing
  foundation model addresses it (with evidence from M-FM ablations);
  architecture decision then follows
  SPARTINAFM_ARCHITECTURE_DECISION.md component gates G1–G4.
- PIVOT: no gap satisfies the conditions → contribution redirects to
  data/benchmark/ecology/recurrence; this is a valid, documented outcome
  (HYPOTHESES.md H6 decision rule), recorded in the gap document with
  the quantified evidence for the absence.
- AMBIGUOUS: gaps satisfy (a)–(c) but only one track → escalate to
  Owner with evidence; no unilateral build decision.

## 5. Anti-fabrication constraints

- No gap claim without a reproducible notebook/script + registry ref.
- Every percentage in the gap document must be recomputable from the
  failure registry CSVs committed with the document.
- Negative findings (e.g. "phenology stratification explains <1 IoU
  point") are recorded, not dropped.
