# Spartina GoldSet Protocol v0.1 — Issue #11

Status: **PLANNING (v0.1)**. No GOLD labels exist in the repository today
(`PILOT0_DATASET_CARD.md`: GOLD labels = NONE). This document defines the
admission rules before any site is collected. It does not authorize
mapping, training, or label production.

Last updated: 2026-10-06 (M2.4 external-label intake guard added to
§1.1; no GOLD labels created — GOLD count remains 0).

---

## 1. What GOLD means (exhaustive list)

A pixel/polygon is admitted to GoldSet **only** when one of the following
holds **and** the acquisition date is independently verifiable:

1. **Field survey** — georeferenced ground observation (GPS/GNSS position,
   photo, observer, timestamp) recorded at the site.
2. **UAV or high-resolution imagery + expert interpretation** — the
   imagery has a known acquisition date and provenance, and interpretation
   is performed by a qualified expert against a written decision rule.
3. **Independent expert consensus** — at least two qualified interpreters
   independently label the same dated evidence and reach adjudicated
   agreement (see §5).

Without a verifiable acquisition date the record is **not admitted**,
regardless of visual quality.

### 1.1 Forbidden "upgrades" (max SILVER or WEAK)

| Source | Maximum tier |
|---|---|
| 2015 national Spartina raster | SILVER |
| CM-SSM products | SILVER (license/provenance permitting) |
| GEODATA national 30 m Spartina masks (1990/2000/2015/2020) | SILVER |
| CMSA annual Spartina vectors 2017–2021 (NESDC) | SILVER |
| Legacy local mask (`old datasets/`) | WEAK |
| SAI / NDVI / any index threshold | WEAK |
| Model predictions / pseudo labels | WEAK |
| Undated satellite-derived polygons | WEAK or rejected |
| Crowdsourced points without field evidence | WEAK |

**M2.4 guard (2026-10-06).** The GEODATA and CMSA national products
became available and byte-audited in M2.4 (see
`datasets/manifests/china_external_label_registry_v1.csv` and
`docs/audit/CHINA_EXTERNAL_LABEL_INTAKE_AUDIT_V1.md`). Authority of the
publisher, a 10 m / sub-meter input resolution, a DOI, or a reported
92–97 % accuracy does **not** confer GOLD: these products ship no
field/UAV/expert-verified label chain under our control, and their
accuracy claims have not been independently reproduced by us. All ten
entities are registered `label_tier=SILVER`, `gold_use=FALSE`. They may
be used only as *external reference products* (agreement/
disagreement/context), never as GoldSet seeds, never as evaluation
ground truth, and never as model training labels under current project
policy. The project GOLD count remains **0**.

## 2. Candidate site typology

GoldSet v0.1 must deliberately span the confuser space, not only the easy
core. Ten site classes:

| Code | Site type |
|---|---|
| G-DENSE | Dense, contiguous Spartina canopy |
| G-FRAG | Fragmented / patchy Spartina |
| G-TINY | Very small patches (below or near one 10 m / 30 m pixel) |
| G-MUD | Bare mudflat confounders (tidal exposure, tidal creeks) |
| G-PHRAG | Phragmites / reed confounders |
| G-NATIVE | Native salt-marsh vegetation (e.g. *Scirpus mariqueter*, *Suaeda*) |
| G-EDGE | Water / vegetation edge and open water |
| G-REMOVED | Documented post-removal / treatment sites |
| G-RECUR | Post-removal recurrence candidates |
| G-MIXED | Uncertain / mixed stands |

Stratification targets (how many sites per class) are **not set in v0.1**;
they require a power/precision analysis against benchmark metrics and are
decided with the user before field work is scheduled.

## 3. Required per-site record

Every site carries these fields; missing evidence is written
`MISSING`/`UNKNOWN`, never guessed:

| Field | Meaning |
|---|---|
| `site_id` | Stable id, e.g. `GOLD-HZB-0001` |
| `location` | Geometry (point/polygon) + CRS + positional accuracy |
| `acquisition_date` | Date of the *evidence* (field visit / image take), verified |
| `reference_source` | Field form / UAV mission id / imagery product id + license |
| `resolution` | GSD for UAV/high-res; GNSS accuracy for points |
| `annotator` | Identity + role/qualification |
| `annotation_method` | Written decision-rule / protocol version |
| `permission` | Land access + data-use permission documented |
| `label_confidence` | HIGH / MEDIUM / LOW with justification |
| `phenology_stage` | Recorded at visit (flowering/senescent/...) |
| `tide_state` | Observed note or explicit `PROXY`/`UNKNOWN` |
| `site_class` | One of the ten codes above |

A site without a demonstrable date **cannot** enter GoldSet.

## 4. Label ontology — four classes, no forced binary

Annotators use exactly:

- `SPARTINA`
- `NON_SPARTINA`
- `UNCERTAIN` — evidence present, class ambiguous
- `NON_EVALUABLE` — cloud, shadow, inundation, no-data, out of frame

`UNCERTAIN`/`NON_EVALUABLE` are first-class outputs; evaluation excludes
or reports them explicitly. They must never be silently mapped to 0.

## 5. Double annotation and adjudication

A defined subset of sites (target: the majority of polygon sites, all
G-FRAG/G-TINY/G-PHRAG/G-MIXED) is annotated twice, independently:

| Field | Content |
|---|---|
| `annotator_a` / `annotator_b` | Different people; B cannot see A's labels |
| `agreement` | IoU for polygons, confusion table for points, both by class |
| `disagreement` | Per-region description; no pixel averaging |
| `adjudication` | Third-expert decision or joint review session; dated |
| `adjudicator` | Identity; adjudicated labels are the GoldSet version |

Annotators use the same protocol version and the same dated evidence.
Inter-annotator agreement is a **reported dataset statistic**, not a
threshold for hiding disagreement.

## 6. Independence policy (GoldSet is held out, always)

Final Gold evaluation sites are forbidden from:

- model training or self-supervised pretraining sample selection;
- threshold / calibration fitting;
- weak-label generation tuning;
- hyperparameter or architecture search;
- Pilot-0 split construction and any future split revision.

Enforcement:

1. Gold site envelopes live in a separate manifest with an
   `evaluation_role: GOLD_EVAL` marker.
2. Before every data freeze, the isolation checker
   (`src/spartina/evaluation/goldset_isolation.py`) intersects Gold
   envelopes (with a documented buffer) against every train/val/test
   spatial unit; any overlap hard-fails the freeze.
3. Access is procedural: Gold envelopes are excluded from training data
   manifests by construction, not by convention.
4. GoldSet may only be consumed by evaluation code at a declared
   evaluation version; a GoldSet touch creates a new evaluation version.

## 7. Existing evidence assessment (2026-09-30)

- In-repository evidence for GOLD: **NONE**
  (`docs/benchmark/PILOT0_DATASET_CARD.md` §labels).
- Possible future high-confidence sources, all currently **MISSING /
  unverified**:
  - Wetland Ecosystem Research Station of Hangzhou Bay (CAF subtropical
    forestry institute) field data — `TODO_VERIFY`, requires agreement;
  - Zhejiang forestry / natural-resources survey materials (e.g. the
    provincial Spartina remediation inventories) — at best SILVER unless
    field sheets + dates are obtained;
  - New UAV campaigns under written permission — GOLD-eligible if §3 is
    satisfied.
- Nothing from legacy code, SAI thresholds, or model outputs may seed
  GoldSet (they may only motivate where to look, logged separately).

## 8. v0.1 deliverables and boundaries

In scope (planning): this protocol, the site schema, the isolation
checker, and a candidate-site **long-list design** (no acquisition yet).
Out of scope until user approval: field work, UAV flights, purchasing
imagery, labeling at scale, consuming GoldSet in any experiment.
