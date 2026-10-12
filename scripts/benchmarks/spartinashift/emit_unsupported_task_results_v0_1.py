#!/usr/bin/env python3
"""Emit tracked no-run result records for frozen INSUFFICIENT_SUPPORT tasks.

C1 (GEODATA cross-year Landsat) and every C3 province holdout were frozen
INSUFFICIENT_SUPPORT before training. This script materialises those
verdicts as benchmark result artifacts from the frozen protocol only;
it executes no models and invents no metrics.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
BENCH = REPO_ROOT / "benchmarks" / "spartinashift" / "silver_v0_1"


def main() -> int:
    protocol = json.loads((BENCH / "SPARTINASHIFT_SILVER_V0_1_PROTOCOL.json")
                          .read_text())
    splits_sha = hashlib.sha256(
        (BENCH / "splits_v0_1.json").read_bytes()).hexdigest()
    matrix_sha = hashlib.sha256(
        (BENCH / "support_matrix_v0_1.csv").read_bytes()).hexdigest()
    git = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
        capture_output=True, text=True, check=True).stdout.strip()
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    base = {
        "protocol_name": protocol["protocol_name"],
        "protocol_checksum": protocol["checksum"],
        "splits_sha256": splits_sha,
        "support_matrix_sha256": matrix_sha,
        "git_commit": git,
        "emitted_utc": stamp,
        "runs_executed": 0,
        "metrics": "NOT_RUN_INSUFFICIENT_SUPPORT"}

    c1 = protocol["tasks"]["C1_cross_year_geodata_l8"]
    (BENCH / "results" / "C1").mkdir(parents=True, exist_ok=True)
    c1_out = {
        **base, "task": "C1", "verdict": c1["verdict"],
        "eo_sensor": c1["eo_sensor"], "bands": c1["bands"],
        "runs_planned": c1["runs_planned"],
        "evidence": c1["detail"]}
    (BENCH / "results" / "C1" / "C1_INSUFFICIENT_SUPPORT.json").write_text(
        json.dumps(c1_out, sort_keys=True, indent=2, ensure_ascii=False) + "\n")

    c3 = protocol["tasks"]["C3_cross_region"]
    (BENCH / "results" / "C3").mkdir(parents=True, exist_ok=True)
    c3_out = {
        **base, "task": "C3", "verdict": c3["verdict"],
        "runs_planned": 0, "rules": c3["rules"],
        "regions": c3["regions"]}
    (BENCH / "results" / "C3" / "C3_INSUFFICIENT_SUPPORT.json").write_text(
        json.dumps(c3_out, sort_keys=True, indent=2, ensure_ascii=False) + "\n")
    print("emitted C1 and C3 INSUFFICIENT_SUPPORT records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
