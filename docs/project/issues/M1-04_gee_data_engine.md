# [M1-04] Implement the EO data engine v1

**Milestone:** M1
**Type:** feature
**Depends on:** M1-01, M1-02

## Context

Design: `docs/architecture/EO_DATA_ENGINE.md`; skeleton interfaces with
mocked tests: `src/spartina/data/gee/` (auth, catalog, collections,
quality, export, manifest). No GEE calls were made in M0.

## Tasks

- [ ] GEE authentication flow documented; service-account vs. user OAuth
      decision; no credentials committed
- [ ] Sensor registry coverage (`data/sensors/registry.py`) verified
      against real collection band definitions (L5/L7/L8/L9, S1, S2)
- [ ] Region/date table drives exports; cloud/tide quality filters;
      export manifests round-trip through the schema validator
- [ ] Region table is versioned; region IDs are anonymized stable
      identifiers
- [ ] Small smoke export on one tile before any bulk job; bulk downloads
      remain gated behind explicit approval and GPU/storage checks

## Acceptance

A documented command reproduces one small, checksummed analysis-ready
tile from GEE given a region/date record; integration tests marked
`gee_integration` stay opt-in.
