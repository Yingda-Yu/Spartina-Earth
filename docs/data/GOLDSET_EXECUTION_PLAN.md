# GOLDSET_EXECUTION_PLAN — Tier-1 pilot execution (4 sites)

Version: v1.0 (2026-11-27). Operationalizes the Tier-1 pilot defined in
`GOLDSET_ACQUISITION_PLAN.md` §8. This is an execution plan; no site has
been collected, no permission obtained, GOLD remains 0.

## 1. Tier-1 scope (frozen from acquisition plan)

| Slot | Selection rule | Province pool | Site count |
|---|---|---|---|
| T1-a, T1-b | SOURCE_DISAGREEMENT_POSITIVE (highest information) | ZJ / FJ | 2 |
| T1-c | BOUNDARY_SITE | SD / JS | 1 |
| T1-d | SMALL_FRAGMENTED_PATCH | SD / JS / ZJ | 1 |

Selection from `benchmarks/spartinashift/v0_2/v02_gold_candidates.csv`
(30 candidates). Exact site IDs are fixed **before** any collection and
frozen in the registry; selection uses only registry metadata (source
disagreement class, patch-size class), never model outputs.

## 2. Stage gates

| Gate | Requirement | Owner action |
|---|---|---|
| G0 permission | written land/flight permission per site, document reference recorded in registry | Owner drives contacts; nothing flies before G0 |
| G1 equipment | UAV ≥2 cm/px RGB (+optional multispectral), flight-logging capability; or HR-imagery license ≥0.5 m | equipment audit recorded |
| G2 timing | flight within ±3 days of a clear S2 overpass (binds reference to EO event) | overpass plan per site |
| G3 annotation | protocol per acquisition plan §4 (MMU 4 m² UAV / 25 m² HR; class set spartina_alive/dead/other_veg/mudflat/water/other) | annotator A/B named |
| G4 double review | 100% blind re-annotation on disagreement sites, ≥30% others; IoU agreement + adjudication log | reviewers A/B/C recorded |
| G5 registry update | all new registry columns filled (reference_evidence_type … license ref); SHA-256 of imagery manifest | acceptance review |
| G6 isolation check | `src/spartina/evaluation/goldset_isolation.py` run exit 0 against current splits | recorded |

## 3. Annotation workflow (software)

- Digitization in QGIS with a locked class schema (no free-text classes).
- Per-polygon provenance JSON auto-generated; imagery manifest + SHA-256
  computed at ingest (template: `engineering/run_manifest/`).
- Annotator confidence (3-level), edge-ambiguity flag, tide state,
  phenology note stored per polygon (acquisition plan §4).
- Imagery RAW + flight logs stored outside Git; manifest + SHA-256 in Git.

## 4. What Tier-1 does and does not deliver

- DOES: end-to-end protocol validation; reviewer-agreement statistics;
  first independent reference polygons for 4 sites; calibration of the
  full T2/T3 workflow.
- DOES NOT: allow any accuracy claim beyond the 4 sites; promote any site
  to GOLD automatically; touch panel labels, Reserve cells, or splits.
- Until G4 passes for a site, its tier stays reference-candidate with the
  recorded disagreement (acquisition plan §5).

## 5. Risks

- Permission denial or delay at any site → substitute from same
  stratum/province only, re-frozen before collection.
- Weather window misses → reschedule; a reference not bound to a S2
  overpass is recorded as `timing_exception` and is not used for
  overpass-matched validation.
- UAV regulations (airspace/COA-equivalent) → fall back to HR-imagery
  license path with license document archived.

## 6. Immediate next actions (owner-facing)

1. Owner selects/contacts the 4 sites for permission (G0).
2. On G0 for ≥1 site: fix exact site IDs + overpass plan; freeze selection.
3. Annotation software setup + annotator training on a non-registry
   practice site (never a candidate site, never a Reserve cell).
