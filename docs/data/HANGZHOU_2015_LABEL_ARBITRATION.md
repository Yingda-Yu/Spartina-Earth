# Hangzhou Bay 2015 Pilot-0 — Label Arbitration Report (M1.3)

Outputs:
- `artifacts/audit/pilot0/label_arbitration.json`
- `artifacts/audit/pilot0/label_arbitration_samples.csv`
  (120 deterministic stratified points for OWNER visual inspection)
- `work/hangzhou2015/v1/{silver_2015_30m,label_disagreement_30m,ignore_30m}.tif`

Script: `scripts/data/hangzhou2015/arbitrate_labels.py` (seed 0,
deterministic; read-only inputs).

Neither label is GOLD. "SILVER" = national 2015 IGA distribution
product (DOI 10.12041/geodata.65372070926827.ver1.db). "WEAK" = local
legacy mask `c201511839DTSP_2.tif` of unknown production rule.

---

## 0. National product semantics established first

The national file is a **presence-only thematic raster**: VAT lists a
single class Value=1 (608 287 px nationally); value 255 is storage
NoData and even unequivocally inland points (Shanghai city centre,
inland Jiangsu) read 255. We therefore read 1 = *Spartina present* and
255 = *background*. Whether "background" means verified absence or
"outside the mapped domain" is **not documented in the file**
(`MISSING_EVIDENCE`); metrics below follow the product's stated purpose
as a complete national distribution map while flagging this caveat.
All metrics are computed on the correctly warped EPSG:32651 grid;
M1.1's raw-window comparison was approximate.

## E. Why is Jaccard only ≈0.49?

Full-window confusion (background treated negative):

| | pixels | area km² |
|---|---:|---:|
| both positive (TP) | 9 855 | 8.870 |
| SILVER-only (FN vs WEAK) | 4 416 | 3.974 |
| WEAK-only (FP vs WEAK) | 5 723 | 5.151 |
| union | 20 004 | 17.995 |
| WEAK total | 15 578 | 14.020 |
| SILVER total | 14 271 | 12.844 |

**Jaccard 0.4929**, precision of WEAK vs SILVER 0.633, recall 0.691.
This confirms the earlier ≈0.497 on the proper grid — the disagreement
is real, not a projection artefact. It is also **not** a systematic
translation: the ±5 px shift scan peaks at zero lag, and content
co-registration is within one pixel (see co-registration report). The
gap arises from genuinely different map content, summarised below.

## F. Geography of disagreement

**SILVER-only (3.97 km², 248 components, median 3 px, largest
0.38 km²):**
- 69 % of pixels lie 30–90 m from a WEAK boundary; 84 % within 300 m;
  only 0.57 km² is >300 m interior. 180/248 components are ≤9 px.
- Spectral/SAR context: mean NDVI 0.117, SAI −0.214; 33 % mudflat/
  wet-soil proxy, 63 % sparse-veg proxy, 4 % green-veg.
- Interpretation: **boundary buffering + fragmented marginal stands /
  mixed 30 m pixels** that the local mask did not include. Boundary
  convention differences at 30 m explain the majority.

**WEAK-only (5.15 km², 527 components):**
- **85 % of pixels are >300 m from any SILVER pixel** (median distance
  2 014 m); 4.39 km² forms distant patches. 436 components are tiny
  (≤9 px, 0.95 km²) but **9 components of 101–1 000 px contain
  2.36 km²**, largest 0.81 km² — material, isolated stands.
- Context: mean NDVI 0.189, SAI −0.311, VH −16.6 dB; 69 % sparse-veg,
  22 % green-veg proxy. These are vegetated, radar-rough pixels, **not**
  open water (0 % water proxy) and only 10 % mudflat/wet-soil proxy.
- Their SAI/NDVI/VH signatures sit between the both-positive class
  (SAI −0.422, NDVI 0.274, VH −15.6) and true background
  (SAI −0.140, NDVI 0.058, VH −20.4) — i.e. they are **more
  Spartina-like than the SILVER-only pixels**, but are equally
  consistent with other tall wetland vegetation (e.g. *Phragmites*) or
  with 2015 stands the national product omitted.
- WEAK-positive centroid lies 5.6 km W / 1.6 km S of the SILVER
  centroid — driven by these distant patches, **not** by a map-wide
  shift (intersection aligns at zero lag).

**Neither (background):** 70 % mudflat/wet-soil proxy, NDVI 0.058,
SAI −0.140, VV −12.8 / VH −20.4 dB.

Water-edge caveat: the NDWI proxy convention (Green,NIR; >0.10) marks
almost no in-window pixels as water because open water is fill/NaN in
the legacy optical export and turbid tidal water has low/negative
NDWI. The proxy classes are analytical aids, **not ground truth**.

**Summary of disagreement geography:** (i) SILVER-only is mainly
boundary-scale sparse/marginal pixels; (ii) WEAK-only is mainly a set
of isolated, distant, spectrally Spartina-like patches the national
map lacks; (iii) it is neither a small-patch-only effect (large
distant patches exist) nor a water-edge artefact, nor a systematic
offset.

## G. Could the WEAK mask come from a simple SAI/NDVI threshold?

On the optical-valid domain, exhaustive 1-D threshold sweeps and a
33×33 conjunction grid:

| Rule | Best parameter(s) | Jaccard vs WEAK | precision | recall |
|---|---|---:|---:|---:|
| SAI < t | t = −0.327 | 0.332 | 0.40 | 0.66 |
| NDVI > t | t = 0.181 | 0.338 | 0.39 | 0.72 |
| SAI < t_s ∧ NDVI > t_n | −0.292 / −0.028 | 0.337 | — | — |

All **REJECTED** (pre-declared plausibility 0.90; even the weak 0.75
bar fails). Any single global threshold over-predicts ~26–31 k pixels
vs 15.6 k. The local mask is **not reproducible** as a global SAI or
NDVI threshold of these composites, nor as their conjunction.
Segmentation + local thresholds, multi-index rules, manual editing, or
a different source composite remain untested — production rule stays
**UNKNOWN**.

## Arbitration decision for Pilot-0

Adopt **Issue #3 option 1 + option 3, conditional**:

1. **SILVER national 2015 is the evaluation reference** for Pilot-0
   (known provenance, peer-reviewed/distributed, complete coverage);
   the WEAK mask is **auxiliary information**, never the truth.
2. **IGNORE mask** for validation: invalid optical pixels plus
   disagreement pixels within **60 m (2 L8 px)** of either label
   boundary. On evaluable pixels Jaccard = **0.953** (P 0.969 /
   R 0.982) — disagreement is overwhelmingly boundary-adjacent after
   exclusion of the distant WEAK-only stands, which remain the key
   open scientific question.
3. The 9 large distant WEAK-only patches (2.36 km²) are **excluded
   from positive scoring but retained as a named "WEAK-only
   candidate" stratum** (not silently discarded). Baselines
   (Issue #5) report metrics on (a) SILVER reference with IGNORE and
   (b) the WEAK-only candidate stratum separately.
4. **No GOLD claim is permitted** until owner visual adjudication of
   `label_arbitration_samples.csv` (4 strata × up to 30 points) over
   best-available imagery, and ideally 2015-era high-resolution /
   field evidence for the distant WEAK-only patches. This is the
   principal unresolved blocker.

What would change the decision: if owner inspection confirms the
distant WEAK-only patches are Spartina, the SILVER product has local
omissions and Pilot-0 evaluation needs an uncertainty-weighted scheme
(option 2 consensus pseudo-label) for those components; if they are
other vegetation/mudflat, the WEAK mask is confirmed unsuitable as
reference and option 1 stands cleanly.
