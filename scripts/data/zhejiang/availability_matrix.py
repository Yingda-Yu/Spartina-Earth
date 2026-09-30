#!/usr/bin/env python
"""Generate the Zhejiang Data Availability Matrix v0 (Issue #7 prep).

Planning scaffold only: the matrix covers 1985 and 1990-2026 for the
three candidate bays. Platform-era columns record nominal SENSOR ERAS
(public mission facts); ROI-level scene counts and every label/field/tide
column stay MISSING/UNKNOWN -- nothing is interpolated and no catalog is
queried here. Real ROI scene counts arrive from the Issue #6 GEE factory
and replace MISSING rows under a new matrix version.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUT = REPO_ROOT / "docs" / "data" / "zhejiang_data_availability_v0.csv"

REGIONS: tuple[tuple[str, str], ...] = (
    ("ZJ-HZB", "Hangzhou Bay"),
    ("ZJ-SMB", "Sanmen Bay"),
    ("ZJ-YQB", "Yueqing Bay"),
)

COLUMNS: tuple[str, ...] = (
    "year", "roi_id", "region",
    "landsat_sensor_nominal", "landsat_roi_scene_count",
    "sentinel1_nominal", "sentinel1_roi_scene_count",
    "sentinel2_nominal", "sentinel2_roi_scene_count",
    "label_available", "label_tier",
    "field_uav_available",
    "management_event_known",
    "tide_metadata",
    "status",
)

MISSING = "MISSING"
UNKNOWN = "UNKNOWN"
UNQUERIED = "NOT_ASSESSED"


def _years() -> list[int]:
    return [1985, *range(1990, 2027)]


def landsat_nominal(year: int) -> str:
    """Nominal operating Landsat missions (mission era, not ROI facts)."""
    if year < 1984:
        return MISSING
    if 1985 <= year <= 1998:
        return "LANDSAT5_TM_NOMINAL"
    if 1999 <= year <= 2002:
        return "LANDSAT5_TM+LANDSAT7_ETM_NOMINAL"
    if 2003 <= year <= 2011:
        return "LANDSAT5_TM+LANDSAT7_ETM_SLC_OFF_NOMINAL"
    if 2012 <= year <= 2013:
        return "LANDSAT7_ETM_SLC_OFF+LANDSAT8_OLI_NOMINAL"
    if 2014 <= year <= 2021:
        return "LANDSAT7_ETM_SLC_OFF+LANDSAT8_OLI_NOMINAL"
    return "LANDSAT7_ETM_SLC_OFF+LANDSAT8_OLI+LANDSAT9_OLI2_NOMINAL"


def s1_nominal(year: int) -> str:
    if year < 2014:
        return MISSING
    if year == 2014:
        return "S1A_COMMISSIONING_NOMINAL"
    return "S1_GRD_IW_NOMINAL_UNQUERIED"


def s2_nominal(year: int) -> str:
    if year < 2015:
        return MISSING
    if year in (2015, 2016):
        return "S2A_L1C_NOMINAL_SR_NOT_AVAILABLE"
    if year == 2017:
        return "S2A_SR_PARTIAL_NOMINAL_UNQUERIED"
    return "S2_SR_HARMONIZED_NOMINAL_UNQUERIED"


def build_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for year in _years():
        for roi_id, region in REGIONS:
            rows.append({
                "year": str(year),
                "roi_id": roi_id,
                "region": region,
                "landsat_sensor_nominal": landsat_nominal(year),
                "landsat_roi_scene_count": MISSING,
                "sentinel1_nominal": s1_nominal(year),
                "sentinel1_roi_scene_count": MISSING,
                "sentinel2_nominal": s2_nominal(year),
                "sentinel2_roi_scene_count": MISSING,
                "label_available": MISSING,
                "label_tier": MISSING,
                "field_uav_available": MISSING,
                "management_event_known": UNKNOWN,
                "tide_metadata": MISSING,
                "status": UNQUERIED,
            })
    return rows


def write_matrix(path: str | Path = DEFAULT_OUT) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(COLUMNS))
        writer.writeheader()
        writer.writerows(build_rows())
    return output


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    written = write_matrix(path)
    print(f"wrote {written} ({len(build_rows())} rows)")


if __name__ == "__main__":
    main()
