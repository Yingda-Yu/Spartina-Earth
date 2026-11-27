#!/usr/bin/env python3
"""M2.1a2-R1 blocker #3: Sentinel-1 representative-vs-actual footprint audit.

Deterministic sample (target 24-60 GRD scenes; strata = bay x orbit
direction x relative orbit, spread across years) of ACTUAL per-scene
footprints fetched from GEE (geometry metadata only: one getInfo on the
filtered collection; no pixels, no export). Compare actual coverage with
the v0 representative-frame approximation on 10 km COASTAL_RELEVANT
cells and report MAE / P95 / max abs coverage error and false
eligible / false rejected counts at the unchanged coverage >= 0.99 gate.

Outputs:
  datasets/manifests/zhejiang_s1_footprint_audit_v0.{csv,parquet}
  datasets/manifests/zhejiang_s1_footprint_audit_summary_v0.csv
  datasets/manifests/zhejiang_s1_footprint_audit_v0.policy.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyproj
import yaml
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as shp_transform

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

from spartina.data.zhejiang.cells import RELEVANT, cell_polygon, grid_spec  # noqa: E402
from spartina.data.zhejiang.census import install_export_guard  # noqa: E402

COLLECTION = "COPERNICUS/S1_GRD"
CELL_SIZE = 10_000
COV_GATE = 0.99
MAX_SCENES = 60
MIN_SCENES = 24


def _spread_positions(n: int, k: int) -> list[int]:
    """Deterministic evenly-spread 0-based positions, k picks from n."""
    if k <= 1:
        return [0]
    return sorted({round(j * (n - 1) / (k - 1)) for j in range(k)})


def select_s1_sample(
    census: pd.DataFrame,
    max_scenes: int = MAX_SCENES,
) -> list[dict[str, Any]]:
    """Round-robin strata; picks within a stratum spread across time."""
    # IW is the operational coastal land mode; EW (open-ocean extra-wide
    # swath, 16 census rows total) is excluded from this audit and from
    # production coastal planning.
    s1 = census[(census.sensor == "sentinel1")
                & (census.instrument_mode == "IW")].copy()
    strata = sorted(
        s1.groupby(["roi_id", "orbit_direction",
                    "relative_orbit_number"], dropna=False).size().index)
    pools: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for key in strata:
        bay, direction, rel = key
        sub = s1[(s1.roi_id == bay) & (s1.orbit_direction == direction)
                 & (s1.relative_orbit_number.isna()
                    if pd.isna(rel)
                    else s1.relative_orbit_number == rel)]
        scenes = sub.sort_values(
            ["year", "acquisition_utc", "scene_id"]).to_dict("records")
        pools[key] = scenes
    # The same physical GRD scene can intersect several bays (250 km
    # swath), so candidate pools share scene ids. Globally de-duplicate,
    # while round-robining every (bay x direction x rel orbit) stratum so
    # all strata still contribute. Each stratum proposes up to 24
    # candidates in a deterministic YEAR-ROUND-ROBIN order (rank within
    # year, then year) so the first picks span the full time range.
    def year_round_robin(pool: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_year: dict[int, list[dict[str, Any]]] = {}
        for sc in pool:
            by_year.setdefault(int(sc["year"]), []).append(sc)
        years = sorted(by_year)
        out: list[dict[str, Any]] = []
        rank = 0
        while len(out) < 24:
            added = False
            for y in years:
                if rank < len(by_year[y]):
                    out.append(by_year[y][rank])
                    added = True
            if not added:
                break
            rank += 1
        return out

    orders = {key: year_round_robin(pool) for key, pool in pools.items()}
    chosen: list[dict[str, Any]] = []
    seen: set[str] = set()
    while len(chosen) < max_scenes:
        progressed = False
        for key in strata:
            for scene in orders[key]:
                if scene["scene_id"] not in seen:
                    seen.add(scene["scene_id"])
                    chosen.append(scene)
                    progressed = True
                    break
            if len(chosen) >= max_scenes:
                break
        if not progressed:
            break
    return chosen


def _to_32651(geom_4326: BaseGeometry) -> BaseGeometry:
    to_p = pyproj.Transformer.from_crs(
        4326, 32651, always_xy=True).transform
    return shp_transform(to_p, geom_4326)


def run_audit(config_path: Path | None = None,
              max_scenes: int = MAX_SCENES) -> pd.DataFrame:
    import ee

    from spartina.data.gee import auth

    cfg_path = config_path or (
        REPO_ROOT / "configs/data/zhejiang_multibay_m21a.yaml")
    config = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    m2 = config["m21a2"]
    mdir = REPO_ROOT / "datasets/manifests"

    census = pd.read_parquet(REPO_ROOT / config["census"]["scene_table_path"])
    sample = select_s1_sample(census, max_scenes=max_scenes)
    if len(sample) < MIN_SCENES:
        raise RuntimeError(
            f"S1 sample too small: {len(sample)} < {MIN_SCENES}")

    # representative (approx) frames in EPSG:32651
    import importlib.util
    sim_path = REPO_ROOT / "scripts/data/zhejiang/simulate_acquisition_groups.py"
    spec = importlib.util.spec_from_file_location("sim_groups", sim_path)
    assert spec and spec.loader
    sim = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sim)
    frames = sim.load_frames(REPO_ROOT / m2["frame_registry"]["path"])

    cells_df = pd.read_csv(mdir / "zhejiang_analysis_cells_v0.csv")
    bay_cells: dict[str, list[tuple[str, BaseGeometry]]] = {}
    for bay in sorted({s["roi_id"] for s in sample}):
        sub = cells_df[(cells_df.cell_size_m == CELL_SIZE)
                       & (cells_df.coastal_relevance == RELEVANT)
                       & (cells_df.bay_id == bay)]
        bay_cells[bay] = [
            (r["cell_id"],
             cell_polygon(grid_spec(CELL_SIZE), int(r["index_east"]),
                          int(r["index_north"])))
            for r in sub.to_dict("records")]

    auth.initialize()
    restore = install_export_guard(ee)
    try:
        ids = [s["scene_id"] for s in sample]
        col = ee.ImageCollection(COLLECTION).filter(
            ee.Filter.inList("system:index", ids))
        # S1_GRD image getInfo omits geometry; wrap to features so the
        # actual per-scene footprint comes back in ONE getInfo call.
        fc = ee.FeatureCollection(col.map(
            lambda img: ee.Feature(
                img.geometry(), {"sid": img.get("system:index")})))
        info = fc.getInfo()
    finally:
        restore()
    actual_geoms: dict[str, BaseGeometry] = {}
    for f in info["features"]:
        actual_geoms[f["properties"]["sid"]] = _to_32651(
            shape(f["geometry"]))

    rows: list[dict[str, Any]] = []
    for s in sample:
        sid = s["scene_id"]
        bay = s["roi_id"]
        direction = s["orbit_direction"]
        rel = int(s["relative_orbit_number"])
        approx = frames.get(f"S1:{direction}:{rel}")
        actual = actual_geoms.get(sid)
        for cid, geom in bay_cells[bay]:
            cov_approx = (float(geom.intersection(approx).area / geom.area)
                          if approx is not None and approx.intersects(geom)
                          else 0.0)
            cov_actual = (float(geom.intersection(actual).area / geom.area)
                          if actual is not None and actual.intersects(geom)
                          else 0.0)
            if cov_approx == 0.0 and cov_actual == 0.0:
                continue
            elig_approx = cov_approx >= COV_GATE
            elig_actual = cov_actual >= COV_GATE
            rows.append({
                "scene_id": sid,
                "bay_id": bay,
                "year": int(s["year"]),
                "orbit_direction": direction,
                "relative_orbit_number": rel,
                "cell_id": cid,
                "coverage_actual": round(cov_actual, 6),
                "coverage_approx_representative": round(cov_approx, 6),
                "abs_error": round(abs(cov_actual - cov_approx), 6),
                "eligible_actual_ge_0.99": elig_actual,
                "eligible_approx_ge_0.99": elig_approx,
                "false_eligible_approx_only": elig_approx and not elig_actual,
                "false_rejected_actual_only": elig_actual and not elig_approx,
                "actual_geometry_present": actual is not None,
            })
    df = pd.DataFrame(rows)
    if df.empty or not df["actual_geometry_present"].all():
        raise RuntimeError("S1 footprint audit: missing actual geometries")
    df.to_csv(mdir / "zhejiang_s1_footprint_audit_v0.csv", index=False)
    df.to_parquet(mdir / "zhejiang_s1_footprint_audit_v0.parquet",
                  index=False)
    return df


def _summary(df: pd.DataFrame) -> pd.DataFrame:
    def agg(d: pd.DataFrame, label: str, key: dict[str, Any]) -> dict[str, Any]:
        err = d.abs_error.to_numpy()
        return {
            **key,
            "stratum": label,
            "n_scenes": d.scene_id.nunique(),
            "n_cell_rows": len(d),
            "coverage_mae": round(float(np.mean(err)), 6),
            "coverage_p95_abs_error": round(float(np.quantile(err, 0.95)), 6),
            "coverage_max_abs_error": round(float(np.max(err)), 6),
            "false_eligible_approx_only": int(
                d["false_eligible_approx_only"].sum()),
            "false_rejected_actual_only": int(
                d["false_rejected_actual_only"].sum()),
            "eligible_actual_pairs": int(
                d["eligible_actual_ge_0.99"].sum()),
            "eligible_approx_pairs": int(
                d["eligible_approx_ge_0.99"].sum()),
        }
    out = [agg(df, "ALL", {})]
    for bay, d0 in df.groupby("bay_id"):
        out.append(agg(d0, f"bay:{bay}", {"bay_id": bay,
                                          "orbit_direction": "",
                                          "relative_orbit_number": ""}))
        for (direction, rel), d1 in d0.groupby(
                ["orbit_direction", "relative_orbit_number"]):
            out.append(agg(d1, f"bay:{bay}/{direction}/{int(rel)}", {
                "bay_id": bay, "orbit_direction": direction,
                "relative_orbit_number": int(rel)}))
    return pd.DataFrame(out)


def write_policy(df: pd.DataFrame, summary: pd.DataFrame) -> dict[str, Any]:
    overall = summary[summary.stratum == "ALL"].iloc[0]
    n_fe = int(overall["false_eligible_approx_only"])
    n_fr = int(overall["false_rejected_actual_only"])
    needs_actual = (n_fe + n_fr) > 0
    policy = {
        "audit": "zhejiang_s1_footprint_audit_v0",
        "marker": "S1_REPRESENTATIVE_FOOTPRINT_NOT_PRODUCTION_GEOMETRY",
        "sample_n_scenes": int(df.scene_id.nunique()),
        "cell_size_m": CELL_SIZE,
        "coverage_gate_unchanged": COV_GATE,
        "overall": {
            "coverage_mae": float(overall["coverage_mae"]),
            "coverage_p95_abs_error": float(
                overall["coverage_p95_abs_error"]),
            "coverage_max_abs_error": float(
                overall["coverage_max_abs_error"]),
            "false_eligible_approx_only": n_fe,
            "false_rejected_actual_only": n_fr,
        },
        "production_footprint_policy": (
            "Actual per-scene GEE geometry is the production eligibility "
            "geometry: the representative-frame approximation disagrees "
            "with the 0.99 coverage decision on at least one sampled "
            "cell. Representative frames remain a cheap planning / "
            "prefilter estimate only and must never be silently used as "
            "the final pair geometry."
            if needs_actual else
            "On this sample the representative frame never disagrees "
            "with actual geometry at the 0.99 gate; it may be used as a "
            "prefilter, but actual GEE geometry remains the production "
            "QA source for frozen pairs."),
        "approx_status": "PLANNING_PREFILTER_ONLY",
        "actual_status": "PRODUCTION_ELIGIBILITY_AND_QA",
        "metadata_only": True,
    }
    path = (REPO_ROOT / "datasets/manifests"
            / "zhejiang_s1_footprint_audit_v0.policy.json")
    path.write_text(json.dumps(policy, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    return policy


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config")
    parser.add_argument("--max-scenes", type=int, default=MAX_SCENES)
    args = parser.parse_args()
    df = run_audit(Path(args.config) if args.config else None,
                   max_scenes=args.max_scenes)
    summary = _summary(df)
    summary.to_csv(REPO_ROOT / "datasets/manifests"
                   / "zhejiang_s1_footprint_audit_summary_v0.csv",
                   index=False)
    policy = write_policy(df, summary)
    print(summary[summary.stratum.isin(
        ["ALL"] + [f"bay:{b}" for b in sorted(df.bay_id.unique())])]
        .to_string(index=False))
    print("false eligible:", policy["overall"]["false_eligible_approx_only"],
          "false rejected:", policy["overall"]["false_rejected_actual_only"],
          "n_scenes:", policy["sample_n_scenes"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
