# R6 Scientific Integrity Audit — Final Pre-Publication Verification

**Date:** 2026-11-08
**Scope:** Every primary numerical claim in `manuscript/main.tex` re-verified
against committed result artifacts (R4 post-commit provenance runs at Git
commit `f2c7368`, recorded in `results/*_meta.json`). No new experiments were
designed or run; per the R6 brief, existing reproducible results were audited
in place.

---

## 1. National IoU and 95 % bootstrap CIs (100 m, EPSG:3410)

| Claim in manuscript | Source artifact | Verdict |
|---|---|---|
| CMSA–CM-SSM IoU 0.5395, CI [0.5096, 0.5708] | `results/e5e_bootstrap_100m.csv`, pair CMSA_vs_CMSSM, National, block 2 km: exact 0.5395, ci 0.5096/0.5708 | **PASS** |
| CMSA–GEODATA IoU 0.4444, CI [0.4128, 0.4733] | same file, CMSA_vs_GEODATA, National, 2 km: 0.4444, 0.4128/0.4733 | **PASS** |
| CM-SSM–GEODATA IoU 0.3432, CI [0.3139, 0.3714] | same file, CMSSM_vs_GEODATA, National, 2 km: 0.3432, 0.3139/0.3714 | **PASS** |

Method (verified in `experiments/e5e_bootstrap_100m.py`): spatial block
bootstrap, 2 km primary blocks, 1000 replicates, seed 202601; MC seed
sensitivity < 0.003 on CI endpoints (recorded in CSV). Reproduction:
`python experiments/e5e_bootstrap_100m.py` (foreground, ~long).

## 2. National area range (2020)

| Claim | Source | Verdict |
|---|---|---|
| 519.89–593.71 km², differ by 14.2 % | `results/area_summary.json`: GEODATA 519.8913, CM_SSM_planar 593.7098, CMSA 571.3516; (593.71−519.89)/519.89 = 14.2 % | **PASS** |
| GEODATA 2020 = 577,657 px = 519.89 km² | `results/r4_coverage_meta.json` geodata_entity value_counts (1: 577,657; presence_area 519.89) | **PASS** |
| CM-SSM 148,072 patches, 593.71 km² planar | `r4_coverage_meta.json` vector_entities.CMSSM n_patches 148,072; area_summary | **PASS** |

## 3. Regional contrast (Bohai/Yellow vs South China)

| Claim | Source | Verdict |
|---|---|---|
| Ratio 4.18, CI [2.74, 7.51], p<0.001 (CMSA–GEODATA, policy B) | `results/e5e_region_contrasts_100m.csv`: 4.175, [2.74, 7.513], p=0.0 | **PASS** |
| Ratio 4.37 (CM-SSM–GEODATA) | same file: 4.367 [2.643, 9.096] | **PASS** |
| CMSA–CM-SSM statistically indistinguishable from unity | same file: 0.978 [0.805, 1.185], p=0.876 | **PASS** |
| Policy stability 4.06–4.18 (CMSA–GEODATA) | `results/r4_region_contrasts_policy.csv`: A 4.090 [2.576, 9.803]; C5 4.058 [2.731, 7.066]; C10 4.116 [2.672, 7.151]; C20 4.150 [2.775, 7.409]; B 4.175 [2.74, 7.513] — all CIs exclude 1 | **PASS** |
| Policy stability 4.37–4.64 (CM-SSM–GEODATA) | same file: A 4.644; C5 4.556; C10 4.630; C20 4.620; B 4.367 | **PASS** |
| CMSA–CM-SSM 0.98–1.04 across policies | same file: 1.016, 1.029, 1.023, 1.041, 0.978 | **PASS** |
| Absolute regional IoU shifts ≤ 0.05, no rank reversal | `results/r4_region_assignment_sensitivity.csv` + policy CSV; e.g. CMSA–GEODATA East China 0.3439 (A) vs 0.3923 (B), Δ=0.048; region ordering unchanged in all rows | **PASS** |

## 4. Attribution of positive pixels outside sea polygons

| Claim | Source | Verdict |
|---|---|---|
| 34.42 % of positive-union pixels nearest-assigned | `results/r4_attribution_meta.json`: 31,201/90,641 = 34.42 % | **PASS** |
| East China receives 22,262 assigned px = 44.9 % of its union (policy B) | `r4_region_assignment_sensitivity.csv` B row East_China: assigned 22,262, share 44.88 % | **PASS** |
| East China median assignment distance 6.83 km; p99 50.4 km | `r4_attribution_meta.json` region_distance_summary East_China: 6.825 / 50.413 | **PASS** |
| South China median 1.61 km | same: 1.612 | **PASS** |
| Max assignment distance 54.0 km | same: dist_max 53.968 (Bohai/Yellow) | **PASS** |
| East China pixels beyond 50 km | `r4_attribution_meta.json`: East_China n_beyond_50km = **237** | **FAIL → FIXED** |

**Fix record (R6):** manuscript previously stated "478 East China pixels lie
beyond 50 km" — 478 is the Bohai/Yellow count; East China is 237. Corrected in
`manuscript/main.tex` (attribution-policy sensitivity paragraph). No other
occurrence of the erroneous number exists (grep verified).

## 5. South China diagnostics

| Claim | Source | Verdict |
|---|---|---|
| GEODATA maps largest South China extent 26.31 vs CMSA 19.27, CM-SSM 14.69 km² | `results/r4_south_china_diagnostics.csv` | **PASS** |
| 40–53 % of disagreement pixels within 1 km of the other product | same file: only_a_within_1km 47.26/44.84; only_b_within_1km 53.39/40.0 | **PASS** |
| 28–44 % beyond 5 km | same file: 28.75/29.25/29.4/44.41 | **PASS** |
| Displacement "consistent with, not conclusively sole cause" | Manuscript wording verified in 4 locations (R5 audit, unchanged) | **PASS** |

## 6. Coverage-normalized IoU: correctly NOT computed

| Check | Source | Verdict |
|---|---|---|
| GEODATA presence-only with uniform 255 fill (absence vs no-data indistinguishable) | `r4_coverage_meta.json` verdict: `coverage_normalized_iou_computable: false`; value_counts 1/255 only | **PASS** |
| Manuscript does not claim coverage-normalized IoU | main.tex reports footprint-proximity proxies instead | **PASS** |
| Proxy: 17.6 % GEODATA positives > 5 km from any CM-SSM positive; 8.1 % vs CMSA | `r4_coverage_meta.json` distance_statistics: 17.58 / 8.12 | **PASS** |
| Strip-level footprint gaps ≤ 0.28 % | `results/r4_coverage_strips.csv` (audited in R4; consistent) | **PASS** |

## 7. Processing sensitivity

| Claim | Source | Verdict |
|---|---|---|
| Resolution 30/50/100 m negligible (IoU changes ≤ 0.4 %) | `results/iou_dice_2020_multi_res.csv`: 0.5375/0.5371/0.5395 etc. | **PASS** |
| Grid origin shifts ±100 m negligible | `results/robustness_2020.csv` shift rows: Δ ≤ 0.001 | **PASS** |
| Coastline buffer 0–50 km negligible | `robustness_2020.csv` buffer rows: Δ ≤ 0.003 | **PASS** |
| Rasterization rule (all_touched) shifts mixed vector–raster IoU by up to 29 % | `robustness_2020.csv`: CM-SSM–GEODATA 0.3415 → 0.2418 (−29.2 % rel.); CMSA–GEODATA 0.4437 → 0.3456 (−22.1 %); manuscript states "22–29 %" | **PASS** |

## 8. Integrity principles (semantic checks)

| Principle | Status |
|---|---|
| CMSA `gridcode=0` treated as UNKNOWN, never absence (50 such polygons excluded) | **PASS** — main.tex data section + `r4_coverage_meta.json` gridcode_counts |
| GEODATA 255 never treated as valid absence | **PASS** — explicit in methods and coverage audit |
| No coverage-normalized IoU claimed | **PASS** (Section 6 above) |
| Agreement never called accuracy; IoU never labelled "accuracy" | **PASS** — grep-verified; abstract/discussion distinguish the two |
| No claim that one product is more accurate (no GOLD reference) | **PASS** — disclosed as scope limit |
| Single-cause attribution of spatial differences avoided | **PASS** — displacement wording hedged |
| CRS/area consistency (EPSG:3410 equal-area; planar areas flagged) | **PASS** |
| No TODO_EXPERIMENT / invented numbers in tables | **PASS** (R5 check; re-grepped clean in R6) |

## 9. Reproduction commands (documented, not re-run in R6)

```
python3.11 experiments/e3_spatial_agreement.py        # area + multi-res IoU
python3.11 experiments/e5e_bootstrap_100m.py         # national/regional bootstrap
python3.11 experiments/r4_region_attribution.py       # policies A/B/C (runtime ~54 min)
python3.11 experiments/r4_coverage_agreement.py       # coverage verdict (~6 min)
python3.11 experiments/r4_south_china.py             # South China diagnostics
python3.11 experiments/r4_bootstrap.py                # policy-contrast bootstrap
```
All artifacts carry `git_commit` in their `*_meta.json` (R4 provenance runs at
`f2c7368`). Seed 202601 throughout. R6 verified numbers **from these committed
artifacts**, which is the appropriate reproduction level for a consolidation
round; full recomputation is wired and available but was not re-executed to
avoid redundant heavy runs (per R6 brief §3).

## 10. Verdict

**One numerical error found and fixed** (237 vs 478 pixels beyond 50 km,
§4). All other primary claims — national IoUs and CIs, area range, regional
ratios and their policy robustness, attribution statistics, South China
diagnostics, coverage limitations, and processing sensitivities —
**PASS against committed result artifacts**, and all eight semantic integrity
principles of the R6 brief are correctly implemented in the manuscript.
