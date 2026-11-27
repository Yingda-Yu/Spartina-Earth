"""Write the tracked supersession manifest for national census v0_1.

Inputs (all executed artifacts / tracked audits):
  work/national/census_r1/products/china_eo_census_report_v0_1.json
  docs/data/national/S1_PASS_DISTRIBUTION_AUDIT_v0_1.json
  docs/data/national/NE_CHRONIC_ZERO_AUDIT_v0.json
  docs/data/national/FOOTPRINT_INDICES_v0_1.json

Output:
  docs/data/national/CHINA_EO_CENSUS_SUPERSESSION_v0_1.json

The v0 products are never modified; this manifest only records the
v0_1 fingerprints and the four audited change reasons.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

CHANGE_REASONS = (
    "2026_YTD_ADDED",
    "S1_PASS_AUDIT",
    "NE_EDGE_AUDIT",
    "L7_EXTENDED_MISSION_PRESERVED",
)


def _git_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report",
        type=Path,
        default=Path(
            "work/national/census_r1/products/china_eo_census_report_v0_1.json"
        ),
    )
    parser.add_argument(
        "--docs-dir", type=Path, default=Path("docs/data/national")
    )
    args = parser.parse_args()

    report = json.loads(args.report.read_text(encoding="utf-8"))
    docs = args.docs_dir
    s1_audit = json.loads(
        (docs / "S1_PASS_DISTRIBUTION_AUDIT_v0_1.json").read_text(
            encoding="utf-8"
        )
    )
    ne_audit = json.loads(
        (docs / "NE_CHRONIC_ZERO_AUDIT_v0.json").read_text(encoding="utf-8")
    )
    fp_indices = json.loads(
        (docs / "FOOTPRINT_INDICES_v0_1.json").read_text(encoding="utf-8")
    )

    manifest: dict[str, Any] = {
        "manifest": "china_eo_census_supersession",
        "new_version": "v0_1",
        "supersedes": "v0",
        "generated_utc": report.get("generated_utc"),
        "git_commit": _git_commit(),
        "census_cutoff_utc": report["census_cutoff_utc"],
        "year_status": "2026=PARTIAL_YEAR; comparisons use full years only",
        "v0_products_untouched": True,
        "change_reasons": [
            {
                "reason": "2026_YTD_ADDED",
                "description": (
                    "2026 acquisitions queried only for operational sensors "
                    "through the frozen cutoff; Landsat 5 recorded as "
                    "SENSOR_NOT_OPERATIONAL without a query; Landsat 7 has "
                    "zero rows (imaging suspended 2024-01-19)."
                ),
                "evidence": report["scene_counts_2026_ytd"],
            },
            {
                "reason": "S1_PASS_AUDIT",
                "description": (
                    "National unfiltered Sentinel-1 funnel rebuilt with ASC "
                    "and DESC kept at every funnel level, relative orbits, "
                    "and deterministic live spot checks; v0_1 scene set is "
                    "the rebuilt IW/VV|VH/W10-intersecting universe."
                ),
                "diagnosis_token": s1_audit["diagnosis_token"],
                "audit_doc": "S1_PASS_DISTRIBUTION_AUDIT_v0_1.json",
            },
            {
                "reason": "NE_EDGE_AUDIT",
                "description": (
                    "The 23 far-northeast chronic-zero cells were audited; "
                    "chronic zeros are domain/index artifacts, not query "
                    "failures. Footprint indices expanded (+5 WRS-2 frames, "
                    "+13 MGRS tiles) and affected historical ranges were "
                    "re-queried."
                ),
                "class_counts": ne_audit["class_counts"],
                "wrs2_frames": fp_indices["wrs2"]["n_frames"],
                "mgrs_tiles": fp_indices["mgrs"]["n_tiles"],
                "audit_docs": (
                    "NE_CHRONIC_ZERO_AUDIT_v0.json; "
                    "FOOTPRINT_INDICES_v0_1.json; "
                    "datasets/manifests/china_ne_chronic_zero_audit_v0.csv"
                ),
            },
            {
                "reason": "L7_EXTENDED_MISSION_PRESERVED",
                "description": (
                    "All v0 Landsat 7 rows preserved; post-2022-05-05 "
                    "Extended Science Mission scenes remain ineligible for "
                    "default production but are now joined to cells through "
                    "their actual pulled footprints and reported separately "
                    "from nominal WRS-2 events."
                ),
                "evidence": report["l7_extended_mission"],
            },
        ],
        "product_fingerprints_sha256": report["sha256"],
        "product_bytes": report["product_bytes"],
        "aggregates": {
            "scene_counts": report["scene_counts"],
            "unique_scenes_total": report["unique_scenes_total"],
            "cell_event_pairs": report["cell_event_pairs"],
            "observed_cells": report["observed_cells"],
            "geometry_basis_pair_counts": report[
                "geometry_basis_pair_counts"
            ],
            "gap_class_counts": report["gap_class_counts"],
            "chronic_zero_cells_common_era": report[
                "chronic_zero_cells_common_era"
            ],
        },
        "failed_scopes": report["failed_scopes"],
        "change_reason_tokens": list(CHANGE_REASONS),
    }

    out = docs / "CHINA_EO_CENSUS_SUPERSESSION_v0_1.json"
    out.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
