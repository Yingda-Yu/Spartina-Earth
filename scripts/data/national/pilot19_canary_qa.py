#!/usr/bin/env python3
"""Issue #19 canary Phase H/I QA gate (real pixels only).

Runs AFTER the five canary products have landed. Every dimension emits
an explicit PASS / WARN / FAIL / SKIPPED. Any FAIL is a canary hard
stop: the remaining 390 pilot tasks must not be submitted.

Dimensions:
* manifest integrity (files, sizes, independently recomputed SHA-256);
* component grid consistency from the GeoTIFF headers themselves;
* independent grid rebuild straight from the frozen W10 Albers cell and
  ``spartina.data.gee.grid.covering_grid`` (the Phase F/G rule), cross
  checked against both EO headers and frozen label-adapter headers;
* Landsat C02 L2 semantics: band accounting (6 L5/L7, 7 L8),
  SR = DN*2.75e-5 - 0.2 with fill masked before scaling (no exact
  -0.2 leak), VALID reconstructed independently at revision r2 (raw
  QA_PIXEL bits + QA_RADSAT + all SR bands observed) locally and through
  a LIVE independent GEE reducer, reflectance percentiles, QA bit
  fractions, LZW ratios;
* Sentinel-2: s2_scl_qa_v1_1 semantics plus a LIVE independent SCL
  frequency histogram (valid exactly {4,5,6}; water valid;
  2/7/11 invalid), same-datatake grouping, contributing granule ids;
* Sentinel-1: VV/VH identity checked against a LIVE independent server
  recompute (no second 10*log10), pass + relative orbit vs the frozen
  plan, measured footprint coverage, constant/clipped/tail morphology;
* alignment: EO vs W10 cell (centre-in-cell coverage; >=0.95 gate for
  STRICT_FULL products), EO vs each relevant frozen label adapter
  (exact same-resolution transform; positive-pixel coverage), GSHHS
  coastline overlay;
* quicklooks: per-product PNGs with cell edge, coastline and labels.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))
SCRIPTS_NATIONAL = REPO_ROOT / "scripts/data/national"

import geopandas as gpd  # noqa: E402
import matplotlib  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import rasterio  # noqa: E402
from pyproj import CRS, Transformer  # noqa: E402
from shapely.geometry.base import BaseGeometry  # noqa: E402

from spartina.data.gee.auth import initialize  # noqa: E402
from spartina.data.gee.grid import covering_grid  # noqa: E402
from spartina.data.gee.landsat import (  # noqa: E402
    QA_CIRRUS,
    QA_CLEAR,
    QA_CLOUD,
    QA_CLOUD_SHADOW,
    QA_DILATED_CLOUD,
    QA_FILL,
    QA_SNOW,
    sr_bands,
)
from spartina.data.gee.provenance import git_context, runtime_environment  # noqa: E402
from spartina.data.national.grid import (  # noqa: E402
    CHINA_ALBERS_PROJ4,
    utm_epsg,
)

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

CANARY_CSV = REPO_ROOT / "datasets/manifests/national_pilot19_canary_v1.csv"
MANIFEST_DIR = REPO_ROOT / "work/national/pilot19/manifests"
SUPPORTS_CSV = (
    REPO_ROOT / "datasets/manifests/national_pilot19_label_supports_v1.csv")
GSHHS = (REPO_ROOT / "work/external/gshhg_2_3_7/extracted/GSHHS_shp/h"
         / "GSHHS_h_L1.shp")
QUICKLOOK_DIR = REPO_ROOT / "work/national/pilot19/quicklooks"
OUT_JSON = REPO_ROOT / "datasets/manifests/national_pilot19_canary_qa_v1.json"

DENSIFY = 21
COVERAGE_GATE = 0.95
FOOTPRINT_GATE = 0.50
COVERAGE_WARN = 0.90
POSITIVE_COV_WARN = 0.90
#: Relative tolerances for live reducer vs landed-pixel comparisons.
LIVE_COUNT_REL_TOL = 2e-3
LIVE_DB_EXTREMA_TOL = 1.0
LIVE_DB_PCT_TOL = 0.6
ALBERS = CRS.from_proj4(CHINA_ALBERS_PROJ4)

#: relevant-year label adapters per (sensor, event year). GEODATA years
#: are 1990/2000/2015/2020; CMSA covers 2017-2021; CM-SSM is 2020 only.
#: Years without a contemporary adapter use the nearest frozen source and
#: the comparison is recorded as cross-year (occupancy alignment only,
#: never an accuracy claim).
LABEL_SOURCES: dict[tuple[str, int], list[tuple[str, int]]] = {
    ("landsat5", 1990): [("geodata-1990", 30)],
    ("landsat5", 2000): [("geodata-2000", 30)],
    ("landsat7", 2000): [("geodata-2000", 30)],
    ("landsat8", 2015): [("geodata-2015", 30)],
    ("landsat8", 2020): [("cmsa-2020", 30), ("geodata-2020", 30)],
    ("landsat8", 2021): [("cmsa-2021", 30), ("geodata-2020", 30)],
    ("sentinel1", 2015): [("geodata-2015", 30)],
    ("sentinel1", 2020): [
        ("cmsa-2020", 30), ("geodata-2020", 30), ("cmssm-2020", 10)],
    ("sentinel1", 2021): [
        ("cmsa-2021", 30), ("geodata-2020", 30), ("cmssm-2020", 10)],
    ("sentinel2", 2015): [("geodata-2015", 30)],
    ("sentinel2", 2020): [
        ("cmsa-2020", 30), ("geodata-2020", 30),
        ("cmssm-2020", 10), ("cmssm-2020", 30)],
    ("sentinel2", 2021): [
        ("cmsa-2021", 30), ("geodata-2020", 30),
        ("cmssm-2020", 10), ("cmssm-2020", 30)],
}

RGB_BANDS: dict[str, tuple[str, str, str]] = {
    "landsat5": ("SR_B3", "SR_B2", "SR_B1"),
    "landsat7": ("SR_B3", "SR_B2", "SR_B1"),
    "landsat8": ("SR_B4", "SR_B3", "SR_B2"),
    "sentinel2": ("B4", "B3", "B2"),
}

PASS, WARN, FAIL, SKIPPED = "PASS", "WARN", "FAIL", "SKIPPED"
_RANK = {PASS: 0, WARN: 1, SKIPPED: 1, FAIL: 2}


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class Dimension:
    name: str
    verdict: str
    detail: dict[str, Any] = field(default_factory=dict)
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "verdict": self.verdict,
                "detail": self.detail, "note": self.note}


def worst(verdicts: list[str]) -> str:
    return max(verdicts, key=lambda v: _RANK[v])


# ---------------------------------------------------------------------------
# module loading and frozen inputs
# ---------------------------------------------------------------------------

def _load_module(name: str, rel: str) -> Any:
    path = REPO_ROOT / rel
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_DRIVER = _load_module("pilot19_export_driver",
                       "scripts/data/national/pilot19_export_products.py")
_SUPPORTS_BUILDER = _load_module(
    "pilot19_label_support_builder",
    "scripts/data/national/build_pilot_label_supports_v1.py")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _paths(mf: dict[str, Any]) -> dict[str, Path]:
    return {f["role"]: Path(f["local_uri"]) for f in mf["landed_files"]}


def _header(path: Path) -> dict[str, Any]:
    with rasterio.open(path) as ds:
        return {
            "crs_epsg": int(ds.crs.to_epsg()),
            "transform": [float(v) for v in list(ds.transform)[:6]],
            "width": ds.width, "height": ds.height,
            "count": ds.count, "dtypes": list(ds.dtypes),
            "descriptions": list(ds.descriptions),
            "compress": ds.profile.get("compress"), "nodata": ds.nodata}


# ---------------------------------------------------------------------------
# independent geometry
# ---------------------------------------------------------------------------

def expected_grid(cell_id: str, zone: int, pixel_m: float) -> dict[str, Any]:
    """Rebuild the EO grid straight from the frozen W10 cell definition.

    Same densified-edge rule as the Phase F/G support builder; this never
    reads the export driver, the manifest, or any landed file.
    """
    epsg, bounds = _SUPPORTS_BUILDER.cell_utm_bounds(cell_id, zone)
    grid = covering_grid(bounds, epsg, pixel_m)
    return {"crs_epsg": grid.crs_epsg,
            "transform": [float(v) for v in grid.transform],
            "width": grid.width, "height": grid.height,
            "bounds": [float(v) for v in bounds]}


def cell_polygon(cell_id: str, zone: int) -> BaseGeometry:
    return _SUPPORTS_BUILDER.cell_polygon_utm(cell_id, zone)


def centre_in_cell(cell_id: str, zone: int, hdr: dict[str, Any],
                   pixel_m: float) -> np.ndarray[Any, Any]:
    """Boolean (height, width) mask of pixel centres inside the W10 cell."""
    from affine import Affine

    poly = cell_polygon(cell_id, zone)
    tf = Affine(*hdr["transform"])
    cols, rows = np.meshgrid(np.arange(hdr["width"]),
                             np.arange(hdr["height"]))
    xs = tf.c + (cols.ravel() + 0.5) * pixel_m
    ys = tf.f - (rows.ravel() + 0.5) * pixel_m
    import shapely

    inside = shapely.contains(poly, shapely.points(xs, ys))
    return np.asarray(inside, dtype=bool).reshape(hdr["height"],
                                                  hdr["width"])


def zone_from_center_lon(lon: float) -> int:
    return int(math.floor((float(lon) + 180.0) / 6.0) + 1)


# ---------------------------------------------------------------------------
# dimensions: manifest + grids (every sensor)
# ---------------------------------------------------------------------------

def dim_manifest_integrity(mf: dict[str, Any]) -> Dimension:
    problems: list[str] = []
    files: list[dict[str, Any]] = []
    for f in mf["landed_files"]:
        p = Path(f["local_uri"])
        rec: dict[str, Any] = {"role": f["role"], "path": str(p)}
        if not p.exists():
            problems.append(f"{f['role']}: missing")
            rec["exists"] = False
        else:
            rec["exists"] = True
            rec["size_bytes_manifest"] = int(f["size_bytes"])
            rec["size_bytes_actual"] = p.stat().st_size
            if p.stat().st_size != int(f["size_bytes"]):
                problems.append(
                    f"{f['role']}: size {p.stat().st_size} != "
                    f"{f['size_bytes']}")
            digest = _sha256(p)
            rec["sha256_manifest"] = f["sha256"]
            rec["sha256_recomputed"] = digest
            if digest != f["sha256"]:
                problems.append(f"{f['role']}: sha256 mismatch")
            if not f.get("grid_verified"):
                problems.append(f"{f['role']}: grid_verified not set")
        files.append(rec)
    tasks = mf.get("export_tasks", [])
    task_states = {t["role"]: t.get("state") for t in tasks}
    for f in mf["landed_files"]:
        if task_states.get(f["role"]) != "COMPLETED":
            problems.append(
                f"{f['role']}: task state {task_states.get(f['role'])}")
    verdict = FAIL if problems else PASS
    return Dimension("manifest_integrity", verdict,
                     {"files": files, "task_states": task_states,
                      "n_bytes_manifest": int(mf.get("n_bytes", 0))},
                     "; ".join(problems))


def dim_component_grids(mf: dict[str, Any]) -> Dimension:
    paths = _paths(mf)
    headers = {role: _header(p) for role, p in paths.items()}
    ref = next(iter(headers.values()))
    problems: list[str] = []
    for role, h in headers.items():
        for key in ("crs_epsg", "transform", "width", "height"):
            if h[key] != ref[key]:
                problems.append(f"{role}:{key} differs across components")
    g = dict(mf["grid_spec"])
    want_tf = [float(v) for v in g["transform"]]
    if ref["transform"] != want_tf or ref["width"] != int(g["width"]) \
            or ref["height"] != int(g["height"]) \
            or ref["crs_epsg"] != int(str(g["crs"]).replace("EPSG:", "")):
        problems.append("component headers disagree with manifest grid_spec")
    verdict = FAIL if problems else PASS
    return Dimension("component_grid_consistency", verdict,
                     {"headers": headers}, "; ".join(problems))


def dim_independent_grid(mf: dict[str, Any], panel_row: pd.Series,
                         pixel_m: float) -> Dimension:
    cell_id = str(mf["cell_id"])
    zone_manifest = int(mf["utm_zone"])
    zone_panel = zone_from_center_lon(float(panel_row["center_lon"]))
    exp = expected_grid(cell_id, zone_manifest, pixel_m)
    paths = _paths(mf)
    hdr = _header(next(iter(paths.values())))
    problems: list[str] = []
    if zone_manifest != zone_panel:
        problems.append(
            f"utm zone manifest {zone_manifest} != center_lon {zone_panel}")
    if utm_epsg(zone_manifest) != hdr["crs_epsg"]:
        problems.append("raster EPSG != cell UTM zone EPSG")
    for key in ("transform", "width", "height"):
        if hdr[key] != exp[key]:
            problems.append(f"raster {key} {hdr[key]} != rebuilt {exp[key]}")
    verdict = FAIL if problems else PASS
    return Dimension("independent_grid_rebuild", verdict,
                     {"manifest_zone": zone_manifest,
                      "panel_center_lon": float(panel_row["center_lon"]),
                      "rebuilt": exp, "header": {k: hdr[k] for k in
                      ("crs_epsg", "transform", "width", "height")}},
                     "; ".join(problems))


def observed_masks(path: Path, count: int) -> np.ndarray[Any, Any]:
    """(count, height, width) finite-observed mask."""
    with rasterio.open(path) as ds:
        dsmask = ds.dataset_mask() > 0
        out = np.zeros((count, ds.height, ds.width), dtype=bool)
        for i in range(1, count + 1):
            arr = ds.read(i)
            out[i - 1] = dsmask & np.isfinite(arr)
    return out


def dim_cell_coverage(mf: dict[str, Any], pixel_m: float) -> Dimension:
    """Observed and QA-valid coverage of pixel centres inside the W10 cell."""
    paths = _paths(mf)
    sensor = str(mf["sensor"])
    role = "sr" if sensor in ("sentinel2",) or sensor.startswith("landsat") \
        else "vvvh"
    sr_hdr = _header(paths[role])
    n_bands = sr_hdr["count"]
    observed = observed_masks(paths[role], n_bands).all(axis=0)
    inside = centre_in_cell(str(mf["cell_id"]), int(mf["utm_zone"]),
                            sr_hdr, pixel_m)
    n_cell = int(inside.sum())
    obs_in = int((observed & inside).sum())
    detail: dict[str, Any] = {
        "n_cell_centre_pixels": n_cell,
        "observed_in_cell": obs_in,
        "observed_coverage": obs_in / n_cell,
        "coverage_tier": str(mf.get("coverage_tier"))}
    valid_in: int | None = None
    if "valid" in paths:
        with rasterio.open(paths["valid"]) as ds:
            valid = ds.read(1) == 1
        valid_in = int((valid & inside).sum())
        detail["valid_in_cell"] = valid_in
        detail["valid_coverage"] = valid_in / n_cell
    strict_full = detail["coverage_tier"] == "STRICT_FULL"
    gate = COVERAGE_GATE if strict_full else FOOTPRINT_GATE
    detail["gate"] = gate
    cov = obs_in / n_cell
    notes: list[str] = []
    verdict = PASS
    if cov < gate:
        verdict = FAIL
        notes.append(f"observed cell coverage {cov:.4f} below gate {gate}")
    elif strict_full and cov < COVERAGE_WARN:
        verdict = WARN
        notes.append(
            f"observed cell coverage {cov:.4f} below WARN {COVERAGE_WARN}")
    else:
        notes.append(f"observed cell coverage {cov:.4f} (gate {gate})")
    # QA-valid (clear-surface) coverage is a source-scene quality signal,
    # not a geometric export failure: surfaced as WARN only.
    if valid_in is not None:
        vcov = valid_in / n_cell
        detail["valid_coverage_warn_below"] = COVERAGE_WARN
        if vcov < COVERAGE_WARN:
            verdict = WARN if verdict != FAIL else FAIL
            notes.append(
                f"QA-valid clear-surface coverage only {vcov:.4f}: source "
                "scene cloud/QA quality, export semantics unaffected")
    return Dimension("cell_geometry_coverage", verdict, detail,
                     "; ".join(notes))


# ---------------------------------------------------------------------------
# label adapter alignment + coastline
# ---------------------------------------------------------------------------

def _adapter_path(supports: pd.DataFrame, cell_id: str,
                  source: str, support_m: int) -> Path | None:
    rows = supports[(supports.cell_id == cell_id)
                    & (supports.source == source)
                    & (supports.support_m == support_m)]
    if rows.empty:
        return None
    return REPO_ROOT / str(rows.iloc[0]["fraction_tif"])


def dim_label_alignment(mf: dict[str, Any],
                        supports: pd.DataFrame,
                        eo_valid: np.ndarray[Any, Any] | None,
                        eo_observed: np.ndarray[Any, Any]) -> Dimension:
    cell_id = str(mf["cell_id"])
    sensor = str(mf["sensor"])
    year = int(mf["year"])
    eo_paths = _paths(mf)
    eo_role = ("sr" if sensor.startswith("landsat") or sensor == "sentinel2"
               else "vvvh")
    eo_hdr = _header(eo_paths[eo_role])
    eo_pixel = 30 if sensor.startswith("landsat") else 10
    sources = LABEL_SOURCES[(sensor, year)]
    problems: list[str] = []
    records: list[dict[str, Any]] = []
    for source, support_m in sources:
        ap = _adapter_path(supports, cell_id, source, support_m)
        rec: dict[str, Any] = {"source": source, "support_m": support_m}
        if ap is None or not ap.exists():
            rec["status"] = "MISSING"
            problems.append(f"{source}@{support_m}m adapter missing")
            records.append(rec)
            continue
        with rasterio.open(ap) as ds:
            a_tf = [float(v) for v in list(ds.transform)[:6]]
            a_w, a_h = ds.width, ds.height
            a_crs = int(ds.crs.to_epsg())
            lab = ds.read(1)
        uniq = [float(v) for v in np.unique(lab) if np.isfinite(v)][:8]
        rec.update({"crs_epsg": a_crs, "transform": a_tf,
                    "width": a_w, "height": a_h,
                    "dtype": str(lab.dtype),
                    "unique_sample": uniq})
        if a_crs != eo_hdr["crs_epsg"]:
            problems.append(f"{source}: adapter CRS {a_crs} != EO "
                            f"{eo_hdr['crs_epsg']}")
        if support_m == eo_pixel:
            same = (a_tf == eo_hdr["transform"] and a_w == eo_hdr["width"]
                    and a_h == eo_hdr["height"])
            rec["exact_same_resolution_transform"] = bool(same)
            if not same:
                problems.append(
                    f"{source}@{support_m}m transform/shape differs from EO")
            # pixel-centre residual is exactly zero on identical lattices.
            dx = abs(a_tf[2] - eo_hdr["transform"][2])
            dy = abs(a_tf[5] - eo_hdr["transform"][5])
            rec["pixel_center_residual_m"] = [dx, dy]
        else:
            # Cross-resolution nested-lattice check: both windows come
            # from covering_grid on the same densified cell bounds. The
            # coarser-grid origin is itself on the fine lattice, and window
            # boundaries can differ by at most (coarse - fine) metres
            # (derived: offsets in {0, fine, ..., coarse-fine}).
            ew, ee_, en, es = _bounds(eo_hdr)
            aw, ae, an, as_ = (a_tf[2], a_tf[2] + a_w * support_m,
                               a_tf[5], a_tf[5] - a_h * support_m)
            fine_m = min(eo_pixel, float(support_m))
            coarse_m = max(eo_pixel, float(support_m))
            origin_dx = a_tf[2] - ew
            origin_dy = a_tf[5] - en
            origin_aligned = (abs(origin_dx % fine_m) < 1e-9
                              and abs(origin_dy % fine_m) < 1e-9)
            delta = max(abs(ew - aw), abs(ee_ - ae), abs(en - an),
                        abs(es - as_))
            tol = coarse_m - fine_m + 0.5
            rec["cross_resolution_bounds_delta_m"] = delta
            rec["cross_resolution_tolerance_m"] = tol
            rec["origin_offset_m"] = [origin_dx, origin_dy]
            rec["origin_on_fine_lattice"] = bool(origin_aligned)
            if not origin_aligned:
                problems.append(
                    f"{source}@{support_m}m origin {origin_dx}/{origin_dy}"
                    " not on the fine lattice")
            if delta > tol:
                problems.append(
                    f"{source}@{support_m}m window bounds delta {delta:.2f}"
                    f" > nested tol {tol:.1f} m")
        # Positive-pixel coverage by the EO valid / observed mask.
        positive = lab > 0
        n_pos = int(positive.sum())
        rec["positive_pixels"] = n_pos
        if n_pos > 0 and lab.shape == eo_observed.shape:
            cover_src = (eo_valid if eo_valid is not None
                         else eo_observed)
            rec["positive_valid_fraction"] = float(
                (cover_src & positive).sum() / n_pos)
        elif n_pos > 0:
            frac = _warp_coverage(eo_valid
                                  if eo_valid is not None else eo_observed,
                                  eo_hdr, a_tf, a_w, a_h)
            rec["positive_observed_fraction_resampled"] = float(
                np.where(positive, frac, 0.0).sum() / n_pos)
        records.append(rec)
    low_pos = [r for r in records
               if r.get("positive_pixels")
               and r.get("positive_valid_fraction", 1.0) < POSITIVE_COV_WARN]
    verdict = FAIL if problems else (WARN if low_pos else PASS)
    note = ("; ".join(problems)
            or (f"{len(low_pos)} adapter(s) with <"
                f"{POSITIVE_COV_WARN:.0%} positive pixels QA-valid")
            if low_pos else "all relevant adapters align")
    return Dimension("label_adapter_alignment", verdict,
                     {"adapters": records}, note)


def _warp_coverage(mask: np.ndarray[Any, Any], src_hdr: dict[str, Any],
                  dst_transform: list[float], dst_w: int,
                  dst_h: int) -> np.ndarray[Any, Any]:
    """Mean resample a fine-resolution boolean mask onto a coarse grid."""
    from affine import Affine
    from rasterio.warp import Resampling, reproject

    dst = np.zeros((dst_h, dst_w), dtype="float32")
    reproject(
        source=mask.astype("float32"),
        destination=dst,
        src_transform=Affine(*src_hdr["transform"]),
        src_crs=f"EPSG:{src_hdr['crs_epsg']}",
        dst_transform=Affine(*dst_transform),
        dst_crs=f"EPSG:{src_hdr['crs_epsg']}",
        resampling=Resampling.average,
    )
    return dst


def _bounds(hdr: dict[str, Any]) -> tuple[float, float, float, float]:
    tf = hdr["transform"]
    px = abs(tf[0])
    west = tf[2]
    north = tf[5]
    east = west + hdr["width"] * px
    south = north - hdr["height"] * abs(tf[4])
    return west, east, north, south


def dim_coastline(mf: dict[str, Any], panel_row: pd.Series) -> Dimension:
    cell_id = str(mf["cell_id"])
    zone = int(mf["utm_zone"])
    paths = _paths(mf)
    hdr = _header(next(iter(paths.values())))
    west, east, north, south = _bounds(hdr)
    to_wgs = Transformer.from_crs(hdr["crs_epsg"], 4326, always_xy=True)
    lon_lats = list(to_wgs.transform([west, east, east, west],
                                     [south, south, north, north]))
    minx, maxx = min(lon_lats[0]), max(lon_lats[0])
    miny, maxy = min(lon_lats[1]), max(lon_lats[1])
    detail: dict[str, Any] = {"gshhs": str(GSHHS)}
    if not GSHHS.exists():
        return Dimension("coastline_overlay", WARN, detail,
                         "GSHHS coastline shapefile not available")
    try:
        coast = gpd.read_file(GSHHS, bbox=(minx - 0.05, miny - 0.05,
                                            maxx + 0.05, maxy + 0.05))
        poly = cell_polygon(cell_id, zone)
        if coast.empty:
            return Dimension("coastline_overlay", WARN, detail,
                             "no GSHHS land polygon intersects cell bbox")
        coast_u = coast.to_crs(epsg=hdr["crs_epsg"])
        land = coast_u.geometry.union_all().intersection(poly)
        land_frac = float(land.area / poly.area)
        edge_len = 0.0
        for geom in getattr(coast_u.geometry, "geoms", coast_u.geometry):
            edge_len += float(geom.boundary.intersection(
                poly.buffer(500)).length)
        detail.update({"n_polygons_intersecting": int(len(coast)),
                       "land_area_fraction_of_cell": land_frac,
                       "coastline_length_m_in_buffer": edge_len})
        if not (0.0 < land_frac < 1.0):
            return Dimension("coastline_overlay", WARN, detail,
                             f"cell land fraction {land_frac:.3f}; "
                             "verify coastal membership")
        return Dimension("coastline_overlay", PASS, detail,
                         f"coastline present; land fraction "
                         f"{land_frac:.3f}")
    except Exception as exc:  # noqa: BLE001 -- external layer; record reason
        return Dimension("coastline_overlay", WARN, detail,
                         f"coastline analysis failed: {exc}")


def compression_records(mf: dict[str, Any]) -> list[dict[str, Any]]:
    """Measured LZW compression ratio per landed component."""
    out: list[dict[str, Any]] = []
    for f in mf["landed_files"]:
        p = Path(f["local_uri"])
        hdr = _header(p)
        bytes_per = 4.0 if hdr["dtypes"][0] == "float32" else (
            2.0 if hdr["dtypes"][0] == "uint16" else 1.0)
        uncompressed = int(hdr["width"] * hdr["height"] * hdr["count"]
                           * bytes_per)
        actual = p.stat().st_size
        out.append({"role": f["role"], "dtype": hdr["dtypes"][0],
                    "bands": hdr["count"], "uncompressed_bytes": uncompressed,
                    "actual_bytes": actual,
                    "lzw_ratio_uncompressed_over_actual": (
                        uncompressed / actual if actual else None)})
    return out


# ---------------------------------------------------------------------------
# sensor-specific QA
# ---------------------------------------------------------------------------

def _ee_rect(ee: Any, mf: dict[str, Any]) -> Any:
    paths = _paths(mf)
    hdr = _header(next(iter(paths.values())))
    west, east, north, south = _bounds(hdr)
    return (ee.Geometry.Rectangle([west, south, east, north],
                                  f"EPSG:{hdr['crs_epsg']}", False),
            hdr["crs_epsg"], abs(hdr["transform"][0]))


def qa_landsat(ee: Any | None, mf: dict[str, Any]) -> list[Dimension]:
    sensor = str(mf["sensor"])
    paths = _paths(mf)
    dims: list[Dimension] = []
    n_bands = len(sr_bands(sensor))
    names = list(sr_bands(sensor))
    sr_hdr = _header(paths["sr"])
    problems: list[str] = []
    if sr_hdr["count"] != n_bands:
        problems.append(f"SR bands {sr_hdr['count']} != {n_bands}")
    if sr_hdr["dtypes"] != ["float32"] * n_bands:
        problems.append(f"SR dtypes {sr_hdr['dtypes']}")
    if sr_hdr["descriptions"] != names:
        problems.append(f"band order {sr_hdr['descriptions']} != {names}")
    qa_hdr = _header(paths["qapixel"])
    vd_hdr = _header(paths["valid"])
    if qa_hdr["dtypes"] != ["uint16"]:
        problems.append("QA_PIXEL not uint16")
    if vd_hdr["dtypes"] != ["uint8"]:
        problems.append("VALID not uint8")
    dims.append(Dimension(
        "landsat_band_accounting", FAIL if problems else PASS,
        {"sensor": sensor, "n_sr_bands_expected": n_bands,
         "sr_header": {k: sr_hdr[k] for k in
                       ("count", "dtypes", "descriptions")},
         "qapixel_dtype": qa_hdr["dtypes"], "valid_dtype": vd_hdr["dtypes"]},
        "; ".join(problems)))

    with rasterio.open(paths["sr"]) as ds:
        sr = ds.read().astype("float64")
        dsmask = ds.dataset_mask() > 0
    with rasterio.open(paths["valid"]) as ds:
        valid = ds.read(1) == 1
    with rasterio.open(paths["qapixel"]) as ds:
        qpx = ds.read(1)
    observed = np.broadcast_to(dsmask, sr.shape)
    finite = observed & np.isfinite(sr)

    # DN=0 fill masked BEFORE scaling: no finite pixel may be exactly -0.2.
    neg02 = int((finite & np.isclose(sr, -0.2, atol=0.0)).sum())
    cap = float(_DRIVER.SR_SATURATION_CAP)
    at_cap = int((finite & np.isclose(sr, cap, atol=1e-6)).sum())
    at_cap_valid = int((valid & np.isclose(sr, cap, atol=1e-6)).sum())
    pct: dict[str, list[float]] = {}
    for i, name in enumerate(names):
        vals = sr[i][valid & np.isfinite(sr[i])]
        pct[name] = [float(v) for v in
                     np.percentile(vals, [0, 1, 50, 99, 100])]
    sem_problems = []
    if neg02:
        sem_problems.append(f"{neg02} finite pixels at exact -0.2 (DN=0 leak)")
    bad_range = [n for n, q in pct.items() if q[1] < -0.30 or q[3] > 1.30]
    if bad_range:
        sem_problems.append(f"VALID p01/p99 outside [-0.30,1.30]: {bad_range}")
    if at_cap_valid > max(1, int(0.001 * valid.sum())):
        sem_problems.append(
            f"{at_cap_valid} saturated pixels inside VALID")
    dims.append(Dimension(
        "landsat_scaling_semantics", FAIL if sem_problems else PASS,
        {"formula": "SR = DN * 2.75e-5 - 0.2; fill DN=0 masked pre-scale",
         "exact_minus_0p2_finite_pixels": neg02,
         "saturation_cap": cap, "at_cap_finite_pixels": at_cap,
         "at_cap_valid_pixels": at_cap_valid,
         "valid_percentiles": pct},
        "; ".join(sem_problems)))

    # Independent VALID reconstruction from the raw QA_PIXEL bytes.
    clear = (qpx & (1 << QA_CLEAR)) != 0
    blocked = np.zeros_like(qpx, dtype=bool)
    for bit in (QA_FILL, QA_DILATED_CLOUD, QA_CIRRUS, QA_CLOUD,
                QA_CLOUD_SHADOW, QA_SNOW):
        blocked |= (qpx & (1 << bit)) != 0
    qpx_valid = clear & ~blocked
    # r2: VALID must additionally sit on pixels where every landed SR band
    # is finite/observed (interior per-band nodata under clear QA motivated
    # the r2 revision during pilot D1).
    observed_all = finite.all(axis=0)
    violations = int((valid & ~qpx_valid).sum())
    r2_violations = int((valid & ~observed_all).sum())
    radsat_only_excluded = int((qpx_valid & observed_all & ~valid).sum())
    bit_fractions = {
        name: float(((qpx & (1 << bit)) != 0).mean())
        for name, bit in (("fill", QA_FILL), ("dilated", QA_DILATED_CLOUD),
                          ("cirrus", QA_CIRRUS), ("cloud", QA_CLOUD),
                          ("shadow", QA_CLOUD_SHADOW), ("snow", QA_SNOW),
                          ("clear", QA_CLEAR))}
    live: dict[str, Any] = {"attempted": ee is not None}
    recon_problems = []
    if violations:
        recon_problems.append(
            f"{violations} VALID pixels contradict QA_PIXEL bit rule")
    if r2_violations:
        recon_problems.append(
            f"{r2_violations} r2 VALID pixels lack finite observations in "
            "one or more SR bands")
    if ee is not None:
        try:
            live_count = _live_landsat_valid_count(ee, mf)
            n_landed = int(valid.sum())
            rel = abs(live_count - n_landed) / max(n_landed, 1)
            live.update({"live_valid_pixels": live_count,
                         "landed_valid_pixels": n_landed,
                         "relative_difference": rel,
                         "tolerance": LIVE_COUNT_REL_TOL})
            if rel > LIVE_COUNT_REL_TOL:
                recon_problems.append(
                    f"live valid pixel count rel diff {rel:.2e}")
        except Exception as exc:  # noqa: BLE001
            live["error"] = str(exc)
            recon_problems.append(f"live cross-check failed: {exc}")
    dims.append(Dimension(
        "landsat_valid_reconstruction",
        FAIL if recon_problems else (SKIPPED if ee is None else PASS),
        {"rule": ("r2: bit6 CLEAR set; bits 0-5 all clear; QA_RADSAT == 0; "
                  "all SR bands observed (min mask == 1). RADSAT leg and "
                  "all-observed leg verified by live reducer"),
         "qa_pixel_valid_pixels": int(qpx_valid.sum()),
         "qa_clear_and_observed_pixels": int((qpx_valid & observed_all).sum()),
         "landed_valid_pixels": int(valid.sum()),
         "landed_minus_qapixel_rule_pixels": int(
             valid.sum() - (valid & qpx_valid).sum()),
         "contradictions": violations,
         "r2_nan_under_valid_pixels": r2_violations,
         "radsat_or_unobserved_excluded_pixels": radsat_only_excluded,
         "bit_fractions": bit_fractions, "live": live},
        "; ".join(recon_problems)))

    comp = compression_records(mf)
    dims.append(Dimension("measured_lzw_compression", PASS,
                          {"components": comp}, ""))
    return dims


def _live_landsat_valid_count(ee: Any, mf: dict[str, Any]) -> int:
    """Live independent r2 valid-pixel count for the exact scene/region."""
    rect, epsg, scale = _ee_rect(ee, mf)
    scene_id = str(mf["source_scene_ids"][0])
    img = (ee.ImageCollection(_DRIVER.collection_for(str(mf["sensor"])))
           .filter(ee.Filter.eq("system:index", scene_id)).first())
    qpxb = img.select("QA_PIXEL")
    radsat = img.select("QA_RADSAT")
    valid = qpxb.bitwiseAnd(1 << QA_CLEAR).neq(0)
    for bit in (QA_FILL, QA_DILATED_CLOUD, QA_CIRRUS, QA_CLOUD,
                QA_CLOUD_SHADOW, QA_SNOW):
        valid = valid.And(qpxb.bitwiseAnd(1 << bit).eq(0))
    valid = valid.And(radsat.eq(0))
    # r2 all-SR-bands-observed leg; fill mask applied before scaling as in
    # the export driver, so per-band nodata cannot hide under clear QA.
    sr = img.select(list(sr_bands(str(mf["sensor"])))).updateMask(
        qpxb.bitwiseAnd(1 << QA_FILL).eq(0))
    valid = valid.And(sr.mask().reduce(ee.Reducer.min()).eq(1))
    raw = valid.reduceRegion(
        reducer=ee.Reducer.sum(), geometry=rect, crs=f"EPSG:{epsg}",
        scale=scale, bestEffort=False, tileScale=4).getInfo()
    return int(round(float(next(iter(raw.values())))))


def qa_s2(ee: Any | None, mf: dict[str, Any]) -> list[Dimension]:
    paths = _paths(mf)
    dims: list[Dimension] = []
    sr_hdr = _header(paths["sr"])
    vd_hdr = _header(paths["valid"])
    problems: list[str] = []
    if sr_hdr["count"] != 4 or sr_hdr["dtypes"] != ["float32"] * 4:
        problems.append("SR must be 4x float32")
    if sr_hdr["descriptions"] != ["B2", "B3", "B4", "B8"]:
        problems.append(f"band order {sr_hdr['descriptions']}")
    if vd_hdr["dtypes"] != ["uint8"]:
        problems.append("VALID not uint8")
    with rasterio.open(paths["sr"]) as ds:
        sr = ds.read().astype("float64")
        dsmask = ds.dataset_mask() > 0
    with rasterio.open(paths["valid"]) as ds:
        valid = ds.read(1)
    uvals = {int(v) for v in np.unique(valid)}
    if not uvals <= {0, 1}:
        problems.append(f"VALID values {sorted(uvals)} not in {{0,1}}")
    finite = dsmask & np.isfinite(sr).all(axis=0)
    dn_like = int((np.abs(sr) > 100.0).any(axis=0)[finite].sum())
    negatives = int((sr < 0.0).any(axis=0)[finite].sum())
    stats: dict[str, dict[str, float]] = {}
    for i, name in enumerate(sr_hdr["descriptions"]):
        vals = sr[i][valid == 1]
        vals = vals[np.isfinite(vals)]
        stats[str(name)] = {
            "p01": float(np.percentile(vals, 1)),
            "p50": float(np.percentile(vals, 50)),
            "p99": float(np.percentile(vals, 99)),
            "max": float(vals.max())}
    if dn_like:
        problems.append(f"{dn_like} pixels look like unscaled DN")
    if negatives:
        problems.append(f"{negatives} negative reflectance pixels")
    dims.append(Dimension(
        "s2_bands_scaling", FAIL if problems else PASS,
        {"header": {k: sr_hdr[k] for k in ("count", "dtypes",
                                           "descriptions")},
         "valid_unique": sorted(uvals), "scale": 10000.0,
         "dn_like_pixels": dn_like, "negative_pixels": negatives,
         "valid_percentiles": stats}, "; ".join(problems)))

    cfg = mf["processing_config"]
    policy = cfg["scl_qa_policy"]
    policy_problems: list[str] = []
    valid_classes = {int(k) for k, v in policy["valid_classes"].items()}
    not_valid = {int(k) for k, v in policy["not_valid_classes"].items()}
    if policy.get("version") != "s2_scl_qa_v1_1":
        policy_problems.append("policy version != s2_scl_qa_v1_1")
    if valid_classes != {4, 5, 6}:
        policy_problems.append(f"valid classes {sorted(valid_classes)}")
    if 6 not in valid_classes:
        policy_problems.append("water class 6 not valid")
    for cls in (2, 7, 11):
        if cls not in not_valid:
            policy_problems.append(f"class {cls} not marked invalid")
    datatakes = set(str(cfg["datatake_identifier"]).split(";"))
    if len(datatakes) != 1:
        policy_problems.append(f"datatakes {datatakes}")
    live: dict[str, Any] = {"attempted": ee is not None}
    if ee is not None:
        try:
            live_res = _live_s2_scl(ee, mf)
            live.update(live_res)
            n_landed = int((valid == 1).sum())
            rel = abs(live_res["live_valid_pixels"] - n_landed) / max(
                n_landed, 1)
            live["landed_valid_pixels"] = n_landed
            live["relative_difference"] = rel
            live["tolerance"] = LIVE_COUNT_REL_TOL
            water = int(live_res["scl_class_counts"].get("6", 0))
            live["water_class_6_included_in_live_valid"] = water > 0
            if rel > LIVE_COUNT_REL_TOL:
                policy_problems.append(
                    f"live SCL valid count rel diff {rel:.2e}")
        except Exception as exc:  # noqa: BLE001
            live["error"] = str(exc)
            policy_problems.append(f"live SCL cross-check failed: {exc}")
    verdict = FAIL if policy_problems else (SKIPPED if ee is None else PASS)
    dims.append(Dimension(
        "s2_scl_policy_live", verdict,
        {"policy_version": policy.get("version"),
         "valid_classes": sorted(valid_classes),
         "not_valid_classes": sorted(not_valid),
         "datatake_identifier": cfg["datatake_identifier"],
         "contributing_source_product_ids":
             cfg["contributing_source_product_ids"],
         "spacecraft": mf.get("spacecraft"), "live": live},
        "; ".join(policy_problems)))

    comp = compression_records(mf)
    dims.append(Dimension("measured_lzw_compression", PASS,
                          {"components": comp}, ""))
    return dims


def _live_s2_scl(ee: Any, mf: dict[str, Any]) -> dict[str, Any]:
    rect, epsg, scale = _ee_rect(ee, mf)
    scene_ids = [str(s) for s in mf["source_scene_ids"]]
    col = (ee.ImageCollection(_DRIVER.collection_for("sentinel2"))
           .filter(ee.Filter.inList("system:index", scene_ids)))
    n_scenes = int(col.size().getInfo())
    datatakes = col.aggregate_array("DATATAKE_IDENTIFIER").distinct().getInfo()
    products = col.aggregate_array("PRODUCT_ID").getInfo()
    img = col.first()
    hist = img.select("SCL").reduceRegion(
        reducer=ee.Reducer.frequencyHistogram(), geometry=rect,
        crs=f"EPSG:{epsg}", scale=scale, bestEffort=False,
        tileScale=4).getInfo()
    raw_counts = hist.get("SCL", {})
    counts = {str(int(float(k))): int(v) for k, v in raw_counts.items()}
    valid_n = sum(counts.get(str(c), 0) for c in (4, 5, 6))
    return {"n_scenes_for_ids": n_scenes,
            "live_datatakes": list(datatakes),
            "live_contributing_products": list(products),
            "scl_class_counts": counts,
            "live_valid_pixels": valid_n,
            "live_valid_rule": "classes {4 vegetation, 5 bare, 6 water}"}


def qa_s1(ee: Any | None, mf: dict[str, Any],
          plan_row: pd.Series) -> list[Dimension]:
    paths = _paths(mf)
    dims: list[Dimension] = []
    hdr = _header(paths["vvvh"])
    problems: list[str] = []
    if hdr["count"] != 2 or hdr["dtypes"] != ["float32", "float32"]:
        problems.append("must be 2x float32")
    if hdr["descriptions"] != ["VV", "VH"]:
        problems.append(f"band order {hdr['descriptions']}")
    with rasterio.open(paths["vvvh"]) as ds:
        vv = ds.read(1).astype("float64")
        vh = ds.read(2).astype("float64")
        dsmask = ds.dataset_mask() > 0
    fv, fh = dsmask & np.isfinite(vv), dsmask & np.isfinite(vh)
    stats = {
        "VV": {k: float(v) for k, v in zip(
            ("min", "p01", "p50", "p99", "max"),
            np.percentile(vv[fv], [0, 1, 50, 99, 100]), strict=True)},
        "VH": {k: float(v) for k, v in zip(
            ("min", "p01", "p50", "p99", "max"),
            np.percentile(vh[fh], [0, 1, 50, 99, 100]), strict=True)}}
    stats["VV"]["std"] = float(vv[fv].std())
    stats["VH"]["std"] = float(vh[fh].std())
    stats["VV"]["finite_fraction"] = float(fv.mean())
    stats["VH"]["finite_fraction"] = float(fh.mean())
    if stats["VV"]["std"] <= 0 or stats["VH"]["std"] <= 0:
        problems.append("constant band")
    hard = ((vv[fv] < _DRIVER.S1_DB_HARD_MIN)
            | (vv[fv] > _DRIVER.S1_DB_HARD_MAX)
            | (vh[fh] < _DRIVER.S1_DB_HARD_MIN)
            | (vh[fh] > _DRIVER.S1_DB_HARD_MAX))
    if int(hard.sum()):
        problems.append("pixels beyond hard dB envelope")
    # stripe / block morphology of point-target tail
    tail = vv > _DRIVER.S1_DB_BULK_MAX
    row_frac = tail.mean(axis=1).max()
    stripe_ratio = float(row_frac / max(float(tail.mean()), 1e-12))
    live: dict[str, Any] = {"attempted": ee is not None}
    if ee is not None:
        try:
            live_stats = _live_s1_stats(ee, mf)
            checks: dict[str, bool] = {}
            deltas: dict[str, float] = {}
            for band in ("VV", "VH"):
                for stat, tol in (("min", LIVE_DB_EXTREMA_TOL),
                                  ("max", LIVE_DB_EXTREMA_TOL),
                                  ("p01", LIVE_DB_PCT_TOL),
                                  ("p50", LIVE_DB_PCT_TOL),
                                  ("p99", LIVE_DB_PCT_TOL)):
                    d = abs(stats[band][stat] - live_stats[band][stat])
                    deltas[f"{band}_{stat}"] = round(d, 4)
                    checks[f"{band}_{stat}"] = d <= tol
            live = {"attempted": True, "server_stats": live_stats,
                    "abs_deltas": deltas, "checks": checks,
                    "pass": all(checks.values())}
            if not live["pass"]:
                problems.append(
                    f"live identity mismatch: "
                    f"{[k for k, ok in checks.items() if not ok]}")
        except Exception as exc:  # noqa: BLE001
            live = {"attempted": True, "error": str(exc)}
            problems.append(f"live S1 cross-check failed: {exc}")
    dims.append(Dimension(
        "s1_identity_and_physics",
        FAIL if problems else (SKIPPED if ee is None else PASS),
        {"bands": stats, "point_target_row_stripe_ratio": stripe_ratio,
         "live": live,
         "transform": "IDENTITY_SELECT_ONLY_NO_10LOG10"},
        "; ".join(problems)))

    pass_problems: list[str] = []
    props = mf["processing_config"].get("properties", {})
    plan_pass = str(plan_row.get("orbit_pass") or "")
    plan_orbit = plan_row.get("relative_orbit")
    gee_pass = props.get("orbitProperties_pass")
    expect = {"ASC": "ASCENDING", "DESC": "DESCENDING"}.get(plan_pass)
    if expect is not None and gee_pass != expect:
        pass_problems.append(f"pass {gee_pass} != plan {plan_pass}")
    if (plan_orbit is not None and not pd.isna(plan_orbit)
            and int(props.get("relativeOrbitNumber_start", -1))
            != int(float(plan_orbit))):
        pass_problems.append("relative orbit mismatch")
    pol = props.get("transmitterReceiverPolarisation")
    if sorted(pol or []) != ["VH", "VV"]:
        pass_problems.append(f"polarisation {pol}")
    dims.append(Dimension(
        "s1_pass_orbit_footprint", FAIL if pass_problems else PASS,
        {"plan_pass": plan_pass, "gee_pass": gee_pass,
         "plan_relative_orbit": (None if pd.isna(plan_orbit)
                                 else int(float(plan_orbit))),
         "gee_relative_orbit": props.get(
             "relativeOrbitNumber_start"),
         "polarisation": pol,
         "source_product_id":
             mf["processing_config"].get("source_product_id"),
         "productIdentifier_property_present":
             mf["processing_config"].get(
                 "productIdentifier_property_present"),
         "VV_finite_fraction": stats["VV"]["finite_fraction"],
         "VH_finite_fraction": stats["VH"]["finite_fraction"],
         "coverage_tier": mf.get("coverage_tier")},
        "; ".join(pass_problems)))

    comp = compression_records(mf)
    dims.append(Dimension("measured_lzw_compression", PASS,
                          {"components": comp}, ""))
    return dims


def _live_s1_stats(ee: Any, mf: dict[str, Any]) -> dict[str, dict[str, float]]:
    rect, epsg, scale = _ee_rect(ee, mf)
    scene_id = str(mf["source_scene_ids"][0])
    img = (ee.ImageCollection(_DRIVER.collection_for("sentinel1"))
           .filter(ee.Filter.eq("system:index", scene_id)).first())
    reducer = (ee.Reducer.minMax()
               .combine(ee.Reducer.percentile([1, 50, 99]),
                        sharedInputs=True))
    raw = img.select(["VV", "VH"]).reduceRegion(
        reducer=reducer, geometry=rect, crs=f"EPSG:{epsg}", scale=scale,
        bestEffort=False, tileScale=4).getInfo()
    out: dict[str, dict[str, float]] = {}
    for band in ("VV", "VH"):
        out[band] = {
            stat: float(raw[f"{band}_{src}"])
            for stat, src in (("min", "min"), ("max", "max"),
                              ("p01", "p1"), ("p50", "p50"),
                              ("p99", "p99"))}
    return out


# ---------------------------------------------------------------------------
# quicklooks
# ---------------------------------------------------------------------------

def _stretch(band: np.ndarray[Any, Any], mask: np.ndarray[Any, Any],
             p_lo: float = 2.0, p_hi: float = 98.0) -> np.ndarray[Any, Any]:
    vals = band[mask]
    if vals.size == 0:
        return np.zeros_like(band, dtype="float32")
    lo, hi = np.percentile(vals, [p_lo, p_hi])
    if hi <= lo:
        hi = lo + 1e-6
    out = np.clip((band - lo) / (hi - lo), 0.0, 1.0)
    out[~mask] = np.nan
    return np.asarray(out.astype("float32"))


def render_quicklook(mf: dict[str, Any], supports: pd.DataFrame) -> Path:
    sensor = str(mf["sensor"])
    paths = _paths(mf)
    cell_id = str(mf["cell_id"])
    zone = int(mf["utm_zone"])
    if sensor.startswith("landsat") or sensor == "sentinel2":
        role = "sr"
        hdr = _header(paths[role])
        with rasterio.open(paths[role]) as ds:
            arr = ds.read().astype("float64")
            dsmask = ds.dataset_mask() > 0
            names = list(ds.descriptions)
        finite = dsmask & np.isfinite(arr).all(axis=0)
        rgb_names = RGB_BANDS[sensor]
        idx = [names.index(n) for n in rgb_names]
        rgb = np.dstack([_stretch(arr[i], finite) for i in idx])
        naxes = 2
    else:
        hdr = _header(paths["vvvh"])
        with rasterio.open(paths["vvvh"]) as ds:
            vv = ds.read(1).astype("float64")
            vh = ds.read(2).astype("float64")
            dsmask = ds.dataset_mask() > 0
        fv, fh = dsmask & np.isfinite(vv), dsmask & np.isfinite(vh)
        vvs, vhs = _stretch(vv, fv), _stretch(vh, fh)
        rgb = np.dstack([vvs, vhs, (vvs + vhs) / 2.0])
        naxes = 2
    west, east, north, south = _bounds(hdr)
    fig, axes = plt.subplots(1, naxes, figsize=(11, 5.5))
    ax_img, ax_meta = axes[0], axes[1]
    ax_img.imshow(rgb, extent=[west, east, south, north],
                  origin="upper", interpolation="nearest")
    ax_meta.imshow(rgb, extent=[west, east, south, north],
                   origin="upper", interpolation="nearest", alpha=0.55)
    poly = cell_polygon(cell_id, zone)
    px, py = poly.exterior.xy
    for ax in axes:
        ax.plot(px, py, color="red", linewidth=1.4,
                label="W10 cell edge")
        ax.set_xlim(west, east)
        ax.set_ylim(south, north)
        ax.set_aspect("equal")
    try:
        to_wgs = Transformer.from_crs(hdr["crs_epsg"], 4326,
                                      always_xy=True)
        blon = list(to_wgs.transform([west, east], [south, north]))
        coast = gpd.read_file(
            GSHHS,
            bbox=(min(blon[0]) - 0.05, min(blon[1]) - 0.05,
                  max(blon[0]) + 0.05, max(blon[1]) + 0.05))
        if not coast.empty:
            coast.to_crs(epsg=hdr["crs_epsg"]).boundary.plot(
                ax=ax_meta, color="deepskyblue", linewidth=1.0)
    except Exception:  # noqa: BLE001 -- overlay is best-effort
        pass
    # Relevant-year positive label overlay.
    year = int(mf["year"])
    sources = LABEL_SOURCES.get((sensor, year), [])
    for source, support_m in sources:
        ap = _adapter_path(supports, cell_id, source, support_m)
        if ap is None or not ap.exists():
            continue
        with rasterio.open(ap) as ds:
            lab = ds.read(1)
            ltf = ds.transform
            lw, lh = ds.width, ds.height
        pos = np.ma.masked_where(lab <= 0, lab)  # type: ignore[no-untyped-call]
        ax_meta.imshow(pos, cmap="Greens", alpha=0.6,
                       extent=[ltf.c, ltf.c + lw * support_m,
                               ltf.f - lh * support_m, ltf.f],
                       interpolation="nearest")
        break
    ax_meta.set_title("cell edge / coastline / label positives")
    title = f"{mf['product_id']} ({sensor}, {year})"
    ax_img.set_title(title)
    ax_img.legend(loc="lower right", fontsize=7)
    fig.tight_layout()
    out = QUICKLOOK_DIR / f"{mf['product_id']}_quicklook.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=130)
    plt.close(fig)
    return out


# ---------------------------------------------------------------------------
# per-product runner
# ---------------------------------------------------------------------------

def run_product(mf: dict[str, Any], plan_row: pd.Series,
                panel_row: pd.Series, supports: pd.DataFrame,
                ee: Any | None) -> tuple[list[Dimension], str]:
    sensor = str(mf["sensor"])
    pixel_m = 30.0 if sensor.startswith("landsat") else 10.0
    dims: list[Dimension] = [
        dim_manifest_integrity(mf),
        dim_component_grids(mf),
        dim_independent_grid(mf, panel_row, pixel_m),
        dim_cell_coverage(mf, pixel_m),
    ]
    paths = _paths(mf)
    sr_role = "sr" if "sr" in paths else "vvvh"
    sr_hdr = _header(paths[sr_role])
    eo_observed = observed_masks(paths[sr_role], sr_hdr["count"]).all(axis=0)
    eo_valid: np.ndarray[Any, Any] | None = None
    if "valid" in paths:
        with rasterio.open(paths["valid"]) as ds:
            eo_valid = ds.read(1) == 1
    dims.append(dim_label_alignment(mf, supports, eo_valid, eo_observed))
    dims.append(dim_coastline(mf, panel_row))
    if sensor.startswith("landsat"):
        dims.extend(qa_landsat(ee, mf))
    elif sensor == "sentinel2":
        dims.extend(qa_s2(ee, mf))
    else:
        dims.extend(qa_s1(ee, mf, plan_row))
    qpath = render_quicklook(mf, supports)
    dims.append(Dimension(
        "quicklook", PASS if qpath.exists() and qpath.stat().st_size > 0
        else FAIL, {"path": str(qpath), "bytes": qpath.stat().st_size}))
    verdicts = [d.verdict for d in dims]
    return dims, worst(verdicts)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-live", action="store_true",
                    help="skip live GEE cross-checks (not recommended)")
    ap.add_argument("--out", type=Path, default=OUT_JSON)
    args = ap.parse_args()
    ee: Any | None = None
    if not args.no_live:
        initialize()
        import ee as _ee  # noqa: PLC0415

        ee = _ee

    canary = pd.read_csv(CANARY_CSV)
    scope = {str(r["product_id"]): r
             for r in _DRIVER.load_scope(canary=True, only_sensor=None)}
    supports = pd.read_csv(SUPPORTS_CSV)
    panel_rows = _DRIVER.load_panel()
    panel = {str(cid): row for cid, row in panel_rows.iterrows()}

    products: list[dict[str, Any]] = []
    verdicts_all: list[str] = []
    for crow in canary.itertuples(index=False):
        pid = str(crow.product_id)
        mf_path = MANIFEST_DIR / f"{pid}.json"
        if not mf_path.exists():
            products.append({"product_id": pid, "fatal": "manifest missing"})
            verdicts_all.append(FAIL)
            continue
        mf = json.loads(mf_path.read_text())
        plan_row = scope[pid]
        panel_row = panel[str(mf["cell_id"])]
        dims, verdict = run_product(mf, plan_row, panel_row, supports, ee)
        verdicts_all.append(verdict)
        products.append({
            "product_id": pid, "cell_id": str(mf["cell_id"]),
            "sensor": str(mf["sensor"]), "year": int(mf["year"]),
            "verdict": verdict,
            "dimensions": [d.to_dict() for d in dims]})
        print(f"[{pid}] {verdict}: "
              + ", ".join(f"{d.name}={d.verdict}" for d in dims))
    gate = worst(verdicts_all) if verdicts_all else FAIL
    decision = "CANARY_PASS" if gate != FAIL else "CANARY_FAIL"
    report = {
        "schema": "spartina_pilot19_canary_qa_v1",
        "issue": "#19",
        "created_utc": _now(),
        "live_gee_cross_checks": not args.no_live,
        "gate_verdict": gate,
        "decision": decision,
        "coverage_gate_strict_full": COVERAGE_GATE,
        "git": git_context(str(REPO_ROOT)),
        "environment": runtime_environment(),
        "products": products}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"{decision}; report -> {args.out}")
    return 0 if gate != FAIL else 2


if __name__ == "__main__":
    raise SystemExit(main())
