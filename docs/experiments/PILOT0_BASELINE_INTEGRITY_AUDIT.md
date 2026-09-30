# Pilot-0 Baseline Integrity Audit — Issue #10 (M1.5a)

Date: 2026-09-30. Branch: `reboot/spartina-earth-m0`.
Scope gate: **no retraining, no re-prediction on TEST, no threshold
re-tuning**. Only frozen checkpoints (scored on VALIDATION mosaics),
stored `val_metrics.json` / `test_metrics.json`, run manifests, the
registry, `FINAL_EVAL_LOCK.json` and training source code were used.

**Verdict: ENGINEERING_VERIFIED / SCIENTIFICALLY_LIMITED.**
No implementation defect affecting official results was found. The
freeze document `PILOT0_BASELINE_FREEZE_V1.json` is emitted. Scientific
interpretation remains limited by SILVER-only labels, one region,
UNKNOWN legacy-composite acquisition dates, and a 7-window / 5-patch
TEST geography.

Machine-generated evidence (all produced by
`scripts/experiments/pilot0/audit/run_audit.py` from raw artifacts):

| File | Content |
|---|---|
| `pilot0_run_accounting.csv` | All 54 manifests: official vs smoke, status, TEST-record flags |
| `pilot0_collapse_forensics.csv` | 12 SegFormer runs, TRAIN/VAL forensics + classification |
| `pilot0_rf_audit.csv` | 12 RF runs, VAL probability / class-column / ranking audit |
| `pilot0_index_distributions.csv` | NDVI/SAI distributions vs SILVER label (TRAIN/VAL) |
| `pilot0_index_probes.csv` | MI + logistic probes (TRAIN fit, VAL eval) |
| `pilot0_metrics_audit.csv` | Strict rebuild of every val/test metric row (98 rows) |
| `pilot0_variant_deltas.csv` | Per model/seed/split variant contrasts |
| `pilot0_model_means.csv` | Mean/SD with collapsed runs retained |
| `pilot0_stress_audit.csv` | 9 full neural runs × 3 drop modes × 2 views |
| `pilot0_component_sensitivity.csv` | Static SILVER census + stored aggregates + NOT_PERSISTED list |

---

## A1. Run accounting — 49 official runs, exact reconciliation

Disk contains **54 run manifests = 49 official COMPLETED + 5 smoke**
(3 `SMOKE_OK`, 2 early `FAILED` U-Net smoke runs). No diagnostic runs
exist; nothing extra is mixed into official statistics.

| Model | Official runs |
|---|---:|
| SAI rule (`sai` / `spectral_sai`, deterministic) | 1 |
| Random Forest | 12 (4 variants × seeds 17/42/2026) |
| U-Net | 12 |
| DeepLabV3+ | 12 |
| SegFormer-B0 | 12 |
| **Total** | **49** |

Triple mapping verified with hard failures
(`src/spartina/audit/accounting.py::reconcile`):

* `FINAL_EVAL_LOCK.json` run list == 49 official COMPLETED manifests ==
  official rows in `docs/experiments/registries/pilot0_registry.csv` ==
  49 stored `test_metrics.json`;
* no duplicate run keys; every non-official run has **no** TEST record;
* checkpoint SHA256, VAL threshold and config hash match the lock for
  every run.

Lock hash: `b80e86abf65fbafb00e2d5d669164430a7619bca124e497051eec1b36b7769a5`.

Smoke runs retained for traceability (excluded from all means):
`unet_optical_seed-17_20260927T075110Z` (FAILED),
`unet_optical_seed-17_20260927T075139Z` (FAILED),
`unet_optical_seed-17_20260927T075208Z`,
`deeplabv3plus_optical_seed-17_20260927T075248Z`,
`segformer_b0_optical_seed-17_20260927T075312Z` (SMOKE_OK).

### The "14/14 thresholds at 0.05" statement

The number 14 is correct; the attribution was not. The 14 official runs
whose VAL-optimal threshold sits on the 0.05 grid floor are **12 Random
Forest runs + U-Net optical_sar/seed 2026 + DeepLabV3+ optical_sar/seed
2026**. The Issue #5 report phrase "(all Random Forest)" was wrong and
has been corrected in `PILOT0_BASELINE_REPORT.md` §11.

---

## A2. SegFormer collapse forensics — TRAIN/VAL only

Definition used throughout: **collapse** = stored TEST arbitrated-core
recall < 0.15 (read-only stored metric; never re-evaluated). Four runs
qualify:

| Variant | Seed | best epoch | best VAL IoU | VAL thr | VAL pos-ref mean prob | TEST recall | Classification |
|---|---:|---:|---:|---:|---:|---:|---|
| full | 42 | 7 | 0.553 | 0.50 | 0.589 | 0.037 | SMALL_DATA_STOCHASTIC_COLLAPSE |
| optical | 17 | 7 | 0.515 | 0.46 | 0.537 | 0.039 | SMALL_DATA_STOCHASTIC_COLLAPSE |
| optical | 42 | 14 | 0.551 | 0.58 | 0.636 | 0.000 | SMALL_DATA_STOCHASTIC_COLLAPSE |
| optical_sar | 42 | 79 | 0.752 | 0.19 | 0.646 | 0.095 | SMALL_DATA_STOCHASTIC_COLLAPSE |

The other 8 runs are `NO_COLLAPSE` (TEST recall 0.61–0.96).
**Zero `IMPLEMENTATION_DEFECT`, zero `OPTIMIZATION_INSTABILITY`, zero
`THRESHOLD_OR_CALIBRATION_PATHOLOGY`.**

### Implementation checks (all pass; code + frozen artifacts)

| Check | Result |
|---|---|
| Target-positive pixels enter TRAIN windows | 8,353 SILVER px across 94 windows (same static count every run) |
| Target-positive pixels in VAL mosaic | 3,653 px |
| First-layer inflation at construction | `inflation_init_max_abs_err = 0.0` for all 12 runs (mean-RGB kernel ×3/C rule applied exactly; per-channel spread 0) |
| First layer actually trained | trained weight drift from init 0.002–0.014 (not frozen) |
| State dict coverage | 0 missing, 0 unexpected keys; strict load |
| Segmentation head | single output class (`[1, 256, 1, 1]`) |
| NaN/Inf in recorded history | none; all train-loss and VAL-IoU series finite; no NaN-abort runs |
| IGNORE / WEAK mask logic | identical for all three neural models — shared `Pilot0WindowDataset` + `segmentation_loss` (validity-masked BCE and Dice); no model-specific code path |
| Channel order / normalization | identical for all three — `VARIANT_BANDS[variant]` index into the same normalized grid |
| Optimizer coverage | one `AdamW(model.parameters(), lr, weight_decay=0.01)` over **all** parameters (input projection + encoder + decode head); no param-group exclusions, no `requires_grad=False` anywhere in the SegFormer builder |

### Why the four runs are small-data stochastic collapses, not defects

* All implementation invariants above also hold for the collapsed runs.
* Their TRAIN targets and masks were identical to successful runs.
* Their own VAL mosaics were scored with the **frozen** checkpoints:
  VAL IoU 0.51–0.75, positive-reference mean probability 0.54–0.65,
  finite broad probability ranges — the models learned the in-region
  signal and their VAL-selected thresholds are interior (0.19–0.58),
  not boundary artefacts.
* Failure appears only against the out-of-region 5-patch TEST mosaic.
* Seed pattern: seed 42 collapses in 3 of 4 variants (full, optical,
  optical_sar) yet succeeds with optical_indices (TEST recall 0.89);
  seeds 17/2026 succeed in 6 of 8 variant combinations. This
  seed × variant interaction on 94 training windows is the signature of
  high-variance optimization on small data, not a swapped label or a
  broken layer.
* Mechanism nuance retained in the CSV: `full/42` and `optical/17` have
  mediocre VAL separation (VAL Brier ≈ 0.087–0.090, probability medians
  0.22–0.23) — weak fits that nevertheless generalized on VAL;
  `optical_sar/42` is the opposite pattern — sharp, confident, VAL-strong
  (IoU 0.752) but TEST recall 0.095: over-specialization to the VAL
  geography. Both are subsumed under small-data stochastic failure given
  n_train = 94 windows.

### Engine evidence gaps (NOT RECORDED, not reconstructed)

The Issue #5 engine did not persist per-step gradient norms, AMP
`GradScaler` events, per-batch losses, or per-epoch validation loss.
These are explicitly `False`/unrecorded columns in
`pilot0_collapse_forensics.csv`; NaN status is inferred only from the
finite recorded series (all finite) and from the fact that a non-finite
loss triggers `ctx.fail("non-finite loss …")` (no official FAILED run
exists). Logging these is an evaluation-v1.1 recommendation.

---

## A3. Random Forest low-threshold audit — no class/score inversion

Frozen `rf.joblib` of all 12 RF runs was reloaded on CPU and scored on
the VAL arbitrated-core mosaic (`pilot0_rf_audit.csv`):

* `rf.classes_ == [0, 1]` for every run; the positive score column is
  selected explicitly via `np.flatnonzero(rf.classes_ == 1)`
  (`src/spartina/models/baselines/random_forest.py`) — column index 1,
  no class inversion, no score-column swap. Training labels are the
  SILVER mask (1 = Spartina) on TRAIN-unique arbitrated-core pixels.
* The VAL threshold-grid optimum recomputed from the frozen model
  **matches the stored threshold (0.05) for all 12 runs**.
* Ranking quality is good: VAL AUROC 0.870–0.923, AUPRC 0.716–0.820
  against a 12.3–12.6 % positive base rate (≈5.8–6.6× lift). The 0.05
  threshold is therefore a **probability-scale/calibration** phenomenon,
  not a ranking failure.
* Probability mass: ≈92.6–93.1 % of VAL pixels score below 0.05. With
  `class_weight="balanced_subsample"`, 500 trees and
  `min_samples_leaf=2`, leaf votes are concentrated near zero; the
  probabilities are not assumed calibrated.
* The 400k-pixel subsample cap never binds (fitted 140,754–144,083 of
  the same-sized TRAIN domain; only 1,606 positive pixels, ≈1.1 %).
* Brier on VAL ≈ 0.084–0.085 across variants.

Conclusion: no code bug; the predeclared threshold protocol is
unchanged. The lower-bound threshold must be reported as a calibration
property of the class-weighted RF on this pixel distribution.

---

## A4. Index dependence — useful signal, strong label association, no causal claim

### Variant contrasts on TEST core IoU (per seed; means in the CSV)

Δ = variant minus baseline; positive = improvement.

| Model | Seed | +indices | +SAR | SAR marginal (full − +indices) | full − optical |
|---|---:|---:|---:|---:|---:|
| U-Net | 17 | +0.060 | −0.040 | −0.153 | −0.093 |
| U-Net | 42 | +0.032 | −0.097 | −0.023 | +0.008 |
| U-Net | 2026 | +0.115 | +0.149 | −0.187 | −0.072 |
| DeepLabV3+ | 17 | +0.045 | +0.009 | −0.140 | −0.095 |
| DeepLabV3+ | 42 | −0.058 | −0.199 | +0.049 | −0.009 |
| DeepLabV3+ | 2026 | +0.036 | −0.047 | −0.045 | −0.009 |
| SegFormer-B0 | 17 | +0.764 | +0.467 | −0.171 | +0.592 |
| SegFormer-B0 | 42 | +0.667 | +0.085 | −0.639 | +0.028 |
| SegFormer-B0 | 2026 | +0.106 | +0.075 | −0.096 | +0.010 |
| Random Forest | 17 | −0.010 | −0.009 | +0.005 | −0.005 |
| Random Forest | 42 | −0.004 | −0.003 | +0.003 | −0.001 |
| Random Forest | 2026 | +0.011 | +0.004 | −0.007 | +0.004 |

(ΔF1, ΔAUPRC, ΔBrier, ΔECE, Δarea-bias and VAL versions in
`pilot0_variant_deltas.csv`.)

* **Indices gain is not cross-model stable on TEST**: clearly positive
  for U-Net (+0.069 mean IoU; +0.045 F1; Brier/ECE improve on every
  seed), small/positive for DeepLabV3+ (+0.008), effectively zero for
  RF (−0.001; AUPRC +0.011), and large but collapse-confounded for
  SegFormer (the optical cell contains 2 collapsed seeds; among
  non-collapsed seeds the gain is +0.106 to +0.764).
* On VAL, +indices is positive for every neural model (U-Net +0.056,
  DeepLabV3+ +0.028, SegFormer +0.090 mean IoU), so the U-Net gain is
  not a TEST-only fluctuation.
* Adding SAR on top of indices (full − optical_indices) is negative in
  8/9 neural seed-rows on TEST (range −0.639…+0.049).

### Are NDVI/SAI a label proxy? Association diagnostics (TRAIN/VAL only)

VAL distributions (arbitrated_core, n = 29,118; 3,653 positive):

| Feature | Class | p05 | median | p95 |
|---|---|---:|---:|---:|
| NDVI | Spartina | 0.144 | 0.265 | 0.404 |
| NDVI | background | −0.129 | 0.034 | 0.194 |
| SAI | Spartina | −0.576 | −0.419 | −0.249 |
| SAI | background | −0.336 | −0.104 | −0.015 |

Diagnostic probes (fit on TRAIN-unique pixels, evaluated on VAL):

| Probe | VAL AUPRC | VAL best-threshold IoU | I(feat;label) bits | Pearson r (TRAIN) |
|---|---:|---:|---:|---:|
| NDVI only | 0.829 | 0.612 | 0.159 | +0.462 |
| SAI only | 0.805 | 0.595 | 0.158 | −0.480 |
| NDVI + SAI | 0.808 | 0.601 | 0.158 | +0.462 / −0.480 |

Interpretation (associational, not causal):

* Both indices are individually strongly associated with the SILVER
  label — a single linear index already reaches VAL IoU ≈ 0.60. A
  model *could* lean on them as a cheap shortcut, and this audit cannot
  rule that out from observational data.
* NDVI and SAI carry essentially redundant label information (equal MI,
  opposite-sign near-equal correlations; the bivariate logistic probe
  does not improve over NDVI alone).
* But "indices are useful" is also supported: all-neural VAL gains are
  positive, optical-only models plateau around 0.74–0.75 TEST IoU, and
  U-Net improves consistently on every seed.
* We therefore report both facts and do **not** claim indices are
  causally necessary. Distinguishing genuine complementary physics from
  a reference-product shortcut requires new evidence (cross-year /
  cross-region VAL and dated source scenes — Issue #6 prerequisites).

---

## A5. SAR contribution — neutral-to-negative here; dates UNKNOWN

TEST contrasts (table above): `optical → optical_sar` is ≈0 for RF
(−0.003 to +0.004 per seed), mixed for U-Net (−0.097/+0.149/−0.040),
negative for DeepLabV3+ (−0.199/+0.009/−0.047) and positive but
collapse-confounded for SegFormer. `optical_indices → full` is negative
for all three neural architectures on most seeds (U-Net −0.023/−0.153/
−0.187; DeepLab −0.140/+0.049/−0.045; SegFormer −0.171/−0.639/−0.096).
On VAL the same SAR contrasts are small-positive for the neural models,
so the TEST direction is not simply in-sample overfitting.

**Mandatory confounder statement:** the exact Sentinel-1 and Landsat
acquisition dates of the legacy Hangzhou composite are **UNKNOWN**.
Tidal state, inundation, phenology and sensor time gaps cannot be
controlled. Every SAR number here is reported strictly **"under the
current legacy composite"**; it must not be read as evidence that SAR is
intrinsically useless (or useful) for Spartina.

---

## A6. Missing-modality stress — deployment robustness, not feature importance

Mechanism verified in code: normalization is
`(clip(x) − train_mean)/train_std` with NaN filled by 0, and the stress
harness sets dropped **normalized** channels to exactly 0
(`src/spartina/evaluation/predict.py`). Zero ⇔ post-clip TRAIN mean, so
the stress is precisely train-mean imputation (identical encoding to a
missing input pixel).

All 9 full-variant neural runs × 3 drop modes were already stored in
`test_metrics.json`; full per-run values are in
`pilot0_stress_audit.csv`. TEST core IoU:

| Model / seed | full | drop indices | drop SAR | drop SAR+indices |
|---|---:|---:|---:|---:|
| U-Net 17 | 0.689 | 0.037 | 0.720 | 0.019 |
| U-Net 42 | 0.807 | 0.055 | 0.703 | 0.318 |
| U-Net 2026 | 0.589 | 0.020 | 0.556 | 0.045 |
| DeepLabV3+ 17 | 0.626 | 0.066 | 0.540 | 0.275 |
| DeepLabV3+ 42 | 0.775 | 0.337 | 0.704 | 0.422 |
| DeepLabV3+ 2026 | 0.710 | 0.519 | 0.619 | 0.522 |
| SegFormer 17 | 0.621 | 0.228 | 0.202 | 0.000 |
| SegFormer 42 | 0.028 (collapsed) | 0.006 | 0.028 | 0.000 |
| SegFormer 2026 | 0.599 | 0.125 | 0.006 | 0.004 |

* Dropping indices degrades every model on every seed (IoU deltas
  −0.023…−0.752), most catastrophically for U-Net. Dropping SAR is mild
  for U-Net/DeepLab (−0.10…+0.03) but severe for two SegFormer seeds.
* These are **deployment-robustness** numbers for a model trained with
  all modalities present. They are not causal feature importance and do
  not justify modality claims; they are direct evidence for future
  explicit modality-dropout / missing-modality training.

---

## A7. TEST fragility — dominance quantified; LOCO not reconstructable

Static label census on the frozen split geometry (no predictions used):

* TEST = 7 windows.
* **5 full-grid SILVER ecological patches** intersect TEST coverage:
  `silver-0015`, `silver-0018`, `silver-0023`, `silver-0024`,
  `silver-0025`.
* Window/guard-band gaps fragment them into **12 reference pieces** in
  the evaluated mosaic (8 pieces ≥ 10 px; 4 small pieces) — this is why
  stored `patch_025.n_ref = 12`. The two conventions describe the same
  geography at different connectivity scopes.

| Component | Total px (grid) | Covered px | Core px in TEST windows | Share of 1,413 ref px | Fragments |
|---|---:|---:|---:|---:|---:|
| silver-0015 | 2,818 | 1,522 | 1,045 | **74.0 %** | 4 |
| silver-0023 | 353 | 353 | 240 | 17.0 % | 1 |
| silver-0025 | 264 | 264 | 123 | 8.7 % | 5 |
| silver-0018 | 89 | 10 | 2 | 0.1 % | 1 |
| silver-0024 | 18 | 18 | 3 | 0.2 % | 1 |

**The headline IoU is strongly controlled by one patch** (≈3/4 of
positive pixel support). A leave-one-component-out IoU would be the
direct answer, but:

* `final_eval.py` persisted only aggregate `evaluate_view` output. The
  stitched TEST probability raster, hard predictions and per-component
  match lists were **not written to disk**.
* Recomputing per-component IoU or LOCO therefore requires re-running
  inference on TEST, which Issue #10 forbids. These quantities are
  marked **NOT_PERSISTED** in `pilot0_component_sensitivity.csv`; no
  numbers are fabricated and no spatial confidence interval is offered
  at n = 5 patches.
* Evaluation v1.1 must persist stitched probabilities and the
  component-match table before this question can be answered under a
  new, explicitly approved evaluation version.

The 7 covered WEAK-only material components do have stored per-component
response records for all 49 runs (`pilot0_weak_candidate_response.csv`;
diagnostic only, never accuracy).

---

## A8. Tables rebuilt from raw artifacts — hard-fail generator

`src/spartina/audit/tables.py` rebuilds every table from run manifests
and stored metric JSON and raises on any of: missing/duplicate official
run key, wrong seed/variant matrix, an official run missing val/TEST
records, a non-official run carrying TEST records, means computed over
fewer than 3 seeds (collapsed runs must stay in the denominator),
missing stress coverage (expected 9 runs × 3 drops × 2 views = 54
rows), or WEAK-response coverage other than 7 components × 49 runs.

The strict rebuild was cross-checked against the Issue #5 machine-
generated `pilot0_metrics.csv`: **98 rows (49 runs × val/test), all
compared IoU/F1/AUPRC/Brier/ECE/area-bias/precision/recall columns
match to 1e-12**. Mean/SD are recomputed; collapsed seeds are retained
(`collapsed_seeds` column; `n_seeds_in_denominator = 3` everywhere).
No table value is hand-entered.

---

## A9. Freeze decision

All gates passed → **freeze issued**: `PILOT0_BASELINE_FREEZE_V1.json`.

* Engineering status: **ENGINEERING_VERIFIED**
* Scientific status: **SCIENTIFICALLY_LIMITED**
* `freeze_sha256` (canonical over evidence content; the emission
  timestamp is recorded in the document but excluded from its hash, so
  re-running the audit on unchanged artifacts reproduces the same hash):
  **`7dc9da76b7b2d720d302d41e853ddf957ea66816d55b64885783adad586ee614`**
* Pinned: git commit, split logical fingerprint, normalization hash,
  FINAL_EVAL_LOCK hash, official-registry canonical hash, metrics/means/
  deltas table hashes (all in the JSON):
  split `1d178352…21dd80`, normalization `864c86e5…0e8d`,
  lock `b80e86ab…769a5`, registry `ebcba905…f60a`,
  metrics `da974769…cea3`, means `14671408…95a9`,
  deltas `65f07c13…3661`.
* The 4 collapsed SegFormer runs are listed by run ID and remain in all
  means.
* Declared limitations: NO GOLD labels; single region; nominal 2015 with
  actual composite acquisition dates UNKNOWN; 7 windows / 5 patches with
  one patch dominating; no spatial CI; stress tests are robustness, not
  causal importance.
* No run is INVALIDATED; no new TEST evaluation version is needed for
  engineering reasons. Any future v1.1 is driven by the documented
  persistence gaps, requires explicit approval, and must not reuse the
  v1 lock.
