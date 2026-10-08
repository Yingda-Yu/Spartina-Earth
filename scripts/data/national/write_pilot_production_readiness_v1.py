#!/usr/bin/env python3
"""Issue #19 Phase N/O -- national production recommendation and the
Issue #20 readiness checklist (evidence summary, decision artifact).

This script launches nothing and changes no registry value. It joins the
frozen Issue #19 artifacts (panel, event plan, label supports, Issue #18
bridge, SILVER policy recommendation, split-prep fields, Phase M storage
study) into one owner-facing decision document:

* Phase N  -- explicit GO / NO_GO recommendation for a larger national
              real-pixel production, with the gates that must close first;
* Phase O  -- Issue #20 (SpartinaShift-Silver v0.1) readiness checklist,
              mapping existing artifacts to Issue #20 section A-H and
              listing the decisions that remain owner-only.

Output:
* docs/data/national/PILOT19_PRODUCTION_READINESS_v1.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

MANIFESTS = REPO_ROOT / "datasets/manifests"
DOCS = REPO_ROOT / "docs/data/national"
OUT_JSON = DOCS / "PILOT19_PRODUCTION_READINESS_v1.json"

REFERENCED = [
    MANIFESTS / "china_coastal_cells_v1_1_core_frozen.csv",
    MANIFESTS / "national_first_pixel_panel_v1.csv",
    MANIFESTS / "national_pilot_event_plan_v1.json",
    MANIFESTS / "national_pilot19_label_supports_v1.json",
    MANIFESTS / "national_pilot19_issue18_bridge_v1.json",
    MANIFESTS / "national_pilot19_split_prep_v1.json",
    MANIFESTS / "national_pilot19_storage_study_v1.json",
    DOCS / "PILOT_SILVER_TRAINING_POLICY_v1.json",
    DOCS / "FIRST_PIXEL_PILOT_DESIGN_v0.json",
]


def _git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, check=True,
            capture_output=True, text=True)
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNKNOWN"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def gate(
    gate_id: str, title: str, status: str, evidence: str,
    closer: str,
) -> dict[str, str]:
    return {
        "gate_id": gate_id, "title": title, "status": status,
        "evidence": evidence, "how_to_close": closer}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-json", default=str(OUT_JSON))
    args = parser.parse_args()

    missing = [str(p) for p in REFERENCED if not p.exists()]
    if missing:
        raise SystemExit(f"missing referenced artifacts: {missing}")

    study = json.loads(
        (MANIFESTS / "national_pilot19_storage_study_v1.json")
        .read_text(encoding="utf-8"))
    policy = json.loads(
        (DOCS / "PILOT_SILVER_TRAINING_POLICY_v1.json")
        .read_text(encoding="utf-8"))
    plan = json.loads(
        (MANIFESTS / "national_pilot_event_plan_v1.json")
        .read_text(encoding="utf-8"))

    minimal = study["national_minimal_scenario"]
    standard = study["national_standard_scenario"]
    pilot = study["pilot_scenario"]
    auth = study["gee_auth_probe"]

    # -- Phase N gates -----------------------------------------------------
    n_gates = [
        gate(
            "N1_GEE_PROJECT_AND_AUTH", "GEE project + re-authentication",
            "BLOCKED",
            f"probe: project_set={auth['spartina_gee_project_set']}, "
            f"earthengine_ls_users_ok={auth['earthengine_ls_users_ok']}; "
            "Phase D/E has been blocked since Issue #19 start",
            "owner sets SPARTINA_GEE_PROJECT and runs "
            "`earthengine authenticate`; rerun probe"),
        gate(
            "N2_PILOT_PIXEL_EXPORT",
            "Land all 194 planned pilot products (83 Landsat / 42 S2 / "
            "69 S1) on per-cell native UTM grids",
            "NOT_RUN",
            "event plan frozen at 194 SELECTED / 280 rows; zero pixels "
            "exported; M2.1b proved the pipeline on Zhejiang cells",
            "execute the Phase D/E driver after N1; per-product manifest "
            "and SHA-256 for every landed file"),
        gate(
            "N3_PHASE_H_QA_GATES",
            "Quicklooks, coastline/grid and label/pixel alignment, "
            "physical ranges, valid fractions, duplicate/cross-date "
            "detection; near-full geometric gate >=0.95",
            "NOT_RUN",
            "selection policy flags 7 near-full Landsat pilot products "
            "with the post-export geometric gate; label/label bridge "
            "already matches frozen Issue #18 panel totals within 0.12% "
            "(see bridge manifest)",
            "run the Phase H QA pack on the 194 products; any systematic "
            "misregistration is a STOP condition"),
        gate(
            "N4_L5_L7_BYTE_RATIO",
            "Replace borrowed L5/L7 float32 LZW ratio with measured bytes",
            "ESTIMATE_OPEN",
            "M2.1b exported only L8/L9, S1, S2; L5/L7 SR ratio is "
            "borrowed from L8 and flagged in the storage study",
            "measure real L5/L7 bundles during the pilot export and "
            "rebuild the storage study"),
        gate(
            "N5_DRIVE_QUOTA_VERIFICATION",
            "Verify live-project GEE concurrent-task and Drive download "
            "behaviour at the minimal-run scale",
            "TODO_VERIFY",
            "M2.1b observed backend minutes per <=10 km tile but the end "
            "to end is polling/Drive bound; official quotas unverified",
            "stair-step pilot concurrency and record observed throughput "
            "before the national run"),
        gate(
            "N6_DEDUP_BATCH_DESIGN",
            "Decide per-cell clips vs one export per shared source event",
            "DECISION_REQUIRED",
            "pilot 194 products derive from 135 distinct source events "
            "(S1 1.60 products/event, S2 1.56); per-cell export repeats "
            "shared scenes",
            "owner/engineering decision for Issue #20 production: event-"
            "union bbox export + local windowing, or accept per-cell "
            "redundancy"),
        gate(
            "N7_NATIONAL_LABEL_SUPPORTS",
            "Regenerate the label-adapter supports for all production "
            "cells on the same grids",
            "READY_TO_RUN",
            "adapter proven on the 20 pilot cells (220 supports, 0.0% "
            "repair area change, STOP guards built in)",
            "run build_pilot_label_supports_v1 logic over the production "
            "cell list; source archives stay read-only"),
        gate(
            "N8_SCOPE_AND_STORAGE",
            "Storage provisioning for the chosen national scenario",
            "QUANTIFIED_ESTIMATE",
            f"minimal anchors: {minimal['n_gee_tasks']} GEE tasks, "
            f"{minimal['bytes_base']/1e9:.1f} GB EO (base estimate; "
            f"range {minimal['bytes_low']/1e9:.1f}-"
            f"{minimal['bytes_high']/1e9:.1f} GB); standard core and "
            "pilot 194-product projections are tabulated in the storage "
            "study",
            "owner picks minimal vs standard scope and provisions "
            "staging/archive storage"),
    ]

    recommendation = {
        "decision": "NO_GO_FOR_NATIONAL_BATCH_NOW",
        "conditional": (
            "CONDITIONAL_GO after gates N1-N6 close and N7/N8 are actioned; "
            "the decision remains owner-only and no national export, "
            "training, split creation or SpartinaFM work may start from "
            "this document"),
        "rationale": [
            "zero of the 194 planned pilot products have landed (GEE "
            "authentication is the hard blocker); Issue #19 acceptance "
            "question 1 cannot be answered from pixels yet",
            "the label/label bridge (independent lattice) matches frozen "
            "Issue #18 panel totals within 0.12% and no STOP condition "
            "has fired in label adaptation",
            "the export pipeline itself is proven on real Zhejiang pixels "
            "(M2.1b: 27 products, per-product manifests, checksums)",
            "minimal-national scale is quantified from exact metadata "
            "counts and measured bytes, so provisioning and scheduling "
            "can be planned without launching anything"],
        "gates": n_gates,
        "scale_evidence": {
            "pilot_selected_products": pilot["n_products"],
            "minimal_national": {
                "n_products": minimal["n_products"],
                "n_gee_tasks": minimal["n_gee_tasks"],
                "eo_bytes_base_gb": round(minimal["bytes_base"] / 1e9, 2),
                "eo_bytes_low_gb": round(minimal["bytes_low"] / 1e9, 2),
                "eo_bytes_high_gb": round(minimal["bytes_high"] / 1e9, 2)},
            "standard_national_core": {
                "n_products": standard["core_series"]["n_products"],
                "n_gee_tasks": standard["core_series"]["n_gee_tasks"],
                "eo_bytes_base_gb": round(
                    standard["core_series"]["bytes_base"] / 1e9, 2)},
            "standard_national_plus_l9": {
                "n_products": standard["core_plus_l9"]["n_products"],
                "eo_bytes_base_gb": round(
                    standard["core_plus_l9"]["bytes_base"] / 1e9, 2)},
            "label_supports_one_time_estimate_bytes":
                study["label_supports_national_projection"][
                    "national_bytes_estimate"],
            "estimate_tokens": list(study["estimate_tokens"].keys())},
    }

    # -- Phase O: Issue #20 readiness -------------------------------------
    issue20 = {
        "issue": "20 (M2.6 SpartinaShift-Silver v0.1)",
        "section_mapping": [
            {"issue20_section": "A freeze benchmark protocol",
             "status": "INPUTS_READY_SPLIT_NOT_CREATED",
             "note": "split-prep fields, grouping unit W10_CELL, 250 m "
                     "buffer, witness-holdout recommendation frozen; "
                     "no split exists (forbidden in Issue #19)"},
            {"issue20_section": "B benchmark tasks 1-6",
             "status": "BLOCKED_ON_PIXELS",
             "note": "named SILVER supports and policy exist; task "
                     "definition is possible now, execution waits for "
                     "Phase D/E pixels and owner SILVER activation"},
            {"issue20_section": "C baseline ladder",
             "status": "NOT_STARTED_BY_DESIGN",
             "note": "no training of any kind in Issue #19"},
            {"issue20_section": "D metrics",
             "status": "PARTIALLY_SPECIFIED",
             "note": "fractional supports distinguish PURE/MIXED and "
                     "carry per-pixel fractions; area/agreement metrics "
                     "prototype in the Issue #18 bridge; calibration and "
                     "boundary metrics remain to be implemented"},
            {"issue20_section": "E 2020 protection",
             "status": "DESIGN_INPUT_READY",
             "note": "2020 triad anchors; split-prep marks "
                     "PILOT_WITNESS_HOLDOUT_CANDIDATE; the held-out 2020 "
                     "set must be pre-registered in Issue #20"},
            {"issue20_section": "F GoldSet separation",
             "status": "ENFORCEABLE_NOW",
             "note": "GOLD count is 0; SILVER policy gate G2 isolates "
                     "future Gold sites from training/HPO/thresholds"},
            {"issue20_section": "G model escalation gate",
             "status": "NOT_REACHED",
             "note": "no SpartinaFM work; baselines must identify the "
                     "gap first"},
            {"issue20_section": "H paper outputs",
             "status": "PILOT_EVIDENCE_ONLY",
             "note": "only verified pilot/metadata evidence may be "
                     "written; national claims and benchmark numbers "
                     "stay TODO_EXPERIMENT"}],
        "ready_artifacts": [
            "W10_DOMAIN_V1_CORE_FROZEN: 3,016 KEEP cells",
            "frozen 20-cell panel + predeclared selection policy",
            "194-product event plan with honest absence states",
            "220 fractional label supports + adapter manifest",
            "Issue #18 independent-lattice bridge (within 0.12%)",
            "SILVER training policy recommendation (not in force)",
            "split-prep fields (no split created)",
            "Phase M storage/scale study with measured byte factors",
            "M2.1b proven GEE export/download/resume pipeline",
            "spartina.evaluation.splits.assert_spatially_disjoint"],
        "owner_decisions_required_before_issue20": [
            "activate or revise the SILVER training policy "
            f"(current status: {policy.get('status')})",
            "confirm external-label license classes for redistribution "
            "and training (G5 in the SILVER policy)",
            "choose national scope and dedup batching (gates N6/N8)",
            "pre-register the 2020 held-out external-reference set",
            "approve the split protocol (regions, buffers, val policy)"],
        "hard_constraints": [
            "GOLD stays 0 pending Issue #11 evidence",
            "cross-source agreement is reference transfer, not accuracy",
            "train/val/test spatially disjoint; test never tunes",
            "no fabricated results; TODO_EXPERIMENT/TODO_VERIFY stand"],
        "plan_status_summary": {
            "n_plan_rows": plan["n_plan_rows"],
            "n_selected": plan["n_selected"],
            "state": plan["status"]},
    }

    doc = {
        "product": "national_pilot19_production_readiness_v1",
        "issue": 19,
        "phases": ["N", "O"],
        "generated_utc": datetime.now(UTC).isoformat(),
        "git_commit": _git_commit(),
        "status": (
            "RECOMMENDATION_ONLY; launches nothing; changes no registry "
            "or policy value; owner decision required"),
        "phase_n_recommendation": recommendation,
        "phase_o_issue20_readiness": issue20,
        "issue19_acceptance_answers": {
            "Q1_reproducible_national_examples": (
                "PARTIAL: pipeline proven on M2.1b real pixels; pilot "
                "national cells not exported (N1/N2)"),
            "Q2_labels_aligned_enough_for_benchmark": (
                "PARTIAL: label-vs-label independent lattices agree "
                "within 0.12% panel area; EO-vs-label alignment awaits "
                "Phase H pixels"),
            "Q3_what_must_change_before_national_batch": (
                "see gates N1-N8; decision recorded as conditional"),
            "Q4_silver_eligible_vs_reference_only": (
                "RECOMMENDED_NOT_IN_FORCE: tier/gate framework emitted; "
                "owner activation pending; GOLD = 0")},
        "referenced_artifacts": [
            {"path": str(p.relative_to(REPO_ROOT)),
             "sha256": _sha256(p)} for p in REFERENCED],
    }

    out = Path(args.out_json)
    out.write_text(
        json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({
        "decision": recommendation["decision"],
        "gates": {g["gate_id"]: g["status"] for g in n_gates},
        "out": str(out)}, indent=2))


if __name__ == "__main__":
    main()
