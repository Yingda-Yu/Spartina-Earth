# Hangzhou Bay 2015 bundle — grid alignment audit (Pilot-0 evidence)

Generated read-only by
`scripts/data/audit_hangzhou_alignment.py`
(machine evidence: `artifacts/audit/hangzhou_alignment.json`).
No pixel was resampled on disk; bounds were transformed for comparison
only.

## 1. Per-file facts

| File | CRS | Size | Bands/dtype | Native pixel (deg or m) | Ground pixel at centre |
|---|---|---|---|---|---|
| `c201511839DTSP_2.tif` (mask) | EPSG:32651 | 1292×501 | 1×uint8 | 29.977 m × 29.946 m | 29.98 × 29.95 m |
| `L8_AllBands_2015.tif` | EPSG:4326 | 1486×482 | SR_B1..B7 uint16 | 0.00026949° | **25.91 × 29.87 m** |
| `NDVI_2015.tif` | EPSG:4326 | 1486×482 | float32 | same | 25.91 × 29.87 m |
| `SAI_2015.tif` | EPSG:4326 | 1486×482 | float64 | same | 25.91 × 29.87 m |
| `S1_VH_2015.tif` | EPSG:4326 | 4456×1445 | float64 VH | 0.00008983° | **8.64 × 9.96 m** |
| `S1_VV_2015.tif` | EPSG:4326 | 4456×1445 | float64 VV | same | 8.64 × 9.96 m |

## 2. Answers to the six required questions

1. **Same region?** Yes. All six footprints cover one ~581 km²
   rectangle at Hangzhou Bay (lon 121.018–121.418, lat 30.266–30.396;
   UTM 51N bounds identical to the centimetre for mask/L8/NDVI/SAI).
2. **Same dates?** UNRESOLVED. Nothing in raster tags carries
   acquisition/composite dates; "2015" exists only in filenames.
   Manuscript Table II prints three 2015 dates (08/15, 09/01, 10/03),
   sensor line mislabelled TM. Whether each composite uses those dates
   is MISSING_EVIDENCE (no GEE export script present).
3. **Why is S1 ~3× denser?** S1 is exported on GEE's ~0.00008983°
   grid (≈10 m native Sentinel-1; anisotropic 8.64 m E–W × 9.96 m
   N–S at lat 30.3); 4456/1486 ≈ 3.00 and 1445/482 ≈ 3.00 ⇒ exactly
   3× per axis (9× pixels). It reflects native sensor spacing, not
   sub-pixel information beyond Sentinel-1's resolution.
4. **Which grid does the mask match?** The mask defines its own UTM
   50N grid (29.98 m); L8/NDVI/SAI geographic exports reproduce the
   mask rectangle *exactly* when reprojected (bounds identical to
   <0.01 m), so exports were cut from the mask region, but cell
   centres do not coincide (1292×501 vs 1486×482). S1 shares the
   rectangle to ~17 m/10 m (99.89% overlap).
5. **Spatial shift?** No datum-level mis-registration: same WGS84
   datum, transformed bounds agree. Grids are offset in sampling phase
   and cell size by construction; S1 edge offset ≈17 m W, ≈10 m S.
   Pixel-level alignment error after future co-registration will be
   bounded by ~half a 30 m L8 pixel (~15 m) and ~5 m for S1.
6. **Scientifically co-registerable?** Yes, with documented caveats:
   (a) reproject/cut features in `work/` only at explicit target grids;
   (b) never present S1 upsampled to 30 m or L8 at 10 m as "new"
   information — report analysis at a declared common resolution with
   resolution provenance per modality; (c) UTM 50N is the correct
   analysis zone for Hangzhou (zone 51 is present in the source mask;
   UTM **51N**, not 50N — EPSG:32651; the 2015 national product uses
   EPSG:32650, zone 50N, applied nationwide); (d) co-registration does
   not fix the label-provenance defect of the mask (WEAK tier).

## 3. Conclusion

The bundle is a deliberately assembled multi-modal window over one
region (mask rectangle ⇒ all exports), and is geometrically coherent.
It is suitable as the **Pilot-0 co-registration / data-engine test
bed**, but date provenance and label provenance must be closed before
any scientific metric is produced. No resampling has been performed in
M1.1.
