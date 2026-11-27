# [M1-07] Freeze the research -> SpartinaGuard product interface

**Milestone:** M1
**Type:** integration / architecture
**Depends on:** M1-02

## Context

`integrations/spartinaguard/README.md` defines the hand-off boundary:
research repo emits COG, GeoParquet/GeoJSON, model manifests, uncertainty
maps, time-series products, recurrence-risk outputs; SpartinaGuard
consumes them. The Web GIS product is not duplicated here.

## Tasks

- [ ] Agree file formats, CRS convention, schema versions, and metadata
      required per product artifact
- [ ] Add validator(s) for emitted artifacts (reuse manifest schema)
- [ ] Define uncertainty-map and risk-product semantics with downstream
- [ ] Versioned contract document; example synthetic (not fabricated
      research data) fixture for consumer testing

## Acceptance

A documented, validated artifact can cross the boundary end to end with
a synthetic fixture; research and product codebases stay decoupled.
