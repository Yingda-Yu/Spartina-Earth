#!/usr/bin/env python
"""Train ONE official (or smoke) neural baseline run.

TRAIN+VAL only. TEST is structurally unavailable to the engine. Usage:
  python train_neural.py --model unet --variant optical --seed 17 --gpu 1
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from spartina.experiments.registry import (  # noqa: E402
    RunContext,
    append_registry_row,
    git_commit,
    git_dirty,
)
from spartina.experiments.runner import load_all, repo_root  # noqa: E402
from spartina.models.baselines import MODEL_BUILDERS  # noqa: E402
from spartina.training.engine import train_neural_run  # noqa: E402

MODELS = ("unet", "deeplabv3plus", "segformer_b0")
VARIANTS = ("optical", "optical_indices", "optical_sar", "full")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", choices=MODELS, required=True)
    ap.add_argument("--variant", choices=VARIANTS, required=True)
    ap.add_argument("--seed", type=int, choices=[17, 42, 2026],
                    required=True)
    ap.add_argument("--gpu", type=int, required=True)
    ap.add_argument("--phase", choices=["official", "smoke"],
                    default="official")
    ap.add_argument("--epochs", type=int, default=None)
    ap.add_argument("--repo", type=Path, default=repo_root())
    args = ap.parse_args()

    ctx_env = load_all(args.repo)
    common = ctx_env["common"]
    model_cfg = ctx_env["model_cfgs"][args.model]
    in_channels = len(common["variants"][args.variant]["bands"])
    model, pretrained_meta = MODEL_BUILDERS[args.model](
        in_channels=in_channels, pretrained=True)

    ctx = RunContext(
        repo=args.repo,
        runs_root=args.repo / common["paths"]["runs_root"],
        registry_dir=args.repo / common["paths"]["registry_dir"],
        model=args.model, variant=args.variant, seed=args.seed,
        phase=args.phase).initialize()

    config_blob = json.dumps(
        {"common_frozen": {k: common[k] for k in
                           ("variants", "normalization", "labels",
                            "training", "threshold", "geometry",
                            "mosaic")},
         "model_cfg": model_cfg}, sort_keys=True)
    config_hash = hashlib.sha256(config_blob.encode("utf-8")).hexdigest()
    ctx.manifest.update({
        "git_commit": git_commit(args.repo),
        "dirty_tree": git_dirty(args.repo),
        "source_stack_checksum": ctx_env["sources"].stack_checksum,
        "split_logical_fingerprint": ctx_env["split_fingerprint"],
        "normalization_sha256": ctx_env["norm_checksum"],
        "config_sha256": config_hash,
        "optimizer": "AdamW",
        "lr": float(model_cfg["lr"]),
        "schedule": common["training"]["schedule"],
        "batch_size": int(common["training"]["batch_size"]),
        "variant_bands": common["variants"][args.variant]["bands"],
    })
    try:
        result = train_neural_run(
            ctx, common, model_cfg, ctx_env["sources"], ctx_env["grid"],
            model, pretrained_meta, args.variant, args.seed, args.gpu,
            {"checksum": ctx_env["norm_checksum"]},
            ctx_env["split_fingerprint"],
            epoch_override=args.epochs,
            patience_override=(10_000 if args.phase == "smoke" else None))
    except Exception as exc:
        ctx.fail(f"{type(exc).__name__}: {exc}")
        append_registry_row(args.repo, ctx.registry_dir, ctx.manifest)
        raise
    ctx.manifest.update({
        "training": {"best_epoch": result["best_epoch"]},
        "val_threshold": result["val_threshold"],
        "val_core_iou": result["val_core_iou"],
        "pos_weight": result["pos_weight"],
        "efficiency": result["efficiency"],
        "gpu": result["gpu"],
        "pretrained": result["pretrained"],
        "checkpoint_sha256": result["checkpoint"]["checkpoint_sha256"],
        "checkpoint_size_bytes": result["checkpoint"]["checkpoint_size_bytes"],
    })
    ctx.finalize("COMPLETED" if args.phase == "official" else "SMOKE_OK")
    append_registry_row(args.repo, ctx.registry_dir, ctx.manifest)
    print(json.dumps({
        "run_id": ctx.run_id, "best_epoch": result["best_epoch"],
        "val_threshold": result["val_threshold"],
        "val_core_iou": result["val_core_iou"],
        "checkpoint_sha256": result["checkpoint"]["checkpoint_sha256"][:16],
        "gpu": result["gpu"]["id"],
        "wall_s": round(result["efficiency"]["train_wall_s"], 1)},
        indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
