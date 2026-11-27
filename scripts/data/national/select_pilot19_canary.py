#!/usr/bin/env python3
"""Issue #19 Phase D0 -- deterministic multi-sensor canary selection.

Picks exactly one already-SELECTED product per sensor
(L5, L7, L8, S1, S2) from the FROZEN 194-row event plan. This is an
export-subset choice only: it never re-runs or changes event selection,
never looks at pixels or labels, and uses no model-performance signal.

Deterministic, label-blind ranking (fixed sensor order):
  1. prefer a cell whose province is not yet used by an earlier canary
     pick (region diversity, per owner instruction);
  2. then prefer an unused coastal segment;
  3. ties broken by product_id ascending.

Outputs:
  datasets/manifests/national_pilot19_canary_v1.csv
  datasets/manifests/national_pilot19_canary_v1.json
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

PLAN_CSV = REPO_ROOT / "datasets/manifests/national_pilot_event_plan_v1.csv"
PLAN_JSON = REPO_ROOT / "datasets/manifests/national_pilot_event_plan_v1.json"
PANEL_CSV = REPO_ROOT / "datasets/manifests/national_first_pixel_panel_v1.csv"
OUT_CSV = REPO_ROOT / "datasets/manifests/national_pilot19_canary_v1.csv"
OUT_JSON = REPO_ROOT / "datasets/manifests/national_pilot19_canary_v1.json"

#: Fixed canary sensor order.
CANARY_SENSORS: tuple[str, ...] = (
    "landsat5", "landsat7", "landsat8", "sentinel1", "sentinel2")

SELECTION_RULE = (
    "deterministic canary: fixed sensor order (L5,L7,L8,S1,S2); one "
    "SELECTED product per sensor; rank key = (province already used, "
    "coastal segment already used, product_id asc); label-blind, "
    "pixel-blind, no event-selection change")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, check=True,
            capture_output=True, text=True)
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNKNOWN"


def select_canary(
    plan: pd.DataFrame, panel: pd.DataFrame,
) -> list[dict[str, Any]]:
    selected = plan[plan.status == "SELECTED"].copy()
    regions = panel.set_index("cell_id")[
        ["region_province", "coastal_segment"]]
    picked: list[dict[str, Any]] = []
    used_provinces: set[str] = set()
    used_segments: set[str] = set()
    for sensor in CANARY_SENSORS:
        pool = selected[selected.sensor == sensor].merge(
            regions, left_on="cell_id", right_index=True, how="left")
        if pool.empty:
            continue  # sensor legitimately absent -> honest skip
        pool["province_used"] = pool.region_province.isin(used_provinces)
        pool["segment_used"] = pool.coastal_segment.isin(used_segments)
        pool = pool.sort_values(
            ["province_used", "segment_used", "product_id"],
            kind="mergesort")
        row = pool.iloc[0]
        province = str(row.region_province)
        segment = str(row.coastal_segment)
        picked.append({
            "product_id": str(row.product_id),
            "cell_id": str(row.cell_id),
            "sensor": sensor,
            "year": int(row.year),
            "event_id": str(row.event_id),
            "event_utc": str(row.event_utc),
            "province": province,
            "coastal_segment": segment,
            "pass": ("" if pd.isna(row["pass"]) else str(row["pass"])),
            "coverage_tier": str(row.coverage_tier),
            "selection_order": len(picked) + 1,
            "canary_reason": SELECTION_RULE,
            "region_diversity": (
                f"province {province} "
                f"{'reused' if province in used_provinces else 'new'}; "
                f"segment {segment} "
                f"{'reused' if segment in used_segments else 'new'}"),
        })
        used_provinces.add(province)
        used_segments.add(segment)
    return picked


def main() -> None:
    plan = pd.read_csv(PLAN_CSV)
    panel = pd.read_csv(PANEL_CSV)
    plan_doc = json.loads(PLAN_JSON.read_text(encoding="utf-8"))
    expected = plan_doc["checksums"]["plan_csv_sha256"]
    if _sha256(PLAN_CSV) != expected:
        raise SystemExit("frozen plan CSV checksum mismatch; abort")

    picks = select_canary(plan, panel)
    if {p["sensor"] for p in picks} != set(CANARY_SENSORS):
        raise SystemExit(
            f"canary must cover {CANARY_SENSORS}, got "
            f"{[p['sensor'] for p in picks]}")

    out = pd.DataFrame(picks)
    out.to_csv(OUT_CSV, index=False)
    manifest = {
        "product": "national_pilot19_canary_v1",
        "issue": 19,
        "phase": "D0",
        "generated_utc": datetime.now(UTC).isoformat(),
        "git_commit": _git_commit(),
        "status": "CANARY_SELECTED_NOT_EXPORTED",
        "selection_rule": SELECTION_RULE,
        "sensor_order": list(CANARY_SENSORS),
        "n_products": len(picks),
        "products": picks,
        "inputs": {
            "plan_csv": PLAN_CSV.name,
            "plan_csv_sha256": expected,
            "panel_csv": PANEL_CSV.name,
            "panel_csv_sha256": _sha256(PANEL_CSV)},
    }
    OUT_JSON.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8")
    print(json.dumps([{"product_id": p["product_id"],
                       "sensor": p["sensor"],
                       "region": p["region_diversity"]}
                      for p in picks], indent=1))
    print(f"wrote {OUT_JSON.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
