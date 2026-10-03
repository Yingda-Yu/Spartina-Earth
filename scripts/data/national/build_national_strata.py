#!/usr/bin/env python3
"""Attach evidence strata to national coastal cells (Issue #14, section 28).

Two strata are built from products physically obtained and passported in
this repository:

* ``SILVER_2015_POSITIVE`` - the 2015 30 m Landsat product raster local
  copy (SILVER tier; geodata.cn ordered product, see audit docs);
* ``CMSSM_2020_POSITIVE`` - the verified official CM-SSM 2020 sub-meter
  shapefile (SILVER tier published map, never treated as GOLD).

``SILVER_2015_NEARBY`` marks cells inside one 10 km lattice ring of a
positive cell (fixed a-priori radius).  ``UNLABELED_COASTAL`` is the
absence-of-evidence remainder, never an ecological negative.  CMSA,
management and GOLD strata are DESIGNED_NOT_BUILD in this run and are
reported as such.

All flags are produced for the China-Albers lattice at 5/10/20 km.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import rasterio
from pyproj import Transformer
from rasterio.windows import from_bounds
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry

from spartina.data.national.geometry import CHINA_ALBERS_CRS
from spartina.data.national.grid import CELL_SIZE_M, GridKind, parse_cell_id


def _git_commit() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    )
    return proc.stdout.strip() if proc.returncode == 0 else "UNKNOWN"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_albers_cells(csv_path: Path) -> list[tuple[str, int, int]]:
    rows: list[tuple[str, int, int]] = []
    with csv_path.open(newline="", encoding="utf-8") as handle:
        for record in csv.DictReader(handle):
            ref = parse_cell_id(record["cell_id"])
            if ref.kind is not GridKind.CHINA_ALBERS:
                raise ValueError(f"strata build expects Albers cells, got {record['cell_id']}")
            rows.append((record["cell_id"], ref.row, ref.col))
    return rows


def silver_positive_cells(
    cells: list[tuple[str, int, int]], tif_path: Path
) -> tuple[set[str], dict[str, Any]]:
    """Windowed raster check: cell intersects any value-1 2015 pixel."""
    positives: set[str] = set()
    with rasterio.open(tif_path) as dataset:
        to_raster = Transformer.from_crs(CHINA_ALBERS_CRS, dataset.crs, always_xy=True)
        value_name = str(dataset.dtypes[0])
        checked = 0
        for cell_id, row, col in cells:
            x0 = col * CELL_SIZE_M
            x1 = x0 + CELL_SIZE_M
            y0 = row * CELL_SIZE_M
            y1 = y0 + CELL_SIZE_M
            wx0, wy0 = to_raster.transform(x0, y0)
            wx1, wy1 = to_raster.transform(x1, y1)
            minx, maxx = sorted((wx0, wx1))
            miny, maxy = sorted((wy0, wy1))
            window = from_bounds(
                minx - 60, miny - 60, maxx + 60, maxy + 60, dataset.transform
            ).round_lengths().round_offsets()
            window = window.crop(dataset.height, dataset.width)
            if window.width <= 0 or window.height <= 0:
                continue
            block = dataset.read(1, window=window)
            checked += 1
            if (block == 1).any():
                positives.add(cell_id)
    meta = {
        "raster": str(tif_path),
        "positive_value": 1,
        "dtype": value_name,
        "windows_checked": checked,
    }
    return positives, meta


def nearby_cell_ids(
    cells: list[tuple[str, int, int]], positives: set[str]
) -> set[str]:
    """One-lattice-ring (10 km) dilation of positive cells."""
    index = {(row, col): cell_id for cell_id, row, col in cells}
    positive_rc = {(row, col) for cell_id, row, col in cells if cell_id in positives}
    nearby: set[str] = set()
    for row, col in positive_rc:
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                neighbour = index.get((row + dr, col + dc))
                if neighbour is not None and neighbour not in positives:
                    nearby.add(neighbour)
    return nearby


def cmssm_positive_cells(
    cells: list[tuple[str, int, int]], shp_path: Path
) -> set[str]:
    polys = gpd.read_file(shp_path, engine="pyogrio")
    polys_aea = polys.to_crs(CHINA_ALBERS_CRS)
    geometries: list[BaseGeometry] = [
        box(col * CELL_SIZE_M, row * CELL_SIZE_M, (col + 1) * CELL_SIZE_M, (row + 1) * CELL_SIZE_M)
        for _, row, col in cells
    ]
    cell_frame = gpd.GeoDataFrame(
        {"cell_id": [c[0] for c in cells]}, geometry=geometries, crs=CHINA_ALBERS_CRS
    )
    joined = gpd.sjoin(
        cell_frame, polys_aea[["geometry"]], how="inner", predicate="intersects"
    )
    return set(joined["cell_id"].unique())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cells-dir", type=Path, required=True)
    parser.add_argument("--silver2015-tif", type=Path, required=True)
    parser.add_argument("--cmssm-shp", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    widths = (5000, 10000, 20000)
    cell_sets: dict[int, list[tuple[str, int, int]]] = {}
    for width in widths:
        cell_sets[width] = read_albers_cells(
            args.cells_dir / f"cells_china_albers_W{width}.csv"
        )

    silver10, raster_meta = silver_positive_cells(cell_sets[10000], args.silver2015_tif)
    nearby10 = nearby_cell_ids(cell_sets[10000], silver10)

    silver_by_width: dict[int, set[str]] = {10000: silver10}
    for width in (5000, 20000):
        silver_by_width[width], meta_w = silver_positive_cells(
            cell_sets[width], args.silver2015_tif
        )
        raster_meta[f"windows_checked_W{width}"] = meta_w["windows_checked"]
    cmssm = cmssm_positive_cells(cell_sets[10000], args.cmssm_shp)
    cmssm_by_width: dict[int, set[str]] = {10000: cmssm}
    for width in (5000, 20000):
        cmssm_by_width[width] = cmssm_positive_cells(cell_sets[width], args.cmssm_shp)

    stats: dict[str, Any] = {
        "artifact": "china_national_cell_strata",
        "version": "v0",
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "git_commit": _git_commit(),
        "tier_discipline": {
            "SILVER_2015_POSITIVE": (
                "SILVER: published 30 m map product, not field-verified by us"
            ),
            "CMSSM_2020_POSITIVE": (
                "SILVER: published sub-meter map, official archive byte-verified"
            ),
            "SILVER_2015_NEARBY": "derived flag, one 10 km lattice ring, fixed a priori",
            "UNLABELED_COASTAL": (
                "absence of evidence in obtained products; NOT an ecological negative"
            ),
            "CMSA_POSITIVE_HISTORY": (
                "DESIGNED_NOT_BUILD: CMSA archive not obtained "
                "(6.16 GB, purpose-declaration download)"
            ),
                "MANAGEMENT_EVIDENCE_AVAILABLE": (
                    "DESIGNED_NOT_BUILD: no management source registry yet",
                ),
            "GOLD_EVIDENCE_TARGET": "DESIGNED_NOT_BUILD: requires field/UAV/verified campaign data",
        },
        "sources": {
            "silver2015_raster": str(args.silver2015_tif),
            "cmssm_shapefile": str(args.cmssm_shp),
            "cmssm_identity_audit": (
                "docs/audit/vector_reports/30mSpartinaChina__2020__CM-SSM__OFFICIAL_IDENTITY.json"
            ),
        },
        "raster_meta": raster_meta,
        "nearby_radius_m": CELL_SIZE_M,
        "widths": [],
    }

    for width in widths:
        cells = cell_sets[width]
        positive = silver_by_width[width]
        cmssm_set = cmssm_by_width[width]
        out_csv = args.out_dir / f"strata_china_albers_W{width}.csv"
        with out_csv.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                [
                    "cell_id",
                    "silver_2015_positive",
                    "silver_2015_nearby",
                    "cmssm_2020_positive",
                    "unlabeled_coastal",
                ]
            )
            for cell_id, _, _ in cells:
                is_pos = cell_id in positive
                is_near = cell_id in nearby10
                is_cmssm = cell_id in cmssm_set
                writer.writerow(
                    [
                        cell_id,
                        int(is_pos),
                        int(is_near),
                        int(is_cmssm),
                        int(not is_pos),
                    ]
                )
        unlabeled = len(cells) - len(positive)
        stats["widths"].append(
            {
                "width_m": width,
                "coastal_cells": len(cells),
                "silver_2015_positive_cells": len(positive),
                "silver_2015_nearby_only_cells": sum(
                    1
                    for cid in nearby10
                    if cid in {cell[0] for cell in cells}
                ),
                "cmssm_2020_positive_cells": len(cmssm_set),
                "silver_or_cmssm_positive_cells": len(positive | cmssm_set),
                "unlabeled_coastal_cells": unlabeled,
                "strata_csv": out_csv.name,
                "strata_csv_sha256": _sha256(out_csv),
            }
        )

    stats_path = args.out_dir / "strata_stats.json"
    stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n")
    print(f"wrote {stats_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
