#!/usr/bin/env python3
"""Issue #21, Phase L -- SpartinaShift v0.2 readiness decision.

Answers the seven directive questions strictly from frozen, signed
artifacts (requirements, Phase I QA summary, Phase J support matrix,
per-cell CSV, fresh reserve, GOLD candidate registry) and returns
exactly one verdict:

    READY_FOR_SPARTINASHIFT_V0_2_PROTOCOL
    NOT_READY_FOR_SPARTINASHIFT_V0_2_PROTOCOL

Thresholds come from the frozen Phase A requirements, never from this
script. The counting unit is the W10 cell; patches are never counted as
independent cells. The decision describes observation *support* only;
no model result enters it, and it authorises no training.
"""

from __future__ import annotations

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

from spartina.benchmark.v02 import acquisition as A  # noqa: E402

V02_DIR = REPO_ROOT / "benchmarks/spartinashift/v0_2"
REQ_JSON = V02_DIR / "SPARTINASHIFT_V0_2_SUPPORT_REQUIREMENTS.json"
QA_JSON = V02_DIR / "V0_2_EXPORT_QA_SUMMARY.json"
MATRIX_JSON = V02_DIR / "V0_2_SUPPORT_MATRIX.json"
PER_CELL_CSV = V02_DIR / "v02_support_matrix_per_cell.csv"
RESERVE_JSON = V02_DIR / "V0_2_FRESH_TEST_RESERVE.json"
GOLD_JSON = V02_DIR / "V0_2_GOLD_CANDIDATE_REGISTRY.json"
OUT_JSON = V02_DIR / "V0_2_READINESS_DECISION.json"

READY = "READY_FOR_SPARTINASHIFT_V0_2_PROTOCOL"
NOT_READY = "NOT_READY_FOR_SPARTINASHIFT_V0_2_PROTOCOL"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verified(path: Path) -> dict[str, Any]:
    doc: dict[str, Any] = json.loads(path.read_text("utf-8"))
    if A.document_checksum(doc) != doc.get("document_checksum"):
        raise SystemExit(f"frozen artifact checksum mismatch: {path.name}")
    return doc


def main() -> int:
    req = _verified(REQ_JSON)
    qa = _verified(QA_JSON)
    matrix = _verified(MATRIX_JSON)
    reserve = _verified(RESERVE_JSON)
    gold = _verified(GOLD_JSON)
    cells = pd.read_csv(PER_CELL_CSV)
    if sha256(PER_CELL_CSV) != matrix.get("per_cell_csv_sha256"):
        raise SystemExit("per-cell CSV does not match frozen matrix hash")

    goals = req["support_goals"]
    g_geo: dict[str, Any] = goals["geodata_temporal"]
    g_cmsa: dict[str, Any] = goals["cmsa_temporal"]
    g_xr: dict[str, Any] = goals["cross_region"]
    g_ns: dict[str, Any] = goals["near_synchronous"]

    landed = cells[cells["any_landed"]]

    # Q1 -- GEODATA temporal: positive in BOTH years with landed Landsat
    # in BOTH anchor years (30 m science stream), regions, background.
    geo_pos = landed[(landed["geo15"] == 1) & (landed["geo20"] == 1)
                     & (landed["landsat_landed_2015"] >= 1)
                     & (landed["landsat_landed_2020"] >= 1)]
    geo_bg = landed[(landed["clean_background"] == 1)
                    & (landed["landsat_landed_2015"] >= 1)
                    & (landed["landsat_landed_2020"] >= 1)]
    q1 = {
        "requirement": {
            "positive_cells_both_years_min": int(
                g_geo["positive_cells_usable_both_years_min"]),
            "regions_min": int(g_geo["regions_min"]),
            "background_cells_min": int(g_geo["background_cells_min"])},
        "measured": {
            "positive_cells_both_2015_2020_with_landed_landsat_both":
                int(len(geo_pos)),
            "regions": int(geo_pos["region_province"].nunique()),
            "region_names": sorted(geo_pos["region_province"].unique()),
            "background_cells_with_landed_eo": int(len(geo_bg))},
    }
    q1["meets"] = (
        q1["measured"][
            "positive_cells_both_2015_2020_with_landed_landsat_both"]
        >= q1["requirement"]["positive_cells_both_years_min"]
        and q1["measured"]["regions"] >= q1["requirement"]["regions_min"]
        and q1["measured"]["background_cells_with_landed_eo"]
        >= q1["requirement"]["background_cells_min"])

    # Q2 -- CMSA temporal: positive in BOTH years with landed S2 in both.
    cmsa_pos = landed[(landed["cmsa20"] == 1) & (landed["cmsa21"] == 1)
                      & (landed["s2_landed_2020"] >= 1)
                      & (landed["s2_landed_2021"] >= 1)]
    cmsa_bg = landed[(landed["clean_background"] == 1)
                     & (landed["s2_landed_2020"] >= 1)
                     & (landed["s2_landed_2021"] >= 1)]
    q2 = {
        "requirement": {
            "positive_cells_both_years_min": int(
                g_cmsa["positive_cells_usable_both_years_min"]),
            "regions_min": int(g_cmsa["regions_min"]),
            "background_cells_min": int(g_cmsa["background_cells_min"])},
        "measured": {
            "positive_cells_both_2020_2021_with_landed_s2_both":
                int(len(cmsa_pos)),
            "regions": int(cmsa_pos["region_province"].nunique()),
            "region_names": sorted(cmsa_pos["region_province"].unique()),
            "background_cells_with_landed_s2_both": int(len(cmsa_bg))},
    }
    q2["meets"] = (
        q2["measured"]["positive_cells_both_2020_2021_with_landed_s2_both"]
        >= q2["requirement"]["positive_cells_both_years_min"]
        and q2["measured"]["regions"] >= q2["requirement"]["regions_min"]
        and q2["measured"]["background_cells_with_landed_s2_both"]
        >= q2["requirement"]["background_cells_min"])

    # Q3 -- defensible cross-region holdouts over landed cells only.
    holdouts: list[dict[str, Any]] = []
    for prov, g in landed.groupby("region_province"):
        n_cells = int(len(g))
        n_pos = int((g["any_positive"] == 1).sum())
        outside = landed[landed["region_province"] != prov]
        if (n_cells >= int(g_xr["held_region_cells_min"])
                and n_pos >= int(g_xr["held_region_positive_cells_min"])
                and len(outside) >= int(g_xr["outside_pool_cells_min"])
                and int((outside["any_positive"] == 1).sum())
                >= int(g_xr["outside_pool_positive_cells_min"])):
            holdouts.append({
                "held_region": str(prov),
                "held_cells": n_cells,
                "held_positive_cells": n_pos,
                "outside_cells": int(len(outside)),
                "outside_positive_cells":
                    int((outside["any_positive"] == 1).sum())})
    holdouts.sort(key=lambda h: h["held_region"])
    q3 = {
        "requirement": {
            "defensible_holdouts_min":
                int(g_xr["defensible_region_holdouts_min"]),
            "held_region_cells_min":
                int(g_xr["held_region_cells_min"]),
            "held_region_positive_cells_min":
                int(g_xr["held_region_positive_cells_min"]),
            "outside_pool_cells_min":
                int(g_xr["outside_pool_cells_min"]),
            "outside_pool_positive_cells_min":
                int(g_xr["outside_pool_positive_cells_min"])},
        "measured": {"n_defensible_holdouts": len(holdouts),
                     "holdouts": holdouts},
        "meets": len(holdouts) >= int(
            g_xr["defensible_region_holdouts_min"])}

    # Q4 -- single-date phenology confounding: measured multi-date fill.
    s2_block = matrix["s2_multi_date"]
    ge2_per_year = {
        y: int(s2_block[y]["cells_with_ge2_events"])
        for y in ("2020", "2021")}
    full3_per_year = {
        y: int(s2_block[y]["cells_with_3_events_full_tertile_spread"])
        for y in ("2020", "2021")}
    cell_years_total = int(len(landed)) * 2
    cy_multi = sum(
        1 for _, r in landed.iterrows()
        for y in ("s2_landed_2020", "s2_landed_2021") if int(r[y]) >= 2)
    q4 = {
        "design": "one gate-passing event per predeclared tertile "
                  "(EARLY DOY260-279 / MID 280-299 / LATE 300-320) per "
                  "cell-year; no cross-tertile borrowing",
        "measured": {
            "s2_events_landed":
                int(landed["s2_landed_2020"].sum()
                    + landed["s2_landed_2021"].sum()),
            "cell_years_with_ge2_landed_s2": cy_multi,
            "cell_years_total": cell_years_total,
            "fraction_cell_years_multi_date":
                round(cy_multi / cell_years_total, 4),
            "cells_ge2_events_by_year": ge2_per_year,
            "cells_full_tertile_spread_by_year": full3_per_year,
            "tertile_fill": {
                y: s2_block[y]["tertile_slots_filled"]
                for y in ("2020", "2021")}},
        "answer": "materially_reduced_by_design_and_measurement"
        if cy_multi / cell_years_total >= 0.5 else "not_materially_reduced"}

    # Q5 -- near-synchronous <=7 d pairs (landed S1 products).
    s1_pairs_block: dict[str, Any] = matrix["s1_s2_pairs"]
    ledger_pairs = pd.read_csv(V02_DIR / "v02_s1_pairing_ledger.csv")
    primary = ledger_pairs[
        ledger_pairs["status"] == A.STATUS_PAIRED]
    landed_pair_rows = int(sum(
        landed[f"pairs_landed_{y}"].sum() for y in (2020, 2021)))
    pos_ids = set(landed.loc[landed["any_positive"] == 1, "cell_id"])
    paired_cells = set(primary["cell_id"]) & set(landed["cell_id"])
    q5 = {
        "requirement": {
            "paired_cells_min": int(g_ns["paired_cells_min"]),
            "paired_positive_cells_min":
                int(g_ns["paired_positive_cells_min"]),
            "gap_days_max": int(g_ns["primary_pairing_gap_days_max"])},
        "measured": {
            "primary_pairs_lte7d_planned":
                int((primary["status"] == A.STATUS_PAIRED).sum()),
            "primary_pairs_landed": landed_pair_rows,
            "paired_cells": int(len(paired_cells)),
            "paired_positive_cells":
                int(len(paired_cells & pos_ids)),
            "same_day_gap0_pairs": int((primary["gap_days"] == 0).sum()),
            "gap_histogram": {
                str(k): int(v)
                for k, v in primary["gap_days"].value_counts().sort_index()
                .items()},
            "sensitivity_tier_only_events":
                int(s1_pairs_block["sensitivity_tier_only_events"])},
    }
    q5["meets"] = (
        q5["measured"]["paired_cells"] >= q5["requirement"]["paired_cells_min"]
        and q5["measured"]["paired_positive_cells"]
        >= q5["requirement"]["paired_positive_cells_min"]
        and q5["measured"]["primary_pairs_landed"]
        == q5["measured"]["primary_pairs_lte7d_planned"])

    # Q6 -- fresh untouched reserve.
    reserve_members = reserve["members"]
    reserve_ids = {str(m["cell_id"]) for m in reserve_members}
    reserve_n = int(reserve["n_cells"])
    assert len(reserve_ids) == reserve_n
    old_stage1_cells = set(
        matrix["old_stage1_cells"]["cells"])
    stage1_overlap = reserve_ids & old_stage1_cells
    q6 = {
        "note": "Reserve is drawn FROM the new panel pool (24/24 cells are "
                "in the exported panel). The exported Panel bytes go "
                "into the Phase H accepted denominator; the reserve is "
                "SEALED from training/tuning/role assignment until the "
                "future v0.2 protocol freezes final train/val/test.",
        "measured": {
            "fresh_reserve_cells": reserve_n,
            "model_output_influence":
                bool(reserve["model_output_influence"]),
            "final_roles_assigned_now":
                bool(req["fresh_test_reserve"]["final_roles_assigned_now"]),
            "stage1_cell_overlap": int(len(stage1_overlap)),
            "export_status_reserve_cells_landed":
                int(len(reserve_ids & set(landed["cell_id"])))},
        "meets": (
            reserve_n > 0
            and not stage1_overlap
            and not req["fresh_test_reserve"]["final_roles_assigned_now"]
            and not reserve["model_output_influence"])}

    # Q7 -- GOLD candidate support (CANDIDATE_ONLY only; GOLD stays 0).
    by_type_ct: dict[str, int] = {}
    for cand in gold["candidates"]:
        types = cand["candidate_types"]
        for t in (types if isinstance(types, list) else [types]):
            by_type_ct[str(t)] = by_type_ct.get(str(t), 0) + 1
    by_type = dict(sorted(by_type_ct.items()))
    q7 = {
        "measured": {
            "candidate_sites": int(gold["n_candidates"]),
            "by_type": by_type,
            "gold_status": "CANDIDATE_ONLY",
            "promoted_gold_labels": 0},
        "meets": int(gold["n_candidates"]) > 0}

    qa_pass = qa.get("verdict") in ("QA_PASS", "QA_PASS_WITH_HONEST_SOURCE_REJECTIONS")
    threshold_gates = {
        "qa_pass": qa_pass,
        "q1_geodata_temporal": bool(q1["meets"]),
        "q2_cmsa_temporal": bool(q2["meets"]),
        "q3_cross_region_holdouts": bool(q3["meets"]),
        "q5_near_synchronous_pairs": bool(q5["meets"]),
        "q6_fresh_reserve": bool(q6["meets"]),
        "q7_gold_candidates": bool(q7["meets"])}
    verdict = READY if all(threshold_gates.values()) else NOT_READY

    doc: dict[str, Any] = {
        "product": "V0_2_READINESS_DECISION",
        "issue": 21,
        "phase": "L",
        "generated_utc": datetime.now(UTC).isoformat(),
        "git_commit": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, check=True,
            capture_output=True, text=True).stdout.strip(),
        "bound_checksums": {
            "requirements": req["document_checksum"],
            "export_qa": qa["document_checksum"],
            "support_matrix": matrix["document_checksum"],
            "per_cell_csv": matrix["per_cell_csv_sha256"],
            "fresh_reserve": reserve["document_checksum"],
            "gold_candidate_registry": gold["document_checksum"]},
        "scope": {
            "new_panel_cells": int(matrix["cell_roles"]["new_panel_cells"]),
            "fresh_reserve_cells":
                int(matrix["cell_roles"]["fresh_reserve_cells"]),
            "old_stage1_cells":
                int(matrix["cell_roles"]["old_stage1_cells"]),
            "products_landed":
                int(matrix["landed_totals"]["products_landed"]),
            "landed_bytes": int(matrix["landed_totals"]["landed_bytes"]),
            "open_failures": int(matrix["landed_totals"]["open_failures"])},
        "answers": {
            "q1_geodata_temporal": q1,
            "q2_cmsa_temporal": q2,
            "q3_cross_region_holdouts": q3,
            "q4_phenology_confounding": q4,
            "q5_near_synchronous_pairs": q5,
            "q6_fresh_untouched_reserve": q6,
            "q7_gold_candidate_support": q7},
        "gates": threshold_gates,
        "verdict": verdict,
        "interpretation": (
            "Support readiness only. No model has been trained on v0.2; "
            "this verdict authorises no training and makes no accuracy "
            "claim. The v0.1 Stage-1 results remain a support/"
            "instrumentation diagnostic. Final train/val/test roles and "
            "any benchmark run remain a separate frozen-protocol owner "
            "decision." if verdict == READY else
            "At least one frozen support goal is not met on landed "
            "evidence; deficits are reported above honestly and no "
            "threshold was relaxed."),
        "scientific_framing":
            req["scientific_interpretation"]["stage1_statement"]}
    doc["document_checksum"] = A.document_checksum(doc)

    if OUT_JSON.exists():
        old = json.loads(OUT_JSON.read_text("utf-8"))
        if old.get("document_checksum") != doc["document_checksum"]:
            raise SystemExit(
                "REFUSING TO MUTATE FROZEN READINESS DECISION: existing "
                "document differs")
        print("readiness decision already frozen and identical")
    else:
        OUT_JSON.write_text(
            json.dumps(doc, indent=2, ensure_ascii=False, default=str)
            + "\n", encoding="utf-8")
        print(f"wrote {OUT_JSON.name}")
    print(json.dumps({"verdict": verdict, "gates": threshold_gates},
                     indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
