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
from spartina.data.national.strata import (
    BOOLEAN_FLAGS,
    assign_priority_stratum,
    stratum_counts,
)


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
    cells: list[tuple[str, int, int]], positives: set[str], ring: int = 1
) -> set[str]:
    """Lattice dilation of positive cells by ``ring`` cells per side.

    The ring width is chosen per grid so the physical band stays ~10 km:
    1 ring at W10000/W20000, 2 rings at W5000.  IDs never cross grid
    files: each width has its own index space (the shared ``CNA10K``
    prefix is disambiguated by file/grid width).
    """
    index = {(row, col): cell_id for cell_id, row, col in cells}
    positive_rc = {(row, col) for cell_id, row, col in cells if cell_id in positives}
    offsets = range(-ring, ring + 1)
    nearby: set[str] = set()
    for row, col in positive_rc:
        for dr in offsets:
            for dc in offsets:
                if dr == 0 and dc == 0:
                    continue
                neighbour = index.get((row + dr, col + dc))
                if neighbour is not None and neighbour not in positives:
                    nearby.add(neighbour)
    return nearby


NEARBY_RING_CELLS: dict[int, int] = {5000: 2, 10000: 1, 20000: 1}


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

    nearby_by_width: dict[int, set[str]] = {
        width: nearby_cell_ids(cell_sets[width], silver_by_width[width], ring)
        for width, ring in NEARBY_RING_CELLS.items()
    }

    stats: dict[str, Any] = {
        "artifact": "china_national_cell_strata",
        "version": "v0",
        "schema": "orthogonal_boolean_flags_plus_exclusive_priority_strata",
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "git_commit": _git_commit(),
        "priority_order": [
            "GOLD_EVIDENCE",
            "MULTI_PRODUCT_SILVER_POSITIVE",
            "SILVER_2015_POSITIVE_ONLY",
            "CMSSM_2020_POSITIVE_ONLY",
            "NEAR_SILVER_UNLABELED",
            "UNLABELED_COASTAL",
        ],
        "boolean_flags": list(BOOLEAN_FLAGS),
        "designed_not_build_flags": {
            "gold_evidence": "requires field/UAV/expert-verified campaign data",
            "cmsa_positive_history": (
                "CMSA archive not obtained (6.16 GB, purpose-declaration download)"
            ),
            "management_evidence_available": "no management source registry yet",
        },
        "tier_discipline": {
            "MULTI_PRODUCT_SILVER_POSITIVE": (
                "SILVER in two products (2015 30 m raster and 2020 CM-SSM); "
                "not field-verified by us"
            ),
            "SILVER_2015_POSITIVE_ONLY": (
                "SILVER: published 30 m map product, not field-verified by us"
            ),
            "CMSSM_2020_POSITIVE_ONLY": (
                "SILVER: published sub-meter map, official archive byte-verified"
            ),
            "NEAR_SILVER_UNLABELED": (
                "one 10 km lattice ring from a 2015-positive cell; "
                "no positive evidence in either obtained product"
            ),
            "UNLABELED_COASTAL": (
                "absence of evidence in obtained products; NOT an ecological negative"
            ),
            "GOLD_EVIDENCE": "DESIGNED_NOT_BUILD at v0",
        },
        "sources": {
            "silver2015_raster": str(args.silver2015_tif),
            "cmssm_shapefile": str(args.cmssm_shp),
            "cmssm_identity_audit": (
                "docs/audit/vector_reports/30mSpartinaChina__2020__CM-SSM__OFFICIAL_IDENTITY.json"
            ),
        },
        "raster_meta": raster_meta,
        "nearby_radius_m": 10000,
        "nearby_ring_cells_by_width": NEARBY_RING_CELLS,
        "widths": [],
    }

    for width in widths:
        cells = cell_sets[width]
        positive = silver_by_width[width]
        cmssm_set = cmssm_by_width[width]
        nearby_set = nearby_by_width[width]
        out_csv = args.out_dir / f"strata_china_albers_W{width}.csv"
        rows_for_validation: list[dict[str, object]] = []
        labels: list[str] = []
        flag_totals = {flag: 0 for flag in BOOLEAN_FLAGS}
        with out_csv.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["cell_id", *BOOLEAN_FLAGS, "exclusive_stratum"])
            for cell_id, _, _ in cells:
                is_pos = cell_id in positive
                is_cmssm = cell_id in cmssm_set
                is_near = cell_id in nearby_set and not is_pos
                row: dict[str, object] = {
                    "gold_evidence": 0,
                    "silver_2015_positive": int(is_pos),
                    "cmssm_2020_positive": int(is_cmssm),
                    "silver_2015_nearby": int(is_near),
                    "multi_product_positive": int(is_pos and is_cmssm),
                    "cmsa_positive_history": 0,
                    "management_evidence_available": 0,
                }
                stratum = assign_priority_stratum(
                    silver_2015_positive=is_pos,
                    cmssm_2020_positive=is_cmssm,
                    silver_2015_nearby=is_near,
                )
                for flag, value in row.items():
                    assert isinstance(value, int)
                    flag_totals[flag] += value
                labels.append(stratum)
                writer.writerow([cell_id, *(row[f] for f in BOOLEAN_FLAGS), stratum])
                check_row = dict(row)
                check_row["exclusive_stratum"] = stratum
                rows_for_validation.append(check_row)
        counts = stratum_counts(labels)
        assert sum(counts.values()) == len(cells), "strata do not partition the domain"
        stats["widths"].append(
            {
                "width_m": width,
                "coastal_cells": len(cells),
                "priority_stratum_counts": counts,
                "orthogonal_flag_cells": flag_totals,
                "silver_or_cmssm_positive_cells": len(positive | cmssm_set),
                "partition_check": "exclusive_stratum_counts_sum_to_coastal_cells",
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
