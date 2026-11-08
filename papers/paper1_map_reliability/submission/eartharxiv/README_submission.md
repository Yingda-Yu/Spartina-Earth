# Spartina Earth Paper 1 — EarthArXiv Submission Package

**Package version:** R6, 2026-11-08
**Status:** assembled, awaiting Owner approval. **No submission has been
made.** Actual submission requires explicit Owner authorization (standing
project rule) and the owner-confirmation items in `FINAL_CHECKLIST.md`.

## Contents

| File | Purpose |
|---|---|
| `Spartina_Earth_Paper1_Preprint.pdf` | The single PDF to upload: 1-page coversheet + 35-page manuscript (all appendices in-document, per EarthArXiv "one PDF" rule) |
| `Spartina_Earth_Paper1_Preprint_source.zip` | LaTeX sources (main.tex, references.bib) + the 9 figure PDFs needed to recompile; local archive, not uploaded |
| `coversheet.tex` / `coversheet.pdf` | Coversheet source and single-page PDF (statements required by EarthArXiv moderation policy v2.9) |
| `figures/` | The 9 manuscript figures (PDF + PNG preview each) |
| `supplement/` | Owner-side bookkeeping pointers only — EarthArXiv hosts no supplementary files; links to the code/results repository are entered in the submission form (see `metadata.yaml`) |
| `metadata.yaml` | All Janeway form fields (title, abstract, author, keywords, links) with TODO_OWNER markers |
| `cover_abstract.txt` | Plain-text title / authors / abstract / keywords for copy-paste |
| `LICENSE_AND_ATTRIBUTION.md` | Data licensing and attribution statement |
| `FINAL_CHECKLIST.md` | Pre-submission checklist including all Owner-confirmation items |

## How to submit (Owner, after approvals)

1. Resolve every `TODO_OWNER` item in `FINAL_CHECKLIST.md` (ORCID, license,
   funding/COI wording, dataset-license confirmations, legal name).
2. If the Git commit reference changed since the package was built, re-merge
   the PDF (see rebuild commands below) and update the Conclusions commit
   hash if applicable.
3. Create an account / sign in at https://eartharxiv.org/repository/submit/start/
   using the author email (yuying@kean.edu); the ORCID record must show
   educational history and a current or recent affiliation, and the ORCID
   email should match the submitter account.
4. Upload `Spartina_Earth_Paper1_Preprint.pdf`, fill the form from
   `metadata.yaml`, choose the license, add the external repository link,
   and confirm the "cover sheet included" checkbox.
5. Moderation typically completes within about one week (EarthArXiv
   Moderation Policy v2.9).

## Rebuild commands

```bash
cd papers/paper1_map_reliability/submission/eartharxiv
pdflatex -interaction=nonstopmode coversheet.tex
cd ../../manuscript
pdflatex -interaction=nonstopmode main.tex && bibtex main \
  && pdflatex -interaction=nonstopmode main.tex \
  && pdflatex -interaction=nonstopmode main.tex
cd ../submission/eartharxiv
pdfunite coversheet.pdf ../../manuscript/main.pdf \
  Spartina_Earth_Paper1_Preprint.pdf
```

Source zip rebuild: copy `manuscript/main.tex`, `manuscript/references.bib`
and the 9 figure PDFs listed in `main.tex` into a `figures/` subfolder and
zip them.

## Important constraints

- Do **not** merge `feat/paper1-map-reliability` into `main` (standing rule).
- Do **not** upload any supplementary files — only the single PDF; other
  materials are linked externally.
- The preprint DOI, once assigned, is permanent; withdrawal is treated as
  retraction (EarthArXiv policy). Verify all owner items before uploading.
- If a concurrent journal submission (e.g. IJRS) is planned, check the
  journal's preprint policy first (SHERPA/RoMEO) and update the coversheet's
  "Journal submission" line.
