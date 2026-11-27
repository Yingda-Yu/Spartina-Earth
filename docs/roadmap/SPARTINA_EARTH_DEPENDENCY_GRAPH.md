# SPARTINA EARTH DEPENDENCY GRAPH

Version: v1.0 (2026-11-27). Nodes are milestones (see
`SPARTINA_EARTH_MILESTONE_REGISTRY.csv` for statuses and evidence). Edges
are hard dependencies: a downstream node must not start until every
incoming edge is satisfied. No edge may be silently bypassed.

## 1. Critical chain (benchmark)

```
M-PHASE2C2 (QA grid alignment) ................ COMPLETED (fdda75a)
        │
        ▼
M-V022-APPROVAL (Owner approves v0.2.2) ....... OWNER_REVIEW  ◄── ACTIVE GATE
        │
        ▼
M-READY (independent readiness decision) ...... NOT_STARTED
        │
        ▼
M-SPLIT (split freeze + leakage audit) ........ NOT_STARTED
        │
        ▼
M-SMOKE (smoke tests, ≤3 GPUs, no GPU 0) ...... NOT_STARTED
        │
        ▼
M-BASE-A ──► M-BASE-B, M-BASE-C, M-FM (parallel stages)
        │
        ▼
M-GAP (failure taxonomy on ≥2 tracks) ──► M-FM-DECISION (conditional SpartinaFM)
```

Rule: if M-FM-DECISION's gap conditions are **not** met, the contribution
pivots to data/benchmark/ecology (H6 decision rule) — the pivot itself is
the documented outcome, not a failure.

## 2. Parallel track (independent validation)

```
M-GOLD-PERM (permission drive) ──► M-GOLD-T1 (4-site pilot)
                                          │
                                          ▼
                          GOLD-validated accuracy claims
                          (replaces "agreement, not accuracy")
```

This track is independent of the benchmark chain and may proceed at any
time, but every site is currently blocked at the permission gate
(30/30 UNVERIFIED_PENDING_OWNER). GOLD evidence never flows back into
training or label re-drawing (GOLDSET_ACQUISITION_PLAN §6).

## 3. Product tracks

```
M-ATLAS-PLAN (specs; plan-only) ──► M-ATLAS-PROD
        │                                  │
        │                                  └── requires separate Owner export
        │                                      authorization (nationwide)
        └──► M-MGMT-LEDGER (treatment records) ──► RQ4/RQ8 unblock
             └── currently BLOCKED: 0 verified records
        └──► M-INTL-INV (licensing review) ──► RQ7 unblock
             └── currently BLOCKED: availability UNKNOWN
```

## 4. Cross-cutting resource constraints

- GPU: never GPU 0; ≤3 GPUs total; smoke before formal; resumable
  checkpoints (SPARTINAFM_DESIGN §7).
- Disk: /data at 91% (686 GB free) — every model download or Atlas export
  requires a prior disk audit; raw data/checkpoints/outputs stay outside
  Git.
- Data: training reads only local frozen manifests; no live GEE calls
  during training (BENCHMARK_NEXT_STAGE_PLAN §4, EO_DATA_ENGINE.md).

## 5. Blocked-node register (exact missing dependency + resolution)

| Node | Missing dependency | Proposed resolution |
|---|---|---|
| M-V022-APPROVAL (upstream of all benchmark work) | Owner decision on protocol effectiveness | Owner reviews V022_QA_PROTOCOL_FINAL.md + checksum; single decision unblocks the whole chain |
| M-GOLD-T1 | 4 written permission documents | Owner-led permission drive for the 4 Tier-1 sites (2 ZJ/FJ disagreement, 1 boundary, 1 small-patch) |
| M-MGMT-LEDGER | ≥1 verified treatment boundary+date | acquire from county-level forestry/nature-reserve management records; provenance audit before use |
| M-INTL-INV | license + label availability verification for ≥1 region | start with North American native-range public datasets (USGS/NASA, permissive licenses); document license text per region |
| M-ATLAS-PROD | separate Owner export authorization | present Atlas data-production plan for approval after benchmark Stage A begins |
