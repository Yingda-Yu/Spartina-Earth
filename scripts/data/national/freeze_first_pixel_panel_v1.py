#!/usr/bin/env python3
"""Issue #19 Phase A -- freeze the 20-cell national real-pixel panel v1.

Joins the preselected panel
(``docs/data/national/FIRST_PIXEL_PILOT_DESIGN_v0.json``; selected before
any pixel evidence existed) to the frozen ``W10_DOMAIN_V1_CORE_FROZEN``
registry and refuses to proceed unless every cell is KEEP + production
eligible.  Writes the frozen panel manifest and a flat per-cell CSV:

* ``datasets/manifests/national_first_pixel_panel_v1.json``
* ``datasets/manifests/national_first_pixel_panel_v1.csv``

Province attribution follows the Issue #18 R1 source-independent rule
(Natural Earth 10m admin-1 v5.1.1; centroid-in-province, else unique
nearest province <=25 km with >300 m second-province margin, else
UNKNOWN). EO availability is counted from the frozen national metadata
census (no GEE calls). This script never substitutes a cell.
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

import geopandas as gpd  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from shapely.geometry import Point  # noqa: E402

from spartina.data.national.grid import CHINA_ALBERS_PROJ4  # noqa: E402
from spartina.data.national.pilot_panel import (  # noqa: E402
    ANCHOR_SLOTS,
    PANEL_DOMAIN_VERSION,
    PanelError,
    coastal_segment,
    label_agreement_category_2020,
    verify_panel,
)

PANEL_DESIGN = (
    REPO_ROOT / "docs" / "data" / "national"
    / "FIRST_PIXEL_PILOT_DESIGN_v0.json")
REGISTRY_CSV = (
    REPO_ROOT / "datasets" / "manifests"
    / "china_coastal_cells_v1_1_core_frozen.csv")
V1_CANDIDATE_CSV = (
    REPO_ROOT / "datasets" / "manifests"
    / "china_coastal_cells_v1_candidate.csv")
CELLS_CSV = (
    REPO_ROOT / "work" / "national" / "domain"
    / "cells_china_albers_W10000.csv")
STRATA_CSV = (
    REPO_ROOT / "work" / "national" / "strata"
    / "strata_china_albers_W10000.csv")
CENSUS_PARQUET = (
    REPO_ROOT / "work" / "national" / "census"
    / "china_cell_event_census_v0.parquet")
NE_ADMIN1 = (
    REPO_ROOT / "work" / "external" / "naturalearth_10m_admin1"
    / "extracted" / "ne_10m_admin_1_states_provinces.shp")
S30_CELLS = REPO_ROOT / "work/issue18/derived/s30_cells.csv"
S10_CELLS = REPO_ROOT / "work/issue18/derived/s10_cells.csv"

OUT_JSON = REPO_ROOT / "datasets/manifests/national_first_pixel_panel_v1.json"
OUT_CSV = REPO_ROOT / "datasets/manifests/national_first_pixel_panel_v1.csv"

V1_DOMAIN_STATUSES = (
    "KEEP_MAINLAND_COASTAL", "KEEP_ISLAND_COASTAL", "PROVISIONAL_UNRESOLVED")
NEAREST_PROVINCE_MAX_M = 25_000.0
SECOND_PROVINCE_MARGIN_M = 300.0
CHINA_ISO = "CN"


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


def _v1_domain_order() -> pd.DataFrame:
    """Reproduce the Issue #18 3,021-cell domain frame and cell_idx."""
    frame = pd.read_csv(CELLS_CSV)
    membership = pd.read_csv(V1_CANDIDATE_CSV)[
        ["cell_id", "membership_v1_candidate"]]
    frame = frame.merge(membership, on="cell_id", how="left")
    frame = frame[
        frame["membership_v1_candidate"].isin(V1_DOMAIN_STATUSES)
    ].copy()
    frame["cell_idx"] = np.arange(len(frame))
    return frame


def attribute_provinces(panel: pd.DataFrame) -> dict[str, dict[str, Any]]:
    """Centroid-in-province, else unique nearest <=25 km (R1 rule)."""
    provinces = gpd.read_file(NE_ADMIN1)
    cn = provinces[
        (provinces["iso_a2"] == CHINA_ISO)
        | (provinces["admin"] == "China")
    ].copy()
    cn = cn[["name_en", "geometry"]].to_crs(3857)
    cn = cn[~cn["name_en"].isin(
        ("Paracel Islands", "Spratly Islands", "Taiwan"))]
    pts = gpd.GeoDataFrame(
        panel[["cell_id", "center_lon", "center_lat"]].copy(),
        geometry=[
            Point(r.center_lon, r.center_lat)
            for r in panel.itertuples()],
        crs=4326).to_crs(3857)
    joined = gpd.sjoin(
        pts, cn, how="left", predicate="within").drop(
        columns=["index_right"], errors="ignore")
    out: dict[str, dict[str, Any]] = {}
    cn_geoms = list(zip(cn["name_en"], cn.geometry, strict=True))
    for r in joined.itertuples():
        if isinstance(r.name_en, str) and r.name_en:
            out[r.cell_id] = {
                "province": r.name_en, "rule": "CENTROID_WITHIN_PROVINCE"}
            continue
        pt = r.geometry
        dists = sorted(
            ((float(pt.distance(geom)), name)
             for name, geom in cn_geoms))
        nearest_d, nearest_name = dists[0]
        second_d = dists[1][0]
        if (nearest_d <= NEAREST_PROVINCE_MAX_M
                and second_d - nearest_d > SECOND_PROVINCE_MARGIN_M):
            out[r.cell_id] = {
                "province": nearest_name,
                "rule": "UNIQUE_NEAREST_PROVINCE_LE_25KM",
                "nearest_distance_m": round(nearest_d, 1),
                "second_province_margin_m": round(
                    second_d - nearest_d, 1)}
        else:
            out[r.cell_id] = {
                "province": "UNKNOWN", "rule": "UNKNOWN",
                "nearest_distance_m": round(nearest_d, 1)}
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-csv", default=str(OUT_CSV))
    args = parser.parse_args()

    design = json.loads(PANEL_DESIGN.read_text(encoding="utf-8"))
    selected = design["selected_cells"]
    panel_ids = [c["cell_id"] for c in selected]

    registry = pd.read_csv(REGISTRY_CSV)
    verify_panel(
        panel_ids,
        set(registry["cell_id"]),
        dict(zip(registry["cell_id"], registry["membership_v1_1"],
                 strict=True)),
        dict(zip(registry["cell_id"], registry["production_eligible"],
                 strict=True)))

    reg = registry.set_index("cell_id")
    strata = pd.read_csv(STRATA_CSV).set_index("cell_id")

    # --- 2020 three-product context (Issue #18 cell_idx universe) --------
    domain = _v1_domain_order().set_index("cell_id")
    s30 = pd.read_csv(S30_CELLS).set_index("cell_idx")
    s10 = pd.read_csv(S10_CELLS).set_index("cell_idx")

    # --- EO availability over the anchor slots (frozen metadata census) --
    census = pd.read_parquet(CENSUS_PARQUET,
                             columns=["cell_id", "sensor", "year", "event_id"])
    anchor_years = sorted({slot.year for slot in ANCHOR_SLOTS})
    counts = (census[census["cell_id"].isin(panel_ids)
                     & census["year"].isin(anchor_years)]
              .groupby(["cell_id", "sensor", "year"])["event_id"]
              .nunique().rename("n_events").reset_index())
    avail: dict[tuple[str, str, int], int] = {
        (r.cell_id, r.sensor, int(r.year)): int(r.n_events)
        for r in counts.itertuples()}

    panel = pd.DataFrame([
        {"cell_id": c["cell_id"],
         "center_lon": c["center_lon"],
         "center_lat": c["center_lat"],
         "design_land_class": c["land_class"],
         "design_stratum": c["exclusive_stratum"],
         "reason_for_inclusion": c["selected_for"]}
        for c in selected])
    provinces = attribute_provinces(panel)

    rows: list[dict[str, Any]] = []
    for c in selected:
        cid = c["cell_id"]
        rr = reg.loc[cid]
        st = strata.loc[cid]
        cidx = int(domain.loc[cid, "cell_idx"])
        g30 = float(s30.loc[cidx, "g"]) if cidx in s30.index else 0.0
        c30 = float(s30.loc[cidx, "c"]) if cidx in s30.index else 0.0
        m30 = float(s30.loc[cidx, "m"]) if cidx in s30.index else 0.0
        c10 = float(s10.loc[cidx, "c"]) if cidx in s10.index else 0.0
        m10 = float(s10.loc[cidx, "m"]) if cidx in s10.index else 0.0
        prov = provinces[cid]
        slot_counts = {
            f"{slot.sensor}_{slot.year}":
            avail.get((cid, slot.sensor, slot.year), 0)
            for slot in ANCHOR_SLOTS}
        rows.append({
            "cell_id": cid,
            "domain_version": PANEL_DOMAIN_VERSION,
            "membership_v1_1": rr["membership_v1_1"],
            "production_eligible": bool(rr["production_eligible"]),
            "region_province": prov["province"],
            "region_rule": prov["rule"],
            "coastal_segment": coastal_segment(prov["province"]),
            "land_class_frozen": rr["island_class"],
            "design_land_class": c["land_class"],
            "label_stratum": c["exclusive_stratum"],
            "silver_2015_positive": bool(st["silver_2015_positive"]),
            "cmsa_positive_history": bool(st["cmsa_positive_history"]),
            "cmssm_2020_positive_stratum": bool(st["cmssm_2020_positive"]),
            "geodata_2020_positive_30m": g30 > 0.0,
            "cmsa_2020_positive_30m": c30 > 0.0,
            "cmssm_2020_positive_30m": m30 > 0.0,
            "cmsa_2020_positive_10m": c10 > 0.0,
            "cmssm_2020_positive_10m": m10 > 0.0,
            "agreement_category_2020": label_agreement_category_2020(
                g30 > 0.0, c30 > 0.0, m30 > 0.0),
            "geodata_2020_area_km2_30m": round(g30 * 900.0 / 1e6, 4),
            "cmsa_2020_area_km2_30m": round(c30 * 900.0 / 1e6, 4),
            "cmssm_2020_area_km2_30m": round(m30 * 900.0 / 1e6, 4),
            "center_lon": c["center_lon"],
            "center_lat": c["center_lat"],
            "n_wrs_frames_design": c["n_wrs_frames"],
            "n_mgrs_tiles_design": c["n_mgrs_tiles"],
            "n_mgrs_zones_design": c["n_mgrs_zones"],
            "reason_for_inclusion": c["selected_for"],
            **slot_counts,
        })

    panel_df = pd.DataFrame(rows)
    out_csv = Path(args.out_csv)
    panel_df.to_csv(out_csv, index=False)

    checksums = {
        "panel_design_v0_sha256": _sha256(PANEL_DESIGN),
        "registry_v1_1_csv_sha256": _sha256(REGISTRY_CSV),
        "v1_candidate_csv_sha256": _sha256(V1_CANDIDATE_CSV),
        "cells_csv_sha256": _sha256(CELLS_CSV),
        "strata_csv_sha256": _sha256(STRATA_CSV),
        "census_v0_parquet_sha256": _sha256(CENSUS_PARQUET),
        "s30_cells_csv_sha256": _sha256(S30_CELLS),
        "s10_cells_csv_sha256": _sha256(S10_CELLS),
        "panel_csv_sha256": hashlib.sha256(
            out_csv.read_bytes()).hexdigest(),
    }
    manifest = {
        "product": "national_first_pixel_panel_v1",
        "issue": 19,
        "generated_utc": datetime.now(timezone.utc).isoformat(),  # noqa: UP017
        "git_commit": _git_commit(),
        "domain_version": PANEL_DOMAIN_VERSION,
        "registry": REGISTRY_CSV.name,
        "preflight": {
            "n_panel_cells": len(panel_ids),
            "all_exist_in_v1_1_registry": True,
            "all_keep": True,
            "all_production_eligible": True,
            "cell_ids_preserved_from_design_v0": panel_ids,
            "no_substitution": True,
        },
        "region_attribution": {
            "source": "Natural Earth 10m admin-1 v5.1.1",
            "rule": ("centroid-in-province; else unique nearest province "
                     "<=25 km with >300 m second-province margin; else "
                     "UNKNOWN (never forced)"),
        },
        "anchor_slots": [
            {"sensor": s.sensor, "year": s.year, "priority": s.priority,
             "note": s.note} for s in ANCHOR_SLOTS],
        "eo_availability_basis": (
            "work/national/census/china_cell_event_census_v0.parquet; "
            "counts are distinct intersecting events, not exported products"),
        "cells": rows,
        "checksums": checksums,
        "china_albers_proj4": CHINA_ALBERS_PROJ4,
    }
    out_json = Path(args.out_json)
    out_json.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=False),
        encoding="utf-8")
    print(json.dumps({
        "product": manifest["product"],
        "n_cells": len(rows),
        "segments": panel_df["coastal_segment"].value_counts().to_dict(),
        "provinces": panel_df["region_province"].value_counts().to_dict(),
        "out_json": str(out_json), "out_csv": str(out_csv)},
        indent=2, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except PanelError as exc:
        print(f"PANEL_PREFLIGHT_STOP: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
