#!/usr/bin/env python3
"""C4 cross-source 2020 agreement evaluation (frozen C2 model reuse).

No training and no threshold tuning: each frozen C2 run's VAL-selected
threshold is applied unchanged to 2020 Sentinel-2 predictions evaluated

* against GEODATA_2020 on the two positive TEST cells it maps, and
* against CM-SSM_2020 on the 2020 witness pair + positive test, under
  EXTERNAL_REFERENCE_ONLY rights (never trained/tuned on).

All numbers are CROSS-SOURCE AGREEMENT, not accuracy; CM-SSM is never
used for model selection or early stopping.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

from spartina.benchmark.silver.data import (  # noqa: E402
    NormStats,
    apply_norm,
    load_cell_arrays,
    target_masks,
)
from spartina.benchmark.silver.runner import (  # noqa: E402
    BENCH_DIR,
    MATRIX_PATH,
    SPLITS_PATH,
    block_bootstrap_ci,
    mixed_agreement,
    pooled_view,
    predict_neural,
    predict_rf,
    rf_feature_volume,
    sha256_file,
)
from spartina.evaluation.metrics import evaluate_view  # noqa: E402

MODELS = ("rf_pixel", "unet", "deeplabv3plus", "segformer_b0")
SEEDS = (17, 42, 2026)


def _norm(summary: dict[str, Any]) -> NormStats:
    n = summary["normalization"]
    return NormStats(
        np.array(n["p_low"], dtype=np.float32),
        np.array(n["p_high"], dtype=np.float32),
        np.array(n["mean"], dtype=np.float32),
        np.array(n["std"], dtype=np.float32))


def _load_predictor(
    summary: dict[str, Any], gpu_index: int,
) -> tuple[Any, torch.device]:
    model = summary["model"]
    run_dir = REPO_ROOT / summary["artifacts"]["run_dir"]
    norm = _norm(summary)
    if model == "rf_pixel":
        import joblib
        rf = joblib.load(run_dir / "rf.joblib")

        def predict(arrays: Any) -> np.ndarray[Any, Any]:
            volume = rf_feature_volume(
                arrays.features, arrays.valid, norm, arrays.band_names)
            return predict_rf(rf, volume, arrays.valid)

        return predict, torch.device("cpu")
    name = model
    if name == "unet":
        from spartina.models.baselines.unet import build_unet
        net, _ = build_unet(4, pretrained=False)
    elif name == "deeplabv3plus":
        from spartina.models.baselines.deeplabv3plus import build_deeplabv3plus
        net, _ = build_deeplabv3plus(4, pretrained=False)
    else:
        from spartina.models.baselines.segformer_b0 import build_segformer_b0
        net, _ = build_segformer_b0(4, pretrained=True)
    device = torch.device(
        f"cuda:{gpu_index}" if torch.cuda.is_available() else "cpu")
    ckpt = torch.load(run_dir / "best.pt", map_location="cpu",
                      weights_only=False)
    net.load_state_dict(ckpt["model_state"])
    net = net.to(device).eval()

    def predict_nn(arrays: Any) -> np.ndarray[Any, Any]:
        x = apply_norm(arrays.features, arrays.valid, norm)
        return predict_neural(net, x, arrays.valid, device)

    return predict_nn, device


def _agreement_set(
    predict: Any, cell_year_label: list[tuple[str, str, int, str, bool]],
    threshold: float,
) -> dict[str, Any]:
    bin_views = []
    mix_views = []
    per_cell = []
    for cell_id, product_id, year, label_key, positive in cell_year_label:
        arrays = load_cell_arrays(cell_id, product_id, label_key)
        family = "GEODATA" if label_key.startswith("GEODATA") else "CM-SSM"
        masks = target_masks(arrays.fraction, arrays.occ_class, family, year)
        prob = predict(arrays)
        bv = masks["binary_valid"]
        row = evaluate_view(np.nan_to_num(prob), masks["y"], bv, threshold)
        row.update({"cell_id": cell_id, "label_source": label_key,
                    "positive_cell": positive,
                    "n_positive_pixels": int((masks["y"] & bv).sum()),
                    "n_unknown_pixels": int(masks["unknown"].sum()),
                    "n_mixed_pixels": int(masks["mixed"].sum())})
        per_cell.append(row)
        bin_views.append((np.nan_to_num(prob), masks["y"], bv))
        mix_views.append((prob, arrays.fraction, masks["mixed"],
                          arrays.valid))
    out: dict[str, Any] = {
        "n_cells": len(per_cell),
        "pooled": pooled_view(bin_views, threshold),
        "per_cell": per_cell,
        "block_bootstrap": block_bootstrap_ci(bin_views, threshold),
        "mixed_agreement": mixed_agreement(mix_views)}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gpu", type=int, default=0)
    ap.add_argument("--model", choices=[*MODELS, "all"], default="all")
    ap.add_argument("--seed", type=int, choices=[*SEEDS, -1], default=-1)
    args = ap.parse_args()
    splits = json.loads(SPLITS_PATH.read_text())["splits"]["SPLIT-S2"]
    pos_test = splits["positive_by_role"]["test"]
    witness = splits["witness_2020"]
    cmssm_cells = sorted(set(witness) | set(pos_test))
    geodata_cells = list(pos_test)
    province = splits["province_of"]

    models = list(MODELS) if args.model == "all" else [args.model]
    seeds = list(SEEDS) if args.seed == -1 else [args.seed]
    out_dir = BENCH_DIR / "results" / "C4"
    out_dir.mkdir(parents=True, exist_ok=True)
    for model in models:
        for seed in seeds:
            c2_path = (BENCH_DIR / "results" / "C2"
                       / f"{model}_s2_seed{seed}.json")
            summary = json.loads(c2_path.read_text())
            threshold = float(summary["training"]["val_threshold"])
            predict, device = _load_predictor(summary, args.gpu)

            def pid(cell: str) -> str:
                return f"NP19_{cell[7:]}_S2_2020"

            geodata = _agreement_set(
                predict,
                [(c, pid(c), 2020, "GEODATA_2020", True)
                 for c in geodata_cells], threshold)
            geodata["language"] = "cross-source agreement"
            geodata["agreement_is_not_accuracy"] = True
            geodata["rights"] = "SILVER_TRAINING_ELIGIBLE_INTERNAL_RESEARCH_ONLY"
            cmssm = _agreement_set(
                predict,
                [(c, pid(c), 2020, "CM-SSM_2020", c in pos_test)
                 for c in cmssm_cells], threshold)
            cmssm["language"] = (
                "external-reference agreement; CM-SSM never trained or tuned")
            cmssm["agreement_is_not_accuracy"] = True
            cmssm["rights"] = (
                "EXTERNAL_REFERENCE_ONLY_SOURCE_LICENSE_CONFLICT")
            cmssm["witness_2020_cells"] = witness
            cmssm["positive_test_cells"] = pos_test
            doc = {
                "protocol_name": "SPARTINASHIFT_SILVER_V0_1_PROTOCOL",
                "task": "C4", "model": model, "seed": seed,
                "status": "COMPLETED",
                "created_utc": time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "reuses": {
                    "task": "C2", "arm": "s2",
                    "c2_summary": str(c2_path.relative_to(REPO_ROOT)),
                    "c2_run_dir": summary["artifacts"]["run_dir"],
                    "c2_checkpoint_sha256":
                        summary["artifacts"]["checkpoint_sha256"],
                    "frozen_val_threshold": threshold},
                "no_new_training": True,
                "no_tuning_on_these_labels": True,
                "agreement_is_not_accuracy": True,
                "province_of": {c: province[c] for c in
                                sorted(set(geodata_cells + cmssm_cells))},
                "protocol_checksum": summary["protocol_checksum"],
                "splits_sha256": sha256_file(SPLITS_PATH),
                "support_matrix_sha256": sha256_file(MATRIX_PATH),
                "agreement": {"GEODATA_2020": geodata,
                              "CM_SSM_2020": cmssm}}
            out = out_dir / f"{model}_s2_seed{seed}.json"
            out.write_text(json.dumps(doc, sort_keys=True, indent=2,
                                      ensure_ascii=False) + "\n")
            print(f"C4 {model} seed {seed}: GEODATA IoU "
                  f"{geodata['pooled']['iou']} | CM-SSM IoU "
                  f"{cmssm['pooled']['iou']}")
            del predict
            if device.type == "cuda":
                torch.cuda.empty_cache()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
