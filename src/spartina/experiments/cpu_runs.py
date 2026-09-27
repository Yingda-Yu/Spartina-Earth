"""Orchestration for the deterministic SAI rule and Random Forest runs.

Both fit on unique TRAIN source pixels only and freeze their decision
on VAL arbitrated_core IoU; TEST is never accessed.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import joblib
import numpy as np

from spartina.data.dataset import grid_view_masks
from spartina.data.pilot0 import (
    VARIANT_BANDS,
    split_coverage_mask,
    train_unique_pixel_mask,
)
from spartina.evaluation.metrics import (
    THRESHOLD_GRID_DEFAULT,
    choose_threshold,
    evaluate_view,
)
from spartina.experiments.registry import (
    RunContext,
    append_registry_row,
    git_commit,
    git_dirty,
    sha256_file,
)
from spartina.models.baselines.random_forest import (
    fit_rf,
    rf_predict_proba,
    sample_train_pixels,
)
from spartina.models.baselines.spectral import (
    NDVI_BAND,
    SAI_BAND,
    apply_rule,
    fit_index_threshold,
)


def _common_manifest(ctx: RunContext, env: dict[str, Any]) -> None:
    ctx.manifest.update({
        "git_commit": git_commit(ctx.repo),
        "dirty_tree": git_dirty(ctx.repo),
        "source_stack_checksum": env["sources"].stack_checksum,
        "split_logical_fingerprint": env["split_fingerprint"],
        "normalization_sha256": env["norm_checksum"],
    })


def _val_bundle(
    prob: np.ndarray[Any, Any], sources: Any,
    views: dict[str, np.ndarray[Any, Any]], threshold: float,
) -> dict[str, Any]:
    coverage = ~np.isnan(prob)
    p0 = np.nan_to_num(prob)
    return {
        "arbitrated_core": evaluate_view(
            p0, sources.silver,
            views["arbitrated_core"] & coverage, threshold),
        "silver_strict": evaluate_view(
            p0, sources.silver,
            views["silver_strict"] & coverage, threshold),
    }


def run_spectral(ctx_env: dict[str, Any], repo: Path) -> dict[str, Any]:
    env = ctx_env
    common = env["common"]
    sources = env["sources"]
    ctx = RunContext(
        repo=repo, runs_root=repo / common["paths"]["runs_root"],
        registry_dir=repo / common["paths"]["registry_dir"],
        model="sai", variant="spectral_sai", seed=None,
        phase="official").initialize()
    _common_manifest(ctx, env)

    t0 = time.time()
    train_cov = train_unique_pixel_mask(sources)
    finite = np.isfinite(sources.stack[SAI_BAND])
    sai = sources.stack[SAI_BAND]
    ndvi = sources.stack[NDVI_BAND]
    train_domain = train_cov & finite
    sai_t, sai_iou = fit_index_threshold(sai, sources.silver, train_domain)
    nd_t, nd_iou = fit_index_threshold(ndvi, sources.silver,
                                       train_cov & np.isfinite(ndvi))
    rule = {"band": "SAI", "band_index": SAI_BAND, "threshold": sai_t,
            "train_core_iou": sai_iou,
            "ndvi_diagnostic": {"band_index": NDVI_BAND,
                                "threshold": nd_t,
                                "train_core_iou": nd_iou}}
    cfg_hash = hashlib.sha256(json.dumps(
        {"model": "sai_spectral", "grid": common.get("threshold"),
         "index": "SAI"}, sort_keys=True).encode("utf-8")).hexdigest()
    ctx.manifest["config_sha256"] = cfg_hash
    rule_path = ctx.write_json("rule.json", rule)
    rule_sha = sha256_file(rule_path)

    val_cov = split_coverage_mask(sources, "val")
    prob = np.where(val_cov & finite, apply_rule(sai, sai_t), np.nan)
    from spartina.data.dataset import view_masks
    views = view_masks(np.isfinite(sai), sources.silver, sources.weak,
                       sources.ignore, sources.weak_only)
    val_metrics = _val_bundle(prob, sources, views, 0.5)
    ctx.write_json("val_metrics.json", val_metrics)
    ctx.manifest.update({
        "artifact_kind": "spectral_rule",
        "artifact": "rule.json",
        "checkpoint_sha256": rule_sha,
        "checkpoint_size_bytes": rule_path.stat().st_size,
        "training": {"best_epoch": None},
        "val_threshold": 0.5,
        "val_core_iou": val_metrics["arbitrated_core"]["iou"],
        "sai_train_threshold": sai_t,
        "sai_train_iou": sai_iou,
        "ndvi_diagnostic_threshold": nd_t,
        "ndvi_diagnostic_train_iou": nd_iou,
        "efficiency": {"train_wall_s": time.time() - t0},
    })
    ctx.finalize("COMPLETED")
    append_registry_row(repo, ctx.registry_dir, ctx.manifest)
    return ctx.manifest


def run_random_forest(
    ctx_env: dict[str, Any], repo: Path, variant: str, seed: int,
) -> dict[str, Any]:
    env = ctx_env
    common = env["common"]
    sources = env["sources"]
    grid = env["grid"]
    rfcfg = common["rf"]
    bands = VARIANT_BANDS[variant]
    ctx = RunContext(
        repo=repo, runs_root=repo / common["paths"]["runs_root"],
        registry_dir=repo / common["paths"]["registry_dir"],
        model="random_forest", variant=variant, seed=seed,
        phase="official").initialize()
    _common_manifest(ctx, env)
    cfg_hash = hashlib.sha256(json.dumps(
        {"model": "random_forest", "variant": variant, "rf": rfcfg},
        sort_keys=True).encode("utf-8")).hexdigest()
    ctx.manifest["config_sha256"] = cfg_hash

    features = grid.norm[bands]
    views = grid_view_masks(sources, grid, variant)
    train_cov = train_unique_pixel_mask(sources)
    train_domain = train_cov & views["arbitrated_core"]
    cap = int(rfcfg["max_train_pixels"])
    t0 = time.time()
    X, yy = sample_train_pixels(
        features, sources.silver, train_domain, cap, seed)
    rf = fit_rf(X, yy, seed, rfcfg)
    fit_s = time.time() - t0
    art = ctx.path("rf.joblib")
    joblib.dump({"rf": rf, "bands": bands, "variant": variant,
                 "seed": seed, "n_train_pixels": int(X.shape[0])}, art)
    art_sha = sha256_file(art)

    val_cov = split_coverage_mask(sources, "val")
    valid_inputs = np.all(grid.valid[bands], axis=0)
    prob = rf_predict_proba(rf, features, val_cov & valid_inputs)
    core_val = views["arbitrated_core"] & val_cov
    threshold, val_iou = choose_threshold(
        np.nan_to_num(prob), sources.silver, core_val,
        np.array(THRESHOLD_GRID_DEFAULT))
    val_metrics = _val_bundle(prob, sources, views, threshold)
    ctx.write_json("val_metrics.json", val_metrics)
    ctx.manifest.update({
        "artifact_kind": "random_forest_joblib",
        "artifact": "rf.joblib",
        "checkpoint_sha256": art_sha,
        "checkpoint_size_bytes": art.stat().st_size,
        "training": {"best_epoch": None},
        "val_threshold": threshold,
        "val_core_iou": val_iou,
        "n_train_pixels": int(X.shape[0]),
        "efficiency": {"train_wall_s": fit_s},
    })
    ctx.finalize("COMPLETED")
    append_registry_row(repo, ctx.registry_dir, ctx.manifest)
    return ctx.manifest
