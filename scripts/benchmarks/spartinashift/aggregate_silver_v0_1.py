#!/usr/bin/env python3
"""Aggregate frozen SpartinaShift-Silver v0.1 per-run summaries over seeds.

Reads only the tracked ``results/<task>/*_<arm>_seed*.json`` files and
writes ``results/<task>/aggregate_<task>_<arm>.json``: per-model mean
and seed standard deviation for every headline metric, plus the spatial
block-bootstrap intervals produced by each run. No run is re-executed.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
RESULTS = REPO_ROOT / "benchmarks" / "spartinashift" / "silver_v0_1" / "results"

SCALAR_METRICS = (
    "iou", "f1", "precision", "recall", "auprc", "bf1_30m", "bf1_60m",
    "brier", "ece", "signed_area_bias", "pred_area_ha", "ref_area_ha",
    "patch_025_patch_recall", "patch_050_patch_recall")
VIEWS = ("val_2020", "test_2020", "test_2021")
MODELS = ("rf_pixel", "unet", "deeplabv3plus", "segformer_b0")
SEEDS = (17, 42, 2026)


def _num(x: object) -> float | None:
    return None if x is None else float(x)  # type: ignore[arg-type]


def _msd(values: list[float | None]) -> dict[str, Any]:
    xs = [v for v in values if v is not None]
    if not xs:
        return {"n": len(values), "mean": None, "sd_seeds": None,
                "min": None, "max": None}
    import numpy as np
    arr = np.array(xs, dtype=np.float64)
    return {
        "n": len(values), "n_finite": len(xs),
        "mean": float(arr.mean()),
        "sd_seeds": float(arr.std(ddof=0)),
        "values": values,
        "min": float(arr.min()), "max": float(arr.max())}


def _flatten(view: dict[str, Any], prefix: str) -> dict[str, float | None]:
    pooled = view["pooled"]
    out: dict[str, float | None] = {}
    for key in ("iou", "f1", "precision", "recall", "auprc", "bf1_30m",
                "bf1_60m", "brier", "ece", "signed_area_bias",
                "pred_area_ha", "ref_area_ha"):
        out[f"{prefix}_{key}"] = _num(pooled.get(key))
    for pk in ("patch_025", "patch_050"):
        out[f"{prefix}_{pk}_patch_recall"] = _num(
            pooled[pk]["patch_recall"])
        out[f"{prefix}_{pk}_n_ref"] = pooled[pk]["n_ref"]
    out[f"{prefix}_n_cells"] = view["n_cells"]
    out[f"{prefix}_n_positive_cells"] = view["n_positive_cells"]
    if "strata" in view:
        pos = view["strata"]["positive_cells"]
        bg = view["strata"]["background_cells"]
        out[f"{prefix}_posstratum_iou"] = _num(pos["iou"])
        out[f"{prefix}_posstratum_recall"] = _num(pos["recall"])
        out[f"{prefix}_bg_pred_area_ha"] = _num(bg["pred_area_ha"])
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--task", default="C2")
    ap.add_argument("--arm", default="s2")
    args = ap.parse_args()
    d = RESULTS / args.task
    summaries = []
    for model in MODELS:
        for seed in SEEDS:
            p = d / f"{model}_{args.arm}_seed{seed}.json"
            payload = json.loads(p.read_text())
            assert payload["status"] == "COMPLETED"
            summaries.append((model, seed, payload))

    aggregate: dict[str, Any] = {
        "protocol_name": "SPARTINASHIFT_SILVER_V0_1_PROTOCOL",
        "task": args.task, "arm": args.arm,
        "seeds": list(SEEDS), "models": list(MODELS),
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git_commit": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
            capture_output=True, text=True, check=True).stdout.strip(),
        "models_out": {}}
    for model in MODELS:
        rows = [x for x in summaries if x[0] == model]
        flat_runs: list[dict[str, float | int | None]] = []
        bootstraps: dict[str, list[list[float | None]]] = {
            "test_2020_iou_ci95": [], "test_2021_iou_ci95": [],
            "test_2020_f1_ci95": [], "test_2021_f1_ci95": []}
        for _, seed, payload in rows:
            flat: dict[str, float | int | None] = {"seed": seed}
            ev = payload["evaluation"]
            flat.update(_flatten(ev["test_2020"], "test_2020"))
            flat.update(_flatten(ev["test_2021"], "test_2021"))
            flat.update(_flatten(ev["val_2020"], "val_2020"))
            flat["threshold"] = payload["training"]["val_threshold"]
            flat["epochs_run"] = payload["training"]["epochs_run"]
            flat_runs.append(flat)
            for yr in (2020, 2021):
                bs = ev[f"test_{yr}"].get("block_bootstrap")
                if bs:
                    bootstraps[f"test_{yr}_iou_ci95"].append(
                        bs["iou_ci95"])
                    bootstraps[f"test_{yr}_f1_ci95"].append(bs["f1_ci95"])
        keys: list[str] = [k for k in flat_runs[0] if k != "seed"]
        agg = {k: _msd([row[k] for row in flat_runs])
               for k in keys}
        aggregate["models_out"][model] = {
            "per_seed": flat_runs, "aggregate": agg,
            "spatial_block_bootstrap_ci95": bootstraps}

    out = d / f"aggregate_{args.task}_{args.arm}.json"
    out.write_text(json.dumps(aggregate, sort_keys=True, indent=2,
                              ensure_ascii=False) + "\n")
    print(f"wrote {out.relative_to(REPO_ROOT)}")
    for model in MODELS:
        a = aggregate["models_out"][model]["aggregate"]
        print(f"  {model:15s} test2020 IoU "
              f"{a['test_2020_iou']['mean']} +/- {a['test_2020_iou']['sd_seeds']}"
              f" | test2021 IoU {a['test_2021_iou']['mean']} "
              f"+/- {a['test_2021_iou']['sd_seeds']}")
    return 0


if __name__ == "__main__":
    from typing import Any

    raise SystemExit(main())
