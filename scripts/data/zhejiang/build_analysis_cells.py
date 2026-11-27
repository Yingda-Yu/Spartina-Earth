#!/usr/bin/env python3
"""Build the fixed Zhejiang analysis-cell registries (M2.1a2, Issue #12).

Offline geometry only:
    config + pinned GSHHG v2.3.7 shoreline + Tier-C bay envelopes
    -> 5/10/20 km fixed-grid cell registries with deterministic IDs,
       target-independent coastal relevance, per-cell/registry hashes.

No Earth Engine, no labels, no pixels. Existing bay polygons are preserved
and only re-semanticked as PROVISIONAL_BAY_ENVELOPE_V0.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

import geopandas as gpd  # noqa: E402
import pandas as pd  # noqa: E402
import yaml  # noqa: E402
from shapely.geometry.base import BaseGeometry  # noqa: E402
from shapely.ops import transform as shp_transform  # noqa: E402

from spartina.data.zhejiang.cells import (  # noqa: E402
    ANALYSIS_CELL_COLUMNS,
    build_cells,
    cells_are_interior_disjoint,
    grid_spec,
    registry_fingerprint,
)
from spartina.data.zhejiang.rois import (  # noqa: E402
    construct_bay,
    parse_bay_specs,
    polygon_rings,
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config",
                        default=str(REPO_ROOT
                                    / "configs/data/zhejiang_multibay_m21a.yaml"))
    parser.add_argument("--manifest-dir",
                        default=str(REPO_ROOT / "datasets/manifests"))
    args = parser.parse_args()

    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    base = config["base_coastline"]
    shp_path = REPO_ROOT / base["local_path"]
    if not shp_path.exists():
        print(f"ERROR: pinned coastline missing: {shp_path}", file=sys.stderr)
        return 2
    if sha256_file(shp_path) != base["shp_sha256"]:
        print("ERROR: coastline sha256 mismatch", file=sys.stderr)
        return 2

    import pyproj

    specs = parse_bay_specs(config)
    margin = 0.12
    anchor_pts = [(a["lon"], a["lat"])
                  for b in config["rois"] for a in b["anchors"]]
    minx = min(x for x, _ in anchor_pts) - margin
    maxx = max(x for x, _ in anchor_pts) + margin
    miny = min(y for _, y in anchor_pts) - margin
    maxy = max(y for _, y in anchor_pts) + margin
    coast = gpd.read_file(shp_path, bbox=(minx, miny, maxx, maxy))
    land_union = coast.geometry.union_all()
    rings_source = list(coast.geometry)

    projection = config["analysis_crs"]
    to_p = pyproj.Transformer.from_crs(4326, projection, always_xy=True).transform

    envelopes: dict[str, BaseGeometry] = {}
    for spec in specs:
        geom = construct_bay(spec, land_union,
                             polygon_rings(rings_source), projection)
        envelopes[spec.roi_id] = shp_transform(to_p, geom.envelope)

    land_p = shp_transform(to_p, land_union)
    coastline_p = land_p.boundary

    m2 = config["m21a2"]
    belt_m = float(m2["coastal_relevance"]["belt_half_width_m"])
    sizes = [int(s) for s in m2["grid"]["candidate_cell_sizes_m"]]

    all_rows: list[dict[str, Any]] = []
    spec_rows: list[dict[str, Any]] = []
    registry_fps: dict[int, str] = {}
    for size in sizes:
        gs = grid_spec(size)
        records = build_cells(
            gs, envelopes, land_p, coastline_p, coastal_belt_m=belt_m)
        if not cells_are_interior_disjoint(records):
            raise AssertionError(f"{size} m cells fail interior-disjoint")
        fp = registry_fingerprint(records)
        registry_fps[size] = fp
        rows = [r.as_row() for r in records]
        all_rows.extend(rows)
        by_bay: dict[str, dict[str, int]] = {}
        for r in records:
            d = by_bay.setdefault(r.bay_id, {
                "total": 0, "coastal": 0, "inland": 0, "open_water": 0})
            d["total"] += 1
            if r.coastal_relevance == "COASTAL_RELEVANT":
                d["coastal"] += 1
            elif r.coastal_relevance == "NOT_RELEVANT_INLAND":
                d["inland"] += 1
            else:
                d["open_water"] += 1
        for bay_id in sorted(by_bay):
            d = by_bay[bay_id]
            spec_rows.append({
                "grid_id": gs.grid_id,
                "cell_size_m": size,
                "bay_id": bay_id,
                "total_cells": d["total"],
                "coastal_relevant_cells": d["coastal"],
                "not_relevant_inland_cells": d["inland"],
                "not_relevant_open_water_cells": d["open_water"],
            })
        print(f"{size} m grid: {len(records)} cells, "
              f"{sum(d['coastal'] for d in by_bay.values())} coastal, "
              f"registry_fp={fp[:12]}")

    out_dir = Path(args.manifest_dir)
    df = pd.DataFrame(all_rows, columns=list(ANALYSIS_CELL_COLUMNS))
    csv_path = out_dir / "zhejiang_analysis_cells_v0.csv"
    pq_path = out_dir / "zhejiang_analysis_cells_v0.parquet"
    df.to_csv(csv_path, index=False)
    df.to_parquet(pq_path, index=False)

    # grid specs (one row per size)
    grid_rows = []
    for size in sizes:
        gs = grid_spec(size)
        grid_rows.append({
            "grid_id": gs.grid_id,
            "crs": gs.crs,
            "anchor_easting_m": gs.anchor_easting_m,
            "anchor_northing_m": gs.anchor_northing_m,
            "cell_size_m": size,
            "coastal_belt_half_width_m": belt_m,
            "grid_spec_fingerprint": gs.fingerprint(),
            "registry_fingerprint": registry_fps[size],
            "recommended": size == int(m2["grid"]["recommended_cell_size_m"]),
            "recommendation_status": m2["grid"]["recommendation_status"],
        })
    gdf = pd.DataFrame(grid_rows)
    gdf.to_csv(out_dir / "zhejiang_grid_specs_v0.csv", index=False)

    sdf = pd.DataFrame(spec_rows)
    sdf.to_csv(out_dir / "zhejiang_cell_grid_comparison_v0.csv", index=False)
    print(f"wrote {csv_path.relative_to(REPO_ROOT)} ({len(df)} rows), "
          f"grid specs, grid comparison")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
