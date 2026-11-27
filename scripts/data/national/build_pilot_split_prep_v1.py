#!/usr/bin/env python3
"""Issue #19 Phase L -- split-PREPARATION fields only (no split created).

Emits the spatial/grouping fields a future Issue #20 benchmark split
would consume, for the 20 pilot cells, WITHOUT assigning any cell to
train/val/test and WITHOUT running any leakage-segregation choice. The
actual split decision is deferred to Issue #20 (owner constraint 4:
no split creation / HPO).

Outputs:
* datasets/manifests/national_pilot19_split_prep_v1.csv
* datasets/manifests/national_pilot19_split_prep_v1.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

import pandas as pd  # noqa: E402

from spartina.data.national.grid import (  # noqa: E402
    GridKind,
    parse_cell_id,
)
from spartina.data.national.grid import (  # noqa: E402
    GridSpec as LatticeSpec,
)

PANEL_CSV = REPO_ROOT / "datasets/manifests/national_first_pixel_panel_v1.csv"
SUPPORTS_CSV = (
    REPO_ROOT / "datasets/manifests/national_pilot19_label_supports_v1.csv")
POLICY_JSON = (
    REPO_ROOT / "docs/data/national/PILOT_SILVER_TRAINING_POLICY_v1.json")
OUT_CSV = REPO_ROOT / "datasets/manifests/national_pilot19_split_prep_v1.csv"
OUT_JSON = (
    REPO_ROOT / "datasets/manifests/national_pilot19_split_prep_v1.json")

#: Mirrors spartina.evaluation.splits default; recorded, not invented.
LEAKAGE_BUFFER_M = 250.0
SPLIT_STATUS = "NO_SPLIT_CREATED_ISSUE19"
RECOMMENDED_ROLE = "PILOT_WITNESS_HOLDOUT_CANDIDATE"

GEODATA_YEARS = (1990, 2000, 2015, 2020)
CMSA_YEARS = (2017, 2018, 2019, 2020, 2021)


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


def _present(
    cs: pd.DataFrame, family: str, year: int, support_m: int = 30,
) -> bool:
    try:
        return bool(float(cs.loc[(family, year, support_m),
                                 "positive_area_km2_in_cell"]) > 0.0)
    except KeyError:
        return False


def _window_ok(cs: pd.DataFrame, year: int) -> bool:
    try:
        v = cs.loc[("GEODATA", year, 30), "source_window_overlap"]
        return bool(v) if not pd.isna(v) else False
    except KeyError:
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-csv", default=str(OUT_CSV))
    parser.add_argument("--out-json", default=str(OUT_JSON))
    args = parser.parse_args()

    panel = pd.read_csv(PANEL_CSV)
    supports = pd.read_csv(SUPPORTS_CSV)
    lattice = LatticeSpec(GridKind.CHINA_ALBERS)

    rows: list[dict[str, Any]] = []
    for cell in panel.itertuples(index=False):
        cell_id = str(cell.cell_id)
        ref = parse_cell_id(cell_id)
        xmin, ymin, xmax, ymax = lattice.cell_bounds_projected(
            ref.row, ref.col)
        cs = supports[supports.cell_id == cell_id].set_index(
            ["family", "year", "support_m"])

        gz_values = supports[
            (supports.cell_id == cell_id)
            & (supports.family == "CMSA")]["gridcode0_pixels"].dropna()
        gridcode0_present = bool(any(int(v) > 0 for v in gz_values))

        row = {
            "cell_id": cell_id,
            "albers_row": ref.row,
            "albers_col": ref.col,
            "albers_xmin_m": xmin,
            "albers_ymin_m": ymin,
            "albers_xmax_m": xmax,
            "albers_ymax_m": ymax,
            "cell_size_m": ref.cell_size_m,
            "utm_zone": int((float(cell.center_lon) + 180) // 6 + 1),
            "region_province": cell.region_province,
            "coastal_segment": cell.coastal_segment,
            "label_stratum": cell.label_stratum,
            "agreement_category_2020": cell.agreement_category_2020,
            "spatial_grouping_unit": "W10_CELL",
            "temporal_grouping_rule": (
                "all scenes of one cell across dates stay together"),
            "leakage_check_utility": (
                "spartina.evaluation.splits.assert_spatially_disjoint"),
            "leakage_buffer_m": LEAKAGE_BUFFER_M,
            "cmsa_gridcode0_intersects_cell": gridcode0_present,
            "split_assigned": False,
            "split_status": SPLIT_STATUS,
            "recommended_role": RECOMMENDED_ROLE,
            "recommended_role_basis": (
                "Phase K gate G7 recommendation; owner decides at "
                "Issue #20 setup"),
        }
        for year in GEODATA_YEARS:
            row[f"geodata_window_overlap_{year}"] = _window_ok(cs, year)
            row[f"geodata_positive_in_cell_{year}"] = _present(
                cs, "GEODATA", year)
        for year in CMSA_YEARS:
            row[f"cmsa_positive_in_cell_{year}"] = _present(
                cs, "CMSA", year)
        row["cmssm_positive_in_cell_2020_30m"] = _present(
            cs, "CM-SSM", 2020, 30)
        row["cmssm_positive_in_cell_2020_10m"] = _present(
            cs, "CM-SSM", 2020, 10)
        rows.append(row)

    prep = pd.DataFrame(rows)
    out_csv = Path(args.out_csv)
    prep.to_csv(out_csv, index=False)

    manifest = {
        "product": "national_pilot19_split_prep_v1",
        "issue": 19,
        "phase": "L (split-preparation fields only)",
        "generated_utc": datetime.now(timezone.utc).isoformat(),  # noqa: UP017
        "git_commit": _git_commit(),
        "split_status": SPLIT_STATUS,
        "no_split_statement": (
            "No train/validation/test assignment exists in this product. "
            "split_assigned is False for every cell. Split creation, HPO "
            "and any training are deferred to Issue #20 and require "
            "explicit owner authorization."),
        "grouping": {
            "spatial_unit": "W10_CELL (10 km China Albers lattice cell)",
            "temporal_rule": (
                "scenes of the same cell across dates/sensors are grouped"),
            "buffer_m": LEAKAGE_BUFFER_M,
            "leakage_utility": (
                "spartina.evaluation.splits.assert_spatially_disjoint; "
                "a split manifest plus leakage report are prerequisites "
                "of any future training use"),
        },
        "recommendation": {
            "pilot_cell_role": RECOMMENDED_ROLE,
            "rationale": (
                "keep the 20 controlled pilot cells out of training so "
                "the first national read and the Phase H/I QA remain "
                "uncontaminated (Phase K gate G7); recommendation only"),
        },
        "field_groups": {
            "geometry": [
                "albers_row", "albers_col", "albers_xmin_m",
                "albers_ymin_m", "albers_xmax_m", "albers_ymax_m",
                "cell_size_m", "utm_zone"],
            "region_and_stratum": [
                "region_province", "coastal_segment", "label_stratum",
                "agreement_category_2020"],
            "label_presence": (
                [f"geodata_window_overlap_{y}" for y in GEODATA_YEARS]
                + [f"geodata_positive_in_cell_{y}" for y in GEODATA_YEARS]
                + [f"cmsa_positive_in_cell_{y}" for y in CMSA_YEARS]
                + ["cmssm_positive_in_cell_2020_30m",
                   "cmssm_positive_in_cell_2020_10m"]),
            "split_control": [
                "spatial_grouping_unit", "temporal_grouping_rule",
                "leakage_check_utility", "leakage_buffer_m",
                "split_assigned", "split_status", "recommended_role"],
        },
        "n_rows": len(prep),
        "checksums": {
            "panel_csv_sha256": _sha256(PANEL_CSV),
            "supports_csv_sha256": _sha256(SUPPORTS_CSV),
            "silver_policy_json_sha256": _sha256(POLICY_JSON)
            if POLICY_JSON.exists() else "MISSING_RUN_PHASE_K_FIRST",
            "split_prep_csv_sha256":
                hashlib.sha256(out_csv.read_bytes()).hexdigest(),
        },
    }
    out_json = Path(args.out_json)
    out_json.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8")
    print(json.dumps({
        "rows": len(prep),
        "split_assigned_any": bool(prep.split_assigned.any()),
        "geodata_positive_cells": {
            str(y): int(prep[f"geodata_positive_in_cell_{y}"].sum())
            for y in GEODATA_YEARS},
        "cmsa_positive_cells": {
            str(y): int(prep[f"cmsa_positive_in_cell_{y}"].sum())
            for y in CMSA_YEARS},
        "cmssm_positive_cells_2020":
            int(prep.cmssm_positive_in_cell_2020_30m.sum())}, indent=2))


if __name__ == "__main__":
    main()
