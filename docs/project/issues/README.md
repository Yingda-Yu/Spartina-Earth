# Proposed GitHub issues (drafts, not yet filed)

`gh` is not installed/authenticated on this host, so the existing remote
**Issue #1 could not be read** and no issues were created online. The
drafts below are the M0/M1 split proposed by the reboot plan; the owner
should reconcile them with Issue #1 before filing (avoid duplicate
roadmaps).

## File map

| Draft | Title | Milestone |
|---|---|---|
| [M0-01](M0-01_m0_reboot_acceptance.md) | Accept M0 repository reboot and freeze the baseline | M0 |
| [M1-01](M1-01_environment_and_dependencies.md) | Create reproducible M1 environment (conda + lockfile) | M1 |
| [M1-02](M1-02_asset_manifests_and_checksums.md) | Manifest every `old datasets/` asset with SHA-256 | M1 |
| [M1-03](M1-03_label_qa_licensing.md) | Label QA gates and license/citation resolution | M1 |
| [M1-04](M1-04_gee_data_engine.md) | Implement the EO data engine (auth, collections, export, manifests) | M1 |
| [M1-05](M1-05_spatial_splits_and_leakage_ci.md) | Spatial-disjoint splits and leakage CI | M1 |
| [M1-06](M1-06_legacy_claim_adjudication.md) | Adjudicate manuscript claims (CISNet / multimodal drafts) | M1 |
| [M1-07](M1-07_spartinaguard_interface.md) | Freeze the research->SpartinaGuard product interface | M1 |

## Note on remote Issue #1

- Status: **UNREAD** (no `gh`, no token requested per M0 rules).
- Before creating issues: run `gh issue view 1` on an authenticated
  machine, map its bullet points onto the drafts above, and close/merge
  duplicates.
