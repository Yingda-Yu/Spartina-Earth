#!/usr/bin/env python
"""Run the ONE final TEST evaluation. Requires FROZEN lock + explicit env.

  SPARTINA_PILOT0_ALLOW_TEST=1 python final_eval.py --gpu 1
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from spartina.experiments.final_eval import evaluate_all  # noqa: E402
from spartina.experiments.runner import load_all, repo_root  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gpu", type=int, required=True)
    ap.add_argument("--repo", type=Path, default=repo_root())
    args = ap.parse_args()
    results = evaluate_all(args.repo, load_all(args.repo), args.gpu)
    print(f"{len(results)} runs evaluated on TEST exactly once")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
