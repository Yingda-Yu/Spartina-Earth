#!/usr/bin/env python3
"""M2.1b Issue #13 -- live GEE event discovery for the selected cells.

METADATA + GEOMETRY ONLY. This script creates ZERO export tasks:

* queries the three real collections (S2 SR harmonized, Landsat 8/9 C2
  L2, S1 GRD IW) once each against the UNION of the selected 10 km
  cells, over the proposed autumn_primary_v1 DOY window;
* measures coverage from each scene's ACTUAL per-scene geometry
  locally (shapely), never from representative frames;
* groups S2 scenes by the real DATATAKE_IDENTIFIER and applies the
  corrected R1 gates (union coverage >= 0.99; cloud <= 0.30 over the
  scenes that actually intersect the cell);
* plans deterministic products: one clearest S2 event per cell, up to
  two additional same-datatake multi-tile events if encountered, the
  first naturally-eligible L8 and L9 scene, and the first eligible S1
  scene per orbit direction (passes never mixed).

Outputs a signed event plan consumed by the export driver, plus a full
evidence dump under ignored work/m21b/. Failures (no eligible event for
a stratum) go into the ledger -- they never become silent substitutions.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

import pandas as pd  # noqa: E402
import pyproj  # noqa: E402
from shapely.geometry import box, mapping, shape  # noqa: E402
from shapely.geometry.base import BaseGeometry  # noqa: E402
from shapely.ops import transform as shp_transform  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

from spartina.data.gee.auth import configured_project, initialize  # noqa: E402
from spartina.data.gee.provenance import git_context, sha256_file  # noqa: E402
from spartina.data.gee.selection import canonical_fingerprint  # noqa: E402
from spartina.data.zhejiang import m21b_pilot as pilot  # noqa: E402
from spartina.data.zhejiang.m21b_pilot import (  # noqa: E402
    AUTUMN_PRIMARY_V1_DOY_END,
    AUTUMN_PRIMARY_V1_DOY_START,
    COVERAGE_MIN,
    PILOT_YEAR,
    SCENE_CLOUD_MAX,
    EventEligibility,
    SceneCoverage,
    evaluate_optical_group,
    first_eligible,
    first_s1_per_pass,
    pick_extra_multitile_event,
    pick_primary_s2_event,
)

CELLS_CSV = REPO_ROOT / "datasets/manifests/zhejiang_m21b_pilot_cells_v0.csv"
CELL_REGISTRY = REPO_ROOT / "datasets/manifests/zhejiang_analysis_cells_v0.csv"
WORK_DIR = REPO_ROOT / "work" / "m21b"
OUT_PLAN_CSV = REPO_ROOT / "datasets/manifests/zhejiang_m21b_pilot_event_plan_v0.csv"
OUT_PLAN_JSON = REPO_ROOT / "datasets/manifests/zhejiang_m21b_pilot_event_plan_v0.json"

CRS = "EPSG:32651"
MAX_EXTRA_MULTITILE = 2
PLANNED_BYTES_HARD_CAP = 10 * 1024**3

_TO_UTM = pyproj.Transformer.from_crs(4326, 32651, always_xy=True).transform
_TO_WGS = pyproj.Transformer.from_crs(32651, 4326, always_xy=True).transform


def _iso(ms: Any) -> str:
    return datetime.fromtimestamp(int(ms) / 1000.0, tz=UTC).isoformat()


def _doy(ms: Any) -> int:
    return datetime.fromtimestamp(int(ms) / 1000.0, tz=UTC).timetuple().tm_yday


def _to_utm_geom(geojson: dict[str, Any]) -> BaseGeometry:
    return shp_transform(_TO_UTM, shape(geojson))


def _window_dates() -> tuple[str, str]:
    jan1 = datetime(PILOT_YEAR, 1, 1, tzinfo=UTC)
    start = jan1 + timedelta(days=AUTUMN_PRIMARY_V1_DOY_START - 1)
    end = jan1 + timedelta(days=AUTUMN_PRIMARY_V1_DOY_END - 1)
    return ((start - timedelta(days=1)).date().isoformat(),
            (end + timedelta(days=1)).date().isoformat())


def load_cell_boxes() -> dict[str, BaseGeometry]:
    selected = pd.read_csv(CELLS_CSV)["cell_id"].tolist()
    reg = pd.read_csv(CELL_REGISTRY)
    boxes: dict[str, BaseGeometry] = {}
    for cid in selected:
        row = reg[(reg["cell_id"] == cid)
                  & (reg["cell_size_m"] == 10000)].iloc[0]
        boxes[cid] = box(float(row["westx_easting_m"]),
                         float(row["southy_northing_m"]),
                         float(row["eastx_easting_m"]),
                         float(row["northy_northing_m"]))
    return boxes


def union_region_wgs(boxes: dict[str, BaseGeometry]) -> dict[str, Any]:
    union = unary_union(list(boxes.values()))
    return dict(mapping(shp_transform(_TO_WGS, union)))


def materialize(ee: Any, col: Any) -> tuple[list[dict[str, Any]], float]:
    """Two-pass metadata fetch: properties + ACTUAL per-scene geometry.

    ImageCollection.getInfo omits image geometry; a mapped FeatureCollection
    carrying img.geometry() returns the real footprints in one extra call.
    """
    t0 = time.time()
    features = col.getInfo().get("features", [])
    fc = ee.FeatureCollection(col.map(
        lambda img: ee.Feature(
            img.geometry(), {"sid": img.get("system:index")})))
    geom_info = fc.getInfo().get("features", [])
    geom_by_id = {str(f["properties"]["sid"]): f["geometry"]
                  for f in geom_info if f.get("geometry")}
    missing = 0
    for f in features:
        sid = str(f["properties"]["system:index"])
        geom = geom_by_id.get(sid)
        if geom is None:
            missing += 1
        else:
            f["geometry"] = geom
    elapsed = time.time() - t0
    if missing:
        print(f"[discover] WARNING {missing} scenes without geometry")
    return features, elapsed


def scene_geoms(features: list[dict[str, Any]]) -> dict[str, BaseGeometry]:
    out: dict[str, BaseGeometry] = {}
    for f in features:
        geom = f.get("geometry")
        if not geom:
            continue
        out[f["properties"]["system:index"]] = _to_utm_geom(geom)
    return out


def per_cell_scenes(
    features: list[dict[str, Any]], sensor: str,
    cell_boxes: dict[str, BaseGeometry],
    geoms: dict[str, BaseGeometry],
) -> dict[str, list[SceneCoverage]]:
    """Intersect every ACTUAL scene geometry with every cell."""
    result: dict[str, list[SceneCoverage]] = {cid: [] for cid in cell_boxes}
    cell_area = 10_000.0 * 10_000.0
    for f in features:
        p = f["properties"]
        sid = str(p["system:index"])
        utc = _iso(p.get("system:time_start"))
        doy = _doy(p.get("system:time_start"))
        sgeom = geoms[sid]
        for cid, cbox in cell_boxes.items():
            if not sgeom.intersects(cbox):
                continue
            cov = float(sgeom.intersection(cbox).area / cell_area)
            if sensor == "sentinel2":
                cloud = p.get("CLOUDY_PIXEL_PERCENTAGE")
                rec = SceneCoverage(
                    scene_id=sid, utc=utc, doy=doy,
                    coverage_fraction=round(cov, 6),
                    cloud_fraction=(round(float(cloud) / 100.0, 6)
                                   if cloud is not None else None),
                    mgrs_tile=p.get("MGRS_TILE"),
                    datatake_identifier=p.get("DATATAKE_IDENTIFIER"),
                    extra={"product_id": p.get("PRODUCT_ID")})
            elif sensor in ("landsat8", "landsat9"):
                cloud = p.get("CLOUD_COVER")
                rec = SceneCoverage(
                    scene_id=sid, utc=utc, doy=doy,
                    coverage_fraction=round(cov, 6),
                    cloud_fraction=(round(float(cloud) / 100.0, 6)
                                   if cloud is not None else None),
                    extra={
                        "cloud_cover_land_fraction": (
                            round(float(p["CLOUD_COVER_LAND"]) / 100.0, 6)
                            if p.get("CLOUD_COVER_LAND") is not None else None),
                        "wrs_path": p.get("WRS_PATH"),
                        "wrs_row": p.get("WRS_ROW"),
                        "landsat_product_id": p.get("LANDSAT_PRODUCT_ID"),
                        "spacecraft_id": p.get("SPACECRAFT_ID"),
                        "collection_category": p.get("COLLECTION_CATEGORY")})
            elif sensor == "sentinel1":
                rec = SceneCoverage(
                    scene_id=sid, utc=utc, doy=doy,
                    coverage_fraction=round(cov, 6),
                    cloud_fraction=None,
                    pass_direction=p.get("orbitProperties_pass"),
                    relative_orbit=p.get("relativeOrbitNumber_start"),
                    extra={
                        "product_identifier": p.get("productIdentifier"),
                        "platform": p.get("platform_number")
                        or p.get("SPACECRAFT_NAME"),
                        "instrument_mode": p.get("instrumentMode"),
                        "polarizations": p.get(
                            "transmitterReceiverPolarisation"),
                        "resolution_meters": p.get("resolution_meters")})
            else:  # pragma: no cover - defensive
                raise ValueError(f"unknown sensor {sensor}")
            result[cid].append(rec)
    return result


def s2_events_for_cell(
    cid: str, scenes: list[SceneCoverage],
    geoms: dict[str, BaseGeometry], cbox: BaseGeometry,
) -> list[dict[str, Any]]:
    groups: dict[str, list[SceneCoverage]] = {}
    for s in scenes:
        groups.setdefault(s.datatake_identifier or f"UNKNOWN_{s.scene_id}",
                          []).append(s)
    events: list[dict[str, Any]] = []
    cell_area = cbox.area
    for datatake, members in sorted(groups.items()):
        dates = {m.utc[:10] for m in members}
        union_cov = float(unary_union(
            [geoms[m.scene_id].intersection(cbox) for m in members]
        ).area / cell_area)
        ev = evaluate_optical_group(
            cell_id=cid, sensor="sentinel2", group_key=datatake,
            scenes=members, union_coverage=union_cov)
        events.append({
            "event_key": ev.event_key,
            "event_utc": ev.event_utc,
            "doy": ev.doy,
            "eligible": ev.eligible,
            "coverage_fraction": ev.coverage_fraction,
            "contributing_cloud_max": ev.contributing_cloud_max,
            "coverage_gate": ev.coverage_gate,
            "cloud_gate": ev.cloud_gate,
            "multi_tile": ev.multi_tile,
            "n_contributing": len(ev.member_scene_ids),
            "contributing_scene_ids": list(ev.member_scene_ids),
            "contributing_tiles": list(ev.member_tiles),
            "single_date_assertion": len(dates) == 1,
            "member_utcs": sorted(dates),
        })
    return events


def planned_bytes(grid_width: int, grid_height: int, kind: str) -> int:
    if kind == "s2":
        return grid_width * grid_height * (4 * 4 + 1)
    if kind == "landsat":
        # 7 SR float32 + VALID byte + QA_PIXEL uint16
        return grid_width * grid_height * (7 * 4 + 1 + 2)
    if kind == "s1":
        return grid_width * grid_height * 2 * 4
    raise KeyError(kind)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-csv", default=str(OUT_PLAN_CSV))
    parser.add_argument("--plan-json", default=str(OUT_PLAN_JSON))
    args = parser.parse_args()

    if configured_project() is None:
        raise SystemExit("export SPARTINA_GEE_PROJECT=<project-id> first")
    initialize()
    import ee

    from spartina.data.zhejiang.census import install_export_guard

    install_export_guard(ee)  # metadata-only script: exports must crash

    WORK_DIR.mkdir(parents=True, exist_ok=True)
    start_date, end_date = _window_dates()
    cell_boxes = load_cell_boxes()
    region_wgs = union_region_wgs(cell_boxes)

    queries = {
        "sentinel2": "COPERNICUS/S2_SR_HARMONIZED",
        "landsat8": "LANDSAT/LC08/C02/T1_L2",
        "landsat9": "LANDSAT/LC09/C02/T1_L2",
        "sentinel1": "COPERNICUS/S1_GRD",
    }
    # S1 needs the IW + VV/VH server-side filters from the adapter.
    from spartina.data.gee import sentinel1 as s1adapter

    raw: dict[str, list[dict[str, Any]]] = {}
    query_stats: dict[str, Any] = {}
    region_ee = ee.Geometry(region_wgs, "EPSG:4326", False)
    for sensor, cid_collection in queries.items():
        if sensor == "sentinel1":
            col = s1adapter.load_collection(
                ee, region_ee, start_date, end_date)
        else:
            col = (ee.ImageCollection(cid_collection)
                   .filterBounds(region_ee).filterDate(start_date, end_date))
        features, elapsed = materialize(ee, col)
        raw[sensor] = features
        query_stats[sensor] = {
            "collection_id": cid_collection,
            "scenes_intersecting_union_in_window": len(features),
            "getinfo_seconds": round(elapsed, 2),
        }
        print(f"[discover] {sensor}: {len(features)} scenes "
              f"({elapsed:.1f}s)")

    geoms = {sid: geom
             for feats in raw.values()
             for sid, geom in scene_geoms(feats).items()}

    per_cell: dict[str, dict[str, list[SceneCoverage]]] = {}
    for cid, cbox in cell_boxes.items():
        per_cell[cid] = {
            sensor: per_cell_scenes(feats, sensor, {cid: cbox}, geoms)[cid]
            for sensor, feats in raw.items()}

    # ---------------- S2 plan: primary per cell + multi-tile extras ------
    product_seq = 0
    plan_rows: list[dict[str, Any]] = []
    product_details: list[dict[str, Any]] = []
    failure_ledger: list[dict[str, Any]] = []
    all_events: dict[str, list[dict[str, Any]]] = {}

    def next_pid(prefix: str) -> str:
        nonlocal product_seq
        product_seq += 1
        return f"ZJ_M21B_{prefix}_{product_seq:03d}"

    for cid in sorted(cell_boxes):
        events = s2_events_for_cell(
            cid, per_cell[cid]["sentinel2"], geoms, cell_boxes[cid])
        all_events[cid] = events
        elig_objs = [
            EventEligibility(
                cell_id=cid, sensor="sentinel2",
                event_key=e["event_key"], event_utc=e["event_utc"],
                doy=e["doy"],
                member_scene_ids=tuple(e["contributing_scene_ids"]),
                member_tiles=tuple(e["contributing_tiles"]),
                coverage_fraction=e["coverage_fraction"],
                contributing_cloud_max=e["contributing_cloud_max"],
                coverage_gate=e["coverage_gate"],
                cloud_gate=e["cloud_gate"], eligible=e["eligible"],
                multi_tile=e["multi_tile"])
            for e in events]
        primary = pick_primary_s2_event(elig_objs)
        if primary is None:
            failure_ledger.append({
                "cell_id": cid, "sensor": "sentinel2",
                "code": "NO_ELIGIBLE_S2_EVENT_2022_AUTUMN",
                "detail": (
                    "no same-datatake group reached union coverage "
                    f"{COVERAGE_MIN} with contributing cloud "
                    f"<= {SCENE_CLOUD_MAX} under ACTUAL scene geometry"),
                "groups_observed": len(events)})
        else:
            pid = next_pid("S2")
            ev = next(e for e in events if e["event_key"] == primary.event_key)
            plan_rows.append({
                "product_id": pid, "cell_id": cid, "sensor": "sentinel2",
                "role": "PRIMARY_CLEAREST_EVENT",
                "event_key": primary.event_key,
                "event_utc": primary.event_utc, "doy": primary.doy,
                "coverage_fraction": primary.coverage_fraction,
                "contributing_cloud_max": primary.contributing_cloud_max,
                "multi_tile": primary.multi_tile,
                "n_scenes": len(primary.member_scene_ids),
                "scene_ids": "|".join(primary.member_scene_ids),
                "tiles": "|".join(primary.member_tiles),
                "pass_direction": "", "relative_orbit": "",
            })
            product_details.append({"product_id": pid, **ev})

    # up to two extra multi-tile events, clearest first, one per cell
    extras = 0
    for cid in sorted(cell_boxes):
        if extras >= MAX_EXTRA_MULTITILE:
            break
        existing = {r["event_key"] for r in plan_rows if r["cell_id"] == cid}
        elig_objs = [
            pilot.EventEligibility(
                cell_id=cid, sensor="sentinel2",
                event_key=e["event_key"], event_utc=e["event_utc"],
                doy=e["doy"],
                member_scene_ids=tuple(e["contributing_scene_ids"]),
                member_tiles=tuple(e["contributing_tiles"]),
                coverage_fraction=e["coverage_fraction"],
                contributing_cloud_max=e["contributing_cloud_max"],
                coverage_gate=e["coverage_gate"],
                cloud_gate=e["cloud_gate"], eligible=e["eligible"],
                multi_tile=e["multi_tile"])
            for e in all_events[cid]]
        extra = pick_extra_multitile_event(elig_objs, existing)
        if extra is None:
            continue
        pid = next_pid("S2")
        ev = next(e for e in all_events[cid]
                  if e["event_key"] == extra.event_key)
        plan_rows.append({
            "product_id": pid, "cell_id": cid, "sensor": "sentinel2",
            "role": "EXTRA_SAME_DATATAKE_MULTITILE",
            "event_key": extra.event_key,
            "event_utc": extra.event_utc, "doy": extra.doy,
            "coverage_fraction": extra.coverage_fraction,
            "contributing_cloud_max": extra.contributing_cloud_max,
            "multi_tile": True,
            "n_scenes": len(extra.member_scene_ids),
            "scene_ids": "|".join(extra.member_scene_ids),
            "tiles": "|".join(extra.member_tiles),
            "pass_direction": "", "relative_orbit": "",
        })
        product_details.append({"product_id": pid, **ev})
        extras += 1

    # ---------------- Landsat 8/9: first naturally eligible scene --------
    for sensor in ("landsat8", "landsat9"):
        candidates = []
        for cid in cell_boxes:
            pick = first_eligible(per_cell[cid][sensor])
            if pick is not None:
                candidates.append((cid, pick))
        if not candidates:
            failure_ledger.append({
                "cell_id": "ALL_SELECTED", "sensor": sensor,
                "code": f"NO_ELIGIBLE_{sensor.upper()}_SCENE_2022_AUTUMN",
                "detail": (
                    "no single scene covered a selected cell at "
                    f"{COVERAGE_MIN} with cloud <= {SCENE_CLOUD_MAX}; "
                    "no convenient scene substituted")})
            continue
        cid, scene = sorted(candidates,
                            key=lambda t: (t[1].utc, t[1].scene_id, t[0]))[0]
        pid = next_pid("L8" if sensor == "landsat8" else "L9")
        plan_rows.append({
            "product_id": pid, "cell_id": cid, "sensor": sensor,
            "role": "FIRST_NATURALLY_ELIGIBLE_SCENE",
            "event_key": scene.scene_id, "event_utc": scene.utc,
            "doy": scene.doy, "coverage_fraction": scene.coverage_fraction,
            "contributing_cloud_max": scene.cloud_fraction,
            "multi_tile": False, "n_scenes": 1,
            "scene_ids": scene.scene_id,
            "tiles": (f"WRS{scene.extra['wrs_path']:03d}{scene.extra['wrs_row']:03d}"
                      if scene.extra.get("wrs_path") is not None else ""),
            "pass_direction": "", "relative_orbit": "",
        })
        product_details.append({
            "product_id": pid, "event_key": scene.scene_id,
            "event_utc": scene.utc, "doy": scene.doy,
            "eligible": True, "coverage_fraction": scene.coverage_fraction,
            "contributing_cloud_max": scene.cloud_fraction,
            "multi_tile": False,
            "n_contributing": 1,
            "contributing_scene_ids": [scene.scene_id],
            "contributing_tiles": [],
            "single_date_assertion": True,
            "scene_extra": scene.extra,
        })

    # ---------------- Sentinel-1: first eligible scene per pass ----------
    s1_candidates: dict[str, list[tuple[str, SceneCoverage]]] = {
        "ASCENDING": [], "DESCENDING": []}
    for cid in cell_boxes:
        per_pass = first_s1_per_pass(per_cell[cid]["sentinel1"])
        for pass_dir, scene in per_pass.items():
            s1_candidates[pass_dir].append((cid, scene))
    for pass_dir, cands in s1_candidates.items():
        if not cands:
            failure_ledger.append({
                "cell_id": "ALL_SELECTED", "sensor": "sentinel1",
                "code": f"NO_ELIGIBLE_S1_{pass_dir}_SCENE_2022_AUTUMN",
                "detail": (
                    f"no IW VV+VH {pass_dir} scene reached actual-geometry "
                    f"coverage {COVERAGE_MIN}")})
            continue
        cid, scene = sorted(cands,
                            key=lambda t: (t[1].utc, t[1].scene_id, t[0]))[0]
        pid = next_pid("S1")
        plan_rows.append({
            "product_id": pid, "cell_id": cid, "sensor": "sentinel1",
            "role": f"FIRST_ELIGIBLE_{pass_dir}",
            "event_key": scene.scene_id, "event_utc": scene.utc,
            "doy": scene.doy, "coverage_fraction": scene.coverage_fraction,
            "contributing_cloud_max": "",
            "multi_tile": False, "n_scenes": 1,
            "scene_ids": scene.scene_id, "tiles": "",
            "pass_direction": pass_dir,
            "relative_orbit": scene.relative_orbit,
        })
        product_details.append({
            "product_id": pid, "event_key": scene.scene_id,
            "event_utc": scene.utc, "doy": scene.doy,
            "eligible": True, "coverage_fraction": scene.coverage_fraction,
            "multi_tile": False, "n_contributing": 1,
            "contributing_scene_ids": [scene.scene_id],
            "contributing_tiles": [],
            "single_date_assertion": True,
            "pass_direction": pass_dir,
            "relative_orbit": scene.relative_orbit,
            "scene_extra": scene.extra,
        })

    # ---------------- v0_1 nominal-frame vs ACTUAL geometry check --------
    roster = pd.read_csv(CELLS_CSV)
    sim_discrepancies: list[dict[str, Any]] = []
    for _, r in roster.iterrows():
        cid = str(r["cell_id"])
        live_ok = any(e["eligible"] for e in all_events.get(cid, []))
        sim_ok = bool(r["v0_1_quality_s2_event_2022_autumn"])
        if live_ok and not sim_ok:
            sim_discrepancies.append({
                "cell_id": cid,
                "code": "V0_1_NOMINAL_MGRS_FRAME_UNDERCOVERAGE",
                "v0_1_quality_event": False,
                "live_actual_geometry_eligible": True,
                "interpretation": (
                    "corrected v0_1 simulator used NOMINAL MGRS tile frame "
                    "polygons; they miss this cell while real datatake "
                    "footprints cover it. Pilot eligibility uses ACTUAL "
                    "geometry; the archive simulation needs an actual-"
                    "geometry revision before the standard 303-pair batch"),
            })
        if sim_ok and not live_ok:
            sim_discrepancies.append({
                "cell_id": cid,
                "code": "V0_1_EVENT_NOT_REPRODUCED_LIVE",
                "v0_1_quality_event": True,
                "live_actual_geometry_eligible": False,
                "interpretation": (
                    "live actual geometry contradicts v0_1; "
                    "investigate before export"),
            })

    # ---------------- byte estimate against the hard cap ----------------
    from spartina.data.gee.grid import covering_grid  # noqa: E402

    total_bytes = 0
    for row in plan_rows:
        cbox = cell_boxes[row["cell_id"]]
        if row["sensor"] == "sentinel2":
            g = covering_grid(cbox.bounds, 32651, 10.0)
            nbytes = planned_bytes(g.width, g.height, "s2")
        elif row["sensor"].startswith("landsat"):
            g = covering_grid(cbox.bounds, 32651, 30.0)
            nbytes = planned_bytes(g.width, g.height, "landsat")
        else:
            g = covering_grid(cbox.bounds, 32651, 10.0)
            nbytes = planned_bytes(g.width, g.height, "s1")
        row["estimated_bytes"] = nbytes
        total_bytes += nbytes
    if total_bytes > PLANNED_BYTES_HARD_CAP:
        raise SystemExit(
            f"planned {total_bytes} bytes exceeds 10 GB pilot cap; STOP")

    plan_df = pd.DataFrame(plan_rows)
    plan_df.to_csv(Path(args.plan_csv), index=False)

    evidence = {
        "manifest_id": "zhejiang_m21b_pilot_event_plan_v0",
        "created_utc": datetime.now(UTC).isoformat(),
        "issue": "#13",
        "window": {
            "year": PILOT_YEAR,
            "doy_start": AUTUMN_PRIMARY_V1_DOY_START,
            "doy_end": AUTUMN_PRIMARY_V1_DOY_END,
            "filter_start_date": start_date,
            "filter_end_date": end_date,
            "policy": pilot.SEASON_POLICY_ID,
        },
        "gates": {
            "coverage_min": COVERAGE_MIN,
            "scene_cloud_max": SCENE_CLOUD_MAX,
            "geometry": "ACTUAL_PER_SCENE_GEE_GEOMETRY",
            "s2_grouping": "REAL_DATATAKE_IDENTIFIER",
            "contributing_definition": (
                "member scenes whose actual geometry intersects the cell "
                "at all (v0_1 R1 semantics)"),
            "s1_passes": "ASCENDING/DESCENDING kept separate",
            "s1_units": "dB identity export, no 10log10",
        },
        "query_stats": query_stats,
        "n_products": len(plan_rows),
        "estimated_total_bytes": total_bytes,
        "estimated_total_gib": round(total_bytes / 1024**3, 3),
        "products": plan_rows,
        "failure_ledger": failure_ledger,
        "simulation_discrepancies": sim_discrepancies,
        "product_details": product_details,
        "cells_roster": {
            "path": str(Path("datasets/manifests/zhejiang_m21b_pilot_cells_v0.csv")),
            "sha256": sha256_file(CELLS_CSV)},
        "git": git_context(REPO_ROOT),
    }
    evidence["fingerprint_sha256"] = canonical_fingerprint(
        {k: v for k, v in evidence.items() if k != "fingerprint_sha256"})
    Path(args.plan_json).write_text(
        json.dumps(evidence, indent=2, sort_keys=True, default=str),
        encoding="utf-8")

    full_dump = WORK_DIR / "zhejiang_m21b_event_discovery_v0.json"
    dump_payload = {
        "created_utc": evidence["created_utc"],
        "query_stats": query_stats,
        "all_s2_events_by_cell": all_events,
        "failure_ledger": failure_ledger,
        "simulation_discrepancies": sim_discrepancies,
        "plan_fingerprint_sha256": evidence["fingerprint_sha256"],
    }
    full_dump.write_text(
        json.dumps(dump_payload, indent=2, default=str), encoding="utf-8")

    print(plan_df[["product_id", "cell_id", "sensor", "role",
                   "event_utc", "coverage_fraction",
                   "contributing_cloud_max", "multi_tile"]].to_string(
                       index=False))
    print(f"products={len(plan_rows)} "
          f"estimated={total_bytes / 1024**2:.1f} MiB "
          f"failures={len(failure_ledger)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
