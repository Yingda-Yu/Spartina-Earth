# R4-07 — Submission Readiness Audit

**Paper:** Multi-Source *Spartina alterniflora* Map Reliability
**Manuscript:** `papers/paper1_map_reliability/manuscript/main.tex`
**Auditor:** R4 agent pass, 2026-11-08
**Scope:** reference integrity, dataset citations and licensing, code/data
availability, author metadata, funding, and the separation of scientific
blockers from owner-confirmation items. Nothing in this audit fabricates
owner-dependent information; every open item is listed as such.

---

## 1. Verdict

**Not submission-ready.** The science content is internally consistent,
traceable to executed experiments, and now covers the R4 audits (attribution
robustness, coverage limitation, South China diagnostics). Submission is
blocked by (a) unresolved third-party license/citation verification for CMSA
and GEODATA, (b) owner-dependent front-matter items (affiliation, e-mail,
funding, competing interests), and (c) the standing absence of GOLD reference
data, which the manuscript already discloses rather than claims around.

## 2. Scientific blockers (independent of owner paperwork)

| # | Item | Evidence | Impact |
|---|---|---|---|
| S1 | No nationally representative GOLD reference data; accuracy is not assessable | `audits/feasibility_gate.md` (E7 BLOCKED); Limitations item 1; Abstract discloses agreement-vs-accuracy distinction | The paper can only claim *agreement* findings; already correctly framed |
| S2 | Coverage-normalized IoU not computable from delivered entities | `audits/r4_coverage_audit.md`; manuscript Section sec:coverage-audit states this explicitly with two proxies | Limits interpretation; disclosed as limitation, no claim inflation |
| S3 | CMSA license and redistribution terms unverified | `manuscript/main.tex` tab:data_inv/tab:licenses (`TODO_VERIFY`, UNVERIFIED, NO source-held); `DATA_LICENSE.md` | Legal blocker for publishing CMSA-derived statistics; requires provider contact, not just owner confirmation |
| S4 | GEODATA license recorded as `CC-BY-NC-ND?` (uncertain) in tab:data_inv vs `CC-BY-NC-ND` in tab:licenses/Data Availability | manuscript appendix tables; Data Availability section | License must be confirmed against the IGSNRR Data Open platform record before submission |
| S5 | CM-SSM "mirror-side license conflict flagged" in Data Availability; Zenodo DOI 10.5281/zenodo.16296823 stated | Data Availability; `DATA_LICENSE.md` | Conflict must be resolved or the DOI/licence statement adjusted |

None of S1–S5 can be closed by the agent; S3–S5 require the data owner or
provider. The manuscript does not claim beyond these limits (audited in
R4-05: no promotional claims, no invented ethics approvals, coverage
limitation stated rather than masked).

## 3. Owner-confirmation items (administrative)

| # | Item | Current state in manuscript |
|---|---|---|
| O1 | Author affiliation | `TODO_AFFILIATION` (\maketitle) |
| O2 | Corresponding e-mail | `TODO_EMAIL` |
| O3 | Funding statement | "conducted without external funding" — owner must confirm this is accurate and complete |
| O4 | Competing interests | "no conflicts of interest" declared — owner must confirm |
| O5 | Target journal (IJDE vs Remote Sensing) | Affects format, word limits, and reference style; undecided |
| O6 | CMSA provider contact for license verification (S3) and full citation (C1) | Owner action required |
| O7 | External domain-expert read of the regional interpretation | R3 independent review recommended this; not yet performed |
| O8 | Git commit reference in Section 6/Conclusions | Will be updated to the R4 commit in R4-08 (currently stale `ca11141`) |

## 4. Reference and citation integrity

- `references.bib`: 20 real entries; bibliography compiles with 0 undefined
  references as of R3.1 (to be re-verified at R4-08 compile).
- Placeholders found (all inside `references.bib`):
  - `an_1985_spartina`: `doi = {TODO_VERIFY_AN_1985_DOI}` — DOI must be
    verified or the `doi` field removed before submission.
  - `cmsa_2024_release`, `geodata_time_series`: notes contain
    `TODO_VERIFY` for provider documentation — full citations needed (O6).
  - Unused placeholder entries `TODO_CMSA_CITATION`,
    `TODO_GEODATA_CITATION`, `TODO_2026_admin_warning` exist in the bib but
    are **not cited** in main.tex, so they do not render. Hygiene: remove
    before submission or leave (harmless to output).
- In-text citation spot-check: all `\citet`/`\citep` keys used in main.tex
  exist in references.bib (no `TODO_CITATION` markers remain in the text).
- The appendix data-inventory table carries `TODO_VERIFY` for CMSA license —
  visible in the compiled PDF; acceptable for an internal draft but must be
  resolved before submission (S3).

## 5. Dataset citation completeness

| Dataset | Citation in manuscript | Verifiable DOI | Status |
|---|---|---|---|
| CM-SSM 2020 | Xu et al. 2025 (`xu_2025_cmssm`) + Zenodo DOI in Data Availability | 10.5281/zenodo.16296823 | OK (license conflict S5) |
| GEODATA | `huang_2017_china_spartin`… `geodata_time_series` note | none (institutional platform) | Needs full citation (O6) |
| CMSA | `cmsa_2024_release` note | none (on-request) | Needs license + citation (S3/O6) |
| Natural Earth marine polygons | credited (public domain) | n/a | OK |

## 6. Code and data availability

- Code: `papers/paper1_map_reliability/experiments/`, Apache-2.0 claim in
  Code Availability — consistent with repository licensing of code.
- Results: all CSVs referenced in the manuscript exist under
  `papers/paper1_map_reliability/results/` (R4 additions:
  `r4_region_assignment_sensitivity.csv`, `r4_assignment_distances.csv`,
  `r4_coverage_normalized_iou.csv`, `r4_south_china_diagnostics.csv`,
  `r4_south_china_fragmentation.csv`, `r4_south_china_clusters.csv`,
  `r4_bootstrap_regional.csv`, `r4_region_contrasts_policy.csv`,
  `r4_attribution_meta.json`, `r4_coverage_meta.json`,
  `r4_bootstrap_meta.json`).
- Source geometries are not redistributed — stated; required by licenses.
- Git reference updated to the R4 commit during R4-08 (O8).

## 7. Pre-submission checklist (for the owner)

1. Confirm/resolve S3, S4, S5 (provider contact; license statements).
2. Fill O1, O2; confirm O3, O4.
3. Decide O5 (journal), reformat references accordingly.
4. Verify the `an_1985_spartina` DOI; complete CMSA/GEODATA citations.
5. Commission O7 (external expert read).
6. After R4-08 commit: verify the Git hash and branch statement in the
   Conclusions and re-compile.
