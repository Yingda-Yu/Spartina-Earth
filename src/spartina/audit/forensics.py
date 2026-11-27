"""SegFormer collapse forensics on TRAIN/VAL artifacts only.

TEST probabilities are never recomputed here. Frozen best.pt files are
reloaded for VALIDATION mosaics (VAL was never embargoed) to inspect
probability calibration. Quantities that the Issue #5 engine did not
record (per-step gradient norms, AMP scaler events, per-batch losses)
are reported as NOT_RECORDED, never reconstructed or guessed.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
import torch

from spartina.audit.paths import RunArtifact
from spartina.data.dataset import Pilot0WindowDataset, grid_view_masks
from spartina.evaluation.predict import predict_mosaic
from spartina.models.baselines import MODEL_BUILDERS
from spartina.models.baselines.inflation import inflate_kernel
from spartina.models.baselines.segformer_b0 import HF_NAME

COLLAPSE_TEST_RECALL = 0.15
# collapse is defined from STORED test metrics (read-only), never re-tuned


def _quantiles(p: np.ndarray[Any, Any]) -> dict[str, float]:
    qs = np.quantile(p, [0.0, 0.05, 0.5, 0.95, 1.0])
    return {"prob_min": float(qs[0]), "prob_p05": float(qs[1]),
            "prob_median": float(qs[2]), "prob_p95": float(qs[3]),
            "prob_max": float(qs[4])}


@torch.no_grad()
def val_probability_diagnostics(
    run: RunArtifact, env: dict[str, Any],
) -> dict[str, Any]:
    """Reload frozen checkpoint and score the VAL mosaic (CPU)."""
    ckpt_path = run.dir / "best.pt"
    ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    bands = ckpt["bands"]
    model, _ = MODEL_BUILDERS["segformer_b0"](
        in_channels=len(bands), pretrained=True)
    model.load_state_dict(ckpt["model_state"], strict=True)
    device = torch.device("cpu")
    model.to(device)
    sources, grid, common = env["sources"], env["grid"], env["common"]
    prob = predict_mosaic(model, sources, grid, run.variant, "val",
                          device, int(common["geometry"]["patch_px"]))
    coverage = ~np.isnan(prob)
    views = grid_view_masks(sources, grid, run.variant)
    valid = views["arbitrated_core"] & coverage
    p = np.nan_to_num(prob)[valid]
    y = sources.silver[valid]
    thr = float(run.manifest["val_threshold"])
    pos = p >= thr
    out: dict[str, Any] = {
        "val_n_valid": int(valid.sum()),
        "val_target_positive_px": int(y.sum()),
        "val_pred_positive_px_frozen_thr": int(pos.sum()),
        "val_pred_positive_fraction": float(pos.mean()),
        "val_pred_positive_fraction_at_05": float((p >= 0.5).mean()),
        "val_mean_prob_positive_ref": float(p[y].mean()) if y.any()
        else math.nan,
        "val_mean_prob_negative_ref": float(p[~y].mean()),
        "val_brier": float(np.mean((p - y.astype(np.float64)) ** 2)),
    }
    out.update(_quantiles(p))
    posq = _quantiles(p[y]) if y.any() else {}
    out.update({f"val_pos_ref_{k[5:]}": v for k, v in posq.items()})
    return out


def train_target_entry_check(
    run: RunArtifact, env: dict[str, Any],
) -> dict[str, Any]:
    """Confirm SILVER target pixels enter TRAIN windows (static data)."""
    from spartina.experiments.embargo import EmbargoGate
    sources, grid = env["sources"], env["grid"]
    gate: Any = EmbargoGate(None)
    ds = Pilot0WindowDataset(sources, grid, run.variant, "train", gate,
                             train=False)
    n_pos = n_core = n_weakonly = 0
    for i in range(len(ds)):
        item = ds[i]
        n_pos += int(item["y"][item["core_valid"]].sum().item())
        n_core += int(item["core_valid"].sum().item())
        n_weakonly += int(item["weak_only_mask"].sum().item())
    return {"train_windows": len(ds),
            "train_target_positive_px_in_windows": n_pos,
            "train_core_valid_px_in_windows": n_core,
            "train_weak_only_px_excluded_from_core": n_weakonly}


def inflation_check(run: RunArtifact) -> dict[str, Any]:
    """Verify inflation at CONSTRUCTION time (the code path used at train).

    Post-training checkpoint weights legitimately drift from the inflated
    initialization because the first layer is trainable; that drift is
    reported separately as evidence the layer was optimized, not frozen.
    """
    ckpt = torch.load(run.dir / "best.pt", map_location="cpu",
                      weights_only=False)
    in_c = len(ckpt["bands"])
    # fresh model exactly as the training CLI built it (pretrained weights)
    fresh, _ = MODEL_BUILDERS["segformer_b0"](
        in_channels=in_c, pretrained=True)
    built_proj = fresh.hf.segformer.encoder.patch_embeddings[
        0].proj.weight.detach()
    from transformers import SegformerForSemanticSegmentation
    ref = SegformerForSemanticSegmentation.from_pretrained(
        HF_NAME, num_labels=1, ignore_mismatched_sizes=True)
    rgb = ref.segformer.encoder.patch_embeddings[0].proj.weight.detach()
    expected = inflate_kernel(rgb, in_c) if in_c != 3 else rgb
    init_err = float((built_proj - expected).abs().max())
    ck_w = ckpt["model_state"][
        "hf.segformer.encoder.patch_embeddings.0.proj.weight"]
    trained_drift = float((ck_w - expected).abs().max())
    # at initialization every inflated channel must be identical
    per_channel_spread = float((
        built_proj - built_proj.mean(dim=1, keepdim=True)).abs().max())
    return {"inflation_input_channels": in_c,
            "inflation_init_max_abs_err": init_err,
            "inflation_init_channel_spread": per_channel_spread,
            "first_layer_trained_drift_from_init": trained_drift,
            "inflation_matches_rule": init_err < 1e-6}


def frozen_parameter_check(run: RunArtifact) -> dict[str, Any]:
    """Checkpoint keys must cover every model parameter exactly."""
    ckpt = torch.load(run.dir / "best.pt", map_location="cpu",
                      weights_only=False)
    model, _ = MODEL_BUILDERS["segformer_b0"](
        in_channels=len(ckpt["bands"]), pretrained=True)
    model_keys = set(model.state_dict())
    ck_keys = set(ckpt["model_state"])
    missing = model_keys - ck_keys
    unexpected = ck_keys - model_keys
    head_w = ckpt["model_state"].get(
        "hf.decode_head.classifier.weight")
    return {"state_dict_missing_keys": len(missing),
            "state_dict_unexpected_keys": len(unexpected),
            "head_shape": list(head_w.shape) if head_w is not None else [],
            "head_is_single_class": bool(
                head_w is not None and head_w.shape[0] == 1)}


def history_diagnostics(run: RunArtifact) -> dict[str, Any]:
    h = run.history or []
    losses = np.array([e["train_loss"] for e in h], dtype=np.float64)
    val = np.array([e["val_core_iou"] for e in h], dtype=np.float64)
    return {
        "epochs_recorded": len(h),
        "train_loss_finite_all": bool(np.isfinite(losses).all()),
        "train_loss_first": float(losses[0]),
        "train_loss_last": float(losses[-1]),
        "train_loss_min": float(losses.min()),
        "val_iou_finite_all": bool(np.isfinite(val).all()),
        "val_iou_first": float(val[0]),
        "val_iou_best_over_epochs": float(val.max()),
        "best_epoch": run.manifest["training"]["best_epoch"],
        # Issue #5 engine never persisted these -> explicit gap:
        "gradient_norm_recorded": False,
        "amp_scaler_events_recorded": False,
        "per_batch_loss_recorded": False,
        "per_epoch_val_loss_recorded": False,
        "nan_abort_flag": run.status == "FAILED",
    }


def classify(row: dict[str, Any]) -> str:
    if (row["inflation_init_max_abs_err"] >= 1e-6
            or row["state_dict_missing_keys"] != 0
            or row["state_dict_unexpected_keys"] != 0
            or not row["head_is_single_class"]
            or row["train_target_positive_px_in_windows"] == 0):
        return "IMPLEMENTATION_DEFECT"
    test = row.get("test_recall")
    val = row["val_iou_best_over_epochs"]
    if test is not None and not math.isnan(test) \
            and test < COLLAPSE_TEST_RECALL:
        if val < 0.2:
            return "OPTIMIZATION_INSTABILITY"
        # healthy TRAIN/VAL, healthy VAL probabilities, failure only on
        # the 5-component out-of-region TEST mosaic
        return "SMALL_DATA_STOCHASTIC_COLLAPSE"
    return "NO_COLLAPSE"


def build_forensics(
    runs: list[RunArtifact], env: dict[str, Any],
) -> pd.DataFrame:
    rows = []
    seg = [r for r in runs if r.model == "segformer_b0"
           and r.phase == "official" and r.status == "COMPLETED"]
    for run in sorted(seg, key=lambda r: (r.variant, r.seed or -1)):
        row: dict[str, Any] = {
            "run_id": run.run_id, "variant": run.variant,
            "seed": run.seed, "val_threshold": run.manifest["val_threshold"]}
        row.update(history_diagnostics(run))
        row.update(train_target_entry_check(run, env))
        row.update(val_probability_diagnostics(run, env))
        row.update(inflation_check(run))
        row.update(frozen_parameter_check(run))
        tm = run.test_metrics
        row["test_iou_read_only"] = (
            tm["arbitrated_core"]["iou"] if tm else math.nan)
        row["test_recall"] = (
            tm["arbitrated_core"]["recall"] if tm else math.nan)
        row["classification"] = classify(row)
        rows.append(row)
    return pd.DataFrame(rows)
