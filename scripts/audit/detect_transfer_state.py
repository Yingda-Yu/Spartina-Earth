"""Detect whether a directory tree is still being written to.

The user's ``old datasets/`` transfer may still be in progress. We must not
hash, judge integrity, or freeze provenance while files change, so this
tool records an immutable metadata snapshot (size, mtime, inode) and
compares two snapshots taken minutes apart.

Standard library only. Read-only: nothing under the scanned root is
opened for writing.

Subcommands
-----------
scan      Write one snapshot JSON.
compare   Compare two snapshot JSONs, write a transfer-state report.
watch     scan -> sleep INTERVAL -> scan -> compare, in one invocation.

Status vocabulary (closed set)
------------------------------
STABLE_CANDIDATE      identical size+mtime+inode in both scans
IN_PROGRESS           size or mtime changed, or path only in scan 2
DISAPPEARED           path present in scan 1, absent in scan 2
PENDING_TRANSFER      any non-stable state (alias used by downstream tools)

One stable comparison is NOT proof that the transfer is finished; the
final freeze happens only after the owner says uploads are complete.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STABLE = "STABLE_CANDIDATE"
IN_PROGRESS = "IN_PROGRESS"
DISAPPEARED = "DISAPPEARED"


def _utc_now() -> str:
    now = datetime.now(timezone.utc)  # noqa: UP017 (system Python 3.10 compat)
    return now.isoformat(timespec="seconds")


def scan_tree(root: Path) -> dict[str, Any]:
    """Record size/mtime/inode for every regular file under ``root``."""
    if not root.is_dir():
        raise FileNotFoundError(f"scan root is not a directory: {root}")
    files: dict[str, dict[str, Any]] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        # Deterministic traversal; do not prune anything (lock files and
        # hidden files are evidence too).
        dirnames.sort()
        for name in sorted(filenames):
            path = Path(dirpath) / name
            rel = path.relative_to(root).as_posix()
            try:
                st = path.stat()
            except OSError as exc:
                # A file vanishing mid-scan is itself a transfer signal.
                files[rel] = {"relative_path": rel, "error": repr(exc)}
                continue
            if not path.is_file():
                continue
            files[rel] = {
                "relative_path": rel,
                "size_bytes": st.st_size,
                "mtime_epoch": st.st_mtime,
                "mtime_utc": datetime.fromtimestamp(
                    st.st_mtime, tz=timezone.utc  # noqa: UP017 (system Python 3.10 compat)
                ).isoformat(timespec="seconds"),
                "inode": st.st_ino,
                "device": st.st_dev,
            }
    return {
        "scan_kind": "transfer_scan",
        "root": str(root.resolve()),
        "scan_time_utc": _utc_now(),
        "file_count": len(files),
        "total_bytes": sum(int(f.get("size_bytes", 0)) for f in files.values()),
        "files": files,
    }


def compare_snapshots(scan1: dict[str, Any], scan2: dict[str, Any]) -> dict[str, Any]:
    """Compare two snapshots produced by :func:`scan_tree`."""
    f1 = scan1["files"]
    f2 = scan2["files"]
    entries: list[dict[str, Any]] = []
    counts: dict[str, int] = {STABLE: 0, IN_PROGRESS: 0, DISAPPEARED: 0}
    for rel in sorted(set(f1) | set(f2)):
        a = f1.get(rel)
        b = f2.get(rel)
        if a is not None and b is None:
            status = DISAPPEARED
            detail = "present in scan 1, absent in scan 2"
        elif a is None and b is not None:
            status = IN_PROGRESS
            detail = "new path appearing after scan 1"
        else:
            changed = [
                key
                for key in ("size_bytes", "mtime_epoch", "inode")
                if a is not None
                and b is not None
                and a.get(key) != b.get(key)
            ]
            if changed:
                status = IN_PROGRESS
                detail = "changed: " + ",".join(changed)
            else:
                status = STABLE
                detail = "identical size/mtime/inode"
        counts[status] += 1
        entries.append(
            {
                "relative_path": rel,
                "transfer_status": status,
                "detail": detail,
                "size_bytes": (b or a or {}).get("size_bytes"),
                "mtime_utc": (b or a or {}).get("mtime_utc"),
                "inode": (b or a or {}).get("inode"),
            }
        )
    overall = IN_PROGRESS if counts[IN_PROGRESS] or counts[DISAPPEARED] else STABLE
    return {
        "report_kind": "transfer_state",
        "scan1_time_utc": scan1.get("scan_time_utc"),
        "scan2_time_utc": scan2.get("scan_time_utc"),
        "root": scan2.get("root", scan1.get("root")),
        "overall_status": overall,
        "counts": counts,
        "stable_is_not_final": (
            "STABLE_CANDIDATE means no change between these two scans only; "
            "final freeze requires explicit owner confirmation."
        ),
        "files": entries,
    }


def _write_json(payload: dict[str, Any], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_scan = sub.add_parser("scan", help="record one metadata snapshot")
    p_scan.add_argument("--root", required=True, type=Path)
    p_scan.add_argument("--out", required=True, type=Path)

    p_cmp = sub.add_parser("compare", help="compare two snapshots")
    p_cmp.add_argument("--scan1", required=True, type=Path)
    p_cmp.add_argument("--scan2", required=True, type=Path)
    p_cmp.add_argument("--out", required=True, type=Path)

    p_watch = sub.add_parser("watch", help="scan, sleep, scan, compare")
    p_watch.add_argument("--root", required=True, type=Path)
    p_watch.add_argument("--interval", type=int, default=360, help="seconds")
    p_watch.add_argument("--out", required=True, type=Path)
    p_watch.add_argument("--scan1-out", type=Path, default=None)
    p_watch.add_argument("--scan2-out", type=Path, default=None)

    args = parser.parse_args(argv)

    if args.command == "scan":
        snapshot = scan_tree(args.root)
        _write_json(snapshot, args.out)
        print(f"scanned {snapshot['file_count']} files -> {args.out}")
        return 0

    if args.command == "compare":
        with open(args.scan1, encoding="utf-8") as handle:
            s1 = json.load(handle)
        with open(args.scan2, encoding="utf-8") as handle:
            s2 = json.load(handle)
        report = compare_snapshots(s1, s2)
        _write_json(report, args.out)
        print(json.dumps({"overall_status": report["overall_status"], **report["counts"]}))
        return 0

    first = scan_tree(args.root)
    if args.scan1_out is not None:
        _write_json(first, args.scan1_out)
    print(
        f"scan 1: {first['file_count']} files, {first['total_bytes']} bytes; "
        f"sleeping {args.interval}s",
        flush=True,
    )
    time.sleep(args.interval)
    second = scan_tree(args.root)
    if args.scan2_out is not None:
        _write_json(second, args.scan2_out)
    report = compare_snapshots(first, second)
    _write_json(report, args.out)
    print(json.dumps({"overall_status": report["overall_status"], **report["counts"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
