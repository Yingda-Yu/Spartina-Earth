#!/usr/bin/env python
"""Deterministic SAI threshold baseline (one official run, TEST-free)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from spartina.experiments.cpu_runs import run_spectral  # noqa: E402
from spartina.experiments.runner import load_all, repo_root  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, default=repo_root())
    args = ap.parse_args()
    man = run_spectral(load_all(args.repo), args.repo)
    print(f"SAI threshold={man['sai_train_threshold']:.3f} "
          f"train_iou={man['sai_train_iou']:.4f} "
          f"val_core_iou={man['val_core_iou']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
