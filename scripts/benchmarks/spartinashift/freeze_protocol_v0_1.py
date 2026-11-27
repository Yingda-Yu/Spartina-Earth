#!/usr/bin/env python3
"""Issue #20 Stage 1, Phase B -- freeze SPARTINASHIFT_SILVER_V0_1_PROTOCOL.

Runs BEFORE any model exists. Consumes the Phase A support matrix and
emits the frozen protocol + cell-role split manifests:

  benchmarks/spartinashift/silver_v0_1/SPARTINASHIFT_SILVER_V0_1_PROTOCOL.json
  benchmarks/spartinashift/silver_v0_1/splits_v0_1.json

The Phase A inventory revealed the true SILVER-positive sparsity of the
20-cell pilot: the CMSA positive core shared by 2020/2021 is 5 cells,
and GEODATA 2015/2020 positives are 3 cells per year (2 in both). Per
the predeclared binary-split minimums (>=2 positive train, >=1 positive
val, >=2 positive test cells in every task year), C1 and every C3
province holdout are frozen INSUFFICIENT_SUPPORT; C2/C4/C5 run on
SPLIT-S2. Nothing here is chosen by inspecting model performance.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

from spartina.benchmark.silver import support as sup  # noqa: E402
from spartina.benchmark.silver.protocol import (  # noqa: E402
    BATCH_SIZE,
    BLOCK_BOOTSTRAP_M,
    BLOCK_BOOTSTRAP_REPS,
    CI_LEVEL,
    EARLY_STOP_PATIENCE,
    FRAC_MIXED_LO,
    FRAC_POSITIVE,
    GAP_NEAR_DATE_DAYS,
    GAP_SEASON_MATCH_DAYS,
    L8_BANDS,
    LEAKAGE_BUFFER_M,
    MODEL_CONFIGS,
    P_NORM_HIGH,
    P_NORM_LOW,
    PATCH_PX,
    PATCH_RES_M,
    PATCH_STRIDE_INFER,
    PATCH_STRIDE_TRAIN,
    POS_WEIGHT_CAP,
    POSITIVE_PATCH_FRACTION,
    PROTOCOL_NAME,
    PROTOCOL_VERSION,
    S1_BANDS,
    S2_BANDS,
    SEEDS,
    TRAIN_PATCHES_PER_CELL,
    UNET_DEEPLAB_MAX_EPOCHS,
    WARMUP_EPOCHS,
    SplitRules,
    assign_roles,
    protocol_checksum,
)

MATRIX_CSV = (
    REPO_ROOT / "benchmarks/spartinashift/silver_v0_1"
    / "support_matrix_v0_1.csv")
MATRIX_SUMMARY_JSON = (
    REPO_ROOT / "benchmarks/spartinashift/silver_v0_1"
    / "support_matrix_v0_1_summary.json")
PANEL_CSV = REPO_ROOT / "datasets/manifests/national_first_pixel_panel_v1.csv"
OUT_DIR = REPO_ROOT / "benchmarks/spartinashift/silver_v0_1"

MIN_POS_TRAIN = 2
MIN_POS_VAL = 1
MIN_POS_TEST = 2
REGION_TOTAL_HOLDOUT_MIN = 4
REGION_TOTAL_REMAINING_MIN = 8
REGION_POS_HOLDOUT_MIN = 2


def _git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, check=True,
            capture_output=True, text=True)
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNKNOWN"


def _node(summary: dict[str, Any], path: list[str]) -> Any:
    node: Any = summary
    for key in path:
        node = node[key]
    return node


def _positive_cells(records: list[dict[str, Any]], key: str) -> set[str]:
    return {r["cell_id"] for r in records
            if r["label_source_key"] == key
            and r["label_support_m"] == 30
            and int(r["n_pure_positive_px"]) > 0}


def _c1_verdict(
    records: list[dict[str, Any]], c1_cells: list[str],
) -> dict[str, Any]:
    p15 = {c for c in _positive_cells(records, "GEODATA_2015")
           if c in set(c1_cells)}
    p20 = {c for c in _positive_cells(records, "GEODATA_2020")
           if c in set(c1_cells)}
    both = p15 & p20
    verdict = (
        "INSUFFICIENT_SUPPORT"
        if not (len(p15) >= MIN_POS_TRAIN + MIN_POS_VAL + MIN_POS_TEST
                and len(p20) >= MIN_POS_TRAIN + MIN_POS_VAL
                + MIN_POS_TEST)
        else "SUPPORTED")
    return {
        "verdict": verdict,
        "eo_eligible_cells_both_years": len(c1_cells),
        "geodata_pure_positive_cells_2015": sorted(p15),
        "geodata_pure_positive_cells_2020": sorted(p20),
        "positive_cells_both_years": sorted(both),
        "binary_split_minimum": {
            "n_positive_train": MIN_POS_TRAIN, "n_positive_val": MIN_POS_VAL,
            "n_positive_test": MIN_POS_TEST,
            "required_per_year": (
                MIN_POS_TRAIN + MIN_POS_VAL + MIN_POS_TEST)},
        "reason": (
            "GEODATA is a sparse product within these W10 cells: pure-"
            "positive pixels (fraction >= 0.90) occur in 3 cells in 2015 "
            "and 3 cells in 2020 (2 in both); no spatial train/val/test "
            "binary split meets the frozen minimums. No C1 training is "
            "run; the EO/label support ledger is retained for evidence."),
    }


def _c3_ledger(
    c2_cells: list[str], c1_cells: list[str],
    c2_pos: set[str], c1_pos15: set[str], c1_pos20: set[str],
    province_of: dict[str, str],
) -> dict[str, Any]:
    regions: dict[str, Any] = {}
    all_provs = sorted({province_of[c] for c in c2_cells}
                       | {province_of[c] for c in c1_cells})
    for prov in all_provs:
        c2_hold = [c for c in c2_cells if province_of[c] == prov]
        c2_hold_pos = [c for c in c2_hold if c in c2_pos]
        c2_out_pos = len(c2_pos) - len(c2_hold_pos)
        c1_hold = [c for c in c1_cells if province_of[c] == prov]
        c1_hold_pos = sorted(
            set(c for c in c1_hold if c in c1_pos15)
            & set(c for c in c1_hold if c in c1_pos20))
        reasons: list[str] = []
        if len(c2_hold) < REGION_TOTAL_HOLDOUT_MIN:
            reasons.append(
                f"C2 total held cells {len(c2_hold)} < "
                f"{REGION_TOTAL_HOLDOUT_MIN}")
        if len(c2_cells) - len(c2_hold) < REGION_TOTAL_REMAINING_MIN:
            reasons.append("C2 remaining cells < "
                           f"{REGION_TOTAL_REMAINING_MIN}")
        if len(c2_hold_pos) < REGION_POS_HOLDOUT_MIN:
            reasons.append(
                f"C2 positive held cells {len(c2_hold_pos)} < "
                f"{REGION_POS_HOLDOUT_MIN}")
        if c2_out_pos < MIN_POS_TRAIN + MIN_POS_VAL:
            reasons.append(
                f"C2 positive cells outside holdout {c2_out_pos} < "
                f"{MIN_POS_TRAIN + MIN_POS_VAL}")
        if len(c1_hold_pos) < REGION_POS_HOLDOUT_MIN:
            reasons.append(
                f"C1 both-year positive held cells "
                f"{len(c1_hold_pos)} < {REGION_POS_HOLDOUT_MIN}")
        regions[f"INSUFFICIENT_SUPPORT_FOR_REGION_{prov.upper()}"] = {
            "c2_total_cells": len(c2_hold),
            "c2_positive_cells": len(c2_hold_pos),
            "c2_positive_cells_outside": c2_out_pos,
            "c1_total_cells": len(c1_hold),
            "c1_both_year_positive_cells": len(c1_hold_pos),
            "verdict": "INSUFFICIENT_SUPPORT",
            "reasons": reasons,
        }
    return {
        "verdict": "INSUFFICIENT_SUPPORT_ALL_REGIONS",
        "rules": {
            "min_total_holdout_cells": REGION_TOTAL_HOLDOUT_MIN,
            "min_total_remaining_cells": REGION_TOTAL_REMAINING_MIN,
            "min_positive_holdout_cells": REGION_POS_HOLDOUT_MIN,
            "min_positive_outside": MIN_POS_TRAIN + MIN_POS_VAL},
        "regions": regions,
    }


def _split_payload(split: dict[str, Any]) -> dict[str, Any]:
    keep = ("split_id", "train", "val", "test", "positive_cells",
            "positive_by_role", "witness_2020", "province_of",
            "buffer_check", "rules")
    return {k: split[k] for k in keep}


def _sections() -> dict[str, Any]:
    return {
        "1_eligible_sets": (
            "C1 GEODATA 2015->2020 / Landsat 8: 14 EO-eligible cells but "
            "only 3 GEODATA pure-positive cells per year (2 in both) -> "
            "INSUFFICIENT_SUPPORT, no split, no training. "
            "C2 CMSA 2020->2021 / Sentinel-2: 18 EO-eligible cells, of "
            "which 5 carry CMSA pure-positive pixels in BOTH years "
            "(R00236 Guangdong, R00311/R00334 Zhejiang, R00349 Jiangsu, "
            "R00413 Shandong) -> SUPPORTED on SPLIT-S2. "
            "C4 reuses C2 trained models for cross-source agreement; "
            "C5 restricts SPLIT-S2 roles to the 17 cells with a landed "
            "S1-A 2020 product (all 5 positive cells qualify). "
            "C3: all provinces INSUFFICIENT, see task verdicts. "
            "Missing/zero-support cells are reported, never substituted."),
        "2_cell_grouping": (
            "The W10 Albers 10 km cell is the only split unit. Patches, "
            "scenes, dates, modalities and years of one cell inherit the "
            "cell's single role; patches are never split across roles."),
        "3_region_grouping": (
            "Province (frozen region_province) is the cross-region unit. "
            "The CMSA positive core covers 4 provinces with at most 2 "
            "positive cells each (Zhejiang), and total C2 cells per "
            "province are below the >=4/remaining >=8 rule except "
            "Fujian (4, 0 positive) and Shandong (4, 1 positive); every "
            "province is frozen "
            "INSUFFICIENT_SUPPORT_FOR_REGION_<name> for C3, no run."),
        "4_train_val_test": (
            "SPLIT-S2 (18 cells): 11 train (2 positive + 9 background), "
            "3 val (1 positive + 2 background), 4 test (2 positive + 2 "
            "background); 2 witness cells (1 positive, 1 background from "
            "a different province). Roles are the first admissible "
            "combination in the deterministic SHA-256 scan; exact lists "
            "in splits_v0_1.json. No C1 split exists."),
        "5_leakage_buffer": (
            f"Cross-role cell AABBs in China Albers metres must be >= "
            f"{LEAKAGE_BUFFER_M:g} m apart, verified with "
            "spartina.evaluation.splits.find_cross_split_overlaps; "
            "temporal grouping holds because each cell has one role. "
            "Min cross-role gap and zero-violation requirement are "
            "recorded per split."),
        "6_seeds": {
            "values": list(SEEDS),
            "scope": (
                "weight init, patch order, RF subsampling and geometric "
                "augmentation draws. The cell split is frozen ONCE "
                "(deterministic SHA-256 scan) and is never reseeded.")},
        "7_normalization": {
            "percentile_low": P_NORM_LOW,
            "percentile_high": P_NORM_HIGH,
            "rule": (
                "per-band p005/p995 clip bounds and mean/std from VALID "
                "pixels of TRAIN-role cells ONLY, separately per arm "
                "(S2, S2+S1); val/test/witness never contribute; "
                "post-clip NaN/non-finite -> 0.0; statistics persisted "
                "with every run")},
        "8_patch_extraction": {
            "patch_px": PATCH_PX,
            "patch_resolution_m": PATCH_RES_M,
            "patch_ground_m": PATCH_PX * PATCH_RES_M,
            "train_stride_px": PATCH_STRIDE_TRAIN,
            "inference_stride_px": PATCH_STRIDE_INFER,
            "patches_per_train_cell_per_epoch": TRAIN_PATCHES_PER_CELL,
            "positive_patch_fraction": POSITIVE_PATCH_FRACTION,
            "rule": (
                "patches drawn only AFTER cell roles are frozen; half "
                "the training patches contain >=1 SOURCE_MAPPED_POSITIVE "
                "pixel, half are random valid windows; deterministic "
                "6-way flips/rotations per seed; full-cell tiled "
                "inference on the 30 m grid; padded border predictions "
                "ignored; no 30 m->10 m upsampling anywhere"),
            "10m_to_30m": (
                "native 10 m S1/S2 EO is averaged (rasterio average "
                "resampling) to the 30 m label grid; an aggregated "
                "30 m pixel is valid only when >= 5 of 9 constituent "
                "10 m pixels are valid, else NaN, applied per band")},
        "9_mixed_unknown_handling": {
            "positive_threshold_fraction": FRAC_POSITIVE,
            "mixed_lower_fraction_geodata": FRAC_MIXED_LO,
            "terms": {
                "SOURCE_MAPPED_POSITIVE": (
                    "label fraction >= 0.90 (pure positive)"),
                "SOURCE_BACKGROUND_WEAK": (
                    "valid EO pixels with mapped fraction 0 outside "
                    "gridcode-0/outside-source-window regions; GEODATA "
                    "in-window mapped background"),
                "MIXED": (
                    "0.10 < fraction < 0.90 (GEODATA) or 0 < fraction < "
                    "0.90 (CMSA/CM-SSM); excluded from binary training "
                    "and primary binary metrics; reported separately and "
                    "used by the continuous fraction agreement view"),
                "UNKNOWN_IGNORE": (
                    "NaN/outside-source-window, CMSA gridcode 0 "
                    "(UNKNOWN_GRIDCODE_ZERO_TODO_VERIFY), invalid EO; "
                    "ignored in every loss and metric")},
            "note": (
                "SILVER background is never a verified ecological "
                "negative; source-background agreement is never reported "
                "as ecological specificity")},
        "10_model_selection_data": (
            "All hyperparameters are fixed here (no open-ended HPO). "
            f"Pos-weight derives from TRAIN valid pixels only (cap "
            f"{POS_WEIGHT_CAP:g}). Decision threshold: VALIDATION only "
            "(grid 0.05-0.95 step 0.01, max validation IoU, ties toward "
            "0.5); threshold 0.5 also reported. TEST and witness never "
            "influence sampling, normalization, class weighting, "
            "thresholds, early stopping, architecture or source choice."),
        "11_early_stopping": {
            "monitor": "validation IoU",
            "patience_epochs": EARLY_STOP_PATIENCE,
            "schedule": (
                f"AdamW; cosine LR; {WARMUP_EPOCHS} warm-up epochs; "
                f"batch {BATCH_SIZE}; AMP; max epochs per model in "
                "model_configs; early stopping reads validation only")},
        "12_held_out_eval_sets": (
            "C2 test cells evaluated after the run is frozen: 2020 "
            "(reference) and 2021 (cross-year shift). Positive and "
            "background-only test cells are reported as separate strata; "
            "patch counts AND independent held-out CELL counts are both "
            "reported. C4 adds cross-source agreement rows on the same "
            "cells. C5 reports paired-arm differences on identical "
            "cells/patches/seeds."),
        "13_witness_2020": (
            "Two named witness_2020 cells (splits_v0_1.json): one "
            "CMSA-positive test cell and one background-only test cell "
            "from another province; excluded from every selection/tuning "
            "path. CM-SSM is evaluated on witness/TEST cells as external "
            "reference only and is never trained, validated, "
            "thresholded or tuned against."),
        "14_modality_pairing": {
            "rule": (
                f"season-matched S2/S1 acquisitions within "
                f"{GAP_SEASON_MATCH_DAYS} days in the autumn DOY "
                "260-320 window; per-cell date gaps are ledgered (Phase "
                "A) and carried in run metadata; observations are NEVER "
                "described as simultaneous"),
            "near_date_sensitivity": (
                f"the <= {GAP_NEAR_DATE_DAYS}-day subset among the 17 "
                "C5 cells (5 cells) is descriptive-only and marked "
                "INSUFFICIENT_SUPPORT for its own split"),
            "arms": (
                "optical = S2 B2/B3/B4/B8 (4 ch); optical_sar = "
                "S2 + VV/VH (6 ch); identical cells, patch geometry, "
                "seeds and compute budget; independent train-only "
                "normalization per arm")},
        "15_metrics": [
            "IoU", "Dice/F1", "precision", "recall",
            "area_bias (predicted/source mapped km2)",
            "patch_precision_recall (8-connected, Hungarian, IoS>=0.5)",
            "boundary_F1 at tau = 1, 2, 4 px",
            "calibration: ECE(15 bins), Brier score",
            "positive-stratum vs background-only-cell stratum; "
            "pure-positive vs MIXED reported separately",
            "continuous fraction agreement (probability vs source "
            "fraction on non-unknown pixels)",
            "source-background agreement (never ecological specificity)",
            "all cross-source numbers are AGREEMENT/reproduction, never "
            "accuracy; GOLD = 0"],
        "16_uncertainty": {
            "primary": (
                "per-cell metric values on independent held-out cells; "
                "with only 2 positive test cells no inferential cell-"
                "level interval is claimed: individual cell values and "
                "their range are reported"),
            "secondary_descriptive": (
                f"{BLOCK_BOOTSTRAP_M} m spatial block resampling "
                f"({BLOCK_BOOTSTRAP_REPS} replicates, "
                f"{CI_LEVEL:.0%} percentile) pooled over positive held-"
                "out cells, explicitly labelled descriptive; pixel "
                "bootstrap is forbidden"),
            "reporting": (
                "mean across seeds 17/42/2026 with all per-seed values")},
        "17_compute_budget": {
            "gpus": "at most 3x RTX 3090; nvidia-smi before each launch",
            "models": list(MODEL_CONFIGS),
            "seeds": list(SEEDS),
            "max_epochs": {
                "unet": UNET_DEEPLAB_MAX_EPOCHS,
                "deeplabv3plus": UNET_DEEPLAB_MAX_EPOCHS,
                "segformer_b0": 30},
            "rf": "CPU; pixel cap per train cell persisted",
            "no_hpo": "fixed configs; no architecture search"},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    matrix = pd.read_csv(MATRIX_CSV)
    summary = json.loads(MATRIX_SUMMARY_JSON.read_text())
    panel = pd.read_csv(PANEL_CSV)
    province_of = dict(zip(panel.cell_id, panel.region_province, strict=True))
    records = matrix.to_dict("records")

    c1_cells = [str(c) for c in _node(summary, [
        "tasks", "C1_cross_year_geodata_l8",
        "eligible_cells_both_years"])]
    c2_cells = [str(c) for c in _node(summary, [
        "tasks", "C2_cross_year_cmsa_s2",
        "eligible_cells_both_years"])]
    c5_cells = set(str(c) for c in _node(summary, [
        "tasks", "C5_modality_ablation_2020", "eligible_cells"]))

    c1_verdict = _c1_verdict(records, c1_cells)
    cmsa_core = set.intersection(
        _positive_cells(records, "CMSA_2020"),
        _positive_cells(records, "CMSA_2021")) & set(c2_cells)
    c1_pos15 = {c for c in _positive_cells(records, "GEODATA_2015")
                if c in set(c1_cells)}
    c1_pos20 = {c for c in _positive_cells(records, "GEODATA_2020")
                if c in set(c1_cells)}
    c3 = _c3_ledger(
        c2_cells, c1_cells, cmsa_core, c1_pos15, c1_pos20, province_of)

    split_s2 = assign_roles(
        "SPLIT-S2", c2_cells, province_of, records,
        SplitRules(
            n_test=4, n_val=3,
            positive_source_keys=("CMSA_2020", "CMSA_2021"),
            n_positive_train=MIN_POS_TRAIN, n_positive_val=MIN_POS_VAL,
            n_positive_test=MIN_POS_TEST, positive_test_min_provinces=2,
            positive_test_require_north_south=True,
            min_val_provinces=2, n_witness=2))

    excluded_c5 = sorted(set(c2_cells) - c5_cells)
    tasks = {
        "C1_cross_year_geodata_l8": {
            "verdict": c1_verdict["verdict"],
            "detail": c1_verdict,
            "eo_sensor": "landsat8", "bands": list(L8_BANDS),
            "runs_planned": 0},
        "C2_cross_year_cmsa_s2": {
            "verdict": "SUPPORTED", "split": "SPLIT-S2",
            "eo_sensor": "sentinel2", "bands": list(S2_BANDS),
            "train_year": 2020, "eval_years": [2020, 2021],
            "train_label": "CMSA_2020",
            "runs_planned": 4 * len(SEEDS)},
        "C3_cross_region": c3,
        "C4_cross_source_2020": {
            "verdict": "SUPPORTED",
            "reuses_runs_from": "C2_cross_year_cmsa_s2",
            "split": "SPLIT-S2",
            "agreement_evaluations": [
                {"label": "GEODATA_2020",
                 "cells": "positive test cells where GEODATA maps",
                 "language": "cross-source agreement"},
                {"label": "CM-SSM_2020", "support_m": 30,
                 "cells": "witness_2020 (primary) and positive test",
                 "rights": sup.RIGHTS_CMSSM,
                 "language": "external-reference agreement; never tuned"}],
            "no_new_training": True,
            "runs_planned": 0},
        "C5_modality_ablation": {
            "verdict": "SUPPORTED",
            "optical_arm": {
                "reuses_runs_from": "C2_cross_year_cmsa_s2",
                "bands": list(S2_BANDS)},
            "optical_sar_arm": {
                "split": "SPLIT-S2", "eligible_cells": sorted(c5_cells),
                "excluded_cells_no_s1a": excluded_c5,
                "bands": list(S2_BANDS) + list(S1_BANDS),
                "runs_planned": 4 * len(SEEDS)},
            "identity_requirements": (
                "identical cell roles, patch geometry, seeds, budget; "
                "per-arm train-only normalization")},
    }

    splits_out = {"SPLIT-S2": _split_payload(split_s2)}
    protocol: dict[str, Any] = {
        "protocol_name": PROTOCOL_NAME,
        "protocol_version": PROTOCOL_VERSION,
        "issue": 20,
        "stage": "STAGE_1",
        "status": "FROZEN_PRE_TRAINING",
        "frozen_utc": datetime.now(UTC).isoformat(),
        "git_commit": _git_commit(),
        "gold_label_cells": 0,
        "phase_a_inputs": {
            "support_matrix_csv": str(MATRIX_CSV.relative_to(REPO_ROOT)),
            "support_matrix_sha256": hashlib.sha256(
                MATRIX_CSV.read_bytes()).hexdigest(),
            "support_matrix_summary": str(
                MATRIX_SUMMARY_JSON.relative_to(REPO_ROOT))},
        "rights_policy": {
            "GEODATA": sup.RIGHTS_GEODATA,
            "CMSA": sup.RIGHTS_CMSA,
            "CM-SSM": sup.RIGHTS_CMSSM,
            "gold": 0,
            "agreement_is_not_accuracy": True,
            "cmssm_never_trained_or_tuned": True},
        "splits": splits_out,
        "tasks": tasks,
        "model_configs": MODEL_CONFIGS,
        "protocol_items_1_to_17": _sections(),
    }
    protocol["checksum"] = protocol_checksum(protocol)

    splits_doc = {
        "protocol_name": PROTOCOL_NAME,
        "protocol_version": PROTOCOL_VERSION,
        "status": "FROZEN_PRE_TRAINING",
        "frozen_utc": protocol["frozen_utc"],
        "git_commit": protocol["git_commit"],
        "protocol_checksum": protocol["checksum"],
        "splits": splits_out,
    }
    proto_path = out_dir / "SPARTINASHIFT_SILVER_V0_1_PROTOCOL.json"
    splits_path = out_dir / "splits_v0_1.json"
    proto_path.write_text(json.dumps(protocol, indent=2) + "\n")
    splits_path.write_text(json.dumps(splits_doc, indent=2) + "\n")

    p = split_s2
    print(
        f"SPLIT-S2: train {len(p['train'])} (pos "
        f"{len(p['positive_by_role']['train'])}) / val "
        f"{len(p['val'])} (pos {len(p['positive_by_role']['val'])}) / "
        f"test {len(p['test'])} (pos "
        f"{len(p['positive_by_role']['test'])}) / witness "
        f"{len(p['witness_2020'])}")
    print("  positive train:", [c[-9:] for c in p['positive_by_role']['train']])
    print("  positive val:  ", [c[-9:] for c in p['positive_by_role']['val']])
    print("  positive test: ", [c[-9:] for c in p['positive_by_role']['test']])
    print("  witness:        ", [c[-9:] for c in p['witness_2020']])
    print("  min cross-role gap:",
          p['buffer_check']['min_cross_role_gap_m'], "m; violations:",
          p['buffer_check']['n_cross_role_pairs_closer_than_buffer'])
    print("C1:", c1_verdict["verdict"], "| C3:", c3["verdict"])
    print("protocol ->", proto_path)
    print("checksum:", protocol["checksum"])


if __name__ == "__main__":
    main()
