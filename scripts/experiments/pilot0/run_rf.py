#!/usr/bin/env python
"""One official Random Forest run on unique TRAIN pixels (TEST-free)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from spartina.experiments.cpu_runs import run_random_forest  # noqa: E402
from spartina.experiments.runner import load_all, repo_root  # noqa: E402

VARIANTS = ("optical", "optical_indices", "optical_sar", "full")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", choices=VARIANTS, required=True)
    ap.add_argument("--seed", type=int, choices=[17, 42, 2026],
                    required=True)
    ap.add_argument("--repo", type=Path, default=repo_root())
    args = ap.parse_args()
    man = run_random_forest(load_all(args.repo), args.repo,
                            args.variant, args.seed)
    print(f"RF {args.variant} seed={args.seed} "
          f"n={man['n_train_pixels']} thr={man['val_threshold']:.2f} "
          f"val_iou={man['val_core_iou']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
