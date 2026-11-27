# V022_REGRESSION_EXECUTION_REPORT — independent execution evidence

## 1. Code audit of `classify_v022.py` (frozen at commit `87eb333`)

| aspect | finding |
|---|---|
| REPO_ROOT resolution | `Path(__file__).resolve().parents[4]` — file sits at `benchmarks/spartinashift/v0_2_1_repair/V022_REGRESSION_TESTS/`, so parents[4] = repo root. **Verified correct** (an earlier parents[2] bug was caught by the 0-product result and fixed before the committed run) |
| manifest location | `REPO_ROOT/work/issue21/{export,export_repair}/manifests/*.json` — untracked data dir (gitignored by design); verified 722 + 35 manifests present |
| landed file paths | taken verbatim from each manifest's `landed_files[].local_uri`; opened only for zero-valid candidates (2 products) |
| coverage | 478 optical products (722 panel manifests − 244 Sentinel-1 + 35 repair); asserted == 443 + 35 |
| SHA-256 / grid evidence | for zero-valid candidates, SHA-256 match is taken from the re-verified `UPDATED_REPAIR_EXPORT_MANIFEST.json` fields (`sha256_match_manifest` flags, re-hashed 105/105 in Phase 2A.1) and grid/physical from the frozen QA manifest blocks — not recomputed from rasters in this script (grid rebuild lives in the frozen Phase J machinery, already run in Phase 2A) |
| assertions | 7 historical assertions hardcoded; all PASS (see §3) |

## 2. Clean-worktree re-execution (isolation)

The landed rasters/manifests are untracked data (gitignored), so a
clean worktree cannot see them by design; isolation was achieved by
checking out **clean code** at `87eb333` and symlink-mounting only the
untracked data directory (whose integrity is anchored by the recorded
SHA-256s):

```
$ git worktree add --detach /tmp/v022-wt 87eb333
$ ln -s /data/yingda/Spartina-Earth/work /tmp/v022-wt/work
$ cd /tmp/v022-wt/benchmarks/spartinashift/v0_2_1_repair/V022_REGRESSION_TESTS
$ /data/yingda/software/miniconda3/envs/spartina-earth/bin/python3.11 classify_v022.py
EXIT CODE: 0
```

Environment: Python 3.11.16, numpy 1.26.4, rasterio 1.4.3 (conda env
`spartina-earth`, same interpreter as the original run — isolation is
at the code-tree level; the interpreter is shared and recorded here).

Result: **all 7 assertions PASS; v0.2.2 reclassification list identical
to the committed run** (exactly one product, pixel evidence
`nonfinite_inside_offline_qa_valid_set = 0`, `fill_bit_pixels_anywhere
= 0`). Output file written inside the worktree; the committed
`V022_REGRESSION_RESULTS.json` in the main tree was not modified.

## 3. Assertions verified (both runs)

```
panel_optical_products = 443                  PASS
repair_optical_products = 35                  PASS
exactly_1_panel_honest_rejection              PASS
panel_partial_finite_accepted_146             PASS
repair_partial_finite_accepted_22             PASS
exactly_1_zero_valid_partial_finite_product   PASS
v0_2_2_changes_only_that_product              PASS
```

## 4. Raster-level regression execution

```
$ /data/yingda/software/miniconda3/envs/spartina-earth/bin/python3.11 \
    benchmarks/spartinashift/v0_2_1_repair/V022_REGRESSION_TESTS/raster_level_regression.py
EXIT CODE: 0
```

Coverage and findings: see `V022_FINAL_ACCEPTANCE_REPORT.md` §2 and
`V022_RASTER_LEVEL_REGRESSION.csv`. In short: 198/478 fully readable
(163 panel + 35 repair); 280 panel products have their local qapixel
mirror pruned (sr+valid present) — QA_PIXEL census impossible locally
for those; both zero-valid candidates fully covered; no unreadable
GeoTIFF.
