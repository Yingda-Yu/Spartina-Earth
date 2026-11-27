# GOLDSET_ACQUISITION_PLAN — Independent reference labels for Spartina Earth

Version: v0.1 (plan only — no reference data collected, no promotion
executed). Registry audited: `benchmarks/spartinashift/v0_2/v02_gold_candidates.csv`
(30 sites, `CANDIDATE_ONLY`; `high_resolution_evidence_status = NOT_COLLECTED`
for all 30; `permission_provenance_status = UNVERIFIED_PENDING_OWNER` for all 30).

## 1. Tier definitions (frozen, from AGENTS.md §5)

| Tier | Definition | Current count |
|---|---|---|
| **GOLD** | Field survey / UAV imagery / expert-verified, with per-site evidence chain (date, operator, method, geolocation accuracy) | **0** |
| **SILVER** | Credible government or peer-reviewed mapping products with known provenance (GEODATA, CMSA, CM-SSM) | audited products only |
| **WEAK** | Index/rule/legacy automatic labels | legacy only |
| **UNLABELED** | Raw EO for self-supervised pretraining | all exported EO bytes today |

**No candidate is auto-promoted to GOLD.** Promotion happens only through
the protocol in §4–§6, executed by humans, with the evidence chain recorded
in the site registry.

## 2. Site registry (current state)

30 candidate sites, 12 provinces (FJ 4, ZJ 4, GD 3, GX 3, SD 3, JS 3, TJ 3,
LN 2, HEB 2, HN 1, SH 1, JL 1). Multi-label types (a site can carry >1):
SOURCE_AGREEMENT_POSITIVE 10, SOURCE_BACKGROUND 8,
SOURCE_DISAGREEMENT_POSITIVE 8, SMALL_FRAGMENTED_PATCH 6, BOUNDARY_SITE 6,
CONFOUNDER_PRONE 2.

Registry fields to extend during acquisition (new columns, frozen before
first collection): `reference_evidence_type`, `reference_acquisition_date`,
`operator`, `instrument`, `geolocation_accuracy_m`, `annotation_version`,
`reviewer_1`, `reviewer_2`, `disagreement_resolution`,
`final_tier`, `promotion_decision_id`, `license/permission ref`.

## 3. Independent reference acquisition plan

Priority order (strategic value first):

1. **SOURCE_DISAGREEMENT_POSITIVE (8)** — where GEODATA/CMSA/CM-SSM
   disagree; these quantify label-source error, the largest known threat to
   every downstream benchmark claim.
2. **SMALL_FRAGMENTED_PATCH (6) + BOUNDARY_SITE (6)** — boundary accuracy
   and small-patch recall are the metrics most sensitive to label quality.
3. **CONFOUNDER_PRONE (2)** — e.g., Suaeda/salt-marsh mixtures.
4. **SOURCE_AGREEMENT_POSITIVE (10) + SOURCE_BACKGROUND (8)** — confirmation
   sampling; cheapest, lowest information per site.

Reference data sources, per site (all require the permission gate in §7):

- **UAV flight** (preferred): ≥2 cm/px RGB + optional multispectral; flown
  within ±3 days of a clear Sentinel-2 overpass to bind the reference to a
  specific EO event; flight log + RAW imagery retained outside Git with
  manifest + SHA-256 in Git.
- **High-resolution commercial imagery** (fallback where UAV is infeasible):
  ≥0.5–1 m pan-sharpened, one scene per site, license permitting research
  annotation use; archive the license document.
- **Field survey** (where access is granted): per-site polygon walk /
  quadrat photos; GPS tracks recorded; photos time-stamped and
  geotagged; species identification by a qualified botanist
  (name + qualification recorded, personally identifying info kept out of
  public artifacts per project privacy rules).

## 4. Annotation protocol

- Annotation unit: polygon at native reference resolution, mapped onto the
  W10 cell grid; classes: `spartina_alive`, `spartina_dead/treated`,
  `other_vegetation`, `mudflat`, `water`, `other`.
- Digitization rules fixed before first site: minimum mapping unit 4 m²
  (UAV) / 25 m² (HR imagery); boundary placed at visually continuous cover
  edge; mixed pixels assigned by dominant cover.
- Each site produces: polygon shapefile/GeoJSON + per-polygon class +
  annotator notes + provenance JSON (dates, instruments, operators,
  resolution, QA flags).
- Every annotated polygon carries the **uncertainty record**: annotator
  confidence (3-level), edge ambiguity flag, tide state if relevant,
  and phenology note (DOY vs autumn window).

## 5. Double-review protocol

1. Annotator A produces polygons blind (no model outputs, no SILVER
   product overlays).
2. Annotator B independently re-annotates a 100% sample of
   DISAGREEMENT/CONFOUNDER sites and ≥30% of others.
3. Agreement metric: polygon IoU + class confusion computed per site;
   disagreement ≥10% IoU delta or any class conflict → adjudication by a
   third reviewer; the resolution is logged (`disagreement_resolution`).
4. Only sites passing double review enter GOLD consideration; the rest stay
   WEAK/reference-candidate with the recorded disagreement.

## 6. Spatial isolation policy

- GOLD sites inherit the spatial-isolation rules of SpartinaShift: site =
  its W10 cell; sites are assigned to splits at cell level by the future
  v0.2 protocol; GOLD evidence from a test cell must never be visible
  during training/tuning of that split.
- GOLD annotation is **not** used to re-select, re-draw, or re-label any
  benchmark panel cell label family (GEODATA/CMSA stay frozen as SILVER);
  GOLD is an independent evaluation reference.
- The 24-cell sealed reserve: no GOLD/UAV mission is flown over a reserve
  cell until the v0.2 protocol freezes roles, to keep the reserve
  genuinely untouched by any development decision.

## 7. Permissions and governance gate (blocking)

All 30 sites currently `UNVERIFIED_PENDING_OWNER`. Before any flight or
field visit: written permission / land-access confirmation per site,
recorded with document reference in the registry. Sites without confirmed
permission remain NOT_COLLECTED — no informal access, no fabrication.

## 8. Budget-scaled execution tiers

| Tier | Scope | Output |
|---|---|---|
| T1 (pilot) | 4 sites: 2 disagreement + 1 boundary + 1 small-patch (ZJ/FJ/SD/JS) | protocol validated end-to-end, double-review tested |
| T2 | + DISAGREEMENT/SMALL/BOUNDARY remainder (≈12 sites) | first defensible independent accuracy estimate vs SILVER products |
| T3 | all 30 | full GOLD evaluation panel |

## 9. Honest boundary

Until Tier ≥1 executes with double-reviewed polygons, every accuracy claim
in the project remains bounded by "GOLD = 0; agreement, not accuracy" — the
existing ledger rule. This plan changes nothing until executed.
