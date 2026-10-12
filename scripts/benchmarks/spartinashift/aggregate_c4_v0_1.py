#!/usr/bin/env python3
"""Aggregate C4 cross-source agreement over the three frozen seeds."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
D = REPO_ROOT / "benchmarks" / "spartinashift" / "silver_v0_1" / "results" / "C4"
MODELS = ("rf_pixel", "unet", "deeplabv3plus", "segformer_b0")
SEEDS = (17, 42, 2026)
KEYS = ("iou", "f1", "precision", "recall", "bf1_30m", "bf1_60m", "auprc",
        "brier", "ece")


def msd(values: list[float | None]) -> dict[str, Any]:
    xs = [v for v in values if v is not None]
    if not xs:
        return {"n": len(values), "mean": None, "sd_seeds": None,
                "values": values}
    a = np.array(xs)
    return {"n": len(values), "n_finite": len(xs),
            "mean": float(a.mean()), "sd_seeds": float(a.std(ddof=0)),
            "values": values}


def main() -> int:
    out: dict[str, Any] = {
        "protocol_name": "SPARTINASHIFT_SILVER_V0_1_PROTOCOL",
        "task": "C4", "seeds": list(SEEDS), "models": list(MODELS),
        "agreement_is_not_accuracy": True,
        "cmssm_never_trained_or_tuned": True,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git_commit": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
            capture_output=True, text=True, check=True).stdout.strip(),
        "models_out": {}}
    for model in MODELS:
        docs = [json.loads((D / f"{model}_s2_seed{s}.json").read_text())
                for s in SEEDS]
        mout: dict[str, Any] = {"per_seed": {}}
        for label in ("GEODATA_2020", "CM_SSM_2020"):
            agg: dict[str, Any] = {}
            for key in KEYS:
                vals = [float(d["agreement"][label]["pooled"][key])
                        if d["agreement"][label]["pooled"][key] is not None
                        else None for d in docs]
                agg[key] = msd(vals)
            cis = [d["agreement"][label]["block_bootstrap"]["iou_ci95"]
                   for d in docs]
            agg["spatial_block_bootstrap_iou_ci95"] = cis
            per_seed = {}
            for d in docs:
                view = d["agreement"][label]
                per_seed[str(d["seed"])] = {
                    "iou": view["pooled"]["iou"],
                    "f1": view["pooled"]["f1"],
                    "n_cells": view["n_cells"],
                    "per_cell_positive_pixels":
                        [c["n_positive_pixels"] for c in view["per_cell"]],
                    "frozen_val_threshold": d["reuses"]
                    ["frozen_val_threshold"]}
            mout[label] = {"aggregate": agg}
            mout["per_seed"][label] = per_seed
        out["models_out"][model] = mout
    path = D / "aggregate_C4.json"
    path.write_text(json.dumps(out, sort_keys=True, indent=2,
                               ensure_ascii=False) + "\n")
    print(f"wrote {path.relative_to(REPO_ROOT)}")
    for model in MODELS:
        g = out["models_out"][model]["GEODATA_2020"]["aggregate"]["iou"]["mean"]
        c = out["models_out"][model]["CM_SSM_2020"]["aggregate"]["iou"]["mean"]
        print(f"  {model:15s} GEODATA {g}  CM-SSM {c}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
