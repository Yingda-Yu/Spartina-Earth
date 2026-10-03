#!/usr/bin/env python3
"""M2.1b Issue #13 -- deterministic stratified pilot-cell selection.

Offline: reads only tracked manifests and the corrected v0_1 observation
artifact. No Earth Engine calls, no pixels, no performance data. Writes
the frozen cell roster (CSV + signed JSON) that the live event
discovery and real-export drivers must consume exactly.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

import pandas as pd  # noqa: E402

from spartina.data.gee.provenance import git_context, sha256_file  # noqa: E402
from spartina.data.gee.selection import canonical_fingerprint  # noqa: E402
from spartina.data.zhejiang.m21b_pilot import (  # noqa: E402
    AUTUMN_PRIMARY_V1_DOY_END,
    AUTUMN_PRIMARY_V1_DOY_START,
    CELL_SIZE_M,
    PILOT_BAY_ID,
    PILOT_YEAR,
    CellLabelSummary,
    select_pilot_cells,
    summarize_cell_labels,
)

OVERLAP_CSV = REPO_ROOT / "datasets/manifests/zhejiang_label_cell_overlap_v0_1.csv"
DISAGREEMENT_CSV = REPO_ROOT / "datasets/manifests/zhejiang_hzb_label_disagreement_v0_1.csv"
CELLS_CSV = REPO_ROOT / "datasets/manifests/zhejiang_analysis_cells_v0.csv"
OBSERVATIONS_PARQUET = REPO_ROOT / "work/derived/zhejiang_cell_observations_v0_1.parquet"
OUT_CSV = REPO_ROOT / "datasets/manifests/zhejiang_m21b_pilot_cells_v0.csv"
OUT_JSON = REPO_ROOT / "datasets/manifests/zhejiang_m21b_pilot_cells_v0.json"


def _input_record(path: Path) -> dict[str, Any]:
    return {"path": str(path.relative_to(REPO_ROOT)),
            "sha256": sha256_file(path)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-csv", default=str(OUT_CSV))
    parser.add_argument("--out-json", default=str(OUT_JSON))
    args = parser.parse_args()

    overlap = pd.read_csv(OVERLAP_CSV)
    disagreement = pd.read_csv(DISAGREEMENT_CSV)
    cells = pd.read_csv(CELLS_CSV)
    obs = pd.read_parquet(OBSERVATIONS_PARQUET)

    hzb_cells = cells[(cells["bay_id"] == PILOT_BAY_ID)
                      & (cells["cell_size_m"] == CELL_SIZE_M)]
    relevance = dict(zip(hzb_cells["cell_id"],
                         hzb_cells["coastal_relevance"], strict=True))

    ov_hzb = overlap[(overlap["bay_id"] == PILOT_BAY_ID)
                     & (overlap["cell_size_m"] == CELL_SIZE_M)]
    s2_eligible = set(obs[
        (obs["bay_id"] == PILOT_BAY_ID)
        & (obs["cell_size_m"] == CELL_SIZE_M)
        & (obs["sensor"] == "sentinel2")
        & (obs["year"] == PILOT_YEAR)
        & (obs["day_of_year"].between(
            AUTUMN_PRIMARY_V1_DOY_START, AUTUMN_PRIMARY_V1_DOY_END))
        & (obs["quality_pass"])]["cell_id"].unique())

    summaries: dict[str, CellLabelSummary] = {}
    for cell_id, relevance_flag in relevance.items():
        rows = ov_hzb[ov_hzb["cell_id"] == cell_id].to_dict("records")
        summaries[cell_id] = summarize_cell_labels(
            cell_id=cell_id, overlap_rows=rows,
            coastal_relevance=str(relevance_flag),
            s2_quality_event_in_v0_1=cell_id in s2_eligible)

    diag_rows = disagreement[disagreement["cell_size_m"] == CELL_SIZE_M]
    disagreement_map = {
        str(r["cell_id"]): r for r in diag_rows.to_dict("records")}

    choices = select_pilot_cells(summaries, disagreement_map)
    if not 6 <= len(choices) <= 8:
        raise SystemExit(
            f"selection must yield 6-8 cells, got {len(choices)}")

    rows = []
    for order, choice in enumerate(choices, start=1):
        lab = choice.label
        diag = disagreement_map.get(choice.cell_id, {})
        rows.append({
            "selection_order": order,
            "bay_id": PILOT_BAY_ID,
            "cell_id": choice.cell_id,
            "cell_size_m": CELL_SIZE_M,
            "stratum": choice.stratum,
            "rank_metric": choice.rank_metric,
            "rank_value": choice.rank_value,
            "selection_rationale": choice.rationale,
            "bay_clip_area_km2": lab.bay_clip_area_km2,
            "silver_area_km2_bay_clip": lab.silver_area_km2,
            "silver_fraction_of_bay_clip": lab.silver_fraction,
            "weak_max_area_km2_bay_clip": lab.weak_max_area_km2,
            "label_status_bay_scoped": lab.silver_status,
            "unlabeled_control": lab.unlabeled,
            "coastal_relevance": lab.coastal_relevance,
            "diagnostic_jaccard_v0_1": diag.get("jaccard"),
            "v0_1_quality_s2_event_2022_autumn":
                lab.s2_quality_event_2022_autumn_in_v0_1,
            "selection_basis": "LABEL_COMPOSITION_ONLY_NEVER_MODEL_PERFORMANCE",
        })
    out_csv = Path(args.out_csv)
    pd.DataFrame(rows).to_csv(out_csv, index=False)

    payload = {
        "manifest_id": "zhejiang_m21b_pilot_cells_v0",
        "issue": "#13 M2.1b controlled real-pixel multimodal pilot",
        "created_utc": datetime.now(UTC).isoformat(),
        "pilot_scope": {
            "bay_id": PILOT_BAY_ID,
            "year": PILOT_YEAR,
            "season_policy": "autumn_primary_v1 PROPOSED_NOT_FROZEN",
            "doy_window": [AUTUMN_PRIMARY_V1_DOY_START,
                           AUTUMN_PRIMARY_V1_DOY_END],
            "cell_size_m": CELL_SIZE_M,
            "n_cells": len(choices),
        },
        "selection_rule": {
            "basis": (
                "deterministic stratified ranking on label composition; "
                "no use of imagery quality beyond a documented pilot "
                "observability constraint, never model performance"),
            "strata_order": [
                "HIGH_SILVER_FRACTION", "MEDIUM_SILVER_FRACTION x2",
                "LOW_SILVER_FRACTION", "SILVER_WEAK_DISAGREEMENT min J",
                "second diagnostic cell",
                "VERY_LOW positive with existing v0_1 quality S2 event",
                "UNLABELED coastal control with existing v0_1 quality S2 "
                "event"],
            "tiebreak": "lexical cell_id",
            "weak_area_aggregation": (
                "max over audited WEAK products, never the sum"),
        },
        "inputs": {
            "label_overlap_v0_1": _input_record(OVERLAP_CSV),
            "label_disagreement_v0_1": _input_record(DISAGREEMENT_CSV),
            "analysis_cells_v0": _input_record(CELLS_CSV),
            "cell_observations_v0_1": _input_record(OBSERVATIONS_PARQUET),
        },
        "cells": rows,
        "git": git_context(REPO_ROOT),
    }
    payload["fingerprint_sha256"] = canonical_fingerprint(
        {k: v for k, v in payload.items() if k != "fingerprint_sha256"})
    out_json = Path(args.out_json)
    out_json.write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    for row in rows:
        print(f"{row['selection_order']}. {row['cell_id']} "
              f"{row['stratum']:<32} silver_frac={row['silver_fraction_of_bay_clip']} "
              f"v0_1_S2={row['v0_1_quality_s2_event_2022_autumn']}")
    print(f"wrote {out_csv.relative_to(REPO_ROOT)} and "
          f"{out_json.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
