# R6-06 — Live EarthArXiv Requirements Audit

**Date of live check:** 2026-11-08 (Asia/Shanghai)
**Pages consulted (all accessed 2026-11-08):**

1. https://eartharxiv.org/ — platform home (Janeway-based, hosted by
   California Digital Library; assigns DOIs; volunteer-moderated).
2. https://eartharxiv.org/repository/about/ — scope and platform facts.
3. https://eartharxiv.github.io/moderation.html — Moderation Policy and
   Terms of Use, **v2.9, October 13, 2025** (the authoritative requirements
   list).
4. https://eartharxiv.github.io/faq.html — supplementary-material hosting,
   indexing, journal-policy questions.

---

## 1. Requirement checklist (verbatim source: moderation.html §"Basic
Requirements for Paper Submissions", plus related clauses)

| # | EarthArXiv requirement | Paper 1 status | Verdict |
|---|---|---|---|
| 1 | Within scope: Earth & planetary science; environmental biology/ecology with an Earth-science perspective welcome | Remote-sensing map-reliability study of a coastal invasive plant | PASS |
| 2 | Contains title, abstract, author names, affiliations | All present in main.tex; single author with 2 affiliations | PASS |
| 3 | Uploaded by one of the listed authors | Single author = submitter (Owner). Submission itself is an Owner-authorized manual action | OWNER ACTION |
| 4 | All metadata provided; every listed author appears in metadata; ≥1 keyword for indexing | metadata.yaml lists the single author; 7 keywords present | PASS |
| 5 | Written in English | Yes | PASS |
| 6 | **One single PDF; no additional supplemental PDFs** ("All material must be included in ONE PDF") | Data-inventory appendix is inside main.tex; code/data are external links, not extra PDFs | PASS (verify final PDF is single) |
| 7 | At least one author email for correspondence | yuying@kean.edu in author block | PASS |
| 8 | ORCID: full URL link to ORCID on the coversheet or top of first page; ORCID record must include educational history + current/recent affiliation; ORCID email must match submitter email | **MISSING — Owner must provide ORCID URL** | **OWNER ACTION** |
| 9 | Cover sheet (Option 1) or per-page header (Option 2) stating "non-peer reviewed preprint submitted to EarthArXiv"; journal name if simultaneously submitted; citation+DOI if postprint | Coversheet must be prepared; journal-name field left empty unless Owner decides on concurrent IJRS submission | TO BUILD (R6-08) |
| 10 | Citations to established scientific literature | 20 verified references incl. peer-reviewed articles | PASS |
| 11 | Not a commentary/opinion piece; not a poster/thesis | Research article | PASS |
| 12 | Co-author permission | Single author; N/A | N/A |

## 2. Supplementary materials policy

EarthArXiv **does not host supplementary files**; it displays links to
external hosts (GitHub, Zenodo, FigShare). Our supplementary assets
(code/experiments, results CSVs, audit trail) live in the Spartina Earth
repository, so the submission links must point to the public repository
location. **Consequence for R6-08:** the `supplement/` folder is for
Owner-side bookkeeping only; nothing but the single PDF is uploaded, and
external links are entered in the submission form fields.

## 3. Journal-policy risk (preprint ⇒ prior publication)

Per the FAQ, authors must check their target journal's preprint policy via
SHERPA/RoMEO and the publisher site. The recorded secondary possibility is
IJRS (Taylor & Francis). **TODO_OWNER:** confirm T&F's current preprint
policy for IJRS before any concurrent journal submission; the preprint itself
does not require it.

## 4. Withdrawal/permanence warning

EarthArXiv preprints receive a DOI and persist indefinitely; withdrawals are
treated as retractions. This is the reason the R6 brief requires explicit
Owner approval before actual submission.

## 5. Items required from the Owner before submission

1. **ORCID URL** (with educational history + current affiliation populated in
   the ORCID record; the ORCID email should match the submitter account).
2. Decision on the coversheet journal-name line (leave blank vs. name IJRS
   as concurrent submission).
3. Choice of publication license in the submission form (e.g., CC BY 4.0 vs
   more restrictive options offered by Janeway) — Owner's decision.
4. Confirmation that Spartina Technology's formal legal name (used on the
   coversheet) is correct.

## 6. Impact on the R6-08 package

- `Spartina_Earth_Paper1_Preprint.pdf` must be a **single PDF** containing
  manuscript + all appendices (already the case; data inventory and license
  appendix are in-document) **plus a coversheet page** stating non-peer-
  reviewed preprint status, with the ORCID URL.
- `metadata.yaml`, `README_submission.md`, `cover_abstract.txt` support the
  Janeway form fields (title, abstract, keywords, author metadata, external
  links to the code/results repository).
- The coversheet template archive referenced by EarthArXiv lives on
  https://eartharxiv.github.io/resources.html (accessed 2026-11-08); we
  implement the required statements directly rather than depending on the
  external template.

**Verdict: all machine-checkable requirements are satisfiable from existing
materials; submission is blocked only on Owner items (ORCID, license choice,
journal-line decision, legal name) and on the standing rule that no actual
submission happens without Owner authorization.**
