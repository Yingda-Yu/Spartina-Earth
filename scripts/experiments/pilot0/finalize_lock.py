#!/usr/bin/env python
"""Freeze all train/val decisions; prerequisite for the one TEST eval."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from spartina.experiments.lock import (  # noqa: E402
    build_lock,
    discover_official_runs,
    validate_matrix,
)
from spartina.experiments.registry import git_commit, git_dirty  # noqa: E402
from spartina.experiments.runner import load_all, repo_root  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, default=repo_root())
    args = ap.parse_args()
    env = load_all(args.repo)
    common = env["common"]
    lock_path = args.repo / common["paths"]["lock_file"]
    if lock_path.exists():
        raise SystemExit(f"lock already exists: {lock_path}")
    runs = discover_official_runs(
        args.repo / common["paths"]["runs_root"])
    counts = validate_matrix(runs)
    plan = {
        "variants": common["variant_order"],
        "seeds": common["seeds"],
        "threshold_grid": common["threshold"],
        "training": common["training"],
        "normalization_pct": [common["normalization"]["low_pct"],
                              common["normalization"]["high_pct"]],
        "mosaic": common["mosaic"],
        "rf": common["rf"],
        "expected_runs": counts,
    }
    payload = build_lock(
        runs, env["split_fingerprint"], env["norm_checksum"],
        git_commit(args.repo), git_dirty(args.repo), plan)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8")
    print(f"FROZEN {len(payload['runs'])} runs -> {lock_path}")
    print(f"lock_sha256: {payload['lock_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
