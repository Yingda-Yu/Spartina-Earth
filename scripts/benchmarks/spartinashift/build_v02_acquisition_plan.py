#!/usr/bin/env python3
"""Issue #21, Phases D/E/G -- v0.2 multi-date acquisition selection.

Selects, for the 53 frozen NEW panel cells, with no model input:

* Phase D: up to 3 same-datatake Sentinel-2 events per cell-year
  (2020/2021), one per predeclared phenology tertile, each passing the
  existing >= 0.95 ACTUAL observed-mask gate on the locked export grid
  (s2_scl_qa_v1_1 is the VALID contract preserved for export).
* Phase E: up to 3 Landsat C2 L2 observations per cell-year (2015/2020),
  one per tertile, sensor identity preserved, observed-mask gate on the
  exact 30 m grid; no compositing/harmonization.
* Phase G: per selected S2 event, a complete ASC/DESC S1 pairing ledger;
  primary iff gap <= 7 d and s1_dualpol_valid_v2 actual mask >= 0.95;
  a separate frozen 14 d sensitivity tier; never "simultaneous" unless
  gap == 0.

Reuses the Issue #19 V2 primitives (candidate pools, live reduceRegion
coverage, coverage cache) -- it does not fork them. GEE is used for
metadata-scale reduceRegion coverage evidence only; no pixels are
downloaded (export is Phase H, separately capped).

Runs only with SPARTINA_V02_SELECT=1 and SPARTINA_GEE_PROJECT. Outputs:

  benchmarks/spartinashift/v0_2/V0_2_S2_ACQUISITION_PLAN.{json,csv}
  benchmarks/spartinashift/v0_2/V0_2_LANDSAT_ACQUISITION_PLAN.{json,csv}
  benchmarks/spartinashift/v0_2/V0_2_S1_PAIRING_LEDGER.{json,csv}
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts/data/national"))

import geopandas as gpd  # noqa: E402
import pandas as pd  # noqa: E402

from spartina.benchmark.v02 import acquisition as A  # noqa: E402
from spartina.data.gee.auth import configured_project, initialize  # noqa: E402
from spartina.data.gee.collections import collection_for  # noqa: E402
from spartina.data.gee.landsat import QA_FILL, sr_bands  # noqa: E402
from spartina.data.national.geometry import cell_polygon_wgs84  # noqa: E402
from spartina.data.national.grid import GridKind, GridSpec, parse_cell_id  # noqa: E402
from spartina.data.national.pilot_events import AUTUMN_TAG  # noqa: E402

V02_DIR = REPO_ROOT / "benchmarks/spartinashift/v0_2"
REQUIREMENTS_JSON = V02_DIR / "SPARTINASHIFT_V0_2_SUPPORT_REQUIREMENTS.json"
PANEL_JSON = V02_DIR / "SPARTINASHIFT_V0_2_CELL_PANEL.json"
PANEL_CSV = V02_DIR / "v02_cell_panel.csv"
REGISTRY_CSV = (REPO_ROOT / "datasets/manifests"
                / "china_coastal_cells_v1_1_core_frozen.csv")
CENSUS_DIR = REPO_ROOT / "work/national/census_r1/products"
CELL_EVENTS = CENSUS_DIR / "china_cell_event_census_v0_1.parquet"
SCENE_TABLE = CENSUS_DIR / "china_eo_scene_census_v0_1.parquet"
SUPERSESSION_DOC = (
    REPO_ROOT / "docs/data/national/CHINA_EO_CENSUS_SUPERSESSION_v0_1.json")
MGRS_GPKG = REPO_ROOT / "work/national/footprints/mgrs_china_coast_v0_1.gpkg"
WRS_GPKG = REPO_ROOT / "work/national/footprints/wrs2_china_coast_v0_1.gpkg"
WORK_DIR = REPO_ROOT / "work/issue21"
CACHE_JSON = WORK_DIR / "v02_coverage_cache.json"
PROGRESS_JSON = WORK_DIR / "derived/v02_acquisition_progress.json"

OUT_S2_JSON = V02_DIR / "V0_2_S2_ACQUISITION_PLAN.json"
OUT_S2_CSV = V02_DIR / "v02_s2_acquisition_plan.csv"
OUT_L_JSON = V02_DIR / "V0_2_LANDSAT_ACQUISITION_PLAN.json"
OUT_L_CSV = V02_DIR / "v02_landsat_acquisition_plan.csv"
OUT_G_JSON = V02_DIR / "V0_2_S1_PAIRING_LEDGER.json"
OUT_G_CSV = V02_DIR / "v02_s1_pairing_ledger.csv"

LANDSAT_SENSORS = ("landsat8", "landsat7", "landsat5")


def _load_module(name: str, rel_path: str) -> Any:
    path = REPO_ROOT / rel_path
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, check=True,
            capture_output=True, text=True)
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNKNOWN"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def live_landsat_fraction(
    ee: Any, sensor: str, scene_id: str, grid: Any, region: dict[str, Any],
) -> dict[str, Any]:
    """Observed Landsat fraction over the EXACT 30 m export grid.

    Observed = QA_PIXEL fill bit clear AND every exported SR band mask
    present -- the geometric analog of the S2 all-band observed mask; it
    is NOT the clear-sky VALID decision (cloud/shadow stay a separate QA
    concern and candidates are prefiltered on scene cloud <= 0.30).
    """
    col = (ee.ImageCollection(collection_for(sensor))
           .filter(ee.Filter.eq("system:index", scene_id)))
    if int(col.size().getInfo()) != 1:
        raise RuntimeError(
            f"{sensor} catalog returned != 1 scene for {scene_id}")
    img = col.first()
    band_names = list(sr_bands(sensor))
    qa = img.select("QA_PIXEL")
    fill_clear = qa.bitwiseAnd(1 << QA_FILL).eq(0)
    observed = (img.select(band_names).mask().reduce(ee.Reducer.min())
                .eq(1).And(fill_clear).rename("obs_l"))
    return _grid_coverage_landsat(ee, observed, grid, region)


def _grid_coverage_landsat(
    ee: Any, observed: Any, grid: Any, region: dict[str, Any],
) -> dict[str, Any]:
    obs = observed.unmask(0, False)
    reducer = ee.Reducer.sum().combine(ee.Reducer.count(), sharedInputs=True)
    rect = ee.Geometry.Rectangle(
        region["coordinates"][0], region["crs"], False)
    expected = int(grid.width * grid.height)
    raw: dict[str, Any] | None = None
    last_exc: Exception | None = None
    for tile_scale in (8, 16):
        try:
            raw = obs.reduceRegion(
                reducer=reducer, geometry=rect, crs=grid.crs,
                crsTransform=list(grid.transform), bestEffort=False,
                tileScale=tile_scale).getInfo()
            break
        except ee.EEException as exc:
            last_exc = exc
    if raw is None:
        raise RuntimeError(f"GEE landsat coverage reducer failed: {last_exc}")
    n_total = raw.get("obs_l_count")
    n_obs = raw.get("obs_l_sum")
    if n_total != expected:
        raise RuntimeError(
            f"landsat coverage reducer visited {n_total} pixels, export "
            f"grid has {expected}; evidence grid mismatch")
    return {"fraction": 0.0 if n_obs is None else float(n_obs) / n_total,
            "n_grid_pixels": expected}


def landsat_candidates(
    cell_id: str, year: int, *, ce: pd.DataFrame,
    scene_lookup: dict[str, pd.DataFrame], frame_geom: dict[tuple[int, int],
                                                            Any],
    cell_geom: Any,
) -> list[dict[str, Any]]:
    """Discovery pool across L8/L7/L5: autumn + nominal >= 0.90 + cloud."""
    out: list[dict[str, Any]] = []
    for sensor in LANDSAT_SENSORS:
        events = ce[(ce["cell_id"] == cell_id) & (ce["sensor"] == sensor)
                    & (ce["year"] == year)
                    & (ce["season_tag"] == AUTUMN_TAG)].copy()
        if events.empty:
            continue
        attrs = scene_lookup[sensor]
        meta = attrs.loc[attrs.index.intersection(events["event_id"])]
        events = events.merge(
            meta[["scene_id", "product_id", "cloud_cover",
                  "wrs_path", "wrs_row", "l7_era"]],
            on="event_id", how="left")
        events["cloud_fraction"] = (
            pd.to_numeric(events["cloud_cover"], errors="coerce") / 100.0)
        for r in events.itertuples(index=False):
            if pd.isna(r.cloud_fraction) or (
                    float(r.cloud_fraction) > A.OPTICAL_CLOUD_MAX):
                continue
            if str(r.coverage) == "FULL_CELL_COVERED":
                nominal = 1.0
            else:
                if pd.isna(r.wrs_path) or pd.isna(r.wrs_row):
                    continue
                geom = frame_geom.get((int(r.wrs_path), int(r.wrs_row)))
                if geom is None or not str(
                        r.geometry_basis).startswith("WRS2"):
                    continue
                nominal = float(geom.intersection(cell_geom).area
                                / cell_geom.area)
            if nominal < A.NOMINAL_PREFILTER_MIN:
                continue
            product_id = (str(r.product_id)
                          if pd.notna(r.product_id) else "")
            scene_index = _gee_landsat_index(product_id) if product_id else ""
            out.append({
                "event_id": str(r.event_id), "sensor": sensor,
                "scene_id": scene_index, "source_product_id": product_id,
                "utc": str(r.utc), "doy": int(r.doy),
                "cloud_fraction": float(r.cloud_fraction),
                "wrs_path": int(r.wrs_path) if pd.notna(r.wrs_path) else None,
                "wrs_row": int(r.wrs_row) if pd.notna(r.wrs_row) else None,
                "l7_era": str(r.l7_era) if pd.notna(r.l7_era) else "",
                "nominal_coverage_fraction": nominal})
    return out


def _gee_landsat_index(product_id: str) -> str:
    parts = product_id.split("_")
    if len(parts) < 4:
        raise ValueError(f"unexpected Landsat C2 product id: {product_id}")
    return f"{parts[0]}_{parts[2]}_{parts[3]}"


def process_cell(
    cell_id: str, *, ee: Any, v2: Any, p19: Any,
    ce: pd.DataFrame, scene_lookup: dict[str, pd.DataFrame],
    tiles_by_cell: dict[str, set[str]], tile_geom: dict[str, Any],
    frame_geom: dict[tuple[int, int], Any], s2_scenes: pd.DataFrame,
    panel: pd.DataFrame, cache: Any,
) -> dict[str, Any]:
    grids: dict[str, Any] = {}
    for sensor in ("sentinel2", "sentinel1", "landsat8"):
        grid, region, _zone = p19.product_grid(
            {"cell_id": cell_id, "sensor": sensor}, panel)
        grids[sensor] = (grid, region)
    cell_geom_wgs = v2.CELL_POLYS[cell_id]

    def eval_s2(cand: dict[str, Any]) -> dict[str, Any]:
        scenes = str(cand["scene_ids"]).split("|")
        date = str(cand["utc"])[:10]
        key = "V02S2|" + cell_id + "|" + "|".join(scenes)
        hit: dict[str, Any] | None = cache.get(key)
        if hit is None:
            grid, region = grids["sentinel2"]
            hit = v2.live_s2_fraction(ee, scenes, date, grid, region)
            hit["evidence_source"] = "LIVE_GEE_EXPORT_GRID"
            cache.put(key, hit)
        return hit

    def eval_l(cand: dict[str, Any]) -> dict[str, Any]:
        key = f"V02L|{cell_id}|{cand['sensor']}|{cand['scene_id']}"
        hit: dict[str, Any] | None = cache.get(key)
        if hit is None:
            grid, region = grids["landsat8"]
            hit = live_landsat_fraction(
                ee, cand["sensor"], cand["scene_id"], grid, region)
            hit["evidence_source"] = "LIVE_GEE_EXPORT_GRID"
            cache.put(key, hit)
        return hit

    def eval_s1(cand: dict[str, Any]) -> dict[str, Any]:
        scene = str(cand["scene_id"])
        date = str(cand["utc"])[:10]
        key = f"V02S1|{cell_id}|{scene}"
        hit: dict[str, Any] | None = cache.get(key)
        if hit is None:
            grid, region = grids["sentinel1"]
            hit = v2.live_s1_fraction(ee, scene, date, grid, region)
            hit["evidence_source"] = "LIVE_GEE_EXPORT_GRID"
            cache.put(key, hit)
        frac = float(hit["fraction"])
        floor_frac = float(hit["s1_floor_check_fraction"])
        if (frac >= A.ACTUAL_MASK_GATE) != (
                floor_frac >= A.ACTUAL_MASK_GATE):
            raise RuntimeError(
                f"STOP_OWNER_REVIEW: S1 dualpol mask ({frac:.4f}) and "
                f"literal > -70 dB check ({floor_frac:.4f}) disagree on "
                f"the {A.ACTUAL_MASK_GATE:.2f} gate for {cell_id} {scene}")
        return hit

    s2_slots: list[dict[str, Any]] = []
    pairings: list[dict[str, Any]] = []
    for year in A.S2_YEARS:
        pool_df = v2.s2_candidate_pool(
            cell_id, year, ce=ce, tiles_by_cell=tiles_by_cell,
            tile_geom=tile_geom, s2_scenes=s2_scenes)
        candidates = pool_df.to_dict("records") if not pool_df.empty else []
        slots = A.select_tertile_slots(
            cell_id, year, "sentinel2", candidates, A.s2_slot_rank, eval_s2)
        # Attach provenance columns needed by the production contract.
        by_event = {str(c["event_id"]): c for c in candidates}
        for ev in (e for s in slots for e in s["evaluated"]):
            c0 = by_event.get(ev["event_id"])
            if c0 is not None:
                ev["scene_ids"] = str(c0["scene_ids"])
        for slot in slots:
            if slot["status"] == A.STATUS_ELIGIBLE:
                c = by_event[slot["event_id"]]
                slot["scene_ids"] = str(c["scene_ids"])
                slot["product_ids_source"] = str(c["product_ids"])
                slot["mgrs_tiles"] = str(c["mgrs_tiles"])
                slot["member_scene_count"] = int(c["member_scene_count"])
                slot["platform"] = str(c["platform"])
            else:
                slot.update({"scene_ids": "", "product_ids_source": "",
                             "mgrs_tiles": "", "member_scene_count": None,
                             "platform": ""})
        s2_slots.extend(slots)

        # Phase G -- one pairing scan per selected S2 event.
        pools_pass: dict[str, list[A.S1Candidate]] = {}
        for pass_dir in ("ASC", "DESC"):
            df = v2.s1_candidate_pool(
                cell_id, year, pass_dir, ce=ce, scene_lookup=scene_lookup)
            cands: list[A.S1Candidate] = []
            if not df.empty:
                for r in df.itertuples(index=False):
                    cands.append(A.S1Candidate(
                        event_id=str(r.event_id), scene_id=str(r.scene_id),
                        utc=str(r.utc), doy=int(r.doy),
                        pass_direction=pass_dir,
                        relative_orbit=(int(r.relative_orbit)
                                        if pd.notna(r.relative_orbit)
                                        else None),
                        platform=str(r.platform)))
            pools_pass[pass_dir] = cands
        for slot in slots:
            if slot["status"] != A.STATUS_ELIGIBLE:
                continue
            pairings.append(A.pair_s2_event(slot, pools_pass, eval_s1))

    landsat_slots: list[dict[str, Any]] = []
    for year in A.LANDSAT_YEARS:
        candidates = landsat_candidates(
            cell_id, year, ce=ce, scene_lookup=scene_lookup,
            frame_geom=frame_geom, cell_geom=cell_geom_wgs)
        slots = A.select_tertile_slots(
            cell_id, year, "landsat", candidates, A.landsat_slot_rank,
            eval_l)
        by_event = {str(c["event_id"]): c for c in candidates}
        # Sensor identity must survive on EVERY ledgered candidate,
        # including gate failures (Phase E provenance requirement).
        for ev in (e for s in slots for e in s["evaluated"]):
            c0 = by_event.get(ev["event_id"])
            if c0 is not None:
                ev["sensor"] = c0["sensor"]
                ev["scene_id"] = c0["scene_id"]
                ev["source_product_id"] = c0["source_product_id"]
                ev["wrs_path"] = c0["wrs_path"]
                ev["wrs_row"] = c0["wrs_row"]
                ev["l7_era"] = c0["l7_era"]
                ev["nominal_coverage_fraction"] = c0[
                    "nominal_coverage_fraction"]
        for slot in slots:
            if slot["status"] == A.STATUS_ELIGIBLE:
                c = by_event[slot["event_id"]]
                slot["sensor"] = c["sensor"]
                slot["scene_id"] = c["scene_id"]
                slot["source_product_id"] = c["source_product_id"]
                slot["wrs_path"] = c["wrs_path"]
                slot["wrs_row"] = c["wrs_row"]
                slot["l7_era"] = c["l7_era"]
                slot["nominal_coverage_fraction"] = c[
                    "nominal_coverage_fraction"]
            else:
                slot.update({"sensor": "", "scene_id": "",
                             "source_product_id": "", "wrs_path": None,
                             "wrs_row": None, "l7_era": "",
                             "nominal_coverage_fraction": None})
        landsat_slots.extend(slots)

    return {"cell_id": cell_id, "s2_slots": s2_slots,
            "landsat_slots": landsat_slots, "pairings": pairings}


# -- assembly / counts / freeze ------------------------------------------

S2_CSV_COLUMNS = [
    "cell_id", "year", "tertile", "status", "event_id", "event_utc", "doy",
    "cloud_fraction", "actual_observed_fraction", "evidence_source",
    "scene_ids", "product_ids_source", "mgrs_tiles", "member_scene_count",
    "platform", "n_candidates_evaluated"]
L_CSV_COLUMNS = [
    "cell_id", "year", "tertile", "status", "sensor", "event_id",
    "scene_id", "source_product_id", "event_utc", "doy", "cloud_fraction",
    "wrs_path", "wrs_row", "l7_era", "nominal_coverage_fraction",
    "actual_observed_fraction", "evidence_source",
    "n_candidates_evaluated"]
G_CSV_COLUMNS = [
    "cell_id", "year", "tertile", "s2_event_id", "s2_doy", "status",
    "pair_token", "s1_event_id", "s1_scene_id", "s1_doy", "gap_days",
    "pass", "relative_orbit", "platform", "actual_observed_fraction",
    "evidence_source", "best_primary_window_gap_days",
    "n_evaluated_asc", "n_evaluated_desc"]


def _slot_csv_row(slot: dict[str, Any]) -> dict[str, Any]:
    return {k: slot.get(k) for k in S2_CSV_COLUMNS}


def _l_csv_row(slot: dict[str, Any]) -> dict[str, Any]:
    return {k: slot.get(k) for k in L_CSV_COLUMNS}


def _g_csv_row(rec: dict[str, Any]) -> dict[str, Any]:
    scans = {p["pass"]: p for p in rec["pass_scans"]}
    row = {k: rec.get(k) for k in G_CSV_COLUMNS}
    row["n_evaluated_asc"] = scans.get("ASC", {}).get("n_evaluated", 0)
    row["n_evaluated_desc"] = scans.get("DESC", {}).get("n_evaluated", 0)
    return row


def gap_distribution(pairings: list[dict[str, Any]]) -> dict[str, Any]:
    primary = [p for p in pairings if p["status"] == A.STATUS_PAIRED]
    hist: dict[str, int] = {}
    for p in primary:
        g = int(p["gap_days"])
        hist[str(g)] = hist.get(str(g), 0) + 1
    return {
        "n_selected_s2_events": len(pairings),
        "n_paired_lte7d": len(primary),
        "n_same_day_gap0": sum(1 for p in primary if p["gap_days"] == 0),
        "n_sensitivity_lte14d_only": sum(
            1 for p in pairings if p["status"] == A.STATUS_SENSITIVITY),
        "n_modality_slot_unavailable": sum(
            1 for p in pairings if p["status"] == A.STATUS_UNAVAILABLE),
        "primary_gap_histogram_days": dict(sorted(hist.items(),
                                                  key=lambda kv: int(kv[0]))),
        "min_gap": min((int(p["gap_days"]) for p in primary), default=None),
        "max_gap": max((int(p["gap_days"]) for p in primary), default=None)}


def build_documents(
    progress: dict[str, Any], *, requirements: dict[str, Any],
    panel_freeze: dict[str, Any], input_checksums: dict[str, str],
    finished_cells: list[str],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    records = [progress["cells"][c] for c in finished_cells]
    s2_slots = [s for r in records for s in r["s2_slots"]]
    l_slots = [s for r in records for s in r["landsat_slots"]]
    pairings = [p for r in records for p in r["pairings"]]

    def per_cellyear_counts(slots: list[dict[str, Any]]) -> dict[str, int]:
        dist: dict[str, int] = {}
        keys = {(s["cell_id"], s["year"]) for s in slots}
        for key in keys:
            n = sum(1 for s in slots
                    if (s["cell_id"], s["year"]) == key
                    and s["status"] == A.STATUS_ELIGIBLE)
            dist[str(n)] = dist.get(str(n), 0) + 1
        return dict(sorted(dist.items()))

    s2_doc = {
        "product": A.S2_PLAN_NAME,
        "issue": 21,
        "phases": ["D"],
        "requirements_checksum": requirements["checksum"],
        "panel_name": panel_freeze["panel_name"],
        "panel_selection_checksum": panel_freeze["selection_checksum"],
        "status": "FROZEN_SELECTION; actual-mask eligibility on locked "
                  "export grids; export is the separately capped Phase H",
        "rules": {
            "years": list(A.S2_YEARS),
            "phenology_window_doy": [260, 320],
            "tertiles": [
                {"name": n, "doy_min": lo, "doy_max": hi,
                 "preferred_center_doy": c}
                for n, lo, hi, c in A.TERTILES],
            "max_datatakes_per_cell_year": A.MAX_DATATAKES_PER_CELL_YEAR,
            "one_event_per_tertile": True,
            "no_cross_tertile_borrowing": True,
            "composite": "same-datatake ordered union; no cross-date",
            "scene_cloud_max": A.OPTICAL_CLOUD_MAX,
            "required_bands_for_observed_mask": ["B2", "B3", "B4", "B8"],
            "actual_mask_gate": A.ACTUAL_MASK_GATE,
            "valid_qa_policy_preserved_for_export": "s2_scl_qa_v1_1",
            "nominal_geometry_role": "discovery_prefilter_only",
            "within_tertile_rank": ["cloud_fraction asc",
                                    "|doy - tertile_center| asc",
                                    "event_id asc"],
            "label_independent": True,
            "threshold_relaxation_forbidden": True},
        "n_cells": len(records),
        "n_cell_years": len(records) * len(A.S2_YEARS),
        "counts": {
            "eligible_slots": sum(
                1 for s in s2_slots if s["status"] == A.STATUS_ELIGIBLE),
            "no_eligible_slots": sum(
                1 for s in s2_slots if s["status"] == A.STATUS_NO_ELIGIBLE),
            "no_scene_slots": sum(
                1 for s in s2_slots if s["status"] == A.STATUS_NO_SCENE),
            "eligible_events_per_cell_year": per_cellyear_counts(s2_slots),
            "eligible_by_tertile": {
                t: sum(1 for s in s2_slots
                       if s["tertile"] == t
                       and s["status"] == A.STATUS_ELIGIBLE)
                for t in A.TERTILE_ORDER},
            "eligible_by_year": {
                str(y): sum(1 for s in s2_slots
                            if s["year"] == y
                            and s["status"] == A.STATUS_ELIGIBLE)
                for y in A.S2_YEARS}},
        "input_checksums": input_checksums,
        "cell_ids": finished_cells,
        "slots": s2_slots,
    }
    l_doc = {
        "product": A.LANDSAT_PLAN_NAME,
        "issue": 21,
        "phases": ["E"],
        "requirements_checksum": requirements["checksum"],
        "panel_name": panel_freeze["panel_name"],
        "panel_selection_checksum": panel_freeze["selection_checksum"],
        "status": s2_doc["status"],
        "rules": {
            "years": list(A.LANDSAT_YEARS),
            "phenology_window_doy": [260, 320],
            "tertiles": s2_doc["rules"]["tertiles"],
            "max_observations_per_cell_year": A.MAX_LANDSAT_PER_CELL_YEAR,
            "target_observations_per_cell_year":
                A.LANDSAT_TARGET_PER_CELL_YEAR,
            "collection": "Collection 2 Level-2 (T1_L2 GEE)",
            "sensors_considered": list(LANDSAT_SENSORS),
            "scene_cloud_max": A.OPTICAL_CLOUD_MAX,
            "nominal_prefilter_min": A.NOMINAL_PREFILTER_MIN,
            "actual_mask_gate": A.ACTUAL_MASK_GATE,
            "actual_mask_definition": (
                "QA_PIXEL fill bit clear AND every exported SR band "
                "observed, measured over the exact 30 m export grid"),
            "sensor_identity_preserved": True,
            "qa_pixel_preserved": True,
            "physical_scaling": "0.0000275 * DN - 0.2 applied at export",
            "cross_sensor_composite": "FORBIDDEN",
            "spectral_harmonization": "NONE; silent harmonization forbidden",
            "within_tertile_rank": ["cloud_fraction asc",
                                    "|doy - tertile_center| asc",
                                    "sensor priority landsat8<landsat7<5",
                                    "scene_id asc"]},
        "n_cells": len(records),
        "n_cell_years": len(records) * len(A.LANDSAT_YEARS),
        "counts": {
            "eligible_slots": sum(
                1 for s in l_slots if s["status"] == A.STATUS_ELIGIBLE),
            "no_eligible_slots": sum(
                1 for s in l_slots if s["status"] == A.STATUS_NO_ELIGIBLE),
            "no_scene_slots": sum(
                1 for s in l_slots if s["status"] == A.STATUS_NO_SCENE),
            "eligible_observations_per_cell_year":
                per_cellyear_counts(l_slots),
            "eligible_by_sensor": {
                s: sum(1 for x in l_slots
                       if x.get("sensor") == s
                       and x["status"] == A.STATUS_ELIGIBLE)
                for s in LANDSAT_SENSORS},
            "cell_years_at_target_ge2": None},
        "input_checksums": input_checksums,
        "cell_ids": finished_cells,
        "slots": l_slots,
    }
    cy = l_doc["counts"]["eligible_observations_per_cell_year"]
    l_doc["counts"]["cell_years_at_target_ge2"] = sum(
        v for k, v in cy.items() if int(k) >= A.LANDSAT_TARGET_PER_CELL_YEAR)
    g_doc = {
        "product": A.PAIRING_LEDGER_NAME,
        "issue": 21,
        "phases": ["G"],
        "requirements_checksum": requirements["checksum"],
        "panel_name": panel_freeze["panel_name"],
        "panel_selection_checksum": panel_freeze["selection_checksum"],
        "status": "FROZEN_LEDGER; optical samples preserved when no <= 7 d "
                  "pair exists; threshold never widened post hoc",
        "rules": {
            "primary_gap_days_max": A.S1_PRIMARY_GAP_DAYS,
            "sensitivity_gap_days_frozen": A.S1_SENSITIVITY_GAP_DAYS,
            "sensitivity_usage": "predeclared sensitivity tier only; "
                                  "never back-fills the primary view",
            "primary_search_doy_window": [A.PAIR_PRIMARY_DOY_MIN,
                                          A.PAIR_PRIMARY_DOY_MAX],
            "mode": "IW", "polarization": "VV+VH",
            "validity_token": "s1_dualpol_valid_v2",
            "actual_mask_gate": A.ACTUAL_MASK_GATE,
            "asc_desc_preserved": True,
            "relative_orbit_preserved": True,
            "pass_fusion": "FORBIDDEN",
            "gap_convention": "absolute difference of UTC calendar dates",
            "simultaneous_token_requires_gap_zero": True,
            "rank": ["min |gap| among gate-passing candidates",
                     "higher actual observed fraction",
                     "ASC before DESC", "deterministic source id"]},
        "counts": gap_distribution(pairings),
        "input_checksums": input_checksums,
        "cell_ids": finished_cells,
        "pairings": pairings,
    }
    for doc in (s2_doc, l_doc, g_doc):
        doc["generated_utc"] = _now()
        doc["git_commit"] = git_commit()
        doc["document_checksum"] = A.document_checksum(doc)
    return s2_doc, l_doc, g_doc


def freeze_document(doc: dict[str, Any], out_json: Path,
                    out_csv: Path | None, rows: list[dict[str, Any]],
                    columns: list[str]) -> None:
    # Serialize the CSV first so its hash is part of the signed body.
    if out_csv is not None:
        pd.DataFrame(rows, columns=columns).to_csv(out_csv, index=False)
        doc["plan_csv_sha256"] = sha256(out_csv)
        doc["document_checksum"] = A.document_checksum(doc)
    if out_json.exists():
        old = json.loads(out_json.read_text("utf-8"))
        if old.get("document_checksum") != doc["document_checksum"]:
            raise SystemExit(
                f"REFUSING TO MUTATE FROZEN ARTIFACT {out_json.name}: "
                "existing freeze differs")
        print(f"{out_json.name}: already frozen and identical")
        return
    out_json.write_text(
        json.dumps(doc, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8")
    print(f"wrote {out_json.name} (checksum {doc['document_checksum'][:12]})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cells", nargs="*",
                        help="optional explicit cell-id subset (smoke)")
    parser.add_argument("--reset-progress", action="store_true")
    parser.add_argument("--freeze", action="store_true",
                        help="assemble and freeze final artifacts")
    args = parser.parse_args()

    if os.environ.get("SPARTINA_V02_SELECT") != "1":
        raise SystemExit(
            "live v0.2 selection needs SPARTINA_V02_SELECT=1 (explicit "
            "operator opt-in; reduceRegion coverage evidence only)")
    if configured_project() is None:
        raise SystemExit("export SPARTINA_GEE_PROJECT=<project-id> first")
    initialize()
    import ee  # imported after auth gate

    requirements = json.loads(REQUIREMENTS_JSON.read_text("utf-8"))
    panel_freeze = json.loads(PANEL_JSON.read_text("utf-8"))
    if sha256(PANEL_CSV) != panel_freeze["panel_csv_sha256"]:
        raise SystemExit("panel CSV checksum drift; refusing selection")
    fingerprints = json.loads(
        SUPERSESSION_DOC.read_text("utf-8"))["product_fingerprints_sha256"]
    for name, expected in fingerprints.items():
        if sha256(CENSUS_DIR / name) != expected:
            raise SystemExit(f"frozen census checksum mismatch: {name}")

    panel_csv = pd.read_csv(PANEL_CSV)
    panel_ids = list(panel_csv["cell_id"])
    if args.cells:
        unknown = sorted(set(args.cells) - set(panel_ids))
        if unknown:
            raise SystemExit(f"unknown panel cells: {unknown}")
        panel_ids = list(args.cells)

    registry = pd.read_csv(REGISTRY_CSV)
    center = registry.set_index("cell_id")[["center_lon", "center_lat"]]
    driver_panel = center.loc[center.index.intersection(panel_ids)].copy()

    spec = GridSpec(GridKind.CHINA_ALBERS)
    polys = gpd.GeoDataFrame(
        {"cell_id": panel_ids},
        geometry=[cell_polygon_wgs84(
            spec, *(lambda cid: (lambda r: (r.row, r.col))(
                parse_cell_id(cid)))(cid)) for cid in panel_ids],
        crs=4326)

    v2 = _load_module("issue19_v2_plan",
                      "scripts/data/national/build_pilot_event_plan_v2.py")
    v2.CELL_POLYS = dict(zip(polys["cell_id"], polys.geometry, strict=True))
    p19 = v2._load_driver()

    ce_all = pd.read_parquet(CELL_EVENTS)
    ce = ce_all[ce_all["cell_id"].isin(panel_ids)].copy()
    scenes = pd.read_parquet(SCENE_TABLE)
    scene_lookup = {
        sensor: scenes[scenes["sensor"] == sensor].set_index("event_id")
        for sensor in (*LANDSAT_SENSORS, "sentinel1", "sentinel2")}
    mgrs = gpd.read_file(MGRS_GPKG)[["mgrs_tile", "geometry"]]
    tile_geom = dict(zip(mgrs["mgrs_tile"], mgrs.geometry, strict=True))
    cell_tiles = gpd.sjoin(polys, mgrs, how="left",
                           predicate="intersects")[
        ["cell_id", "mgrs_tile"]].dropna()
    tiles_by_cell: dict[str, set[str]] = {
        cid: set(g["mgrs_tile"])
        for cid, g in cell_tiles.groupby("cell_id")}
    wrs = gpd.read_file(WRS_GPKG)[["path", "row", "geometry"]].to_crs(4326)
    frame_geom = {(int(r.path), int(r.row)): r.geometry
                  for r in wrs.itertuples(index=False)}
    s2_scenes = scenes[scenes["sensor"] == "sentinel2"].copy()
    s2_scenes["utc_day"] = pd.to_datetime(
        s2_scenes["utc"], utc=True, format="ISO8601").dt.date.astype(str)
    s2_scenes["s2_event_group"] = [
        v2.s2_event_group_id(str(d), str(day))
        for d, day in zip(s2_scenes["datatake_identifier"],
                          s2_scenes["utc_day"], strict=True)]

    cache = v2.CoverageCache(CACHE_JSON)
    if CACHE_JSON.exists() and "product" in cache.doc:
        cache.doc["product"] = "spartinashift_v0_2_coverage_cache"

    PROGRESS_JSON.parent.mkdir(parents=True, exist_ok=True)
    if PROGRESS_JSON.exists() and not args.reset_progress:
        progress = json.loads(PROGRESS_JSON.read_text("utf-8"))
    else:
        progress = {"product": "V0_2_ACQUISITION_PROGRESS",
                    "cells": {}}

    for cell_id in panel_ids:
        if cell_id in progress["cells"]:
            print(f"{cell_id}: cached", flush=True)
            continue
        rec = process_cell(
            cell_id, ee=ee, v2=v2, p19=p19, ce=ce,
            scene_lookup=scene_lookup, tiles_by_cell=tiles_by_cell,
            tile_geom=tile_geom, frame_geom=frame_geom,
            s2_scenes=s2_scenes, panel=driver_panel, cache=cache)
        progress["cells"][cell_id] = rec
        PROGRESS_JSON.write_text(
            json.dumps(progress, indent=2, default=str), "utf-8")
        n_s2 = sum(1 for s in rec["s2_slots"]
                   if s["status"] == A.STATUS_ELIGIBLE)
        n_l = sum(1 for s in rec["landsat_slots"]
                  if s["status"] == A.STATUS_ELIGIBLE)
        n_p = sum(1 for p in rec["pairings"]
                  if p["status"] == A.STATUS_PAIRED)
        print(f"{cell_id}: s2_eligible={n_s2} landsat_eligible={n_l} "
              f"paired_lte7={n_p}", flush=True)

    if not args.freeze:
        print(f"progress: {len(progress['cells'])}/{len(panel_ids)} cells; "
              "rerun with --freeze to assemble frozen artifacts")
        return 0

    finished = [c for c in panel_ids if c in progress["cells"]]
    if len(finished) != len(panel_ids):
        raise SystemExit(
            f"cannot freeze: {len(finished)}/{len(panel_ids)} cells done")
    input_checksums = {
        "requirements_json_sha256": sha256(REQUIREMENTS_JSON),
        "panel_csv_sha256": sha256(PANEL_CSV),
        **{f"census_{k}": v for k, v in fingerprints.items()},
        "mgrs_footprints_v0_1_sha256": sha256(MGRS_GPKG),
        "wrs2_footprints_v0_1_sha256": sha256(WRS_GPKG)}
    s2_doc, l_doc, g_doc = build_documents(
        progress, requirements=requirements, panel_freeze=panel_freeze,
        input_checksums=input_checksums, finished_cells=finished)

    s2_rows = [_slot_csv_row(s)
               for r in finished for s in progress["cells"][r]["s2_slots"]]
    l_rows = [_l_csv_row(s)
              for r in finished for s in progress["cells"][r]["landsat_slots"]]
    g_rows = [_g_csv_row(p)
              for r in finished for p in progress["cells"][r]["pairings"]]
    freeze_document(s2_doc, OUT_S2_JSON, OUT_S2_CSV, s2_rows, S2_CSV_COLUMNS)
    # Re-sign JSON after embedding CSV hash (freeze_document already did).
    freeze_document(l_doc, OUT_L_JSON, OUT_L_CSV, l_rows, L_CSV_COLUMNS)
    freeze_document(g_doc, OUT_G_JSON, OUT_G_CSV, g_rows, G_CSV_COLUMNS)
    print(json.dumps({"s2": s2_doc["counts"],
                      "landsat": l_doc["counts"],
                      "pairing": g_doc["counts"]}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
