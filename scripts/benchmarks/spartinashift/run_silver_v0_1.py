#!/usr/bin/env python3
"""Execute frozen SpartinaShift-Silver v0.1 Stage-1 baseline runs.

C2: train on CMSA 2020 Sentinel-2 (SPLIT-S2), select state/threshold on
VAL 2020, evaluate held-out 2020 reference and 2021 temporal shift.
One process per (model, seed); see --help.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

from spartina.benchmark.silver.protocol import SEEDS  # noqa: E402
from spartina.benchmark.silver.runner import (  # noqa: E402
    ALL_MODELS,
    NEURAL_MODELS,
    build_c2_spec,
    load_frozen_inputs,
    run_neural,
    run_rf,
)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--task", choices=["C2"], default="C2")
    ap.add_argument("--arm", choices=["s2", "s2_s1"], default="s2")
    ap.add_argument("--model", required=True,
                    choices=[*ALL_MODELS, "all"])
    ap.add_argument("--seed", required=True, type=int,
                    choices=[*SEEDS, -1],
                    help="frozen seed, or -1 for all seeds")
    ap.add_argument("--gpu", type=int, default=0)
    ap.add_argument("--smoke", action="store_true",
                    help="tiny deterministic sanity run (not an official run)")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    protocol, splits, matrix = load_frozen_inputs()
    print(f"[runner] protocol checksum verified: "
          f"{protocol['checksum'][:16]}...")
    task = build_c2_spec(matrix, splits, arm=args.arm)
    print(f"[runner] {args.task}/{args.arm}: "
          f"{sum(c.role == 'train' for c in task.cells.values())} train / "
          f"{sum(c.role == 'val' for c in task.cells.values())} val / "
          f"{sum(c.role == 'test' for c in task.cells.values())} test cells")
    models = list(ALL_MODELS) if args.model == "all" else [args.model]
    seeds = list(SEEDS) if args.seed == -1 else [args.seed]
    summaries = []
    for model in models:
        for seed in seeds:
            print(f"[runner] === {model} seed {seed} "
                  f"({'SMOKE' if args.smoke else 'official'}) ===")
            if model == "rf_pixel":
                summary = run_rf(task, seed=seed, smoke=args.smoke)
            else:
                if model not in NEURAL_MODELS:
                    raise ValueError(model)
                summary = run_neural(task, model, seed=seed,
                                     gpu_index=args.gpu, smoke=args.smoke)
            pooled = summary["evaluation"]["test_2020"]["pooled"]
            pooled21 = summary["evaluation"]["test_2021"]["pooled"]
            summaries.append({
                "model": model, "seed": seed,
                "test_2020_iou": pooled["iou"],
                "test_2021_iou": pooled21["iou"],
                "val_threshold": summary["training"]["val_threshold"]})
            print(f"[runner] {model} seed {seed} DONE: "
                  f"2020 IoU {pooled['iou']} 2021 IoU {pooled21['iou']}")
    print("[runner] all requested runs complete")
    print(json.dumps(summaries, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
