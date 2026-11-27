# R5-08 — Submission Declarations, Licensing and Owner-Confirmation Checklist

**Journal:** International Journal of Remote Sensing (subscription route)
**Date:** 2026-11-08
**Principle:** nothing owner-dependent is invented; every open item is listed
for owner action. This file supersedes the administrative sections of
`audits/r4_submission_readiness.md` for the IJRS submission.

---

## 1. Dataset licensing verification status

| Dataset | License on record | Verification status | Submission consequence |
|---|---|---|---|
| CMSA 2017–2021 (CAS) | TODO_VERIFY (unknown) | **UNVERIFIED** — provider contact required | Aggregated statistics publication is asserted in the draft but source terms must be confirmed by the data provider before submission; no redistribution of source geometries occurs in any deliverable |
| GEODATA 1990–2020 (IGSNRR) | CC-BY-NC-ND (recorded with "?" in appendix) | **UNCERTAIN** — confirm against the IGSNRR Data Open platform record | If CC-BY-NC-ND holds: non-commercial scientific publication is permitted with attribution and no derivatives of the source; only aggregated numbers and derived statistics are used |
| CM-SSM 2020 (CNU, Xu et al.) | Zenodo DOI 10.5281/zenodo.16296823, CC-BY-4.0; NESDC mirror shows CC-BY-NC-4.0 | **CONFLICT** between deposit and mirror | Cite the Zenodo deposit (authoritative record) with its CC-BY-4.0; resolve the mirror conflict or note it; verify DOI resolves before submission |

Redistribution policy in all deliverables: source geometries and rasters are
never redistributed; only aggregated numerical results, statistics and
figures rendered from harmonized grids. This is stated in the manuscript Data
Availability section.

## 2. Dataset citations still to be completed (owner/provider action)

- **CMSA formal citation**: the manuscript currently cites
  `cmsa_2024_release` (institutional release note) because no peer-reviewed
  or formal data-paper citation has been verified. Owner must supply or
  confirm the official citation from the provider.
- **GEODATA formal citation**: currently cites `huang_2017_china_spartina`
  (Global Change Research Data publication). Verification of exact
  bibliographic metadata is in progress in R5-05; owner should confirm the
  official IGSNRR citation.
- **CM-SSM citation**: `xu_2025_cmssm` (ESSD, DOI 10.5194/essd-17-6601-2025)
  — verification in progress in R5-05.

## 3. Author metadata (owner-confirmation checklist)

The manuscript is under an anonymized-review author block
(`TODO_AFFILIATION`, `TODO_EMAIL`). Before submission the owner MUST
provide/confirm:

- [ ] Full author list, order, and approval of the list
- [ ] Affiliations for every author
- [ ] Corresponding author designation, e-mail, and country
- [ ] ORCID iDs (encouraged by IJRS)
- [ ] CRediT author-contribution roles per author (IJRS supports CRediT)
- [ ] Funding statement: draft says "conducted without external funding;
  infrastructure and compute provided by the authors' institution" — owner
  must confirm this is accurate and complete
- [ ] Disclosure of interest: draft says "The authors report no conflict of
  interest" — owner must confirm
- [ ] Declaration of generative AI use (IJRS requirement): placeholder in
  manuscript; owner must supply final wording stating whether and how
  generative AI was used in research and manuscript preparation
- [ ] Keywords: final selection entered in the submission portal (manuscript
  front matter currently lists 7)
- [ ] Word count of the full paper (IJRS asks authors to include it; the
  compiled manuscript is 29 pp / approx. 10,200 words total incl. tables
  (command-stripped count, 2026-11-08)

## 4. RSPSoc / institutional membership (optional)

RSPSoc members get a discounted personal subscription; a 50% APC discount
exists only for the optional gold-OA route, which this submission does not
use. No action needed for the subscription route.

## 5. Scientific blockers (carried from R4, unchanged)

1. No GOLD reference data exist → the paper reports agreement only (already
   correctly framed throughout).
2. Coverage-normalized IoU not computable from delivered entities →
   disclosed with two proxies (already in manuscript).
3. CMSA license unverified (Section 1 above) — legal check before submission.
4. GEODATA license uncertainty (Section 1 above).
5. CM-SSM mirror license conflict (Section 1 above).

## 6. Verdict

All scientific content is in a submittable state. The submission is blocked
only by owner-dependent administrative items in Section 3 and the license
confirmations in Section 1. None of these can be closed by the agent without
fabricating information, per AGENTS.md integrity rules.
