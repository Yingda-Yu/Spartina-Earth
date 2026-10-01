#!/usr/bin/env python3
"""Build the Zhejiang three-bay ROI registry (M2.1a, Issue #7).

Deterministic Tier-C derivation only:
    config (named anchors) + GSHHG v2.3.7 shoreline -> polygons, QA,
    fingerprints, CSV/parquet registry + GeoJSON (LGPL attribution).

This script never touches Earth Engine and never downloads imagery.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

import geopandas as gpd  # noqa: E402
import pandas as pd  # noqa: E402
import yaml  # noqa: E402

from spartina.data.zhejiang.contracts import (  # noqa: E402
    ROI_REGISTRY_COLUMNS,
    ROI_SOURCE_COLUMNS,
)
from spartina.data.zhejiang.rois import (  # noqa: E402
    construct_bay,
    geojson_feature,
    parse_bay_specs,
    polygon_rings,
    registry_row,
)

ANCHOR_SNAP_COLUMNS = (
    "roi_id", "anchor_id", "kind", "place_zh",
    "requested_lon", "requested_lat",
    "snapped_lon", "snapped_lat", "snap_distance_m",
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write_csv(path: Path, rows: list[dict], columns: tuple[str, ...]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(columns),
                                extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config",
                        default=str(REPO_ROOT
                                    / "configs/data/zhejiang_multibay_m21a.yaml"))
    parser.add_argument("--manifest-dir",
                        default=str(REPO_ROOT / "datasets/manifests"))
    parser.add_argument("--geojson",
                        default=str(REPO_ROOT
                                    / "datasets/rois/zhejiang_bays_v0.geojson"))
    parser.add_argument("--version", default="v0")
    args = parser.parse_args()

    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    base = config["base_coastline"]
    shp_path = REPO_ROOT / base["local_path"]
    if not shp_path.exists():
        print(f"ERROR: pinned coastline not found at {shp_path}; download "
              f"{base['url']} outside Git and verify checksum.",
              file=sys.stderr)
        return 2
    actual_sha = sha256_file(shp_path)
    if actual_sha != base["shp_sha256"]:
        print(f"ERROR: {shp_path} sha256 mismatch:\n"
              f"  expected {base['shp_sha256']}\n  got      {actual_sha}",
              file=sys.stderr)
        return 2

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
    rings = polygon_rings(list(coast.geometry))

    projection = config["analysis_crs"]
    source_by_id = {s["id"]: s for s in config["sources"]}

    registry_rows: list[dict] = []
    snap_rows: list[dict] = []
    features: list[dict] = []
    for spec in specs:
        geom = construct_bay(spec, land_union, rings, projection)
        src_ids = sorted({
            a.source_id for a in spec.anchors if a.source_id
        } | {"src_gshhg", "src_bay_method_li2020"})
        row = registry_row(
            spec, geom,
            base_coastline_id=base["id"],
            base_coastline_sha256=base["shp_sha256"],
            projection=projection,
            source_ids=src_ids,
        )
        registry_rows.append(row)
        features.append(geojson_feature(spec, geom, row))
        by_id = {a.anchor_id: a for a in spec.anchors}
        for rec in geom.snap_records:
            snap_rows.append({
                "roi_id": spec.roi_id,
                "anchor_id": rec.anchor_id,
                "kind": rec.kind,
                "place_zh": by_id[rec.anchor_id].place_zh,
                "requested_lon": rec.requested_lon,
                "requested_lat": rec.requested_lat,
                "snapped_lon": round(rec.snapped_lon, 6),
                "snapped_lat": round(rec.snapped_lat, 6),
                "snap_distance_m": rec.snap_distance_m,
            })

    manifest_dir = Path(args.manifest_dir)
    registry_csv = manifest_dir / f"zhejiang_roi_registry_{args.version}.csv"
    registry_pq = manifest_dir / f"zhejiang_roi_registry_{args.version}.parquet"
    snaps_csv = manifest_dir / f"zhejiang_roi_anchor_snaps_{args.version}.csv"
    sources_csv = manifest_dir / f"zhejiang_roi_source_audit_{args.version}.csv"

    write_csv(registry_csv, registry_rows, ROI_REGISTRY_COLUMNS)
    pd.DataFrame(registry_rows, columns=list(ROI_REGISTRY_COLUMNS)).to_parquet(
        registry_pq, index=False)
    write_csv(snaps_csv, snap_rows, ANCHOR_SNAP_COLUMNS)

    source_rows = []
    for source in config["sources"]:
        source_rows.append({
            "source_id": source["id"],
            "applies_to": "|".join(source.get("applies_to", [])),
            "publisher": source["publisher"],
            "title": source["title"],
            "url": source["url"],
            "doi": source["doi"],
            "publication_date": source["publication_date"],
            "access_date": source["access_date"],
            "geometry_type": source["geometry_type"],
            "crs": source["crs"],
            "boundary_meaning": source["boundary_meaning"],
            "license": source["license"],
            "status": source["status"],
            "notes": source.get("notes", ""),
        })
    write_csv(sources_csv, source_rows, ROI_SOURCE_COLUMNS)

    geojson_path = Path(args.geojson)
    geojson_path.parent.mkdir(parents=True, exist_ok=True)
    geojson_path.write_text(json.dumps(
        {
            "type": "FeatureCollection",
            "name": "zhejiang_bays_m21a_v0_provisional_tier_c",
            "metadata": {
                "status": "PROVISIONAL_TIER_C_DERIVED",
                "not_official": True,
                "base_coastline_id": base["id"],
                "base_coastline_sha256": base["shp_sha256"],
                "license_of_base": base["license"],
                "attribution": (
                    "GSHHG v2.3.7 (c) University of Hawaii and NOAA; "
                    "Wessel & Smith 1996, DOI 10.1029/96JB00104"
                ),
                "derivation": (
                    "named sections snapped to nearest GSHHG vertex within "
                    "per-anchor radii; water=envelope-land; +2 km onshore "
                    "belt; see configs/data/zhejiang_multibay_m21a.yaml"
                ),
            },
            "features": features,
        },
        ensure_ascii=False, indent=1,
    ), encoding="utf-8")

    for row in registry_rows:
        print(
            f"{row['roi_id']}: water={row['water_area_km2']} km2 "
            f"belt={row['onshore_belt_area_km2']} "
            f"roi={row['roi_area_km2']} "
            f"published={row['published_area_km2']} "
            f"delta={row['published_area_delta_pct']}% "
            f"valid={row['geometry_is_valid']} "
            f"fp={row['geometry_fingerprint'][:12]}"
        )
    print(f"wrote {registry_csv.relative_to(REPO_ROOT)}, "
          f"{registry_pq.relative_to(REPO_ROOT)}, "
          f"{sources_csv.relative_to(REPO_ROOT)}, "
          f"{snaps_csv.relative_to(REPO_ROOT)}, "
          f"{geojson_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
