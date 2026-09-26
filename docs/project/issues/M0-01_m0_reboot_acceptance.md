# [M0-01] Accept M0 repository reboot and freeze the baseline

**Milestone:** M0
**Type:** process / acceptance
**Depends on:** nothing

## Context

Branch `reboot/spartina-earth-m0` reboots the repository: legacy prototype
preserved under `legacy/`, governance + research + audit docs added,
interface skeletons and stdlib-only tests added. See
`docs/audit/REPOSITORY_BASELINE.md` and the M0 acceptance report.

## Acceptance criteria

- [ ] Five logical commits present; tests/lint/type-check outputs recorded
- [ ] Audit docs reviewed (BASELINE, LEGACY_RESULT_AUDIT, DATA_INVENTORY,
      LABEL_INVENTORY)
- [ ] No large files, secrets, or `old datasets/` bytes tracked by Git
- [ ] Merge to `main` (owner decision; do not push/create PR without
      confirmation)

## Out of scope

Training, GEE downloads, foundation-model downloads.
