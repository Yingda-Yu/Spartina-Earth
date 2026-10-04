# W10 coastal-cell freeze recommendation (v1 candidate review)

Date: 2026-10-04. Companion:
[`CHINA_COASTAL_DOMAIN_V1_AUDIT.md`](CHINA_COASTAL_DOMAIN_V1_AUDIT.md)
and [`national/CHINA_DOMAIN_SUPERSESSION_v0_to_v1.json`](national/CHINA_DOMAIN_SUPERSESSION_v0_to_v1.json).

## Verdict

**REMAIN_PROVISIONAL — DO NOT FREEZE YET.**

The W10 grid geometry itself and the v1 membership rule are
deterministic, fully audited, and safe to use as a *candidate*; the
freeze is blocked only by ten `PROVISIONAL_UNRESOLVED` cells and the
formal owner acceptance of the v1 candidate. No pipeline should silently
treat "v1 candidate" as "frozen v1".

## Freeze criteria and current status

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | Grid geometry generated deterministically from documented parameters | PASS | `src/spartina/data/national/grid.py`; registries in `work/national/domain/`; 3,319 W10 cells |
| 2 | Cell IDs stable and immutable; v0 registry never overwritten | PASS | v0 SHA-256 pinned in supersession JSON; candidate manifest carries all 3,319 IDs on the same space; test `test_candidate_manifest_keeps_every_v0_cell_id` |
| 3 | Membership rule deterministic, ordered, parameter-locked | PASS | `domain_membership.py` constants; decisions reproducible; 19 unit tests |
| 4 | Known artifacts resolved and versioned | PASS | all 20 Issue #16 cells `EXCLUDE_DOMAIN_ARTIFACT`; 3 INDEX_MISS confirmed Chinese mainland; 278 further artifacts catalogued |
| 5 | No target leakage into membership | PASS | evidence schema contains no labels/scenes/events/model/context; Murray/JRC joined as context columns only |
| 6 | Source versions locked and licenses recorded | PASS | GSHHS 2.3.7, NE 10 m passports; Murray CC BY 4.0, JRC Copernicus in `DOMAIN_V1_CONTEXT_PASSPORT_v0.json`; GEE ledger records calls |
| 7 | Supersession complete and traceable | PASS | counts, full ID lists, parameters and hashes in the supersession JSON |
| 8 | No unresolved/provisional memberships | **FAIL** | 10 provisional cells (5 unadministered-land, 5 Kinmen contested) |
| 9 | Owner acceptance of v1 candidate and of contested-territory policy | **FAIL** | requires explicit human/programme decision |
| 10 | Downstream consumers migrated to membership-aware selection | **OPEN** | the 20-cell first-pixel pilot already references only active cells; census/event joins must filter on the frozen membership at adoption |

## What can be used now (candidate, not frozen)

* Spatial planning, strata design, coverage accounting against the 3,011
  active candidate cells.
* The 20-cell first-pixel pilot: re-validated against v1 on
  2026-10-04 — all 20 selected cells are
  `KEEP_MAINLAND_COASTAL`/`KEEP_ISLAND_COASTAL`; no replacement needed.
* Excluding the 298 artifact cells from new analysis footprints.

## Closure conditions for FREEZE_RECOMMENDED

1. Resolve the five `UNADMINISTERED_LAND` cells (Pearl estuary R00231-C00093;
   Matsu channel R00283-C00149; Zhejiang remote islands R00314-C00162,
   R00314-C00163, R00316-C00163) with a higher-resolution shoreline or
   explicit exclusion, each with recorded evidence.
2. Record an explicit programme decision on the five Kinmen cells
   (`CONTESTED_ADMIN_NEARSHORE`): include-with-disclaimer, exclude, or
   leave out of the frozen product with a stated reason. The rule must
   encode that decision as a versioned v1.1, never as an ad-hoc edit.
3. Re-run `audit_domain_membership_v1.py` so zero cells remain
   provisional (or a documented, owner-approved residual list is
   carried in the supersession record).
4. Re-run the full QA gate (`pytest`, `ruff`, `mypy --strict`) and
   record the accepting git commit in the supersession JSON; rename the
   artifact `v1_candidate → v1` only at that commit.
5. Owner sign-off recorded against Issue #17.

Until all five are met the frozen operational grid remains the v0
registry **with the v1 membership filter applied at read time**, and any
product using it must say so.
