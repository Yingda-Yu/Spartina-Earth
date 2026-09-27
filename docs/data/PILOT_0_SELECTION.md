# Pilot-0 selection — Hangzhou Bay 2015 evidence baseline (M1.1)

Decision (recommendation, pending owner review): **Pilot-0 = the
Hangzhou Bay 2015 multi-modal bundle** under
`old datasets/Spartina/HangZhouBay/`.

## Why this site

1. **Only co-located multi-modal bundle in the store:** one mask, a
   7-band Landsat composite (`SR_B1..B7`), NDVI, SAI, and Sentinel-1
   VH/VV — all sharing one ~581 km² rectangle to sub-metre precision
   (see HANGZHOU_2015_ALIGNMENT_AUDIT.md). This is the minimal complete
   substrate for testing the data engine and co-registration code.
2. **Manuscript anchor:** both owner drafts use Hangzhou Bay / SCWHB
   (Fig. 3 of the CISNet paper; study area (d) of the SAI paper), so
   Pilot-0 work directly supports evidence closure for existing claims.
3. **Scale is tractable:** 581 km², files 0.7–31 MB; minute-scale
   processing; no bulk GEE download is needed to start.
4. **Failure modes are exposed here on purpose:** geographic vs
   projected grids, ~30 m Landsat vs ~10 m S1, weak-label provenance,
   date-provenance gaps — solving them here defines the reusable
   pipeline before national-scale work.

## Pilot-0 evidence baseline (frozen in M1.1 as *evidence*, not labels)

- Region: lon 121.018–121.418, lat 30.266–30.396; UTM 51N
  (EPSG:32651) bounds 309,298–348,029 E, 3,349,364–3,364,367 N.
- Mask: 0/1, 15,600 positive px = 14.004 km² (native pixel area;
  **WEAK tier**, provenance UNRESOLVED).
- Features: L8 SR_B1..B7 (uint16), NDVI (float32), SAI (float64) on a
  1486×482 EPSG:4326 grid (25.91×29.87 m ground); S1 VV/VH (float64)
  on 4456×1445 (8.64×9.96 m ground).
- Manuscript targets needing closure: 2015 row of Tables I/II/VI in
  `Spartina_Detection.pdf`; SCWHB results in the SAI manuscript.
- All six asset checksums are in `datasets/manifests/old_assets.csv`
  (STABLE_CANDIDATE at audit time; freeze pending owner confirmation).

## Open issues that gate science (but not engineering)

1. **Label provenance** (LABEL_TIER_REVIEW.md §2): mask is WEAK; no
   GOLD truth exists. Pilot-0 must commission GOLD/SILVER labels
   (expert interpretation protocol or field/UAV) before metrics count.
2. **Date provenance:** composite dates and cloud/tide filtering are
   unknown; obtain the original GEE export script or re-export with
   logged config (M1.2+; requires owner decision on GEE use).
3. **Count mismatch:** mask 15,600 vs paper Table I 12,347 sample
   pixels — determine label version/sampling difference.
4. **SAI polarity anomaly:** mask positives show lower SAI than
   negatives; SAI formula/version must be recovered.
5. **Registration:** implement documented co-registration in `work/`
   only; keep per-modality resolution provenance; no fake 10 m
   long-term products.

## Explicit non-goals for Pilot-0 (M1.1)

- No model training, no checkpoint use (none exist), no GEE bulk
  export, no change detection, no editing of `old datasets/`, no claim
  that the mask is ground truth.
