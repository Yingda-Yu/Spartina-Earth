#!/usr/bin/env python3
"""Build the committed availability + gap matrices from census summaries.

Pure-local: reads the committed census summary parquet and the legacy
label inventory, never contacts Earth Engine. Missing stays explicit
(SENSOR_NOT_OPERATIONAL vs NO_SCENES_FOUND ...), nothing is interpolated.

Outputs:
  datasets/manifests/zhejiang_eo_availability_v0.csv  (wide, year x roi)
  datasets/manifests/zhejiang_data_gap_matrix_v0.csv  (long, all axes)
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

import pandas as pd  # noqa: E402
import yaml  # noqa: E402

from spartina.data.zhejiang.contracts import (  # noqa: E402
    AVAILABILITY_COLUMNS,
    GAP_NO_QUALITY,
    GAP_NO_SCENES,
    GAP_NONE,
    GAP_NOT_OPERATIONAL,
    SENSORS,
)

TIDE_METADATA = ("HARMONIC_MODELS_SELECTABLE_1985-2026_NOT_JOINED;"
                 "PUBLIC_GAUGE_OBS_BLOCKED_POST_1997")
FIELD_UAV = "NONE_FOUND"
MANAGEMENT = "UNKNOWN_NO_EVIDENCE_INVENTORY_AT_M21A"


def label_status_by_year(
    inventory_csv: Path, bay_column: str
) -> dict[int, str]:
    """Return year -> best label tier actually overlapping a bay."""
    df = pd.read_csv(inventory_csv)
    out: dict[int, dict[str, int]] = {}
    for _, r in df.iterrows():
        raw = str(r[bay_column])
        if raw.startswith("footprint_intersection"):
            # composites are not labels
            continue
        try:
            count = int(raw)
        except ValueError:
            continue
        if count <= 0:
            continue
        year = int(r["nominal_year"])
        tier = str(r["label_tier"])
        out.setdefault(year, {})[tier] = count
    result: dict[int, str] = {}
    rank = {"GOLD": 3, "SILVER": 2, "WEAK": 1}
    for year, tiers in out.items():
        result[year] = max(tiers, key=lambda t: rank.get(t, 0))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config",
                        default=str(REPO_ROOT
                                    / "configs/data/zhejiang_multibay_m21a.yaml"))
    parser.add_argument("--manifest-dir",
                        default=str(REPO_ROOT / "datasets/manifests"))
    args = parser.parse_args()

    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    mdir = Path(args.manifest_dir)
    summary = pd.read_parquet(mdir / "zhejiang_eo_census_summary_v0.parquet")
    inventory = mdir / "zhejiang_legacy_label_inventory_v0.csv"

    y0 = int(config["time_axis"]["start_year"])
    y1 = int(config["time_axis"]["end_year"])
    roi_ids = [b["roi_id"] for b in config["rois"]]

    # column names in inventory for per-bay overlap counts
    bay_col = {
        "ZJ-HZB": "overlap_zj_hzb",
        "ZJ-SMB": "overlap_zj_smb",
        "ZJ-YQB": "overlap_zj_yqb",
    }

    wide_rows: list[dict[str, Any]] = []
    long_rows: list[dict[str, Any]] = []
    for roi_id in roi_ids:
        labels = label_status_by_year(inventory, bay_col[roi_id])
        sub = summary[summary.roi_id == roi_id].set_index(
            ["year", "sensor"])
        for year in range(y0, y1 + 1):
            row: dict[str, Any] = {"year": year, "roi_id": roi_id}
            for sensor in SENSORS:
                if (year, sensor) not in sub.index:
                    status = "QUERY_NOT_RUN"
                    scenes: int | str = ""
                else:
                    rec = sub.loc[(year, sensor)]
                    status = str(rec["gap_status"])
                    scenes = int(rec["total_scenes"])
                row[f"{sensor}_status"] = status
                row[f"{sensor}_scenes"] = scenes
                if status != GAP_NONE:
                    long_rows.append({
                        "roi_id": roi_id, "year": year,
                        "axis": sensor, "gap_status": status,
                        "detail": f"total_scenes={scenes}",
                    })
            tier = labels.get(year, "NONE")
            row["label_available"] = tier
            row["field_uav_available"] = FIELD_UAV
            row["management_event_known"] = MANAGEMENT
            row["tide_metadata"] = TIDE_METADATA
            sensor_gaps = [row[f"{s}_status"] for s in SENSORS]
            if all(st == GAP_NOT_OPERATIONAL for st in sensor_gaps):
                row["status"] = "PRE_SENSOR_ERA"
            elif GAP_NONE in sensor_gaps:
                row["status"] = "EO_SCENES_PRESENT"
            elif GAP_NO_SCENES in sensor_gaps or GAP_NO_QUALITY in sensor_gaps:
                row["status"] = "OPERATIONAL_BUT_GAPPED"
            else:
                row["status"] = "UNKNOWN"
            if tier == "NONE":
                long_rows.append({"roi_id": roi_id, "year": year,
                                  "axis": "label", "gap_status": "NO_LABEL",
                                  "detail": "no in-bay legacy label"})
            for axis, value, detail in (
                ("field_uav", "NONE_FOUND", "no field/UAV evidence asset"),
                ("management_event", "UNKNOWN", "no event inventory evidence"),
                ("tide", "MODEL_SELECTABLE_NOT_JOINED", TIDE_METADATA),
            ):
                long_rows.append({"roi_id": roi_id, "year": year,
                                  "axis": axis, "gap_status": value,
                                  "detail": detail})
            wide_rows.append(row)

    avail_path = mdir / "zhejiang_eo_availability_v0.csv"
    with avail_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(AVAILABILITY_COLUMNS))
        writer.writeheader()
        writer.writerows(wide_rows)

    gap_path = mdir / "zhejiang_data_gap_matrix_v0.csv"
    with gap_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=("roi_id", "year", "axis", "gap_status", "detail"))
        writer.writeheader()
        writer.writerows(long_rows)

    print(f"wrote {avail_path.name} ({len(wide_rows)} rows) and "
          f"{gap_path.name} ({len(long_rows)} rows)")

    index_rows = []
    for name in (
        "zhejiang_roi_registry_v0.parquet",
        "zhejiang_legacy_label_inventory_v0.parquet",
        "zhejiang_eo_scene_census_v0.parquet",
        "zhejiang_eo_census_summary_v0.parquet",
        "zhejiang_eo_availability_v0.csv",
        "zhejiang_data_gap_matrix_v0.csv",
    ):
        target = mdir / name
        if not target.exists():
            continue
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        index_rows.append({
            "artifact": name,
            "bytes": target.stat().st_size,
            "sha256": digest,
        })
    index_path = mdir / "zhejiang_m21a_artifact_fingerprints_v0.csv"
    with index_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=("artifact", "bytes", "sha256"))
        writer.writeheader()
        writer.writerows(index_rows)
    print(f"wrote {index_path.name} ({len(index_rows)} artifacts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
