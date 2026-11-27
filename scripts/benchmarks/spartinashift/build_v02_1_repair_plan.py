#!/usr/bin/env python3
"""Issue #21 v0.2.1 repair -- Owner-approved Option A, Phase 2A Step 1+2.

Landsat-only live GEE verification and export planning for the 14 frozen
GEODATA repair candidates (benchmarks/spartinashift/v0_2_1_repair/
v0_2_1_repair_candidate_table.csv). Reuses the frozen Issue #21 Phase D/E
primitives -- discovery pool, tertile slot selection, >= 0.95
actual-observed-mask gate on the exact 30 m export grid, QA_PIXEL fill
bit, cloud prefilter <= 0.30 -- with NO threshold change and NO
re-ranking. Only changes vs the panel run: cell set (the 14 candidates)
and output location (this repair directory). No frozen v0_2 artifact is
touched.

Runs only with SPARTINA_V02_SELECT=1 and SPARTINA_GEE_PROJECT. GEE is
used for metadata-scale reduceRegion coverage evidence only; pixel export
is a separate Owner-gated step.

Outputs (in benchmarks/spartinashift/v0_2_1_repair/):
  LIVE_GEE_REPAIR_PLAN.{json,csv}
  progress/cache under work/issue21/{derived,v02_1_repair_coverage_cache.json}
"""

from __future__ import annotations

import argparse
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
from spartina.data.national.geometry import cell_polygon_wgs84  # noqa: E402
from spartina.data.national.grid import GridKind, GridSpec, parse_cell_id  # noqa: E402

REPAIR_DIR = REPO_ROOT / "benchmarks/spartinashift/v0_2_1_repair"
CANDIDATE_CSV = REPAIR_DIR / "v0_2_1_repair_candidate_table.csv"
OUT_JSON = REPAIR_DIR / "LIVE_GEE_REPAIR_PLAN.json"
OUT_CSV = REPAIR_DIR / "LIVE_GEE_REPAIR_PLAN.csv"

V02_DIR = REPO_ROOT / "benchmarks/spartinashift/v0_2"
REGISTRY_CSV = (REPO_ROOT / "datasets/manifests"
                / "china_coastal_cells_v1_1_core_frozen.csv")
CENSUS_DIR = REPO_ROOT / "work/national/census_r1/products"
CELL_EVENTS = CENSUS_DIR / "china_cell_event_census_v0_1.parquet"
SCENE_TABLE = CENSUS_DIR / "china_eo_scene_census_v0_1.parquet"
SUPERSESSION_DOC = (
    REPO_ROOT / "docs/data/national/CHINA_EO_CENSUS_SUPERSESSION_v0_1.json")
WRS_GPKG = REPO_ROOT / "work/national/footprints/wrs2_china_coast_v0_1.gpkg"
CACHE_JSON = REPO_ROOT / "work/issue21/v02_1_repair_coverage_cache.json"
PROGRESS_JSON = (REPO_ROOT / "work/issue21/derived"
                 / "v02_1_repair_progress.json")

CSV_COLUMNS = [
    "cell_id", "year", "tertile", "status", "sensor", "event_id",
    "scene_id", "source_product_id", "event_utc", "doy", "cloud_fraction",
    "wrs_path", "wrs_row", "l7_era", "nominal_coverage_fraction",
    "actual_observed_fraction", "evidence_source",
    "n_candidates_evaluated", "grid_crs", "grid_transform",
    "grid_width", "grid_height"]


def _load_module(name: str, rel_path: str) -> Any:
    path = REPO_ROOT / rel_path
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def sha256(path: Path) -> str:
    import hashlib
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


def process_cell_landsat(
    cell_id: str, *, ee: Any, P: Any, p19: Any,
    ce: pd.DataFrame, scene_lookup: dict[str, pd.DataFrame],
    frame_geom: dict[tuple[int, int], Any], cell_geom: Any,
    panel: pd.DataFrame, cache: Any,
) -> dict[str, Any]:
    grid, region, _zone = p19.product_grid(
        {"cell_id": cell_id, "sensor": "landsat8"}, panel)

    def eval_l(cand: dict[str, Any]) -> dict[str, Any]:
        key = f"V02L|{cell_id}|{cand['sensor']}|{cand['scene_id']}"
        hit: dict[str, Any] | None = cache.get(key)
        if hit is None:
            hit = P.live_landsat_fraction(
                ee, cand["sensor"], cand["scene_id"], grid, region)
            hit["evidence_source"] = "LIVE_GEE_EXPORT_GRID"
            cache.put(key, hit)
        return hit

    slots_all: list[dict[str, Any]] = []
    for year in A.LANDSAT_YEARS:
        candidates = P.landsat_candidates(
            cell_id, year, ce=ce, scene_lookup=scene_lookup,
            frame_geom=frame_geom, cell_geom=cell_geom)
        slots = A.select_tertile_slots(
            cell_id, year, "landsat", candidates, A.landsat_slot_rank,
            eval_l)
        by_event = {str(c["event_id"]): c for c in candidates}
        prov = ("sensor", "scene_id", "source_product_id", "wrs_path",
                "wrs_row", "l7_era", "nominal_coverage_fraction")
        for ev in (e for s in slots for e in s["evaluated"]):
            c0 = by_event.get(ev["event_id"])
            if c0 is not None:
                for k in prov:
                    ev[k] = c0[k]
        for slot in slots:
            if slot["status"] == A.STATUS_ELIGIBLE:
                c = by_event[slot["event_id"]]
                for k in prov:
                    slot[k] = c[k]
            else:
                slot.update({"sensor": "", "scene_id": "",
                             "source_product_id": "", "wrs_path": None,
                             "wrs_row": None, "l7_era": "",
                             "nominal_coverage_fraction": None})
        slots_all.extend(slots)

    return {"cell_id": cell_id, "landsat_slots": slots_all,
            "grid": {"crs": str(grid.crs),
                     "transform": list(grid.transform),
                     "width": int(grid.width), "height": int(grid.height),
                     "n_pixels": int(grid.width * grid.height)}}.copy()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cells", nargs="*", help="cell-id subset (smoke)")
    parser.add_argument("--reset-progress", action="store_true")
    args = parser.parse_args()

    if os.environ.get("SPARTINA_V02_SELECT") != "1":
        raise SystemExit("set SPARTINA_V02_SELECT=1 (explicit operator opt-in)")
    if configured_project() is None:
        raise SystemExit("export SPARTINA_GEE_PROJECT=<project-id> first")
    initialize()
    import ee  # after auth gate

    cand = pd.read_csv(CANDIDATE_CSV)
    cell_ids = list(cand["cell_id"])
    if args.cells:
        unknown = sorted(set(args.cells) - set(cell_ids))
        if unknown:
            raise SystemExit(f"unknown repair candidates: {unknown}")
        cell_ids = list(args.cells)

    # Frozen-input integrity (same checks as the panel planner).
    P = _load_module(
        "build_v02_acquisition_plan",
        "scripts/benchmarks/spartinashift/build_v02_acquisition_plan.py")
    fingerprints = json.loads(
        P.SUPERSESSION_DOC.read_text("utf-8"))["product_fingerprints_sha256"]
    for name, expected in fingerprints.items():
        if sha256(P.CENSUS_DIR / name) != expected:
            raise SystemExit(f"frozen census checksum mismatch: {name}")

    registry = pd.read_csv(REGISTRY_CSV)
    center = registry.set_index("cell_id")[["center_lon", "center_lat"]]
    driver_panel = center.loc[center.index.intersection(cell_ids)].copy()

    spec = GridSpec(GridKind.CHINA_ALBERS)
    polys = gpd.GeoDataFrame(
        {"cell_id": cell_ids},
        geometry=[cell_polygon_wgs84(spec, *(lambda cid: (
            lambda r: (r.row, r.col))(parse_cell_id(cid)))(cid))
            for cid in cell_ids],
        crs=4326)

    v2 = _load_module("issue19_v2_plan",
                      "scripts/data/national/build_pilot_event_plan_v2.py")
    v2.CELL_POLYS = dict(zip(polys["cell_id"], polys.geometry, strict=True))
    p19 = v2._load_driver()

    ce_all = pd.read_parquet(P.CELL_EVENTS)
    ce = ce_all[ce_all["cell_id"].isin(cell_ids)].copy()
    scenes = pd.read_parquet(P.SCENE_TABLE)
    scene_lookup = {
        sensor: scenes[scenes["sensor"] == sensor].set_index("event_id")
        for sensor in P.LANDSAT_SENSORS}
    wrs = gpd.read_file(P.WRS_GPKG)[["path", "row", "geometry"]].to_crs(4326)
    frame_geom = {(int(r.path), int(r.row)): r.geometry
                  for r in wrs.itertuples(index=False)}

    cache = v2.CoverageCache(CACHE_JSON)

    PROGRESS_JSON.parent.mkdir(parents=True, exist_ok=True)
    if PROGRESS_JSON.exists() and not args.reset_progress:
        progress = json.loads(PROGRESS_JSON.read_text("utf-8"))
    else:
        progress = {"product": "V0_2_1_REPAIR_ACQUISITION_PROGRESS",
                    "cells": {}}

    for cell_id in cell_ids:
        if cell_id in progress["cells"]:
            print(f"{cell_id}: cached", flush=True)
            continue
        rec = process_cell_landsat(
            cell_id, ee=ee, P=P, p19=p19, ce=ce,
            scene_lookup=scene_lookup, frame_geom=frame_geom,
            cell_geom=v2.CELL_POLYS[cell_id], panel=driver_panel,
            cache=cache)
        progress["cells"][cell_id] = rec
        PROGRESS_JSON.write_text(
            json.dumps(progress, indent=2, default=str), "utf-8")
        n_l = sum(1 for s in rec["landsat_slots"]
                  if s["status"] == A.STATUS_ELIGIBLE)
        per_year = {}
        for s in rec["landsat_slots"]:
            if s["status"] == A.STATUS_ELIGIBLE:
                per_year[s["year"]] = per_year.get(s["year"], 0) + 1
        print(f"{cell_id}: landsat_eligible={n_l} per_year={per_year}",
              flush=True)

    if not args.cells or len(cell_ids) == len(cand):
        pass  # full run; freeze below only with --freeze
    if os.environ.get("SPARTINA_V02_FREEZE") != "1":
        done = [c for c in cell_ids if c in progress["cells"]]
        print(f"progress: {len(done)}/{len(cell_ids)} cells; "
              "set SPARTINA_V02_FREEZE=1 (full 14-cell run only) to freeze")
        return 0

    if len(cell_ids) != len(cand):
        raise SystemExit("freeze requires the full 14-cell run")
    slots = [s for c in cell_ids for s in progress["cells"][c]["landsat_slots"]]
    rows = []
    for c in cell_ids:
        g = progress["cells"][c]["grid"]
        for s in progress["cells"][c]["landsat_slots"]:
            row = {k: s.get(k) for k in CSV_COLUMNS if k not in
                   ("grid_crs", "grid_transform", "grid_width", "grid_height")}
            row.update({"grid_crs": g["crs"],
                        "grid_transform": json.dumps(g["transform"]),
                        "grid_width": g["width"], "grid_height": g["height"]})
            rows.append(row)
    doc = {
        "product": "V0_2_1_REPAIR_LIVE_GEE_PLAN",
        "issue": 21,
        "phase": "2A_STEP1",
        "owner_authorization": "Option A live-GEE planner, 2026-11-26",
        "scope": "Landsat 7/8 only; years 2015/2020; 14 frozen repair "
                 "candidates; no cell added, no re-ranking, no QA change",
        "rules": {
            "discovery_prefilter": "autumn DOY 260-320; nominal coverage "
                                   ">= %.2f; scene cloud <= %.2f" % (
                                       A.NOMINAL_PREFILTER_MIN,
                                       A.OPTICAL_CLOUD_MAX),
            "actual_mask_gate": A.ACTUAL_MASK_GATE,
            "observed_definition": "QA_PIXEL fill bit clear AND all SR "
                                   "bands masked-present on exact 30 m "
                                   "export grid (LIVE_GEE_EXPORT_GRID)",
            "tertiles": [{"name": n, "doy_min": lo, "doy_max": hi}
                         for n, lo, hi, _ in A.TERTILES],
            "max_observations_per_cell_year": A.LANDSAT_TARGET_PER_CELL_YEAR,
            "one_event_per_tertile": True,
            "no_cross_tertile_borrowing": True,
            "label_independent": True},
        "counts": {
            "cells": len(cell_ids),
            "eligible_observations_total": sum(
                1 for s in slots if s["status"] == A.STATUS_ELIGIBLE),
            "eligible_by_status": pd.Series(
                [s["status"] for s in slots]).value_counts().to_dict()},
        "input_checksums": {
            "candidate_table_sha256": sha256(CANDIDATE_CSV),
            "registry_csv_sha256": sha256(REGISTRY_CSV),
            **{f"census_{k}": v for k, v in fingerprints.items()},
            "wrs2_footprints_v0_1_sha256": sha256(P.WRS_GPKG)},
        "cell_ids": cell_ids,
        "slots": slots,
        "generated_utc": datetime.now(UTC).isoformat(),
        "git_commit": git_commit(),
    }
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=CSV_COLUMNS).to_csv(OUT_CSV, index=False)
    doc["plan_csv_sha256"] = sha256(OUT_CSV)
    doc["document_checksum"] = A.document_checksum(doc)
    if OUT_JSON.exists():
        raise SystemExit(f"REFUSING TO MUTATE {OUT_JSON.name}: exists")
    OUT_JSON.write_text(
        json.dumps(doc, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8")
    print(f"wrote {OUT_JSON.name} "
          f"(checksum {doc['document_checksum'][:12]})")
    print(json.dumps(doc["counts"], indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
