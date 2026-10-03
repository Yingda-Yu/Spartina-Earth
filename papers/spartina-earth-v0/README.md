# Spartina Earth — Working Manuscript v0

> **Working draft, not submission-ready.** Started 2026-10-03 under
> Issue #15. This manuscript is a living document and is updated in
> parallel with data construction (Issues #7/#13/#14).

## Working title

**Spartina Earth: A Provenance-Aware Multisensor Framework for Long-Term
Monitoring of *Spartina alterniflora* Across Sensor Generations**

This is deliberately **not** a "foundation model" paper: no SpartinaFM
representation-learning results exist yet. Sensor-agnostic temporal
representation learning is presented as future work only.

## Source of truth

- Claim status is governed by [`CLAIM_EVIDENCE_LEDGER.md`](CLAIM_EVIDENCE_LEDGER.md).
- Every external reference in `references.bib` was verified against
  CrossRef metadata (or arXiv) on 2026-10-03; see
  [`literature_matrix.md`](literature_matrix.md). There are no
  LLM-memory citations.
- Every numeric result in the text traces to a tracked repository
  manifest or audit report (ledger column `Evidence`).
- Missing evidence is marked `TODO_EVIDENCE` / `PLANNED` / `UNKNOWN`;
  it is never written as a result.

## Layout

```
main.tex                 neutral article-class working template (no journal locked)
references.bib           37 DOI/arXiv-verified references
sections/01..11_*.tex    manuscript sections
tables/                  LaTeX tables generated from tracked manifests/reports
figures/                 FIGURE_MANIFEST.md + placeholders only (no rendered artwork yet)
literature_matrix.md     reference-by-reference verification and coverage matrix
PAPER_STATUS.md          section-by-section status, venue-family analysis (not locked)
CLAIM_EVIDENCE_LEDGER.md claim -> status -> evidence chain
```

## Compile

```bash
latexmk -pdf -interaction=nonstopmode main.tex
# or: pdflatex main && bibtex main && pdflatex main && pdflatex main
```

Compile requires only a standard TeX Live (`article`, `geometry`,
`booktabs`, `amsmath`, `hyperref`, `natbib`). No journal class is locked.

## Rules inherited from the repository

- No fabricated citations, results, dates, or assets (`AGENTS.md` §4, §8).
- No "first", "world-first", "state-of-the-art" without strict evidence.
- `GOLD = 0` at present; SILVER/WEAK labels are never described as GOLD.
- Bay envelopes are PROVISIONAL; the 10 km cell is recommended but not
  frozen; UNLABELED is never NEGATIVE.
- Figures are placeholders: per the academic-writing skill's rendering
  gate, no final figure artwork is rendered without an explicit request.
