# China mainland coastal-domain membership audit (v0 → v1 candidate)

Status: **v1_candidate — NOT FROZEN**. Machine-generated audit of
Issue #17 (domain membership), 2026-10-04.

> **Update 2026-10-08:** the v1 rule output below is retained unchanged
> and has been reproduced byte-for-byte; the owner decision added a v1.1
> layer freezing the KEEP core as **W10_DOMAIN_V1_CORE_FROZEN**
> (3,016 KEEP / 298 EXCLUDE / 5 PROVISIONAL_OFFSHORE_POLICY). See
> [CHINA_W10_FREEZE_RECOMMENDATION.md](CHINA_W10_FREEZE_RECOMMENDATION.md)
> and
> [`national/CHINA_DOMAIN_SUPERSESSION_v1_to_v1_1.json`](national/CHINA_DOMAIN_SUPERSESSION_v1_to_v1_1.json).
> This page remains the historical v1-candidate audit record. All decisions are
deterministic, target-independent, and versioned as attributes on the
**immutable** v0 cell-id space. The companion machine artefacts are:

* [`national/CHINA_DOMAIN_SUPERSESSION_v0_to_v1.json`](national/CHINA_DOMAIN_SUPERSESSION_v0_to_v1.json)
  — counts, full excluded/provisional cell lists, rule parameters,
  v0 registry SHA-256;
* [`national/DOMAIN_V1_SENSITIVITY.json`](national/DOMAIN_V1_SENSITIVITY.json)
  — W5/W10/W20 sensitivity;
* [`national/DOMAIN_V1_CONTEXT_PASSPORT_v0.json`](national/DOMAIN_V1_CONTEXT_PASSPORT_v0.json)
  and [`national/DOMAIN_V1_CONTEXT_FETCH_LEDGER_v0.json`](national/DOMAIN_V1_CONTEXT_FETCH_LEDGER_v0.json)
  — Murray/JRC source provenance and GEE call ledger;
* `datasets/manifests/china_coastal_cells_v1_candidate.{csv,parquet}` —
  one row per v0 cell (3,319 rows) with decision, reason and evidence;
* `datasets/manifests/china_domain_artifact_audit_v0.csv` — the 20
  Issue #16 flagged cells with full GIS evidence;
* `datasets/manifests/china_intertidal_context_v0.{csv,parquet}` —
  context-only Murray/JRC per-cell summaries.

Rule implementation:
[`src/spartina/data/national/domain_membership.py`](../../src/spartina/data/national/domain_membership.py);
GIS assembly:
[`scripts/data/national/audit_domain_membership_v1.py`](../../scripts/data/national/audit_domain_membership_v1.py);
context fetch:
[`scripts/data/national/fetch_domain_context_gee.py`](../../scripts/data/national/fetch_domain_context_gee.py).

## 1. Question and scope

The v0 "national coastal domain" conflated three different things: the
10 km corridor geometry, the W10 grid, and domain membership. Issue #17
asks whether every one of the 3,319 v0 W10 cells is genuinely a
**mainland China coastal** evidence unit, using only target-independent
geographic evidence (administration, coastline, fixed-distance rules) —
never labels, scene/event counts, model outputs, or intertidal context.

Layers:

| Layer | Source | Version | Role |
|---|---|---|---|
| Detailed coastline/land | GSHHS high-resolution L1 | 2.3.7 (`work/external/gshhg_2_3_7/SOURCE_PASSPORT.json`) | land polygons and coast |
| Administration | Natural Earth admin-0 | 10 m (`work/external/naturalearth_10m_admin0/SOURCE_PASSPORT.json`) | ownership only |
| Intertidal context | Murray Intertidal v1.1 (`UQ/murray/Intertidal/v1_1/global_intertidal`) | 11 epochs 1984–2016, CC BY 4.0 | context column only |
| Surface-water context | JRC GSW 1.4 (`JRC/GSW1_4/GlobalSurfaceWater`) | 1984–2021, Copernicus free use | context column only |

GSHHS polygons are clipped to the audit bbox in WGS84 **before**
projection into China Albers; projecting the unclipped continental
polygon corrupted regional spatial predicates in an earlier iteration.

## 2. The deterministic rule

Decision vocabulary (closed): `KEEP_MAINLAND_COASTAL`,
`KEEP_ISLAND_COASTAL`, `EXCLUDE_DOMAIN_ARTIFACT`,
`PROVISIONAL_UNRESOLVED`. Fixed ordering:

1. China-administered mainland land ≥ 100 m² in the cell →
   `KEEP_MAINLAND_COASTAL` (reason `CHINA_MAINLAND_LAND`; a foreign
   sliver alongside real Chinese land keeps the cell as
   `MIXED_CHINA_FOREIGN` with both shares recorded).
2. Otherwise contested-admin land present: distance to the Chinese
   mainland ≤ corridor half-width (10 km) →
   `PROVISIONAL_UNRESOLVED` (`CONTESTED_ADMIN_NEARSHORE`); beyond reach
   → `EXCLUDE_DOMAIN_ARTIFACT` (`CONTESTED_OUTSIDE_REACH`).
3. Otherwise a qualifying Chinese nearshore island ≥ 100 m² →
   `KEEP_ISLAND_COASTAL` (`CHINA_NEARSHORE_ISLAND`).
4. Missing landfall distances → `PROVISIONAL_UNRESOLVED`
   (`MISSING_EVIDENCE`; never guessed).
5. GSHHS land attributed to no admin unit covering ≥ 1 % of the cell →
   `PROVISIONAL_UNRESOLVED` (`UNADMINISTERED_LAND`).
6. Foreign-state land ≥ 100 m² (admin polygon or foreign-nearer
   landfall island) → `EXCLUDE_DOMAIN_ARTIFACT` (`FOREIGN_LAND_ONLY`).
7. Pure water cells: distance to Chinese mainland > 10 km →
   `EXCLUDE_DOMAIN_ARTIFACT` (`OPEN_WATER_OUTSIDE_REACH`); landfalls
   within a 500 m border tie → `PROVISIONAL_UNRESOLVED`
   (`BORDER_LANDFALL_TIE`); China strictly nearest →
   `KEEP_MAINLAND_COASTAL` (`CHINA_SEAWARD_WATER`); foreign strictly
   nearer → `EXCLUDE_DOMAIN_ARTIFACT` (`FOREIGN_NEARER_LANDFALL`).

Ownership normalisation on Natural Earth units:

* **China** = `China` ∪ `Hong Kong S.A.R.` ∪ `Macao S.A.R`. The SARs are
  Chinese territory; a naïve "anything not named China is foreign"
  reading had falsely excluded 23 Hong Kong/Macao cells in an internal
  iteration. They are folded before any rule runs.
* **Contested** = `Taiwan` (within the corridor this is the
  Kinmen/Matsu archipelago) and `Scarborough Reef`. Never folded into
  China, never silently deleted (see §5).
* Every other map unit (Russia, North Korea, South Korea, Japan,
  Vietnam, Philippines, …) = foreign state.

Island rule. v0 recovered GSHHS polygons absent from the generalised
admin layer when ≤ 100 km² with representative point within 25 km of
China. v1 additionally requires the **Chinese mainland to be the
strictly nearest administered landfall**; every unattributed polygon is
now assigned by nearest landfall (Chinese nearshore island, foreign
landfall, or genuinely unresolved). The v1 island set (2,996 pieces) is
a strict, independently computed superset-refinement of the v0 recovered
set (3,093 pieces) at the polygon level.

## 3. Results (W10, 3,319 v0 cells)

| v1 candidate decision | Cells | Reason breakdown |
|---|---:|---|
| `KEEP_MAINLAND_COASTAL` | 2,752 | `CHINA_MAINLAND_LAND` 2,152; `CHINA_SEAWARD_WATER` 600 |
| `KEEP_ISLAND_COASTAL` | 259 | `CHINA_NEARSHORE_ISLAND` 259 |
| `EXCLUDE_DOMAIN_ARTIFACT` | 298 | `OPEN_WATER_OUTSIDE_REACH` 256; `FOREIGN_LAND_ONLY` 39; `FOREIGN_NEARER_LANDFALL` 2; `CONTESTED_OUTSIDE_REACH` 1 |
| `PROVISIONAL_UNRESOLVED` | 10 | `UNADMINISTERED_LAND` 5; `CONTESTED_ADMIN_NEARSHORE` 5 |

Kept total **3,011 / 3,319**; nominal cell-area footprint
301,100 km² vs 331,900 km² v0 (−30,800 km²; sums of 100 km² cell
areas, not de-overlapped geographic area). Island classes across all
cells: MAINLAND 1,578; MAINLAND_PLUS_NEARSHORE_ISLAND 574;
NEARSHORE_ISLAND 264; NONE 903. Excluded artifacts = 8.98 % of the v0
registry — far more than the 20 manually flagged cells, which is why a
full-population rule audit was required.

## 4. The 20 Issue #16 flagged cells

All 20 are independently confirmed `EXCLUDE_DOMAIN_ARTIFACT` from the
pure rule (their v0 event-pair counts are recorded for provenance only
and are not decision inputs):

* 14 `MIXED_ADMIN_COAST_ARTIFACT` → 14 `FOREIGN_LAND_ONLY` (Russia /
  North Korea / Vietnam administered land; Tumen-border examples
  re-verified in UTM 52N, e.g. cell R00483-C00206 92.4 % Russian land,
  R00486-C00205 70.3 % Russian land);
* 6 `DOMAIN_EDGE_ARTIFACT` → 3 `FOREIGN_LAND_ONLY` + 3
  `OPEN_WATER_OUTSIDE_REACH`.

The three `INDEX_MISS` rows of the Issue #16 table (R00485-C00204,
R00485-C00205, R00486-C00204) contain real Chinese mainland land and
are `KEEP_MAINLAND_COASTAL`; they were footprint-index gaps, not domain
artifacts.

## 5. Hidden artifact classes found by the full scan

The 20 known cells were a subset. The other 278 exclusions and the
ownership corrections are the substantive new findings:

1. **Open-sea edge cells (256):** seaward corridor slivers more than
   10 km from any landfall. No administrative content, no intertidal
   zone — pure buffer geometry.
2. **Foreign-administered land beyond the known 14 (39 total):**
   additional Russia / North Korea / Vietnam coast-sliver cells and
   transboundary pieces (foreign-name breakdown: unnamed landfall
   slivers 11, Vietnam 10, Russia 9, North Korea 7,
   North Korea+Russia 2).
3. **Foreign-nearer water (2)** and **one contested beyond-reach cell**
   (a Kinmen-side cell 16.5 km from the Chinese mainland).
4. **SAR mis-attribution (corrected, not excluded):** 23 Pearl River
   delta cells that a literal admin-name reading marked foreign are
   Chinese (Hong Kong/Macao SAR) and are kept.
5. **Contested nearshore cells (5 provisional, not excluded and not
   claimed):** Kinmen islands cells at 118.27–118.49 E, 24.38–24.53 N,
   0.9–9.0 km from Fujian, with 2.3–60 km² Taiwan-administered land.
   One adjacent cell containing real Fujian mainland land is kept as
   mainland with the contested share recorded.

Border policy. Two evidence layers are deliberately retained: the
admin-clipped mainland AND raw GSHHS coastline. True Chinese coast
across the DPRK/Russia and Vietnam borders is kept (Chinese land
present → keep with mixed admin evidence), while corridor slivers over
the neighbour are excluded. Border landfalls within 500 m are
provisional rather than auto-assigned.

## 6. Provisional cells (10) — human closure required

| Cell | Lon/Lat | Reason | Note |
|---|---|---|---|
| CNA10K-R00231-C00093 | 113.97 E, 21.90 N | unadministered land ≥1 % | Pearl River estuary islets, 16.4 km from mainland |
| CNA10K-R00283-C00149 | 120.03 E, 25.97 N | unadministered land ≥1 % | Matsu-channel rocks, 27.3 km |
| CNA10K-R00314-C00162 | 121.83 E, 28.53 N | unadministered land ≥1 % | remote Zhejiang islands, 18.3 km |
| CNA10K-R00314-C00163 | 121.94 E, 28.51 N | unadministered land ≥1 % | remote Zhejiang islands, 26.4 km |
| CNA10K-R00316-C00163 | 121.97 E, 28.69 N | unadministered land ≥1 % | remote Zhejiang islands, 26.3 km |
| CNA10K-R00263-C00134 | 118.27 E, 24.38 N | contested nearshore | Kinmen, 7.7 km |
| CNA10K-R00264-C00134 | 118.28 E, 24.47 N | contested nearshore | Kinmen, 3.0 km |
| CNA10K-R00264-C00135 | 118.38 E, 24.45 N | contested nearshore | Kinmen, 8.9 km |
| CNA10K-R00264-C00136 | 118.48 E, 24.44 N | contested nearshore | Kinmen, 5.6 km |
| CNA10K-R00265-C00136 | 118.49 E, 24.53 N | contested nearshore | Kinmen, 0.9 km |

Closure requires a documented human decision (higher-resolution
administration/shoreline for the five unadministered cells; an explicit
programme policy on Kinmen/Matsu inclusion). They stay in the grid and
in the candidate manifest; no product freeze may silently include or
drop them.

## 7. Murray/JRC context — descriptive only

Fetched 2026-10-04 as batched server-side `reduceRegions` scalar
summaries at 30,000 m scale (83 batches per dataset, batch size 40,
166 reduce calls for a clean run; no national image/array export;
ledger in the fetch ledger JSON). Licenses: Murray CC BY 4.0 (cite
10.1038/s41586-018-0805-8); JRC under the Copernicus Programme, free
use with "Source: EC JRC/Google" attribution (10.1038/nature20584).

The Murray layer is a **coarse support indicator**: at 30 km sampling,
2,867 of 3,011 kept cells and also 249 of 298 excluded cells contain a
weighted intertidal pixel. The indicator therefore demonstrates coastal
reach at the population level but cannot measure cell-level tidal-flat
area (weighted fractions can exceed 1), and it is explicitly excluded
from membership decisions. JRC surface water is **not a tide proxy**;
its mean occurrence, seasonality and ever-water fraction are descriptive
columns only. Murray covers 1984–2016; it says nothing about post-2016
intertidal change.

## 8. W5 / W10 / W20 sensitivity

| Width | v0 cells | v1 kept | Excluded | Provisional | Artifact rate | Island-only cells | v1 cell area (km²) | Murray-present (kept) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| W5 (5 km) | 8,192 | 7,234 | 938 | 20 | 11.45 % | 792 | 180,850 | n/a (context at W10 only) |
| W10 (10 km) | 3,319 | 3,011 | 298 | 10 | 8.98 % | 264 | 301,100 | 2,867 |
| W20 (20 km) | 1,383 | 1,274 | 107 | 2 | 7.74 % | 92 | 509,600 | n/a (context at W10 only) |

Artifacts concentrate at finer widths (edge fragmentation); W10 keeps
the artifact rate below 10 % while limiting island-only fragmentation to
7.95 %. W20 dilutes the same artifacts over fewer, larger cells rather
than removing them. Corridor areas (v0, geographic): W5 142,048 km²,
W10 235,984 km², W20 388,139 km².

## 9. Integrity properties

* **Grid immutability:** the v0 registries
  (`work/national/domain/cells_china_albers_W*.csv`) are never
  overwritten; the W10 SHA-256 recorded in the supersession JSON is
  `144acb7a328692e871487f8ed58d50015800a70f91b64133d5e7cc950d5e6b25`.
  Excluded cells remain rows in the candidate manifest with a versioned
  membership attribute.
* **Target independence:** the evidence dataclass has no label, scene,
  event, pair-count, model or context field; `decide_membership` takes
  only evidence. Unit tests pin this
  (`tests/unit/test_domain_membership.py`, 19 tests).
* **Determinism:** identical evidence yields identical decisions; rule
  parameters are constants in one module and are echoed into the
  supersession JSON.
* **No fabricated completeness:** unresolved administration is marked
  provisional rather than forced to a binary outcome.

## 9a. First-pixel pilot re-validation (no execution)

The deterministic 20-cell panel in
`docs/data/national/FIRST_PIXEL_PILOT_DESIGN_v0.json` (five strata,
four geometry-edge quotas, SHA-256 ranked on cell IDs) was re-checked
against the v1 candidate tokens in
`datasets/manifests/china_coastal_cells_v1_candidate.csv` on
2026-10-04. Result: **20/20 active members, 0 excluded, 0
provisional** -- 19 `KEEP_MAINLAND_COASTAL` (reason
`CHINA_MAINLAND_LAND` for 18; `CNA10K-R00226-C00080` is
`CHINA_SEAWARD_WATER`, 1.55 km from the Chinese mainland) and 1
`KEEP_ISLAND_COASTAL` (`CNA10K-R00274-C00147`, nearshore island 7.99 km
out). No panel redesign is required; this is a membership re-validation
only -- no pixel download was executed and none is authorized. A unit
test pins this result (`test_first_pixel_pilot_references_only_active_v1_cells`).

## 10. Limitations

* Administration boundaries come from 10 m Natural Earth (generalised);
  fine border and estuary geometry is approximate, hence the 100 m²
  touch threshold and the 500 m border-tie band.
* Murray context ends in 2016; no modeled tide layer is deployed.
* Management/intervention event geometry is absent and plays no role
  here.
* v1 is a **candidate**: the 10 provisional cells require human closure
  before any freeze (see
  [`CHINA_W10_FREEZE_RECOMMENDATION.md`](CHINA_W10_FREEZE_RECOMMENDATION.md)).
