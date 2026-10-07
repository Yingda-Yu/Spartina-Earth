# SILVER external-label training eligibility — recommendation v1

Date: 2026-10-07. Trigger: Issue #18 (2020 multi-resolution label
disagreement and scale audit). Status: **RECOMMENDATION ONLY — no
registry value is changed by this note.** The registry field
`internal_training_allowed` remains `NO_REFERENCE_ONLY` for all external
SILVER labels until the owner accepts a stage-gated change.

## Why a change is worth considering

The Issue #18 audit shows national SILVER products disagree in
structured, quantifiable ways driven by scale, boundaries, patch size
and protocol. That is an argument for **provenance-explicit** training
use, not for discarding SILVER labels: a shift-aware learner can treat
source and support as first-class context, provided evaluation
separation is guaranteed. With GOLD still at 0, SILVER labels can never
anchor final evaluation; they can anchor training and external
agreement studies.

## Recommended categories

| Category | Meaning | Permitted uses |
|---|---|---|
| `SILVER_TRAINING_ELIGIBLE` | Provenance VERIFIED; semantics VERIFIED_SPARTINA; license permits internal research use; leakage-safe partition exists | Self-supervised/supervised training inputs; per-source/per-year heads; shift augmentation; NOT held-out evaluation |
| `EXTERNAL_REFERENCE_ONLY` | Provenance/semantics verified, but source is used as a comparator, or license/provenance limits training, or leakage separation not yet encoded | Cross-product agreement/scale studies (e.g. Issue #18); contextual covariates; never training targets |
| `FINAL_GOLD_EVAL_ONLY` | Reserved for GOLD-tier data (field/UAV/expert verified) | Final evaluation only; never training; none exists today (GOLD = 0) |

Current products map conservatively as: GEODATA family and CMSA
2017–2021 and CM-SSM stay `EXTERNAL_REFERENCE_ONLY` under this note;
they become `SILVER_TRAINING_ELIGIBLE` only after the gates below.
`gridcode-0` CMSA features remain UNKNOWN/TODO_VERIFY and are eligible
for nothing.

## Gates before any SILVER label may enter training

1. **Manifest gate.** Dataset manifest and registry row complete:
   checksum, provider, license, semantic status, repair/transform
   provenance chain.
2. **Semantics gate.** Positive class independently reproduced from
   bytes; known defects enumerated; no silent non-Spartina conversion
   of UNKNOWN values.
3. **Leakage gate.** Spatial-block partition (W10-cell or larger
   grouped units) passes `src/spartina/evaluation/splits.py` leakage
   checks; all scenes of one location across dates stay in one split;
   test blocks never enter hyperparameter selection.
4. **Evaluation-separation gate.** Any block or region used for
   external-reference analysis that also motivates model choices is
   either excluded from training or replaced by disjoint blocks; the
   chosen partition version is recorded per experiment.
5. **Source-attribution gate.** Training records carry product id,
   year, nominal support and protocol; no mixing of sources into one
   pseudo-ground-truth target without a source channel.
6. **License gate.** Redistribution and output-deployment constraints
   checked per product; GEODATA terms are RESTRICTED_RESEARCH_ONLY.
7. **Owner gate.** Stage approval recorded against the registry;
   category changes are versioned, never edited in place.

## What explicitly does NOT change now

- No registry value is changed by this note.
- No model training starts with SILVER labels in Issue #18.
- SILVER agreement never produces an "accuracy" claim; final evaluation
  remains GOLD-only.
- Contested-domain and PROVISIONAL W10 cells add no eligibility until
  Issue #17 owner sign-off.
