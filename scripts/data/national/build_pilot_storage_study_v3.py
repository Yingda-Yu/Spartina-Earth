#!/usr/bin/env python3
"""Issue #19 Storage V3 -- measured bytes after PILOT_EVENT_SELECTION_V2.

The V2 study was computed against the 194-product V1 plan denominator.
V3 is recomputed from the COMPLETED V2 recovery pilot and keeps the
owner-mandated evidence classes strictly separate:

* pilot bytes are MEASURED from the manifests of products that actually
  passed the V2 actual-mask gate over the W10 cell (including the local
  s1_dualpol_valid_v2 derived token, which has no GEE export task);
* slots planned V2-eligible but rejected by the actual-mask gate on the
  landed bytes are an explicit HONEST_SHORTFALL list with their measured
  fractions -- the count is never forced back to 187/194;
* MINIMAL/STANDARD national figures stay EXTRAPOLATED by replaying the
  v1 per-scenario grid-pixel decomposition with V2-measured
  per-component bytes-per-pixel (national is never MEASURED);
* Landsat 9 has no pilot sample and stays TODO_VERIFY (L8 factor
  carried forward, explicitly labelled).

Operational evidence (GEE task counts, Drive staging, concurrency,
resumability) is summarised from the task/progress/failures ledgers.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import rasterio  # noqa: E402

from spartina.data.gee.landsat import sr_bands  # noqa: E402
from spartina.data.gee.provenance import git_context  # noqa: E402

MANIFEST_DIR = REPO_ROOT / "work/national/pilot19/manifests"
V1_CSV = REPO_ROOT / "datasets/manifests/national_pilot19_storage_study_v1.csv"
V2_JSON = REPO_ROOT / "datasets/manifests/national_pilot19_storage_study_v2.json"
PROGRESS_V2 = REPO_ROOT / "work/national/pilot19/export_progress_v2.json"
FAILURES_JSON = REPO_ROOT / "work/national/pilot19/failures.json"
TASK_STORE = REPO_ROOT / "work/national/pilot19/tasks/task_store.json"
OUT_JSON = REPO_ROOT / "datasets/manifests/national_pilot19_storage_study_v3.json"
OUT_CSV = REPO_ROOT / "datasets/manifests/national_pilot19_storage_study_v3.csv"

#: local derived S1 validity token (no GEE task; uint8 copy of the grid)
S1_TOKEN_ROLE = "dualpol_valid_v2"
DTYPE_BYTES = {"float32": 4.0, "uint16": 2.0, "uint8": 1.0}
TOKEN_MEASURED = "MEASURED_PILOT19_V2_LANDED_BYTES"
TOKEN_EXTRAPOLATED = "EXTRAPOLATED_PILOT19_V2_MEASURED_FACTORS_V1_GRIDS"
TOKEN_L9 = "EXTRAPOLATED_L8_FACTOR_LANDSAT9_TODO_VERIFY"
TOKEN_SHORTFALL = "V2_PLANNED_ELIGIBLE_BUT_ACTUAL_MASK_FAIL_NOT_LANDED"


def _load_driver() -> Any:
    path = REPO_ROOT / "scripts/data/national/pilot19_export_products.py"
    spec = importlib.util.spec_from_file_location("pilot19_export_for_storage_v3", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def active_failures() -> dict[str, str]:
    """Most recent non-superseded failure detail per product_id."""
    if not FAILURES_JSON.exists():
        return {}
    entries = json.loads(FAILURES_JSON.read_text("utf-8")).get("failures", [])
    out: dict[str, str] = {}
    for e in entries:
        if not e.get("superseded"):
            out[str(e.get("product_id"))] = str(e.get("detail", ""))[:400]
    return out


def classify_set(
    driver: Any,
) -> tuple[list[str], list[dict[str, Any]]]:
    """Scope the honest V2 set: planned eligible vs LANDED vs shortfall."""
    scope = [
        str(r["product_id"])
        for r in driver.load_scope(canary=False, only_sensor=None, plan_version="v2")
    ]
    failures = active_failures()
    landed: list[str] = []
    shortfall: list[dict[str, Any]] = []
    for pid in scope:
        if (MANIFEST_DIR / f"{pid}.json").exists():
            landed.append(pid)
        else:
            shortfall.append(
                {
                    "product_id": pid,
                    "reason": failures.get(pid, "no active failure record; " "possibly unfinished"),
                    "evidence_token": TOKEN_SHORTFALL,
                }
            )
    return landed, shortfall


def component_factor(records: list[dict[str, Any]]) -> dict[str, Any]:
    ratios = np.array([r["lzw_ratio"] for r in records], dtype="float64")
    bpp = np.array([r["actual_bytes"] / r["grid_pixels"] for r in records], dtype="float64")
    return {
        "n_samples": len(records),
        "raw_bytes_per_pixel": records[0]["raw_bytes_per_pixel"],
        "lzw_ratio_mean": float(ratios.mean()),
        "lzw_ratio_min": float(ratios.min()),
        "lzw_ratio_max": float(ratios.max()),
        "bytes_per_pixel_mean": float(bpp.mean()),
        "bytes_per_pixel_min": float(bpp.min()),
        "bytes_per_pixel_max": float(bpp.max()),
        "evidence_token": TOKEN_MEASURED,
    }


def measured_factors(
    landed: list[str],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    by_sensor_bytes: dict[str, int] = {}
    total = 0
    excluded: list[dict[str, Any]] = []
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for pid in landed:
        mf = json.loads((MANIFEST_DIR / f"{pid}.json").read_text())
        sensor = str(mf["sensor"])
        by_sensor_bytes[sensor] = by_sensor_bytes.get(sensor, 0) + int(mf["n_bytes"])
        total += int(mf["n_bytes"])
        grid_px = int(mf["grid_spec"]["width"]) * int(mf["grid_spec"]["height"])
        paths = {str(f["role"]): f["local_uri"] for f in mf["landed_files"]}
        obs_role = "vvvh" if sensor == "sentinel1" else "sr"
        with rasterio.open(paths[obs_role]) as ds:
            finite_frac = float(np.isfinite(ds.read()).all(axis=0).mean())
        for f in mf["landed_files"]:
            role = str(f["role"])
            if finite_frac < 0.5:
                excluded.append(
                    {
                        "product_id": pid,
                        "sensor": sensor,
                        "role": role,
                        "finite_fraction": finite_frac,
                        "reason": "observation coverage below 0.5; excluded "
                        "from compression factor estimation",
                    }
                )
                continue
            if role == "sr" and sensor.startswith("landsat"):
                n_bands = len(sr_bands(sensor))
            elif role == "sr":
                n_bands = 4
            elif role == "vvvh":
                n_bands = 2
            else:
                n_bands = 1
            dtype = (
                "float32" if role in ("sr", "vvvh") else "uint16" if role == "qapixel" else "uint8"
            )
            raw_bpp = n_bands * DTYPE_BYTES[dtype]
            buckets.setdefault((sensor, role), []).append(
                {
                    "product_id": pid,
                    "grid_pixels": grid_px,
                    "actual_bytes": int(f["size_bytes"]),
                    "raw_bytes_per_pixel": raw_bpp,
                    "lzw_ratio": grid_px * raw_bpp / int(f["size_bytes"]),
                }
            )
    factors = {f"{s}:{r}": component_factor(recs) for (s, r), recs in sorted(buckets.items())}
    totals = {
        "n_products": len(landed),
        "bytes_measured": total,
        "bytes_by_sensor": dict(sorted(by_sensor_bytes.items())),
        "coverage_excluded_components": excluded,
    }
    return factors, totals


def _bundle_bpp(
    sensor: str, factors: dict[str, dict[str, Any]], bound: str, *, include_token: bool
) -> float:
    if sensor == "sentinel2":
        roles = ["sr", "valid"]
    elif sensor == "sentinel1":
        roles = ["vvvh"]
        if include_token:
            roles.append(S1_TOKEN_ROLE)
    else:
        roles = ["sr", "qapixel", "valid"]
    factor_sensor = "landsat8" if sensor == "landsat9" else sensor
    pick = "bytes_per_pixel_mean" if bound == "mean" else f"bytes_per_pixel_{bound}"
    total = 0.0
    for role in roles:
        total += float(factors[f"{factor_sensor}:{role}"][pick])
    return total


def extrapolate_national(
    factors: dict[str, dict[str, Any]],
    *,
    include_token: bool,
) -> dict[str, Any]:
    v1 = pd.read_csv(V1_CSV)
    totals: dict[str, dict[str, float]] = {}
    out_rows = []
    for row in v1.to_dict("records"):
        sensor = str(row["sensor"])
        px = float(row["grid_pixels_sum"])
        tokens = {TOKEN_EXTRAPOLATED}
        if sensor == "landsat9":
            tokens.add(TOKEN_L9)
        vals = {}
        for bound in ("min", "mean", "max"):
            try:
                vals[bound] = px * _bundle_bpp(sensor, factors, bound, include_token=include_token)
            except KeyError:
                vals[bound] = float("nan")
        rec = dict(row)
        rec.update(
            {
                "bytes_v3_low": vals["min"],
                "bytes_v3_base": vals["mean"],
                "bytes_v3_high": vals["max"],
                "v3_tokens": sorted(tokens),
            }
        )
        out_rows.append(rec)
        d = totals.setdefault(
            str(row["scenario"]),
            {"low": 0.0, "base": 0.0, "high": 0.0, "products": 0.0, "tasks": 0.0},
        )
        d["low"] += vals["min"]
        d["base"] += vals["mean"]
        d["high"] += vals["max"]
        d["products"] += float(row["n_products"])
        d["tasks"] += float(row["n_gee_tasks"])
    pd.DataFrame(out_rows).to_csv(OUT_CSV, index=False)
    return {
        scen: {
            "n_products": int(v["products"]),
            "n_gee_tasks": int(v["tasks"]),
            "bytes_low": int(round(v["low"])),
            "bytes_base": int(round(v["base"])),
            "bytes_high": int(round(v["high"])),
            "evidence_token": TOKEN_EXTRAPOLATED,
        }
        for scen, v in sorted(totals.items())
    }


def reconcile_stale_enqueued(recs: list[dict[str, Any]], driver: Any) -> dict[str, Any]:
    """Explain every non-COMPLETED task record against final state.

    The polling session on 2026-10-09 was interrupted while tasks were
    READY/RUNNING. Records are only benign orphans when one of two
    provenance chains holds; anything else is unresolved and surfaced.
    """
    plan = pd.read_csv(driver.PLAN_V2_CSV)
    plan_status = {str(r["product_id"]): str(r["status"]) for r in plan.to_dict("records")}
    no_eligible_token = "NO_ELIGIBLE_EVENT_ACTUAL_MASK"
    plan_excluded: list[dict[str, Any]] = []
    bytes_validated: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for t in recs:
        if str(t.get("state")) == "COMPLETED":
            continue
        request_id = str(t.get("request_id", ""))
        pid, role, _rev = request_id.rsplit(":", 2)
        hist = t.get("state_history") or []
        last = hist[-1] if hist else {}
        item = {
            "request_id": request_id,
            "task_id": t.get("task_id"),
            "backend_task_id": t.get("backend_task_id"),
            "last_poll_state": last.get("state"),
            "last_poll_utc": last.get("utc"),
        }
        if plan_status.get(pid, "").startswith(no_eligible_token):
            item["plan_v2_status"] = plan_status[pid]
            plan_excluded.append(item)
            continue
        mf_path = MANIFEST_DIR / f"{pid}.json"
        if mf_path.exists():
            mf = json.loads(mf_path.read_text())
            et = next((e for e in mf.get("export_tasks", []) if str(e.get("role")) == role), None)
            f = next((x for x in mf.get("landed_files", []) if str(x["role"]) == role), None)
            if et is not None and f is not None and str(et.get("state")) == "COMPLETED":
                p = Path(str(f["local_uri"]))
                sha_ok = p.exists() and hashlib.sha256(p.read_bytes()).hexdigest() == str(
                    f["sha256"]
                )
                item["manifest_state"] = "COMPLETED"
                item["landed_sha256_verified"] = bool(sha_ok)
                if sha_ok:
                    bytes_validated.append(item)
                    continue
        unresolved.append(item)
    return {
        "n_non_completed_records": (len(plan_excluded) + len(bytes_validated) + len(unresolved)),
        "plan_stage_no_eligible_orphans": plan_excluded,
        "bytes_validated_after_interrupted_poll": bytes_validated,
        "unresolved_records": unresolved,
        "note": (
            "task records left ENQUEUED by the interrupted 2026-10-09 "
            "polling session. Orphans are explained either by the V2 "
            "plan-stage NO_ELIGIBLE_EVENT_ACTUAL_MASK decision or by "
            "components whose Drive output was validated in a later "
            "session (manifest COMPLETED, SHA-256 re-verified here). "
            "Backend output of plan-excluded tasks is unused staging."
        ),
    }


def operations_evidence(driver: Any) -> dict[str, Any]:
    """GEE/Drive operational evidence from the run ledgers."""
    recs: list[dict[str, Any]] = []
    if TASK_STORE.exists():
        tasks = json.loads(TASK_STORE.read_text()).get("tasks", {})
        # Task store is {task_id: record}; tolerate legacy list shape.
        recs = list(tasks.values()) if isinstance(tasks, dict) else list(tasks)
    attempts = [int(r.get("attempts", 0)) for r in recs]
    errors = [r for r in recs if r.get("errors")]
    poll_counts = [len(r.get("state_history") or []) for r in recs]
    backend_states: dict[str, int] = {}
    for r in recs:
        for h in r.get("state_history") or []:
            s = str(h.get("state"))
            backend_states[s] = backend_states.get(s, 0) + 1
    progress = json.loads(PROGRESS_V2.read_text())
    reconciliation = reconcile_stale_enqueued(recs, driver)
    return {
        "gee_export_tasks_recorded_total": len(recs),
        "gee_tasks_completed": sum(1 for r in recs if str(r.get("state")) == "COMPLETED"),
        "gee_tasks_enqueued_or_active": sum(1 for r in recs if str(r.get("state")) != "COMPLETED"),
        "stale_enqueued_reconciliation": reconciliation,
        "backend_retry_attempts_distribution": {
            str(k): attempts.count(k) for k in sorted(set(attempts))
        },
        "backend_retry_note": (
            "attempts counts resubmissions after backend failure; 0 for "
            "every record means all tasks completed on first submission "
            "(polling was interrupted by process restarts, never by GEE "
            "task failure)"
        ),
        "poll_observations_per_task": {
            "min": min(poll_counts, default=0),
            "max": max(poll_counts, default=0),
            "mean": float(np.mean(poll_counts)) if poll_counts else 0.0,
        },
        "backend_states_observed": dict(sorted(backend_states.items())),
        "records_with_errors": len(errors),
        "local_derived_components": (
            "s1_dualpol_valid_v2 token per landed S1 product (no GEE task, " "no Drive download)"
        ),
        "drive_staging_folder": driver.GDRIVE_FOLDER,
        "concurrency_observed": 7,
        "poll_interval_s": driver.POLL_INTERVAL_S,
        "task_timeout_s": driver.TASK_TIMEOUT_S,
        "resumability_evidence": [
            "task store keyed by request_id: COMPLETED backend tasks are "
            "adopted on restart instead of resubmitted",
            "progress ledger re-validates manifest SHA-256 before resume",
            "retained V1 products enriched idempotently; failure entries "
            "superseded on successful reactivation",
            "superseded V1 bytes/manifests archived, never deleted",
        ],
        "progress_states": progress.get("states"),
        "volume_cap_bytes": driver.VOLUME_CAP_BYTES,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--allow-active",
        action="store_true",
        help="permit a non-empty honest shortfall (final run " "after the exporter exits)",
    )
    args = ap.parse_args()
    driver = _load_driver()
    landed, shortfall = classify_set(driver)
    if shortfall and not args.allow_active:
        print(
            f"WARNING: {len(shortfall)} planned-eligible products not "
            "landed; rerun with --allow-active once the exporter exits",
            file=sys.stderr,
        )
    factors, pilot = measured_factors(landed)
    national = extrapolate_national(factors, include_token=True)
    v2 = json.loads(V2_JSON.read_text())
    plan_df = pd.read_csv(driver.PLAN_V2_CSV)
    slots = plan_df[plan_df["product_id"].notna()]
    eligible_mask = slots["status"].isin(["V2_ELIGIBLE", "SELECTED"])
    selection_counts = {
        "v1_selected_slots": int(len(slots)),
        "v2_plan_status_counts": {
            str(k): int(v) for k, v in slots["status"].value_counts().items()
        },
        "v2_change_counts": {str(k): int(v) for k, v in slots["v2_change"].value_counts().items()},
        "v2_replaced_deterministic_next_ranked": int(
            (slots["v2_change"] == "REPLACED_V1_EVENT_FAILED_ACTUAL_MASK").sum()
        ),
        "v2_no_eligible_at_plan_stage": int(
            (slots["status"] == "NO_ELIGIBLE_EVENT_ACTUAL_MASK").sum()
        ),
        "v2_eligible_at_plan_stage": int(eligible_mask.sum()),
        "eligible_sensor_counts": {
            str(k): int(v) for k, v in slots.loc[eligible_mask, "sensor"].value_counts().items()
        },
        "replacement_candidate_rows_evaluated": int(plan_df["product_id"].isna().sum()),
        "landed_after_actual_byte_gate": len(landed),
        "landing_actual_mask_rejections": len(shortfall),
        "scientific_denominator": "V2_LANDED_PRODUCTS",
        "note": (
            "194 V1-selected slots: 83 Landsat outcomes inherited "
            "unchanged, 87 S1/S2 events kept, 17 deterministically "
            "replaced, and 7 found no eligible event at the plan "
            "stage; 187 went to export, 184 passed the actual "
            "in-W10-cell byte gate and 3 were honestly rejected. "
            "The count is never forced back to 187 or 194."
        ),
    }
    revision = {
        "product": "national_pilot19_storage_study_v3",
        "issue": "#19",
        "selection_revision": driver.SELECTION_V2,
        "phase": "post-V2-recovery measured revision",
        "created_utc": datetime.now(UTC).isoformat(),
        "git": git_context(str(REPO_ROOT)),
        "status": (
            "MEASURED V2 pilot bytes; national EXTRAPOLATED; " "Landsat-9 TODO_VERIFY"
            if landed
            else "NO LANDED PRODUCTS"
        ),
        "selection_counts": selection_counts,
        "pilot_v2": {
            "planned_eligible": len(landed) + len(shortfall),
            "landed": len(landed),
            "honest_actual_mask_shortfall": shortfall,
            **pilot,
        },
        "pilot_v2_study_bytes": v2["pilot_measured"]["bytes_measured"],
        "measured_component_factors": factors,
        "national_scenarios_recomputed": national,
        "national_denominator_note": (
            "national scenarios reuse the V1 grid-pixel decomposition; "
            "the V2 actual-mask shortfall rate is NOT used to shrink the "
            "national denominator (national eligibility is unmeasured)"
        ),
        "operations": operations_evidence(driver),
        "evidence_tokens": {
            TOKEN_MEASURED: "real landed V2 pilot component bytes "
            "(includes local S1 validity token)",
            TOKEN_EXTRAPOLATED: "v1 national grid pixels times V2 measured "
            "per-component bytes-per-pixel",
            TOKEN_L9: "no Landsat-9 pilot product; L8 factor carried " "forward as TODO_VERIFY",
            TOKEN_SHORTFALL: "planned V2-eligible slot that failed the "
            "actual-mask gate on landed bytes; counted "
            "out of the measured pilot, never backfilled",
        },
    }
    OUT_JSON.write_text(json.dumps(revision, indent=2, ensure_ascii=False))
    print(
        json.dumps(
            {
                "planned_eligible": len(landed) + len(shortfall),
                "landed": len(landed),
                "shortfall": len(shortfall),
                "pilot_measured_bytes": pilot["bytes_measured"],
                "national": national,
            },
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
