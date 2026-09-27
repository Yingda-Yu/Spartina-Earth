"""The single permitted TEST evaluation, executed only after the lock."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import torch

from spartina.data.dataset import grid_view_masks, view_masks
from spartina.data.pilot0 import (
    VARIANT_BANDS,
    split_coverage_mask,
)
from spartina.evaluation.metrics import evaluate_view
from spartina.evaluation.predict import predict_mosaic
from spartina.evaluation.weak_response import (
    component_responses,
    material_weak_labels,
)
from spartina.experiments.embargo import read_lock
from spartina.models.baselines import MODEL_BUILDERS
from spartina.models.baselines.spectral import SAI_BAND, apply_rule


def verify_lock(path: Path) -> dict[str, Any]:
    lock = read_lock(path)
    if lock is None:
        raise RuntimeError("final evaluation lock missing")
    payload = dict(lock.payload)
    stated = payload.pop("lock_sha256", None)
    calc = hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    if stated != calc:
        raise RuntimeError("FINAL_EVAL_LOCK checksum mismatch")
    if payload.get("status") != "FROZEN":
        raise RuntimeError("lock is not FROZEN")
    return lock.payload


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def evaluate_all(
    repo: Path, env: dict[str, Any], gpu_index: int,
) -> list[dict[str, Any]]:
    env["gate"].request_split("test")  # env var + FROZEN lock enforced
    common = env["common"]
    sources = env["sources"]
    grid = env["grid"]
    lock_path = repo / common["paths"]["lock_file"]
    lock = verify_lock(lock_path)
    if lock["normalization_sha256"] != env["norm_checksum"]:
        raise RuntimeError("normalization does not match lock")
    if lock["split_logical_fingerprint"] != env["split_fingerprint"]:
        raise RuntimeError("split fingerprint does not match lock")

    device = torch.device(f"cuda:{gpu_index}" if torch.cuda.is_available()
                          else "cpu")
    test_cov = split_coverage_mask(sources, "test")
    # Frozen Issue #4 candidate registry: disagreement code 3 incl. the
    # IGNORE boundary buffer; only invalid-input pixels are dropped at
    # response aggregation via the variant validity mask.
    weak_labels, weak_comps = material_weak_labels(
        sources.weak_candidates,
        int(common["eval"]["small_patch_max_px"]))
    if len(weak_comps) != 91:  # Issue #4 material-component count
        raise RuntimeError(
            f"material WEAK-only components changed: {len(weak_comps)} != 91")

    results: list[dict[str, Any]] = []
    for entry in lock["runs"]:
        run_dir = repo / entry["run_dir"]
        out_path = run_dir / "test_metrics.json"
        if out_path.exists():
            raise RuntimeError(
                f"TEST already evaluated for {entry['run_id']}; "
                "second evaluation forbidden")
        prob, valid_grid, threshold = _predict(
            entry, run_dir, sources, grid, device, common)
        views = _views(entry, sources, grid)
        coverage = ~np.isnan(prob)
        p0 = np.nan_to_num(prob)
        metrics = {
            "run_id": entry["run_id"], "model": entry["model"],
            "variant": entry["variant"], "seed": entry["seed"],
            "threshold": threshold,
            "arbitrated_core": evaluate_view(
                p0, sources.silver,
                views["arbitrated_core"] & coverage, threshold),
            "silver_strict": evaluate_view(
                p0, sources.silver,
                views["silver_strict"] & coverage, threshold),
            "weak_candidate_response": component_responses(
                p0, weak_labels, weak_comps, threshold,
                test_cov & valid_grid),
        }
        is_neural = entry["model"] in {
            "unet", "deeplabv3plus", "segformer_b0"}
        if is_neural and entry["variant"] == "full":
            metrics["missing_modality_stress"] = _stress(
                entry, run_dir, sources, grid, device, common,
                views, test_cov)
        out_path.write_text(
            json.dumps(metrics, sort_keys=True, indent=2) + "\n",
            encoding="utf-8")
        results.append(metrics)
        print(f"TEST {entry['model']:15s} {entry['variant']:16s} "
              f"seed={entry['seed']} iou="
              f"{metrics['arbitrated_core']['iou']:.4f}")
    return results


def _views(entry: dict[str, Any], sources: Any, grid: Any) -> Any:
    if entry["model"] == "sai":
        finite = np.isfinite(sources.stack[SAI_BAND])
        return view_masks(finite, sources.silver, sources.weak,
                          sources.ignore, sources.weak_only)
    return grid_view_masks(sources, grid, str(entry["variant"]))


def _valid_grid(entry: dict[str, Any], sources: Any, grid: Any) -> Any:
    if entry["model"] == "sai":
        return np.isfinite(sources.stack[SAI_BAND])
    bands = VARIANT_BANDS[str(entry["variant"])]
    return np.all(grid.valid[bands], axis=0)


def _predict(
    entry: dict[str, Any], run_dir: Path, sources: Any, grid: Any,
    device: torch.device, common: dict[str, Any],
    drop: str | None = None,
) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any], float]:
    kind = entry["artifact_kind"]
    threshold = float(entry["val_threshold"])
    if kind == "spectral_rule":
        finite = np.isfinite(sources.stack[SAI_BAND])
        cov = split_coverage_mask(sources, "test")
        rule = json.loads((run_dir / "rule.json").read_text("utf-8"))
        prob = np.where(cov & finite,
                        apply_rule(sources.stack[SAI_BAND],
                                   float(rule["threshold"])), np.nan)
        return prob.astype(np.float32), finite, threshold
    if kind == "random_forest_joblib":
        from spartina.models.baselines.random_forest import rf_predict_proba
        blob = joblib.load(run_dir / "rf.joblib")
        bands = blob["bands"]
        cov = split_coverage_mask(sources, "test")
        valid = np.all(grid.valid[bands], axis=0)
        prob = rf_predict_proba(blob["rf"], grid.norm[bands], cov & valid)
        return prob, valid, threshold
    return _predict_neural(entry, run_dir, sources, grid, device, common,
                           drop)


def _predict_neural(
    entry: dict[str, Any], run_dir: Path, sources: Any, grid: Any,
    device: torch.device, common: dict[str, Any], drop: str | None,
) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any], float]:
    ckpt_path = run_dir / "best.pt"
    if _sha(ckpt_path) != entry["checkpoint_sha256"]:
        raise RuntimeError(f"checkpoint mismatch for {entry['run_id']}")
    ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    if ckpt["val_threshold"] != entry["val_threshold"]:
        raise RuntimeError(f"threshold mismatch for {entry['run_id']}")
    bands = ckpt["bands"]
    model, _ = MODEL_BUILDERS[str(entry["model"])](
        in_channels=len(bands), pretrained=True)
    model.load_state_dict(ckpt["model_state"], strict=True)
    model.to(device)
    prob = predict_mosaic(
        model, sources, grid, str(entry["variant"]), "test", device,
        int(common["geometry"]["patch_px"]), drop=drop)
    valid = np.all(grid.valid[bands], axis=0)
    return prob.astype(np.float32), valid, float(ckpt["val_threshold"])


def _stress(
    entry: dict[str, Any], run_dir: Path, sources: Any, grid: Any,
    device: torch.device, common: dict[str, Any], views: Any,
    test_cov: Any,
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for drop in ("indices", "sar", "sar_indices"):
        prob, _, threshold = _predict_neural(
            entry, run_dir, sources, grid, device, common, drop)
        coverage = ~np.isnan(prob)
        p0 = np.nan_to_num(prob)
        out[drop] = {
            "arbitrated_core": evaluate_view(
                p0, sources.silver,
                views["arbitrated_core"] & coverage, threshold),
            "silver_strict": evaluate_view(
                p0, sources.silver,
                views["silver_strict"] & coverage, threshold),
        }
    return out
