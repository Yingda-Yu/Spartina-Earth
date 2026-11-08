# R6 Baseline Inventory — EarthArXiv Preprint Finalization

**Date:** 2026-11-08
**Auditor:** R6 execution round (automated, evidence-based)
**Purpose:** Establish the verified starting state for the R6 EarthArXiv
preprint finalization round. Supersedes nothing; extends the R5 record.

---

## 1. Git baseline (verified live)

| Item | Value | Evidence |
|---|---|---|
| Branch | `feat/paper1-map-reliability` | `git branch --show-current` |
| HEAD | `e963b4a` ("R5: update manuscript Git reference to 948c17c") | `git log -8 --oneline` |
| R5 main commit | `948c17c` ("R5: IJRS submission-targeted finalization", +3246/−429, 19 files) | `git log` |
| R4 commits | `3ed17a8` (R4 main), `b84feda` (docs follow-up) | `git log` |
| Remote sync | In sync with `origin/feat/paper1-map-reliability` (no ahead/behind) | `git status -sb` after `git fetch origin --prune` |
| Merge state | **NOT merged into main** (per standing rule) | branch intact |

**Correction to the R6 brief:** the brief's stated baseline `b84feda` is the
R4 docs commit. The actual verified baseline is `e963b4a`; R5 was completed
and pushed in the prior session. No R5 work is lost or unpushed.

## 2. Working-tree state

| Path | State | Disposition |
|---|---|---|
| `submission/ijrs/latex_source/main.tex` | Modified (1 line): Git-reference commit `3ed17a8` → `948c17c` | Correct leftover follow-up matching canonical `main.tex` (updated in commit `e963b4a`). Will be committed during R6. Not overwritten. |
| `SpartinaGuard/` (repo root) | Untracked | Per standing rule, never commit. |
| `_incoming_task.txt` (repo root) | Untracked (transient) | Never commit. |

No other agent's uncommitted work exists in the tree.

## 3. Manuscript and package inventory (verified live via `find`)

### 3.1 Canonical manuscript

| Item | Value |
|---|---|
| `manuscript/main.tex` | Present; title "Spatial Agreement and Regional Uncertainty in Multi-Source Maps of *Spartina alterniflora* along the Chinese Coast" |
| `manuscript/main.pdf` | **32 pages**, letter, 595 KB (`pdfinfo`) |
| `manuscript/references.bib` | 17 entries, all verified in R5 (12 fabricated entries removed) |
| Abstract | 281 words |
| Figures included | 8 (PDF+PNG in `figures/`) |
| Tables included | 12 (`tables/*.tex`) |
| Supplementary | `supplementary/supplementary_information.tex` + PDF (§S1) |
| Undefined refs (last R5 build) | 0 |

### 3.2 Directories

- `audits/` — 16 audit files R1–R5 (incl. `r5_ijrs_journal_requirements.md`,
  `r5_figure_table_qa.md`, `r5_ijrs_peer_review.md`, `r5_submission_declarations.md`,
  R4 attribution/coverage/South-China audits).
- `experiments/` — 21 scripts incl. E3–E7, R4 suite, figure generators
  (`e6_agreement_map.py`, `r4_fig03_upgrade.py`, `r4_region_assignment_figure.py`,
  `r4_south_china.py`).
- `results/` — 27 CSV/JSON result files incl. `e5e_bootstrap_100m.csv`,
  `r4_region_assignment_sensitivity.csv`, `r4_bootstrap_regional.csv`,
  South-China diagnostics; `superseded_e5_longitude_bands/` preserved.
- `figures/` — 8 figures as PDF+PNG pairs (fig03 agreement map, fig04 stats,
  fig05 regional IoU + resolution, fig06 robustness, fig_r4_* ×4).
- `submission/ijrs/` — complete R5 IJRS package (PDF, LaTeX source, TIFFs,
  cover letter, statements, checklists). **Retained; not deleted** — IJRS remains
  the recorded secondary possibility for a journal permitting preprints.
- `literature/r5_ijrs_related_work_matrix.md`.
- `PROGRESS.md` — R5 section is the authoritative prior-round record.

## 4. Data versions (unchanged since R4/R5)

| Dataset | Version/reference | Notes |
|---|---|---|
| CMSA | 2020 vector (`CMSA_2020.shp`), 10 m, 2017–2021 series | `gridcode=0` treated as UNKNOWN, not absence |
| GEODATA | 2020 raster layer, 30 m, presence-only, uniform 255 fill | No valid-observation domain |
| CM-SSM | 2020 sub-meter patch vectors (148,072 patches) | Zenodo DOI 10.5281/zenodo.16296823 (license conflict open) |
| Harmonization grid | EPSG:3410 equal-area, 100 m primary | — |

## 5. Verified key numbers carried from R4/R5 (to be re-audited in R6-03)

- National IoU @100 m: CMSA–CM-SSM 0.5395 [0.5096, 0.5708]; CMSA–GEODATA
  0.4444 [0.4128, 0.4733]; CM-SSM–GEODATA 0.3432 [0.3139, 0.3714].
- Bohai/Yellow-vs-South-China IoU ratio 4.18 [2.74, 7.51] (CMSA–GEODATA);
  survives policies A/C5/C10/C20/B at 4.06–4.18.
- 34.42 % of positive-union pixels nearest-assigned (median 6.83 km).
- Coverage-normalized IoU: NOT computable (no valid-observation domain).
- South China: displacement-consistent disagreement (40–53 % within 1 km).
- No GOLD reference → accuracy not assessable (agreement ≠ accuracy).

## 6. Open issues carried into R6

1. **Owner-dependent metadata (BLOCKER-class until Owner confirms):** ORCID;
   funding; competing-interest wording; generative-AI-use declaration;
   formal English legal name of "Spartina Technology" (affiliation 2).
2. **Dataset licensing:** CMSA license UNVERIFIED (provider contact needed);
   GEODATA license presumed CC-BY-NC-ND, unconfirmed; CM-SSM mirror-license
   conflict. R6-07 re-audits all three and adds Natural Earth basemap data.
3. **Cartography (R6 highest priority):** current maps lack full geographic
   context (coastlines, admin boundaries, graticules, scale bars, locators).
   Figures 1–5 to be redesigned per the R6 brief §4 with a unified,
   colorblind-safe, grayscale-safe academic design system; Natural Earth
   as the licensed basemap source.
4. **Preprint repositioning:** manuscript currently framed for IJRS; needs
   EarthArXiv-appropriate front matter (real author block per Owner
   instruction: single author Yingda Yu, Wenzhou-Kean University +
   Spartina Technology, corresponding yuying@kean.edu), plus fresh
   EarthArXiv policy verification (R6-06).

## 7. Environment notes (verified prior rounds)

- Python: `/data/yingda/software/miniconda3/envs/spartina-earth/bin/python3.11`;
  `PROJ_lib` under that env; `MPLCONFIGDIR=/data/yingda/Spartina-Earth/work/tmp_mpl`.
- Tests: `python3.11 -m pytest tests -q` → 588 passed / 21 skipped (~76–91 s).
- LaTeX: `pdflatex -interaction=nonstopmode main.tex` + `bibtex main` + 2 passes.
- Long-running shell commands must run FOREGROUND (background shells get killed).
- `.gitignore` excludes `papers/**/*.pdf`, `*.tif` — PDFs/TIFFs are disk-only
  artifacts; pre-commit hook blocks files > 1 MiB.

**R6-01 verdict: baseline verified and safe to proceed.**
