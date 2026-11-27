#!/usr/bin/env python3
"""Issue #19 Phase M -- storage / scaling study (offline; no GEE calls).

Answers section H of Issue #19 from measured bytes and the frozen
metadata census, without launching any export:

* bytes per cell-year-event -- measured LZW/GeoTIFF byte factors from the
  27 real M2.1b products, applied to the EXACT per-cell native-UTM export
  grids (30 m / 10 m) of every W10_DOMAIN_V1_CORE_FROZEN cell;
* GEE export/task counts -- exact metadata counts obtained by replaying
  the predeclared Phase C selection policy over the frozen v0_1 census
  for the 3,016 KEEP cells (strict tier via census flags; Landsat
  near-full tier via the same nominal WRS-2 frame intersection; S2 via
  same-datatake member-tile union; S1 per pass); aggregates only, no
  per-cell national event plan is emitted (that is Issue #20);
* pilot scenario -- the 194 selected products of the frozen 20-cell plan;
* minimal national scenario -- the same five anchor slots per cell;
* standard national scenario -- one product per cell x sensor x year
  (S1 per pass) over full operational years (scenario assumption, clearly
  marked, not a production policy);
* bottlenecks, throughput evidence and restart/resume behaviour.

Every projected figure carries an explicit MEASURED / ESTIMATE token.

Outputs:
* datasets/manifests/national_pilot19_storage_study_v1.json
* datasets/manifests/national_pilot19_storage_study_v1.csv
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts/data/national"))

import geopandas as gpd  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import rasterio  # noqa: E402
from build_pilot_label_supports_v1 import cell_utm_bounds  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

from spartina.data.gee.grid import covering_grid  # noqa: E402
from spartina.data.national.census_join import s2_event_group_id  # noqa: E402
from spartina.data.national.geometry import cell_polygon_wgs84  # noqa: E402
from spartina.data.national.grid import GridKind, GridSpec  # noqa: E402
from spartina.data.national.pilot_events import (  # noqa: E402
    AUTUMN_TAG,
    FULL_COVER,
    NEAR_FULL_NOMINAL_MIN,
    S1_DUAL_POL_TOKENS,
    S1_IW,
)

REGISTRY_CSV = (
    REPO_ROOT / "datasets/manifests/china_coastal_cells_v1_1_core_frozen.csv")
PANEL_CSV = REPO_ROOT / "datasets/manifests/national_first_pixel_panel_v1.csv"
PLAN_CSV = REPO_ROOT / "datasets/manifests/national_pilot_event_plan_v1.csv"
PLAN_JSON = REPO_ROOT / "datasets/manifests/national_pilot_event_plan_v1.json"
SUPERSESSION_DOC = (
    REPO_ROOT / "docs/data/national/CHINA_EO_CENSUS_SUPERSESSION_v0_1.json")
CENSUS_DIR = REPO_ROOT / "work/national/census_r1/products"
CELL_EVENTS = CENSUS_DIR / "china_cell_event_census_v0_1.parquet"
SCENE_TABLE = CENSUS_DIR / "china_eo_scene_census_v0_1.parquet"
MGRS_GPKG = REPO_ROOT / "work/national/footprints/mgrs_china_coast_v0_1.gpkg"
WRS2_GPKG = REPO_ROOT / "work/national/footprints/wrs2_china_coast_v0_1.gpkg"
M21B_PRODUCTS = REPO_ROOT / "work/m21b/products"
M21B_TASK_STORE = REPO_ROOT / "work/m21b/tasks/task_store.json"
PILOT_LABEL_DIR = REPO_ROOT / "work/national/pilot19/labels"
OUT_JSON = (
    REPO_ROOT / "datasets/manifests/national_pilot19_storage_study_v1.json")
OUT_CSV = (
    REPO_ROOT / "datasets/manifests/national_pilot19_storage_study_v1.csv")

KEEP_STATES = ("KEEP_MAINLAND_COASTAL", "KEEP_ISLAND_COASTAL")
OPTICAL_CLOUD_MAX = 0.30

#: Full-year (non-YTD) operational ranges used by the STANDARD scenario.
#: 2026 is partial in census v0_1 and is excluded from the standard base;
#: raw pre-gate 2026 presence is carried as a memo only.
STANDARD_YEARS: dict[str, list[int]] = {
    "landsat5": list(range(1984, 2012)),
    "landsat7": list(range(1999, 2024)),
    "landsat8": list(range(2013, 2026)),
    "landsat9": list(range(2022, 2026)),
    "sentinel1": list(range(2015, 2026)),
    "sentinel2": list(range(2015, 2026)),
}
STANDARD_ADD_ON = ("landsat9",)

#: GEE export tasks / Drive files landed per product bundle, as proven by
#: the M2.1b real run (valid masks are computed server-side and exported
#: as their own single-band file; QA_PIXEL is exported separately).
BUNDLE_COMPONENTS: dict[str, tuple[str, ...]] = {
    "landsat5": ("l57_sr", "l_qa", "l_valid"),
    "landsat7": ("l57_sr", "l_qa", "l_valid"),
    "landsat8": ("l89_sr", "l_qa", "l_valid"),
    "landsat9": ("l89_sr", "l_qa", "l_valid"),
    "sentinel2": ("s2_sr", "s2_valid"),
    "sentinel1": ("s1_vvvh",),
}
#: Uncompressed bytes per pixel (bands x dtype) per component.
RAW_BPP: dict[str, float] = {
    "l57_sr": 6.0 * 4.0,   # six SR bands x float32 (L5 TM / L7 ETM+)
    "l89_sr": 7.0 * 4.0,   # seven SR bands x float32 (L8/L9 OLI)
    "l_qa": 1.0 * 2.0,     # QA_PIXEL uint16
    "l_valid": 1.0 * 1.0,  # derived valid mask uint8
    "s2_sr": 4.0 * 4.0,    # B/B/G/R/NIR float32
    "s2_valid": 1.0 * 1.0,
    "s1_vvvh": 2.0 * 4.0,  # VV + VH float32
}
PIXEL_RES: dict[str, str] = {
    "landsat5": "30m", "landsat7": "30m", "landsat8": "30m",
    "landsat9": "30m", "sentinel2": "10m", "sentinel1": "10m"}

TOKEN_MEASURED = "MEASURED_M21B_LZW_GEOTIFF"
TOKEN_L57_EST = (
    "ESTIMATE_FLOAT32_LZW_RATIO_BORROWED_FROM_L8_TODO_MEASURE_AT_PHASE_D")


@dataclass(frozen=True)
class ByteFactor:
    """Measured/derived LZW byte factor for one product component."""

    component: str
    n_samples: int
    raw_bytes_per_pixel: float
    ratio_mean: float
    ratio_min: float
    ratio_max: float
    token: str

    def bytes_per_pixel(self, variant: str = "mean") -> float:
        ratio = {"mean": self.ratio_mean, "low": self.ratio_min,
                 "high": self.ratio_max}[variant]
        return self.raw_bytes_per_pixel * ratio

    def to_dict(self) -> dict[str, float | str | int]:
        return {
            "component": self.component,
            "n_samples": self.n_samples,
            "raw_bytes_per_pixel": self.raw_bytes_per_pixel,
            "lzw_ratio_mean": round(self.ratio_mean, 6),
            "lzw_ratio_min": round(self.ratio_min, 6),
            "lzw_ratio_max": round(self.ratio_max, 6),
            "bytes_per_pixel_mean": round(self.bytes_per_pixel(), 4),
            "bytes_per_pixel_low": round(self.bytes_per_pixel("low"), 4),
            "bytes_per_pixel_high": round(self.bytes_per_pixel("high"), 4),
            "evidence_token": self.token,
        }


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


# ---------------------------------------------------------------------------
# Measured byte factors (M2.1b real exports)
# ---------------------------------------------------------------------------

def measure_byte_factors() -> dict[str, ByteFactor]:
    """Measure LZW byte factors directly from the 27 M2.1b GeoTIFFs."""
    samples: dict[str, list[tuple[int, float]]] = {
        k: [] for k in RAW_BPP}
    for path in sorted(glob.glob(str(M21B_PRODUCTS / "*.tif"))):
        name = os.path.basename(path)
        if "_S1_" in name:
            component = "s1_vvvh"
        elif "_S2_" in name and "_valid_" in name:
            component = "s2_valid"
        elif "_S2_" in name:
            component = "s2_sr"
        elif "_qapixel_" in name:
            component = "l_qa"
        elif "_valid_" in name:
            component = "l_valid"
        else:  # L8/L9 SR
            component = "l89_sr"
        with rasterio.open(path) as ds:
            raw = ds.width * ds.height * ds.count * np.dtype(
                ds.dtypes[0]).itemsize
        samples[component].append((raw, os.path.getsize(path) / raw))

    factors: dict[str, ByteFactor] = {}
    for component, obs in samples.items():
        if not obs:
            # Filled in below (L5/L7 SR ratio is borrowed from L8/L9).
            continue
        ratios = [r for _, r in obs]
        factors[component] = ByteFactor(
            component, len(obs), RAW_BPP[component],
            float(np.mean(ratios)), float(np.min(ratios)),
            float(np.max(ratios)), TOKEN_MEASURED)
    if "l57_sr" not in factors:
        # L5/L7 SR was not exported in M2.1b: borrow the measured L8/L9
        # float32 LZW ratio (same physical-scaling pipeline) and flag it.
        ref = factors["l89_sr"]
        factors["l57_sr"] = ByteFactor(
            "l57_sr", 0, RAW_BPP["l57_sr"],
            ref.ratio_mean, ref.ratio_min, ref.ratio_max, TOKEN_L57_EST)
    return factors


# ---------------------------------------------------------------------------
# Per-cell export grids (exact, native UTM; no GEE)
# ---------------------------------------------------------------------------

def national_grid_pixels(keep: pd.DataFrame) -> pd.DataFrame:
    """Exact covering-grid pixel counts for every KEEP cell at 30/10 m."""
    out: list[tuple[str, int, int, int]] = []
    for r in keep.itertuples():
        zone = int(np.floor((r.center_lon + 180.0) / 6.0)) + 1
        epsg, bounds = cell_utm_bounds(r.cell_id, zone)
        g30 = covering_grid(bounds, epsg, 30)
        g10 = covering_grid(bounds, epsg, 10)
        out.append((r.cell_id, zone, g30.width * g30.height,
                    g10.width * g10.height))
    return pd.DataFrame(out, columns=["cell_id", "utm_zone", "px30", "px10"])


# ---------------------------------------------------------------------------
# Eligibility replay over the frozen census (aggregates only)
# ---------------------------------------------------------------------------

def _cell_polygons(cell_ids: list[str]) -> gpd.GeoDataFrame:
    spec = GridSpec(GridKind.CHINA_ALBERS)
    geom: list[Any] = []
    for cid in cell_ids:
        tok = cid.removeprefix("CNA10K-")
        row = int(tok.split("-")[0].removeprefix("R"))
        col = int(tok.split("-")[1].removeprefix("C"))
        geom.append(cell_polygon_wgs84(spec, row, col))
    return gpd.GeoDataFrame(
        {"cell_id": cell_ids}, geometry=geom, crs=4326)


def landsat_eligibility(
    ce: pd.DataFrame, scenes: pd.DataFrame, cell_geom: dict[str, Any],
    frame_geom: dict[tuple[int, int], Any], sensors: list[str],
    years: list[int],
) -> dict[str, dict[str, dict[int, set[str]]]]:
    """Strict + near-only eligible cell sets per Landsat sensor per year."""
    result: dict[str, dict[str, dict[int, set[str]]]] = {}
    attrs_cols = ["event_id", "year", "cloud_cover", "wrs_path", "wrs_row"]
    for sensor in sensors:
        e = ce[(ce.sensor == sensor) & (ce.year.isin(years))
               & (ce.season_tag == AUTUMN_TAG)]
        j = e.merge(
            scenes[(scenes.sensor == sensor)][attrs_cols],
            on=["event_id", "year"], how="left")
        j["cloud"] = pd.to_numeric(j.cloud_cover, errors="coerce") / 100.0
        j = j[j.cloud <= OPTICAL_CLOUD_MAX]
        strict = {
            int(y): set(g.cell_id)
            for y, g in j[j.coverage == FULL_COVER].groupby("year")}
        part = j[(j.coverage != FULL_COVER)
                 & j.geometry_basis.astype(str).str.startswith("WRS2")]
        near: dict[int, set[str]] = {}
        for r in part.itertuples():
            geom = frame_geom.get((int(r.wrs_path), int(r.wrs_row)))
            if geom is None:
                continue
            cg = cell_geom[str(r.cell_id)]
            if geom.intersection(cg).area / cg.area >= NEAR_FULL_NOMINAL_MIN:
                near.setdefault(int(r.year), set()).add(str(r.cell_id))
        result[sensor] = {
            "strict": {y: strict.get(y, set()) for y in years},
            "near_only": {
                y: near.get(y, set()) - strict.get(y, set()) for y in years},
        }
    return result


def s2_eligibility(
    ce: pd.DataFrame, scenes2: pd.DataFrame,
    tiles_by_cell: dict[str, set[str]],
    tile_geom: dict[str, Any], cell_geom: dict[str, Any],
    years: list[int],
) -> dict[int, set[str]]:
    """Eligible cells per year: same-datatake tile union covers the cell."""
    gran = scenes2.copy()
    e = ce[(ce.sensor == "sentinel2") & (ce.year.isin(years))
           & (ce.season_tag == AUTUMN_TAG)]
    eligible: dict[int, set[str]] = {y: set() for y in years}
    for (cid, year), gev in e.groupby(["cell_id", "year"]):
        members = gran[
            gran.mgrs_tile.isin(tiles_by_cell.get(str(cid), set()))
            & (gran.year == year) & (gran.grp.isin(gev.event_id))]
        if members.empty:
            continue
        cg = cell_geom[str(cid)]
        for _gid, g in members.groupby("grp"):
            union = unary_union(
                [tile_geom[t] for t in set(g.mgrs_tile) if t in tile_geom])
            cloud = float(pd.to_numeric(
                g.cloudy_pixel_percent, errors="coerce").max()) / 100.0
            if union.covers(cg) and cloud <= OPTICAL_CLOUD_MAX:
                eligible[int(year)].add(str(cid))
                break
    return eligible


def s1_pass_eligibility(
    ce: pd.DataFrame, scenes: pd.DataFrame, years: list[int],
) -> dict[tuple[int, str], set[str]]:
    """Eligible cells per (year, pass): autumn IW VV+VH GRD."""
    j = ce[(ce.sensor == "sentinel1") & (ce.year.isin(years))
           & (ce.season_tag == AUTUMN_TAG)].merge(
        scenes[(scenes.sensor == "sentinel1")][[
            "event_id", "year", "pass", "instrument_mode",
            "polarization"]],
        on=["event_id", "year"], how="left")
    j = j[(j.instrument_mode == S1_IW)
          & (j.polarization.isin(S1_DUAL_POL_TOKENS))]
    out: dict[tuple[int, str], set[str]] = {}
    for (year, pass_direction), g in j.groupby(["year", "pass"]):
        if pass_direction in ("ASC", "DESC"):
            out[(int(year), str(pass_direction))] = set(g.cell_id)
    return out


# ---------------------------------------------------------------------------
# Byte accounting
# ---------------------------------------------------------------------------

def bundle_bytes(
    sensor: str, pixels: float, factors: dict[str, ByteFactor],
    variant: str = "mean",
) -> float:
    return sum(
        pixels * factors[c].bytes_per_pixel(variant)
        for c in BUNDLE_COMPONENTS[sensor])


def sum_pixels(
    cells: set[str], dims: pd.DataFrame, column: str,
) -> int:
    if not cells:
        return 0
    idx = dims.set_index("cell_id")
    return int(idx.loc[idx.index.intersection(pd.Index(list(cells))),
                       column].sum())


def line(
    scenario: str, scope: str, sensor: str, slot: str, tier: str,
    pass_direction: str, cells: set[str], dims: pd.DataFrame,
    factors: dict[str, ByteFactor],
) -> dict[str, Any]:
    res = PIXEL_RES[sensor]
    column = "px30" if res == "30m" else "px10"
    pixels = sum_pixels(cells, dims, column)
    n = len(cells)
    components = BUNDLE_COMPONENTS[sensor]
    base = pixels * sum(
        factors[c].bytes_per_pixel() for c in components)
    low = pixels * sum(
        factors[c].bytes_per_pixel(
            "low" if c == "s2_sr" else "mean") for c in components)
    high = pixels * sum(
        factors[c].bytes_per_pixel(
            "high" if c == "s2_sr" else "mean") for c in components)
    return {
        "scenario": scenario, "scope": scope, "sensor": sensor,
        "slot": slot, "tier": tier, "pass": pass_direction,
        "n_products": n,
        "n_gee_tasks": n * len(components),
        "n_files": n * len(components),
        "resolution": res,
        "grid_pixels_sum": pixels,
        "bytes_base": round(base), "bytes_low": round(low),
        "bytes_high": round(high),
        "estimate_tokens": sorted({factors[c].token
                                   for c in components})}


def totals(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "n_products": int(sum(r["n_products"] for r in rows)),
        "n_gee_tasks": int(sum(r["n_gee_tasks"] for r in rows)),
        "n_files": int(sum(r["n_files"] for r in rows)),
        "bytes_base": int(sum(r["bytes_base"] for r in rows)),
        "bytes_low": int(sum(r["bytes_low"] for r in rows)),
        "bytes_high": int(sum(r["bytes_high"] for r in rows))}


# ---------------------------------------------------------------------------
# M2.1b throughput / resume evidence
# ---------------------------------------------------------------------------

def task_store_evidence() -> dict[str, Any]:
    store = json.loads(M21B_TASK_STORE.read_text(encoding="utf-8"))
    tasks: dict[str, dict[str, Any]] = store["tasks"]
    durations: dict[str, list[float]] = {}
    n_completed = 0
    for rec in tasks.values():
        result = rec.get("result", {})
        if result.get("state") != "COMPLETED":
            continue
        n_completed += 1
        start = result.get("start_timestamp_ms")
        update = result.get("update_timestamp_ms")
        if start and update and update > start:
            kind = str(rec["request_id"]).split(":")[1]
            durations.setdefault(kind, []).append((update - start) / 60000.0)
    per_kind = {
        kind: {
            "n": len(v), "minutes_min": round(float(min(v)), 2),
            "minutes_median": round(float(np.median(v)), 2),
            "minutes_max": round(float(max(v)), 2)}
        for kind, v in sorted(durations.items())}
    return {
        "source": str(M21B_TASK_STORE.relative_to(REPO_ROOT)),
        "n_completed_tasks_recorded": n_completed,
        "backend_duration_minutes": per_kind,
        "note": (
            "GEE backend start->update wall time for <=10 km tiles; "
            "small-batch observations, not a quota or SLA measurement; "
            "end-to-end time is polling/Drive-download bound")}


def probe_gee_auth() -> dict[str, Any]:
    project = os.environ.get("SPARTINA_GEE_PROJECT", "")
    try:
        probe = subprocess.run(
            ["earthengine", "ls", "users"], capture_output=True,
            text=True, timeout=20)
        auth_ok = probe.returncode == 0
        detail = (probe.stdout + probe.stderr)[:300]
    except (OSError, subprocess.TimeoutExpired) as exc:
        auth_ok = False
        detail = f"probe failed: {exc}"
    return {
        "spartina_gee_project_set": bool(project),
        "earthengine_ls_users_ok": auth_ok,
        "detail": detail.replace("\n", " ")[:300],
        "phase_d_e_status": "BLOCKED_OWNER_GEE_REAUTHENTICATION_REQUIRED"
        if not (project and auth_ok) else "AVAILABLE"}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-csv", default=str(OUT_CSV))
    args = parser.parse_args()

    supersession = json.loads(
        SUPERSESSION_DOC.read_text(encoding="utf-8"))
    fingerprints = dict(supersession["product_fingerprints_sha256"])
    for name, expected in fingerprints.items():
        got = _sha256(CENSUS_DIR / name)
        if got != expected:
            raise SystemExit(
                f"frozen census input {name} checksum mismatch")

    factors = measure_byte_factors()
    print("byte factors measured:", {
        k: (v.n_samples, round(v.ratio_mean, 4))
        for k, v in factors.items()})

    registry = pd.read_csv(REGISTRY_CSV)
    keep = registry[registry.membership_v1_1.isin(KEEP_STATES)].copy()
    panel = pd.read_csv(PANEL_CSV)
    plan = pd.read_csv(PLAN_CSV)
    panel_ids = list(panel.cell_id)
    keep_ids = list(keep.cell_id)
    print(f"domain KEEP cells: {len(keep)}; computing per-cell grids...")
    dims = national_grid_pixels(keep)

    print("replaying eligibility policy over frozen census...")
    ce = pd.read_parquet(CELL_EVENTS)
    ce = ce[ce.cell_id.isin(keep_ids)].copy()
    scenes = pd.read_parquet(SCENE_TABLE)

    polys = _cell_polygons(keep_ids)
    cell_geom = dict(zip(polys.cell_id, polys.geometry, strict=True))
    wrs = gpd.read_file(WRS2_GPKG)[["path", "row", "geometry"]].to_crs(4326)
    frame_geom = {
        (int(r.path), int(r.row)): r.geometry
        for r in wrs.itertuples(index=False)}
    mgrs = gpd.read_file(MGRS_GPKG)[["mgrs_tile", "geometry"]]
    tile_geom = dict(zip(mgrs.mgrs_tile, mgrs.geometry, strict=True))
    cell_tiles = gpd.sjoin(
        polys, mgrs, how="left", predicate="intersects")[
        ["cell_id", "mgrs_tile"]].dropna()
    tiles_by_cell = {
        str(cid): set(g.mgrs_tile)
        for cid, g in cell_tiles.groupby("cell_id")}

    all_years = sorted({y for ys in STANDARD_YEARS.values() for y in ys}
                       | {1990, 2000, 2015, 2020, 2021})
    land = landsat_eligibility(
        ce, scenes, cell_geom, frame_geom,
        ["landsat5", "landsat7", "landsat8", "landsat9"], all_years)
    s2sc = scenes[scenes.sensor == "sentinel2"].copy()
    s2sc["utc_day"] = pd.to_datetime(
        s2sc.utc, utc=True, format="ISO8601").dt.date.astype(str)
    s2sc["grp"] = [
        s2_event_group_id(str(d), str(day))
        for d, day in zip(s2sc.datatake_identifier, s2sc.utc_day,
                          strict=True)]
    s2 = s2_eligibility(
        ce, s2sc, tiles_by_cell, tile_geom, cell_geom,
        sorted(set(STANDARD_YEARS["sentinel2"]) | {2015, 2020, 2021}))
    s1 = s1_pass_eligibility(
        ce, scenes, sorted(set(STANDARD_YEARS["sentinel1"]) | {2015, 2020, 2021}))
    print("eligibility replay complete")

    rows: list[dict[str, Any]] = []

    # -- Pilot scenario: the frozen plan's SELECTED products --------------
    selected = plan[plan.status == "SELECTED"]
    pilot_dims = dims[dims.cell_id.isin(panel_ids)]
    pilot_counts = selected.groupby("sensor").size().to_dict()
    for rec in selected.to_dict("records"):
        cells = {str(rec["cell_id"])}
        sensor = str(rec["sensor"])
        s1_pass = str(rec["pass"]) if sensor == "sentinel1" else ""
        slot = f"anchor_{rec['year']}" + (
            f"_{s1_pass}" if sensor == "sentinel1" else "")
        tier = ("near_full" if rec["coverage_tier"]
                == "NEAR_FULL_NOMINAL_TOLERANCE"
                else ("s1_actual_footprint" if sensor == "sentinel1"
                      else "strict"))
        rows.append(line(
            "pilot_20_cell", "observed_plan", sensor, slot, tier,
            s1_pass, cells, pilot_dims, factors))

    # -- Minimal national scenario: anchor slots over 3,016 KEEP cells ----
    minimal_rows: list[dict[str, Any]] = []

    def add_land_slot(
        sensor: str, slot_name: str,
        cells_strict: set[str], cells_near: set[str],
    ) -> None:
        minimal_rows.append(line(
            "national_minimal_anchors", "national_3016", sensor, slot_name,
            "strict", "", cells_strict, dims, factors))
        minimal_rows.append(line(
            "national_minimal_anchors", "national_3016", sensor, slot_name,
            "near_full_only", "", cells_near, dims, factors))

    add_land_slot("landsat5", "anchor_1990_L5",
                  land["landsat5"]["strict"][1990],
                  land["landsat5"]["near_only"][1990])
    # 2000: L5 preferred, L7 fills only cells L5 cannot cover (sequential).
    l5_covered = (land["landsat5"]["strict"][2000]
                  | land["landsat5"]["near_only"][2000])
    l7_fill_strict = (land["landsat7"]["strict"][2000] - l5_covered)
    l7_fill_near = (land["landsat7"]["near_only"][2000] - l5_covered
                    - l7_fill_strict)
    add_land_slot("landsat5", "anchor_2000_L5_preferred",
                  land["landsat5"]["strict"][2000],
                  land["landsat5"]["near_only"][2000])
    add_land_slot("landsat7", "anchor_2000_L7_fallback_fill",
                  l7_fill_strict, l7_fill_near)
    for sensor, year in (("landsat8", 2015), ("landsat8", 2020),
                         ("landsat8", 2021)):
        add_land_slot(sensor, f"anchor_{year}_{sensor[-2:]}",
                      land[sensor]["strict"][year],
                      land[sensor]["near_only"][year])
    for year in (2015, 2020, 2021):
        minimal_rows.append(line(
            "national_minimal_anchors", "national_3016", "sentinel2",
            f"anchor_{year}_S2", "strict_datatake_union", "",
            s2.get(year, set()), dims, factors))
        for pass_direction in ("ASC", "DESC"):
            minimal_rows.append(line(
                "national_minimal_anchors", "national_3016", "sentinel1",
                f"anchor_{year}_S1", "actual_footprint", pass_direction,
                s1.get((year, pass_direction), set()), dims, factors))
    rows.extend(minimal_rows)

    # -- Standard national scenario: annual per sensor series -------------
    standard_rows: list[dict[str, Any]] = []
    for sensor, years in STANDARD_YEARS.items():
        role = ("add_on_not_in_pilot_contract"
                if sensor in STANDARD_ADD_ON else "core_series")
        if sensor == "sentinel1":
            for year in years:
                for pass_direction in ("ASC", "DESC"):
                    standard_rows.append(line(
                        "national_standard_annual", role, sensor,
                        f"annual_{year}", "actual_footprint",
                        pass_direction,
                        s1.get((year, pass_direction), set()),
                        dims, factors))
        elif sensor == "sentinel2":
            for year in years:
                standard_rows.append(line(
                    "national_standard_annual", role, sensor,
                    f"annual_{year}", "strict_datatake_union", "",
                    s2.get(year, set()), dims, factors))
        else:
            for year in years:
                standard_rows.append(line(
                    "national_standard_annual", role, sensor,
                    f"annual_{year}", "strict", "",
                    land[sensor]["strict"].get(year, set()),
                    dims, factors))
                standard_rows.append(line(
                    "national_standard_annual", role, sensor,
                    f"annual_{year}", "near_full_only", "",
                    land[sensor]["near_only"].get(year, set()),
                    dims, factors))
    rows.extend(standard_rows)

    # -- Label supports (measured pilot bytes; national projection) -------
    label_files = [
        Path(p) for p in glob.glob(str(PILOT_LABEL_DIR / "**" / "*.tif"),
                                   recursive=True)]
    label_bytes = sum(p.stat().st_size for p in label_files)
    label_per_cell = label_bytes / len(panel_ids)
    label_national_est = int(round(label_per_cell * len(keep_ids)))

    # -- Pilot source-event dedup evidence ---------------------------------
    dedup = []
    for sensor, g in selected.groupby("sensor"):
        n_events = g.event_id.nunique()
        dedup.append({
            "sensor": sensor, "n_products": int(len(g)),
            "n_distinct_source_events": int(n_events),
            "products_per_source_event": round(len(g) / n_events, 3)})

    standard_core = [
        r for r in standard_rows if r["scope"] == "core_series"]
    standard_addon = [
        r for r in standard_rows if r["scope"] == "add_on_not_in_pilot_contract"]
    pilot_bytes_total = sum(
        os.path.getsize(p)
        for p in glob.glob(str(M21B_PRODUCTS / "*.tif")))

    manifest: dict[str, Any] = {
        "product": "national_pilot19_storage_study_v1",
        "issue": 19,
        "phase": "M",
        "generated_utc": datetime.now(UTC).isoformat(),
        "git_commit": _git_commit(),
        "status": (
            "STUDY_ONLY; no GEE calls made; no national batch launched; "
            "aggregates only (no per-cell national event plan)"),
        "domain": {
            "version": "W10_DOMAIN_V1_CORE_FROZEN",
            "n_keep_cells": len(keep_ids),
            "keep_states": list(KEEP_STATES),
            "utm_zones": {
                str(k): int(v)
                for k, v in dims.utm_zone.value_counts().sort_index().items()},
            "export_grid_pixels_30m": {
                "mean": int(dims.px30.mean()), "min": int(dims.px30.min()),
                "max": int(dims.px30.max())},
            "export_grid_pixels_10m": {
                "mean": int(dims.px10.mean()), "min": int(dims.px10.min()),
                "max": int(dims.px10.max())},
            "grid_rule": (
                "cell native UTM zone from WGS84 centroid; edges densified "
                "21 points/edge before projection; covering_grid origin "
                "snapped to pixel multiples (same rule as label supports)")},
        "inputs": {
            "registry_csv": REGISTRY_CSV.name,
            "census_version": "v0_1",
            "census_supersession_doc": SUPERSESSION_DOC.name,
            "m21b_products_dir": str(M21B_PRODUCTS.relative_to(REPO_ROOT)),
            "n_m21b_tifs": len(
                glob.glob(str(M21B_PRODUCTS / "*.tif"))),
            "m21b_bytes_total": pilot_bytes_total,
            "pilot_plan_csv": PLAN_CSV.name,
            "pilot_selected_products": int(len(selected)),
            "checksums": {
                "registry_csv_sha256": _sha256(REGISTRY_CSV),
                "panel_csv_sha256": _sha256(PANEL_CSV),
                "plan_csv_sha256": _sha256(PLAN_CSV),
                "cell_event_census_v0_1_sha256": _sha256(CELL_EVENTS),
                "scene_census_v0_1_sha256": _sha256(SCENE_TABLE),
                "wrs2_footprints_v0_1_sha256": _sha256(WRS2_GPKG),
                "mgrs_footprints_v0_1_sha256": _sha256(MGRS_GPKG)}},
        "byte_factors": {k: v.to_dict() for k, v in factors.items()},
        "bundle_task_model": {
            sensor: {
                "components": list(components),
                "gee_tasks_per_product": len(components),
                "files_per_product": len(components),
                "resolution": PIXEL_RES[sensor]}
            for sensor, components in BUNDLE_COMPONENTS.items()},
        "pilot_scenario": {
            "scope": "20 fixed panel cells",
            "selected_products_by_sensor": {
                k: int(v) for k, v in pilot_counts.items()},
            **totals([r for r in rows
                      if r["scenario"] == "pilot_20_cell"]),
            "source_event_dedup": dedup,
            "label_supports": {
                "n_tifs": len(label_files),
                "bytes_measured": int(label_bytes),
                "bytes_per_cell_measured": round(label_per_cell, 1)}},
        "national_minimal_scenario": {
            "scope": "3,016 KEEP cells; five anchor slots (1990/2000/2015/"
                     "2020/2021); S1 one product per pass; 2000 L5->L7 "
                     "sequential fallback; strict + Landsat near-full tiers",
            **totals(minimal_rows)},
        "national_standard_scenario": {
            "scope": (
                "3,016 KEEP cells; one selected product per cell x sensor x "
                "year under the same predeclared gates; S1 per pass; full "
                "operational years only (2026 YTD excluded); L7 and L8 both "
                "retained in overlap years (conservative per-series upper "
                "bound); SCENARIO ASSUMPTION FOR SIZING, NOT A PRODUCTION "
                "POLICY"),
            "years": {k: [min(v), max(v)] for k, v in STANDARD_YEARS.items()},
            "core_series": totals(standard_core),
            "landsat9_add_on": totals(standard_addon),
            "core_plus_l9": totals(standard_core + standard_addon),
            "y2026_memo_pre_gate_autumn_cells": {
                "landsat8": 1601, "landsat9": 2793,
                "sentinel1": 2891, "sentinel2": 3016,
                "note": "raw census presence before cloud/coverage gates; "
                        "excluded from base because census v0_1 2026 is YTD"}},
        "label_supports_national_projection": {
            "basis": "pilot measured mean per cell x 3,016",
            "pilot_n_tifs_per_cell": len(label_files) // len(panel_ids),
            "pilot_bytes_per_cell": round(label_per_cell, 1),
            "national_bytes_estimate": label_national_est,
            "token": "ESTIMATE_PILOT_MEAN_ONE_TIME_LABEL_BYTES"},
        "throughput_evidence": task_store_evidence(),
        "bottlenecks": [
            "GEE project/auth currently unavailable: Phase D/E hard blocker",
            f"~{totals(minimal_rows)['n_gee_tasks']:,} GEE export tasks for "
            "the minimal anchor run; orchestration is task-poll/Drive bound, "
            "not compute (observed backend minutes per <=10 km tile)",
            "per-cell clips re-export shared source events (pilot: 194 "
            "products from 135 distinct events; S1 1.60 products/event); "
            "Issue #20 should evaluate one export per source event on a "
            "union bbox plus local windowing",
            "float32 SR barely compresses under LZW (L8 ratio ~1.08, S1 "
            "~1.11); storage is dominated by SR bytes, masks are <1%",
            "Google Drive is the staging lane; official concurrent-task and "
            "download quotas are TODO_VERIFY against the live project",
            "Landsat near-full products carry the Phase H >=0.95 geometric "
            "valid gate; failures force re-selection and re-export",
            "native UTM zones span 48-52; cross-zone S2 same-datatake "
            "mosaics already supported by the selection policy"],
        "restart_resume": {
            "task_store": "spartina.data.gee.tasks.TaskStore persists "
                          "stable ids, attempt history and terminal state",
            "request_ids": "deterministic request_id -> get_by_request_id "
                           "resume; list_non_terminal after a crash",
            "attempts": "max 3 attempts with recorded errors before FAILED",
            "drive": "driveio.find_latest_file/download_latest by prefix; "
                     "M2.1b r3->r4->r5 revisions show the re-run path",
            "idempotency": "product_id + revision named exports; landed "
                           "products carry per-product manifest and "
                           "checksums, so skip-if-landed is possible"},
        "estimate_tokens": {
            TOKEN_MEASURED: "LZW bytes measured from 27 real M2.1b exports",
            TOKEN_L57_EST: "no L5/L7 M2.1b export exists; ratio borrowed",
            "ESTIMATE_PILOT_MEAN_ONE_TIME_LABEL_BYTES":
                "label bytes projected from the 20-cell pilot mean",
            "S2_SR_RANGE": "bytes_low/high span the 10 measured S2 SR "
                           "LZW ratios (0.49-0.83); all other components "
                           "use their measured mean (S1 n=1)"},
        "gee_auth_probe": probe_gee_auth(),
    }

    out_rows = pd.DataFrame(rows)
    out_csv = Path(args.out_csv)
    out_rows.to_csv(out_csv, index=False)
    manifest["checksums"] = {"study_csv_sha256": _sha256(out_csv)}
    out_json = Path(args.out_json)
    out_json.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8")
    print(json.dumps({
        "pilot": manifest["pilot_scenario"]["n_products"],
        "minimal_tasks":
            manifest["national_minimal_scenario"]["n_gee_tasks"],
        "minimal_bytes_base":
            manifest["national_minimal_scenario"]["bytes_base"],
        "standard_core_bytes_base":
            manifest["national_standard_scenario"]["core_series"][
                "bytes_base"],
        "out": str(out_json)}, indent=2))


if __name__ == "__main__":
    main()
