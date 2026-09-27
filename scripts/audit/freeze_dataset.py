"""Freeze the read-only ``old datasets/`` tree into versioned evidence.

This tool is PREPARED in M1.1 but MUST NOT be executed until the dataset
owner explicitly confirms the upload transfer is complete. It refuses to
run without ``--owner-confirmed-transfer-complete`` and refuses if the
latest transfer-state comparison is not STABLE_CANDIDATE.

When executed it produces:
  datasets/manifests/old_assets_frozen_v1.csv
  datasets/manifests/old_assets_frozen_v1.parquet
  artifacts/freeze/OLD_DATASETS_V1.sha256
  artifacts/freeze/OLD_DATASETS_FREEZE_V1.md

Read-only with respect to the scanned tree.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Imported lazily so ``--help`` works without geo deps.


def sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(chunk), b""):
            digest.update(block)
    return digest.hexdigest()


def git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except Exception:  # noqa: BLE001
        return "UNKNOWN"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("old datasets"))
    parser.add_argument(
        "--transfer-state", type=Path,
        default=Path("artifacts/audit/transfer_state.json"),
    )
    parser.add_argument("--owner-confirmed-transfer-complete", action="store_true")
    parser.add_argument(
        "--manifest-csv", type=Path,
        default=Path("datasets/manifests/old_assets.csv"),
    )
    parser.add_argument(
        "--frozen-csv", type=Path,
        default=Path("datasets/manifests/old_assets_frozen_v1.csv"),
    )
    parser.add_argument(
        "--frozen-parquet",
        type=Path,
        default=Path("datasets/manifests/old_assets_frozen_v1.parquet"),
    )
    parser.add_argument(
        "--sha-file", type=Path,
        default=Path("artifacts/freeze/OLD_DATASETS_V1.sha256"),
    )
    parser.add_argument(
        "--report", type=Path,
        default=Path("artifacts/freeze/OLD_DATASETS_FREEZE_V1.md"),
    )
    args = parser.parse_args(argv)

    if not args.owner_confirmed_transfer_complete:
        print(
            "REFUSED: freeze requires --owner-confirmed-transfer-complete "
            "after the owner declares the upload finished.",
            file=sys.stderr,
        )
        return 2
    state = json.loads(args.transfer_state.read_text(encoding="utf-8"))
    if state.get("overall_status") != "STABLE_CANDIDATE":
        print(f"REFUSED: transfer state is {state.get('overall_status')}", file=sys.stderr)
        return 2

    import pandas as pd

    frame = pd.read_csv(args.manifest_csv)
    pending = frame[frame["transfer_status"] != "STABLE_CANDIDATE"]
    if len(pending):
        print(f"REFUSED: manifest still lists {len(pending)} pending files", file=sys.stderr)
        return 2

    # Re-verify every checksum immediately before freezing.
    rows = frame.to_dict("records")
    mismatches: list[str] = []
    lines: list[str] = []
    for row in rows:
        rel = str(row["relative_path"])
        digest = sha256_file(args.root / rel)
        if digest != row["sha256"]:
            mismatches.append(rel)
        lines.append(f"{digest}  {rel}")
    if mismatches:
        print("REFUSED: checksum mismatch:\n" + "\n".join(mismatches), file=sys.stderr)
        return 2

    args.frozen_csv.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(args.frozen_csv, index=False)
    frame.to_parquet(args.frozen_parquet, index=False)
    args.sha_file.parent.mkdir(parents=True, exist_ok=True)
    args.sha_file.write_text("\n".join(sorted(lines)) + "\n", encoding="utf-8")
    total_bytes = int(frame["size_bytes"].sum())
    frozen_at = datetime.now(timezone.utc).isoformat(timespec="seconds")  # noqa: UP017
    report = f"""# OLD_DATASETS FREEZE V1

- Frozen at (UTC): {frozen_at}
- Git commit: {git_commit()}
- Root: `{args.root}` (read-only tree, never modified)
- Files: **{len(rows)}**
- Total bytes: **{total_bytes}** ({total_bytes / 2**30:.3f} GiB)
- SHA-256 manifest: `{args.sha_file}`
- Frozen tabular manifest: `{args.frozen_csv}`, `{args.frozen_parquet}`
- Basis: owner-confirmed transfer complete + two-scan STABLE_CANDIDATE + re-verified checksums

Any byte change in this tree invalidates this freeze; subsequent changes
require a new versioned freeze (V2), never an overwrite.
"""
    args.report.write_text(report, encoding="utf-8")
    print(f"FREEZE V1 written: {len(rows)} files, {total_bytes} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
