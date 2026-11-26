# V022_QA_PROTOCOL_PROPOSAL — QA semantics audit and revision proposal

Audit-only phase deliverable. **No frozen QA code, threshold, label,
Reserve, or export was modified.** This document proposes the v0.2.2
protocol revision for Owner approval (formal立项 decision pending).

## 1. Existing QA semantics (as frozen)

Sources audited: `scripts/benchmarks/spartinashift/qa_v02_export.py`
(`_informative_check`, `verify_product`, Phase J contract list),
`scripts/benchmarks/spartinashift/qa_v02_1_repair.py` (frozen machinery
redirected, zero semantic change), Issue #21 Phase J QA contract
(`V0_2_EXPORT_QA_SUMMARY.json` qa_contracts), Issue #19 honest-rejection
policy (class definition, zero pilot occurrences), and
`V0_2_1_FINAL_READINESS_DECISION.json`.

Mechanics: a product with `VALID` = 0 is an honest rejection
(`ZERO_QA_VALID_SURFACE_PIXELS`) **iff** it is Landsat AND every SR band
is 100 % finite AND the physical audit passes; otherwise it is a hard
error. Any hard error flips the batch verdict to
`QA_FAIL_SYSTEMATIC_STOP`, which forces
`NOT_READY_FOR_SPARTINASHIFT_V0_2_PROTOCOL` under the frozen readiness
rule.

## 2. Rejection-class taxonomy (A–E as requested)

| class | definition | current treatment | correct bucket |
|---|---|---|---|
| **A. Genuine source-quality rejection** | export byte-faithful (SHA-256/grid/physical audit pass), mask gate ≥0.95, but the scene's own QA_PIXEL classification yields no usable surface over the cell (e.g. 100 % cloud-flagged) | honest rejection (with the all-finite precondition) | honest rejection |
| **B. Export pipeline failure** | task failure, file missing, SHA-256 mismatch, CRS/transform wrong, wrong scene | hard error (systematic stop) | must stop |
| **C. Invalid or incomplete raster** | all-NaN product, truncated file, unreadable GeoTIFF, zero finite pixels in every band | hard error (systematic stop) | must stop |
| **D. Zero QA_PIXEL-valid surface observations** | subclass of A: QA_PIXEL `clear` = 0 over the cell while bytes are faithful and mask gate passes | honest rejection if all-finite; **hard error if any band has NaN** (the precondition) | honest rejection — precondition is the defect being proposed for revision |
| **E. Partial non-finite SR bands** | some (not all) SR bands have finite fraction < 1.0 | **accepted** whenever VALID > 0 (146 panel + 22 repair precedents, min 0.980) | accepted; escalates class D to hard error only in the zero-valid corner case (the inconsistency) |

**Current state in one sentence**: A and D qualify as honest rejection
only when all SR bands are 100 % finite; B and C must stop; E is
accepted in every observed case except that it disqualifies a zero-valid
product from the honest-rejection class.

## 3. Proposed v0.2.2 revision (Owner decision required)

Replace the all-finite precondition for class A/D with:

> A zero-VALID Landsat product is an honest source-quality rejection
> (`ZERO_QA_VALID_SURFACE_PIXELS`) iff: (a) landed SHA-256 matches, (b)
> locked grid/CRS rebuild passes, (c) physical audit passes, (d) the
> byte-level actual-mask ≥ 0.95 gate passes, and (e) every non-finite
> SR pixel lies inside a QA_PIXEL non-clear class (verifiable by
> cross-tabulation). Otherwise it remains a hard error.

Rationale: condition (e) removes the only observable consequence of the
old precondition while keeping its protective intent — NaNs that could
ever matter (inside potentially-clear surface) still force a hard error.
The forensic report shows the current failure satisfies (e): all 2,001
non-finite band-1/2 pixels are inside cloud/shadow classes, and the fill
bit is never set.

Explicitly preserved (no relaxation): ≥0.95 mask gate, physical audit,
SHA-256/grid contracts, B/C as hard errors, zero-tolerance for fill-bit
mismatch, and the batch semantics (any true hard error still stops the
batch).

## 4. Why this is a protocol question, not an agent action

The frozen contract's precondition was calibrated on a single historical
case (see `HISTORICAL_QA_CONSISTENCY_AUDIT.md`). Revising it is a
legitimate Owner-level protocol change precisely because: (i) it affects
the accepted-denominator definition that all published numbers depend
on; (ii) the revision must be versioned (v0.2.2), checksummed, and
applied uniformly — never as a per-product exception; and (iii) it
changes what "QA pass" means for the readiness flip.

## 5. Alternatives considered and rejected

- Silent agent-side reclassification: forbidden (contract freeze).
- Rank-2 substitute: exhausted — no gate-passing candidate (frozen pool,
  `RANK2_SUBSTITUTE_PLAN.json`).
- Keeping v0.2 as-is with NOT_READY: defensible (Option A in
  `V022_IMPACT_ANALYSIS.md`) but leaves the gate closed on an artifact
  of an untested precondition while all three support thresholds are
  met on the QA-clean denominator.
- Expanding the discovery pool (cloud 43 % / partial coverage events):
  rejected — violates the frozen prefilter and imports systematically
  cloudier scenes into the benchmark.
