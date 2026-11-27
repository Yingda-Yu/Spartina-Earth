#!/usr/bin/env python3
"""Offline acquisition-group + cell-QA simulation (M2.1a2, Issue #12).

Inputs (all already on disk; NO Earth Engine calls here):
  * M2.1a 18,435-scene census parquet
  * S2 datatake supplement (real DATATAKE_IDENTIFIER for every S2 scene)
  * representative frame footprints (21 fixed frames)
  * fixed analysis-cell registries (5/10/20 km)

Outputs:
  * zhejiang_acquisition_group_simulation_v0.parquet (tracked) and
  * work/derived/...csv (wide, >1 MiB, not tracked)  (event rows)
  * work/derived/zhejiang_cell_observations_v0.parquet       (long pairs)
  * zhejiang_cell_observation_stats_v0.csv                   (aggregates)
  * zhejiang_s2_recovery_v0.csv                              (section 19)
  * zhejiang_monthly_availability_v0.csv                     (real-data window)
  * zhejiang_coastal_state_example_v0.csv                    (SIMULATED schema)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pyproj  # noqa: E402
import yaml  # noqa: E402
from shapely.geometry import shape  # noqa: E402
from shapely.geometry.base import BaseGeometry  # noqa: E402
from shapely.ops import transform as shp_transform  # noqa: E402
from shapely.strtree import STRtree  # noqa: E402

from spartina.data.zhejiang.acquisition import (  # noqa: E402
    ACQUISITION_GROUP_COLUMNS,
    CELL_OBSERVATION_COLUMNS,
    CLOUD_GATE_BASIS_CONTRIBUTING,
    CLOUD_GATE_BASIS_NA,
    CLOUD_GATE_FAIL,
    CLOUD_GATE_MISSING,
    CLOUD_GATE_NA,
    CLOUD_GATE_PASS,
    QA_BASIS,
    frame_key,
    group_footprint,
    group_scenes,
)
from spartina.data.zhejiang.cells import (  # noqa: E402
    RELEVANT,
    cell_polygon,
    grid_spec,
)
from spartina.data.zhejiang.coastal import (  # noqa: E402
    COASTAL_STATE_COLUMNS,
    SHORELINE_SOURCE_NONE,
    STATUS_MISSING,
    STATUS_SIMULATED_EXAMPLE,
    CoastalStateRecord,
)

OPTICAL = ("landsat5", "landsat7", "landsat8", "landsat9", "sentinel2")


def load_frames(path: Path) -> dict[str, BaseGeometry]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    to_p = pyproj.Transformer.from_crs(4326, 32651, always_xy=True).transform
    frames: dict[str, BaseGeometry] = {}
    for f in doc["features"]:
        frames[f["properties"]["frame_key"]] = shp_transform(
            to_p, shape(f["geometry"]))
    return frames


def q(vals: list[float], qq: float) -> float | None:
    if not vals:
        return None
    return round(float(np.quantile(vals, qq)), 4)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config",
                        default=str(REPO_ROOT
                                    / "configs/data/zhejiang_multibay_m21a.yaml"))
    parser.add_argument("--manifest-dir",
                        default=str(REPO_ROOT / "datasets/manifests"))
    parser.add_argument("--work-dir",
                        default=str(REPO_ROOT / "work/derived"))
    args = parser.parse_args()

    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    mdir = Path(args.manifest_dir)
    wdir = Path(args.work_dir)
    wdir.mkdir(parents=True, exist_ok=True)
    m2 = config["m21a2"]

    census = pd.read_parquet(REPO_ROOT / config["census"]["scene_table_path"])
    supp = pd.read_parquet(REPO_ROOT / m2["s2_datatake_supplement"]["path"])
    frames = load_frames(REPO_ROOT / m2["frame_registry"]["path"])

    # --- merge real datatake into physical scenes (dedupe across bays) ----
    sup = supp.set_index("scene_id")
    scenes: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in census.to_dict("records"):
        sid = row["scene_id"]
        if sid in seen:
            continue
        seen.add(sid)
        d = dict(row)
        if d["sensor"] == "sentinel2" and sid in sup.index:
            r = sup.loc[sid]
            if isinstance(r, pd.DataFrame):  # duplicate guard, take first
                r = r.iloc[0]
            d["datatake_identifier"] = r["datatake_identifier"]
            rel = r["relative_orbit_number"]
            d["relative_orbit_number"] = (
                int(rel) if pd.notna(rel) else None)
            if not d.get("spacecraft"):
                d["spacecraft"] = r["spacecraft"]
        else:
            d["datatake_identifier"] = (
                "" if d["sensor"] == "sentinel2" else None)
        scenes.append(d)
    s2 = [s for s in scenes if s["sensor"] == "sentinel2"]
    n_dt = sum(1 for s in s2 if s["datatake_identifier"])
    print(f"physical scenes={len(scenes)} (census rows={len(census)}); "
          f"S2 with real datatake={n_dt}/{len(s2)}")

    groups = group_scenes(scenes)
    print(f"acquisition groups={len(groups)} "
          f"(multi-scene: {sum(1 for g in groups if g.n_scenes > 1)})")

    cells_df = pd.read_csv(mdir / "zhejiang_analysis_cells_v0.csv")
    windows = config["season_windows_m21a2"]
    cov_min = float(m2["cell_qa"]["coverage_min"])
    cld_max = float(m2["cell_qa"]["scene_cloud_max"])
    scenes_by_id = {s["scene_id"]: s for s in scenes}

    # index groups by frame geometry for spatial lookup
    group_rows = [g.as_row() for g in groups]

    all_pairs: list[dict[str, Any]] = []
    stats_rows: list[dict[str, Any]] = []
    monthly_rows: list[dict[str, Any]] = []

    sizes = [int(s) for s in m2["grid"]["candidate_cell_sizes_m"]]
    for size in sizes:
        sub = cells_df[(cells_df.cell_size_m == size)
                       & (cells_df.coastal_relevance == RELEVANT)]
        cell_records = []
        cell_geoms: list[BaseGeometry] = []
        for r in sub.to_dict("records"):
            gs = grid_spec(int(r["cell_size_m"]))
            poly = cell_polygon(gs, int(r["index_east"]),
                                int(r["index_north"]))
            cell_records.append(r)
            cell_geoms.append(poly)
        tree = STRtree(cell_geoms)
        n_cells = len(cell_records)

        # group -> candidate cell indices + coverage
        pair_buf: list[dict[str, Any]] = []
        # month aggregates (10 km grid only)
        month_agg: dict[tuple[str, int, str], dict[str, Any]] = {}
        for g in groups:
            fp = group_footprint(g, frames)
            cand = tree.query(fp, predicate="intersects")
            if len(cand) == 0:
                continue
            # group-wide (legacy v0) cloud verdict, diagnostic only
            member_clouds = [
                scenes_by_id[sid].get("scene_cloud_fraction")
                for sid in g.member_scene_ids
                if sid in scenes_by_id
            ]
            clouds = [c for c in member_clouds
                      if isinstance(c, int | float)]
            cloud_max = max(clouds) if clouds else None
            if g.sensor == "sentinel1":
                gw_gate = CLOUD_GATE_NA
            elif cloud_max is None:
                gw_gate = CLOUD_GATE_MISSING
            elif cloud_max <= cld_max:
                gw_gate = CLOUD_GATE_PASS
            else:
                gw_gate = CLOUD_GATE_FAIL
            # member scene -> own frame geometry (R1 contributing gate)
            member_frames: list[tuple[str, BaseGeometry]] = []
            for _sid in g.member_scene_ids:
                _sc = scenes_by_id.get(_sid)
                if _sc is None:
                    continue
                _fg = frames.get(frame_key(_sc))
                if _fg is not None:
                    member_frames.append((_sid, _fg))
            doy = pd.Timestamp(g.event_date).dayofyear
            win_ids = [w["id"] for w in windows
                       if int(w["doy_start"]) <= doy <= int(w["doy_end"])]
            win_layer = "|".join(sorted({
                w.get("layer", "season") for w in windows
                if w["id"] in win_ids}))
            cloudpass_by_cell: dict[int, str] = {}
            for ci in cand:
                cell = cell_records[int(ci)]
                geom = cell_geoms[int(ci)]
                inter = geom.intersection(fp)
                coverage = float(inter.area / geom.area)
                # contributing member scenes = own frame intersects cell
                contributing: list[str] = []
                single_cov = 0.0
                for _sid, _fg in member_frames:
                    if _fg.intersects(geom):
                        contributing.append(_sid)
                        single_cov = max(
                            single_cov,
                            float(geom.intersection(_fg).area / geom.area))
                cclouds = [
                    scenes_by_id[_sid].get("scene_cloud_fraction")
                    for _sid in contributing if _sid in scenes_by_id]
                cnum = [c for c in cclouds if isinstance(c, int | float)]
                cmax = max(cnum) if cnum else None
                if g.sensor == "sentinel1":
                    cloud_gate = CLOUD_GATE_NA
                elif cmax is None:
                    cloud_gate = CLOUD_GATE_MISSING
                elif cmax <= cld_max:
                    cloud_gate = CLOUD_GATE_PASS
                else:
                    cloud_gate = CLOUD_GATE_FAIL
                cloudpass_by_cell[int(ci)] = cloud_gate
                cov_gate = coverage >= cov_min
                quality = bool(
                    cov_gate and cloud_gate in (CLOUD_GATE_PASS,
                                                CLOUD_GATE_NA))
                pair_buf.append({
                    "cell_id": cell["cell_id"],
                    "bay_id": cell["bay_id"],
                    "cell_size_m": size,
                    "group_id": g.group_id,
                    "sensor": g.sensor,
                    "year": int(g.event_date[:4]),
                    "event_date": g.event_date,
                    "day_of_year": doy,
                    "n_member_scenes": g.n_scenes,
                    "contributing_n_scenes": len(contributing),
                    "contributing_scene_ids": "|".join(sorted(contributing)),
                    "coverage_fraction": round(coverage, 6),
                    "single_frame_max_coverage": round(single_cov, 6),
                    "member_scene_cloud_max": (
                        round(cloud_max, 6)
                        if cloud_max is not None else None),
                    "contributing_cloud_max": (
                        round(cmax, 6) if cmax is not None else None),
                    "cloud_gate": cloud_gate,
                    "groupwide_cloud_gate": gw_gate,
                    "cloud_gate_basis": (
                        CLOUD_GATE_BASIS_NA if g.sensor == "sentinel1"
                        else CLOUD_GATE_BASIS_CONTRIBUTING),
                    "coverage_gate": bool(cov_gate),
                    "window_ids": "|".join(win_ids),
                    "window_layer": win_layer,
                    "quality_pass": quality,
                    "geometry_regime": g.geometry_regime,
                    "qa_thresholds": (
                        f"coverage>={cov_min};scene_cloud<={cld_max}"),
                    "qa_basis": QA_BASIS,
                })
            if size == 10_000 and len(cand):
                month = int(g.event_date[5:7])
                for ci in cand:
                    key = (cell_records[int(ci)]["bay_id"], month, g.sensor)
                    agg = month_agg.setdefault(key, {
                        "groups": set(), "cloudpass_groups": set(),
                        "quality_cells": set(), "observed": False})
                    agg["groups"].add(g.group_id)
                    _gate = cloudpass_by_cell[int(ci)]
                    if _gate in (CLOUD_GATE_PASS, CLOUD_GATE_NA):
                        agg["cloudpass_groups"].add(g.group_id)
        dfp = pd.DataFrame(pair_buf)
        if len(dfp):
            all_pairs.extend(pair_buf)

        # --- aggregate stats per bay/year/sensor/window ------------------
        if len(dfp):
            grp = dfp.groupby(
                ["cell_size_m", "bay_id", "year", "sensor"], sort=True)
            for (cs, bay, yr, sen), dfg in grp:
                covs = dfg.coverage_fraction.tolist()
                singles = dfg.single_frame_max_coverage.tolist()
                for w in windows:
                    mask = dfg.window_ids.str.contains(
                        rf"(?:^|\|){w['id']}(\||$)", regex=True)
                    dwin = dfg[mask]
                    stats_rows.append({
                        "cell_size_m": cs,
                        "bay_id": bay,
                        "year": yr,
                        "sensor": sen,
                        "window_id": w["id"],
                        "window_layer": w.get("layer", ""),
                        "n_coastal_cells": n_cells_for_bay(
                            cell_records, bay),
                        "n_cells_any_coverage": dfg.cell_id.nunique(),
                        "n_cells_with_quality_event": (
                            int(dwin[dwin.quality_pass].cell_id.nunique())
                            if len(dwin) else 0),
                        "n_quality_pairs": int(dwin.quality_pass.sum())
                        if len(dwin) else 0,
                        "n_pairs": len(dwin),
                        "coverage_p50": q(covs, 0.5),
                        "coverage_p90": q(covs, 0.9),
                        "coverage_max": q(covs, 1.0),
                        "single_frame_coverage_p90": q(singles, 0.9),
                        "single_frame_coverage_max": q(singles, 1.0),
                    })
                # whole-year row (window_id = ALL)
                stats_rows.append({
                    "cell_size_m": cs,
                    "bay_id": bay,
                    "year": yr,
                    "sensor": sen,
                    "window_id": "__ALL_YEAR__",
                    "window_layer": "year",
                    "n_coastal_cells": n_cells_for_bay(cell_records, bay),
                    "n_cells_any_coverage": dfg.cell_id.nunique(),
                    "n_cells_with_quality_event": int(
                        dfg[dfg.quality_pass].cell_id.nunique()),
                    "n_quality_pairs": int(dfg.quality_pass.sum()),
                    "n_pairs": len(dfg),
                    "coverage_p50": q(covs, 0.5),
                    "coverage_p90": q(covs, 0.9),
                    "coverage_max": q(covs, 1.0),
                    "single_frame_coverage_p90": q(singles, 0.9),
                    "single_frame_coverage_max": q(singles, 1.0),
                })

        if size == 10_000:
            for (bay, month, sen), agg in sorted(month_agg.items()):
                monthly_rows.append({
                    "bay_id": bay,
                    "month": month,
                    "sensor": sen,
                    "n_groups_intersecting": len(agg["groups"]),
                    "n_groups_cloud_or_sar_pass": len(
                        agg["cloudpass_groups"]),
                })
        print(f"{size} m: {n_cells} coastal cells, {len(dfp)} intersecting "
              f"pairs, {int(dfp.quality_pass.sum()) if len(dfp) else 0} "
              f"quality pairs")

    pairs_df = pd.DataFrame(all_pairs, columns=list(
        CELL_OBSERVATION_COLUMNS)) if all_pairs else pd.DataFrame()
    # M2.1a2-R1: contributing-scene cloud gate; v0 pairs superseded
    pairs_path = wdir / "zhejiang_cell_observations_v0_1.parquet"
    pairs_df.to_parquet(pairs_path, index=False)

    # --- group manifest: groups intersecting >=1 10 km coastal cell ------
    keep_ids = set(pairs_df[pairs_df.cell_size_m == 10_000].group_id) \
        if len(pairs_df) else set()
    grow = [r for r in group_rows if r["group_id"] in keep_ids]
    gdf = pd.DataFrame(grow, columns=list(ACQUISITION_GROUP_COLUMNS))
    # wide CSV (>1 MiB) kept out of Git in work/; parquet is canonical
    gdf.to_csv(wdir / "zhejiang_acquisition_group_simulation_v0.csv",
               index=False)
    gdf.to_parquet(mdir / "zhejiang_acquisition_group_simulation_v0.parquet",
                   index=False)

    stats_df = pd.DataFrame(stats_rows)
    stats_df.to_csv(mdir / "zhejiang_cell_observation_stats_v0_1.csv",
                    index=False)
    mdf = pd.DataFrame(monthly_rows)
    mdf.to_csv(mdir / "zhejiang_monthly_availability_v0_1.csv",
               index=False)

    # --- S2 recovery table (section 19) -----------------------------------
    recovery = build_s2_recovery(
        census, pairs_df, stats_df, windows)
    pd.DataFrame(recovery).to_csv(
        mdir / "zhejiang_s2_recovery_v0_1.csv", index=False)

    # --- tiny SIMULATED coastal-state example -----------------------------
    write_coastal_example(cells_df, mdir)

    print(f"groups={len(gdf)} pairs={len(pairs_df)} -> {pairs_path}")
    return 0


def n_cells_for_bay(cell_records: list[dict[str, Any]], bay: str) -> int:
    return sum(1 for c in cell_records if c["bay_id"] == bay)


def build_s2_recovery(
    census: pd.DataFrame,
    pairs_df: pd.DataFrame,
    stats_df: pd.DataFrame,
    windows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Old bay-wide single-scene gate vs new cell x event gate for S2."""
    old = census[census.sensor == "sentinel2"].copy()
    rows: list[dict[str, Any]] = []
    for size in sorted(pairs_df.cell_size_m.unique()):
        p = pairs_df[(pairs_df.cell_size_m == size)
                     & (pairs_df.sensor == "sentinel2")]
        for bay in sorted(p.bay_id.unique()):
            pb = p[p.bay_id == bay]
            ob = old[old.roi_id == bay]
            for (yr, dpy) in pb.groupby("year"):
                for w in windows:
                    m = dpy.window_ids.str.contains(
                        rf"(?:^|\|){w['id']}(\||$)", regex=True)
                    dw = dpy[m]
                    old_scenes = ob[
                        (ob.year == yr)
                        & (ob.day_of_year.between(
                            int(w["doy_start"]), int(w["doy_end"])))
                        & (ob.footprint_coverage_fraction >= 0.99)
                        & (ob.scene_cloud_fraction <= 0.30)]
                    rows.append({
                        "cell_size_m": int(size),
                        "bay_id": bay,
                        "year": int(yr),
                        "window_id": w["id"],
                        "old_baygate_scene_candidates": int(len(old_scenes)),
                        "new_cell_event_quality_pairs": int(
                            dw.quality_pass.sum()),
                        "new_cells_with_quality_event": int(
                            dw[dw.quality_pass].cell_id.nunique()),
                        "new_intersecting_pairs": int(len(dw)),
                    })
    return rows


def write_coastal_example(cells_df: pd.DataFrame, mdir: Path) -> None:
    sample_cells = (
        cells_df[(cells_df.cell_size_m == 10_000)]
        .sort_values(["bay_id", "cell_id"])
        .groupby("bay_id").head(1)["cell_id"].tolist())
    rows: list[dict[str, Any]] = []
    for cid in sample_cells:
        for date in ("2000-09-15", "2015-09-15", "2025-09-15"):
            rows.append(CoastalStateRecord(
                cell_id=cid,
                record_date=date,
                land_fraction=None,
                water_fraction=None,
                intertidal_proxy=None,
                inundation_proxy=None,
                shoreline_source=SHORELINE_SOURCE_NONE,
                shoreline_version="NONE",
                status=STATUS_SIMULATED_EXAMPLE,
                notes=(
                    "schema example only, NOT derived from any shoreline "
                    "product; tide_context_status=MISSING permitted for "
                    "M2.1b pipeline validation, not for final freeze"
                ),
            ).as_row())
        rows.append(CoastalStateRecord(
            cell_id=cid,
            record_date="2026-01-01",
            land_fraction=None, water_fraction=None,
            intertidal_proxy=None, inundation_proxy=None,
            shoreline_source=SHORELINE_SOURCE_NONE,
            shoreline_version="NONE",
            status=STATUS_MISSING,
            notes="no date-specific coastal state exists at M2.1a2",
        ).as_row())
    pd.DataFrame(rows, columns=list(COASTAL_STATE_COLUMNS)).to_csv(
        mdir / "zhejiang_coastal_state_example_v0.csv", index=False)


if __name__ == "__main__":
    raise SystemExit(main())
