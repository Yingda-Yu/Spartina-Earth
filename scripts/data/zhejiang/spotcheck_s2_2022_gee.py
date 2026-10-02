#!/usr/bin/env python3
"""Deterministic live GEE metadata spot-check for the 2022 S2 funnel audit.

Metadata ONLY: one ``getInfo`` on a tiny collection filtered by exact
system:index values. No pixels, no reduceRegion, no export. The export
guard is installed for the duration.

Selection is deterministic: the 3 lexicographically smallest autumn
(DOY 260-320) 2022 S2 scene ids per bay from the census, de-duplicated.

Output: datasets/manifests/zhejiang_s2_2022_spotcheck_v0.csv
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

from spartina.data.zhejiang.census import install_export_guard  # noqa: E402

YEAR = 2022
DOY_START, DOY_END = 260, 320
BAYS = ("ZJ-HZB", "ZJ-SMB", "ZJ-YQB")
N_PER_BAY = 3
COLLECTION = "COPERNICUS/S2_SR_HARMONIZED"
OUTPUT_NAME = "zhejiang_s2_2022_spotcheck_v0.csv"


def select_spotcheck_scenes(
    census: pd.DataFrame,
    n_per_bay: int = N_PER_BAY,
) -> list[dict[str, Any]]:
    """Deterministic scene sample; pure function, no GEE."""
    chosen: dict[str, dict[str, Any]] = {}
    for bay in BAYS:
        sub = census[(census.roi_id == bay)
                     & (census.sensor == "sentinel2")
                     & (census.year == YEAR)
                     & (census.day_of_year.between(DOY_START, DOY_END))]
        for sid in sorted(sub.scene_id.unique())[:n_per_bay]:
            row = sub[sub.scene_id == sid].iloc[0].to_dict()
            chosen.setdefault(sid, {
                "scene_id": sid,
                "roi_id_hint": bay,
                "tile_ref": row["tile_ref"],
                "census_acquisition_utc": row["acquisition_utc"],
                "census_cloud_fraction": row["scene_cloud_fraction"],
            })
    return [chosen[k] for k in sorted(chosen)]


def run_spotcheck(config_path: Path | None = None) -> pd.DataFrame:
    import ee

    from spartina.data.gee import auth

    cfg_path = config_path or (
        REPO_ROOT / "configs/data/zhejiang_multibay_m21a.yaml")
    config = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    m2 = config["m21a2"]
    census = pd.read_parquet(REPO_ROOT / config["census"]["scene_table_path"])
    supp = pd.read_parquet(REPO_ROOT
                           / m2["s2_datatake_supplement"]["path"])
    sup = supp.set_index("scene_id")
    sample = select_spotcheck_scenes(census)

    auth.initialize()
    restore = install_export_guard(ee)
    try:
        ids = [s["scene_id"] for s in sample]
        col = ee.ImageCollection(COLLECTION).filter(
            ee.Filter.inList("system:index", ids))
        # ONE getInfo on <= 9 metadata-only images
        info = col.getInfo()
    finally:
        restore()
    by_index = {f["id"].split("/")[-1]: f["properties"]
                for f in info["features"]}

    rows: list[dict[str, Any]] = []
    for s in sample:
        props = by_index.get(s["scene_id"])
        if props is None:
            rows.append({**s, "status": "MISSING_IN_GEE",
                         "gee_mgrs_tile": None,
                         "gee_datatake_identifier": None,
                         "supplement_datatake_identifier": None,
                         "gee_time_start": None,
                         "gee_cloud_pct": None,
                         "mgrs_match": False,
                         "datatake_match": False,
                         "date_match": False,
                         "cloud_match": False})
            continue
        sup_row = sup.loc[s["scene_id"]]
        if isinstance(sup_row, pd.DataFrame):
            sup_row = sup_row.iloc[0]
        sup_dt = sup_row["datatake_identifier"]
        gee_dt = props.get("DATATAKE_IDENTIFIER")
        gee_tile = props.get("MGRS_TILE")
        gee_ms = props.get("system:time_start")
        gee_time = (pd.Timestamp(gee_ms, unit="ms", tz="UTC").isoformat()
                    if gee_ms is not None else None)
        gee_cloud = props.get("CLOUDY_PIXEL_PERCENTAGE")
        cen_date = pd.Timestamp(s["census_acquisition_utc"])
        gee_date = pd.Timestamp(gee_ms, unit="ms", tz="UTC") if gee_ms else None
        date_match = bool(gee_date is not None
                          and abs((gee_date - cen_date).total_seconds()) < 86400)
        cloud_match = bool(
            gee_cloud is not None
            and abs(float(gee_cloud)
                    - 100.0 * float(s["census_cloud_fraction"])) <= 0.05)
        checks = {
            "mgrs_match": gee_tile == s["tile_ref"],
            "datatake_match": gee_dt == sup_dt,
            "date_match": date_match,
            "cloud_match": cloud_match,
        }
        rows.append({
            **s,
            "gee_mgrs_tile": gee_tile,
            "gee_datatake_identifier": gee_dt,
            "supplement_datatake_identifier": sup_dt,
            "gee_time_start": gee_time,
            "gee_cloud_pct": gee_cloud,
            **checks,
            "status": "PASS" if all(checks.values()) else "FAIL",
        })
    df = pd.DataFrame(rows)
    out = REPO_ROOT / "datasets/manifests" / OUTPUT_NAME
    df.to_csv(out, index=False)
    return df


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config")
    args = parser.parse_args()
    df = run_spotcheck(Path(args.config) if args.config else None)
    print(df[["scene_id", "roi_id_hint", "mgrs_match", "datatake_match",
              "date_match", "cloud_match", "status"]].to_string(index=False))
    if not (df.status == "PASS").all():
        print("SPOTCHECK_FAILED")
        return 1
    print(f"SPOTCHECK_PASS n={len(df)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
