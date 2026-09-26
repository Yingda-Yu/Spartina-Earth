# [M1-05] Spatial-disjoint splits and leakage CI

**Milestone:** M1
**Type:** evaluation / reliability
**Depends on:** M1-02, M1-03

## Context

Benchmark rules: `benchmarks/spartinashift/SPEC.md`; utilities:
`src/spartina/evaluation/splits.py` (spatial-unit grouping, overlap
assertions, date-table grouping). Legacy random image-level splits are
prohibited.

## Tasks

- [ ] Build spatial units for L2 polygons (province-held-out track using
      `name`) and raster tiles (L1 / Hangzhou / Fujian windows)
- [ ] Cross-product overlap check: L1 (2015) vs L2 (2020) vs L3 share
      underlying geography; prove no train/test geometry overlap
- [ ] Temporal rule for the Fujian window: adjacent years of S2 + CMSA
      labels must not cross folds
- [ ] CI test fails the suite on any cross-split overlap or duplicate
      manifest geometry

## Acceptance

Split tables are versioned artifacts; leakage check is an automated,
required test.
