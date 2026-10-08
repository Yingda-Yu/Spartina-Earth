# W10 coastal-cell freeze record — W10_DOMAIN_V1_CORE_FROZEN

Dates: recommendation 2026-10-04; owner decision and v1.1 core freeze
2026-10-08 (Issue #17). Companions:
[`CHINA_COASTAL_DOMAIN_V1_AUDIT.md`](CHINA_COASTAL_DOMAIN_V1_AUDIT.md),
[`national/CHINA_DOMAIN_SUPERSESSION_v0_to_v1.json`](national/CHINA_DOMAIN_SUPERSESSION_v0_to_v1.json),
[`national/CHINA_DOMAIN_SUPERSESSION_v1_to_v1_1.json`](national/CHINA_DOMAIN_SUPERSESSION_v1_to_v1_1.json),
[`owner_review/w10_owner_decision_table_v1.csv`](owner_review/w10_owner_decision_table_v1.csv),
and the frozen registry
`datasets/manifests/china_coastal_cells_v1_1_core_frozen.csv|.parquet`.

## Verdict

**W10_DOMAIN_V1_CORE_FROZEN** (2026-10-08).

The W10 grid geometry, the deterministic v1 rule, and the documented
owner-decision layer together freeze a **3,016-cell KEEP core**
(2,752 `KEEP_MAINLAND_COASTAL` + 264 `KEEP_ISLAND_COASTAL`, nominal
footprint 301,600 km^2), with **298 excluded** artifact cells and **5
cells remaining provisional** as `PROVISIONAL_OFFSHORE_POLICY` outside
the frozen core. The freeze is a **core** freeze: it does not resolve
every spatial-policy question. The general offshore-island policy
beyond the fixed 25 km reach remains open.

The v1 candidate manifest (3,011/298/10) is retained unchanged; the
owner decisions are a separate, versioned layer (v1.1), never edits to
the deterministic rule output.

## Owner decision (2026-10-08)

| Group (5+5 cells) | Owner decision | v1.1 status |
|---|---|---|
| Kinmen cells, 0.9–8.9 km from the Fujian mainland (R00263-C00134, R00264-C00134/135/136, R00265-C00136) | KEEP_ISLAND_COASTAL | KEEP_ISLAND_COASTAL (production eligible) |
| Wanshan R00231-C00093; Juguang R00283-C00149; Dachen R00314-C00162/163; Dongji R00316-C00163 | REMAIN_PROVISIONAL | PROVISIONAL_OFFSHORE_POLICY (excluded from production) |

**Standing disclaimer (verbatim, applies to the five Kinmen cells):**

> Inclusion of cells intersecting contested-administered islands is an
> operational spatial-domain decision based on proximity to the
> mainland coast and does not constitute a statement on sovereignty or
> administrative status.

The contested-admin area fractions, admin names and landfall distances
for those five cells remain verbatim in their `membership_evidence`
JSON (supersession field `evidence_preservation`).

The fixed **25 km offshore-island reach was not extended** and no
cell-specific exception was created. The five beyond-reach cells
remain provisional until a separate, **general and
target-independent** offshore-island policy is established with
authoritative island/administration evidence; their cell IDs and full
GIS evidence are preserved for that review (v1.1 window).

## Production eligibility

* KEEP (3,016 cells): may be used in production datasets and primary
  inference.
* `EXCLUDE_DOMAIN_ARTIFACT` (298): excluded, retained in the registry.
* `PROVISIONAL_OFFSHORE_POLICY` (5): excluded from production datasets
  and primary inference; IDs and evidence preserved.

## Freeze criteria and final status

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | Grid geometry generated deterministically from documented parameters | PASS | `src/spartina/data/national/grid.py`; registries in `work/national/domain/`; 3,319 W10 cells |
| 2 | Cell IDs stable and immutable; v0 registry never overwritten | PASS | v0 SHA-256 pinned in both supersession JSONs; v1 and v1.1 registries carry all 3,319 IDs on the same space; tests `test_candidate_manifest_keeps_every_v0_cell_id`, `test_committed_v1_1_freeze_registry` |
| 3 | Membership rule deterministic, ordered, parameter-locked | PASS | `domain_membership.py`; re-run from cache on 2026-10-08 reproduced the v1 candidate byte-for-byte (SHA-256 `9dbd8cf5…`) |
| 4 | Known artifacts resolved and versioned | PASS | all 20 Issue #16 cells `EXCLUDE_DOMAIN_ARTIFACT`; 3 INDEX_MISS confirmed Chinese mainland; 278 further artifacts catalogued |
| 5 | No target leakage into membership | PASS | evidence schema contains no labels/scenes/events/model outputs; Murray/JRC joined as context columns only |
| 6 | Source versions locked and licenses recorded | PASS | GSHHS 2.3.7, NE 10 m passports; Murray CC BY 4.0, JRC Copernicus in `DOMAIN_V1_CONTEXT_PASSPORT_v0.json`; GEE ledger records calls |
| 7 | Supersession complete and traceable | PASS | counts, full ID lists, parameters and hashes in both supersession JSONs |
| 8 | Provisional memberships handled | PASS (documented residual) | zero `PROVISIONAL_UNRESOLVED` remain; 5 cells carried as an owner-approved residual list under `PROVISIONAL_OFFSHORE_POLICY`, outside the frozen core |
| 9 | Owner acceptance and contested-territory policy | PASS | Issue #17 owner decision 2026-10-08 (`w10_owner_decision_table_v1.csv`); operational inclusion under standing disclaimer; no sovereignty statement |
| 10 | Downstream consumers use membership-aware selection | ADOPTED | consumers filter on `production_eligible` / the two KEEP tokens; the 20-cell first-pixel panel is unaffected (19 mainland + 1 island KEEP cells) |

## Downstream impact of the five promoted cells

* Label strata over the 3,016 KEEP cells: 309 multi-product SILVER
  positive (was 308), 97 2015-only, 76 2020-only, 728 near-positive
  (was 724), 1,806 other unlabeled; all 482 product-positive cells are
  now core members.
* All five promoted cells were observed by at least one sensor in
  every year 2015–2025 in the metadata-only census.
* Issue #18 audit effect (recomputed from existing per-cell aggregates,
  same cluster bootstrap, seed 20201018;
  `2020_label_scale_audit_v2/table15_domain_v1_1_keep_effect.csv`):
  pooled Dice 30 m 0.6073 / 0.5293 / 0.7214 and 10 m 0.7093; point
  shifts versus the executed 3,011-cell primary at most 0.0003; only
  one promoted cell (R00264-C00135) carries 2020 mapped pixels (GEO
  0.684 km^2, CMSA 0.059 km^2, CM-SSM 0.542 km^2 at 30 m). No
  hypothesis decision changes.
* The 20-cell first-pixel panel needs no replacement.

## History

* 2026-10-04: recommendation issued as **REMAIN_PROVISIONAL — DO NOT
  FREEZE YET**, with five closure conditions.
* 2026-10-08: all five closure conditions met: (1) the five
  beyond-reach unattributed-land cells received an explicit owner
  decision to remain provisional under a named pending policy; (2) the
  five contested-administered Kinmen cells received an explicit
  programme decision with a standing disclaimer; (3) the deterministic
  audit was re-run from cache and reproduces the v1 candidate
  byte-for-byte, with the owner-approved residual list carried in the
  v1.1 supersession record (its `git_commit` field pins the code
  state, 7df0f74, that generated the record); (4) the full QA gate
  (`pytest` 413 passed / 21 skipped, `ruff`, `mypy --strict`) was run
  on the change set that commits this freeze; (5) owner sign-off is
  recorded against Issue #17.
