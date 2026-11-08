# FINAL CHECKLIST — EarthArXiv Submission of Spartina Earth Paper 1

Legend: [x] done and verified by R6; [ ] Owner action required.
The submission itself is additionally gated on explicit Owner authorization
(standing rule: never actually publish without it).

## Machine-verifiable items (completed in R6)

- [x] Single PDF assembled (`Spartina_Earth_Paper1_Preprint.pdf`, 36 pages:
      coversheet + 35-page manuscript, appendices in-document)
- [x] Coversheet contains the "non-peer reviewed preprint submitted to
      EarthArXiv" statement, author, affiliations, corresponding email
- [x] Title, abstract, author names, affiliations present (metadata.yaml
      mirrors the PDF)
- [x] 7 keywords listed (≥1 required)
- [x] Written in English
- [x] 20 verified references incl. peer-reviewed literature (bibtex clean,
      0 undefined citations)
- [x] All figures regenerated after basemap fix; cartographic QA re-ran
      (audits/r6_cartographic_qa.md §0.1)
- [x] All primary numbers verified against committed artifacts
      (audits/r6_scientific_integrity.md)
- [x] No source geometry/raster bytes of CMSA/GEODATA/CM-SSM in the PDF,
      zip, or package
- [x] No credentials, tokens, internal paths, or restricted data in the PDF
- [x] Single-author authorship confirmed (git history co-author check,
      R6-02)
- [x] License/attribution statement (LICENSE_AND_ATTRIBUTION.md)
- [x] EarthArXiv requirements audit (audits/r6_eartharxiv_requirements.md)

## Owner-confirmation items (blocking actual submission)

- [ ] **ORCID URL** — fill in coversheet.tex + metadata.yaml; ORCID record
      must include educational history + current/recent affiliation; ORCID
      email must match the submitter account (EarthArXiv policy)
- [ ] **Preprint license choice** — e.g. CC BY 4.0 vs platform options
- [ ] **Funding statement** — manuscript has none (removed as unverified);
      confirm "no funding" is accurate or provide funding text
- [ ] **Competing-interests wording** — Spartina Technology affiliation
      disclosure wording confirmed
- [ ] **AI-use declaration wording** — currently honest AI-assistance
      statement; confirm wording
- [ ] **Spartina Technology formal legal name** — Affiliation 2 rendering
- [ ] **CMSA provider confirmation** — license (NESDC CC BY-NC 4.0) and
      permission to publish derived figures/statistics (r4 S3)
- [ ] **GEODATA license confirmation** — CC BY-NC-ND against IGSNRR
      platform record (r4 S4)
- [ ] **CM-SSM mirror license conflict** — Zenodo CC BY 4.0 vs NESDC CC
      BY-NC 4.0; producer confirmation preferred (r4 S5)
- [ ] **Journal-submission line on coversheet** — currently "not under
      consideration"; update if concurrent IJRS submission decided (and
      check the journal's preprint policy first)
- [ ] **External repository link** — confirm the public repo URL is the
      intended citable snapshot (consider a Zenodo release DOI)
- [ ] **Git commit reference in Conclusions** — update after the final R6
      commit if the Owner wants the preprint to point at the R6 state
      (currently points to the R5 commit 948c17c; the repo branch carries
      the full R6 provenance)
- [ ] **Explicit authorization to submit** — final go/no-go from Owner

## Post-approval submission steps

1. Resolve all items above; rebuild PDF if any file changed (commands in
   README_submission.md).
2. Submit at https://eartharxiv.org/repository/submit/start/ per
   README_submission.md.
3. Record the assigned EarthArXiv DOI in the repository (PROGRESS.md and
   this checklist) after acceptance.
