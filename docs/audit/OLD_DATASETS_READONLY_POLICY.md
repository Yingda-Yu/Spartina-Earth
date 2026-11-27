# `old datasets/` read-only evidence policy (M1.1)

Status: **binding policy**. Applies to every human and AI agent working in
this repository.

## 1. What this directory is

`old datasets/` is the **historical evidence store** inherited from the
pre-reboot prototype. It contains the only bytes we have for the 2015
national raster, the 2020 CM-SSM vectors, Hangzhou Bay / Zhejiang /
Fujian experiment bundles, and owner-authored manuscript PDFs. It is
git-ignored because of size (rule 9), so its preservation cannot rely on
Git history.

## 2. Hard rules

1. **Never rename, move, delete, reproject, re-encode, repair, or overwrite
   anything** under `old datasets/`. This includes sidecars (`.tfw`,
   `.ovr`, `.aux.xml`, `.vat.dbf`, `.sr.lock`, `.cpg`, `.shx`, …) and
   files that look like duplicates or junk (`.rar`, `.exe`, lock files).
2. Tools open these files **read-only** (`rasterio.open`, `fiona.open`,
   `rb`). No tool writes derived data back into the tree.
3. All derived outputs live outside the tree:
   - machine evidence: `artifacts/audit/`, `artifacts/system/`,
     `artifacts/freeze/` (git-ignored bytes / JSON evidence);
   - working copies that require transformation: `work/` (git-ignored);
   - tracked reports / manifests: `docs/audit/`, `docs/data/`,
     `datasets/manifests/`.
4. The transfer may be ongoing. Files are marked `PENDING_TRANSFER` until
   two scans agree; even `STABLE_CANDIDATE` is **not** a declaration that
   the upload is finished — only the owner can declare that (freeze gate).
5. Integrity conclusions (checksum match, corruption, "duplicate",
   provenance) are recorded with timestamps and method, never asserted
   from a filename or from an M0 draft.
6. If legacy code or papers reference files under this tree, record the
   path as-is. Do not reorganize the tree to make references "neat".

## 3. Allowed vs forbidden operations

| Operation | Allowed? | Where output goes |
|---|---|---|
| Metadata read (driver, CRS, dims, schema) | yes | `artifacts/audit/`, `docs/audit/raster_reports/` |
| Windowed/blockwise pixel statistics | yes (read-only) | raster report JSON/MD |
| SHA-256 of stable files | yes | manifest + freeze sidecar |
| PDF text extraction | yes (copy bytes in memory) | manuscript inventory |
| Copy a file for repair/co-registration experiments | only into `work/` | `work/` |
| Rename / delete / reproject / resample in place | **never** | — |
| Add new data into the tree | **never by agents**; owner uploads only | — |
| Judge an `.exe`/archive as malware and remove it | **never remove**; document hash + finding | audit doc |

## 4. Transfer-state and freeze workflow

1. `scripts/audit/detect_transfer_state.py watch` records two scans
   (size/mtime/inode) separated by ≥ 5 minutes.
2. `STABLE_CANDIDATE` permits hashing/inspection work to proceed; it does
   not permit the freeze.
3. `scripts/audit/freeze_dataset.py` refuses to run without
   `--owner-confirmed-transfer-complete` **and** a stable scan; it
   re-verifies every checksum at freeze time.
4. Freezes are versioned (`V1`, `V2`, …), never overwritten.

## 5. Incident handling

If any agent process accidentally opens a file for writing or a tool
proposes a modification inside the tree: stop, do not commit, record the
path/timestamp in an audit note, and notify the owner. The preservation
priority of the raw evidence tree overrides every convenience.
