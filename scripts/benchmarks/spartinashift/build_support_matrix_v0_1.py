#!/usr/bin/env python3
"""Issue #20 Stage 1, Phase A -- SpartinaShift-Silver v0.1 support matrix.

Joins the FROZEN Issue #19 V2 inventories into one machine-readable
cell x year x sensor x label_source x modality matrix and computes the
C1-C5 task-specific support counts BEFORE any split or training:

* datasets/manifests/national_pilot_event_plan_v2.csv (planned EO;
  includes NO_SCENE / actual-mask rejection statuses),
* datasets/manifests/national_pilot19_pilot_qa_v2.json (184 landed
  products, PASS/WARN, actual observed fractions, live QA flags),
* datasets/manifests/national_pilot19_label_supports_v1.csv (SILVER
  label supports at 30 m and the CM-SSM 10 m external support),
* datasets/manifests/national_first_pixel_panel_v1.csv (region).

Outputs (tracked, slim):
  benchmarks/spartinashift/silver_v0_1/support_matrix_v0_1.csv
  benchmarks/spartinashift/silver_v0_1/support_matrix_v0_1_summary.json

Read-only with respect to every input. No pixels are read here; this is
an inventory step.
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

from spartina.benchmark.silver.support import (  # noqa: E402
    ACTUAL_MASK_GATE,
    build_support_matrix,
    task_support_summary,
)

PLAN_CSV = REPO_ROOT / "datasets/manifests/national_pilot_event_plan_v2.csv"
QA_JSON = REPO_ROOT / "datasets/manifests/national_pilot19_pilot_qa_v2.json"
LABELS_CSV = (
    REPO_ROOT / "datasets/manifests/national_pilot19_label_supports_v1.csv")
PANEL_CSV = REPO_ROOT / "datasets/manifests/national_first_pixel_panel_v1.csv"
OUT_DIR = REPO_ROOT / "benchmarks/spartinashift/silver_v0_1"
OUT_CSV = OUT_DIR / "support_matrix_v0_1.csv"
OUT_JSON = OUT_DIR / "support_matrix_v0_1_summary.json"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, check=True,
            capture_output=True, text=True)
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNKNOWN"


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame,
                           pd.DataFrame, dict[str, Any]]:
    plan = pd.read_csv(PLAN_CSV)
    qa = json.loads(QA_JSON.read_text())
    landed = pd.DataFrame(qa["products"])
    event_cols = plan[
        ["product_id", "event_id", "event_utc"]].drop_duplicates(
            "product_id")
    landed = landed.merge(event_cols, on="product_id", how="left")
    labels = pd.read_csv(LABELS_CSV)
    panel = pd.read_csv(PANEL_CSV)[
        ["cell_id", "region_province", "coastal_segment"]]
    return plan, landed, labels, panel, qa


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir", type=Path, default=OUT_DIR,
        help="output directory (default: frozen benchmark location)")
    args = parser.parse_args()
    out_dir = args.out_dir
    out_csv = out_dir / OUT_CSV.name
    out_json = out_dir / OUT_JSON.name
    out_dir.mkdir(parents=True, exist_ok=True)

    plan, landed, labels, panel, qa = load_inputs()
    n_panel = int(panel["cell_id"].nunique())
    if n_panel != 20:
        raise SystemExit(f"expected 20 frozen panel cells, found {n_panel}")
    if len(landed) != 184:
        raise SystemExit(
            f"expected 184 landed V2 products, found {len(landed)}")

    rejected_ids = {
        str(r["product_id"])
        for r in qa.get("actual_mask_rejections", {}).get(
            "confirmed", [])}
    matrix = build_support_matrix(
        plan, landed, labels, panel, rejected_product_ids=rejected_ids)
    matrix.to_csv(out_csv, index=False)

    summary = task_support_summary(matrix)
    summary["generated_utc"] = datetime.now(UTC).isoformat()
    summary["git_commit"] = _git_commit()
    summary["issue"] = 20
    summary["stage"] = "STAGE_1_protocol_freeze_and_conventional_baselines"
    summary["actual_mask_gate"] = ACTUAL_MASK_GATE
    summary["inputs"] = {
        "event_plan_v2_csv": {
            "path": str(PLAN_CSV.relative_to(REPO_ROOT)),
            "sha256": _sha256(PLAN_CSV)},
        "pilot_qa_v2_json": {
            "path": str(QA_JSON.relative_to(REPO_ROOT)),
            "sha256": _sha256(QA_JSON),
            "n_landed_products": len(landed),
            "qa_gate_verdict": qa.get("gate_verdict"),
            "live_cross_checked_products": int(
                landed["live_cross_checked"].sum())},
        "label_supports_v1_csv": {
            "path": str(LABELS_CSV.relative_to(REPO_ROOT)),
            "sha256": _sha256(LABELS_CSV),
            "n_rows": int(len(labels))},
        "first_pixel_panel_v1_csv": {
            "path": str(PANEL_CSV.relative_to(REPO_ROOT)),
            "sha256": _sha256(PANEL_CSV),
            "n_cells": n_panel},
    }
    summary["outputs"] = {
        "support_matrix_csv": {
            "path": str(out_csv.relative_to(REPO_ROOT)),
            "n_rows": int(len(matrix))},
    }
    out_json.write_text(json.dumps(summary, indent=2, sort_keys=False) + "\n")
    summary["outputs"]["support_matrix_csv"]["sha256"] = _sha256(out_csv)
    summary["matrix_sha256"] = summary["outputs"][
        "support_matrix_csv"]["sha256"]
    out_json.write_text(json.dumps(summary, indent=2, sort_keys=False) + "\n")

    tasks = summary["tasks"]
    print(f"matrix rows: {len(matrix)} -> {out_csv}")
    print(f"summary     -> {out_json}")
    print(
        "C1 cells:", tasks["C1_cross_year_geodata_l8"]["n_eligible_cells"],
        "C2 cells:", tasks["C2_cross_year_cmsa_s2"]["n_eligible_cells"],
        "C4 cells:", tasks["C4_cross_source_2020"]["n_eligible_cells"],
        "C5 cells:", tasks["C5_modality_ablation_2020"]["n_eligible_cells"])
    adequate = {
        prov: v["adequate_holdout_under"]
        for prov, v in tasks["C3_cross_region_province_holdout"][
            "regions"].items() if v["adequate_holdout_under"]}
    print("C3 adequate province holdouts:", adequate)


if __name__ == "__main__":
    main()
