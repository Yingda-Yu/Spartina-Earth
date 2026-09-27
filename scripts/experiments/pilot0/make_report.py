#!/usr/bin/env python
"""Aggregate Pilot-0 outputs into final CSVs/parquet/markdown report."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from spartina.experiments.aggregate import collect, write_outputs  # noqa: E402
from spartina.experiments.report import write_report  # noqa: E402
from spartina.experiments.runner import repo_root  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, default=repo_root())
    args = ap.parse_args()
    runs_root = args.repo / "runs/pilot0"
    out_dir = args.repo / "docs/experiments"
    tables = collect(args.repo, runs_root)
    write_outputs(tables, out_dir)
    p = write_report(args.repo)
    print(f"wrote {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
