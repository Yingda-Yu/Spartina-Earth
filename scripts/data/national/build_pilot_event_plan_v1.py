#!/usr/bin/env python3
"""Issue #19 Phase C -- deterministic pilot event plan v1 (metadata only).

Selects exactly one event per cell x anchor slot (plus one per S1 orbit
pass) using the predeclared label-independent policy in
``spartina.data.national.pilot_events`` applied to the FROZEN national
metadata census v0_1 (the checksummed R1 rebuild that supersedes v0:
rebuilt unfiltered S1 funnel, expanded footprint indices, L7 extended
preserved). No GEE calls, no pixel reads, no label inputs.

Outputs:
* datasets/manifests/national_pilot_event_plan_v1.json
* datasets/manifests/national_pilot_event_plan_v1.csv
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
import pandas as pd  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

from spartina.data.national.census_join import s2_event_group_id  # noqa: E402
from spartina.data.national.geometry import cell_polygon_wgs84  # noqa: E402
from spartina.data.national.grid import GridKind, GridSpec, parse_cell_id  # noqa: E402
from spartina.data.national.pilot_events import (  # noqa: E402
    BASIS_LANDSAT_FULL,
    BASIS_LANDSAT_NEAR_FULL,
    BASIS_S2_UNION,
    FULL_COVER,
    NEAR_FULL_NOMINAL_MIN,
    PARTIAL_COVER,
    PASSES,
    POLICY_DOC,
    TIER_NEAR_FULL,
    select_optical,
    select_s1_pass,
)
from spartina.data.national.pilot_panel import (  # noqa: E402
    ANCHOR_SLOTS,
    PANEL_DOMAIN_VERSION,
    SensorYearStatus,
)

PANEL_CSV = REPO_ROOT / "datasets/manifests/national_first_pixel_panel_v1.csv"
CENSUS_DIR = REPO_ROOT / "work/national/census_r1/products"
CELL_EVENTS = CENSUS_DIR / "china_cell_event_census_v0_1.parquet"
SCENE_TABLE = CENSUS_DIR / "china_eo_scene_census_v0_1.parquet"
SUPERSESSION_DOC = (
    REPO_ROOT / "docs/data/national/CHINA_EO_CENSUS_SUPERSESSION_v0_1.json")
MGRS_GPKG = REPO_ROOT / "work/national/footprints/mgrs_china_coast_v0_1.gpkg"
WRS2_GPKG = REPO_ROOT / "work/national/footprints/wrs2_china_coast_v0_1.gpkg"
OUT_JSON = REPO_ROOT / "datasets/manifests/national_pilot_event_plan_v1.json"
OUT_CSV = REPO_ROOT / "datasets/manifests/national_pilot_event_plan_v1.csv"

LANDSAT_SENSORS = ("landsat5", "landsat7", "landsat8")

#: Fingerprints recorded at v0_1 publication; inputs must match or the
#: builder aborts (no silent census drift under a frozen plan). Loaded
#: from the Git-tracked supersession manifest, not retyped.
SUPERSESSION = json.loads(SUPERSESSION_DOC.read_text(encoding="utf-8"))
EXPECTED_FINGERPRINTS: dict[str, str] = dict(
    SUPERSESSION["product_fingerprints_sha256"])


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


def gee_landsat_index(product_id: str) -> str:
    """C02 GEE system:index from the C2 product ID.

    LT05_L2SP_117039_19840502_20200918_02_T1 -> LT05_117039_19840502
    (proven by the M2.1b L8/L9 real exports).
    """
    parts = str(product_id).split("_")
    if len(parts) < 4:
        raise ValueError(f"unexpected Landsat C2 product id: {product_id}")
    return f"{parts[0]}_{parts[2]}_{parts[3]}"


def cell_short(cell_id: str) -> str:
    return cell_id.removeprefix("CNA10K-")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-csv", default=str(OUT_CSV))
    args = parser.parse_args()

    for path, expected in EXPECTED_FINGERPRINTS.items():
        got = _sha256(CENSUS_DIR / path)
        if got != expected:
            raise SystemExit(
                f"frozen census input {path} checksum mismatch: "
                f"expected {expected} got {got}; refusing to build plan")

    panel = pd.read_csv(PANEL_CSV)
    panel_ids = panel["cell_id"].tolist()

    # -- cell polygons (WGS84 bbox of the exact Albers square) -----------
    spec = GridSpec(GridKind.CHINA_ALBERS)
    polys = gpd.GeoDataFrame(
        {"cell_id": panel_ids},
        geometry=[
            cell_polygon_wgs84(spec, *(lambda r: (r.row, r.col))(
                parse_cell_id(cid))) for cid in panel_ids],
        crs=4326)
    cell_polygon = dict(zip(polys["cell_id"], polys.geometry, strict=True))

    # -- frozen census v0_1 tables ---------------------------------------
    ce = pd.read_parquet(CELL_EVENTS)
    ce = ce[ce["cell_id"].isin(panel_ids)].copy()
    scenes = pd.read_parquet(SCENE_TABLE)
    scene_lookup = {
        sensor: scenes[scenes["sensor"] == sensor].set_index("event_id")
        for sensor in (*LANDSAT_SENSORS, "sentinel1", "sentinel2")}

    # -- nominal WRS-2 frame geometries (coverage fractions) -------------
    wrs = gpd.read_file(WRS2_GPKG)[["path", "row", "geometry"]].to_crs(4326)
    frame_geom = {
        (int(r.path), int(r.row)): r.geometry
        for r in wrs.itertuples(index=False)}

    # -- cell <-> MGRS nominal tile intersects (S2 member discovery) -----
    mgrs = gpd.read_file(MGRS_GPKG)[["mgrs_tile", "geometry"]]
    tile_geom = dict(zip(mgrs["mgrs_tile"], mgrs.geometry, strict=True))
    cell_tiles = gpd.sjoin(
        polys, mgrs, how="left", predicate="intersects")[
        ["cell_id", "mgrs_tile"]].dropna()
    tiles_by_cell: dict[str, set[str]] = {
        cid: set(g["mgrs_tile"]) for cid, g in cell_tiles.groupby("cell_id")}

    s2 = scenes[scenes["sensor"] == "sentinel2"].copy()
    s2["utc_day"] = pd.to_datetime(
        s2["utc"], utc=True, format="ISO8601").dt.date.astype(str)
    s2["s2_event_group"] = [
        s2_event_group_id(str(d), str(day))
        for d, day in zip(s2["datatake_identifier"], s2["utc_day"],
                          strict=True)]

    rows: list[dict[str, Any]] = []

    def add_row(cell_id: str, slot: Any, status: SensorYearStatus,
                detail: dict[str, Any], sensor_used: str,
                variant: str = "") -> None:
        ev = detail.get("event", {}) if detail else {}
        abbr = {
            "landsat5": "L5", "landsat7": "L7", "landsat8": "L8",
            "sentinel1": "S1", "sentinel2": "S2"}[sensor_used]
        suffix = f"_{variant}" if variant else ""
        product_id = (
            f"NP19_{cell_short(cell_id)}_{abbr}_"
            f"{slot.year}{suffix}")
        tier = detail.get("coverage_tier", "") if detail else ""
        basis = ev.get("coverage_basis", "")
        if not basis and tier == TIER_NEAR_FULL:
            basis = BASIS_LANDSAT_NEAR_FULL
        rows.append({
            "product_id": product_id if status == SensorYearStatus.SELECTED
            else "",
            "cell_id": cell_id,
            "sensor": sensor_used,
            "year": slot.year,
            "priority": slot.priority,
            "variant": variant or ("PER_PASS" if slot.per_pass else "DEFAULT"),
            "status": status.value,
            "event_id": ev.get("event_id", ""),
            "event_utc": ev.get("utc", ""),
            "doy": ev.get("doy", ""),
            "season_tag": ev.get("season_tag", ""),
            "coverage": ev.get("coverage", ""),
            "coverage_tier": tier,
            "coverage_basis": basis,
            "coverage_fraction": ev.get("coverage_fraction", ""),
            "cloud_fraction": ev.get("cloud_fraction", ""),
            "pass": ev.get("pass", ""),
            "relative_orbit": ev.get("relative_orbit", ""),
            "platform": ev.get("platform", "") or ev.get("spacecraft", ""),
            "scene_ids": ev.get("scene_ids", ""),
            "product_ids_source": ev.get("product_ids", ""),
            "mgrs_tiles": ev.get("mgrs_tiles", ""),
            "wrs_path": ev.get("wrs_path", ""),
            "wrs_row": ev.get("wrs_row", ""),
            "member_scene_count": ev.get("member_scene_count", ""),
            "selection_reason": detail.get("reason", ""),
            "selection_detail": json.dumps(
                {k: v for k, v in detail.items() if k not in ("event", "reason")},
                ensure_ascii=False, sort_keys=True),
        })

    def landsat_pool(cell_id: str, sensor: str, year: int) -> pd.DataFrame:
        events = ce[(ce["cell_id"] == cell_id) & (ce["sensor"] == sensor)
                    & (ce["year"] == year)].copy()
        if events.empty:
            return events
        attrs = scene_lookup[sensor]
        meta = attrs.loc[attrs.index.intersection(events["event_id"])]
        events = events.merge(
            meta[["scene_id", "product_id", "cloud_cover",
                  "wrs_path", "wrs_row", "l7_era"]],
            on="event_id", how="left")
        events["cloud_fraction"] = (
            pd.to_numeric(events["cloud_cover"], errors="coerce") / 100.0)
        events["scene_ids"] = [
            gee_landsat_index(pid) if isinstance(pid, str) else ""
            for pid in events["product_id"]]
        events["product_ids"] = events["product_id"].fillna("")
        # Exact nominal frame coverage fraction (deterministic, offline).
        cg = cell_polygon[cell_id]
        fractions: list[float] = []
        bases: list[str] = []
        for r in events.itertuples():
            if r.coverage == FULL_COVER:
                fractions.append(1.0)
                bases.append(BASIS_LANDSAT_FULL)
                continue
            geom = frame_geom.get((int(r.wrs_path), int(r.wrs_row)))
            frac = (float(geom.intersection(cg).area / cg.area)
                    if geom is not None else 0.0)
            fractions.append(frac)
            bases.append(
                BASIS_LANDSAT_NEAR_FULL
                if (frac >= NEAR_FULL_NOMINAL_MIN
                    and str(r.geometry_basis).startswith("WRS2"))
                else str(r.geometry_basis))
        events["coverage_fraction"] = fractions
        events["coverage_basis"] = bases
        return events

    def s2_pool(cell_id: str, year: int) -> pd.DataFrame:
        events = ce[(ce["cell_id"] == cell_id) & (ce["sensor"] == "sentinel2")
                    & (ce["year"] == year)].copy()
        if events.empty:
            return events
        tiles = tiles_by_cell.get(cell_id, set())
        gran = s2[s2["mgrs_tile"].isin(tiles)
                  & (s2["year"] == year)
                  & (s2["s2_event_group"].isin(events["event_id"]))]
        cell_geom = cell_polygon[cell_id]
        coverage_rows: list[dict[str, object]] = []
        for group_id, g in gran.groupby("s2_event_group"):
            member_tiles = sorted(set(g["mgrs_tile"]))
            union_geom = unary_union(
                [tile_geom[t] for t in member_tiles if t in tile_geom])
            covers_cell = bool(union_geom.covers(cell_geom))
            coverage_rows.append({
                "s2_event_group": group_id,
                "cloud_fraction":
                    float(pd.to_numeric(
                        g["cloudy_pixel_percent"],
                        errors="coerce").max()) / 100.0,
                "scene_ids": "|".join(sorted(g["system_index"])),
                "product_ids": "|".join(sorted(g["product_id"])),
                "mgrs_tiles": "|".join(member_tiles),
                "member_scene_count": int(g["system_index"].nunique()),
                "platform": "|".join(sorted(
                    {str(v) for v in g["spacecraft_name"]
                     if pd.notna(v)})),
                "coverage": (FULL_COVER if covers_cell else PARTIAL_COVER),
                "coverage_basis": BASIS_S2_UNION,
            })
        agg = pd.DataFrame(coverage_rows).set_index("s2_event_group")
        # Event coverage is the union of its same-datatake members:
        # multi-tile / cross-zone cells are FULL when the mosaic covers
        # them (same date, same datatake -- no cross-date composite).
        # member_scene_count is recomputed from the granule members, so
        # the census-level column is dropped to avoid merge suffixing.
        return events.drop(
            columns=["coverage", "member_scene_count"]).merge(
            agg, left_on="event_id", right_index=True, how="left")

    for cell_id in panel_ids:
        for slot in ANCHOR_SLOTS:
            if slot.sensor == "sentinel1":
                scenes_all = ce[(ce["cell_id"] == cell_id)
                                & (ce["sensor"] == "sentinel1")
                                & (ce["year"] == slot.year)]
                attrs = scene_lookup["sentinel1"]
                meta = attrs.loc[
                    attrs.index.intersection(scenes_all["event_id"])]
                scenes_y = scenes_all.merge(
                    meta[["scene_id", "pass", "relative_orbit", "platform",
                          "instrument_mode", "polarization"]],
                    on="event_id", how="left")
                scenes_y["scene_ids"] = scenes_y["scene_id"].fillna("")
                scenes_y["product_ids"] = scenes_y["scene_id"].fillna("")
                for pass_direction in PASSES:
                    s1_status, s1_detail = select_s1_pass(
                        scenes_y, pass_direction)
                    variant = f"{pass_direction[0]}"  # A / D
                    add_row(cell_id, slot, s1_status, s1_detail,
                            sensor_used=slot.sensor, variant=variant)
                continue

            # Optical slots (with the 2000 L5 -> L7 fallback chain).
            sensor_chain = (slot.sensor, *slot.fallback_sensors)
            status = SensorYearStatus.NO_SCENE
            detail: dict[str, Any] = {"reason": "empty chain"}
            sensor_used = slot.sensor
            for sensor in sensor_chain:
                pool = (s2_pool(cell_id, slot.year)
                        if sensor == "sentinel2"
                        else landsat_pool(cell_id, sensor, slot.year))
                status, detail = select_optical(pool)
                sensor_used = sensor
                if status == SensorYearStatus.SELECTED:
                    break
            add_row(cell_id, slot, status, detail, sensor_used=sensor_used)

    plan = pd.DataFrame(rows)
    out_csv = Path(args.out_csv)
    plan.to_csv(out_csv, index=False)

    summary = (
        plan[plan["status"] == SensorYearStatus.SELECTED.value]
        .groupby(["sensor", "year", "variant", "coverage_tier"])
        .size().rename("selected_products").reset_index())
    state_matrix = (
        plan.groupby(["sensor", "year", "variant", "status"]).size()
        .rename("n").reset_index())

    manifest = {
        "product": "national_pilot_event_plan_v1",
        "issue": 19,
        "generated_utc": datetime.now(timezone.utc).isoformat(),  # noqa: UP017
        "git_commit": _git_commit(),
        "domain_version": PANEL_DOMAIN_VERSION,
        "census_version": "v0_1",
        "census_supersedes": "v0",
        "census_supersession_doc": SUPERSESSION_DOC.name,
        "census_supersession_generated_utc":
            SUPERSESSION.get("generated_utc"),
        "census_supersession_change_tokens":
            SUPERSESSION.get("change_reason_tokens"),
        "panel_manifest": PANEL_CSV.name,
        "status": "PLANNED_NOT_EXPORTED; metadata only; no GEE calls made",
        "selection_policy": POLICY_DOC,
        "anchor_slots": [
            {"sensor": s.sensor, "year": s.year, "priority": s.priority,
             "fallback_sensors": list(s.fallback_sensors),
             "per_pass": s.per_pass, "note": s.note}
            for s in ANCHOR_SLOTS],
        "gee_index_rules": {
            "landsat_c02": (
                "system:index = <PLATFORM>_<PATHROW>_<YYYYMMDD> derived from "
                "C2 LANDSAT_PRODUCT_ID; proven by M2.1b L8/L9 exports"),
            "sentinel2": "system:index from census system_index (granule)",
            "sentinel1": "system:index = full S1 GRD product identifier",
        },
        "selected_products_summary": summary.to_dict(orient="records"),
        "state_matrix": state_matrix.to_dict(orient="records"),
        "n_plan_rows": len(plan),
        "n_selected": int(
            (plan["status"] == SensorYearStatus.SELECTED.value).sum()),
        "rows": rows,
        "checksums": {
            "panel_csv_sha256": _sha256(PANEL_CSV),
            "cell_event_census_v0_1_sha256": _sha256(CELL_EVENTS),
            "scene_census_v0_1_sha256": _sha256(SCENE_TABLE),
            "wrs2_footprints_v0_1_sha256": _sha256(WRS2_GPKG),
            "mgrs_footprints_v0_1_sha256": _sha256(MGRS_GPKG),
            "plan_csv_sha256":
                hashlib.sha256(out_csv.read_bytes()).hexdigest(),
        },
    }
    out_json = Path(args.out_json)
    out_json.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=False),
        encoding="utf-8")
    print(json.dumps({
        "plan_rows": len(plan),
        "selected": manifest["n_selected"],
        "summary": manifest["selected_products_summary"],
        "state_counts": plan["status"].value_counts().to_dict()},
        indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
