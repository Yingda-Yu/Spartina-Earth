"""Render docs/experiments/PILOT0_BASELINE_REPORT.md from result tables."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from spartina.experiments.aggregate import MODEL_LABELS, VARIANTS, collect


def _fmt(v: Any, nd: int = 3) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "N/A"
    return f"{float(v):.{nd}f}"


def _msd(values: pd.Series, nd: int = 3) -> str:
    vals = values.dropna()
    if vals.empty:
        return "N/A"
    if len(vals) == 1:
        return f"{float(vals.iloc[0]):.{nd}f}"
    return (f"{float(vals.mean()):.{nd}f} ± "
            f"{float(vals.std(ddof=1)):.{nd}f}")


def _cell(df: pd.DataFrame, model: str, variant: str, col: str) -> str:
    sub = df[(df["model"] == model) & (df["variant"] == variant)]
    if sub.empty:
        return "—"
    return _msd(sub[col])


def main_table(metrics: pd.DataFrame) -> str:
    test = metrics[metrics["split"] == "test"]
    lines = [
        "| Model | Variant | TEST core IoU | TEST core F1 | TEST core AUPRC |",
        "|---|---|---:|---:|---:|"]
    for model, label in MODEL_LABELS.items():
        if model not in set(test["model"]):
            continue
        variants = ["spectral_sai"] if model == "sai" else list(VARIANTS)
        for variant in variants:
            sub = test[(test["model"] == model) &
                       (test["variant"] == variant)]
            if sub.empty:
                continue
            lines.append(
                f"| {label} | {variant} | "
                f"{_msd(sub['arbitrated_core_iou'])} | "
                f"{_msd(sub['arbitrated_core_f1'])} | "
                f"{_msd(sub['arbitrated_core_auprc'])} |")
    return "\n".join(lines)


def ablation_table(metrics: pd.DataFrame) -> str:
    test = metrics[metrics["split"] == "test"]
    lines = ["| Model | optical Δ IoU | +indices Δ | +SAR Δ | full Δ |",
             "|---|---:|---:|---:|---:|"]
    for model in ("random_forest", "unet", "deeplabv3plus",
                  "segformer_b0"):
        sub = test[test["model"] == model]
        if sub.empty:
            continue
        means = {v: sub[sub["variant"] == v]
                 ["arbitrated_core_iou"].mean() for v in VARIANTS}
        if np.isnan(means["optical"]):
            continue
        deltas = {v: (m - means["optical"]) if not np.isnan(m) else np.nan
                  for v, m in means.items()}
        lines.append(
            f"| {MODEL_LABELS[model]} | 0.000 | "
            f"{_fmt(deltas['optical_indices'])} | "
            f"{_fmt(deltas['optical_sar'])} | "
            f"{_fmt(deltas['full'])} |")
    return "\n".join(lines)


def seed_table(metrics: pd.DataFrame) -> str:
    test = metrics[metrics["split"] == "test"].sort_values(
        ["model", "variant", "seed"])
    lines = ["| Model | Variant | Seed | core IoU | core F1 | "
             "strict IoU | strict F1 | thr |",
             "|---|---|---|---:|---:|---:|---:|---:|"]
    for _, r in test.iterrows():
        seed_txt = ("deterministic" if pd.isna(r["seed"])
                    else str(int(r["seed"])))
        lines.append(
            f"| {MODEL_LABELS.get(r['model'], r['model'])} | "
            f"{r['variant']} | {seed_txt} | "
            f"{_fmt(r['arbitrated_core_iou'])} | "
            f"{_fmt(r['arbitrated_core_f1'])} | "
            f"{_fmt(r['silver_strict_iou'])} | "
            f"{_fmt(r['silver_strict_f1'])} | "
            f"{_fmt(r['arbitrated_core_threshold'], 2)} |")
    return "\n".join(lines)


def views_table(metrics: pd.DataFrame) -> str:
    test = metrics[metrics["split"] == "test"]
    lines = ["| Model | Variant | core IoU | strict IoU | core Precision | "
             "strict Precision | core Recall | strict Recall |",
             "|---|---|---:|---:|---:|---:|---:|---:|"]
    for model, label in MODEL_LABELS.items():
        for variant in VARIANTS + ("spectral_sai",):
            sub = test[(test["model"] == model) &
                       (test["variant"] == variant)]
            if sub.empty:
                continue
            lines.append(
                f"| {label} | {variant} | "
                f"{_msd(sub['arbitrated_core_iou'])} | "
                f"{_msd(sub['silver_strict_iou'])} | "
                f"{_msd(sub['arbitrated_core_precision'])} | "
                f"{_msd(sub['silver_strict_precision'])} | "
                f"{_msd(sub['arbitrated_core_recall'])} | "
                f"{_msd(sub['silver_strict_recall'])} |")
    return "\n".join(lines)


def weak_table(weak: pd.DataFrame) -> str:
    if weak.empty:
        return "_No WEAK-only candidate components were covered by TEST "
        "windows; diagnostic not computable (N/A)._"
    g = weak.groupby(["model", "variant"])
    agg = g.agg(
        n_components=("component_id", "nunique"),
        mean_prob=("mean_prob", "mean"),
        median_prob=("median_prob", "mean"),
        above_fraction=("above_threshold_fraction", "mean"),
        response_rate=("component_response", "mean")).reset_index()
    lines = ["| Model | Variant | covered components | mean prob | "
             "median prob | above-thr fraction | component response rate |",
             "|---|---|---:|---:|---:|---:|---:|"]
    for _, r in agg.iterrows():
        lines.append(
            f"| {MODEL_LABELS.get(r['model'], r['model'])} | "
            f"{r['variant']} | {int(r['n_components'])} | "
            f"{_fmt(r['mean_prob'])} | {_fmt(r['median_prob'])} | "
            f"{_fmt(r['above_fraction'])} | {_fmt(r['response_rate'])} |")
    lines.append("")
    lines.append("_This is a candidate-response diagnostic, NOT accuracy "
                 "or recall: there is no GOLD label for these pixels._")
    return "\n".join(lines)


def stress_table(stress: pd.DataFrame, metrics: pd.DataFrame) -> str:
    if stress.empty:
        return "N/A (computed only after final TEST evaluation)."
    test = metrics[metrics["split"] == "test"]
    lines = ["| Model | Input | core IoU | strict IoU | core F1 |",
             "|---|---|---:|---:|---:|"]
    for model in ("unet", "deeplabv3plus", "segformer_b0"):
        base = test[(test["model"] == model) &
                    (test["variant"] == "full")]
        if not base.empty:
            lines.append(
                f"| {MODEL_LABELS[model]} | full (no drop) | "
                f"{_msd(base['arbitrated_core_iou'])} | "
                f"{_msd(base['silver_strict_iou'])} | "
                f"{_msd(base['arbitrated_core_f1'])} |")
        for drop in ("indices", "sar", "sar_indices"):
            sub = stress[(stress["model"] == model) &
                         (stress["drop"] == drop) &
                         (stress["view"] == "arbitrated_core")]
            subs = stress[(stress["model"] == model) &
                          (stress["drop"] == drop) &
                          (stress["view"] == "silver_strict")]
            if sub.empty:
                continue
            lines.append(
                f"| {MODEL_LABELS[model]} | drop {drop} | "
                f"{_msd(sub['m_iou'])} | {_msd(subs['m_iou'])} | "
                f"{_msd(sub['m_f1'])} |")
    return "\n".join(lines)


def calibration_table(metrics: pd.DataFrame) -> str:
    test = metrics[metrics["split"] == "test"]
    lines = ["| Model | Variant | Brier | ECE(15) |",
             "|---|---|---:|---:|"]
    for model, label in MODEL_LABELS.items():
        for variant in VARIANTS + ("spectral_sai",):
            sub = test[(test["model"] == model) &
                       (test["variant"] == variant)]
            if sub.empty:
                continue
            lines.append(
                f"| {label} | {variant} | "
                f"{_msd(sub['arbitrated_core_brier'])} | "
                f"{_msd(sub['arbitrated_core_ece'])} |")
    return "\n".join(lines)


def patch_table(metrics: pd.DataFrame) -> str:
    test = metrics[metrics["split"] == "test"]
    lines = ["| Model | Variant | P@.25 | R@.25 | P@.50 | R@.50 | "
             "small-patch R |",
             "|---|---|---:|---:|---:|---:|---:|"]
    for model, label in MODEL_LABELS.items():
        for variant in VARIANTS + ("spectral_sai",):
            sub = test[(test["model"] == model) &
                       (test["variant"] == variant)]
            if sub.empty:
                continue
            small = sub["arbitrated_core_patch_025_small_patch_recall"]
            lines.append(
                f"| {label} | {variant} | "
                f"{_msd(sub['arbitrated_core_patch_025_patch_precision'])} | "
                f"{_msd(sub['arbitrated_core_patch_025_patch_recall'])} | "
                f"{_msd(sub['arbitrated_core_patch_050_patch_precision'])} | "
                f"{_msd(sub['arbitrated_core_patch_050_patch_recall'])} | "
                f"{_msd(small)} |")
    return "\n".join(lines)


def area_table(metrics: pd.DataFrame) -> str:
    test = metrics[metrics["split"] == "test"]
    lines = ["| Model | Variant | abs area err (ha) | relative err | "
             "signed bias |",
             "|---|---|---:|---:|---:|"]
    for model, label in MODEL_LABELS.items():
        for variant in VARIANTS + ("spectral_sai",):
            sub = test[(test["model"] == model) &
                       (test["variant"] == variant)]
            if sub.empty:
                continue
            lines.append(
                f"| {label} | {variant} | "
                f"{_msd(sub['arbitrated_core_abs_area_error_ha'], 2)} | "
                f"{_msd(sub['arbitrated_core_rel_area_error'])} | "
                f"{_msd(sub['arbitrated_core_signed_area_bias'])} |")
    return "\n".join(lines)


def efficiency_table(eff: pd.DataFrame) -> str:
    lines = ["| Model | params | peak VRAM MiB | wall s | windows/s | "
             "checkpoint MiB | GPU |",
             "|---|---:|---:|---:|---:|---:|---|"]
    for model, label in MODEL_LABELS.items():
        sub = eff[eff["model"] == model]
        if sub.empty:
            continue
        def med(col: str, sub: pd.DataFrame = sub) -> str:
            v = pd.to_numeric(sub[col], errors="coerce").dropna()
            return _fmt(float(v.median()), 1) if not v.empty else "N/A"
        params = pd.to_numeric(sub["params"], errors="coerce").dropna()
        ps = f"{int(params.median())}" if not params.empty else "N/A (CPU)"
        ckpt = pd.to_numeric(sub["checkpoint_size_bytes"],
                             errors="coerce").dropna()
        cm = _fmt(float(ckpt.median()) / 2**20, 2) if not ckpt.empty \
            else "N/A"
        gpus = "/".join(sorted({str(g) for g in sub["gpu_id"].dropna()
                                if g})) or "CPU"
        lines.append(
            f"| {label} | {ps} | {med('peak_vram_mib')} | "
            f"{med('train_wall_s')} | {med('windows_per_s')} | "
            f"{cm} | {gpus} |")
    return "\n".join(lines)


def render(repo: Path) -> str:
    runs_root = repo / "runs/pilot0"
    tables = collect(repo, runs_root)
    metrics, eff = tables["metrics"], tables["efficiency"]
    weak, stress = tables["weak"], tables["stress"]
    registry = repo / "docs/experiments/registries/pilot0_registry.csv"
    n_fail_official = 0
    n_fail_smoke = 0
    n_boundary_thr = 0
    if registry.exists():
        reg = pd.read_csv(registry)
        off = reg[reg["phase"] == "official"]
        n_fail_official = int((off["status"] == "FAILED").sum())
        n_fail_smoke = int((reg["status"] == "FAILED").sum())
        n_boundary_thr = int((off["val_threshold"] == 0.05).sum())
    test = metrics[metrics["split"] == "test"]
    degenerate = test[test["arbitrated_core_iou"] < 0.10][[
        "model", "variant", "seed", "arbitrated_core_iou"]]
    parts = [
        "# Pilot-0 Baseline Ladder — M1.5 Report",
        "",
        "Generated from frozen run manifests; split **Pilot-0 v1** was "
        "not modified. Labels: SILVER national map + WEAK local mask, "
        "**no GOLD**. Primary view `arbitrated_core`; `silver_strict` "
        "measures SILVER-product reproduction only. TEST was accessed "
        "exactly once after `FINAL_EVAL_LOCK.json` was frozen.",
        "",
        "Spatial CI note: TEST contains 7 windows / 5 SILVER components, "
        "so spatial block-level confidence intervals are not estimable; "
        "the 3 seeds cover initialization/training randomness only, not "
        "geographic uncertainty.",
        "",
        "## 1. Baseline main table", "", main_table(metrics), "",
        "## 2. Input ablation (Δ TEST core IoU vs optical)", "",
        ablation_table(metrics), "",
        "## 3. Seed-level results", "", seed_table(metrics), "",
        "## 4. arbitrated_core vs silver_strict", "",
        views_table(metrics), "",
        "## 5. WEAK-only candidate response (diagnostic)", "",
        weak_table(weak), "",
        "## 6. Missing-modality stress (full model, no retraining)", "",
        stress_table(stress, metrics), "",
        "## 7. Calibration (15 equal-width ECE)", "",
        calibration_table(metrics), "",
        "## 8. Patch metrics (8-connectivity, one-to-one)", "",
        patch_table(metrics), "",
        "## 9. Area error", "", area_table(metrics), "",
        "## 10. Efficiency", "", efficiency_table(eff), "",
        "## 11. Failure cases and notable observations", "",
        f"- Official runs FAILED: **{n_fail_official}** of 49; "
        f"retained early smoke failures: {n_fail_smoke} (registry keeps "
        "both for traceability; they never entered the official matrix).",
        f"- VAL thresholds at the grid floor (0.05): "
        f"{n_boundary_thr} official runs (all Random Forest) — low "
        "probability scale under class imbalance; threshold protocol was "
        "not altered.",
        "- TEST core IoU < 0.10 (seed-level collapse, reported as run, "
        "not averaged away):",
    ]
    if degenerate.empty:
        parts.append("  - none")
    for _, r in degenerate.iterrows():
        parts.append(
            f"  - {MODEL_LABELS.get(r['model'], r['model'])} / "
            f"{r['variant']} / seed {int(r['seed'])}: "
            f"TEST core IoU {float(r['arbitrated_core_iou']):.3f}")
    parts += [
        "- The first `final_eval.py` invocation aborted on the material "
        "WEAK-component guard (9 != 91) **before** any TEST metric was "
        "written; the candidate mask was corrected to the frozen Issue #4 "
        "definition (disagreement code 3, incl. IGNORE boundary buffer) "
        "and TEST was evaluated exactly once afterwards.",
        "- TEST = 7 windows / 5 SILVER components: all differences at this "
        "scale are sensitive to individual patches; no spatial CI.",
        "",
        "See `docs/experiments/registries/pilot0_registry.csv` for "
        "per-run checkpoint hashes, thresholds and GPU metadata.",
        "",
    ]
    return "\n".join(parts)


def write_report(repo: Path) -> Path:
    out = repo / "docs/experiments/PILOT0_BASELINE_REPORT.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(repo), encoding="utf-8")
    return out
