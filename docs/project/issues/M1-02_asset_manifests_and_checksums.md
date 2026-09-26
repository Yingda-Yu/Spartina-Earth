# [M1-02] Manifest every legacy asset with SHA-256

**Milestone:** M1
**Type:** data
**Depends on:** M1-01

## Context

`docs/audit/DATA_INVENTORY.md` inventories 14 proposed asset groups in the
git-ignored `old datasets/` (7.2 GiB). Bytes stay out of Git; manifests
are the traceable record. Schema: `datasets/manifests/schema.json`
(22 required fields; UNKNOWN/null, never guessed).

## Tasks

- [ ] SHA-256 every file (incl. `.rar`/`.zip` archives; note duplicates)
- [ ] Enumerate true band names/scales with rasterio (11-band Zhejiang
      stacks, 5-band S2 stacks are UNKNOWN)
- [ ] Confirm CRS + transforms; flag the 32651-vs-4326 and S1/L8 grid
      mismatches in Hangzhou Bay
- [ ] One JSON manifest per asset; validator
      (`src/spartina/data/manifests/validator.py`) must pass in CI
- [ ] Re-scan `old datasets/` first (transfer completed 2026-09-27; later
      additions possible)

## Acceptance

`pytest` proves every manifest validates; every on-disk asset has exactly
one manifest and vice versa.
