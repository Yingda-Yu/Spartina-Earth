#!/usr/bin/env python3
"""Issue #19 -- PILOT_EVENT_SELECTION_V2 (owner-approved recovery).

V1 selected S2/S1 events from NOMINAL MGRS/frame geometry. Pilot D1
proved nominal coverage is not actual coverage: three same-datatake
selections exported 100 % NaN and one S1 frame covered 12 % of its
cell. V2 keeps every V1 seasonal/quality rule and replaces ONLY the
eligibility evidence:

* S2: same-datatake ordered union of the required 10 m SR bands
  (B2/B3/B4/B8); candidate production-eligible iff the actual observed
  fraction over the locked W10 export grid is >= 0.95. Nominal MGRS
  geometry is a prefilter (candidate discovery) only.
* S1: single IW GRD VV+VH scene per ASC/DESC slot; eligible iff the
  s1_dualpol_valid_v2 token (finite VV AND finite VH AND
  VV > -70 dB AND VH > -70 dB) covers >= 0.95. The byte-validated live
  proxy is VV.mask AND VH.mask over the export grid; the literal live
  > -70 dB comparison is cross-recorded per candidate and gate
  disagreement raises STOP_OWNER_REVIEW (see manifest rules).
* ranking is unchanged and label-blind: S2 (cloud asc, |doy-290| asc,
  event_id asc); S1 (|doy-290| asc, event_id asc); no cross-date
  mosaic; ASC/DESC never fused.
* candidates failing the gate are recorded with their measured
  fraction; when none passes the slot is
  NO_ELIGIBLE_EVENT_ACTUAL_MASK and the count is never forced.

Landsat rows are inherited unchanged (27/27 landed windows showed
observed coverage >= 0.999 under r2). V1 manifests/checksums are never
overwritten; this script writes v2 plan + an explicit v1->v2
supersession map.

Actual fractions come from landed bytes whenever the candidate event is
already on disk (identical export grid), otherwise from a live GEE
reduceRegion on the export grid's exact crsTransform. Live calls are
cached incrementally. Runs only with
``SPARTINA_PILOT19_V2_SELECT=1`` and ``SPARTINA_GEE_PROJECT``.

Outputs:
* datasets/manifests/national_pilot_event_plan_v2.{json,csv}
* datasets/manifests/national_pilot_event_plan_v1_v2_supersession.json
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

import geopandas as gpd  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import rasterio  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

from spartina.data.gee.auth import configured_project, initialize  # noqa: E402
from spartina.data.gee.collections import collection_for  # noqa: E402
from spartina.data.gee.grid import GridSpec as GeeGridSpec  # noqa: E402
from spartina.data.national.census_join import s2_event_group_id  # noqa: E402
from spartina.data.national.geometry import cell_polygon_wgs84  # noqa: E402
from spartina.data.national.grid import GridKind, GridSpec, parse_cell_id  # noqa: E402
from spartina.data.national.pilot_events import (  # noqa: E402
    AUTUMN_TAG,
    OPTICAL_CLOUD_MAX,
    PASSES,
    S1_DUAL_POL_TOKENS,
    S1_IW,
    TARGET_DOY,
)
from spartina.data.national.pilot_panel import ANCHOR_SLOTS, PANEL_DOMAIN_VERSION  # noqa: E402

# -- frozen inputs (identical set and gate as the v1 builder) -----------
PANEL_CSV = REPO_ROOT / "datasets/manifests/national_first_pixel_panel_v1.csv"
V1_PLAN_CSV = REPO_ROOT / "datasets/manifests/national_pilot_event_plan_v1.csv"
V1_PLAN_JSON = REPO_ROOT / "datasets/manifests/national_pilot_event_plan_v1.json"
CENSUS_DIR = REPO_ROOT / "work/national/census_r1/products"
CELL_EVENTS = CENSUS_DIR / "china_cell_event_census_v0_1.parquet"
SCENE_TABLE = CENSUS_DIR / "china_eo_scene_census_v0_1.parquet"
SUPERSESSION_DOC = (
    REPO_ROOT / "docs/data/national/CHINA_EO_CENSUS_SUPERSESSION_v0_1.json")
MGRS_GPKG = REPO_ROOT / "work/national/footprints/mgrs_china_coast_v0_1.gpkg"
WORK_DIR = REPO_ROOT / "work" / "national" / "pilot19"
MANIFEST_DIR = WORK_DIR / "manifests"
PRODUCT_DIR = WORK_DIR / "products"
CACHE_JSON = WORK_DIR / "v2_coverage_cache.json"
OUT_JSON = REPO_ROOT / "datasets/manifests/national_pilot_event_plan_v2.json"
OUT_CSV = REPO_ROOT / "datasets/manifests/national_pilot_event_plan_v2.csv"
OUT_SUPER = (
    REPO_ROOT / "datasets/manifests"
    / "national_pilot_event_plan_v1_v2_supersession.json")

ACTUAL_MASK_GATE: float = 0.95
S1_FLOOR_DB: float = -70.0
LANDSAT_SENSORS = ("landsat5", "landsat7", "landsat8")
S2_YEARS = (2015, 2020, 2021)
S1_YEARS = (2015, 2020, 2021)

STATUS_ELIGIBLE = "V2_ELIGIBLE"
STATUS_NO_ELIGIBLE = "NO_ELIGIBLE_EVENT_ACTUAL_MASK"
STATUS_NO_SCENE = "NO_SCENE"
#: v2_change token for optical rows inherited from V1 unchanged.
CHANGE_LANDSAT = "V1_INHERITED_LANDSAT"

# v2 coverage basis / tier tokens
TIER_ACTUAL = "ACTUAL_MASK_GTE_0P95"
BASIS_S2_V2 = "V2_SAME_DATATAKE_UNION_ACTUAL_SR_MASK_OVER_EXPORT_GRID"
BASIS_S1_V2 = "V2_DUALPOL_ACTUAL_MASK_INCL_EXTREME_FLOOR_OVER_EXPORT_GRID"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()  # noqa: UP017


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, check=True,
            capture_output=True, text=True)
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNKNOWN"


def _load_driver() -> Any:
    """Reuse the production export grid/bundle machinery, not a copy."""
    path = REPO_ROOT / "scripts/data/national/pilot19_export_products.py"
    spec = importlib.util.spec_from_file_location("pilot19_export_for_v2",
                                                  path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Local evidence: actual coverage from landed bytes on the identical grid
# ---------------------------------------------------------------------------

def local_evidence_registry() -> dict[tuple[str, str], dict[str, Any]]:
    """Map (slot_product_id, event_date) -> measured coverage evidence.

    Includes LANDED manifests and the quarantined vvvh rasters that were
    downloaded but rejected at the pre-v2 landing validation.
    """
    reg: dict[tuple[str, str], dict[str, Any]] = {}
    if MANIFEST_DIR.exists():
        for mp in sorted(MANIFEST_DIR.glob("*.json")):
            mf = json.loads(mp.read_text("utf-8"))
            sensor = str(mf.get("sensor"))
            if sensor not in ("sentinel1", "sentinel2"):
                continue
            pid = str(mf["product_id"])
            date = str(mf.get("acquisition_utc_planned", ""))[:10]
            scenes = set(mf.get("source_scene_ids", []))
            if sensor == "sentinel2":
                sr = next((f for f in mf["landed_files"]
                           if f["role"] == "sr"), None)
                if sr is None:
                    continue
                with rasterio.open(sr["local_uri"]) as ds:
                    arr = ds.read()
                observed = np.isfinite(arr).all(axis=0)
                frac = float(observed.mean())
            else:
                vvvh = next((f for f in mf["landed_files"]
                             if f["role"] == "vvvh"), None)
                if vvvh is None:
                    continue
                with rasterio.open(vvvh["local_uri"]) as ds:
                    vv = ds.read(1).astype("float64")
                    vh = ds.read(2).astype("float64")
                observed = np.isfinite(vv) & np.isfinite(vh)
                floor = observed & ((vv <= S1_FLOOR_DB)
                                    | (vh <= S1_FLOOR_DB))
                frac = float((observed & ~floor).mean())
                dual_frac = float(observed.mean())
            reg[(pid, date)] = {
                "fraction": frac,
                "dual_fraction": dual_frac,
                "scene_ids": scenes,
                "evidence_class": "LANDED",
                "path": mp.name}
    # Quarantined S1 raw rasters (rejected at landing; no manifest).
    if PRODUCT_DIR.exists():
        for tif in sorted(PRODUCT_DIR.glob("*_S1_*_vvvh_*.tif")):
            parts = tif.name.split("_vvvh_")
            pid = parts[0].removeprefix("spartina_pilot19_")
            date = parts[1].split("_")[0]
            date_iso = f"{date[:4]}-{date[4:6]}-{date[6:8]}"
            if any(k[0] == pid and k[1] == date_iso for k in reg):
                continue
            with rasterio.open(tif) as ds:
                vv = ds.read(1).astype("float64")
                vh = ds.read(2).astype("float64")
            observed = np.isfinite(vv) & np.isfinite(vh)
            floor = observed & ((vv <= S1_FLOOR_DB) | (vh <= S1_FLOOR_DB))
            reg[(pid, date_iso)] = {
                "fraction": float((observed & ~floor).mean()),
                "dual_fraction": float(observed.mean()),
                "scene_ids": set(),
                "evidence_class": "QUARANTINED_UNLANDED",
                "path": tif.name}
    return reg


class CoverageCache:
    def __init__(self, path: Path) -> None:
        self.path = path
        if path.exists():
            self.doc = json.loads(path.read_text("utf-8"))
        else:
            self.doc = {"product": "national_pilot19_v2_coverage_cache",
                        "evaluations": {}}

    def get(self, key: str) -> dict[str, Any] | None:
        return self.doc["evaluations"].get(key)  # type: ignore[no-any-return]

    def put(self, key: str, value: dict[str, Any]) -> None:
        self.doc["evaluations"][key] = value
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.doc, indent=2, default=str),
                             encoding="utf-8")


# ---------------------------------------------------------------------------
# Candidate pools (census plumbing identical to the v1 builder; nominal
# geometry retained as discovery prefilter only)
# ---------------------------------------------------------------------------

def s2_candidate_pool(
    cell_id: str, year: int, *, ce: pd.DataFrame,
    tiles_by_cell: dict[str, set[str]], tile_geom: dict[str, Any],
    s2_scenes: pd.DataFrame,
) -> pd.DataFrame:
    events = ce[(ce["cell_id"] == cell_id) & (ce["sensor"] == "sentinel2")
                & (ce["year"] == year)].copy()
    if events.empty:
        return events
    tiles = tiles_by_cell.get(cell_id, set())
    gran = s2_scenes[s2_scenes["mgrs_tile"].isin(tiles)
                     & (s2_scenes["year"] == year)
                     & (s2_scenes["s2_event_group"].isin(events["event_id"]))]
    rows: list[dict[str, Any]] = []
    cell_polys = CELL_POLYS[cell_id]
    for group_id, g in gran.groupby("s2_event_group"):
        member_tiles = sorted(set(g["mgrs_tile"]))
        union_geom = unary_union(
            [tile_geom[t] for t in member_tiles if t in tile_geom])
        rows.append({
            "event_id": group_id,
            "utc": str(g["utc"].iloc[0]),
            "doy": int(g["doy"].iloc[0]),
            "season_tag": str(g["season_tag"].iloc[0]),
            "cloud_fraction": float(pd.to_numeric(
                g["cloudy_pixel_percent"], errors="coerce").max()) / 100.0,
            "scene_ids": "|".join(sorted(g["system_index"])),
            "product_ids": "|".join(sorted(g["product_id"])),
            "mgrs_tiles": "|".join(member_tiles),
            "member_scene_count": int(g["system_index"].nunique()),
            "platform": "|".join(sorted(
                {str(v) for v in g["spacecraft_name"] if pd.notna(v)})),
            "nominal_union_covers_cell": bool(union_geom.covers(cell_polys)),
        })
    pool = pd.DataFrame(rows)
    if pool.empty:
        return pool
    pool = pool[pool["season_tag"] == AUTUMN_TAG]
    pool = pool[pool["cloud_fraction"] <= OPTICAL_CLOUD_MAX].copy()
    pool["doy_dist"] = (pool["doy"] - TARGET_DOY).abs()
    return pool.sort_values(
        ["cloud_fraction", "doy_dist", "event_id"]).reset_index(drop=True)


def s1_candidate_pool(
    cell_id: str, year: int, pass_direction: str, *,
    ce: pd.DataFrame, scene_lookup: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    events = ce[(ce["cell_id"] == cell_id) & (ce["sensor"] == "sentinel1")
                & (ce["year"] == year)].copy()
    if events.empty:
        return events
    attrs = scene_lookup["sentinel1"]
    meta = attrs.loc[attrs.index.intersection(events["event_id"])]
    pool = events.merge(
        meta[["scene_id", "pass", "relative_orbit", "platform",
              "instrument_mode", "polarization"]],
        on="event_id", how="left")
    pool = pool[
        (pool["pass"] == pass_direction)
        & (pool["season_tag"] == AUTUMN_TAG)
        & (pool["instrument_mode"] == S1_IW)
        & (pool["polarization"].isin(S1_DUAL_POL_TOKENS))].copy()
    if pool.empty:
        return pool
    pool["doy_dist"] = (pd.to_numeric(pool["doy"]).astype(int)
                        - TARGET_DOY).__abs__()
    pool["scene_ids"] = pool["scene_id"].astype(str)
    return pool.sort_values(
        ["doy_dist", "event_id"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Actual-mask evaluation (live GEE on the exact export crsTransform)
# ---------------------------------------------------------------------------

def _day_window(date_iso: str) -> tuple[str, str]:
    """Half-open [day, next day) UTC filter window for one date."""
    day = datetime.strptime(date_iso, "%Y-%m-%d").date()
    nxt = day + timedelta(days=1)
    return day.isoformat() + "T00:00:00Z", nxt.isoformat() + "T00:00:00Z"


def _grid_coverage(
    ee: Any, observed: Any, grid: GeeGridSpec, region: dict[str, Any],
) -> dict[str, Any]:
    """Observed fraction over the EXACT export grid.

    A plain mean() of a mask silently excludes masked (non-observed)
    pixels, which would bias every partial frame toward 1.0. Instead the
    mask is unmasked to 0 over the full footprint and reduced with paired
    sum/count: fraction = observed pixels / every export-grid pixel.
    The reducer's pixel count must equal grid.width*grid.height (the
    dimensions pinned at export task submission), otherwise the evidence
    does not correspond to the landed raster and the caller must stop.
    """
    obs = observed.unmask(0, False).rename("obs")
    reducer = ee.Reducer.sum().combine(
        ee.Reducer.count(), sharedInputs=True)
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
        except ee.EEException as exc:  # transient/timeout: larger tiles
            last_exc = exc
    if raw is None:
        raise RuntimeError(f"GEE coverage reducer failed: {last_exc}")
    n_total = raw.get("obs_count")
    n_obs = raw.get("obs_sum")
    if n_total != expected:
        raise RuntimeError(
            f"coverage reducer visited {n_total} pixels, export grid has "
            f"{expected}; evidence grid mismatch")
    return {"fraction": 0.0 if n_obs is None else float(n_obs) / n_total,
            "n_grid_pixels": expected}


def live_s2_fraction(
    ee: Any, scene_ids: list[str], date_iso: str, grid: GeeGridSpec,
    region: dict[str, Any],
) -> dict[str, Any]:
    start, end = _day_window(date_iso)
    col = (ee.ImageCollection(collection_for("sentinel2"))
           .filterDate(start, end)
           .filter(ee.Filter.inList("system:index", scene_ids)))
    n = int(col.size().getInfo())
    if n != len(scene_ids):
        raise RuntimeError(
            f"S2 catalog returned {n} scenes for {scene_ids}")
    datatakes = sorted(set(
        col.aggregate_array("DATATAKE_IDENTIFIER").getInfo()))
    dates = sorted({s[:8] for s in scene_ids})
    if len(datatakes) != 1:
        raise RuntimeError(f"cross-datatake candidate {datatakes}")
    if len(dates) != 1:
        raise RuntimeError(f"cross-date candidate {dates}")
    ordered = col.sort("MGRS_TILE")

    def _obs(img: Any) -> Any:
        m = img.select("B2").mask()
        for b in ("B3", "B4", "B8"):
            m = m.And(img.select(b).mask())
        return m

    observed = ordered.map(_obs).mosaic()
    out = _grid_coverage(ee, observed, grid, region)
    out.update({"datatake": datatakes[0], "date": dates[0],
                "n_member_scenes": n})
    return out


def live_s1_fraction(
    ee: Any, scene_id: str, date_iso: str, grid: GeeGridSpec,
    region: dict[str, Any],
) -> dict[str, Any]:
    """Dual-pol actual coverage on the exact export grid.

    Two fractions are measured in ONE stacked reduction:

    * ``dualpol_mask`` = VV.mask AND VH.mask -- the byte-validated live
      proxy of the production ``s1_dualpol_valid_v2`` token. Validation on
      10 landed/quarantined rasters (incl. both discrete -80.031 dB floor
      frames) matched exported bytes (finite VV AND finite VH AND
      VV>-70 AND VH>-70) to 4 decimals: GEE's source masks already carry
      the no-signal floor as masked, and byte-level finite dual-pol pixels
      never contain <= -70 dB values (F3 audit).
    * ``floor_check`` adds the literal VV/VH > -70 dB comparisons. At
      reduceRegion time this exhibits a fractional-edge-mask resampling
      artifact on partial frames (0.1214 -> 0.1067 on one control scene),
      so it is recorded as a cross-check, not the primary measure.

    The caller hard-stops when the two expressions disagree on the 0.95
    gate; the threshold is never silently chosen between (owner F3).
    """
    start, end = _day_window(date_iso)
    img = (ee.ImageCollection(collection_for("sentinel1"))
           .filterDate(start, end)
           .filter(ee.Filter.eq("system:index", scene_id)).first())
    vv = img.select("VV")
    vh = img.select("VH")
    dual = vv.mask().And(vh.mask()).rename("dualpol_mask")
    floored = dual.And(vv.gt(S1_FLOOR_DB)).And(vh.gt(S1_FLOOR_DB)).rename(
        "floor_check")
    rect = ee.Geometry.Rectangle(
        region["coordinates"][0], region["crs"], False)
    expected = int(grid.width * grid.height)
    raw: dict[str, Any] | None = None
    last_exc: Exception | None = None
    for tile_scale in (8, 16):
        try:
            raw = ee.Image.cat([dual, floored]).unmask(0, False).reduceRegion(
                reducer=ee.Reducer.sum(), geometry=rect, crs=grid.crs,
                crsTransform=list(grid.transform), bestEffort=False,
                tileScale=tile_scale).getInfo()
            break
        except ee.EEException as exc:
            last_exc = exc
    if raw is None:
        raise RuntimeError(f"GEE coverage reducer failed: {last_exc}")
    for key in ("dualpol_mask", "floor_check"):
        if raw.get(key) is None:
            raise RuntimeError(
                f"S1 reducer missing {key} for {scene_id}")
    return {"fraction": float(raw["dualpol_mask"]) / expected,
            "s1_floor_check_fraction":
                float(raw["floor_check"]) / expected,
            "n_grid_pixels": expected}


def evaluate_s2_slot(
    ee: Any, pid: str, pool: pd.DataFrame,
    grids: dict[str, Any], cache: CoverageCache,
    local: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    if pool.empty:
        return {"status": STATUS_NO_SCENE, "pick": None,
                "evaluated": []}
    grid, region = grids["sentinel2"]
    evaluated: list[dict[str, Any]] = []
    for cand in pool.itertuples(index=False):
        date = str(cand.utc)[:10]
        scenes = str(cand.scene_ids).split("|")
        local_hit = local.get((pid, date))
        # Byte evidence is admissible only for the exact same acquisition
        # (same granule set for S2; the V1-picked event for a quarantined
        # download). Same-day different-event candidates go to live GEE.
        if (local_hit is not None
                and local_hit["evidence_class"] == "LANDED"
                and set(local_hit["scene_ids"]) == set(scenes)):
            evidence = {"fraction": local_hit["fraction"],
                        "evidence_source": "LANDED_BYTES"}
        else:
            # Coverage is cell-grid specific: the same datatake can be a
            # candidate over neighbouring cells with different fractions.
            key = f"S2|{pid}|" + "|".join(scenes)
            hit = cache.get(key)
            if hit is None:
                hit = live_s2_fraction(ee, scenes, date, grid, region)
                hit["evidence_source"] = "LIVE_GEE_EXPORT_GRID"
                cache.put(key, hit)
            evidence = hit
        rec = {
            "event_id": cand.event_id, "event_utc": cand.utc,
            "doy": int(cand.doy),
            "cloud_fraction": float(cand.cloud_fraction),
            "scene_ids": scenes,
            "actual_observed_fraction": float(evidence["fraction"]),
            "evidence_source": evidence["evidence_source"],
            "rank": len(evaluated) + 1}
        evaluated.append(rec)
        if float(evidence["fraction"]) >= ACTUAL_MASK_GATE:
            return {"status": STATUS_ELIGIBLE, "pick": cand,
                    "fraction": float(evidence["fraction"]),
                    "evidence_source": evidence["evidence_source"],
                    "evaluated": evaluated}
    return {"status": STATUS_NO_ELIGIBLE, "pick": None,
            "evaluated": evaluated}


def evaluate_s1_slot(
    ee: Any, pass_direction: str, pid: str, pool: pd.DataFrame,
    grids: dict[str, Any], cache: CoverageCache,
    local: dict[tuple[str, str], dict[str, Any]], v1_event_id: str,
) -> dict[str, Any]:
    if pool.empty:
        return {"status": STATUS_NO_SCENE, "pick": None,
                "evaluated": []}
    grid, region = grids["sentinel1"]
    evaluated: list[dict[str, Any]] = []
    for cand in pool.itertuples(index=False):
        date = str(cand.utc)[:10]
        scene = str(cand.scene_id)
        local_hit = local.get((pid, date))
        use_local = False
        if local_hit is not None:
            if (local_hit["evidence_class"] == "LANDED"
                    and set(local_hit["scene_ids"]) == {scene}):
                use_local = True
            elif (local_hit["evidence_class"] == "QUARANTINED_UNLANDED"
                  and str(cand.event_id) == v1_event_id):
                # The unlanded quarantine raster exists only because V1
                # exported this exact event; no same-day misattribution.
                use_local = True
        if use_local:
            assert local_hit is not None
            # On bytes the token fraction already applies the literal
            # > -70 dB rule; the raw dual-finite fraction is recorded too.
            evidence = {
                "fraction": local_hit["fraction"],
                "s1_floor_check_fraction": local_hit["fraction"],
                "s1_dualpol_mask_fraction": local_hit["dual_fraction"],
                "evidence_source": local_hit["evidence_class"]
                + "_BYTES"}
        else:
            key = f"S1|{pid}|{scene}"
            hit = cache.get(key)
            if hit is None:
                hit = live_s1_fraction(ee, scene, date, grid, region)
                hit["evidence_source"] = "LIVE_GEE_EXPORT_GRID"
                cache.put(key, hit)
            evidence = hit
        frac = float(evidence["fraction"])
        floor_frac = float(evidence["s1_floor_check_fraction"])
        if (frac >= ACTUAL_MASK_GATE) != (floor_frac >= ACTUAL_MASK_GATE):
            raise RuntimeError(
                f"STOP_OWNER_REVIEW: S1 dualpol mask ({frac:.4f}) and "
                f"literal > -70 dB floor check ({floor_frac:.4f}) disagree "
                f"on the {ACTUAL_MASK_GATE:.2f} gate for {pid} {scene}; "
                "threshold choice forbidden without owner review")
        rec = {
            "event_id": cand.event_id, "event_utc": cand.utc,
            "doy": int(cand.doy), "scene_id": scene,
            "pass": pass_direction,
            "relative_orbit": (int(cand.relative_orbit)
                               if pd.notna(cand.relative_orbit) else ""),
            "platform": cand.platform,
            "actual_observed_fraction": frac,
            "s1_floor_check_fraction": floor_frac,
            "evidence_source": evidence["evidence_source"],
            "rank": len(evaluated) + 1}
        evaluated.append(rec)
        if frac >= ACTUAL_MASK_GATE:
            return {"status": STATUS_ELIGIBLE, "pick": cand,
                    "fraction": frac,
                    "evidence_source": evidence["evidence_source"],
                    "evaluated": evaluated}
    return {"status": STATUS_NO_ELIGIBLE, "pick": None,
            "evaluated": evaluated}


# module-level cell polygon table (filled in main)
CELL_POLYS: dict[str, Any] = {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-csv", default=str(OUT_CSV))
    parser.add_argument("--out-supersession", default=str(OUT_SUPER))
    args = parser.parse_args()

    if os.environ.get("SPARTINA_PILOT19_V2_SELECT") != "1":
        raise SystemExit(
            "V2 live selection needs SPARTINA_PILOT19_V2_SELECT=1 "
            "(owner-approved recovery; explicit operator opt-in)")
    if configured_project() is None:
        raise SystemExit("export SPARTINA_GEE_PROJECT=<project-id> first")
    initialize()
    import ee

    fingerprints = dict(json.loads(
        SUPERSESSION_DOC.read_text("utf-8"))[
        "product_fingerprints_sha256"])
    for name, expected in fingerprints.items():
        if _sha256(CENSUS_DIR / name) != expected:
            raise SystemExit(f"frozen census checksum mismatch: {name}")
    v1_doc = json.loads(V1_PLAN_JSON.read_text("utf-8"))
    if _sha256(V1_PLAN_CSV) != v1_doc["checksums"]["plan_csv_sha256"]:
        raise SystemExit("V1 plan CSV checksum drift; V1 must stay frozen")

    panel = pd.read_csv(PANEL_CSV).set_index("cell_id")
    panel_ids = list(panel.index)
    spec = GridSpec(GridKind.CHINA_ALBERS)
    polys = gpd.GeoDataFrame(
        {"cell_id": panel_ids},
        geometry=[cell_polygon_wgs84(
            spec, *(lambda cid: (lambda r: (r.row, r.col))(
                parse_cell_id(cid)))(cid))
            for cid in panel_ids], crs=4326)
    CELL_POLYS.update(dict(zip(polys["cell_id"], polys.geometry,
                               strict=True)))

    ce = pd.read_parquet(CELL_EVENTS)
    ce = ce[ce["cell_id"].isin(panel_ids)].copy()
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
    s2_scenes = scenes[scenes["sensor"] == "sentinel2"].copy()
    s2_scenes["utc_day"] = pd.to_datetime(
        s2_scenes["utc"], utc=True, format="ISO8601").dt.date.astype(str)
    s2_scenes["s2_event_group"] = [
        s2_event_group_id(str(d), str(day))
        for d, day in zip(s2_scenes["datatake_identifier"],
                          s2_scenes["utc_day"], strict=True)]

    v1 = pd.read_csv(V1_PLAN_CSV)
    v1_records: list[dict[str, Any]] = [
        {k: ("" if pd.isna(v) else v)
         for k, v in row.items()}
        for row in v1.to_dict("records")]
    v1_lookup = {
        (str(r["cell_id"]), str(r["sensor"]), int(r["year"]),
         str(r["variant"])): r
        for r in v1_records}
    # Exactly one optical (landsat) row per cell x anchor year.
    v1_landsat_lookup: dict[tuple[str, int], dict[str, Any]] = {}
    for r in v1_records:
        if str(r["sensor"]).startswith("landsat"):
            v1_landsat_lookup[
                (str(r["cell_id"]), int(r["year"]))] = r

    p19 = _load_driver()
    local = local_evidence_registry()
    cache = CoverageCache(CACHE_JSON)

    def grids_for(cell_id: str) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for sensor in ("sentinel2", "sentinel1"):
            grid, region, _zone = p19.product_grid(
                {"cell_id": cell_id, "sensor": sensor}, panel)
            out[sensor] = (grid, region)
        return out

    rows: list[dict[str, Any]] = []
    super_rows: list[dict[str, Any]] = []

    def short(cell: str) -> str:
        return cell.removeprefix("CNA10K-")

    def base_v1(cell: str, sensor: str, year: int, variant: str) -> Any:
        return v1_lookup.get((cell, sensor, year, variant))

    for cell_id in panel_ids:
        grids = grids_for(cell_id)
        for slot in ANCHOR_SLOTS:
            if slot.sensor.startswith("landsat"):
                # Exactly one v1 optical row per cell x anchor year;
                # inherit the whole v1 outcome unchanged.
                v1r = v1_landsat_lookup.get((cell_id, slot.year))
                if v1r is None:
                    continue
                row = dict(v1r)
                row["selection_version"] = "V2"
                row["v2_change"] = CHANGE_LANDSAT
                row["v2_actual_observed_fraction"] = ""
                row["v2_candidates_evaluated"] = 0
                row["v2_evidence_source"] = (
                    "NOT_RESELECTED_LANDSAT; all 27 D1 landed windows had "
                    "observed coverage >= 0.999 under VALID r2")
                rows.append(row)
                super_rows.append({
                    "cell_id": cell_id, "sensor": row["sensor"],
                    "year": slot.year, "variant": v1r["variant"],
                    "v1_status": v1r["status"],
                    "v1_event_id": v1r["event_id"],
                    "v2_status": v1r["status"],
                    "v2_event_id": v1r["event_id"],
                    "change": CHANGE_LANDSAT})
                continue

            variants: list[tuple[str, str]]
            if slot.sensor == "sentinel2":
                # V1 plan serializes the single optical variant as DEFAULT.
                variants = [("DEFAULT", "")]
            else:
                variants = [("A", "ASC"), ("D", "DESC")]

            for variant, pass_dir in variants:
                v1r = base_v1(cell_id, slot.sensor, slot.year, variant)
                v1_status = str(v1r["status"]) if v1r is not None else "MISSING"
                v1_event = str(v1r["event_id"]) if v1r is not None else ""
                if slot.sensor == "sentinel2":
                    pid = f"NP19_{short(cell_id)}_S2_{slot.year}"
                    pool = s2_candidate_pool(
                        cell_id, slot.year, ce=ce,
                        tiles_by_cell=tiles_by_cell,
                        tile_geom=tile_geom, s2_scenes=s2_scenes)
                    result = evaluate_s2_slot(
                        ee, pid, pool, grids, cache, local)
                else:
                    pid = f"NP19_{short(cell_id)}_S1_{slot.year}_{variant}"
                    pool = s1_candidate_pool(
                        cell_id, slot.year, pass_dir, ce=ce,
                        scene_lookup=scene_lookup)
                    result = evaluate_s1_slot(
                        ee, pass_dir, pid, pool, grids, cache, local,
                        v1_event)

                evals = result["evaluated"]
                best = max(
                    (e["actual_observed_fraction"] for e in evals),
                    default=None)
                rank1_txt = (f"{evals[0]['actual_observed_fraction']:.4f}"
                             if evals else "noscene")
                print(
                    f"{short(cell_id)} {slot.sensor} {slot.year} "
                    f"{variant or 'DEFAULT'}: {result['status']} "
                    f"rank1={rank1_txt} "
                    f"best={best if best is None else round(best, 4)} "
                    f"n_eval={len(evals)} v1={v1_status}",
                    flush=True)

                if result["status"] == STATUS_ELIGIBLE:
                    pick = result["pick"]
                    v2_event = str(pick.event_id)
                    if v1_status == "SELECTED" and v1_event == v2_event:
                        change = "KEPT_SAME_EVENT_PASSES_ACTUAL_MASK"
                    elif v1_status == "SELECTED":
                        change = "REPLACED_V1_EVENT_FAILED_ACTUAL_MASK"
                    else:
                        change = "NEW_ELIGIBLE_V2_ACTUAL_MASK"
                    row = _v2_row(
                        cell_id, slot, variant, pid, pick, result,
                        sensor=slot.sensor, pass_dir=pass_dir,
                        change=change)
                else:
                    v2_event = ""
                    if v1_status == "SELECTED":
                        change = "V1_SELECTED_BUT_NO_ELIGIBLE_ACTUAL_MASK"
                    elif pool.empty:
                        change = "NO_SCENE_INHERITED"
                    else:
                        change = "STILL_NO_ELIGIBLE_EVENT_ACTUAL_MASK"
                    row = _v2_empty_row(
                        cell_id, slot, variant, pid, result,
                        sensor=slot.sensor, change=change)
                rows.append(row)
                super_rows.append({
                    "cell_id": cell_id, "sensor": slot.sensor,
                    "year": slot.year, "variant": variant,
                    "v1_status": v1_status, "v1_event_id": v1_event,
                    "v2_status": result["status"],
                    "v2_event_id": v2_event,
                    "change": change,
                    "candidates_evaluated": len(result["evaluated"]),
                    "best_actual_observed_fraction": (
                        max((e["actual_observed_fraction"]
                             for e in result["evaluated"]),
                            default=None)),
                    "evaluated": result["evaluated"]})

    plan = pd.DataFrame(rows)

    # Reconciliation: V2 must describe exactly the same 20 cells x
    # anchor slots as V1 -- every V1 row superseded once, nothing added
    # or silently dropped (selection outcomes may change, keys may not).
    v1_keys = {
        (str(r["cell_id"]), str(r["sensor"]), int(r["year"]),
         str(r["variant"])) for r in v1_records}
    v2_keys = {
        (str(r["cell_id"]), str(r["sensor"]), int(r["year"]),
         str(r["variant"])) for r in rows}
    if v1_keys != v2_keys:
        missing = sorted(v1_keys - v2_keys)
        extra = sorted(v2_keys - v1_keys)
        raise SystemExit(
            f"V1->V2 slot reconciliation failure; missing={missing[:5]} "
            f"extra={extra[:5]}")
    if len(rows) != len(v1_records):
        raise SystemExit(
            f"V2 rows {len(rows)} != V1 rows {len(v1_records)}")

    out_csv = Path(args.out_csv)
    plan.to_csv(out_csv, index=False)

    v1_selected = int(sum(1 for r in v1_records
                          if str(r["status"]) == "SELECTED"))
    counts = _counts(plan, super_rows, v1_selected)
    manifest = {
        "product": "national_pilot_event_plan_v2",
        "issue": 19,
        "selection_policy": "PILOT_EVENT_SELECTION_V2",
        "generated_utc": _now(),
        "git_commit": _git_commit(),
        "status": "PLANNED_V2; actual-mask eligibility; owner-approved "
                  "recovery 2026-10-09; not a national expansion",
        "supersedes": "national_pilot_event_plan_v1 (retained unchanged)",
        "domain_version": PANEL_DOMAIN_VERSION,
        "census_version": "v0_1",
        "rules": {
            "s2": {
                "phenology_doy": [260, 320],
                "scene_cloud_max": OPTICAL_CLOUD_MAX,
                "composite": "same-datatake ordered union; no cross-date",
                "required_bands": ["B2", "B3", "B4", "B8"],
                "actual_mask_gate": ACTUAL_MASK_GATE,
                "coverage_measure": (
                    "observed pixel count / total export-grid pixel count "
                    "for the all-four-band mask (unmasked to 0 before the "
                    "sum/count reducer; plain mean would exclude "
                    "non-observed pixels) over the locked W10 native-UTM "
                    "grid (exact crsTransform; reducer pixel count asserted "
                    "equal to grid width*height)"),
                "nominal_geometry_role": "prefilter_only",
                "rank": ["cloud_fraction asc", "|doy-290| asc",
                         "event_id asc"]},
            "sentinel1": {
                "phenology_doy": [260, 320],
                "mode": S1_IW, "polarization": "VV+VH",
                "passes": list(PASSES), "pass_fusion": "FORBIDDEN",
                "validity_token": "s1_dualpol_valid_v2",
                "floor_rule_db": S1_FLOOR_DB,
                "floor_rule_semantics": (
                    "NON_OBSERVATION_EXTREME_FLOOR; raw dB preserved; "
                    "observation validity, not a physical impossibility "
                    "claim; threshold owner-approved 2026-10-09 after "
                    "the F3 evidence audit"),
                "raster_token_definition": (
                    "finite(VV) AND finite(VH) AND VV>-70 AND VH>-70 on "
                    "the identity-preserved exported vvvh raster"),
                "live_measurement_equivalence": (
                    "live reduceRegion uses VV.mask AND VH.mask on the "
                    "exact export grid; validated against exported bytes "
                    "on 10 scenes (incl. both discrete -80.031 dB floor "
                    "frames) to 4 decimals -- GEE source masks already "
                    "carry the no-signal floor as masked, and zero finite "
                    "dual-pol byte pixels are <= -70 dB; the literal "
                    "live > -70 dB comparison is recorded per candidate "
                    "(s1_floor_check_fraction) and any disagreement at "
                    "the 0.95 gate raises STOP_OWNER_REVIEW"),
                "actual_mask_gate": ACTUAL_MASK_GATE,
                "rank": ["|doy-290| asc", "event_id asc"]},
            "landsat": "V1 outcomes inherited unchanged",
            "label_independent": True,
            "threshold_relaxation_forbidden": True},
        "counts": counts,
        "checksums": {
            "v1_plan_csv_sha256": _sha256(V1_PLAN_CSV),
            "cell_event_census_v0_1_sha256": _sha256(CELL_EVENTS),
            "scene_census_v0_1_sha256": _sha256(SCENE_TABLE),
            "mgrs_footprints_v0_1_sha256": _sha256(MGRS_GPKG),
            "plan_v2_csv_sha256":
                hashlib.sha256(out_csv.read_bytes()).hexdigest()},
        "rows": json.loads(plan.to_json(orient="records",
                                        date_format="iso")),
    }
    Path(args.out_json).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8")

    supersession = {
        "product": "national_pilot_event_plan_v1_v2_supersession",
        "issue": 19,
        "generated_utc": _now(),
        "git_commit": _git_commit(),
        "v1_plan_csv_sha256": _sha256(V1_PLAN_CSV),
        "v2_plan_csv_sha256": manifest["checksums"]["plan_v2_csv_sha256"],
        "counts": counts,
        "rows": super_rows}
    Path(args.out_supersession).write_text(
        json.dumps(supersession, indent=2, ensure_ascii=False,
                   default=str),
        encoding="utf-8")
    print(json.dumps({"counts": counts,
                      "plan_csv": str(out_csv.relative_to(REPO_ROOT))},
                     indent=2, default=str))
    return 0


def _v2_row(
    cell_id: str, slot: Any, variant: str, pid: str, pick: Any,
    result: dict[str, Any], *, sensor: str,
    pass_dir: str, change: str,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "product_id": pid, "cell_id": cell_id, "sensor": sensor,
        "year": slot.year, "priority": slot.priority,
        "variant": variant, "status": STATUS_ELIGIBLE,
        "event_id": str(pick.event_id),
        "event_utc": str(pick.utc),
        "doy": int(pick.doy),
        "season_tag": AUTUMN_TAG,
        "coverage": "FULL_CELL_COVERED_ACTUAL_MASK_V2",
        "coverage_tier": TIER_ACTUAL,
        "coverage_basis": (BASIS_S2_V2 if sensor == "sentinel2"
                           else BASIS_S1_V2),
        "coverage_fraction": float(result["fraction"]),
        "cloud_fraction": (float(pick.cloud_fraction)
                           if sensor == "sentinel2" else ""),
        "pass": pass_dir if sensor == "sentinel1" else "",
        "relative_orbit": (int(pick.relative_orbit)
                           if sensor == "sentinel1" else ""),
        "platform": str(pick.platform) if sensor == "sentinel1" else "",
        "scene_ids": (str(pick.scene_ids) if sensor == "sentinel2"
                      else str(pick.scene_id)),
        "product_ids_source": (str(pick.product_ids)
                               if sensor == "sentinel2" else ""),
        "mgrs_tiles": (str(pick.mgrs_tiles)
                       if sensor == "sentinel2" else ""),
        "wrs_path": "", "wrs_row": "",
        "member_scene_count": (int(pick.member_scene_count)
                               if sensor == "sentinel2" else 1),
        "selection_reason": (
            "PILOT_EVENT_SELECTION_V2: actual observed mask >= 0.95 over "
            "the locked export grid; nominal geometry prefilter only; "
            "rank rules unchanged; no labels used"),
        "selection_detail": json.dumps(
            {"v2_change": change,
             "actual_observed_fraction": float(result["fraction"]),
             "evidence_source": result["evidence_source"],
             "rank_of_pick": next(
                 e["rank"] for e in result["evaluated"]
                 if e["event_id"] == str(pick.event_id)),
             "n_candidates_evaluated": len(result["evaluated"]),
             "evaluated_fractions": [
                 {"rank": e["rank"], "event_id": e["event_id"],
                  "fraction": e["actual_observed_fraction"],
                  "source": e["evidence_source"]}
                 for e in result["evaluated"]]},
            ensure_ascii=False),
        "selection_version": "V2",
        "v2_change": change,
        "v2_actual_observed_fraction": float(result["fraction"]),
        "v2_candidates_evaluated": len(result["evaluated"]),
        "v2_evidence_source": result["evidence_source"]}
    return row


def _v2_empty_row(
    cell_id: str, slot: Any, variant: str, pid: str,
    result: dict[str, Any], *, sensor: str, change: str,
) -> dict[str, Any]:
    evaluated = result["evaluated"]
    best = max((e["actual_observed_fraction"] for e in evaluated),
               default=None)
    return {
        "product_id": pid if result["status"] == STATUS_NO_ELIGIBLE else "",
        "cell_id": cell_id, "sensor": sensor, "year": slot.year,
        "priority": slot.priority, "variant": variant,
        "status": result["status"],
        "event_id": "", "event_utc": "", "doy": "", "season_tag": "",
        "coverage": "", "coverage_tier": "", "coverage_basis": "",
        "coverage_fraction": "", "cloud_fraction": "",
        "pass": "", "relative_orbit": "", "platform": "",
        "scene_ids": "", "product_ids_source": "", "mgrs_tiles": "",
        "wrs_path": "", "wrs_row": "", "member_scene_count": "",
        "selection_reason": (
            "NO_ELIGIBLE_EVENT_ACTUAL_MASK: no candidate reached actual "
            "observed fraction >= 0.95; threshold not relaxed"),
        "selection_detail": json.dumps(
            {"v2_change": change, "best_fraction": best,
             "n_candidates_evaluated": len(evaluated),
             "evaluated_fractions": [
                 {"rank": e["rank"], "event_id": e["event_id"],
                  "fraction": e["actual_observed_fraction"],
                  "source": e["evidence_source"]}
                 for e in evaluated]}, ensure_ascii=False),
        "selection_version": "V2",
        "v2_change": change,
        "v2_actual_observed_fraction": best if best is not None else "",
        "v2_candidates_evaluated": len(evaluated),
        "v2_evidence_source": ""}


def _counts(
    plan: pd.DataFrame, super_rows: list[dict[str, Any]],
    v1_selected: int,
) -> dict[str, Any]:
    v2_eligible = plan[plan["status"] == STATUS_ELIGIBLE]
    # Landsat rows are inherited wholesale WITH their V1 status; only
    # V1 SELECTED optical products count toward the V2-eligible set.
    landsat_sel = plan[
        (plan["v2_change"] == CHANGE_LANDSAT)
        & (plan["status"] == "SELECTED")]
    landsat_all = plan[plan["v2_change"] == CHANGE_LANDSAT]
    no_elig = plan[plan["status"] == STATUS_NO_ELIGIBLE]
    no_scene = plan[plan["status"] == STATUS_NO_SCENE]
    changes = pd.Series([r["change"] for r in super_rows]).value_counts()
    eligible = pd.concat([
        v2_eligible[["sensor"]], landsat_sel[["sensor"]]])
    return {
        "V1_SELECTED": int(v1_selected),
        "V2_PLAN_ROWS": int(len(plan)),
        "V2_ELIGIBLE_TOTAL": int(len(v2_eligible) + len(landsat_sel)),
        "V2_ELIGIBLE_S2_S1": int(len(v2_eligible)),
        "V2_LANDSAT_INHERITED_ROWS": int(len(landsat_all)),
        "V2_LANDSAT_INHERITED_SELECTED": int(len(landsat_sel)),
        "V2_REPLACED": int(changes.get(
            "REPLACED_V1_EVENT_FAILED_ACTUAL_MASK", 0)),
        "V2_KEPT_SAME_EVENT": int(changes.get(
            "KEPT_SAME_EVENT_PASSES_ACTUAL_MASK", 0)),
        "V2_NEW_ELIGIBLE": int(changes.get("NEW_ELIGIBLE_V2_ACTUAL_MASK",
                                          0)),
        "V1_SELECTED_BUT_NO_ELIGIBLE_ACTUAL_MASK": int(changes.get(
            "V1_SELECTED_BUT_NO_ELIGIBLE_ACTUAL_MASK", 0)),
        "V2_NO_ELIGIBLE_EVENT_ACTUAL_MASK": int(len(no_elig)),
        "V2_NO_SCENE": int(len(no_scene)),
        "v2_eligible_by_sensor": (
            eligible.groupby("sensor").size().to_dict()),
        "change_counts": {k: int(v) for k, v in changes.items()},
        "scientific_denominator": (
            "V2_ELIGIBLE_TOTAL (honest set; not forced to V1_SELECTED)")}


if __name__ == "__main__":
    raise SystemExit(main())
