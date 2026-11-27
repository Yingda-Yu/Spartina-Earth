# SPLIT_DESIGN_AND_LEAKAGE_AUDIT

Version: v1.0 design + audit tooling status (2026-11-27). Defines how
splits are constructed for Benchmark V1 and what is audited, with the
auditable tooling actually present in the repo. No split is frozen yet —
freezing is gated on v0.2.2 approval + readiness decision.

## 1. Split construction rules (binding, from SPEC.md §3)

1. Unit = CNA10K cell; **no random neighboring-patch splits** (rejected by
   `src/spartina/evaluation/splits.py`).
2. Spatially disjoint units with explicit buffer (default ≥250 m; per-track
   justification recorded in split manifest).
3. All dates of the same cell share the same split (`check_temporal_grouping`).
4. Test cells never touched by training, validation, hyperparameter search,
   early stopping, threshold/calibration fitting. Validation cells disjoint
   from both.
5. Cross-Region holdout province lists frozen before development.
6. Cloud/quality masks never move scenes between splits.
7. Label polygons never cross train-side/test geometry in CRS-appropriate
   coordinates.
8. Resolution honesty: 30 m evaluated on native grid; 10 m comparisons
   reported separately per native resolution.

## 2. Split manifest schema (to be frozen)

```json
{
  "split_id": "SPLIT_V1_<proto>_<date>",
  "protocol": "v0.2.2 (post-approval)",
  "cells": {"train": [...], "validation": [...], "test": [...]},
  "cross_region_holdouts": {"province": [...], "cells": [...]},
  "buffer_m": 250,
  "seed": 42,
  "geometry_hash": "<sha256 of cell geometry set>",
  "leakage_check": {"tool": "src/spartina/evaluation/splits.py",
                    "assert_spatially_disjoint": "exit 0",
                    "check_temporal_grouping": "exit 0"},
  "checksum_sha256": "<sha256 of this file>"
}
```

Test geometry is never edited after freeze; errata require a new split_id.

## 3. Leakage audit checklist (executed at freeze time, results recorded)

| # | Audit | Tool | Gate |
|---|---|---|---|
| A1 | no cell in two roles | split manifest validation script | exit 0 |
| A2 | pairwise spatial disjointness with buffer | `assert_spatially_disjoint` | exit 0 |
| A3 | temporal grouping (all dates per cell in one role) | `check_temporal_grouping` / `check_date_table_grouping` | exit 0 |
| A4 | label polygons do not cross train/test | `goldset_isolation.py` + label-family intersection check | exit 0 |
| A5 | Reserve cells untouched | reserve list check against all roles | exit 0 |
| A6 | holdout provinces absent from all selection configs | config grep audit | recorded |
| A7 | honest-rejection products excluded from all role denominators | QA ledger cross-check | recorded |

A1–A5 are automated at freeze time by
`engineering/dataset_validation/validate_splits.py` (delivered with this
program; executes the spartina splits checker on the frozen manifest).
A6/A7 are recorded as shell/Grep evidence in the freeze report.

## 4. Test-label access prohibition (enforced)

- Test cells are written into the split manifest and then **not loaded**
  during development; loaders accept a `role` filter and development
  configs use only train/validation roles.
- Tuning logs and early stopping read validation cells only. The first
  test evaluation is the frozen-protocol evaluation.
- This prohibition extends to "peeking" statistics: no distribution
  summaries, no visual inspection workflows, no metric computation on
  test cells before the frozen evaluation run. The run manifest records
  which roles a run accessed.

## 5. Known open items for freeze

- Variant 1 vs Variant 2 reserve decision (Owner) — affects which sealed
  cells enter test vs stay untouched.
- Buffer sensitivity check (250 m vs 500 m) recorded as sensitivity note,
  not used to move cells after freeze.
- Per-track minimum label density for region qualification (Cross-Region).
