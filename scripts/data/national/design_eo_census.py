#!/usr/bin/env python3
"""Emit the DESIGNED_NOT_RUN national EO metadata-census contract.

Issue #14 sections 37-40: the Tier 0 census is metadata-only (no pixel
export), uses a static nominal-frame prefilter (MGRS / WRS-2) and one
batched getInfo per frame x year x sensor - never per cell.  This script
records the complete contract from the verified SENSOR_SPECS without
contacting Earth Engine (M0/M1 offline; live execution is behind the
``gee_integration`` marker).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from spartina.data.national import census
from spartina.data.national.tiers import CostAssumptions, NationalScaleModel


def _git_commit() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    )
    return proc.stdout.strip() if proc.returncode == 0 else "UNKNOWN"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cells-csv", type=Path,
                        default=Path("work/national/domain/cells_china_albers_W10000.csv"))
    parser.add_argument("--positive-history-cells", type=int, default=482)
    parser.add_argument("--census-years", type=int, default=42)
    parser.add_argument("--out", type=Path,
                        default=Path("docs/data/national/EO_CENSUS_DESIGN_v0.json"))
    args = parser.parse_args()

    n_cells = sum(1 for _ in csv.DictReader(args.cells_csv.open(encoding="utf-8")))
    contract_checks: dict[str, str] = {}
    for spec in census.SENSOR_SPECS:
        try:
            census.assert_batch_contract(spec)
            contract_checks[spec.sensor.value] = "PASS"
        except ValueError as exc:
            contract_checks[spec.sensor.value] = f"FAIL: {exc}"

    design: dict[str, Any] = {
        "artifact": "national_eo_metadata_census_design",
        "version": "v0",
        "status": "DESIGNED_NOT_RUN",
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "git_commit": _git_commit(),
        "reason_not_run": (
            "M0/M1 metadata-only phase; no GEE credentials exercised and no "
            "bulk server interaction. Live execution must be added behind the "
            "gee_integration pytest marker."
        ),
        "scope": {
            "grid": "China Albers 10 km, W10000 coastal cells",
            "cells_csv": str(args.cells_csv),
            "cells_csv_sha256": _sha256(args.cells_csv),
            "n_cells": n_cells,
            "census_years": (
                f"{min(s.start_year for s in census.SENSOR_SPECS)}-"
                f"{max(s.end_year for s in census.SENSOR_SPECS)}"
            ),
        },
        "hard_rules": [
            "metadata properties only; zero pixel export; ee.batch.Export forbidden",
            "static nominal-frame prefilter: intersect cell union with MGRS tile "
            "(S1/S2) and WRS-2 descending path/row (Landsat) footprints once, offline",
            "one batched getInfo per (nominal_frame, year, sensor); never per cell",
            "nominal frame membership is a PREFILTER only; actual scene geometry is "
            "gated at census time (S1 mandatory; S2 retains the M2.1b lesson that "
            "MGRS nominal membership is not true ground coverage)",

            "no cloud/quality filtering in the census: report candidate counts, "
            "VALID/SCL status is a downstream production gate, not inferred",
            "S1 DN vs gamma0 collections are never mixed; ALOS L-band gap 2011-2014 "
            "is reported, not filled",
        ],
        "sensor_contracts": [asdict(s) for s in census.SENSOR_SPECS],
        "batch_contract_checks": contract_checks,
        "frame_prefilter": {
            "status": "DESIGNED_NOT_RUN",
            "method": (
                "1) load static MGRS tile polygons and WRS-2 descending scene "
                "footprints; 2) spatial-intersect the union of coastal cell "
                "polygons; 3) persist deterministic frame lists "
                "(frame_id, system, intersecting_cell_ids) in work/national/census/; "
                "4) frame x year x sensor query matrix derived from those lists."
            ),
            "frame_count": "UNKNOWN (computed only when the static indexes are added)",
        },
        "query_scale": {
            "upper_bound_naive_cell_queries": "FORBIDDEN (would be cells x years x sensors)",
            "batched_query_units": (
                "frame x year x sensor; exact count UNKNOWN until prefilter runs"
            ),
        },
        "linked_cost_model": "docs/data/national/NATIONAL_TIER_MODEL_v0.json",
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(design, ensure_ascii=False, indent=2) + "\n")

    # Tier cost model with measured cell and positive-history counts.
    model = NationalScaleModel(
        n_cells,
        CostAssumptions(positive_history_cells=args.positive_history_cells),
    )
    cost_path = args.out.parent / "NATIONAL_TIER_MODEL_v0.json"
    model.write_json(args.census_years, cost_path)
    print(f"wrote {args.out} and {cost_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
