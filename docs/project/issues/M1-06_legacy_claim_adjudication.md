# [M1-06] Adjudicate legacy manuscript claims

**Milestone:** M1
**Type:** research integrity
**Depends on:** M1-02, M1-04, M1-05

## Context

Two draft PDFs authored by the repo owner live in
`old datasets/Spartina/zhejiang/`; claims ledger rows 15-20 in
`docs/audit/LEGACY_RESULT_AUDIT.md`. All quantitative claims UNVERIFIED;
CISNet Table VI (2015) is arithmetically self-contradictory for the SVM
and U-Net F1 values.

## Tasks

- [ ] Recover or reconstruct the sample-point tables (2,570 pixels /
      six areas; CISNet 1995/2005/2015 point counts); provenance first
- [ ] Re-derive the 2005/2015 comparison tables from raw predictions if
      code/models can be recovered; explain or retract the inconsistent
        F1 cells
- [ ] Reproduce (or fail to reproduce) OA 87.73-96.39% / kappa
      0.73-0.94 under spatial-disjoint splits - pixel-split numbers may
      not carry over
- [ ] Register every claim in the experiment ledger with run IDs; claims
      without a run stay out of new manuscripts
- [ ] Reconcile co-author spelling and draft versions before citation

## Acceptance

Each claim row 15-19 ends as VERIFIED, CONTRADICTED, or retracted with
evidence; no UNVERIFIED legacy number appears in M1+ publications.
