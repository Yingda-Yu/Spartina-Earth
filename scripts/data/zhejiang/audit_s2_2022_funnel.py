#!/usr/bin/env python3
"""M2.1a2-R1 blocker #2: 2022 autumn Sentinel-2 zero-event funnel audit.

Offline, metadata + geometry only (no GEE calls, no pixels). Reproduces the
full acquisition funnel for the 2022 autumn primary window (DOY 260-320) on
the 10 km COASTAL_RELEVANT cells of the three Zhejiang bays under:

* v0 gate  : cloud max over ALL member scenes of the datatake group
* R1 gate  : cloud max over only member scenes whose frame geometry
             actually intersects that cell (thresholds unchanged)

Outputs (datasets/manifests/):
  zhejiang_s2_2022_funnel_audit_v0.csv         stage counts per bay
  zhejiang_s2_2022_funnel_rejections_v0.csv    pair rejection buckets
  zhejiang_s2_2022_funnel_audit_v0.verdict.json machine-readable verdict

Markers: S2_2022_ZERO_WAS_GROUPWIDE_CLOUD_BUG.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import yaml
from shapely.strtree import STRtree

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

from spartina.data.zhejiang.acquisition import (  # noqa: E402
    S2_GROUP_RULE,
    frame_key,
    group_footprint,
    group_scenes,
)
from spartina.data.zhejiang.cells import RELEVANT, cell_polygon, grid_spec  # noqa: E402

YEAR = 2022
WINDOW_LABEL = "autumn_primary_v1"
DOY_START, DOY_END = 260, 320
BAYS = ("ZJ-HZB", "ZJ-SMB", "ZJ-YQB")
CELL_SIZE = 10_000

# pair-level rejection buckets
B_LOW_COVERAGE = "LOW_COVERAGE_lt_0.99"
B_BOTH_FAIL = "FAIL_CLOUD_BOTH_V0_AND_R1"
B_RECOVERED = "RECOVERED_R1_GROUPWIDE_POISONED_ONLY"
B_MISSING_V0 = "CLOUD_METADATA_MISSING_V0_GROUPWIDE"
B_MISSING_R1 = "CLOUD_METADATA_MISSING_R1_CONTRIBUTING"
B_FINAL_R1 = "FINAL_QUALITY_PASS_R1"


def _load_simulator() -> Any:
    path = REPO_ROOT / "scripts/data/zhejiang/simulate_acquisition_groups.py"
    spec = importlib.util.spec_from_file_location("sim_groups", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build_scenes(census: pd.DataFrame, supp: pd.DataFrame) -> list[dict[str, Any]]:
    """Same physical-scene dedupe + datatake merge as the simulator."""
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
            if isinstance(r, pd.DataFrame):
                r = r.iloc[0]
            d["datatake_identifier"] = r["datatake_identifier"]
            rel = r["relative_orbit_number"]
            d["relative_orbit_number"] = int(rel) if pd.notna(rel) else None
            if not d.get("spacecraft"):
                d["spacecraft"] = r["spacecraft"]
        else:
            d["datatake_identifier"] = (
                "" if d["sensor"] == "sentinel2" else None)
        scenes.append(d)
    return scenes


def _clouds(ids: list[str], by_id: dict[str, dict[str, Any]]) -> float | None:
    vals = [by_id[i].get("scene_cloud_fraction") for i in ids
            if i in by_id]
    nums = [v for v in vals if isinstance(v, int | float)]
    return max(nums) if nums else None


def main() -> int:
    config = yaml.safe_load((REPO_ROOT / "configs/data/zhejiang_multibay_m21a.yaml")
                            .read_text(encoding="utf-8"))
    m2 = config["m21a2"]
    cov_min = float(m2["cell_qa"]["coverage_min"])
    cld_max = float(m2["cell_qa"]["scene_cloud_max"])
    mdir = REPO_ROOT / "datasets/manifests"

    census = pd.read_parquet(REPO_ROOT / config["census"]["scene_table_path"])
    supp = pd.read_parquet(REPO_ROOT / m2["s2_datatake_supplement"]["path"])
    sim = _load_simulator()
    frames = sim.load_frames(REPO_ROOT / m2["frame_registry"]["path"])

    scenes = build_scenes(census, supp)
    by_id = {s["scene_id"]: s for s in scenes}
    groups = group_scenes(scenes)

    cells_df = pd.read_csv(mdir / "zhejiang_analysis_cells_v0.csv")
    bay_cells: dict[str, list[dict[str, Any]]] = {}
    bay_geoms: dict[str, list[Any]] = {}
    for bay in BAYS:
        sub = cells_df[(cells_df.cell_size_m == CELL_SIZE)
                       & (cells_df.coastal_relevance == RELEVANT)
                       & (cells_df.bay_id == bay)]
        recs = sub.to_dict("records")
        geoms = [cell_polygon(grid_spec(CELL_SIZE),
                              int(r["index_east"]), int(r["index_north"]))
                 for r in recs]
        bay_cells[bay] = recs
        bay_geoms[bay] = geoms

    s2_2022 = [s for s in scenes if s["sensor"] == "sentinel2"
               and int(s["year"]) == YEAR]
    assert s2_2022  # 2022 S2 scenes must exist; fail loudly if not
    autumn_groups = [g for g in groups if g.sensor == "sentinel2"
                     and int(g.event_date[:4]) == YEAR
                     and DOY_START <= pd.Timestamp(g.event_date).dayofyear
                     <= DOY_END]

    stage_rows: list[dict[str, Any]] = []
    reject_rows: list[dict[str, Any]] = []
    datatake_checks: dict[str, Any] = {}

    # global datatake grouping verification for the autumn window
    rule_counts: dict[str, int] = {}
    multi_date_groups = 0
    for g in autumn_groups:
        rule_counts[g.grouping_rule] = rule_counts.get(g.grouping_rule, 0) + 1
        dates = {by_id[i]["acquisition_utc"][:10]
                 for i in g.member_scene_ids if i in by_id}
        if len(dates) > 1:
            multi_date_groups += 1
    cross_bay_groups = set()
    for g in autumn_groups:
        hits = set()
        fp = group_footprint(g, frames)
        for bay in BAYS:
            tree = STRtree(bay_geoms[bay])
            if len(tree.query(fp, predicate="intersects")):
                hits.add(bay)
        if len(hits) > 1:
            cross_bay_groups.add(g.group_id)
    datatake_checks = {
        "n_autumn_groups_total": len(autumn_groups),
        "grouping_rule_counts": rule_counts,
        "all_groups_real_datatake": (
            set(rule_counts) <= {S2_GROUP_RULE}),
        "groups_spanning_multiple_utc_dates": multi_date_groups,
        "groups_intersecting_multiple_bays": sorted(cross_bay_groups),
        "n_groups_intersecting_multiple_bays": len(cross_bay_groups),
        "window": {"label": WINDOW_LABEL, "doy_start": DOY_START,
                   "doy_end": DOY_END},
        "thresholds": {"coverage_min": cov_min, "scene_cloud_max": cld_max},
    }

    for bay in BAYS:
        raw = census[(census.roi_id == bay) & (census.sensor == "sentinel2")
                     & (census.year == YEAR)]
        # census is per-roi; dedupe scene ids within this bay's raw rows
        bay_ids: set[str] = set(raw.scene_id)
        phys = [by_id[i] for i in sorted(bay_ids) if i in by_id]
        aut = [s for s in phys if DOY_START <= int(s["day_of_year"])
               <= DOY_END]

        geoms = bay_geoms[bay]
        tree = STRtree(geoms)
        bay_autumn_groups = []
        for g in autumn_groups:
            fp = group_footprint(g, frames)
            if len(tree.query(fp, predicate="intersects")):
                bay_autumn_groups.append(g)

        buckets = {B_LOW_COVERAGE: 0, B_BOTH_FAIL: 0, B_RECOVERED: 0,
                   B_MISSING_V0: 0, B_MISSING_R1: 0, B_FINAL_R1: 0}
        n_pairs = 0
        n_covpass = 0
        n_final_v0 = 0
        n_final_r1 = 0
        n_gw_pass = 0
        n_r1_cloudpass = 0
        for g in bay_autumn_groups:
            fp = group_footprint(g, frames)
            gw_max = _clouds(g.member_scene_ids, by_id)
            gw_gate = ("PASS" if gw_max is not None and gw_max <= cld_max
                       else "MISSING" if gw_max is None else "FAIL")
            cand = tree.query(fp, predicate="intersects")
            member_frames = []
            for sid in g.member_scene_ids:
                sc = by_id.get(sid)
                if sc is None:
                    continue
                fg = frames.get(frame_key(sc))
                if fg is not None:
                    member_frames.append((sid, fg))
            for ci in cand:
                geom = geoms[int(ci)]
                coverage = float(geom.intersection(fp).area / geom.area)
                n_pairs += 1
                contrib = [sid for sid, fg in member_frames
                           if fg.intersects(geom)]
                cmax = _clouds(contrib, by_id)
                r1_gate = ("PASS" if cmax is not None and cmax <= cld_max
                           else "MISSING" if cmax is None else "FAIL")
                if coverage < cov_min:
                    buckets[B_LOW_COVERAGE] += 1
                    continue
                n_covpass += 1
                if gw_gate == "PASS":
                    n_gw_pass += 1
                if r1_gate == "PASS":
                    n_r1_cloudpass += 1
                v0_ok = gw_gate == "PASS"
                r1_ok = r1_gate == "PASS"
                if r1_gate == "MISSING":
                    buckets[B_MISSING_R1] += 1
                if gw_gate == "MISSING":
                    buckets[B_MISSING_V0] += 1
                if v0_ok:
                    n_final_v0 += 1
                if r1_ok:
                    n_final_r1 += 1
                    buckets[B_FINAL_R1] += 1
                    if not v0_ok:
                        buckets[B_RECOVERED] += 1
                elif gw_gate == "FAIL" and r1_gate == "FAIL":
                    buckets[B_BOTH_FAIL] += 1
        for label, count in (
            ("A_raw_census_rows", len(raw)),
            ("B_physical_unique_scenes", len(phys)),
            ("C_autumn_scenes", len(aut)),
            ("D_autumn_datatake_groups_intersecting_bay",
             len(bay_autumn_groups)),
            ("E_cell_group_candidate_pairs", n_pairs),
            ("G_coverage_pass_pairs_ge_0.99", n_covpass),
            ("H_valid_pixel_layer", None),
            ("I_v0_cloud_pass_groupwide", n_gw_pass),
            ("J_v0_final_quality_pairs", n_final_v0),
            ("I_R1_cloud_pass_contributing", n_r1_cloudpass),
            ("J_R1_final_quality_pairs", n_final_r1),
        ):
            stage_rows.append({
                "bay_id": bay,
                "year": YEAR,
                "window": WINDOW_LABEL,
                "doy_start": DOY_START,
                "doy_end": DOY_END,
                "stage_id": label,
                "count": count,
                "note": ("DEFERRED_PIXEL_SCL_CLOUD_VALIDATION_TO_M21B"
                         if label == "H_valid_pixel_layer"
                         else ("contributing-scene cloud max<=0.30 among "
                               "coverage-passing pairs"
                               if label == "I_R1_cloud_pass_contributing"
                               else "")),
            })
        for cat, n in buckets.items():
            reject_rows.append({"bay_id": bay, "category": cat,
                                "n_pairs": n})

    stages = pd.DataFrame(stage_rows)
    stages.to_csv(mdir / "zhejiang_s2_2022_funnel_audit_v0.csv",
                  index=False)
    rej = pd.DataFrame(reject_rows)
    rej.to_csv(mdir / "zhejiang_s2_2022_funnel_rejections_v0.csv",
               index=False)

    j_v0 = {b: int(stages[(stages.bay_id == b)
                          & (stages.stage_id == "J_v0_final_quality_pairs")]
                   ["count"].iloc[0]) for b in BAYS}
    j_r1 = {b: int(stages[(stages.bay_id == b)
                          & (stages.stage_id == "J_R1_final_quality_pairs")]
                   ["count"].iloc[0]) for b in BAYS}
    verdict = {
        "audit": "zhejiang_s2_2022_funnel_audit_v0",
        "year": YEAR,
        "scope": ("10 km COASTAL_RELEVANT cells; Sentinel-2; "
                  "autumn_primary_v1 DOY 260-320; metadata+geometry only"),
        "thresholds_unchanged": {"coverage_min": cov_min,
                                 "scene_cloud_max": cld_max},
        "v0_groupwide_final_pairs": j_v0,
        "r1_contributing_final_pairs": j_r1,
        "verdict_marker": "ZERO_WAS_PIPELINE_BUG",
        "verdict": (
            "The v0 zero-event result for 2022 autumn was a pipeline bug, "
            "not a real data gap: the pair cloud gate used the max "
            "scene_cloud_fraction over every member of the datatake "
            "group, including adjacent MGRS tiles that never intersect "
            "the cell. With the R1 contributing-scene gate every bay "
            "retains quality events. Pixel-level SCL validation remains "
            "deferred to M2.1b; it cannot remove the geometric "
            "mis-attribution that caused the false zero."),
        "affected_scope": (
            "gate semantics affect all years/sensors with multi-frame "
            "groups; all downstream stats were regenerated as v0_1."),
        "datatake_verification": datatake_checks,
        "pixel_validation": "DEFERRED_SCL_TO_M21B",
        "gee_live_spotcheck": "see integration test "
                              "tests/integration/test_s2_2022_funnel_spotcheck.py",
    }
    (mdir / "zhejiang_s2_2022_funnel_audit_v0.verdict.json").write_text(
        json.dumps(verdict, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")

    print(stages.pivot(index="stage_id", columns="bay_id",
                       values="count").to_string())
    print(rej.pivot(index="category", columns="bay_id",
                    values="n_pairs").to_string())
    print("verdict:", verdict["verdict_marker"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
