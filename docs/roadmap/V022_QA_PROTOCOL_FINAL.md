# V022_QA_PROTOCOL_FINAL — SpartinaShift v0.2.2 QA contract (proposal, pending Owner approval)

Version: 0.2.2 | Status: **PROPOSED — not effective** | Supersedes: none
(the frozen v0.2 Phase J contract remains in force until the Owner
approves this document; original NOT_READY results are preserved
untouched). Checksum: see `V022_PROTOCOL_CHECKSUM.json`.

## 1. Rejection-class taxonomy (final wording)

| class | definition | verdict |
|---|---|---|
| **A. Genuine source-quality rejection** | Landed export is byte-faithful (SHA-256, locked grid/CRS, physical audit all pass), byte actual-mask ≥ 0.95, and the scene's own QA_PIXEL classification yields zero QA-valid surface over the cell | `HONEST_REJECTION_ZERO_QA_VALID_SURFACE_PIXELS` — counted out of the accepted denominator; never a systematic stop |
| **B. Export pipeline failure** | task failure, missing file, SHA-256 mismatch, wrong CRS/transform, wrong scene, grid mismatch | `HARD_ERROR` — batch `QA_FAIL_SYSTEMATIC_STOP` |
| **C. Invalid or incomplete raster** | unreadable GeoTIFF, all-NaN product, every band zero-finite, truncated file | `HARD_ERROR` — batch stop |
| **D. Zero QA-valid surface observations** | subclass of A: `VALID` raster all-zero from QA_PIXEL semantics | same as A under the v0.2.2 evidence test |
| **E. Partial non-finite SR bands** | some SR bands have finite fraction < 1.0 while VALID > 0 | **accepted** (historical precedent: 146 panel + 22 repair products); escalates only via the condition-(e) test below when VALID = 0 |

## 2. Deterministic pixel-evidence test (replaces the vague "non-clear" wording)

For a zero-VALID Landsat product, honest rejection requires ALL of:

1. **SHA-256**: every landed file matches its manifest hash;
2. **Grid**: locked transform / dimensions / CRS rebuild identical to
   the frozen plan grid; 30 m resolution;
3. **Physical audit**: frozen Phase J audit passes (scaling, band
   order, saturation bounds);
4. **Mask gate**: byte-level actual-observed fraction ≥ 0.95 on the
   export grid;
5. **Pixel evidence (deterministic)**:
   `nonfinite_inside_offline_qa_valid_set == 0`, where the offline
   QA-valid set is computed directly from the landed QA_PIXEL raster:
   `clear bit SET and fill/dilated-cloud/cirrus/cloud/cloud-shadow/snow
   bits UNSET` (bits 0–5 of 0–7). When there are no non-finite SR
   pixels at all, condition 5 is vacuously satisfied — the v0.2.2 rule
   then reduces exactly to the v0.2 rule.

Sensor-specific bit definitions (USGS Collection 2 QA_PIXEL, identical
layout for L7 and L8 with one reservation):

- **Landsat 8/9**: bit0 Fill, bit1 Dilated Cloud, bit2 Cirrus, bit3
  Cloud, bit4 Cloud Shadow, bit5 Snow, bit6 Clear, bit7 Water.
- **Landsat 7**: same positions; bit2 (Cirrus) is reserved for L7 and
  USGS sets it to 0, so the predicate applies unchanged and is reported
  per-sensor (a `cirrus=1` on L7 would itself be treated as data
  irregularity, not silently ignored).
- **Water (bit 7)**: auxiliary information on both sensors — water
  surface is VALID when bits 0–6 pass and QA_RADSAT = 0 (production
  semantics, unchanged).
- **QA_RADSAT**: part of the production VALID predicate; not exported
  as a component, therefore verified via the physical-audit saturation
  bounds on scaled SR (0 saturated pixels inside VALID is additionally
  asserted by the frozen audit: `SATURATION_IN_VALID_HARD_FRACTION`).

No vague terms ("non-clear", "probably cloud") appear in the rule:
everything is a fixed bit position or a count recomputable from landed
rasters.

## 3. Historical consistency (regression-tested)

`V022_REGRESSION_TESTS/classify_v022.py` re-classified all 478 optical
products read-only under both contracts:
v0.2 → 308 accepted, 168 accepted-partial-finite, 1 honest rejection,
1 hard error; **v0.2.2 changes exactly one classification** —
`V021_R00372-C00139_L8_2015_E` (hard error → honest rejection), with
pixel evidence 1,518 non-finite px, 0 inside the QA-valid set, 0 fill
bits anywhere. No other product moves. Full report:
`V022_HISTORICAL_REGRESSION_REPORT.md`.

## 4. What v0.2.2 does NOT change

- The ≥0.95 actual-mask gate, physical audit, SHA-256/grid contracts;
- classes B and C as hard errors (batch stop);
- the panel's existing verdicts and published numbers (its single
  zero-valid product already passes the stricter v0.2 precondition, so
  both contracts agree on it);
- the readiness semantics (batch verdict must still be a QA_PASS
  variant for READY);
- nothing is applied retroactively to frozen v0.2 artifacts; v0.2.2
  applies to the repair batch record and future exports only, and only
  after Owner approval.

## 5. Effective conditions

This contract becomes effective only when the Owner: (a) approves this
document, (b) records approval in the checksum file
(`V022_PROTOCOL_CHECKSUM.json` `owner_approval` field), and (c) the
readiness decision is re-stamped in a NEW artifact (original
`V0_2_1_FINAL_READINESS_DECISION.json` NOT_READY result is preserved as
history). Until then, v0.2 remains the operative contract.
