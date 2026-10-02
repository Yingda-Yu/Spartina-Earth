#!/usr/bin/env python3
"""Fetch representative frame footprints + verify S2 DATATAKE_IDENTIFIER.

M2.1a2 (Issue #12), metadata-only live Earth Engine step. The 18,435-scene
census carries no footprint geometry; fixed sensor frames repeat across
dates, so ONE representative scene per frame key is enough:

    Sentinel-2 : 8 unique MGRS tiles
    Landsat    : 9 unique WRS path/rows (WRS-2 shared by L5/L7/L8/L9)
    Sentinel-1 : 5 unique (pass, relative orbit) combinations

~22 tiny geometry getInfo calls total. The export guard is live for the
whole process; any ee.batch.Export attempt raises. Frame geometry is
PROVISIONAL representative geometry (especially S1 frames, whose
along-track start can vary slightly between takes).
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

from spartina.data.zhejiang.acquisition import frame_key  # noqa: E402
from spartina.data.zhejiang.census import install_export_guard  # noqa: E402


def representative_scenes(scene_table: Path) -> dict[str, dict[str, Any]]:
    df = pd.read_parquet(scene_table)
    reps: dict[str, dict[str, Any]] = {}
    for row in df.sort_values("scene_id").to_dict("records"):
        key = frame_key(row)
        if key not in reps:
            reps[key] = row
    return reps


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config",
                        default=str(REPO_ROOT
                                    / "configs/data/zhejiang_multibay_m21a.yaml"))
    parser.add_argument("--manifest-dir",
                        default=str(REPO_ROOT / "datasets/manifests"))
    parser.add_argument("--sleep-s", type=float, default=0.25)
    args = parser.parse_args()

    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    scene_table = REPO_ROOT / config["census"]["scene_table_path"]
    out_path = Path(args.manifest_dir) / "zhejiang_eo_frame_footprints_v0.geojson"

    import ee

    from spartina.data.gee import auth
    if not auth.credentials_available():
        print("ERROR: GEE credentials unavailable", file=sys.stderr)
        return 2
    auth.initialize()
    restore = install_export_guard(ee)
    retrieval_ts = datetime.now(UTC).strftime(
        "%Y-%m-%dT%H:%M:%SZ")

    reps = representative_scenes(scene_table)
    print(f"{len(reps)} unique frame keys")
    features: list[dict[str, Any]] = []
    datatake_available: dict[str, object] = {}
    try:
        for key in sorted(reps):
            scene = reps[key]
            image = ee.Image(
                f"{scene['collection_id']}/{scene['scene_id']}")
            geom = image.geometry(30).getInfo()
            props = {
                "frame_key": key,
                "sensor": scene["sensor"],
                "collection_id": scene["collection_id"],
                "representative_scene_id": scene["scene_id"],
                "representative_utc": scene["acquisition_utc"],
                "tile_ref": scene.get("tile_ref"),
                "orbit_direction": scene.get("orbit_direction"),
                "relative_orbit_number": scene.get("relative_orbit_number"),
                "metadata_retrieval_timestamp": retrieval_ts,
                "geometry_status": (
                    "PROVISIONAL_REPRESENTATIVE_FRAME_GEOMETRY"),
            }
            if scene["sensor"] == "sentinel2":
                dt = image.get("DATATAKE_IDENTIFIER").getInfo()
                props["representative_datatake_identifier"] = dt
                datatake_available[key] = dt
            features.append({
                "type": "Feature",
                "geometry": geom,
                "properties": props,
            })
            print(f"  {key:18s} <- {scene['scene_id'][:48]} "
                  f"datatake={datatake_available.get(key, '-')}")
            time.sleep(args.sleep_s)
    finally:
        restore()

    n_dt = sum(1 for v in datatake_available.values() if v)
    print(f"DATATAKE_IDENTIFIER present on {n_dt}/"
          f"{len(datatake_available)} sampled S2 frames")

    doc = {
        "type": "FeatureCollection",
        "name": "zhejiang_eo_frame_footprints_v0",
        "metadata": {
            "status": "PROVISIONAL_REPRESENTATIVE_FRAME_GEOMETRY",
            "n_frames": len(features),
            "metadata_retrieval_timestamp": retrieval_ts,
            "export_guard": "ACTIVE_DURING_FETCH",
            "s2_datatake_property_present_fraction_sampled": (
                n_dt / len(datatake_available) if datatake_available else None),
            "notes": (
                "one representative scene per fixed frame key; S1 frames "
                "are approximate (along-track start varies per take)"
            ),
        },
        "features": features,
    }
    out_path.write_text(json.dumps(doc, ensure_ascii=False),
                        encoding="utf-8")
    print(f"wrote {out_path.relative_to(REPO_ROOT)} "
          f"({out_path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
