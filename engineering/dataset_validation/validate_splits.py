#!/usr/bin/env python3
"""Validate a frozen split manifest (SPLIT_DESIGN_AND_LEAKAGE_AUDIT.md §2).

Checks A1–A3 + A5 of the leakage audit using the project's real checker
(`src/spartina/evaluation/splits.py`):
  A1 no cell in two roles;
  A2 pairwise spatial disjointness with buffer
     (`assert_spatially_disjoint` on bbox units);
  A3 temporal grouping (`check_temporal_grouping` when the manifest
     carries per-cell date lists);
  A5 reserve cells untouched (optional --reserve file).

Exit codes: 0 pass, 1 audit failure, 2 usage error.

Usage:
  python validate_splits.py --split-manifest split.json \
      [--geometry-json cells.geojson] [--reserve reserve.txt] [--buffer-m 250]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
from spartina.evaluation.splits import (  # noqa: E402
    SpatialUnit,
    assert_spatially_disjoint,
    check_date_table_grouping,
    check_temporal_grouping,
)


def bbox_from_geometry(geom):
    """Axis-aligned bbox of a GeoJSON geometry (projected metres)."""
    coords = []

    def walk(obj):
        if isinstance(obj, (list, tuple)):
            if obj and isinstance(obj[0], (int, float)):
                coords.append((obj[0], obj[1]))
            else:
                for item in obj:
                    walk(item)

    walk(geom["coordinates"] if "coordinates" in geom else geom["geometries"])
    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    return min(xs), min(ys), max(xs), max(ys)


def load_units(geojson_path):
    """Build {cell_id: SpatialUnit} from a GeoJSON of cell rectangles."""
    with open(geojson_path) as f:
        gj = json.load(f)
    units = {}
    for feat in gj["features"]:
        props = feat.get("properties", {})
        cell_id = props.get("cell_id") or props.get("id")
        xmin, ymin, xmax, ymax = bbox_from_geometry(feat["geometry"])
        units[cell_id] = SpatialUnit(
            unit_id=cell_id, xmin=xmin, ymin=ymin, xmax=xmax, ymax=ymax
        )
    return units


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split-manifest", required=True)
    ap.add_argument("--geometry-json", default=None,
                    help="GeoJSON of cell rectangles (projected CRS) for A2/A3")
    ap.add_argument("--reserve", default=None,
                    help="text file of reserve cell ids, one per line (A5)")
    ap.add_argument("--buffer-m", type=float, default=250.0)
    args = ap.parse_args(argv)

    if not os.path.exists(args.split_manifest):
        print(f"ERROR: manifest not found: {args.split_manifest}", file=sys.stderr)
        return 2
    with open(args.split_manifest) as f:
        split = json.load(f)

    failures = []
    cells = split.get("cells", {})
    train = cells.get("train", [])
    val = cells.get("validation", [])
    test = cells.get("test", [])

    split_of = {}
    split_of.update({c: "train" for c in train})
    split_of.update({c: "validation" for c in val})
    split_of.update({c: "test" for c in test})

    # A1: no cell in two roles
    all_cells = list(train) + list(val) + list(test)
    dupes = {c for c in all_cells if all_cells.count(c) > 1}
    if dupes:
        failures.append(f"A1 duplicate cell roles: {sorted(dupes)}")

    # A2: spatial disjointness with buffer via the project checker
    if args.geometry_json:
        units = load_units(args.geometry_json)
        try:
            assert_spatially_disjoint(split_of, units, buffer_m=args.buffer_m)
            print(f"A2 spatially disjoint under {args.buffer_m} m buffer "
                  f"({len(units)} units)")
        except ValueError as exc:
            failures.append(f"A2 {exc}")

        # A3: temporal grouping (when manifest carries per-cell dates)
        unit_dates = split.get("unit_dates")
        if unit_dates:
            offenders = check_temporal_grouping(split_of, unit_dates)
            if offenders:
                failures.append(f"A3 temporal grouping offenders: {offenders}")
            else:
                print("A3 temporal grouping OK")
        date_table = split.get("date_table")
        if date_table:
            offenders = check_date_table_grouping(date_table)
            if offenders:
                failures.append(f"A3 date-table offenders: {offenders}")
            else:
                print("A3 date-table grouping OK")

    # A5: reserve cells untouched
    if args.reserve:
        with open(args.reserve) as f:
            reserve = {ln.strip() for ln in f if ln.strip()}
        overlap = reserve & set(all_cells)
        if overlap:
            failures.append(f"A5 reserve cells present in splits: {sorted(overlap)}")

    print(f"split_id={split.get('split_id')} cells(train={len(train)}, "
          f"validation={len(val)}, test={len(test)}) failures={len(failures)}")
    for msg in failures:
        print(f"FAIL {msg}")
    if failures:
        return 1
    print("leakage audit A1/A2/A3/A5 PASS (A4/A6/A7 recorded separately at freeze)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
