# PR_AUDIT — PR #22 (2026-11-26, Phase 1.1)

## 1. State (measured via `gh pr view 22 --json …`)

- **state: OPEN** — not merged, not closed, no auto-merge will be
  performed by the agent. `mergeable: MERGEABLE` (no conflicts).
- base: `main`; head: `reboot/spartina-earth-m2-7-repair`.
- The branch tracks `origin/reboot/spartina-earth-m2-7-repair`; pushes
  update the PR in place.

## 2. Scope of the PR — is it meant to integrate the whole project history?

**Yes, factually.** Because `main` is the stale pre-reboot ancestor
(`2be4672`), the PR diff `main…HEAD` spans the entire project lineage:
**117 commits ahead of `main`** (97 reboot + 18 Paper 1 + this branch's
commits), **994 changed files** (`gh` `changedFiles: 994`). Merging PR
#22 would therefore bring the whole reboot + Paper 1 history into `main`
in one fast-forward-style integration — it is NOT a "9-file patch PR".
This is now stated explicitly in the PR description so the Owner decides
with full information. Alternative (also documented): re-target the PR
to `feat/paper1-map-reliability` so it shows only the 9-file Phase-1
delta; that is an Owner decision and has NOT been executed.

Relative to the actual development base
(`origin/feat/paper1-map-reliability`), the **entire delta of this work
is exactly 9 added files** (verified `git diff --name-status`):
6 documents under `docs/roadmap/` + 3 artifacts under
`benchmarks/spartinashift/v0_2_1_repair/`. Phase 1.1 adds 4 more files
(failure ledger CSV, candidate audit, PR audit, verification log) and
revises 2 of the 9 in place.

## 3. Paper 1 history preservation (verified)

- `git diff origin/feat/paper1-map-reliability...HEAD -- papers/` is
  **empty**: no Paper 1 file was modified or deleted on this branch.
- All 18 Paper 1 commits remain in the branch ancestry
  (`07dfff2`…`6f0f5f4` linearly reachable).
- `feat/paper1-map-reliability` branch itself is untouched on the remote.

## 4. Frozen `benchmarks/spartinashift/v0_2/` integrity (verified)

- `git diff origin/feat/paper1-map-reliability...HEAD -- benchmarks/spartinashift/v0_2/`
  = **0 lines** — no frozen artifact modified, added, or deleted.
- New repair artifacts live exclusively in the new directory
  `benchmarks/spartinashift/v0_2_1_repair/`.
- Checksum re-verification of frozen files recorded in
  `PHASE_1_1_VERIFICATION.log` (panel CSV, reserve CSV, reserve JSON
  document checksum all match frozen records).

## 5. PR description corrections (applied via `gh pr edit`, PR stays OPEN)

The Phase 1 PR body contained the same imprecise failure accounting that
Phase 1.1 corrected ("6 NO_ELIGIBLE + 3 NO_SCENE cells"; "4–21 events").
The body now states: 9 cells / 10 failed cell-years (2020-only 7,
2015-only 1, both-year 1; primary NO_ELIGIBLE_EVENT_ACTUAL_MASK 6,
NO_SCENE 4; 6 of 10 failed cell-years mixed), and the event range
2–21 (positives 4–21), plus the whole-history scope note from §2.
No numbers in the body were invented to force agreement — they are
re-derived from the frozen CSVs and match `V0_2_1_FAILURE_LEDGER.csv`,
`V02_1_READINESS_REPORT.md` (rev.) and `PROJECT_STATUS_2026-11-26.md`.

## 6. Merge policy

No merge, no squash, no force-push. PR remains OPEN awaiting Owner
review; Phase 2 (live-GEE planner + export) starts only on explicit
Owner approval.
