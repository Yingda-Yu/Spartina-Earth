#!/usr/bin/env python3
"""Issue #21, Phase H -- export the frozen v0.2 support expansion.

This is the ONLY export authorized by Issue #21: the products frozen in
V0_2_S2_ACQUISITION_PLAN / V0_2_LANDSAT_ACQUISITION_PLAN /
V0_2_S1_PAIRING_LEDGER, executed through the Issue #19 V2 production
contracts (same image builders, grids, bundle validation, actual-mask
gate replay, task store, Drive landing). Nothing is forked: the pilot19
driver module is imported and redirected at module boundaries

* Drive folder      SpartinaEarthV02Issue21 (not SpartinaEarthPilot19)
* work dir          work/issue21/export (products/manifests/tasks/...)
* task prefixes     spartina_v02_* (never collide with pilot19 names)
* volume cap        the Issue #21 hard cap (40 GiB), not the 4 GiB pilot
* manifest tag      Issue #21 / SpartinaShift v0.2 provenance block

Hard gates before any task is submitted:
  1. the three frozen plans verify against their embedded checksums;
  2. V0_2_EXPORT_SCOPE_ESTIMATE exists, is intact, and its verdict is
     WITHIN_CAP_PROCEED_PHASE_H_EXPORT;
  3. the scope built from the plans exactly equals the frozen scope
     counts (products and GEE component tasks).

A canary set (one S2 event, its <= 7 d S1 pair when present, one
Landsat observation) must land and validate first; canary failure hard-
stops before any further task. Real runs require SPARTINA_V02_EXPORT=1.
``--dry-run`` only assembles and cross-checks the local scope.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts/data/national"))

from spartina.benchmark.v02 import acquisition as A  # noqa: E402
from spartina.benchmark.v02 import scope as S  # noqa: E402
from spartina.data.gee.auth import configured_project, initialize  # noqa: E402

V02_DIR = REPO_ROOT / "benchmarks/spartinashift/v0_2"
S2_JSON = V02_DIR / "V0_2_S2_ACQUISITION_PLAN.json"
L_JSON = V02_DIR / "V0_2_LANDSAT_ACQUISITION_PLAN.json"
G_JSON = V02_DIR / "V0_2_S1_PAIRING_LEDGER.json"
SCOPE_JSON = V02_DIR / "V0_2_EXPORT_SCOPE_ESTIMATE.json"
PANEL_CSV = V02_DIR / "v02_cell_panel.csv"
REGISTRY_CSV = (REPO_ROOT / "datasets/manifests"
                / "china_coastal_cells_v1_1_core_frozen.csv")

EXPORT_WORK = REPO_ROOT / "work/issue21/export"
PRODUCT_DIR = EXPORT_WORK / "products"
MANIFEST_DIR = EXPORT_WORK / "manifests"
TASK_STORE = EXPORT_WORK / "tasks/task_store.json"
FAILURES_JSON = EXPORT_WORK / "failures.json"
PROGRESS_JSON = EXPORT_WORK / "export_progress_v02.json"
INDEX_JSON = EXPORT_WORK / "v02_export_index.json"
CANARY_CSV = EXPORT_WORK / "v02_canary_allowlist.csv"

GDRIVE_FOLDER = "SpartinaEarthV02Issue21"
V02_REVISION = "v02r1"
V02_SELECTION = "SPARTINASHIFT_V0_2_SUPPORT_EXPANSION"
ISSUE_TAG = "#21 M2.7 SpartinaShift v0.2 support expansion"

_TERTILE_TAG = {"EARLY": "E", "MID": "M", "LATE": "L"}
_SENSOR_TAG = {"landsat5": "L5", "landsat7": "L7", "landsat8": "L8"}


def _load_driver() -> Any:
    path = REPO_ROOT / "scripts/data/national/pilot19_export_products.py"
    spec = importlib.util.spec_from_file_location("pilot19_export_products",
                                                  path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["pilot19_export_products"] = mod
    spec.loader.exec_module(mod)
    return mod


def _verify(doc_path: Path) -> dict[str, Any]:
    doc: dict[str, Any] = json.loads(doc_path.read_text("utf-8"))
    expected = str(doc.get("document_checksum"))
    if A.document_checksum(doc) != expected:
        raise SystemExit(f"frozen artifact checksum mismatch: {doc_path.name}")
    return doc


# ---------------------------------------------------------------------------
# frozen plans -> Issue #19 V2 row schema
# ---------------------------------------------------------------------------

def _short(cell_id: str) -> str:
    return cell_id.removeprefix("CNA10K-")


def build_rows(
    s2_doc: dict[str, Any], l_doc: dict[str, Any],
    g_doc: dict[str, Any],
) -> list[dict[str, Any]]:
    """Convert frozen eligible slots/primary pairs into pilot V2 rows."""
    rows: list[dict[str, Any]] = []
    for slot in s2_doc["slots"]:
        if slot["status"] != A.STATUS_ELIGIBLE:
            continue
        tag = _TERTILE_TAG[slot["tertile"]]
        pid = (f"V02_{_short(slot['cell_id'])}_S2_{slot['year']}_{tag}")
        rows.append({
            "product_id": pid,
            "cell_id": slot["cell_id"],
            "sensor": "sentinel2",
            "year": int(slot["year"]),
            "priority": "V02_SUPPORT_EXPANSION",
            "variant": f"V02_{slot['tertile']}_TERTILE",
            "status": A.STATUS_ELIGIBLE,
            "v2_change": V02_SELECTION,
            "event_id": slot["event_id"],
            "event_utc": slot["event_utc"],
            "doy": int(slot["doy"]),
            "season_tag": f"V02_{slot['tertile']}_TERTILE_AUTUMN",
            "cloud_fraction": float(slot["cloud_fraction"]),
            "scene_ids": slot["scene_ids"],
            "product_ids_source": slot.get("product_ids_source"),
            "mgrs_tiles": slot.get("mgrs_tiles"),
            "member_scene_count": int(slot["member_scene_count"]),
            "platform": slot.get("platform"),
            "v2_actual_observed_fraction": float(
                slot["actual_observed_fraction"]),
            "v2_evidence_source": slot["evidence_source"],
            "v02_tertile": slot["tertile"]})
    for slot in l_doc["slots"]:
        if slot["status"] != A.STATUS_ELIGIBLE:
            continue
        sensor = str(slot["sensor"])
        tag = _TERTILE_TAG[slot["tertile"]]
        pid = (f"V02_{_short(slot['cell_id'])}_"
               f"{_SENSOR_TAG[sensor]}_{slot['year']}_{tag}")
        rows.append({
            "product_id": pid,
            "cell_id": slot["cell_id"],
            "sensor": sensor,
            "year": int(slot["year"]),
            "priority": "V02_SUPPORT_EXPANSION",
            "variant": f"V02_{slot['tertile']}_TERTILE",
            "status": A.STATUS_ELIGIBLE,
            "v2_change": V02_SELECTION,
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
    for rec in g_doc["pairings"]:
        if rec["status"] != A.STATUS_PAIRED:
            continue
        tag = _TERTILE_TAG[rec["tertile"]]
        pid = f"V02_{_short(rec['cell_id'])}_S1_{rec['year']}_{tag}"
        rows.append({
            "product_id": pid,
            "cell_id": rec["cell_id"],
            "sensor": "sentinel1",
            "year": int(rec["year"]),
            "priority": "V02_SUPPORT_EXPANSION",
            "variant": f"V02_{rec['tertile']}_TERTILE_PAIR",
            "status": A.STATUS_PAIRED,
            "v2_change": V02_SELECTION,
            "event_id": rec["s1_event_id"],
            "event_utc": rec["s1_event_utc"],
            "doy": int(rec["s1_doy"]),
            "season_tag": f"V02_{rec['tertile']}_TERTILE_AUTUMN_PAIR",
            "scene_ids": rec["s1_scene_id"],
            "pass": rec["pass"],
            "relative_orbit": rec["relative_orbit"],
            "platform": rec.get("platform"),
            "member_scene_count": 1,
            "v2_actual_observed_fraction": float(
                rec["actual_observed_fraction"]),
            "v2_evidence_source": rec["evidence_source"],
            "v02_tertile": rec["tertile"],
            "v02_s2_event_id": rec["s2_event_id"],
            "v02_s2_event_utc": rec["s2_event_utc"],
            "v02_pair_gap_days": int(rec["gap_days"]),
            "v02_pair_token": rec["pair_token"]})
    rows.sort(key=lambda r: str(r["product_id"]))
    return rows


def load_export_panel() -> pd.DataFrame:
    panel = pd.read_csv(PANEL_CSV)[["cell_id", "province", "coastal_segment"]]
    registry = pd.read_csv(REGISTRY_CSV)[["cell_id", "center_lon",
                                          "center_lat"]]
    out = panel.merge(registry, on="cell_id", how="left", validate="1:1")
    if out[["center_lon", "center_lat"]].isna().any().any():
        raise SystemExit("v0.2 panel cells missing from frozen registry")
    out = out.rename(columns={"province": "region_province"})
    return out.set_index("cell_id")


def canary_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deterministic canary: first S2 product + its S1 pair + first L."""
    s2 = sorted((r for r in rows if r["sensor"] == "sentinel2"),
                key=lambda r: str(r["product_id"]))
    landsat = sorted((r for r in rows
                      if str(r["sensor"]).startswith("landsat")),
                     key=lambda r: str(r["product_id"]))
    if not s2 or not landsat:
        raise SystemExit("canary needs at least one S2 and one Landsat "
                         "eligible product")
    chosen: list[dict[str, Any]] = [s2[0]]
    anchor = s2[0]
    match = next((r for r in rows
                  if r["sensor"] == "sentinel1"
                  and r["cell_id"] == anchor["cell_id"]
                  and r["year"] == anchor["year"]
                  and r["v02_tertile"] == anchor["v02_tertile"]), None)
    if match is not None:
        chosen.append(match)
    chosen.append(landsat[0])
    return chosen


# ---------------------------------------------------------------------------
# pilot19 V2 driver redirection at module boundaries
# ---------------------------------------------------------------------------

def configure_driver(
    p19: Any, checksums: dict[str, str],
) -> None:
    p19.GDRIVE_FOLDER = GDRIVE_FOLDER
    p19.ISSUE_TAG = ISSUE_TAG
    p19.WORK_DIR = EXPORT_WORK
    p19.PRODUCT_DIR = PRODUCT_DIR
    p19.MANIFEST_DIR = MANIFEST_DIR
    p19.TASK_STORE = TASK_STORE
    p19.FAILURES_JSON = FAILURES_JSON
    p19.PROGRESS_JSON_V2 = PROGRESS_JSON
    p19.PROGRESS_JSON = PROGRESS_JSON
    p19.VOLUME_CAP_BYTES = S.MAX_LANDED_EO_BYTES

    def v02_prefix_for(
        row: dict[str, Any], role: str, *, plan_version: str = "v2",
        revision: str | None = None,
    ) -> str:
        # plan_version is fixed by the v0.2 contract but kept in-signature
        # because the shared V2 driver calls it as a keyword argument.
        _ = plan_version
        rev = revision or V02_REVISION
        return (f"spartina_v02_{row['product_id']}_{role}_"
                f"{p19.date_tag(row)}_{rev}")

    def v02_request_for(
        row: dict[str, Any], role: str, *, plan_version: str = "v2",
        revision: str | None = None,
    ) -> str:
        _ = plan_version
        rev = revision or V02_REVISION
        return f"v02:{row['product_id']}:{role}:{rev}"

    def v02_event_selection_block(
        row: dict[str, Any], plan_checksum: str,
    ) -> dict[str, Any]:
        _ = plan_checksum  # checksums are embedded from the frozen plans
        block = {
            "revision": V02_SELECTION,
            "issue": 21,
            "phase": "H",
            "eligibility_status": row.get("status"),
            "v2_change": row.get("v2_change"),
            "tertile": row.get("v02_tertile"),
            "actual_mask_gate": A.ACTUAL_MASK_GATE,
            "actual_observed_fraction_planned":
                row.get("v2_actual_observed_fraction"),
            "evidence_source": row.get("v2_evidence_source"),
            "label_independent": True,
            "threshold_relaxation_forbidden": True,
            "plan_checksums": checksums,
        }
        if row["sensor"] == "sentinel1":
            block.update({
                "pair_s2_event_id": row.get("v02_s2_event_id"),
                "pair_s2_event_utc": row.get("v02_s2_event_utc"),
                "pair_gap_days": row.get("v02_pair_gap_days"),
                "pair_token": row.get("v02_pair_token"),
                "primary_gap_days_max": A.S1_PRIMARY_GAP_DAYS})
        return block

    p19.prefix_for = v02_prefix_for
    p19.request_for = v02_request_for
    p19.event_selection_block = v02_event_selection_block


def _make_scheduler_class(p19: Any) -> type[Any]:
    class V02Scheduler(p19.ExportScheduler):  # type: ignore[misc]
        def __init__(
            self, ee: Any, store: Any, panel: pd.DataFrame,
            checksums: dict[str, str], *, concurrency: int,
            hard_stop_on_failure: bool,
        ) -> None:
            super().__init__(
                ee, store, panel, concurrency=concurrency,
                poll_interval_s=p19.POLL_INTERVAL_S,
                task_timeout_s=p19.TASK_TIMEOUT_S,
                hard_stop_on_failure=hard_stop_on_failure,
                plan_version="v2",
                plan_checksum=checksums["scope_estimate"])
            self.v02_checksums = dict(checksums)

        def write_progress(self, scope: list[dict[str, Any]]) -> None:
            failed_pids = {f["product_id"] for f in self.failures
                           if not f.get("superseded")}
            active_map = {pid: self._active_state(job)
                          for pid, job in self.active.items()}
            summary = p19.summarize_states(
                [str(r["product_id"]) for r in scope],
                self.landed_pids, failed_pids, active_map)
            products = [{
                "product_id": str(row["product_id"]),
                "cell_id": row["cell_id"],
                "sensor": row["sensor"],
                "year": int(row["year"]),
                "state": summary["by_product"][str(row["product_id"])],
                "n_components": self._n_components(str(row["sensor"])),
                "n_export_tasks": len(p19.COMPONENTS[str(row["sensor"])]),
                "manifest": (
                    str(p19.MANIFEST_DIR
                        / f"{row['product_id']}.json")
                    if str(row["product_id"]) in self.landed_pids else None)}
                for row in scope]
            doc = {
                "product": "spartinashift_v0_2_export_progress",
                "issue": 21,
                "event_selection_revision": V02_SELECTION,
                "plan_checksums": self.v02_checksums,
                "updated_utc": datetime.now(UTC).isoformat(),
                "gdrive_folder": p19.GDRIVE_FOLDER,
                "revision": V02_REVISION,
                "s1_validity_token_revision": p19.S1_VALID_V2_REVISION,
                "states": summary["states"],
                "total_landed_bytes": self.total_landed_bytes,
                "hard_cap_bytes": S.MAX_LANDED_EO_BYTES,
                "hard_stop": self.stop,
                "products": products,
                "failures": self.failures,
                "git": p19.git_context(REPO_ROOT),
                "environment": p19.runtime_environment()}
            p19.PROGRESS_JSON_V2.parent.mkdir(parents=True, exist_ok=True)
            p19.PROGRESS_JSON_V2.write_text(
                json.dumps(doc, indent=2, default=str), encoding="utf-8")

    V02Scheduler.__name__ = "V02Scheduler"
    return V02Scheduler


def write_index(
    scheduler: Any, scope: list[dict[str, Any]], checksums: dict[str, str],
) -> None:
    products: list[dict[str, Any]] = []
    for row in scope:
        pid = str(row["product_id"])
        if pid not in scheduler.landed_pids:
            continue
        manifest = json.loads(
            (MANIFEST_DIR / f"{pid}.json").read_text("utf-8"))
        products.append({
            "product_id": pid,
            "cell_id": row["cell_id"],
            "sensor": row["sensor"],
            "year": int(row["year"]),
            "tertile": row.get("v02_tertile"),
            "n_bytes": int(manifest["n_bytes"]),
            "manifest": str((MANIFEST_DIR / f"{pid}.json")
                            .relative_to(REPO_ROOT)),
            "qa_gate_pass": bool(
                manifest.get("qa", {})
                .get("actual_mask_v2", {}).get("gate", {}).get("pass"))})
    doc = {
        "product": "SPARTINASHIFT_V0_2_EXPORT_INDEX",
        "issue": 21,
        "generated_utc": datetime.now(UTC).isoformat(),
        "plan_checksums": checksums,
        "gdrive_folder": GDRIVE_FOLDER,
        "n_scope": len(scope),
        "n_landed": len(products),
        "n_failures_open": sum(
            1 for f in scheduler.failures if not f.get("superseded")),
        "landed_bytes": sum(int(p["n_bytes"]) for p in products),
        "hard_cap_bytes": S.MAX_LANDED_EO_BYTES,
        "products": products}
    INDEX_JSON.write_text(
        json.dumps(doc, indent=2, default=str), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canary", action="store_true",
                        help="export only the deterministic canary set")
    parser.add_argument("--only-sensor",
                        choices=["landsat5", "landsat7", "landsat8",
                                 "sentinel1", "sentinel2"])
    parser.add_argument("--products", default="",
                        help="comma-separated product_id allowlist")
    parser.add_argument("--concurrency", type=int, default=7)
    parser.add_argument("--dry-run", action="store_true",
                        help="assemble and verify scope; submit nothing")
    args = parser.parse_args()

    s2_doc = _verify(S2_JSON)
    l_doc = _verify(L_JSON)
    g_doc = _verify(G_JSON)
    scope_doc = _verify(SCOPE_JSON)
    if scope_doc["verdict"] != S.VERDICT_PROCEED:
        raise SystemExit(
            f"scope verdict is {scope_doc['verdict']}; export forbidden")

    rows = build_rows(s2_doc, l_doc, g_doc)
    n_tasks = sum(S.COMPONENT_TASKS[str(r["sensor"])] for r in rows)
    expected = scope_doc["counts"]
    if (len(rows) != (expected["s2_eligible_events"]
                      + expected["s1_primary_pairs_lte7d"]
                      + expected["landsat_eligible_observations"])
            or n_tasks != scope_doc["projected_gee_component_tasks"]):
        raise SystemExit(
            "frozen plans and scope estimate disagree on product/task "
            f"counts: rows={len(rows)} tasks={n_tasks}")

    if args.only_sensor:
        rows = [r for r in rows if r["sensor"] == args.only_sensor]
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

    checksums = {
        "s2_plan": s2_doc["document_checksum"],
        "s2_plan_csv": s2_doc.get("plan_csv_sha256"),
        "landsat_plan": l_doc["document_checksum"],
        "landsat_plan_csv": l_doc.get("plan_csv_sha256"),
        "s1_pairing_ledger": g_doc["document_checksum"],
        "s1_pairing_csv": g_doc.get("plan_csv_sha256"),
        "scope_estimate": scope_doc["document_checksum"]}

    scope_tasks = sum(S.COMPONENT_TASKS[str(r["sensor"])] for r in rows)
    by_sensor = {s: sum(1 for r in rows if r["sensor"] == s)
                 for s in ("sentinel2", "sentinel1",
                           "landsat5", "landsat7", "landsat8")}
    print(f"[v02] scope: {len(rows)} products / {scope_tasks} GEE tasks "
          f"(frozen full-scope total {n_tasks}; canary={args.canary}) "
          f"{by_sensor}", flush=True)
    if args.dry_run:
        print("[v02] dry-run: scope matches frozen estimate; no tasks")
        return 0
    if os.environ.get("SPARTINA_V02_EXPORT") != "1":
        raise SystemExit(
            "real v0.2 export needs SPARTINA_V02_EXPORT=1 (explicit "
            "operator opt-in)")
    if configured_project() is None:
        raise SystemExit("export SPARTINA_GEE_PROJECT=<project-id> first")

    p19 = _load_driver()
    configure_driver(p19, checksums)
    scheduler_cls = _make_scheduler_class(p19)

    initialize()
    import ee

    PRODUCT_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    TASK_STORE.parent.mkdir(parents=True, exist_ok=True)
    if args.canary:
        pd.DataFrame({"product_id": [r["product_id"] for r in rows]}
                     ).to_csv(CANARY_CSV, index=False)

    store = p19.TaskStore(TASK_STORE)
    panel = load_export_panel()
    scheduler = scheduler_cls(
        ee, store, panel, checksums, concurrency=args.concurrency,
        hard_stop_on_failure=args.canary)
    scheduler.run(rows)
    write_index(scheduler, rows, checksums)
    open_failures = [f for f in scheduler.failures
                     if not f.get("superseded")]
    print(f"[v02] landed={len(scheduler.landed_pids)} "
          f"open_failures={len(open_failures)} "
          f"bytes={scheduler.total_landed_bytes}", flush=True)
    if scheduler.stop:
        print("CANARY_FAIL: canary hard stop; no further tasks submitted",
              flush=True)
        return 2
    if open_failures:
        print("EXPORT_FAILURES_PRESENT: systematic failure review required "
              "before Phase I", flush=True)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
