#!/usr/bin/env python3
"""Issue #21 Phase 2A -- Owner-approved Option A repair export (Landsat-only).

Exports ONLY the eligible Landsat observations frozen in
benchmarks/spartinashift/v0_2_1_repair/LIVE_GEE_REPAIR_PLAN.json for the
14 GEODATA repair candidates. No frozen v0_2 artifact is read for export
scope beyond checksum verification, none is modified, and no v0_2 export
task is touched: all paths, Drive folder, task prefix, task store and
progress documents are redirected to the repair namespace
(work/issue21/export_repair/, product ids V021_..., revision
V0_2_1_REPAIR).

Hard gates before any submission:
  * LIVE_GEE_REPAIR_PLAN.json checksum verified
  * V0_2_1_REPAIR_SCOPE_ESTIMATE.json checksum verified, verdict
    WITHIN_CAPS, plan products == option_A planned observations,
    3*products <= option_A projected tasks, landed bytes <= option_A cap
  * SPARTINA_V02_EXPORT=1 (operator opt-in) + SPARTINA_GEE_PROJECT

Real runs: --canary first (1 deterministic Landsat product), then full.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts/data/national"))

from spartina.data.gee.auth import configured_project, initialize  # noqa: E402
from spartina.data.national.pilot_panel import coastal_segment  # noqa: E402,F401
from spartina.data.national import pilot_panel  # noqa: E402

REPAIR_DIR = REPO_ROOT / "benchmarks/spartinashift/v0_2_1_repair"
PLAN_JSON = REPAIR_DIR / "LIVE_GEE_REPAIR_PLAN.json"
SCOPE_JSON = REPAIR_DIR / "V0_2_1_REPAIR_SCOPE_ESTIMATE.json"
REGISTRY_CSV = (REPO_ROOT / "datasets/manifests"
                / "china_coastal_cells_v1_1_core_frozen.csv")


def _load_module(name: str, rel_path: str) -> Any:
    path = REPO_ROOT / rel_path
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _verify(doc_path: Path) -> dict[str, Any]:
    E = _load_module("export_v02_products_mod",
                     "scripts/benchmarks/spartinashift/"
                     "export_v02_products.py")
    doc = json.loads(doc_path.read_text("utf-8"))
    if E.A.document_checksum(doc) != str(doc.get("document_checksum")):
        raise SystemExit(f"artifact checksum mismatch: {doc_path.name}")
    return doc, E  # type: ignore[return-value]


def build_rows(doc: dict[str, Any], E: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for slot in doc["slots"]:
        if slot["status"] != E.A.STATUS_ELIGIBLE:
            continue
        sensor = str(slot["sensor"])
        tag = E._TERTILE_TAG[slot["tertile"]]
        pid = (f"V021_{E._short(slot['cell_id'])}_"
               f"{E._SENSOR_TAG[sensor]}_{slot['year']}_{tag}")
        rows.append({
            "product_id": pid,
            "cell_id": slot["cell_id"],
            "sensor": sensor,
            "year": int(slot["year"]),
            "priority": "V0_2_1_GEODATA_REPAIR",
            "variant": f"V02_{slot['tertile']}_TERTILE",
            "status": E.A.STATUS_ELIGIBLE,
            "v2_change": "V0_2_1_REPAIR",
            "event_id": slot["event_id"],
            "event_utc": slot["event_utc"],
            "doy": int(slot["doy"]),
            "season_tag": f"V02_{slot['tertile']}_TERTILE_AUTUMN",
            "cloud_fraction": float(slot["cloud_fraction"]),
            "scene_ids": slot["scene_id"],
            "product_ids_source": slot.get("source_product_id"),
            "wrs_path": slot.get("wrs_path"),
            "wrs_row": slot.get("wrs_row"),
            "member_scene_count": 1,
            "l7_era": slot.get("l7_era") or None,
            "v2_actual_observed_fraction": float(
                slot["actual_observed_fraction"]),
            "v2_evidence_source": slot["evidence_source"],
            "v02_tertile": slot["tertile"]})
    rows.sort(key=lambda r: str(r["product_id"]))
    return rows


def canary_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    landsat = sorted(rows, key=lambda r: str(r["product_id"]))
    if not landsat:
        raise SystemExit("canary needs at least one Landsat product")
    return [landsat[0]]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canary", action="store_true")
    parser.add_argument("--products", default="",
                        help="comma-separated product_id allowlist")
    parser.add_argument("--concurrency", type=int, default=7)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    plan_doc, E = _verify(PLAN_JSON)
    scope_doc, _ = _verify(SCOPE_JSON)
    if scope_doc["verdict"] != "WITHIN_CAPS_OWNER_DECISION_REQUIRED_BEFORE_EXPORT":
        raise SystemExit(f"scope verdict is {scope_doc['verdict']}")
    if not scope_doc.get("owner_authorization"):
        raise SystemExit("scope doc lacks owner_authorization flag")

    rows = build_rows(plan_doc, E)
    n_tasks = 3 * len(rows)  # landsat component tasks per product
    opt = scope_doc["option_A_landsat_only"]
    cap_tasks = int(opt["projected_gee_component_tasks"])
    cap_bytes = int(opt["projected_landed_eo_bytes"])
    if len(rows) != int(opt["planned_landsat_observations_max"]):
        raise SystemExit(f"plan/estimate disagree: rows={len(rows)} "
                         f"planned={opt['planned_landsat_observations_max']}")
    if n_tasks > cap_tasks or cap_bytes > E.S.MAX_LANDED_EO_BYTES:
        raise SystemExit("scope estimate exceeds Option A caps")
    print(f"[v021] scope: {len(rows)} products / {n_tasks} GEE tasks "
          f"(cap {cap_tasks} tasks, {cap_bytes / 2**30:.3f} GiB)")

    wanted = {p.strip() for p in args.products.split(",") if p.strip()}
    if wanted:
        missing = wanted - {str(r["product_id"]) for r in rows}
        if missing:
            raise SystemExit(f"--products not eligible: {sorted(missing)}")
        rows = [r for r in rows if str(r["product_id"]) in wanted]
    if args.canary:
        rows = canary_rows(rows)
    if not rows:
        raise SystemExit("empty export scope after filters; abort")

    if args.dry_run:
        print("[v021] dry-run: gates pass; no tasks submitted")
        for r in rows:
            print("  ", r["product_id"], r["event_utc"],
                  r["v2_actual_observed_fraction"])
        return 0
    if os.environ.get("SPARTINA_V02_EXPORT") != "1":
        raise SystemExit("real export needs SPARTINA_V02_EXPORT=1")
    if configured_project() is None:
        raise SystemExit("export SPARTINA_GEE_PROJECT=<project-id> first")

    # Repair namespace: redirect ALL mutable paths before configure_driver.
    E.GDRIVE_FOLDER = "SpartinaEarthV021Repair"
    E.ISSUE_TAG = "#21 Phase 2A GEODATA repair (Option A)"
    E.EXPORT_WORK = REPO_ROOT / "work/issue21/export_repair"
    E.PRODUCT_DIR = E.EXPORT_WORK / "products"
    E.MANIFEST_DIR = E.EXPORT_WORK / "manifests"
    E.TASK_STORE = E.EXPORT_WORK / "tasks/task_store.json"
    E.FAILURES_JSON = E.EXPORT_WORK / "failures.json"
    E.PROGRESS_JSON = E.EXPORT_WORK / "export_progress_v021.json"
    E.INDEX_JSON = E.EXPORT_WORK / "v021_export_index.json"
    E.CANARY_CSV = E.EXPORT_WORK / "v021_canary_allowlist.csv"
    E.V02_REVISION = "V0_2_1_REPAIR"
    E.V02_SELECTION = "V0_2_1_GEODATA_REPAIR_OPTION_A"

    checksums = {
        "landsat_plan": plan_doc["document_checksum"],
        "landsat_plan_csv": plan_doc.get("plan_csv_sha256"),
        "scope_estimate": scope_doc["document_checksum"]}

    p19 = E._load_driver()
    E.configure_driver(p19, checksums)
    scheduler_cls = E._make_scheduler_class(p19)

    initialize()
    import ee

    registry = pd.read_csv(REGISTRY_CSV)[
        ["cell_id", "center_lon", "center_lat"]]
    prov = pd.read_csv(REPAIR_DIR / "v0_2_1_repair_candidate_table.csv")[
        ["cell_id", "province"]]
    panel = registry[registry["cell_id"].isin(plan_doc["cell_ids"])].merge(
        prov, on="cell_id", how="left", validate="1:1")
    panel["region_province"] = panel["province"].fillna("UNKNOWN")
    panel["coastal_segment"] = panel["region_province"].map(
        pilot_panel.coastal_segment)
    panel = panel.drop(columns=["province"]).set_index("cell_id")

    E.PRODUCT_DIR.mkdir(parents=True, exist_ok=True)
    E.MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    E.TASK_STORE.parent.mkdir(parents=True, exist_ok=True)
    if args.canary:
        pd.DataFrame({"product_id": [r["product_id"] for r in rows]}
                     ).to_csv(E.CANARY_CSV, index=False)

    store = p19.TaskStore(E.TASK_STORE)
    scheduler = scheduler_cls(
        ee, store, panel, checksums, concurrency=args.concurrency,
        hard_stop_on_failure=args.canary)
    scheduler.run(rows)
    E.write_index(scheduler, rows, checksums)
    open_failures = [f for f in scheduler.failures if not f.get("superseded")]
    print(f"[v021] landed={len(scheduler.landed_pids)} "
          f"open_failures={len(open_failures)} "
          f"bytes={scheduler.total_landed_bytes}", flush=True)
    if scheduler.stop:
        print("CANARY_FAIL: canary hard stop; no further tasks submitted",
              flush=True)
        return 2
    if open_failures:
        print("EXPORT_FAILURES_PRESENT: review required", flush=True)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
