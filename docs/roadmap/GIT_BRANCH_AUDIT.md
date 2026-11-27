# GIT_BRANCH_AUDIT — 2026-11-26

Scope: three known branches (`main`, `reboot/spartina-earth-m0`,
`feat/paper1-map-reliability`), their common ancestry, divergence, and the
decision for the new large-project development branch.

## 1. Lineage facts (measured, local git)

| Branch | Tip | Tip commit date | Commits ahead of merge-base |
|---|---|---|---|
| `main` | `2be4672` ("Create README.md") | stale, pre-reboot | 0 (it IS the merge base) |
| `reboot/spartina-earth-m0` | `0cac824` (Issue #21 Phase I–J–L + readiness verdict) | 2026-10-18 | 97 |
| `feat/paper1-map-reliability` | `07dfff2` (paper1 R6, Git reference update) | 2026-11-09 | 115 |

Merge bases (measured with `git merge-base`):

- `merge-base(main, reboot/spartina-earth-m0)` = `2be4672` = `main` tip.
- `merge-base(main, feat/paper1-map-reliability)` = `2be4672` = `main` tip.
- `merge-base(reboot/spartina-earth-m0, feat/paper1-map-reliability)`
  = `0cac824` = `reboot` tip.

**Conclusion (lineage):** `main` is the common ancestor and is stale.
`reboot/spartina-earth-m0` carries the entire reboot + Issues #19/#20/#21
benchmark lineage. `feat/paper1-map-reliability` was branched FROM the
`reboot` tip and contains that lineage **plus** the Paper 1 work
(115 = 97 + 18 Paper 1 commits; `git diff --stat reboot..paper1` shows
122 files changed, +15,922 lines, all under `papers/paper1_map_reliability/`).

## 2. Which branch is the latest, most complete large-project code?

**`feat/paper1-map-reliability`.** It strictly contains
`reboot/spartina-earth-m0` (`0cac824` is its ancestor) and adds only
Paper-1-scoped files (manuscript, figures, submission package). No reboot
file was removed on Paper 1 branch: the diff `reboot..paper1` contains only
`papers/paper1_map_reliability/**` additions plus manuscript support files.

Consequences:

- Basing the new development branch on `feat/paper1-map-reliability`
  preserves both the full benchmark lineage AND all Paper 1 results
  (per owner instruction: keep all Paper 1 code/figures/audits/results).
- No rebase, no force push, no direct writes to `main` were performed.

## 3. Content comparison summary

| Content | main | reboot/spartina-earth-m0 | feat/paper1-map-reliability |
|---|---|---|---|
| M0 governance (AGENTS.md, RESEARCH_CONTEXT.md, legacy/ audit) | — | ✔ | ✔ |
| Issues #16–#18 national census / domain / disagreement audit | — | ✔ | ✔ |
| Issue #19 v0.1 pilot + products | — | ✔ | ✔ |
| Issue #20 silver_v0_1 benchmark results (C2/C4/C5 executed) | — | ✔ | ✔ |
| Issue #21 v0_2 artifacts (53-cell panel, reserve, gold registry, readiness NOT_READY) | — | ✔ | ✔ |
| Paper 1 manuscript + tables + EarthArXiv package (2026-11-08/09 state) | — | — | ✔ |
| Untracked local-only | — | `SpartinaGuard/`, `_incoming_task.txt` (never committed) | same |

Working-tree note: on the checked-out Paper 1 branch there are untracked
items (`SpartinaGuard/`, `_incoming_task.txt`,
`papers/paper1_map_reliability/submission/eartharxiv/figures/`). These are
local-only and remain untracked; nothing was deleted.

## 4. Decision taken

- New development branch
  **`reboot/spartina-earth-m2-7-repair`** created from
  `feat/paper1-map-reliability` @ `07dfff2aac090007aeee5625fd409e9b5d9b859d`.
- `main` untouched; no force push anywhere; Paper 1 branch left as-is.
- All v0.2.1 repair artifacts live in a NEW directory
  `benchmarks/spartinashift/v0_2_1_repair/` — the checksum-bound frozen
  artifacts under `benchmarks/spartinashift/v0_2/` are not modified.
- Next-stage fast-forward path: when the Owner accepts, this branch can be
  merged forward; `main` update is an explicit Owner decision only.

## 5. Integrity checks performed

- `v02_fresh_test_reserve.csv` SHA-256 `ff1d50ac…` matches the value
  recorded in `V0_2_FRESH_TEST_RESERVE.json` (`reserve_csv_sha256`). ✔
- `v02_cell_panel.csv` SHA-256 `6d527dc8…` matches `panel_csv_sha256`. ✔
- `V0_2_FRESH_TEST_RESERVE.json` `document_checksum` `d93e8820…` matches
  the bound checksum in `V0_2_READINESS_DECISION.json`. ✔
