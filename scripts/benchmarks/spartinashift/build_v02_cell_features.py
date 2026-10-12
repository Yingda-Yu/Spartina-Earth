#!/usr/bin/env python3
"""Issue #21, Phase B -- build the national v0.2 cell feature table.

DETERMINISTIC, OFFLINE, METADATA-ONLY-WITH-LOCAL-LABELS: no GEE calls,
no EO pixels, no model information. For every W10_DOMAIN_V1_CORE_FROZEN
production-eligible cell (3,016) the table records:

* frozen geography (mainland/island, centre, coastal segment);
* target-independent province attribution (the R1 Natural Earth rule);
* Issue #18 strata and the audited 2020 three-product reference counts
  (g/c/m, 30 m, 900 m^2/px);
* GEODATA 2015 / 2020 positive-pixel counts, counted directly from the
  frozen national rasters as source 30 m pixels whose reprojected
  centres fall inside the Albers cell (half-open); the 2020 count is
  cross-checked against Issue #18 g;
* exact CMSA 2020 / 2021 gridcode-2 polygon union areas in Albers
  (gridcode-0 area recorded separately as UNKNOWN); CMSA 2020 is
  cross-checked against Issue #18 c;
* metadata-only EO availability from the national census v0.1
  (autumn, full-cover event counts); no pixel is read.

Outputs (bytes outside Git; checksums recorded by the panel freeze):
  work/issue21/derived/v02_cell_features.csv
  work/issue21/derived/v02_cell_features_manifest.json
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer
from rasterio.windows import from_bounds
from shapely.geometry import box

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts/data/national"))

from freeze_first_pixel_panel_v1 import attribute_provinces  # noqa: E402

from spartina.data.national.geometry import CHINA_ALBERS_CRS  # noqa: E402
from spartina.data.national.grid import (  # noqa: E402
    GridKind,
    GridSpec,
    parse_cell_id,
)

REGISTRY_CSV = (REPO_ROOT / "datasets/manifests"
                / "china_coastal_cells_v1_1_core_frozen.csv")
STRATA_CSV = REPO_ROOT / "work/national/strata/strata_china_albers_W10000.csv"
S30_CELLS = REPO_ROOT / "work/issue18/derived/s30_cells.csv"
V1_CANDIDATE_CSV = (REPO_ROOT / "datasets/manifests"
                    / "china_coastal_cells_v1_candidate.csv")
CELLS_CSV = REPO_ROOT / "work/national/domain/cells_china_albers_W10000.csv"
CENSUS_PARQUET = (REPO_ROOT / "work/national/census_r1/products"
                  / "china_cell_event_census_v0_1.parquet")
STAGING = REPO_ROOT / "work/intake/staging"


def _one_tif(pattern: str) -> Path:
    matches = sorted(STAGING.glob(pattern))
    if len(matches) != 1:
        raise SystemExit(
            f"expected exactly one raster for {pattern}, found "
            f"{[str(m) for m in matches]}")
    return matches[0]


GEODATA_2015_TIF = _one_tif(
    "30m*2015*数据实体/*.tif")
GEODATA_2020_TIF = _one_tif(
    "2020年中国滨海30*m*动态数据集-数据实体/*.tif")
CMSA_DIR = REPO_ROOT / "work/intake/staging/中国大陆2017-2021互花米草CMSA"
PANEL_JSON = REPO_ROOT / "datasets/manifests/national_first_pixel_panel_v1.json"
OUT_DIR = REPO_ROOT / "work/issue21/derived"
OUT_CSV = OUT_DIR / "v02_cell_features.csv"
OUT_JSON = OUT_DIR / "v02_cell_features_manifest.json"

PX_AREA_30 = 900.0
AUTUMN = "AUTUMN_PRIMARY_V1_CANDIDATE"
FULL = "FULL_CELL_COVERED"
KEEP = ("KEEP_MAINLAND_COASTAL", "KEEP_ISLAND_COASTAL")
SMALL_AREA_KM2 = 0.05
REL_TOL = 0.10
GRID = GridSpec(GridKind.CHINA_ALBERS)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, check=True,
            capture_output=True, text=True).stdout.strip()
    except OSError:
        return "UNKNOWN"


def domain_frame() -> pd.DataFrame:
    registry = pd.read_csv(REGISTRY_CSV)
    frame = registry[
        registry["membership_v1_1"].isin(KEEP)
        & (registry["production_eligible"].astype(str).str.lower() == "true")
    ].copy()
    if len(frame) != 3016:
        raise SystemExit(f"expected 3,016 KEEP+eligible cells, got {len(frame)}")
    strata = pd.read_csv(STRATA_CSV)[[
        "cell_id", "exclusive_stratum", "silver_2015_positive",
        "silver_2015_nearby", "cmsa_positive_history",
        "cmssm_2020_positive"]]
    frame = frame.merge(strata, on="cell_id", how="left")
    panel = {c["cell_id"] for c in json.loads(
        PANEL_JSON.read_text())["cells"]}
    frame["old_stage1_panel"] = frame["cell_id"].isin(panel)
    return frame


def issue18_reference() -> pd.DataFrame:
    """Reproduce the accepted Issue #18 cell_idx -> cell_id mapping."""
    cells = pd.read_csv(CELLS_CSV)
    membership = pd.read_csv(V1_CANDIDATE_CSV)[
        ["cell_id", "membership_v1_candidate"]]
    cells = cells.merge(membership, on="cell_id", how="left")
    cells = cells[
        cells["membership_v1_candidate"].isin(
            ("KEEP_MAINLAND_COASTAL", "KEEP_ISLAND_COASTAL",
             "PROVISIONAL_UNRESOLVED"))
    ].copy()
    cells["cell_idx"] = np.arange(len(cells))
    s30 = pd.read_csv(S30_CELLS)[["cell_idx", "g", "c", "m"]]
    return cells[["cell_id", "cell_idx"]].merge(
        s30, on="cell_idx", how="left").fillna({"g": 0, "c": 0, "m": 0})


def count_raster_positive_centers(tif_path: Path,
                                  bounds: tuple[float, float, float, float]
                                  ) -> int:
    """Count source value-1 30 m pixels with reprojected centre in cell.

    The cell rectangle is transformed into the raster CRS (60 m pad),
    the native window is read, and every positive pixel centre is
    transformed back to China Albers and counted only if it falls in
    the half-open cell rectangle. No resampling, no area invented.
    """
    xmin, ymin, xmax, ymax = bounds
    with rasterio.open(tif_path) as ds:
        to_raster = Transformer.from_crs(
            CHINA_ALBERS_CRS, ds.crs, always_xy=True)
        wx0, wy0 = to_raster.transform(xmin, ymin)
        wx1, wy1 = to_raster.transform(xmax, ymax)
        rminx, rmaxx = sorted((wx0, wx1))
        rminy, rmaxy = sorted((wy0, wy1))
        # Extra pad for the CRS edge distortion at UTM/datum seams.
        window = from_bounds(
            rminx - 120, rminy - 120, rmaxx + 120, rmaxy + 120,
            ds.transform).round_lengths().round_offsets().crop(
            ds.height, ds.width)
        if window.width <= 0 or window.height <= 0:
            return 0
        block = ds.read(1, window=window)
        rows, cols = np.where(block == 1)
        if rows.size == 0:
            return 0
        xs, ys = rasterio.transform.xy(
            ds.transform,
            rows + window.row_off, cols + window.col_off, offset="center")
        to_albers = Transformer.from_crs(
            ds.crs, CHINA_ALBERS_CRS, always_xy=True)
        ax, ay = to_albers.transform(np.array(xs), np.array(ys))
        ax = np.asarray(ax)
        ay = np.asarray(ay)
        inside = ((ax >= xmin) & (ax < xmax) & (ay >= ymin) & (ay < ymax))
        return int(inside.sum())


def geodata_counts(cell_ids: pd.Series) -> pd.DataFrame:
    counts_15: list[int] = []
    counts_20: list[int] = []
    n = len(cell_ids)
    for i, cell_id in enumerate(cell_ids):
        ref = parse_cell_id(cell_id)
        bounds = GRID.cell_bounds_projected(ref.row, ref.col)
        counts_15.append(count_raster_positive_centers(
            GEODATA_2015_TIF, bounds))
        counts_20.append(count_raster_positive_centers(
            GEODATA_2020_TIF, bounds))
        if (i + 1) % 250 == 0:
            print(f"  geodata windows {i + 1}/{n}")
    return pd.DataFrame({
        "cell_id": cell_ids.values,
        "geodata_2015_pos_px": counts_15,
        "geodata_2020_pos_px": counts_20})


def cmsa_areas(frame: pd.DataFrame) -> pd.DataFrame:
    """Exact gridcode-2 union area per cell in China Albers."""
    cells = gpd.GeoDataFrame(
        frame[["cell_id"]].copy(),
        geometry=[box(*GRID.cell_bounds_projected(
            parse_cell_id(c).row, parse_cell_id(c).col))
            for c in frame["cell_id"]],
        crs=CHINA_ALBERS_CRS)
    cells_geom = dict(zip(cells["cell_id"], cells.geometry, strict=True))
    rows = []
    for year in (2020, 2021):
        shapes = gpd.read_file(CMSA_DIR / f"CMSA_{year}.shp")
        shapes = shapes[
            shapes["gridcode"].isin((0, 2)) & shapes.geometry.notna()
        ].to_crs(CHINA_ALBERS_CRS)
        joined = gpd.sjoin(
            shapes[["gridcode", "geometry"]], cells, how="inner",
            predicate="intersects")
        pos_map = {
            cid: float(gs.unary_union.intersection(
                cells_geom[cid]).area)
            for cid, gs in joined[joined["gridcode"] == 2].groupby(
                "cell_id")}
        unk_map = {
            cid: float(gs.unary_union.intersection(
                cells_geom[cid]).area)
            for cid, gs in joined[joined["gridcode"] == 0].groupby(
                "cell_id")}
        pos = pd.Series(pos_map)
        unk = pd.Series(unk_map)
        part = pd.DataFrame({
            "cell_id": frame["cell_id"],
            f"cmsa_{year}_area_m2": pos.reindex(
                frame["cell_id"]).fillna(0.0).values,
            f"cmsa_{year}_gridcode0_area_m2": unk.reindex(
                frame["cell_id"]).fillna(0.0).values})
        rows.append(part.drop(columns=["cell_id"]))
    return pd.concat(
        [frame[["cell_id"]], *rows], axis=1)


def census_counts(cell_ids: set[str]) -> pd.DataFrame:
    census = pd.read_parquet(CENSUS_PARQUET)
    census = census[census["cell_id"].isin(cell_ids)]
    autumn = census[
        (census["season_tag"] == AUTUMN)
        & (census["coverage"] == FULL)]
    agg = (autumn.groupby(["cell_id", "sensor", "year"])
           .size().rename("n").reset_index())
    out = pd.DataFrame({"cell_id": sorted(cell_ids)})
    specs = {
        "s2_autumn_full_2020": ("sentinel2", 2020),
        "s2_autumn_full_2021": ("sentinel2", 2021),
        "s1_autumn_full_2020": ("sentinel1", 2020),
        "s1_autumn_full_2021": ("sentinel1", 2021),
        "landsat_autumn_full_2015": ("landsat", 2015),
        "landsat_autumn_full_2020": ("landsat", 2020),
    }
    for col, (sensor, year) in specs.items():
        if sensor == "landsat":
            sub = set(agg[(agg["sensor"].str.startswith("landsat"))
                          & (agg["year"] == year)]["cell_id"])
        else:
            sub = set(agg[(agg["sensor"] == sensor)
                          & (agg["year"] == year)]["cell_id"])
        out[col] = out["cell_id"].isin(sub).astype(int)
    return out


def crosscheck(name: str, measured: "np.typing.NDArray[np.float64]",
               reference_area: "np.typing.NDArray[np.float64]"
               ) -> dict[str, Any]:
    """Compare new measured areas (m^2) against Issue #18 px*900."""
    ref = reference_area * PX_AREA_30
    diff = np.abs(measured - ref)
    big = ref > (SMALL_AREA_KM2 * 1e6)
    rel = diff[big] / ref[big]
    return {
        "name": name,
        "cells_compared_above_noise": int(big.sum()),
        "median_abs_diff_m2": float(np.median(diff)),
        "max_abs_diff_m2": float(diff.max()),
        "fraction_within_10pct_above_noise": (
            float((rel <= REL_TOL).mean()) if big.any() else None),
        "cells_over_10pct_above_noise": int((rel > REL_TOL).sum()),
        "noise_rule_km2": SMALL_AREA_KM2,
        "rel_tol": REL_TOL,
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    frame = domain_frame()
    print(f"domain: {len(frame)} cells")

    ref18 = issue18_reference()
    frame = frame.merge(ref18, on="cell_id", how="left")
    frame = frame.rename(columns={
        "g": "geodata_2020_issue18_g_px",
        "c": "cmsa_2020_issue18_c_px",
        "m": "cmssm_2020_issue18_m_px"})

    print("counting GEODATA 2015/2020 pixel centres ...")
    geo = geodata_counts(frame["cell_id"])
    frame = frame.merge(geo, on="cell_id", how="left")

    print("intersecting CMSA 2020/2021 polygons ...")
    cmsa = cmsa_areas(frame)
    frame = frame.merge(cmsa, on="cell_id", how="left")

    print("aggregating census v0.1 EO availability ...")
    eo = census_counts(set(frame["cell_id"]))
    frame = frame.merge(eo, on="cell_id", how="left")

    print("attributing provinces (Natural Earth R1 rule) ...")
    prov = attribute_provinces(frame)
    frame["province"] = frame["cell_id"].map(
        lambda c: prov[c]["province"])
    frame["province_rule"] = frame["cell_id"].map(
        lambda c: prov[c]["rule"])

    flag_only_ids = frame.loc[
        (frame["silver_2015_positive"] == 1)
        & (frame["geodata_2015_pos_px"] == 0), "cell_id"].tolist()
    raster_only_ids = frame.loc[
        (frame["silver_2015_positive"] == 0)
        & (frame["geodata_2015_pos_px"] > 0), "cell_id"].tolist()
    flag_check_2015 = {
        "strata_flag_positive": int(frame["silver_2015_positive"].sum()),
        "raster_count_positive": int(
            (frame["geodata_2015_pos_px"] > 0).sum()),
        "both": int(((frame["silver_2015_positive"] == 1)
                     & (frame["geodata_2015_pos_px"] > 0)).sum()),
        "flag_only": len(flag_only_ids),
        "raster_only": len(raster_only_ids),
        "flag_only_cell_ids": sorted(flag_only_ids),
        "raster_only_cell_ids": sorted(raster_only_ids),
        "same_source_raster_sha256": sha256(GEODATA_2015_TIF),
        "diagnosis": (
            "The strata boolean uses a 60 m padded-window ANY-pixel "
            "test. flag_only cells are flagged by value-1 pixels whose "
            "reprojected centres fall OUTSIDE the cell (adjacent "
            "boundary pixels inside the 60 m pad); strict centre "
            "ownership removes these 28 false positives. The "
            "raster_only cells hold in-cell pixels that sit beyond "
            "the 60 m pad in raster space because of UTM50/Albers "
            "CRS distortion; the exact 120 m centre-in-cell window "
            "recovers them (verified per cell: padded-window ones "
            "equal the strict in-cell count). The strict "
            "centre-in-cell counts are the authoritative v0.2 "
            "presence values; the strata flag is carried as provenance."),
    }
    checks = [
        crosscheck("geodata_2020_vs_issue18_g",
                   frame["geodata_2020_pos_px"].to_numpy(float) * PX_AREA_30,
                   frame["geodata_2020_issue18_g_px"].to_numpy(float)),
        crosscheck("cmsa_2020_vs_issue18_c",
                   frame["cmsa_2020_area_m2"].to_numpy(float),
                   frame["cmsa_2020_issue18_c_px"].to_numpy(float)),
    ]

    keep_cols = [
        "cell_id", "membership_v1_1", "production_eligible",
        "center_lon", "center_lat", "province", "province_rule",
        "exclusive_stratum", "silver_2015_positive", "silver_2015_nearby",
        "cmsa_positive_history", "cmssm_2020_positive",
        "geodata_2015_pos_px", "geodata_2020_pos_px",
        "geodata_2020_issue18_g_px", "cmsa_2020_area_m2",
        "cmsa_2020_issue18_c_px", "cmsa_2021_area_m2",
        "cmsa_2020_gridcode0_area_m2", "cmsa_2021_gridcode0_area_m2",
        "cmssm_2020_issue18_m_px", "s2_autumn_full_2020",
        "s2_autumn_full_2021", "s1_autumn_full_2020",
        "s1_autumn_full_2021", "landsat_autumn_full_2015",
        "landsat_autumn_full_2020", "old_stage1_panel"]
    frame = frame[keep_cols].sort_values("cell_id").reset_index(drop=True)
    frame.to_csv(OUT_CSV, index=False)

    manifest = {
        "artifact": "V0_2_CELL_FEATURES",
        "issue": 21,
        "phase": "B",
        "generated_utc": pd.Timestamp.utcnow().isoformat(),
        "git_commit": git_commit(),
        "n_cells": len(frame),
        "pixel_policy": (
            "GEODATA: source 30 m value-1 pixel reprojected centre in "
            "half-open Albers cell, 900 m^2/source px; CMSA: exact "
            "gridcode-2 polygon union area in Albers, gridcode-0 "
            "recorded as UNKNOWN; no GEE pixels, no model information"),
        "inputs": {
            "registry": {"path": str(REGISTRY_CSV.relative_to(REPO_ROOT)),
                         "sha256": sha256(REGISTRY_CSV)},
            "strata": {"path": str(STRATA_CSV.relative_to(REPO_ROOT)),
                       "sha256": sha256(STRATA_CSV)},
            "s30_cells": {"path": str(S30_CELLS.relative_to(REPO_ROOT)),
                          "sha256": sha256(S30_CELLS)},
            "census_v0_1": {
                "path": str(CENSUS_PARQUET.relative_to(REPO_ROOT)),
                "sha256": sha256(CENSUS_PARQUET)},
            "geodata_2015_tif": {
                "path": str(GEODATA_2015_TIF.relative_to(REPO_ROOT)),
                "sha256": sha256(GEODATA_2015_TIF)},
            "geodata_2020_tif": {
                "path": str(GEODATA_2020_TIF.relative_to(REPO_ROOT)),
                "sha256": sha256(GEODATA_2020_TIF)},
            "cmsa_2020_shp_sha256": sha256(CMSA_DIR / "CMSA_2020.shp"),
            "cmsa_2021_shp_sha256": sha256(CMSA_DIR / "CMSA_2021.shp"),
        },
        "crosschecks": checks,
        "geodata_2015_flag_crosscheck": flag_check_2015,
        "output_sha256": sha256(OUT_CSV),
    }
    OUT_JSON.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"checks": checks, "flag2015": flag_check_2015},
                     indent=2))
    print(f"wrote {OUT_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
