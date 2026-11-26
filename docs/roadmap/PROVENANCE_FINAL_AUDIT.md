# PROVENANCE_FINAL_AUDIT — Phase 2B

Verified 2026-11-27 by recomputing every `document_checksum` (frozen
`A.document_checksum`, canonical JSON) and comparing stored
`git_commit` / `generated_utc` against the actual repository state
(HEAD `dcca07d4…`).

## 1. Checksum verification (all PASS)

| artifact | checksum recomputed = stored | git_commit stored | generated_utc stored |
|---|---|---|---|
| `UPDATED_REPAIR_EXPORT_MANIFEST.json` | ✔ | `dcca07d4…` (stamped in 2B; previously absent — gap fixed this phase) | 2026-11-27 (stamped in 2B) |
| `UPDATED_REPAIR_QA_REPORT.json` | ✔ | `759eda15…` (HEAD at generation = Phase 1.1 commit) | 2026-11-26T18:03:25Z |
| `V0_2_1_FINAL_READINESS_DECISION.json` | ✔ | `5b10d3b6…` (HEAD at generation = Phase 2A commit) | 2026-11-26T18:24:19Z |
| `REPAIR_QA_REPORT.json` | ✔ | `759eda15…` | 2026-11-26T18:03:25Z |
| `LIVE_GEE_REPAIR_PLAN.json` | ✔ | `759eda15…` | 2026-11-26T17:25:16Z |
| `RANK2_SUBSTITUTE_PLAN.json` | ✔ | `5b10d3b6…` | 2026-11-26T18:24:19Z |

Notes:
- `git_commit` fields record **HEAD at generation time**; the commit
  containing the file lands afterwards, so the stored SHA is the parent
  provenance — correct semantics, verified against `git log` order.
- Timestamps are UTC; stored 2026-11-26T18:xx UTC = 2026-11-27 local
  (Asia/Shanghai) — consistent with run logs.
- The one gap found (`UPDATED_REPAIR_EXPORT_MANIFEST.json` lacked
  `git_commit`/`generated_utc`) was fixed by re-stamping; the
  checksum was recomputed and now verifies (`c1b6eadab4ef…`). No
  substantive field changed.

## 2. Inherited vs newly computed results (explicit marking)

**Inherited (measured in earlier phases, re-verified but not recomputed):**
- Frozen v0.2 measured support (11 positives / 11 backgrounds / 5
  regions) — from `v02_support_matrix_per_cell.csv` (Phase L).
- Panel QA verdict `QA_PASS_WITH_HONEST_SOURCE_REJECTIONS` and its
  single honest rejection (`V02_R00355-C00151_L8_2015_L`) — Phase I/J
  QA summary (frozen).
- Panel product classifications (146 partial-finite acceptances, 1
  zero-valid) — re-scanned from frozen Phase H manifests in 2B (scan is
  new; the artifacts are inherited).

**Newly computed in Phases 2A/2A.1/2B:**
- LIVE-GEE plan (35 eligible / 28 NO_SCENE / 21 gate-failed slots) —
  `LIVE_GEE_REPAIR_PLAN.json` (2A Step 1).
- Repair export (105 tasks, 35 landed products, 132,432,833 bytes,
  per-file SHA-256s) — export manifests + task store (2A Step 4).
- Forensic re-measurement of the failed product (band finiteness,
  QA_PIXEL class decode, VALID histogram, cross-tabulation) — measured
  from landed rasters in 2B (`FAILED_PRODUCT_FORENSIC_REPORT.md`).
- Historical consistency scan (443 optical panel products + 34 repair)
  — 2B (`HISTORICAL_QA_CONSISTENCY_AUDIT.md`).
- Final readiness verdict `NOT_READY_FOR_SPARTINASHIFT_V0_2_PROTOCOL`
  and the gate-support arithmetic (15/12/5 on the QA-clean denominator)
  — 2A Step 5, re-stamped 2A.1.

## 3. Chain of custody

Every new artifact carries `document_checksum`; the export batch carries
real GEE backend task IDs; landed files carry per-file SHA-256. The
chain: frozen candidate table → frozen LIVE plan → task store → per-
product manifests → UPDATED manifest → QA reports → readiness decision.
No frozen v0_2 artifact, label, threshold, or Reserve file was modified
in any phase (verified by zero-diff checks in Phase 1.1 and 2A logs).

## 4. Verdict

Provenance chain is complete and internally consistent; the audit found
and fixed exactly one field-level gap (manifest timestamps). All
reports are ready for Owner review of the v0.2.2立项 decision.
