# [M1-03] Label QA gates and license/citation resolution

**Milestone:** M1
**Type:** data / compliance
**Depends on:** M1-02

## Context

See `docs/audit/LABEL_INVENTORY.md`: L1 national 2015 raster (SILVER
candidate), L2 CM-SSM 2020 polygons (148,072 features; WEAK), L3
Hangzhou Bay mask, L4-L6 CMSA polygons. All licenses UNKNOWN; no
field/UAV GOLD labels exist.

## Tasks

- [ ] Identify L1 published product + citation (`TODO_CITATION`); obtain
      redistribution terms
- [ ] Verify L2 `area` unit (sum 59,371 across 9 provinces) against
      recomputed areas; document OBIA lineage from `CM-SSM.shp.xml`
- [ ] Confirm/deny L2 = the 10 m China-2020 map claimed in the multimodal
      manuscript draft
- [ ] Topology QA for L2/L4-L6: slivers (1 m2 polygons present),
      duplicates, self-intersections, `Id=0`
- [ ] Confirm class legend (`Value=1`, `gridcode=2`) from an authoritative
      source
- [ ] Decide tier upgrades only after evidence; never train on WEAK labels
      as ground truth without an explicit weak-supervision design

## Acceptance

Each L1-L6 artifact has a tier decision with evidence recorded in its
manifest; blocked items stay WEAK/UNKNOWN rather than being assumed.
