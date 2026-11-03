# Feasibility Gate — Paper 1: Multi-Source Spartina alterniflora Map Reliability

**Decision:** PASS — meaningful cross-source comparison is feasible with the available data.

**Date:** 2026-11-03
**Branch:** feat/paper1-map-reliability
**Auditor:** Paper 1 execution (automated, evidence-bound)

---

## Q1: Can we conduct a scientifically meaningful same-year cross-source comparison?

### Evidence

| Criterion | CMSA 2020 | CM-SSM 2020 | GEODATA 2020 |
|---|---|---|---|
| Species | *S. alterniflora* | *S. alterniflora* | *S. alterniflora* |
| Year | 2020 | 2020 | 2020 |
| Geog extent | China coast (28–40°N, ~118M km² domain) | China coast (same) | China coast (same) |
| Native CRS | EPSG:32650 (WGS84 UTM 50N) | EPSG:32650 (same) | EPSG:2433 (Krasovsky Albers) |
| Format | Vector shapefile | Vector shapefile | 30m GeoTIFF |
| Positive class | gridcode=2 (verified in source) | All polygons are Spartina (presence-only) | Value=1 (VAT dbf verified; 255=NoData) |
| NoData handling | gridcode=0 absent (only 50 polygons) | None (presence-only) | Value=255 → 0 in binary |
| Independence from others | **Sentinel-2 10m, CAS-origin, no DOI found** | **Sub-meter drone + Sentinel-2 clump-level, Zenodo-hosted** | **Landsat-based 30m, CC-BY-NC-ND** |

### Conclusion: **YES, scientifically meaningful**

All three products target the same species and same geographic domain for calendar year 2020. They differ in native CRS, spatial resolution, patch-delineation semantics, and encoding style — exactly the conditions needed to quantify cross-source reliability.

### Caveat

CM-SSM's `name` column contains province codes (ZJ, FJ, SH, JS, etc.) that are **researcher-assigned metadata**, NOT authoritative administrative boundaries. Any regional attribution using these codes is circular and prohibited.

---

## Q2: How many independent products are available?

**Answer:** **3 genuinely independent products** (non-derivative, non-reprocessing):

1. **CMSA** — CAS researchers, Sentinel-2 10m, vector, stand-level aggregation, EPSG:32650, UNVERIFIED OPEN LICENSE
2. **CM-SSM** — Zenodo-hosted, sub-meter drone + Sentinel-2, clump-level individual polygons, EPSG:32650, **license conflict**: Zenodo says CC-BY-4.0, NESDC mirror says CC-BY-NC-4.0
3. **GEODATA** — separate research group, Landsat-based 30m raster, presence-only, EPSG:2433 (Krasovsky Albers equal-area), CC-BY-NC-ND

All three were produced by different research groups using different remote-sensing sources and different classification workflows. None is a derivative or reprocessing of another.

**Excluded from this count (verified):**
- No additional *Spartina alterniflora* distribution products found in work/intake/staging/ or work/external/ (search exhausted)
- CMSA 2017–2019, 2021: same product, different year (derivative)
- GEODATA 1990/2000/2015: same product, different year (derivative)
- CM-SSM province codes: metadata only, not a separate product

---

## Q3: What can be compared fairly?

### Fair comparisons (valid scientific question → valid data)

| Comparison | Rationale | Supported RQ |
|---|---|---|
| CMSA 2020 ↔ CM-SSM 2020 | Same CRS, same year, both vector → measures patch-delineation semantic difference | RQ1 (area), RQ2 (spatial), RQ3 (structure) |
| CMSA 2020 ↔ GEODATA 2020 | Same species, same year → measures resolution + encoding difference | RQ1, RQ2, RQ3 |
| CM-SSM 2020 ↔ GEODATA 2020 | Same species, same year → compound difference | RQ2, RQ3 |
| Resolution sensitivity (30→50→100m) | Harmonized grid → pure resolution effect | RQ3 |
| CMSA 2017–2021 annual area trend | Same product, consistent encoding → within-product temporal consistency | RQ4 |
| GEODATA 1990→2015 trend | Same product, consistent encoding | RQ4 (qualified) |

### The "hard floor" comparison (CMSA ↔ CM-SSM)

This pair is the most comparable (same CRS, same year, both vector) yet shows IoU=0.5375 — it sets a lower bound on agreement for two products targeting the same species. This finding is **novel and meaningful** precisely because the two products are the most similar structurally.

---

## Q4: What CANNOT be compared fairly?

### Invalid comparisons (explicitly prohibited)

| Comparison | Why invalid | What NOT to do |
|---|---|---|
| CMSA 2017 ↔ GEODATA 2015 | Different years → mixing expansion/contraction | Never construct artificial change series from incompatible years |
| CMSA planimetric vs GEODATA area | Different CRS: UTM planar (0.5% bias) vs Krasovsky Albers (equal-area) — BUT e3 already harmonizes both to EPSG:3410 so harmonized comparison IS valid | Compare *harmonized* areas only |
| CMSA vs CM-SSM using area statistics | Both are vector with the same CRS → area IS comparable; but area difference ≠ spatial disagreement | Present both area ratio AND IoU separately |
| Cross-product province attribution | CM-SSM province codes are researcher-assigned, not authoritative | Never write "Province X has more Spartina than Province Y" using CM-SSM codes |
| GEODATA 2020 vs CM-SSM 2020 area without harmonization | Native GEODATA uses equal-area projection; CM-SSM uses UTM planimetric | Use EPSG:3410 harmonized area only |

### Implicitly invalid: cross-year cross-product

CMSA 2017→2021 monotonically increases at +4.0%/year. GEODATA 2015→2020 shows apparent decline of 6.8%. These are **never directly comparable** (non-overlapping years). The conflict they create is presented as a product-encoding conflict (RQ4), not an ecological contradiction.

---

## Q5: What claims are IMPOSSIBLE with the available data?

### Absolute accuracy (ground-truth level)
- **No GOLD reference dataset found.** All results measure **inter-product agreement**, NOT accuracy against ground truth.
- This is the single most important scientific integrity limitation and MUST be stated prominently in the manuscript.

### Eradication effectiveness
- No treatment/eradication records linked to map products.
- Cannot distinguish "map says decrease" from "real eradication".

### Causal mechanisms
- No environmental covariates, management histories, or field observations.
- Cannot infer why one product maps more or less Spartina than another.

### Province-level rankings
- CM-SSM province codes are researcher-assigned metadata (not authoritative admin boundaries). Circular attribution prohibited.

### Management recommendations
- Without ground truth, without eradication data, without uncertainty quantification on individual maps → no actionable management advice.

---

## Final Verdict

**FEASIBILITY GATE: PASS** (with critical caveats)

The three independent products enable a meaningful same-year cross-source comparison that quantifies:
- Area disagreement between harmonized estimates (14.2% 2020 range)
- Spatial agreement at the most comparable product pair (IoU=0.5375 hard floor)
- Agreement sensitivity to resolution (≤0.4% change 30→100m)

**Non-negotiable caveats that MUST be incorporated into the manuscript:**
1. All results measure inter-product agreement, NOT ground-truth accuracy.
2. No independent reference data exist (E7 blocked).
3. Cross-year cross-product trends are product conflicts, not ecological conflicts.
4. CM-SSM province codes are researcher metadata, not admin boundaries.
5. Licensing restrictions: no redistributable source geometry, only aggregated statistics.
