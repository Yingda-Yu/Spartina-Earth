"""Aggregate run manifests/metrics into Pilot-0 final tables."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

MODELS = ("sai", "random_forest", "unet", "deeplabv3plus", "segformer_b0")
MODEL_LABELS = {
    "sai": "SAI rule", "random_forest": "Random Forest",
    "unet": "U-Net", "deeplabv3plus": "DeepLabV3+",
    "segformer_b0": "SegFormer-B0"}
VARIANTS = ("optical", "optical_indices", "optical_sar", "full")


def _flatten_view(view: dict[str, Any], prefix: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    scalar_keys = ("threshold", "n_valid_pixels", "n_positive_pixels",
                   "iou", "precision", "recall", "f1", "auprc",
                   "bf1_30m", "bf1_60m", "pred_area_ha", "ref_area_ha",
                   "abs_area_error_ha", "rel_area_error",
                   "signed_area_bias", "brier", "ece")
    for k in scalar_keys:
        out[f"{prefix}_{k}"] = view.get(k)
    for tag in ("patch_025", "patch_050"):
        for k, v in (view.get(tag) or {}).items():
            out[f"{prefix}_{tag}_{k}"] = v
    return out


def collect(repo: Path, runs_root: Path) -> dict[str, pd.DataFrame]:
    metric_rows: list[dict[str, Any]] = []
    eff_rows: list[dict[str, Any]] = []
    weak_rows: list[dict[str, Any]] = []
    stress_rows: list[dict[str, Any]] = []
    for mf in sorted(runs_root.rglob("run_manifest.json")):
        man = json.loads(mf.read_text(encoding="utf-8"))
        if man.get("phase") != "official":
            continue
        base = {"run_id": man["run_id"], "model": man["model"],
                "variant": man["variant"], "seed": man["seed"],
                "status": man["status"]}
        eff = man.get("efficiency", {}) or {}
        eff_rows.append({
            **base,
            "params": eff.get("params"),
            "peak_vram_mib": eff.get("peak_vram_mib"),
            "train_wall_s": eff.get("train_wall_s"),
            "pixels_per_s": eff.get("train_pixels_per_s"),
            "windows_per_s": eff.get("train_windows_per_s"),
            "checkpoint_size_bytes": man.get("checkpoint_size_bytes"),
            "gpu_id": (man.get("gpu") or {}).get("id"),
            "gpu_model": (man.get("gpu") or {}).get("model"),
        })
        for split, fname in (("val", "val_metrics.json"),
                             ("test", "test_metrics.json")):
            fp = mf.parent / fname
            if not fp.exists():
                continue
            payload = json.loads(fp.read_text(encoding="utf-8"))
            row = dict(base)
            row["split"] = split
            for view in ("arbitrated_core", "silver_strict"):
                row.update(_flatten_view(payload[view], view))
            metric_rows.append(row)
            if split == "test":
                for w in payload.get("weak_candidate_response", []):
                    weak_rows.append({**base, **w})
                for drop, views in (payload.get(
                        "missing_modality_stress") or {}).items():
                    for view, bundle in views.items():
                        stress_rows.append({
                            **base, "drop": drop, "view": view,
                            **_flatten_view(bundle, "m")})
    return {
        "metrics": pd.DataFrame(metric_rows),
        "efficiency": pd.DataFrame(eff_rows),
        "weak": pd.DataFrame(weak_rows),
        "stress": pd.DataFrame(stress_rows),
    }


def write_outputs(tables: dict[str, pd.DataFrame], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    tables["metrics"].to_csv(out_dir / "pilot0_metrics.csv", index=False)
    tables["metrics"].to_parquet(
        out_dir / "pilot0_metrics.parquet", index=False)
    tables["efficiency"].to_csv(
        out_dir / "pilot0_efficiency.csv", index=False)
    tables["weak"].to_csv(
        out_dir / "pilot0_weak_candidate_response.csv", index=False)


def seed_summary_text(
    metrics: pd.DataFrame, view: str, col: str,
) -> pd.DataFrame:
    test = metrics[metrics["split"] == "test"]
    g = test.groupby(["model", "variant"])[f"{view}_{col}"]
    return g.agg(["mean", "std", "count"]).reset_index()
