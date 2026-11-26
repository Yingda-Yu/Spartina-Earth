# HISTORICAL_QA_CONSISTENCY_AUDIT — zero-valid & partial-finite precedents

Retrospective scan of every landed product manifest from both executed
exports (panel Phase H: `work/issue21/export/manifests/`, 722 products;
repair Phase 2A: `work/issue21/export_repair/manifests/`, 35 products),
plus the Issue #19 pilot manifests (`work/national/pilot19/manifests/`).
Measured 2026-11-27 from manifests + landed rasters; no artifact was
modified.

## 1. Panel export (Issue #21 Phase H/I/J): 443 optical products

| class | count | disposition |
|---|---|---|
| zero QA_PIXEL-valid surface, **all bands 100 % finite** | **1** (`V02_R00355-C00151_L8_2015_L`) | honest rejection `ZERO_QA_VALID_SURFACE_PIXELS`, counted out of denominator; batch verdict `QA_PASS_WITH_HONEST_SOURCE_REJECTIONS` |
| partial non-finite SR bands (min band finite < 1.0), VALID > 0 | **146** | **accepted** — no error, no rejection |
| zero-valid AND partial-finite | **0** | never occurred |

## 2. Repair export (Phase 2A): 34 optical products (excl. the failure)

| class | count | disposition |
|---|---|---|
| partial non-finite SR bands, VALID > 0 | **22** (lowest min-finite 0.9802) | **accepted** |
| zero-valid (all classes) | **1** (`V021_R00372-C00139_L8_2015_E`; partial-finite too) | hard error under frozen precondition → batch `QA_FAIL_SYSTEMATIC_STOP` |

## 3. Issue #19 pilot

No zero-valid product landed in the pilot manifests; the
`ZERO_QA_VALID_SURFACE_PIXELS` class is *defined* in the v0.2 QA
contract citing the Issue #19 honest-rejection policy, but the pilot
never exercised the partial-finite + zero-valid combination either.

## 4. Consistency findings

1. **Partial non-finiteness has never been a rejection reason by
   itself**: 146 panel + 22 repair products with band gaps (min finite
   as low as 0.98) were all accepted when VALID > 0. The ≥0.95
   actual-mask byte gate is the operative tolerance; the 1.0 all-finite
   precondition only bites in the zero-valid corner case.
2. **The zero-valid + partial-finite combination is unprecedented.** The
   all-finite precondition in `_informative_check` was calibrated on a
   single historical case that happened to have 100 % finite bands. It
   was never validated against the combination that Phase 2A
   encountered.
3. **The precondition produces a de-facto inconsistency**: two products
   with the identical surface-quality defect (cell fully cloud-flagged,
   VALID = 0, byte-mask ≥ 0.95, physical audit pass) receive different
   verdicts solely because one has incidental band NaNs *inside
   non-clear pixels* — pixels that could never contribute surface data
   regardless (forensic: `FAILED_PRODUCT_FORENSIC_REPORT.md` §2).
4. **No phase ever accepted a zero-valid product.** The proposed v0.2.2
   revision therefore does not create an exception for the current
   failure; it aligns the classification of an untested corner case with
   the established treatment of the same phenomenon. No past acceptance
   or rejection would change under the proposal (see
   `V022_IMPACT_ANALYSIS.md` §retroactivity).

## 5. Verdict

The single hard error is an artifact of an untested precondition, not of
a systematic export failure — the historical record supports this
reading, but changing the classification requires the formal v0.2.2
revision (Owner-level), which this phase only proposes.
