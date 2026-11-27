# QA_PIXEL_BIT_AUDIT — V021_R00372-C00139_L8_2015_E (Phase 2C P0)

Full pixel-level re-read of the landed QA_PIXEL GeoTIFF (151,285 px,
uint16). No prior report number was reused as input; every count below
is recomputed from the raster. Corrects the Phase 2B forensic report,
which contained an internally inconsistent pair of statements (see §3).

## 1. Per-bit census (USGS Landsat 8/9 Collection 2 QA_PIXEL, bits 0–7)

| bit | name | set pixels | % of cell |
|---|---|---|---|
| 0 | Fill | 0 | 0.0000 |
| 1 | Dilated Cloud | 12,097 | 7.9962 |
| 2 | Cirrus | 94,558 | 62.5032 |
| 3 | Cloud | 138,922 | 91.8280 |
| 4 | Cloud Shadow | 12,363 | 8.1720 |
| 5 | Snow | 0 | 0.0000 |
| 6 | Clear | **266** | **0.1758** |
| 7 | Water | 0 | 0.0000 |

## 2. Combination cross-tabulation (exhaustive, sums to 151,285)

| combo (fill, dil, cirrus, cloud, shadow, snow, clear) | n | % |
|---|---|---|
| 0,0,1,1,0,0,0 (cirrus+cloud) | 91,693 | 60.609 |
| 0,0,0,1,0,0,0 (cloud only) | 47,229 | 31.219 |
| 0,1,0,0,1,0,0 (dilated+shadow) | 9,232 | 6.102 |
| 0,1,1,0,1,0,0 (dilated+cirrus+shadow) | 2,865 | 1.894 |
| 0,0,0,0,1,0,1 (**shadow+clear**) | **266** | **0.176** |

## 3. Correction of the Phase 2B report

- **Wrong statement (2B)**: "`clear` bit is 0 in 100 % of pixels."
- **Corrected**: the Clear bit (6) is set in 266 px (0.176 %); all 266
  are simultaneously Cloud-Shadow-flagged (bit 4) with no other flag.
  Under USGS C2 semantics — as the Owner noted — Clear bit 6 is not the
  complement of cloud/shadow; here Google's C2 processing sets Clear on
  shadow pixels, and the production VALID predicate independently
  excludes them because Cloud Shadow ∈ blocked bits.
- The other 2B statement ("cloud_shadow+clear = 0.2 %") was correct and
  matches the 266-px class exactly.
- **QA outcome unchanged**: the offline QA predicate (clear SET and bits
  0–5 UNSET) yields **0 pixels**, identical to the landed VALID raster
  (0 nonzero pixels; pixel-wise XOR = 0). The product remains a
  zero-QA-valid-surface observation; the contradiction was in the
  2B prose only, not in any classification decision.

## 4. Reproducibility

All counts are reproducible from the landed raster
`work/issue21/export_repair/products/V021_R00372-C00139_L8_2015_E/*.tif`
by `V022_REGRESSION_TESTS/classify_v022.py` (condition-e block) and the
bit-census snippet embedded in `VALID_MASK_CONSISTENCY_REPORT.md` §4.
Landsat 7 note: L7 C2 QA_PIXEL uses the same bit layout with bit 2
(Cirrus) reserved/unused; the predicate is documented per-sensor in
`V022_QA_PROTOCOL_FINAL.md` §2.
