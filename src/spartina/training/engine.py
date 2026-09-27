"""Neural training engine for Pilot-0 baselines (train+val only).

TEST is never imported or accessed here. Checkpoints and probability
thresholds are chosen on VAL arbitrated_core IoU only.
"""

from __future__ import annotations

import copy
import subprocess
import time
from typing import Any

import numpy as np
import torch
from torch.utils.data import DataLoader

from spartina.data.dataset import (
    Pilot0WindowDataset,
    grid_view_masks,
)
from spartina.data.pilot0 import (
    Pilot0Sources,
    train_unique_pixel_mask,
)
from spartina.evaluation.metrics import (
    THRESHOLD_GRID_DEFAULT,
    choose_threshold,
    evaluate_view,
)
from spartina.evaluation.predict import predict_mosaic
from spartina.experiments.registry import RunContext
from spartina.training.losses import bce_pos_weight, segmentation_loss
from spartina.training.schedule import lr_at_epoch, seed_everything


def gpu_info(gpu_index: int) -> dict[str, Any]:
    try:
        out = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=name,memory.total,driver_version",
             "--format=csv,noheader,nounits", "-i", str(gpu_index)],
            capture_output=True, text=True, check=True)
        name, vram, driver = (x.strip() for x in out.stdout.splitlines()[0]
                              .split(",")[:3])
        return {"id": gpu_index, "model": name, "vram_mib": int(vram),
                "driver": driver}
    except Exception as exc:  # noqa: BLE001 - metadata only
        return {"id": gpu_index, "model": "UNKNOWN", "vram_mib": None,
                "driver": "UNKNOWN", "error": str(exc)}


def _collate(batch: list[dict[str, Any]]) -> dict[str, Any]:
    keys_tensor = ("x", "y", "core_valid", "strict_valid",
                   "weak_only_mask", "valid_inputs")
    out: dict[str, Any] = {k: torch.stack([b[k] for b in batch])
                           for k in keys_tensor}
    out["tile_id"] = [b["tile_id"] for b in batch]
    return out


def train_neural_run(
    ctx: RunContext,
    common: dict[str, Any],
    model_cfg: dict[str, Any],
    sources: Pilot0Sources,
    grid: Any,
    model: torch.nn.Module,
    pretrained_meta: dict[str, Any],
    variant: str,
    seed: int,
    gpu_index: int,
    normalization_payload: dict[str, Any],
    split_fingerprint: str,
    epoch_override: int | None = None,
    patience_override: int | None = None,
) -> dict[str, Any]:
    tcfg = common["training"]
    patch = int(common["geometry"]["patch_px"])
    device = torch.device(f"cuda:{gpu_index}" if torch.cuda.is_available()
                          else "cpu")
    seed_everything(seed)
    model = model.to(device)

    # pos_weight from unique TRAIN source pixels only
    train_union = train_unique_pixel_mask(sources)
    views = grid_view_masks(sources, grid, variant)
    core_train = views["arbitrated_core"] & train_union
    yt = torch.from_numpy(sources.silver[core_train].astype(np.float32))
    vt = torch.ones_like(yt)
    pos_w = bce_pos_weight(yt, vt, float(tcfg["bce_weight_cap"])).to(device)

    gate: Any = _NoTestGate()
    ds_train = Pilot0WindowDataset(
        sources, grid, variant, "train",
        gate=gate, patch=patch, train=True, base_seed=seed)
    ds_val = Pilot0WindowDataset(
        sources, grid, variant, "val",
        gate=gate, patch=patch, train=False)
    assert len(ds_val.rows) > 0  # gated VAL construction
    gen = torch.Generator()
    gen.manual_seed(seed)
    loader = DataLoader(ds_train, batch_size=int(tcfg["batch_size"]),
                        shuffle=True, num_workers=0, generator=gen,
                        collate_fn=_collate)
    opt = torch.optim.AdamW(model.parameters(),
                            lr=float(model_cfg["lr"]), weight_decay=0.01)
    scaler = torch.amp.GradScaler(  # type: ignore[attr-defined]
        "cuda",
        enabled=bool(tcfg["mixed_precision"] and device.type == "cuda"))
    max_epochs = (int(epoch_override) if epoch_override is not None
                  else int(tcfg["max_epochs"]))
    patience = (int(patience_override) if patience_override is not None
                else int(tcfg["patience"]))

    best_iou = -1.0
    best_epoch = -1
    best_threshold = 0.5
    best_state: dict[str, Any] | None = None
    history: list[dict[str, Any]] = []
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(device)
    windows_done = 0
    t0 = time.time()
    nan_abort = False

    for epoch in range(max_epochs):
        ds_train.set_epoch(epoch)
        lr = lr_at_epoch(float(model_cfg["lr"]), epoch, max_epochs,
                         int(tcfg["warmup_epochs"]))
        for pg in opt.param_groups:
            pg["lr"] = lr
        model.train()
        ep_losses: list[float] = []
        for batch in loader:
            x = batch["x"].to(device)
            y = batch["y"].unsqueeze(1).to(device)
            valid = batch["core_valid"].unsqueeze(1).to(device)
            opt.zero_grad(set_to_none=True)
            with torch.amp.autocast(  # type: ignore[attr-defined]
                "cuda",
                enabled=bool(tcfg["mixed_precision"]
                             and device.type == "cuda")):
                logits = model(x)
                loss, _, _ = segmentation_loss(
                    logits, y, valid, pos_w,
                    float(tcfg["loss_bce"]), float(tcfg["loss_dice"]))
            if not torch.isfinite(loss):
                nan_abort = True
                break
            scaler.scale(loss).backward()  # type: ignore[no-untyped-call]
            scaler.unscale_(opt)
            torch.nn.utils.clip_grad_norm_(model.parameters(),
                                           float(tcfg["grad_clip"]))
            scaler.step(opt)
            scaler.update()
            ep_losses.append(float(loss.detach().cpu()))
            windows_done += x.shape[0]
        if nan_abort:
            break

        # VALIDATION ONLY — mosaic-level core IoU, threshold grid on val
        prob = predict_mosaic(model, sources, grid, variant, "val",
                              device, patch)
        coverage = ~np.isnan(prob)
        core_val = views["arbitrated_core"] & coverage
        threshold, iou = choose_threshold(
            np.nan_to_num(prob), sources.silver, core_val,
            np.array(THRESHOLD_GRID_DEFAULT))
        history.append({"epoch": epoch, "lr": lr,
                        "train_loss": float(np.mean(ep_losses)),
                        "val_core_iou": iou, "val_threshold": threshold})
        if iou > best_iou:
            best_iou, best_epoch, best_threshold = iou, epoch, threshold
            best_state = copy.deepcopy(
                {k: v.detach().cpu() for k, v in model.state_dict().items()})
        if epoch - best_epoch >= patience:
            break

    train_wall_s = time.time() - t0
    if nan_abort or best_state is None:
        ctx.fail("non-finite loss or no valid validation epoch")
        raise RuntimeError(f"run {ctx.run_id} aborted: NaN/no progress")

    model.load_state_dict(best_state)
    ckpt_info = ctx.save_checkpoint({
        "model_state": best_state,
        "model": model_cfg["model"],
        "variant": variant,
        "seed": seed,
        "best_epoch": best_epoch,
        "val_threshold": best_threshold,
        "val_core_iou": best_iou,
        "bands": list(_bands(variant)),
        "normalization_sha256": normalization_payload.get("checksum"),
        "split_logical_fingerprint": split_fingerprint,
        "pretrained": pretrained_meta,
        "lr": float(model_cfg["lr"]),
    })

    # frozen-threshold validation metrics (both views), for the record
    prob = predict_mosaic(model, sources, grid, variant, "val", device,
                          patch)
    coverage = ~np.isnan(prob)
    p0 = np.nan_to_num(prob)
    val_core = evaluate_view(p0, sources.silver,
                             views["arbitrated_core"] & coverage,
                             best_threshold)
    val_strict = evaluate_view(p0, sources.silver,
                               views["silver_strict"] & coverage,
                               best_threshold)
    ctx.write_json("val_metrics.json",
                   {"arbitrated_core": val_core,
                    "silver_strict": val_strict})
    ctx.write_json("history.json", {"history": history})

    vram_peak = (torch.cuda.max_memory_allocated(device) / 2**20
                 if device.type == "cuda" else 0.0)
    efficiency = {
        "train_wall_s": train_wall_s,
        "peak_vram_mib": vram_peak,
        "train_windows_per_s": windows_done / max(train_wall_s, 1e-9),
        "train_pixels_per_s": (windows_done * patch * patch)
        / max(train_wall_s, 1e-9),
        "params": sum(p.numel() for p in model.parameters()),
        "checkpoint_size_bytes": ckpt_info["checkpoint_size_bytes"],
        "epochs_run": len(history),
    }
    return {
        "best_epoch": best_epoch,
        "val_threshold": best_threshold,
        "val_core_iou": best_iou,
        "checkpoint": ckpt_info,
        "efficiency": efficiency,
        "gpu": gpu_info(gpu_index),
        "pretrained": pretrained_meta,
        "history": history,
        "pos_weight": float(pos_w.detach().cpu()),
    }


def _bands(variant: str) -> list[int]:
    from spartina.data.pilot0 import VARIANT_BANDS
    return VARIANT_BANDS[variant]


class _NoTestGate:
    """Training-side gate: train/val allowed, test unconditionally denied."""

    def request_split(self, split: str) -> None:
        if split == "test":
            from spartina.experiments.embargo import TestEmbargoError
            raise TestEmbargoError(
                "training engine cannot request TEST under any condition")
