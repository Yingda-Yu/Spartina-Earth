#!/usr/bin/env python3
"""Run the metadata-only Zhejiang EO observational census (M2.1a).

Per (roi x year x sensor) for 1985-2026 this makes exactly ONE
``getInfo`` call returning scene IDs/dates/tile/orbit/scene-cloud and the
server-side ROI footprint coverage fraction. No pixel statistics, no
exports. Pre-operational years emit SENSOR_NOT_OPERATIONAL without any
EE call.

Outputs:
  work/zhejiang_m21a/zhejiang_eo_scene_census_v0.parquet (raw scenes;
      bytes live outside Git; referenced by the committed summary)
  datasets/manifests/zhejiang_eo_census_summary_v0.csv / .parquet
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

import pandas as pd  # noqa: E402
import yaml  # noqa: E402
from shapely.geometry import shape  # noqa: E402

from spartina.data.gee.auth import initialize as ee_initialize  # noqa: E402
from spartina.data.zhejiang.census import (  # noqa: E402
    SUMMARY_COLUMN_ORDER,
    GroupQuery,
    install_export_guard,
    is_operational,
    query_group_scenes,
    summarize_group,
)
from spartina.data.zhejiang.contracts import SENSORS  # noqa: E402


def utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config",
                        default=str(REPO_ROOT
                                    / "configs/data/zhejiang_multibay_m21a.yaml"))
    parser.add_argument("--rois",
                        default=str(REPO_ROOT
                                    / "datasets/rois/zhejiang_bays_v0.geojson"))
    parser.add_argument("--manifest-dir",
                        default=str(REPO_ROOT / "datasets/manifests"))
    parser.add_argument("--sensors", nargs="*", default=list(SENSORS))
    parser.add_argument("--start-year", type=int, default=None)
    parser.add_argument("--end-year", type=int, default=None)
    parser.add_argument("--sleep-s", type=float, default=0.35)
    parser.add_argument("--dry-run", action="store_true",
                        help="list the EE call plan without initializing EE")
    parser.add_argument("--rebuild-from-scene-table", action="store_true",
                        help="skip EE entirely; recompute summaries from the "
                             "raw scene parquet")
    parser.add_argument("--scene-table", default=None)
    args = parser.parse_args()

    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    y0 = args.start_year or int(config["time_axis"]["start_year"])
    y1 = args.end_year or int(config["time_axis"]["end_year"])
    fc = json.loads(Path(args.rois).read_text(encoding="utf-8"))
    roi_geoms = {f["properties"]["roi_id"]: shape(f["geometry"])
                 for f in fc["features"]}

    plan: list[tuple[str, int, str, tuple[int, int]]] = []
    for roi_id in roi_geoms:
        for year in range(y0, y1 + 1):
            for sensor in args.sensors:
                span = tuple(config["sensors"][sensor]["operational_years"])
                plan.append((roi_id, year, sensor, span))
    ee_calls = sum(1 for _, y, _, span in plan if is_operational(y, span))
    print(f"plan: {len(plan)} groups, {ee_calls} live getInfo calls, "
          f"{len(plan) - ee_calls} SENSOR_NOT_OPERATIONAL (no call)")
    if args.dry_run:
        return 0

    scene_table = Path(args.scene_table or
                       REPO_ROOT / config["census"]["scene_table_path"])
    retrieval_ts = utc_now_iso()
    all_scenes_by_group: dict[tuple[str, int, str],
                              list[dict[str, Any]]] = {}
    all_scenes: list[dict[str, Any]] = []
    if args.rebuild_from_scene_table:
        raw = pd.read_parquet(scene_table)
        # keep the original per-scene retrieval timestamps; summaries get a
        # fresh build timestamp recorded via query_status QUERIED
        all_scenes_by_group = {
            (r.roi_id, int(r.year), r.sensor): []
            for r in raw.itertuples(index=False)
        }
        for r in raw.itertuples(index=False):
            all_scenes_by_group[(r.roi_id, int(r.year), r.sensor)].append(
                r._asdict())
        all_scenes = raw.to_dict("records")
        print(f"offline rebuild from {scene_table.name}: "
              f"{len(all_scenes)} scenes")
    else:
        import ee  # imported only for an actual run

        ee_initialize()
        restore = install_export_guard(ee)
    summaries: list[dict[str, Any]] = []
    for roi_id, year, sensor, span in plan:
        cid = config["sensors"][sensor]["gee_collection"]
        operational = is_operational(year, span)
        scenes: list[dict[str, Any]] = []
        if operational and args.rebuild_from_scene_table:
            scenes = all_scenes_by_group.get((roi_id, year, sensor), [])
        elif operational:
            query = GroupQuery(roi_id, year, sensor, cid)
            last_exc: Exception | None = None
            for attempt in range(3):
                try:
                    scenes = query_group_scenes(
                        ee,
                        geometry=roi_geoms[roi_id],
                        query=query,
                        coverage_scale_m=float(
                            config["census"]["metadata_coverage_scale_m"]),
                    )
                    break
                except Exception as exc:  # transient EE/HTTP errors
                    last_exc = exc
                    wait = 5.0 * (2 ** attempt)
                    print(f"  retry {attempt + 1}/3 after error: {exc} "
                          f"(waiting {wait:.0f}s)", file=sys.stderr)
                    time.sleep(wait)
            else:
                raise RuntimeError(
                    f"census query failed for {roi_id}/{year}/{sensor}"
                ) from last_exc
            for s in scenes:
                s["metadata_retrieval_timestamp"] = retrieval_ts
            time.sleep(args.sleep_s)
        if not args.rebuild_from_scene_table:
            all_scenes.extend(scenes)
        summary = summarize_group(
            roi_id=roi_id, year=year, sensor=sensor,
            collection_id=cid, operational=operational, scenes=scenes,
            retrieval_ts=retrieval_ts,
            season_windows=config["season_windows"],
            scene_cloud_max=float(config["census"]["scene_cloud_max"]),
            footprint_coverage_min=float(
                config["census"]["footprint_coverage_min"]),
        )
        summaries.append(summary)
        if operational:
            print(f"{roi_id} {year} {sensor:9s} "
                  f"scenes={summary['total_scenes']:4d} "
                  f"season={summary['season_candidate_scenes']:3d} "
                  f"gap={summary['gap_status']}")

    if not args.rebuild_from_scene_table:
        restore()
        scene_table.parent.mkdir(parents=True, exist_ok=True)
        scene_df = pd.DataFrame(all_scenes)
        scene_df.to_parquet(scene_table, index=False)

    out_dir = Path(args.manifest_dir)
    summary_df = pd.DataFrame(summaries, columns=list(SUMMARY_COLUMN_ORDER))
    summary_csv = out_dir / "zhejiang_eo_census_summary_v0.csv"
    summary_pq = out_dir / "zhejiang_eo_census_summary_v0.parquet"
    summary_df.to_csv(summary_csv, index=False)
    summary_df.to_parquet(summary_pq, index=False)
    print(f"scenes={len(all_scenes)} -> {scene_table.relative_to(REPO_ROOT)}")
    print(f"summaries={len(summaries)} -> "
          f"{summary_csv.relative_to(REPO_ROOT)} (+parquet)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
