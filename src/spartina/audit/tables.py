"""Rebuild Pilot-0 result tables strictly from frozen run artifacts.

Every tracked audit table is generated from the on-disk run manifests and
stored ``val_metrics.json`` / ``test_metrics.json``. Nothing is hand-typed
and TEST probabilities are never recomputed. The builder HARD-FAILS on:

* missing / duplicate official run keys,
* wrong seed/variant matrix,
* an official COMPLETED run without a val or TEST metric record,
* a non-official run carrying TEST metrics,
* mean/SD cells computed over fewer than the declared three seeds
  (collapsed runs must stay in the denominator).
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from spartina.audit.paths import (
    OFFICIAL_COUNTS,
    SEEDS,
    VARIANTS,
    RunArtifact,
    official_completed,
)
from spartina.data.dataset import grid_view_masks
from spartina.data.pilot0 import split_coverage_mask

SCALAR_KEYS = (
    "threshold", "n_valid_pixels", "n_positive_pixels", "iou",
    "precision", "recall", "f1", "auprc", "bf1_30m", "bf1_60m",
    "pred_area_ha", "ref_area_ha", "abs_area_error_ha",
    "rel_area_error", "signed_area_bias", "brier", "ece")
CORE_METRICS = ("iou", "f1", "auprc", "brier", "ece", "signed_area_bias",
                "precision", "recall")
DELTA_METRICS = ("iou", "f1", "auprc", "brier", "ece", "signed_area_bias")
# (output column, numerator variant, denominator variant)
DELTA_CONTRASTS = (
    ("indices_opticalindices_minus_optical", "optical_indices", "optical"),
    ("sar_opticalsar_minus_optical", "optical_sar", "optical"),
    ("sar_marginal_full_minus_opticalindices", "full", "optical_indices"),
    ("full_minus_optical", "full", "optical"),
)


class TableIntegrityError(RuntimeError):
    """Raised when the frozen artifact set cannot form a valid table."""


def expected_keys() -> set[tuple[str, str, int | None]]:
    keys: set[tuple[str, str, int | None]] = {
        ("sai", "spectral_sai", None)}
    for model in ("random_forest", "unet", "deeplabv3plus", "segformer_b0"):
        for variant in VARIANTS:
            for seed in SEEDS:
                keys.add((model, variant, seed))
    return keys


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise TableIntegrityError(message)


def canonical_hash(df: pd.DataFrame) -> str:
    """Deterministic content hash of a table (container-independent)."""
    payload = json.dumps(
        df.where(pd.notnull(df), None).values.tolist(),
        sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _flatten_view(view: dict[str, Any], prefix: str) -> dict[str, Any]:
    out = {f"{prefix}_{k}": view.get(k) for k in SCALAR_KEYS}
    for tag in ("patch_025", "patch_050"):
        for k, v in (view.get(tag) or {}).items():
            out[f"{prefix}_{tag}_{k}"] = v
    return out


@dataclass(frozen=True)
class AuditTables:
    metrics: pd.DataFrame          # one row per run x split
    stress: pd.DataFrame           # stored full-model missing-modality runs
    weak: pd.DataFrame             # stored WEAK candidate component response
    deltas: pd.DataFrame           # variant contrasts per model/seed/split
    means: pd.DataFrame            # model x variant means over ALL seeds
    sensitivity: pd.DataFrame      # A7 evidence + aggregate records


def _metrics_rows(runs: list[RunArtifact]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for run in runs:
        base = {"run_id": run.run_id, "model": run.model,
                "variant": run.variant, "seed": run.seed,
                "status": run.status}
        for split, payload in (
                ("val", run.val_metrics), ("test", run.test_metrics)):
            if payload is None:
                continue
            row = dict(base)
            row["split"] = split
            for view in ("arbitrated_core", "silver_strict"):
                row.update(_flatten_view(payload[view], view))
            rows.append(row)
    return rows


def _stress_rows(runs: list[RunArtifact]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for run in runs:
        tm = run.test_metrics
        if not tm or "missing_modality_stress" not in tm:
            continue
        for drop, views in tm["missing_modality_stress"].items():
            for view, bundle in views.items():
                baseline_iou = float(tm[view]["iou"])
                rows.append({
                    "run_id": run.run_id, "model": run.model,
                    "variant": run.variant, "seed": run.seed,
                    "drop": drop, "view": view,
                    "iou": bundle.get("iou"), "f1": bundle.get("f1"),
                    "auprc": bundle.get("auprc"),
                    "brier": bundle.get("brier"), "ece": bundle.get("ece"),
                    "signed_area_bias": bundle.get("signed_area_bias"),
                    "baseline_iou": baseline_iou,
                    "iou_delta_vs_full": float(bundle.get("iou"))
                    - baseline_iou,
                })
    return rows


def _weak_rows(runs: list[RunArtifact]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for run in runs:
        tm = run.test_metrics
        if not tm:
            continue
        for rec in tm.get("weak_candidate_response", []):
            rows.append({"run_id": run.run_id, "model": run.model,
                         "variant": run.variant, "seed": run.seed, **rec})
    return rows


def _validate_grid(
    runs: list[RunArtifact], metrics: pd.DataFrame,
) -> None:
    official = official_completed(runs)
    found = {(r.model, r.variant, r.seed) for r in official}
    want = expected_keys()
    _require(len(OFFICIAL_COUNTS) == 5 and len(want) == 49,
             "official key template is not the declared 49-run matrix")
    _require(found == want,
             f"official matrix mismatch: missing={sorted(want - found)} "
             f"extra={sorted(found - want)}")
    _require(len(found) == len(official), "duplicate official run keys")

    seen = set(metrics[["run_id", "split"]].itertuples(index=False,
                                                        name=None))
    _require(len(seen) == len(metrics), "duplicate run_id/split metric rows")
    for run in official:
        for split in ("val", "test"):
            hit = metrics[(metrics.run_id == run.run_id)
                          & (metrics.split == split)]
            _require(len(hit) == 1,
                     f"{run.run_id}: expected exactly one {split} record, "
                     f"found {len(hit)}")
    # non-official runs must never carry TEST metrics
    for run in runs:
        if run.phase != "official" and run.test_metrics is not None:
            raise TableIntegrityError(
                f"non-official run {run.run_id} carries TEST metrics")
    # TEST counts per model/variant cell
    test = metrics[metrics.split == "test"]
    for model in ("random_forest", "unet", "deeplabv3plus", "segformer_b0"):
        for variant in VARIANTS:
            n = len(test[(test.model == model) & (test.variant == variant)])
            _require(n == 3,
                     f"{model}/{variant}: {n} TEST rows, expected 3")
    sai = test[test.model == "sai"]
    _require(len(sai) == 1, f"SAI TEST rows={len(sai)}, expected 1")


def _deltas(metrics: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    core = metrics[["run_id", "model", "variant", "seed", "split"] + [
        f"arbitrated_core_{m}" for m in DELTA_METRICS]].copy()
    core.columns = ["run_id", "model", "variant", "seed", "split"] + list(
        DELTA_METRICS)
    for split in ("val", "test"):
        d = core[core.split == split]
        for model in ("random_forest", "unet", "deeplabv3plus",
                      "segformer_b0"):
            for seed in SEEDS:
                cell = d[(d.model == model) & (d.seed == seed)]
                if cell.empty:
                    continue
                by_var = {r.variant: r for r in cell.itertuples(
                    index=False)}
                for name, hi_var, lo_var in DELTA_CONTRASTS:
                    if hi_var not in by_var or lo_var not in by_var:
                        raise TableIntegrityError(
                            f"delta {name} missing for {model}/{seed}")
                    hi, lo = by_var[hi_var], by_var[lo_var]
                    row = {"model": model, "seed": seed, "split": split,
                           "contrast": name}
                    for m in DELTA_METRICS:
                        row[f"delta_{m}"] = float(
                            getattr(hi, m) - getattr(lo, m))
                    rows.append(row)
    return pd.DataFrame(rows)


def _means(
    metrics: pd.DataFrame, classifications: dict[str, str],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    test = metrics[metrics.split == "test"]
    val = metrics[metrics.split == "val"]
    for model in ("sai", "random_forest", "unet", "deeplabv3plus",
                  "segformer_b0"):
        variants = ("spectral_sai",) if model == "sai" else VARIANTS
        for variant in variants:
            for split, frame in (("val", val), ("test", test)):
                cell = frame[(frame.model == model)
                             & (frame.variant == variant)]
                expected_n = 1 if model == "sai" else 3
                _require(len(cell) == expected_n,
                         f"means {model}/{variant}/{split}: "
                         f"{len(cell)} rows, expected {expected_n}")
                row = {"model": model, "variant": variant, "split": split,
                       "n_seeds": len(cell)}
                for m in CORE_METRICS:
                    vals = cell[f"arbitrated_core_{m}"].astype(float)
                    row[f"{m}_mean"] = float(vals.mean())
                    row[f"{m}_std"] = (float(vals.std(ddof=1))
                                       if len(vals) > 1 else math.nan)
                run_ids = cell.run_id.tolist()
                flags = [classifications.get(rid, "NO_COLLAPSE")
                         for rid in run_ids]
                row["collapsed_seeds"] = sum(
                    f != "NO_COLLAPSE" for f in flags)
                row["n_seeds_in_denominator"] = len(cell)
                rows.append(row)
    return pd.DataFrame(rows)


def _sensitivity(
    runs: list[RunArtifact], metrics: pd.DataFrame,
) -> pd.DataFrame:
    """A7: persist only what the stored TEST records actually support."""
    rows: list[dict[str, Any]] = []
    requested = (
        ("per_silver_component_iou", "SILVER component IoU"),
        ("per_silver_component_area_ha", "SILVER component area"),
        ("per_silver_component_recall", "SILVER component recall"),
        ("per_silver_component_boundary_f1",
         "SILVER component boundary F1"),
        ("leave_one_component_out_iou",
         "aggregate IoU recomputed excluding one SILVER component"),
    )
    for key, desc in requested:
        rows.append({
            "section": "silver_component_request",
            "metric": key, "description": desc,
            "status": "NOT_PERSISTED",
            "evidence": (
                "final_eval.py stored only aggregate evaluate_view output; "
                "stitched TEST probability rasters and per-component match "
                "lists were not written to disk, so the quantity cannot be "
                "recomputed without re-accessing TEST, which Issue #10 "
                "forbids. Evaluation v1.1 must persist the stitched "
                "probability mosaic and component match table."),
            "model": "", "variant": "", "seed": "", "value": math.nan})
    test = metrics[metrics.split == "test"]
    for r in test.itertuples(index=False):
        rows.append({
            "section": "stored_test_aggregate",
            "metric": "arbitrated_core",
            "description": "headline aggregate from stored test_metrics",
            "status": "PERSISTED", "evidence": "test_metrics.json",
            "model": r.model, "variant": r.variant,
            "seed": "" if r.seed is None or (isinstance(r.seed, float)
                                              and math.isnan(r.seed))
            else int(r.seed),
            "value": float(r.arbitrated_core_iou),
            "iou": float(r.arbitrated_core_iou),
            "f1": float(r.arbitrated_core_f1),
            "recall": float(r.arbitrated_core_recall),
            "precision": float(r.arbitrated_core_precision),
            "n_ref_components_025": int(
                r.arbitrated_core_patch_025_n_ref),
            "n_matches_025": int(r.arbitrated_core_patch_025_n_matches),
            "n_valid_pixels": int(r.arbitrated_core_n_valid_pixels),
            "n_positive_pixels": int(
                r.arbitrated_core_n_positive_pixels)})
    return pd.DataFrame(rows)


def silver_component_census(
    sources: Any, grid: Any,
) -> list[dict[str, Any]]:
    """Static SILVER label census over TEST geometry (no predictions).

    Full-grid connected components give the ecological patch count (5);
    coverage-fragmented pieces give evaluate_view's ``n_ref`` count (12).
    """
    from spartina.benchmark.splits.components import label_components

    test_cov = split_coverage_mask(sources, "test")
    full_lab, full_reg = label_components(sources.silver, "silver")
    views = grid_view_masks(sources, grid, "optical")
    dom = test_cov & views["arbitrated_core"]
    frag_lab, _ = label_components(sources.silver & dom, "silverfrag")
    rows: list[dict[str, Any]] = []
    total_core = int((sources.silver & dom).sum())
    for idx in np.unique(full_lab[test_cov & (full_lab > 0)]):
        cid = full_reg[int(idx)].component_id
        covered_raw = int(((full_lab == idx) & test_cov).sum())
        comp_total = int(full_reg[int(idx)].pixel_count)
        frag_ids = np.unique(frag_lab[(frag_lab > 0) & (full_lab == idx)])
        core_px = int((sources.silver & dom & (full_lab == idx)).sum())
        rows.append({
            "section": "static_silver_component_census",
            "metric": "full_grid_component",
            "description": (
                "static label census; prediction-free. Ecological patch "
                "(full-grid 8-connectivity) intersecting TEST coverage"),
            "status": "PERSISTED",
            "evidence": "silver label + frozen split geometry",
            "model": "", "variant": "optical_core_view", "seed": "",
            "component_id": cid,
            "component_total_px": comp_total,
            "covered_raw_px": covered_raw,
            "core_px_in_test_windows": core_px,
            "core_fraction_of_test_ref": (
                core_px / total_core if total_core else math.nan),
            "n_coverage_fragments": int(len(frag_ids)),
        })
    rows.append({
        "section": "static_silver_component_census",
        "metric": "totals",
        "description": "5 full-grid patches vs 12 coverage-fragmented "
                       "reference pieces (8 >= 10 px, 4 small)",
        "status": "PERSISTED", "evidence": "static census",
        "model": "", "variant": "optical_core_view", "seed": "",
        "component_id": "ALL",
        "component_total_px": int(sources.silver.sum()),
        "covered_raw_px": int((sources.silver & test_cov).sum()),
        "core_px_in_test_windows": total_core,
        "core_fraction_of_test_ref": 1.0,
        "n_coverage_fragments": int(
            len(np.unique(frag_lab[frag_lab > 0]))),
    })
    return rows


def build_audit_tables(
    runs: list[RunArtifact],
    sources: Any = None,
    grid: Any = None,
    classifications: dict[str, str] | None = None,
) -> AuditTables:
    """Validate the frozen matrix and build every audit table."""
    official = official_completed(runs)
    metrics = pd.DataFrame(_metrics_rows(official))
    _validate_grid(runs, metrics)
    stress = pd.DataFrame(_stress_rows(official))
    weak = pd.DataFrame(_weak_rows(official))
    deltas = _deltas(metrics)
    means = _means(metrics, classifications or {})
    sensitivity = _sensitivity(official, metrics)
    if sources is not None and grid is not None:
        census = pd.DataFrame(silver_component_census(sources, grid))
        sensitivity = pd.concat(
            [census, sensitivity], ignore_index=True, sort=False)

    # stored stress coverage: exactly 9 full neural runs x 3 drops x 2 views
    _require(len(stress) == 9 * 3 * 2,
             f"stress rows={len(stress)}, expected 54 (9 full runs)")
    # stored WEAK component coverage: exactly 7 covered components per run
    counts = weak.groupby("run_id").size()
    _require(bool((counts == 7).all()) and len(counts) == 49,
             "weak_candidate_response must cover 7 components for 49 runs")
    return AuditTables(metrics=metrics, stress=stress, weak=weak,
                       deltas=deltas, means=means, sensitivity=sensitivity)
