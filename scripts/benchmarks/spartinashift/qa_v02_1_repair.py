#!/usr/bin/env python3
"""Issue #21 Phase 2A Step 4 -- QA for the Option A repair export.

Reuses the frozen Phase J QA machinery (qa_v02_export.py) unmodified,
redirected to the repair namespace: expected rows rebuilt from
LIVE_GEE_REPAIR_PLAN.json (Landsat-only), manifests from
work/issue21/export_repair/manifests, QA outputs under
work/issue21/qa_repair/ and
benchmarks/spartinashift/v0_2_1_repair/REPAIR_QA_REPORT.json.
No frozen v0_2 artifact is modified; no threshold changed.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts/data/national"))

REPAIR_DIR = REPO_ROOT / "benchmarks/spartinashift/v0_2_1_repair"
EXPORT_REPAIR = REPO_ROOT / "work/issue21/export_repair"


def _load(name: str, rel: str) -> Any:
    spec = importlib.util.spec_from_file_location(
        name, REPO_ROOT / rel)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    E = _load("export_v02_products_mod",
              "scripts/benchmarks/spartinashift/export_v02_products.py")
    Q = _load("qa_v02_export_mod",
              "scripts/benchmarks/spartinashift/qa_v02_export.py")

    # Repair namespace redirection (before any QA call).
    Q.MANIFEST_DIR = EXPORT_REPAIR / "manifests"
    Q.FAILURES_JSON = EXPORT_REPAIR / "failures.json"
    Q.QA_DIR = REPO_ROOT / "work/issue21/qa_repair"
    Q.OUT_JSON = REPAIR_DIR / "REPAIR_QA_REPORT.json"
    Q.EXPORT_DIR = EXPORT_REPAIR
    if hasattr(Q, "PRODUCT_DIR"):
        Q.PRODUCT_DIR = EXPORT_REPAIR / "products"

    plan = json.loads((REPAIR_DIR / "LIVE_GEE_REPAIR_PLAN.json")
                      .read_text("utf-8"))
    scope = json.loads((REPAIR_DIR / "V0_2_1_REPAIR_SCOPE_ESTIMATE.json")
                       .read_text("utf-8"))
    X = _load("export_v02_1_repair_mod",
              "scripts/benchmarks/spartinashift/export_v02_1_repair.py")
    expected_rows = X.build_rows(plan, E)
    expected = {str(r["product_id"]): r for r in expected_rows}

    manifest_paths = sorted(Q.MANIFEST_DIR.glob("*.json"))
    manifests = [json.loads(p.read_text("utf-8")) for p in manifest_paths]
    by_pid = {str(m["product_id"]): m for m in manifests}
    unexpected = sorted(set(by_pid) - set(expected))

    results: list[dict[str, Any]] = []
    missing: list[str] = []
    for pid in sorted(expected):
        if pid not in by_pid:
            missing.append(pid)
            continue
        results.append(Q.verify_product(by_pid[pid]))
    failures = [f for f in json.loads(
        Q.FAILURES_JSON.read_text("utf-8")).get("failures", [])
        if not f.get("superseded")]

    failed_checks = {r["product_id"]: r["errors"]
                     for r in results if r["errors"]}
    honest_rejections = {r["product_id"]: r["rejection_reason"]
                         for r in results if r["rejection_reason"]}
    by_sensor: dict[str, Any] = {}
    for sensor in Q.SENSORS:
        vals = [r for r in results if r["sensor"] == sensor]
        fracs = [float(r["actual_observed_fraction_in_w10_cell"])
                 for r in vals
                 if r["actual_observed_fraction_in_w10_cell"] is not None]
        by_sensor[sensor] = {
            "n_landed": len(vals),
            "n_failed_checks": sum(1 for r in vals if r["errors"]),
            "w10_fraction_min": min(fracs) if fracs else None,
            "w10_fraction_median": Q._median(fracs),
            "n_below_gate": sum(1 for v in fracs
                                if v < E.A.ACTUAL_MASK_GATE)}

    # Gate-support recomputation on landed + QA-passed products.
    cand = pd.read_csv(REPAIR_DIR / "v0_2_1_repair_candidate_table.csv")
    pos_ids = set(cand.loc[cand["role"] == "GEODATA_POSITIVE_REPAIR",
                           "cell_id"])
    qa_ok_cells = {r["cell_id"] for r in results
                   if not r["errors"] and not r["rejection_reason"]}
    all_ok_cells = {r["cell_id"] for r in results if not r["errors"]}
    per_cell_year: dict[tuple[str, int], int] = {}
    for r in results:
        if r["errors"] or r["rejection_reason"]:
            continue
        key = (r["cell_id"], int(r["year"]))
        per_cell_year[key] = per_cell_year.get(key, 0) + 1
    by_cell: dict[str, dict[int, int]] = {}
    for (cid, yr), n in per_cell_year.items():
        by_cell.setdefault(cid, {})[yr] = n

    def both_years(cid: str) -> bool:
        d = by_cell.get(cid, {})
        return d.get(2015, 0) > 0 and d.get(2020, 0) > 0

    repair_pos = sorted(c for c in by_cell
                        if c in pos_ids and both_years(c))
    repair_bg = sorted(c for c in by_cell
                       if c not in pos_ids and both_years(c))
    alignment = {
        "note": "repair-only counts; final readiness gate adds these to "
                "the frozen v0.2 measured support (11 positives / "
                "11 backgrounds / 5 regions)",
        "repair_positive_cells_both_years_qa_passed": repair_pos,
        "repair_background_cells_both_years_qa_passed": repair_bg,
        "qa_strict_cells_landed": len(qa_ok_cells),
        "qa_error_cells_landed": len(all_ok_cells - qa_ok_cells),
        "honest_rejection_cells": sorted(
            {r["cell_id"] for r in results if r["rejection_reason"]})}

    fig_paths = Q.figures(results) if results else {}
    sheet_paths: dict[str, str] = {}
    if results:
        sheet_paths = Q.contact_sheets(manifests)
    figure_hashes = {
        name: {"path": path, "sha256": Q._sha(REPO_ROOT / path)}
        for name, path in {**fig_paths, **sheet_paths}.items()}

    systematic_stop = bool(missing or unexpected or failed_checks
                           or failures)
    honest_only = bool(honest_rejections) and not systematic_stop
    verdict = ("QA_FAIL_SYSTEMATIC_STOP" if systematic_stop else
               "QA_PASS_WITH_HONEST_SOURCE_REJECTIONS" if honest_only
               else "QA_PASS")
    doc: dict[str, Any] = {
        "product": "V0_2_1_REPAIR_EXPORT_QA_SUMMARY",
        "issue": 21,
        "phase": "2A_STEP4",
        "qa_contracts": [
            "landed sha256", "locked transform/dimensions/CRS rebuild",
            "actual-mask 0.95 gate replay (grid + W10 cell)",
            "physical scaling/band order/QA semantics",
            "no all-NaN/all-zero informative raster",
            "manifest-vs-file consistency"],
        "plan_checksums": {
            "landsat_plan": plan["document_checksum"],
            "scope_estimate": scope["document_checksum"]},
        "verdict": verdict,
        "scope_products_expected": len(expected),
        "products_landed": len(results),
        "products_missing_manifest": missing,
        "unexpected_manifests": unexpected,
        "open_export_failures": failures,
        "products_failing_checks": failed_checks,
        "honest_source_rejections": honest_rejections,
        "honest_rejection_policy": Q._verified.__doc__
        and "Issue #19 class: byte-faithful export with QA_PIXEL surface "
            "mask zero over the cell; counted out of the accepted "
            "denominator; not a systematic failure",
        "by_sensor": by_sensor,
        "gate_support_alignment": alignment,
        "figures": figure_hashes,
        "generated_utc": __import__("datetime").datetime.now(
            __import__("datetime").UTC).isoformat(),
        "git_commit": __import__("subprocess").run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True,
            text=True).stdout.strip()}
    doc["document_checksum"] = E.A.document_checksum(doc)
    Q.OUT_JSON.write_text(
        json.dumps(doc, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8")
    print(json.dumps({
        "verdict": verdict, "landed": len(results),
        "expected": len(expected), "missing": len(missing),
        "failing": len(failed_checks), "open_failures": len(failures),
        "by_sensor": by_sensor, "gate_support_alignment": alignment},
        indent=2, default=str))
    return 0 if verdict == "QA_PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
